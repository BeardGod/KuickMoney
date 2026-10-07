"""Claude-powered betting analyst.

For each league slate, Claude receives the schedule, the posted lines and our
own track record, then researches the games live with web search / web fetch
(injuries, lineups, weather, line movement, matchup and advanced stats) and
returns a written breakdown plus machine-readable picks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

MODEL = "claude-opus-5-5"
MAX_CONTINUATIONS = 6

SYSTEM_PROMPT = """\
You are KuickMoney's lead sports betting analyst: a sharp, disciplined handicapper \
covering NCAA and professional sports. Your job is to find bets with a real edge over \
the market, not to pick every game.

## Research
Use web search and web fetch to gather current information before deciding. Prioritize:
- Injury reports, inactive lists, confirmed lineups/starting pitchers/goalies, suspensions
- Line movement, opening vs. current numbers, and public vs. sharp money splits when available
- Efficiency and advanced metrics (EPA/play, SP+, KenPom/BartTorvik, net rating, xG, \
  wRC+/FIP, Corsi/xGF), pace, and situational spots (rest, travel, lookahead, revenge)
- Weather and venue factors for outdoor sports
- Coaching tendencies and recent form, discounting small samples
Spend your searches on the games most likely to hold value; you do not need to research \
every game equally. Never invent injuries, stats or quotes. If you could not verify \
something, say so.

## Deciding
- Estimate your own win probability for each candidate bet, compare it to the no-vig \
  market probability, and only recommend bets with positive expected value.
- Stake on a 0.5-3 unit scale; reserve 2+ units for your strongest edges. A slate with \
  zero recommended bets is an acceptable answer.
- Prefer the best available price when multiple sportsbook prices are provided, and say \
  which book has it.
- Use the track record you are given to stay calibrated: if a market, league or angle has \
  been losing, tighten your threshold there. If an edge factor is given, scale your \
  estimated edge over 50% by it before deciding. Read the recent lessons and do not \
  repeat a mistake they describe.

## Output
Write a Markdown report with:
1. **Slate overview** - 2-4 sentences on the key storylines and market context.
2. **Best bets** - for each pick: the bet and price, units, your win probability vs. the \
   implied probability, and a concise evidence-based case (key injuries, matchup edges, \
   numbers). Cite sources inline.
3. **Leans & passes** - brief notes on notable games you looked at and why you passed.
4. **Risks** - what would make you wrong.

Then end your response with exactly one fenced ```json block of this shape (and nothing \
after it):
{"picks": [{"game_id": "<id from the slate>", "matchup": "Away @ Home",
  "market": "spread" | "moneyline" | "total" | "prop" | "other",
  "side": "home" | "away" | "draw" | "over" | "under" | "other",
  "selection": "human readable, e.g. Chiefs -3.5",
  "line": <number or null - the spread for the chosen side, or the total>,
  "odds": <American odds integer, e.g. -110>,
  "book": "<sportsbook or null>",
  "win_probability": <0-1>, "units": <0.5-3>, "confidence": <1-5>,
  "summary": "<one sentence>",
  "angles": ["<one or more of: public_fade, sharp_move, injury_edge, qb_change,
    pitching_mismatch, bullpen_edge, form_gap, model_disagreement, situational,
    low_scoring_script, key_number, weather, other>"]}]}
Use "prop"/"other" with side "other" for anything that is not a full-game spread, \
moneyline or total.
"""


@dataclass
class Analysis:
    league: str
    report_markdown: str
    picks: list[dict[str, Any]]
    sources: list[dict[str, str]] = field(default_factory=list)
    stop_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def split_report(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Separate the trailing JSON picks block from the Markdown report."""
    matches = list(_JSON_BLOCK.finditer(text))
    if not matches:
        return text.strip(), []
    last = matches[-1]
    try:
        payload = json.loads(last.group(1))
    except json.JSONDecodeError:
        return text.strip(), []
    picks = [p for p in payload.get("picks", []) if isinstance(p, dict)]
    report = (text[: last.start()] + text[last.end():]).strip()
    return report, picks


def _collect(content: list[Any]) -> tuple[str, list[dict[str, str]]]:
    text_parts: list[str] = []
    sources: dict[str, str] = {}
    for block in content:
        if block.type != "text":
            continue
        text_parts.append(block.text)
        for c in getattr(block, "citations", None) or []:
            url = getattr(c, "url", None)
            if url:
                sources.setdefault(url, getattr(c, "title", None) or url)
    return "".join(text_parts), [{"url": u, "title": t} for u, t in sources.items()]


def build_user_prompt(league_name: str, date: str, slate: list[dict[str, Any]],
                      track_record: str) -> str:
    return (
        f"Date: {date}\nLeague: {league_name}\n\n"
        f"## Our recent track record\n{track_record}\n\n"
        f"## Slate ({len(slate)} games, JSON)\n"
        "`line` is ESPN's posted line (spread is from the home team's perspective). "
        "`market` (when present) is the best price per outcome across US sportsbooks.\n\n"
        f"```json\n{json.dumps(slate, indent=1, default=str)}\n```\n\n"
        "Research this slate and give me your best bets."
    )


class Analyst:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL,
                 effort: str = "high", max_searches: int = 20, max_fetches: int = 10):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.tools: list[dict[str, Any]] = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_fetches},
        ]

    def analyze(self, league_key: str, league_name: str, date: str,
                slate: list[dict[str, Any]], track_record: str) -> Analysis:
        user = build_user_prompt(league_name, date, slate, track_record)
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        content: list[Any] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        response = None

        for _ in range(MAX_CONTINUATIONS):
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
                tools=self.tools,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                # Re-run on Anthropic's recommended fallback model if a safety classifier declines.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                response = stream.get_final_message()

            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens

            if response.stop_reason == "refusal":
                break
            content.extend(response.content)
            if response.stop_reason == "pause_turn":
                # Long server-tool turn paused; resend so Claude resumes where it left off.
                messages = [messages[0], {"role": "assistant", "content": content}]
                continue
            break

        text, sources = _collect(content)
        if response is not None and response.stop_reason == "refusal":
            text = "_The model declined to analyze this slate._"
        report, picks = split_report(text)
        for p in picks:
            p.setdefault("league", league_key)
        return Analysis(
            league=league_key,
            report_markdown=report,
            picks=picks,
            sources=sources,
            stop_reason=response.stop_reason if response is not None else None,
            usage=usage,
        )
