"""Command line entry point: python -m kuick_analyst <command>."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from . import espn, odds
from .leagues import LEAGUES, League, resolve
from .ledger import Ledger
from .notify import send_telegram
from .report import write_daily_index, write_league_report, write_performance

log = logging.getLogger("kuick_analyst")
HOME = Path(os.environ.get("KUICK_HOME", Path(__file__).resolve().parent.parent))
EASTERN = ZoneInfo("America/New_York")


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
    print(ledger.track_record_text())
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
    track_record = ledger.track_record_text()

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

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return args.func(args)
