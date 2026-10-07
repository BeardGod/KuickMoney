"""Command line entry point: python -m kuick_analyst <command>."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from . import espn, odds
from .leagues import LEAGUES, League, resolve
from .learning import ANGLES, add_lesson, unknown_angles
from .ledger import Ledger
from .notify import send_telegram
from .report import write_daily_index, write_league_report, write_performance

log = logging.getLogger("kuick_analyst")
HOME = Path(os.environ.get("KUICK_HOME", Path(__file__).resolve().parent.parent))
EASTERN = ZoneInfo("America/New_York")
LESSONS = HOME / "data" / "lessons.md"


def today() -> dt.date:
    return dt.datetime.now(EASTERN).date()


def build_slate(league: League, date: dt.date, max_games: int,
                session: requests.Session) -> list[dict[str, Any]]:
    games = [g for g in espn.fetch_games(league, date, session) if g.state == "pre"]
    market_events: list[dict[str, Any]] = []
    if league.odds_api_key and os.environ.get("ODDS_API_KEY"):
        try:
            market_events = odds.fetch_market_odds(league.odds_api_key, session=session)
        except requests.RequestException as e:
            log.warning("Odds API failed for %s: %s", league.key, e)
    # Games with a posted line and ranked teams first; big college slates get trimmed.
    games.sort(key=lambda g: (g.line.details is None, not (g.home.rank or g.away.rank), g.start))
    slate = []
    for g in games[:max_games]:
        d = g.to_dict()
        ev = odds.match_event(market_events, g.home.name, g.away.name)
        if ev:
            d["market"] = odds.summarize_event(ev)["best_prices"]
        slate.append(d)
    return slate


def cmd_slate(args: argparse.Namespace) -> int:
    s = requests.Session()
    for lg in resolve(args.leagues):
        try:
            slate = build_slate(lg, args.date, args.max_games, s)
        except requests.RequestException as e:
            print(f"\n== {lg.name}: could not load schedule ({e.__class__.__name__})")
            continue
        print(f"\n== {lg.name}: {len(slate)} upcoming game(s)")
        for g in slate:
            line = g["line"]
            print(f"  [{g['id']}] {g['away']['name']} @ {g['home']['name']}  {g['status']}  "
                  f"{line.get('details') or ''} O/U {line.get('total') or '-'}")
    return 0


def grade(ledger: Ledger, session: requests.Session) -> int:
    def fetch(league_key: str, date: str) -> list[espn.Game]:
        return espn.fetch_games(LEAGUES[league_key], dt.date.fromisoformat(date), session)
    n = ledger.grade(fetch)
    ledger.save()
    write_performance(HOME / "reports" / "performance.md", ledger.summary(), ledger.picks)
    return n


def cmd_grade(args: argparse.Namespace) -> int:
    ledger = Ledger(HOME / "data" / "ledger.json")
    n = grade(ledger, requests.Session())
    print(f"Graded {n} pick(s).")
    print(ledger.track_record_text(lessons_path=LESSONS))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .analyst import Analyst  # imported lazily so `slate`/`grade` work without the SDK

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.error("ANTHROPIC_API_KEY is not set. Add it as an environment variable "
                  "(or a GitHub Actions repository secret) and run again.")
        return 2

    session = requests.Session()
    ledger = Ledger(HOME / "data" / "ledger.json")
    log.info("Graded %d pending pick(s)", grade(ledger, session))
    track_record = ledger.track_record_text(lessons_path=LESSONS)

    date_s = args.date.isoformat()
    out_dir = HOME / "reports" / date_s
    analyst = Analyst(model=args.model, effort=args.effort, max_searches=args.max_searches)
    analyses, skipped, failed = [], [], []
    for lg in resolve(args.leagues):
        try:
            slate = build_slate(lg, args.date, args.max_games, session)
        except requests.RequestException as e:
            log.error("Could not load %s schedule: %s", lg.name, e)
            skipped.append(lg.name)
            continue
        if not slate:
            skipped.append(lg.name)
            continue
        log.info("Analyzing %s: %d game(s)", lg.name, len(slate))
        try:
            a = analyst.analyze(lg.key, lg.name, date_s, slate, track_record)
        except Exception as e:  # keep going with the other leagues
            log.exception("Analysis failed for %s: %s", lg.name, e)
            failed.append(lg.name)
            continue
        write_league_report(out_dir, date_s, lg.name, a)
        ledger.add(date_s, a.picks)
        ledger.save()
        analyses.append((lg.name, a))
        log.info("%s: %d pick(s)", lg.name, len(a.picks))

    index = write_daily_index(out_dir, date_s, analyses, skipped, track_record)
    write_performance(HOME / "reports" / "performance.md", ledger.summary(), ledger.picks)
    all_picks = [p for _, a in analyses for p in a.picks]
    if send_telegram(date_s, all_picks):
        log.info("Telegram alert sent")
    print(f"Report: {index}")
    if failed:
        log.error("Analysis failed for: %s", ", ".join(failed))
        return 1
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Save an analysis produced outside the API path (e.g. by a Claude Code session)."""
    from .analyst import Analysis

    data = json.loads(Path(args.file).read_text())
    league = LEAGUES[data["league"]]
    date_s = args.date.isoformat()
    a = Analysis(league=league.key, report_markdown=data.get("report_markdown", ""),
                 picks=[{**p, "league": league.key} for p in data.get("picks", [])],
                 sources=data.get("sources", []), stop_reason="claude-code")
    out_dir = HOME / "reports" / date_s
    write_league_report(out_dir, date_s, league.name, a)
    (out_dir / f"{league.key}.json").write_text(json.dumps(data, indent=1))
    for p in a.picks:
        bad = unknown_angles(p.get("angles") or [])
        if not p.get("angles"):
            log.warning("Pick %s has no angles; tag it so results can be tracked by reasoning.", p.get("selection"))
        elif bad:
            log.warning("Unknown angle(s) %s on %s. Known: %s", bad, p.get("selection"), ", ".join(ANGLES))
    ledger = Ledger(HOME / "data" / "ledger.json")
    added, removed = ledger.replace_pending(date_s, league.key, a.picks)
    ledger.save()
    if removed > added:
        print(f"{league.name}: dropped {removed - added} pick(s) no longer on the card.")

    analyses = []
    for f in sorted(out_dir.glob("*.json")):
        d = json.loads(f.read_text())
        lg = LEAGUES[d["league"]]
        analyses.append((lg.name, Analysis(league=lg.key, report_markdown="", sources=[],
                                           picks=[{**p, "league": lg.key} for p in d.get("picks", [])])))
    write_daily_index(out_dir, date_s, analyses, [], ledger.track_record_text(lessons_path=LESSONS))
    write_performance(HOME / "reports" / "performance.md", ledger.summary(), ledger.picks)
    print(f"{league.name}: recorded {added} new pick(s) -> {out_dir / (league.key + '.md')}")
    return 0


