"""KenPom-style game projection for college basketball.

Uses the published KenPom method: adjusted efficiencies (points per 100
possessions) and adjusted tempo, scaled by the national averages, with a
small home-court boost to the home side's offense and a matching penalty to
the away side's. The analyst copies each team's AdjO, AdjD and AdjT from
kenpom.com (or FanMatch when it is visible) and this turns them into a
projected score, win probability and cover / over probabilities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# National averages move a little each season; override from kenpom.com when known.
AVG_EFFICIENCY = 109.0
AVG_TEMPO = 67.5
# Home-court edge as a share of efficiency (~2.2% each way is about 3.2 points).
HOME_EDGE = 0.022
# Spread of real outcomes around the projection (points). Used for probabilities.
MARGIN_SD = 11.0
TOTAL_SD = 16.0


@dataclass(frozen=True)
class Team:
    name: str
    adj_o: float  # adjusted offensive efficiency
    adj_d: float  # adjusted defensive efficiency (lower is better)
    adj_t: float  # adjusted tempo (possessions per 40 minutes)


@dataclass(frozen=True)
class Projection:
    a: str
    b: str
    a_points: float
    b_points: float
    tempo: float

    @property
    def margin(self) -> float:  # positive = team A wins by this much
        return self.a_points - self.b_points

    @property
    def total(self) -> float:
        return self.a_points + self.b_points

    @property
    def a_win_prob(self) -> float:
        return _phi(self.margin / MARGIN_SD)

    def a_cover_prob(self, a_spread: float) -> float:
        """Chance team A covers its spread (e.g. -7.5 as a favorite, +7.5 as a dog)."""
        return _phi((self.margin + a_spread) / MARGIN_SD)

    def over_prob(self, total: float) -> float:
        return _phi((self.total - total) / TOTAL_SD)


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def project(a: Team, b: Team, home: str = "neutral", avg_eff: float = AVG_EFFICIENCY,
            avg_tempo: float = AVG_TEMPO, home_edge: float = HOME_EDGE) -> Projection:
    """Project A vs B. `home` is "a", "b" or "neutral"."""
    if home not in ("a", "b", "neutral"):
        raise ValueError("home must be 'a', 'b' or 'neutral'")
    tempo = a.adj_t * b.adj_t / avg_tempo
    a_eff = a.adj_o * b.adj_d / avg_eff
    b_eff = b.adj_o * a.adj_d / avg_eff
    if home == "a":
        a_eff *= 1 + home_edge
        b_eff *= 1 - home_edge
    elif home == "b":
        a_eff *= 1 - home_edge
        b_eff *= 1 + home_edge
    return Projection(a.name, b.name, a_eff * tempo / 100, b_eff * tempo / 100, tempo)


def summary(p: Projection, a_spread: float | None = None, total: float | None = None) -> str:
    lines = [f"KenPom-style projection: {p.a} {p.a_points:.1f}, {p.b} {p.b_points:.1f} "
             f"(tempo {p.tempo:.1f} poss)",
             f"Margin: {p.a} by {p.margin:+.1f}; total {p.total:.1f}",
             f"Win probability: {p.a} {p.a_win_prob:.1%}, {p.b} {1 - p.a_win_prob:.1%}"]
    if a_spread is not None:
        c = p.a_cover_prob(a_spread)
        lines.append(f"Spread {p.a} {a_spread:+g}: {p.a} covers {c:.1%}, {p.b} covers {1 - c:.1%}")
    if total is not None:
        o = p.over_prob(total)
        lines.append(f"Total {total:g}: over {o:.1%}, under {1 - o:.1%}")
    return "\n".join(lines)
