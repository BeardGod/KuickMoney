"""Betting math and an optional multi-sportsbook odds feed (The Odds API).

The Odds API (https://the-odds-api.com) has a free tier; set ODDS_API_KEY to
enable line shopping across books. Without it the app falls back to the
single line ESPN publishes.
"""

from __future__ import annotations

import os
import re
from typing import Any

import requests

ODDS_API = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
TIMEOUT = 20


# --- odds math -------------------------------------------------------------

def american_to_decimal(odds: int) -> float:
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def implied_probability(odds: int) -> float:
    """Break-even win probability for American odds (includes the vig)."""
    return 1 / american_to_decimal(odds)


def no_vig_probabilities(odds: list[int]) -> list[float]:
    """Remove the bookmaker margin from a set of mutually exclusive prices."""
    raw = [implied_probability(o) for o in odds]
    total = sum(raw)
    return [p / total for p in raw]


def expected_value(prob: float, odds: int) -> float:
    """Expected profit per 1 unit staked."""
    return prob * (american_to_decimal(odds) - 1) - (1 - prob)


def kelly_fraction(prob: float, odds: int, multiplier: float = 0.25) -> float:
    """Fractional Kelly stake as a share of bankroll (0 when there is no edge)."""
    b = american_to_decimal(odds) - 1
    f = (b * prob - (1 - prob)) / b
    return max(0.0, f * multiplier)


def profit(odds: int, stake: float = 1.0) -> float:
    """Profit on a winning bet."""
    return stake * (american_to_decimal(odds) - 1)


# --- The Odds API ----------------------------------------------------------

def _norm(name: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", "", name.lower()).split()) - {"st", "state", "university", "the", "fc"}


def same_team(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na <= nb or nb <= na or len(na & nb) >= 2


def fetch_market_odds(sport_key: str, api_key: str | None = None,
                      session: requests.Session | None = None) -> list[dict[str, Any]]:
    api_key = api_key or os.environ.get("ODDS_API_KEY")
    if not api_key:
        return []
    s = session or requests.Session()
    resp = s.get(
        ODDS_API.format(sport=sport_key),
        params={"apiKey": api_key, "regions": "us,us2", "markets": "h2h,spreads,totals",
                "oddsFormat": "american"},
        timeout=TIMEOUT,
    )
    if resp.status_code in (404, 422):  # sport out of season / not offered
        return []
    resp.raise_for_status()
    return resp.json()


def summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Best available price per outcome across books, plus how many books quote it."""
    best: dict[str, dict[str, Any]] = {}
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            for o in market.get("outcomes", []):
                label = f"{market['key']}:{o['name']}" + (f" {o['point']:+g}" if "point" in o and market["key"] == "spreads"
                                                          else f" {o['point']:g}" if "point" in o else "")
                cur = best.get(label)
                if cur is None or o["price"] > cur["price"]:
                    best[label] = {"price": o["price"], "book": book.get("title"), "books": (cur or {}).get("books", 0) + 1}
                else:
                    cur["books"] += 1
    return {"home": event.get("home_team"), "away": event.get("away_team"),
            "commence": event.get("commence_time"), "best_prices": best}


def match_event(events: list[dict[str, Any]], home: str, away: str) -> dict[str, Any] | None:
    for ev in events:
        if same_team(ev.get("home_team", ""), home) and same_team(ev.get("away_team", ""), away):
            return ev
    return None