def cmd_settle(args: argparse.Namespace) -> int:
    """Grade pending picks for one game from a final score (no ESPN access needed)."""
    ledger = Ledger(HOME / "data" / "ledger.json")
    game = espn.Game(id=args.game_id, league=args.league, start="", state="post", status="Final",
                     home=espn.Team(args.home, args.home, score=args.home_score),
                     away=espn.Team(args.away, args.away, score=args.away_score))
    n = ledger.grade(lambda lg, d: [game] if lg == args.league else [])
    ledger.save()
    write_performance(HOME / "reports" / "performance.md", ledger.summary(), ledger.picks)
    print(f"Settled {n} pick(s) for {args.game_id}.")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    """Record the closing price/line for a game's picks (for closing line value)."""
    ledger = Ledger(HOME / "data" / "ledger.json")
    n = ledger.set_closing(args.date.isoformat(), args.game_id, args.odds, args.line, args.market)
    ledger.save()
    write_performance(HOME / "reports" / "performance.md", ledger.summary(), ledger.picks)
    print(f"Closing line set on {n} pick(s) for {args.game_id}.")
    return 0 if n else 1


def cmd_tag(args: argparse.Namespace) -> int:
    angles = args.angles.split(",")
    if bad := unknown_angles(angles):
        print(f"Unknown angle(s): {bad}. Known: {', '.join(ANGLES)}")
        return 1
    ledger = Ledger(HOME / "data" / "ledger.json")
    n = ledger.tag(args.date.isoformat(), args.game_id, angles, args.market)
    ledger.save()
    write_performance(HOME / "reports" / "performance.md", ledger.summary(), ledger.picks)
    print(f"Tagged {n} pick(s) for {args.game_id}: {', '.join(angles)}")
    return 0 if n else 1


