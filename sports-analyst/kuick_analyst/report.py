"""Markdown report writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .analyst import Analysis
from .odds import implied_probability

DISCLAIMER = ("> AI-generated analysis for entertainment and research. No outcome is guaranteed. "
              "Bet only what you can afford to lose. Problem gambling help: 1-800-GAMBLER.")


def picks_table(picks: list[dict[str, Any]]) -> str:
    if not picks:
        return "_No bets recommended._"
    rows = ["| League | Matchup | Bet | Odds | Book | Units | Win % | Implied % | Conf |",
            "|---|---|---|---|---|---|---|---|---|"]
    for p in sorted(picks, key=lambda p: (-float(p.get("units") or 0), -float(p.get("confidence") or 0))):
        try:
            odds = int(p.get("odds"))
            implied = f"{implied_probability(odds) * 100:.1f}"
            odds_s = f"{odds:+d}"
        except (TypeError, ValueError, ZeroDivisionError):
            implied, odds_s = "-", str(p.get("odds", "-"))
        wp = p.get("win_probability")
        rows.append(
            f"| {str(p.get('league', '')).upper()} | {p.get('matchup', '')} | {p.get('selection', '')} | {odds_s} "
            f"| {p.get('book') or '-'} | {p.get('units', '')} "
            f"| {f'{float(wp) * 100:.1f}' if isinstance(wp, (int, float)) else '-'} | {implied} "
            f"| {p.get('confidence', '')} |")
    return "\n".join(rows)


def write_league_report(out_dir: Path, date: str, league_name: str, a: Analysis) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{a.league}.md"
    sources = "\n".join(f"- [{s['title']}]({s['url']})" for s in a.sources) or "_None captured._"
    path.write_text(
        f"# {league_name} betting analysis - {date}\n\n{DISCLAIMER}\n\n"
        f"## Picks\n\n{picks_table(a.picks)}\n\n{a.report_markdown}\n\n"
        f"## Sources\n\n{sources}\n\n"
        f"<sub>tokens in/out: {a.usage.get('input_tokens', 0)}/{a.usage.get('output_tokens', 0)}"
        f" | stop: {a.stop_reason}</sub>\n")
    return path


def write_daily_index(out_dir: Path, date: str, analyses: list[tuple[str, Analysis]],
                      skipped: list[str], track_record: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_picks = [p for _, a in analyses for p in a.picks]
    links = "\n".join(f"- [{name}]({a.league}.md) - {len(a.picks)} pick(s)" for name, a in analyses)
    path = out_dir / "README.md"
    path.write_text(
        f"# KuickMoney daily card - {date}\n\n{DISCLAIMER}\n\n"
        f"## All picks\n\n{picks_table(all_picks)}\n\n"
        f"## League reports\n\n{links or '_No leagues analyzed._'}\n\n"
        + (f"No upcoming games: {', '.join(skipped)}\n\n" if skipped else "")
        + f"## Track record\n\n{track_record}\n")
    return path


def write_performance(path: Path, summary: dict[str, Any], picks: list[dict[str, Any]]) -> Path:
    def table(d: dict[str, dict[str, Any]]) -> str:
        if not d:
            return "_No graded picks yet._"
        rows = ["| | Record | Units | ROI | Bets |", "|---|---|---|---|---|"]
        rows += [f"| {k} | {v['record']} | {v['units']:+} | {v['roi']}% | {v['bets']} |" for k, v in d.items()]
        return "\n".join(rows)

    recent = [p for p in reversed(picks) if p["status"] in ("win", "loss", "push")][:50]
    recent_rows = "\n".join(
        f"| {p['date']} | {p['league'].upper()} | {p.get('selection', '')} | {int(p['odds']):+d} | {p.get('units')} "
        f"| {p['status'].upper()} | {p.get('final', '')} | {p['result_units']:+} |" for p in recent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# KuickMoney performance\n\n"
        f"## Overall\n\n{table({'All': summary['overall']})}\n\n"
        f"## By league\n\n{table(summary['by_league'])}\n\n"
        f"## By market\n\n{table(summary['by_market'])}\n\n"
        f"Pending picks: {summary['pending']}\n\n"
        "## Last 50 graded picks\n\n| Date | League | Bet | Odds | Units | Result | Final | Units +/- |\n"
        "|---|---|---|---|---|---|---|---|\n" + recent_rows + "\n")
    return path
