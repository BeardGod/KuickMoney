---
name: kuickmoney
description: Run the KuickMoney AI sports betting analyst on demand. Use when the user says "run KuickMoney", "run the betting app", "make a betting card", asks for picks for a sport, league or game (NFL, NCAA football, MLB, NBA, NHL, soccer), or asks to grade picks or check the betting record.
---

# KuickMoney AI Sports Analyst: on-demand reference

**What it is:** an AI handicapper for NCAA and pro sports. Claude researches games with web search, picks only bets with a real edge over the market, records them in a ledger, grades them from final scores, and learns from the results (closing line value, calibration, results by angle, lessons log). No API key is needed. Claude does the research itself.

**It runs only when asked.** Never create scheduled tasks, routines, cron jobs or GitHub Actions for it.

## Where it lives
- Repo: `https://github.com/BeardGod/KuickMoney`, branch **`ccr-78b26525-89w68p`** (use `master` instead once that branch is merged).
- App: `sports-analyst/` (Python package `kuick_analyst`).
- Full playbook: `.claude/skills/betting-card/SKILL.md`. **Read it and follow it every run.**
- Data: `sports-analyst/data/ledger.json` (every pick) and `sports-analyst/data/lessons.md` (post-mortems).
- Reports: `sports-analyst/reports/<date>/` (one file per league plus `README.md`, the day's card) and `sports-analyst/reports/performance.md`.

## How to run it (Claude Code with a terminal)
1. **Find or get the repo.** Look for an existing `KuickMoney` folder first. If there isn't one:
   `git clone -b ccr-78b26525-89w68p https://github.com/BeardGod/KuickMoney.git`
   If it exists: `cd KuickMoney && git checkout ccr-78b26525-89w68p && git pull`.
2. `cd sports-analyst && pip install -q -r requirements.txt` (Python 3.10+).
3. Read `../.claude/skills/betting-card/SKILL.md` and follow it for the scope the user asked for:
   | User says | Do |
   |---|---|
   | "Run KuickMoney" / "run the app" / "make today's card" | Grade, then every league with games today |
   | "NCAA football picks" / "MLB picks" / "Nations League" | Grade, then only that league (`ncaaf`, `mlb`, `unl`, ...) |
   | "Analyze Colts vs Commanders" | Deep dive on that one game, added to that league's report for the day |
   | "Picks for Saturday" / a date | Use that date (`--date YYYY-MM-DD`) |
   | "Grade my picks" / "how am I doing" | Grade, then summarize `python -m kuick_analyst learn` |
   | "Rerun today's picks" | Re-research and re-record. Ungraded picks for that league and date get replaced. |
4. Commit the updated `reports/` and `data/`, and push if there's a remote, so the record carries over to the next run.
5. Reply with a short summary: each pick with its price and units, passes and drops with the reason, and the updated record. End with: *AI-generated analysis, no guarantees. Bet responsibly (1-800-GAMBLER).*

## Command cheat sheet (run from `sports-analyst/`)
```bash
python -m kuick_analyst learn       # calibration, closing line value, results by angle, recent lessons (read before picking)
python -m kuick_analyst pending     # picks waiting for results
python -m kuick_analyst settle --league nfl --game-id ATL@NO --home NO --away ATL --home-score 24 --away-score 45
python -m kuick_analyst close  --date 2026-10-05 --game-id ATL@NO --odds -110 --line 1.5      # closing line
python -m kuick_analyst lesson --date 2026-10-05 "what this result teaches"
python -m kuick_analyst record /path/league.json --date 2026-10-07   # save a league's analysis and picks
python -m kuick_analyst tag --date 2026-10-05 --game-id ATL@NO --angles sharp_move,injury_edge
```
League keys: `nfl ncaaf nba wnba ncaamb ncaawb mlb ncaabase nhl mls epl unl`.
Angles: `public_fade sharp_move injury_edge qb_change pitching_mismatch bullpen_edge form_gap model_disagreement situational low_scoring_script key_number weather other`.

## Analyst rules (summary; the playbook has the full version)
- Research injuries, lineups and starting pitchers, line movement and public/sharp splits, efficiency stats, and situational spots. Never invent stats, injuries or prices. If something can't be verified, say so.
- Bet only when your win probability beats the implied probability by **at least 3 points** while actual results are running below predicted. Stake 0.5–3 units. Passing is fine.
- Apply the `learn` output: scale edges by the edge factor once one exists, require bigger edges on losing angles, and don't repeat a mistake from the lessons log.
- Prefer sides the line is moving toward. Be wary of betting against a large line move, since it usually means negative closing line value.
- Soccer moneylines are three-way, so a draw loses a bet on either team.

## If there's no terminal (plain Claude chat)
The app can't execute. Do the same analysis with web search and give the card in chat, in the same format: picks, prices, units, win % vs. implied %, and the reasoning. Then tell the user to open Claude Code in the repo and say "record these picks" so they get added to the ledger and graded later.