def cmd_lesson(args: argparse.Namespace) -> int:
    add_lesson(LESSONS, args.date.isoformat(), args.text, args.pick_id)
    print(f"Lesson added to {LESSONS}")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Print what the analyst should take into account before picking."""
    ledger = Ledger(HOME / "data" / "ledger.json")
    print(ledger.track_record_text(lessons_path=LESSONS))
    print("\nAngles: " + "; ".join(f"{k} = {v}" for k, v in ANGLES.items()))
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    for p in Ledger(HOME / "data" / "ledger.json").pending():
        print(json.dumps({k: p.get(k) for k in ("date", "league", "game_id", "matchup", "selection")}))
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    """Run forever, producing a fresh card every N hours (for a PC or server)."""
    while True:
        args.date = today()
        try:
            cmd_run(args)
        except Exception:
            log.exception("Scheduled run failed")
        log.info("Sleeping %.1f hours", args.every_hours)
        time.sleep(args.every_hours * 3600)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kuick_analyst", description="AI sports betting analyst powered by Claude")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--date", type=dt.date.fromisoformat, default=today(), help="YYYY-MM-DD (default: today ET)")
        sp.add_argument("--leagues", type=lambda s: s.split(","), default=None,
                        help=f"comma list or 'all' (default). Options: {','.join(LEAGUES)}")
        sp.add_argument("--max-games", type=int, default=40, help="max games per league sent for analysis")

    def analysis(sp: argparse.ArgumentParser) -> None:
        common(sp)
        sp.add_argument("--model", default="claude-opus-5-5")
        sp.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
        sp.add_argument("--max-searches", type=int, default=20, help="web searches per league")

    sp = sub.add_parser("run", help="grade old picks, research today's games and write the card")
    analysis(sp)
    sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("schedule", help="keep running every N hours")
    analysis(sp)
    sp.add_argument("--every-hours", type=float, default=6)
    sp.set_defaults(func=cmd_schedule)
    sp = sub.add_parser("slate", help="list today's games and lines (no AI, free)")
    common(sp)
    sp.set_defaults(func=cmd_slate)
    sp = sub.add_parser("grade", help="grade pending picks and update performance.md")
    sp.set_defaults(func=cmd_grade)

    # Commands for running the analyst from a Claude Code session (no API key).
    sp = sub.add_parser("record", help="save a league analysis JSON file (Claude Code mode)")
    sp.add_argument("file")
    sp.add_argument("--date", type=dt.date.fromisoformat, default=today())
    sp.set_defaults(func=cmd_record)
    sp = sub.add_parser("settle", help="grade pending picks for a game from its final score")
    sp.add_argument("--league", required=True, choices=list(LEAGUES))
    sp.add_argument("--game-id", required=True)
    sp.add_argument("--home", required=True)
    sp.add_argument("--away", required=True)
    sp.add_argument("--home-score", type=int, required=True)
    sp.add_argument("--away-score", type=int, required=True)
    sp.set_defaults(func=cmd_settle)
    sp = sub.add_parser("pending", help="list picks waiting to be graded")
    sp.set_defaults(func=cmd_pending)

    # Feedback loop.
    sp = sub.add_parser("close", help="record a game's closing odds/line for closing line value")
    sp.add_argument("--date", type=dt.date.fromisoformat, required=True, help="card date of the pick")
    sp.add_argument("--game-id", required=True)
    sp.add_argument("--odds", type=int, required=True, help="closing American odds for the side we bet")
    sp.add_argument("--line", type=float, default=None, help="closing spread for our side, or closing total")
    sp.add_argument("--market", choices=["spread", "moneyline", "total"], default=None)
    sp.set_defaults(func=cmd_close)
    sp = sub.add_parser("tag", help="set the angles (reasons) on a game's picks")
    sp.add_argument("--date", type=dt.date.fromisoformat, required=True)
    sp.add_argument("--game-id", required=True)
    sp.add_argument("--angles", required=True, help=f"comma list from: {','.join(ANGLES)}")
    sp.add_argument("--market", choices=["spread", "moneyline", "total"], default=None)
    sp.set_defaults(func=cmd_tag)
    sp = sub.add_parser("lesson", help="append a post-mortem note the analyst reads before picking")
    sp.add_argument("text")
    sp.add_argument("--date", type=dt.date.fromisoformat, default=today())
    sp.add_argument("--pick-id", default=None)
    sp.set_defaults(func=cmd_lesson)
    sp = sub.add_parser("learn", help="show calibration, CLV, results by angle and recent lessons")
    sp.set_defaults(func=cmd_learn)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return args.func(args)
