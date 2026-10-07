# KuickMoney AI Sports Analyst

An automated betting analyst powered by Claude. Each run it:

1. **Grades past picks** against final scores and updates the track record.
2. **Pulls every upcoming game** for the day across NCAA and pro leagues: schedule, records, rankings, venue, weather and the posted line (ESPN, free). If you add a key, it also pulls best-price odds across US sportsbooks (The Odds API).
3. **Has Claude research the slate live.** Claude uses web search and web fetch to check injuries, lineups, line movement, advanced metrics, weather and situational spots. It then estimates its own win probabilities and recommends only bets with positive expected value, staked 0.5–3 units.
4. **Writes reports** to `reports/<date>/` (one file per league plus a daily card) and records the picks in `data/ledger.json`. Recent results feed back into the next run so Claude stays calibrated.
5. Optionally **sends the top picks to Telegram**.

| Key | League | Key | League |
|---|---|---|---|
| `nfl` | NFL | `ncaaf` | NCAA Football (all FBS) |
| `nba` | NBA | `ncaamb` | NCAA Men's Basketball (D-I) |
| `wnba` | WNBA | `ncaawb` | NCAA Women's Basketball (D-I) |
| `mlb` | MLB | `ncaabase` | NCAA Baseball |
| `nhl` | NHL | `mls` / `epl` | MLS / Premier League |

Leagues with no games that day are skipped automatically, so `all` only spends money on sports that are in season.

## How to run it (on demand)

Nothing runs on a schedule. To run it, ask Claude in Claude Code (on your computer or in a Claude Code session) with this repo open. For example: "run KuickMoney", "NCAA football picks for Saturday", "analyze Colts vs Commanders" or "grade my picks". Claude follows the playbook in [`.claude/skills/betting-card/SKILL.md`](../.claude/skills/betting-card/SKILL.md): it grades open picks, researches with web search, records picks, and updates the reports. No API key is needed.

[`KUICKMONEY_ANALYST.md`](../KUICKMONEY_ANALYST.md) at the repo root is a one-page reference you can save to Claude's memory, a project, or `~/.claude/skills/` so any Claude session knows how to run it.

There is also a standalone Python path, `python -m kuick_analyst run`. It calls the Claude API directly and needs `ANTHROPIC_API_KEY`.

## Setup (option B)

```bash
cd sports-analyst
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # required for `run`
export ODDS_API_KEY=...                    # optional: multi-book line shopping (the-odds-api.com, free tier)
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...   # optional alerts
```

## Usage

```bash
python -m kuick_analyst slate                      # today's games and lines (free, no AI)
python -m kuick_analyst run                        # full card, all leagues
python -m kuick_analyst run --leagues nfl,ncaaf --effort xhigh
python -m kuick_analyst run --date 2026-10-10 --max-games 25
python -m kuick_analyst grade                      # grade picks, refresh reports/performance.md

# Claude Code mode helpers (no API key)
python -m kuick_analyst record league.json --date 2026-10-04   # save a league analysis + picks
python -m kuick_analyst pending                                # picks waiting for results
python -m kuick_analyst settle --league nfl --game-id BUF@KC --home KC --away BUF --home-score 24 --away-score 20

# Feedback loop
python -m kuick_analyst close --date 2026-10-05 --game-id ATL@NO --odds -110 --line 1.5   # closing line -> CLV
python -m kuick_analyst tag --date 2026-10-05 --game-id ATL@NO --angles sharp_move,injury_edge
python -m kuick_analyst lesson --date 2026-10-05 "what this result teaches"
python -m kuick_analyst learn            # calibration, CLV, results by angle, recent lessons
```

## How it adjusts over time

The model itself does not change. What changes is what the analyst reads before every card:

- **Closing line value (CLV):** each pick's price is compared to the closing line. Beating the close consistently is the earliest reliable sign of a real edge.
- **Calibration:** predicted win % vs. actual win rate, by bucket. After 30 graded picks an *edge factor* is computed, and the analyst scales its claimed edges by it.
- **Results by angle:** every pick is tagged with its reasons (`public_fade`, `injury_edge`, `pitching_mismatch`, ...). Losing angles need bigger edges; winning ones get more trust.
- **Lessons log:** after grading, a short post-mortem is added to `data/lessons.md`. The most recent lessons are shown to the analyst before every card.

All of it is in `reports/performance.md`.

## Cost

Every analyzed league is one Claude Opus 5.5 request, with up to 20 web searches and 10 page fetches by default. Most of the cost comes from the search results Claude reads. A busy league usually costs somewhere between a few tens of cents and a couple of dollars. To lower the cost, use `--effort medium`, `--max-searches 10`, `--max-games 20`, or name only the leagues you care about.

## Development

```bash
pip install pytest && python -m pytest -q
```

## Disclaimer

This is AI-generated analysis for research and entertainment. No model can guarantee winning bets, and sportsbooks build a margin into every line. Only bet where it is legal, never bet more than you can afford to lose, and if gambling stops being fun, call 1-800-GAMBLER.
