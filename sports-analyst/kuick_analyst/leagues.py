"""Supported leagues and how to reach their data sources."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    key: str  # short id used on the CLI, e.g. "nfl"
    name: str
    espn_sport: str  # ESPN path segment: football, basketball, ...
    espn_league: str  # ESPN path segment: nfl, college-football, ...
    odds_api_key: str | None  # The Odds API sport key, if covered
    college: bool = False
    espn_params: tuple[tuple[str, str], ...] = ()  # extra scoreboard query params


LEAGUES: dict[str, League] = {
    lg.key: lg
    for lg in [
        League("nfl", "NFL", "football", "nfl", "americanfootball_nfl"),
        # groups=80 = all FBS games instead of only the Top 25
        League("ncaaf", "NCAA Football (FBS)", "football", "college-football",
               "americanfootball_ncaaf", college=True, espn_params=(("groups", "80"),)),
        League("nba", "NBA", "basketball", "nba", "basketball_nba"),
        League("wnba", "WNBA", "basketball", "wnba", "basketball_wnba"),
        # groups=50 = all Division I games
        League("ncaamb", "NCAA Men's Basketball", "basketball", "mens-college-basketball",
               "basketball_ncaab", college=True, espn_params=(("groups", "50"),)),
        League("ncaawb", "NCAA Women's Basketball", "basketball", "womens-college-basketball",
               "basketball_wncaab", college=True, espn_params=(("groups", "50"),)),
        League("mlb", "MLB", "baseball", "mlb", "baseball_mlb"),
        League("ncaabase", "NCAA Baseball", "baseball", "college-baseball",
               "baseball_ncaa", college=True),
        League("nhl", "NHL", "hockey", "nhl", "icehockey_nhl"),
        League("mls", "MLS", "soccer", "usa.1", "soccer_usa_mls"),
        League("epl", "English Premier League", "soccer", "eng.1", "soccer_epl"),
        League("unl", "UEFA Nations League", "soccer", "uefa.nations", "soccer_uefa_nations_league"),
    ]
}

DEFAULT_LEAGUES = list(LEAGUES)


def resolve(keys: list[str] | None) -> list[League]:
    if not keys or keys == ["all"]:
        return [LEAGUES[k] for k in DEFAULT_LEAGUES]
    unknown = [k for k in keys if k not in LEAGUES]
    if unknown:
        raise ValueError(f"Unknown league(s): {', '.join(unknown)}. Known: {', '.join(LEAGUES)}")
    return [LEAGUES[k] for k in keys]
