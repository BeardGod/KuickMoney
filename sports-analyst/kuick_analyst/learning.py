"""Feedback loop: closing line value, calibration, results by angle and a
lessons log. Everything here is computed from the ledger and fed back to the
analyst before it makes new picks."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

from .odds import implied_probability

# Why a bet was made. Each pick carries one or more of these so results can be
# broken down by reasoning, not just by league or market.
ANGLES: dict[str, str] = {
    "public_fade": "betting against lopsided public money",
    "sharp_move": "following a line move against the public side",
    "injury_edge": "market under-reacting to injuries or absences",
    "qb_change": "starting quarterback out or replaced",
    "pitching_mismatch": "starting pitcher or goalie gap",
    "bullpen_edge": "relief depth or usage advantage",
    "form_gap": "recent form or standings gap",
    "model_disagreement": "market price differs from projection models",
    "situational": "rest, travel, elimination or motivation spot",
    "low_scoring_script": "expecting a slow, low-scoring game",
    "key_number": "getting through a key number (3, 7)",
    "weather": "weather or venue effect",
    "other": "anything else",
}

BUCKETS = [(0.0, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 1.01)]
MIN_SAMPLE_TO_ADJUST = 30


def graded(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in picks if p.get("status") in ("win", "loss")]


# --- closing line value ----------------------------------------------------

def clv(p: dict[str, Any]) -> dict[str, float] | None:
    """How much better our number was than the closing number (positive = beat the close).

    `points`: line value gained on spreads/totals. `prob`: implied-probability
    gained on the price (only meaningful when the line is unchanged).
    """
    if p.get("closing_odds") is None:
        return None
    try:
        prob = implied_probability(int(p["closing_odds"])) - implied_probability(int(p["odds"]))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    points = 0.0
    line, close = p.get("line"), p.get("closing_line")
    if line is not None and close is not None:
        if p.get("market") == "spread":
            points = float(line) - float(close)
        elif p.get("market") == "total":
            points = (float(close) - float(line)) * (1 if p.get("side") == "over" else -1)
    return {"points": round(points, 2), "prob": round(prob, 4)}


def clv_summary(picks: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [(p, clv(p)) for p in picks]
    rows = [(p, c) for p, c in rows if c is not None]
    if not rows:
        return {"n": 0}
    beat = sum(c["points"] > 0 or (c["points"] == 0 and c["prob"] > 0) for _, c in rows)
    return {"n": len(rows), "beat_pct": round(beat / len(rows) * 100, 1),
            "avg_points": round(sum(c["points"] for _, c in rows) / len(rows), 2),
            "avg_prob": round(sum(c["prob"] for _, c in rows) / len(rows) * 100, 2)}


# --- calibration -----------------------------------------------------------

def calibration(picks: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [(float(p["win_probability"]), 1.0 if p["status"] == "win" else 0.0)
            for p in graded(picks) if isinstance(p.get("win_probability"), (int, float))]
    if not rows:
        return {"n": 0, "buckets": []}
    buckets = []
    for lo, hi in BUCKETS:
        b = [(q, y) for q, y in rows if lo <= q < hi]
        if b:
            buckets.append({"range": f"{lo:.0%}-{min(hi, 1):.0%}", "n": len(b),
                            "predicted": round(sum(q for q, _ in b) / len(b), 3),
                            "actual": round(sum(y for _, y in b) / len(b), 3)})
    n = len(rows)
    predicted = sum(q for q, _ in rows) / n
    actual = sum(y for _, y in rows) / n
    pred_edge = sum(q - 0.5 for q, _ in rows)
    # Edge shrink factor: how much of our claimed edge over 50% actually showed up.
    factor = None
    if n >= MIN_SAMPLE_TO_ADJUST and pred_edge > 0:
        factor = round(min(1.2, max(0.3, sum(y - 0.5 for _, y in rows) / pred_edge)), 2)
    return {"n": n, "predicted": round(predicted, 3), "actual": round(actual, 3),
            "brier": round(sum((q - y) ** 2 for q, y in rows) / n, 3),
            "edge_factor": factor, "buckets": buckets}


# --- angles ----------------------------------------------------------------

def angle_summary(picks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by: dict[str, list] = defaultdict(list)
    for p in graded(picks) + [p for p in picks if p.get("status") == "push"]:
        for a in p.get("angles") or ["untagged"]:
            by[a].append(p)
    out = {}
    for a, items in sorted(by.items()):
        w = sum(p["status"] == "win" for p in items)
        l = sum(p["status"] == "loss" for p in items)
        out[a] = {"record": f"{w}-{l}", "units": round(sum(p.get("result_units") or 0 for p in items), 2),
                  "bets": len(items)}
    return out


def unknown_angles(angles: list[str]) -> list[str]:
    return [a for a in angles if a not in ANGLES]


# --- lessons ---------------------------------------------------------------

def add_lesson(path: Path, date: str, text: str, pick_id: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Lessons log\n\nShort post-mortems written after picks are graded. "
                        "The analyst reads the most recent ones before every card.\n\n")
    ref = f" `{pick_id}`" if pick_id else ""
    with path.open("a") as f:
        f.write(f"- **{date}**{ref}: {text.strip()}\n")


def recent_lessons(path: Path, n: int = 15) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line.startswith("- ")][-n:]


# --- what the analyst sees -------------------------------------------------

def learning_text(picks: list[dict[str, Any]], lessons_path: Path | None = None,
                  today: dt.date | None = None, since_days: int = 90) -> str:
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=since_days)).isoformat()
    picks = [p for p in picks if p.get("date", "") >= cutoff]
    out: list[str] = []

    c = calibration(picks)
    if c["n"]:
        out.append(f"Calibration ({c['n']} graded): you predicted {c['predicted']:.1%} on average, "
                   f"actual win rate {c['actual']:.1%}, Brier {c['brier']}.")
        if c["edge_factor"] is not None:
            out.append(f"ADJUST: multiply your estimated edge over 50% by {c['edge_factor']} "
                       f"(e.g. 56% becomes {0.5 + 0.06 * c['edge_factor']:.1%}).")
        else:
            out.append(f"Fewer than {MIN_SAMPLE_TO_ADJUST} graded picks: too few to rescale estimates yet, "
                       "but be skeptical of edges under 3 points.")

    v = clv_summary(picks)
    if v["n"]:
        out.append(f"Closing line value ({v['n']} picks): beat the close {v['beat_pct']}% of the time, "
                   f"avg {v['avg_points']:+} points / {v['avg_prob']:+}% implied probability. "
                   "Consistently negative CLV means the edge is not real, whatever the record says.")
    else:
        out.append("Closing line value: none recorded yet.")

    a = angle_summary(picks)
    if a:
        out.append("Results by angle: " + "; ".join(
            f"{k} {v['record']} ({v['units']:+}u)" for k, v in a.items()))

    if lessons_path is not None:
        lessons = recent_lessons(lessons_path)
        if lessons:
            out.append("Recent lessons:\n" + "\n".join(lessons))
    return "\n".join(out)
