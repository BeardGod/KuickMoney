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

## Setup

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
python -m kuick_analyst schedule --every-hours 6   # keep running on your own PC/server
```

## Running it automatically (GitHub Actions)

`.github/workflows/sports-analyst.yml` runs every day at 10:52 AM ET. It grades yesterday's picks, builds the new card and commits `reports/` and `data/` back to the repo. You can also start it by hand from the **Actions** tab (**Run workflow**) and choose the leagues and effort level.

To set it up, add these repository secrets (**Settings → Secrets and variables → Actions**):
- `ANTHROPIC_API_KEY` (required)
- `ODDS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional)

## Cost

Every analyzed league is one Claude Opus 5.5 request, with up to 20 web searches and 10 page fetches by default. Most of the cost comes from the search results Claude reads. A busy league usually costs somewhere between a few tens of cents and a couple of dollars. To lower the cost, use `--effort medium`, `--max-searches 10`, `--max-games 20`, or name only the leagues you care about.

## Development

```bash
pip install pytest && python -m pytest -q
```

## Disclaimer

This is AI-generated analysis for research and entertainment. No model can guarantee winning bets, and sportsbooks build a margin into every line. Only bet where it is legal, never bet more than you can afford to lose, and if gambling stops being fun, call 1-800-GAMBLER.
