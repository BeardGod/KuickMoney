"""Pick ledger: stores every recommendation, grades it from final scores and
reports the track record (which is fed back to the analyst for calibration)."""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .espn import Game
from .leagues import LEAGUES
from .learning import learning_text
from .odds import profit

GRADEABLE = {"spread", "moneyline", "total"}


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.picks: list[dict[str, Any]] = json.loads(path.read_text()) if path.exists() else []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.picks, indent=1, sort_keys=True))

    def add(self, date: str, picks: list[dict[str, Any]]) -> int:
        existing = {p["id"] for p in self.picks}
        added = 0
        for p in picks:
            pid = f"{date}:{p.get('league')}:{p.get('game_id')}:{p.get('market')}:{p.get('side')}"
            if pid in existing:
                continue
            gradeable = p.get("market") in GRADEABLE and p.get("side") != "other"
            try:
                odds = int(p.get("odds"))
            except (TypeError, ValueError):
                odds = -110
            p = {**p, "odds": odds if odds else -110}
            self.picks.append({**p, "id": pid, "date": date,
                               "status": "pending" if gradeable else "manual", "result_units": None})
            existing.add(pid)
            added += 1
        return added

    def replace_pending(self, date: str, league: str, picks: list[dict[str, Any]]) -> tuple[int, int]:
        """Re-record a league's card: ungraded picks for that date/league are replaced
        by `picks`, so a rerun can update or drop picks. Graded picks are never touched."""
        keep = [p for p in self.picks
                if not (p["date"] == date and p.get("league") == league and p["status"] in ("pending", "manual"))]
        removed = len(self.picks) - len(keep)
        self.picks = keep
        return self.add(date, picks), removed

    def find(self, date: str, game_id: str, market: str | None = None) -> list[dict[str, Any]]:
        return [p for p in self.picks if p["date"] == date and str(p.get("game_id")) == game_id
                and (market is None or p.get("market") == market)]

    def set_closing(self, date: str, game_id: str, odds: int, line: float | None,
                    market: str | None = None) -> int:
        rows = self.find(date, game_id, market)
        for p in rows:
            p["closing_odds"] = odds
            if line is not None:
                p["closing_line"] = line
        return len(rows)

    def tag(self, date: str, game_id: str, angles: list[str], market: str | None = None) -> int:
        rows = self.find(date, game_id, market)
        for p in rows:
            p["angles"] = angles
        return len(rows)

    def pending(self) -> list[dict[str, Any]]:
        return [p for p in self.picks if p["status"] == "pending"]

    def grade(self, fetch: Callable[[str, str], list[Game]]) -> int:
        """Grade pending picks. `fetch(league_key, date)` returns that day's games."""
        cache: dict[tuple[str, str], dict[str, Game]] = {}
        graded = 0
        for p in self.pending():
            key = (p["league"], p["date"])
            if key not in cache:
                try:
                    cache[key] = {g.id: g for g in fetch(*key)}
                except Exception:  # network hiccup; try again next run
                    cache[key] = {}
            game = cache[key].get(str(p.get("game_id")))
            if game is None or game.state != "post":
                continue
            outcome = grade_pick(p, game)
            if outcome is None:
                continue
            p["status"] = outcome
            p["final"] = f"{game.away.abbr} {game.away.score} - {game.home.abbr} {game.home.score}"
            units = float(p.get("units") or 1)
            p["result_units"] = round(
                units * profit(int(p["odds"])) if outcome == "win" else -units if outcome == "loss" else 0.0, 3)
            graded += 1
        return graded

    def summary(self, since_days: int | None = None, today: dt.date | None = None) -> dict[str, Any]:
        today = today or dt.date.today()
        rows = [p for p in self.picks if p["status"] in ("win", "loss", "push")]
        if since_days is not None:
            cutoff = (today - dt.timedelta(days=since_days)).isoformat()
            rows = [p for p in rows if p["date"] >= cutoff]

        def agg(items: list[dict[str, Any]]) -> dict[str, Any]:
            w = sum(p["status"] == "win" for p in items)
            l = sum(p["status"] == "loss" for p in items)
            pu = sum(p["status"] == "push" for p in items)
            risked = sum(float(p.get("units") or 1) for p in items if p["status"] != "push")
            net = sum(p["result_units"] or 0 for p in items)
            return {"record": f"{w}-{l}-{pu}", "units": round(net, 2),
                    "roi": round(net / risked * 100, 1) if risked else 0.0, "bets": len(items)}

        by_league: dict[str, list] = defaultdict(list)
        by_market: dict[str, list] = defaultdict(list)
        for p in rows:
            by_league[p["league"]].append(p)
            by_market[p["market"]].append(p)
        return {"overall": agg(rows),
                "by_league": {k: agg(v) for k, v in sorted(by_league.items())},
                "by_market": {k: agg(v) for k, v in sorted(by_market.items())},
                "pending": len(self.pending())}

    def track_record_text(self, today: dt.date | None = None, lessons_path: Path | None = None) -> str:
        s = self.summary(since_days=60, today=today)
        if not s["overall"]["bets"]:
            return "No graded picks yet."
        return self._record_lines(s) + "\n\n" + learning_text(self.picks, lessons_path, today)

    @staticmethod
    def _record_lines(s: dict[str, Any]) -> str:
        lines = [f"Last 60 days overall: {s['overall']['record']}, {s['overall']['units']:+} units, "
                 f"ROI {s['overall']['roi']}%"]
        lines += [f"- {k}: {v['record']}, {v['units']:+}u, ROI {v['roi']}%" for k, v in s["by_league"].items()]
        lines += [f"- {k} bets: {v['record']}, {v['units']:+}u, ROI {v['roi']}%" for k, v in s["by_market"].items()]
        return "\n".join(lines)


def grade_pick(p: dict[str, Any], g: Game) -> str | None:
    hs, as_ = g.home.score, g.away.score
    if hs is None or as_ is None:
        return None
    side, market, line = p.get("side"), p.get("market"), p.get("line")
    if market == "moneyline":
        if side == "draw":
            return "win" if hs == as_ else "loss"
        if side not in ("home", "away"):
            return None
        if hs == as_:
            # Soccer moneylines are three-way: a draw loses a bet on either team.
            league = LEAGUES.get(p.get("league", ""))
            return "loss" if league and league.espn_sport == "soccer" else "push"
        return "win" if (hs > as_) == (side == "home") else "loss"
    if line is None:
        return None
    line = float(line)
    if market == "spread" and side in ("home", "away"):
        margin = (hs - as_ if side == "home" else as_ - hs) + line
    elif market == "total" and side in ("over", "under"):
        margin = (hs + as_ - line) * (1 if side == "over" else -1)
    else:
        return None
    return "win" if margin > 0 else "loss" if margin < 0 else "push"
