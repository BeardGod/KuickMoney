"""ESPN public scoreboard client (no API key required).

Pulls every game on a date for a league, including records, rankings, venue,
weather and whatever betting line ESPN publishes for the game.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from .leagues import League

BASE = "https://site.api.espn.com/apis/site/v2/sports"
TIMEOUT = 20


@dataclass
class Team:
    name: str
    abbr: str
    record: str | None = None
    rank: int | None = None
    score: int | None = None


@dataclass
class Line:
    provider: str | None = None
    details: str | None = None  # e.g. "KC -3.5"
    spread: float | None = None  # home-team spread
    total: float | None = None
    home_ml: int | None = None
    away_ml: int | None = None


@dataclass
class Game:
    id: str
    league: str
    start: str  # ISO-8601 UTC
    state: str  # pre | in | post
    status: str  # human readable, e.g. "Final", "Sun, Oct 5th at 1:00 PM EDT"
    home: Team
    away: Team
    venue: str | None = None
    neutral: bool = False
    weather: str | None = None
    broadcast: str | None = None
    line: Line = field(default_factory=Line)

    @property
    def matchup(self) -> str:
        return f"{self.away.name} @ {self.home.name}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _int(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _team(c: dict[str, Any]) -> Team:
    t = c.get("team", {})
    records = c.get("records") or []
    rank = (c.get("curatedRank") or {}).get("current")
    return Team(
        name=t.get("displayName") or t.get("name") or "?",
        abbr=t.get("abbreviation") or "",
        record=records[0].get("summary") if records else None,
        rank=rank if isinstance(rank, int) and 0 < rank < 99 else None,
        score=_int(c.get("score")),
    )


def _line(comp: dict[str, Any]) -> Line:
    odds = comp.get("odds") or []
    if not odds:
        return Line()
    o = odds[0]
    return Line(
        provider=(o.get("provider") or {}).get("name"),
        details=o.get("details"),
        spread=_float(o.get("spread")),
        total=_float(o.get("overUnder")),
        home_ml=_int((o.get("homeTeamOdds") or {}).get("moneyLine")),
        away_ml=_int((o.get("awayTeamOdds") or {}).get("moneyLine")),
    )


def parse_scoreboard(data: dict[str, Any], league: League) -> list[Game]:
    games: list[Game] = []
    for ev in data.get("events", []):
        comps = ev.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in sides or "away" not in sides:
            continue
        status = (ev.get("status") or comp.get("status") or {}).get("type", {})
        weather = ev.get("weather") or comp.get("weather")
        broadcasts = comp.get("broadcasts") or []
        games.append(
            Game(
                id=str(ev.get("id")),
                league=league.key,
                start=ev.get("date", ""),
                state=status.get("state", "pre"),
                status=status.get("detail") or status.get("description") or "",
                home=_team(sides["home"]),
                away=_team(sides["away"]),
                venue=(comp.get("venue") or {}).get("fullName"),
                neutral=bool(comp.get("neutralSite")),
                weather=(
                    f"{weather.get('displayValue', '')} {weather.get('temperature', '')}F".strip()
                    if isinstance(weather, dict) else None
                ),
                broadcast=", ".join(n for b in broadcasts for n in b.get("names", [])) or None,
                line=_line(comp),
            )
        )
    return games


def fetch_games(league: League, date: dt.date, session: requests.Session | None = None) -> list[Game]:
    s = session or requests.Session()
    params = {"dates": date.strftime("%Y%m%d"), "limit": "500", **dict(league.espn_params)}
    url = f"{BASE}/{league.espn_sport}/{league.espn_league}/scoreboard"
    resp = s.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_scoreboard(resp.json(), league)
