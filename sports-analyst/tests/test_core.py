import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kuick_analyst import odds
from kuick_analyst.analyst import Analyst, split_report
from kuick_analyst.espn import parse_scoreboard
from kuick_analyst.leagues import LEAGUES, resolve
from kuick_analyst.ledger import Ledger, grade_pick
from kuick_analyst.report import picks_table

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def games():
    return parse_scoreboard(json.loads((FIX / "nfl_scoreboard.json").read_text()), LEAGUES["nfl"])


def test_parse_scoreboard(games):
    kc, dal = games
    assert kc.matchup == "Buffalo Bills @ Kansas City Chiefs"
    assert kc.state == "pre" and kc.home.record == "3-1" and kc.home.rank is None
    assert kc.line.spread == -2.5 and kc.line.total == 48.5 and kc.line.home_ml == -135
    assert kc.weather == "Sunny 68F" and kc.broadcast == "CBS"
    assert dal.state == "post" and dal.away.score == 24 and dal.line.details is None


def test_odds_math():
    assert odds.american_to_decimal(150) == 2.5
    assert odds.implied_probability(-110) == pytest.approx(0.5238, abs=1e-4)
    assert sum(odds.no_vig_probabilities([-110, -110])) == pytest.approx(1)
    assert odds.expected_value(0.5, 100) == pytest.approx(0)
    assert odds.kelly_fraction(0.4, -110) == 0
    assert odds.profit(-200, 2) == pytest.approx(1)


def test_team_matching():
    assert odds.same_team("Kansas City Chiefs", "Kansas City Chiefs")
    assert not odds.same_team("Ohio State Buckeyes", "Ohio Bobcats")
    assert not odds.same_team("Michigan Wolverines", "Michigan State Spartans")


def test_summarize_event_best_price():
    ev = {"home_team": "A", "away_team": "B", "bookmakers": [
        {"title": "DK", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": -120}]}]},
        {"title": "FD", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": -110}]}]}]}
    best = odds.summarize_event(ev)["best_prices"]["h2h:A"]
    assert best == {"price": -110, "book": "FD", "books": 2}


@pytest.mark.parametrize("pick,expected", [
    ({"market": "moneyline", "side": "away"}, "win"),
    ({"market": "moneyline", "side": "home"}, "loss"),
    ({"market": "spread", "side": "home", "line": 4}, "push"),
    ({"market": "spread", "side": "home", "line": 4.5}, "win"),
    ({"market": "spread", "side": "away", "line": -4.5}, "loss"),
    ({"market": "total", "side": "over", "line": 43.5}, "win"),
    ({"market": "total", "side": "under", "line": 44}, "push"),
])
def test_grade_pick(games, pick, expected):
    assert grade_pick(pick, games[1]) == expected


def test_ledger_roundtrip(tmp_path, games):
    led = Ledger(tmp_path / "l.json")
    picks = [
        {"league": "nfl", "game_id": "402", "market": "moneyline", "side": "away", "odds": 120, "units": 2},
        {"league": "nfl", "game_id": "402", "market": "total", "side": "under", "line": 47.5, "odds": "bad", "units": 1},
        {"league": "nfl", "game_id": "401", "market": "prop", "side": "other", "odds": 300, "units": 0.5},
    ]
    assert led.add("2026-10-04", picks) == 3
    assert led.add("2026-10-04", picks) == 0  # deduped
    assert led.grade(lambda lg, d: games) == 2
    led.save()
    led = Ledger(tmp_path / "l.json")
    s = led.summary(today=__import__("datetime").date(2026, 10, 5))
    assert s["overall"]["record"] == "2-0-0"
    assert s["overall"]["units"] == pytest.approx(2 * 1.2 + 100 / 110, abs=0.01)
    assert [p["status"] for p in led.picks] == ["win", "win", "manual"]
    assert "2-0-0" in led.track_record_text(today=__import__("datetime").date(2026, 10, 5))


def test_split_report():
    text = 'Report body\n\n```json\n{"picks": [{"selection": "KC -2.5", "odds": -110}]}\n```\n'
    report, picks = split_report(text)
    assert report == "Report body" and picks[0]["selection"] == "KC -2.5"
    assert split_report("no json")[1] == []
    assert "KC -2.5" in picks_table(picks)


def test_resolve_leagues():
    assert len(resolve(None)) == len(LEAGUES)
    with pytest.raises(ValueError):
        resolve(["xfl"])


class FakeStream:
    def __init__(self, msg): self.msg = msg
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self.msg


def _msg(stop, text):
    return SimpleNamespace(stop_reason=stop, usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                           content=[SimpleNamespace(type="text", text=text, citations=[
                               SimpleNamespace(url="https://x.com/a", title="A")])])


def test_analyst_handles_pause_turn():
    responses = [_msg("pause_turn", "Part one. "),
                 _msg("end_turn", 'Part two.\n```json\n{"picks": [{"game_id": "401", "market": "spread"}]}\n```')]
    calls = []

    def stream(**kw):
        calls.append(kw)
        return FakeStream(responses[len(calls) - 1])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    a = Analyst(client=client).analyze("nfl", "NFL", "2026-10-04", [], "No graded picks yet.")
    assert a.report_markdown == "Part one. Part two."
    assert a.picks == [{"game_id": "401", "market": "spread", "league": "nfl"}]
    assert a.sources == [{"url": "https://x.com/a", "title": "A"}]
    assert a.usage == {"input_tokens": 20, "output_tokens": 10}
    assert calls[1]["messages"][1]["role"] == "assistant"
    assert calls[0]["model"] == "claude-opus-5-5" and calls[0]["fallbacks"] == "default"


def test_record_and_settle_cli(tmp_path, monkeypatch):
    from kuick_analyst import cli
    monkeypatch.setattr(cli, "HOME", tmp_path)
    f = tmp_path / "nfl.json"
    f.write_text(json.dumps({"league": "nfl", "report_markdown": "## Slate overview\nText",
                             "sources": [{"url": "https://a.com", "title": "A"}],
                             "picks": [{"game_id": "BUF@KC", "matchup": "Bills @ Chiefs", "market": "spread",
                                        "side": "away", "line": 2.5, "odds": -110, "units": 1,
                                        "selection": "Bills +2.5"}]}))
    assert cli.main(["record", str(f), "--date", "2026-10-04"]) == 0
    card = (tmp_path / "reports/2026-10-04/README.md").read_text()
    assert "Bills +2.5" in card and "nfl.md" in card
    assert cli.main(["settle", "--league", "nfl", "--game-id", "BUF@KC", "--home", "KC", "--away", "BUF",
                     "--home-score", "24", "--away-score", "23"]) == 0
    led = json.loads((tmp_path / "data/ledger.json").read_text())
    assert led[0]["status"] == "win" and led[0]["result_units"] == pytest.approx(0.909, abs=0.001)


def test_soccer_draw_loses_team_moneyline():
    from kuick_analyst.espn import Game, Team
    g = Game(id="x", league="unl", start="", state="post", status="FT",
             home=Team("NIR", "NIR", score=1), away=Team("GEO", "GEO", score=1))
    assert grade_pick({"league": "unl", "market": "moneyline", "side": "home"}, g) == "loss"
    assert grade_pick({"league": "unl", "market": "moneyline", "side": "draw"}, g) == "win"
    assert grade_pick({"league": "nhl", "market": "moneyline", "side": "home"}, g) == "push"


# --- feedback loop ---------------------------------------------------------

from kuick_analyst import learning


def test_clv_spread_total_and_price():
    # Took +6.5, closed +5.5: one point better than the close.
    assert learning.clv({"market": "spread", "line": 6.5, "closing_line": 5.5, "odds": -110, "closing_odds": -110}) \
        == {"points": 1.0, "prob": 0.0}
    # Took under 49.5, closed 47: 2.5 points better; an over at 49.5 would be 2.5 worse.
    assert learning.clv({"market": "total", "side": "under", "line": 49.5, "closing_line": 47,
                         "odds": -110, "closing_odds": -110})["points"] == 2.5
    assert learning.clv({"market": "total", "side": "over", "line": 49.5, "closing_line": 47,
                         "odds": -110, "closing_odds": -110})["points"] == -2.5
    # Took -104, closed -130: price got more expensive, so we beat it.
    c = learning.clv({"market": "moneyline", "odds": -104, "closing_odds": -130})
    assert c["points"] == 0 and c["prob"] > 0.05
    assert learning.clv({"market": "moneyline", "odds": -104}) is None
    s = learning.clv_summary([{"market": "moneyline", "odds": -104, "closing_odds": -130},
                              {"market": "moneyline", "odds": 150, "closing_odds": 170}])
    assert s["n"] == 2 and s["beat_pct"] == 50.0


def test_calibration_and_edge_factor():
    few = [{"status": "win", "win_probability": 0.6}, {"status": "loss", "win_probability": 0.6},
           {"status": "push", "win_probability": 0.6}]
    c = learning.calibration(few)
    assert c["n"] == 2 and c["actual"] == 0.5 and c["edge_factor"] is None
    # 40 picks at 60% that won only half the time: the claimed edge did not show up.
    many = [{"status": "win" if i % 2 else "loss", "win_probability": 0.6} for i in range(40)]
    assert learning.calibration(many)["edge_factor"] == 0.3
    good = [{"status": "win" if i % 5 else "loss", "win_probability": 0.6} for i in range(40)]
    assert learning.calibration(good)["edge_factor"] == 1.2


def test_angle_summary_and_lessons(tmp_path):
    picks = [{"status": "win", "result_units": 0.9, "angles": ["public_fade", "injury_edge"]},
             {"status": "loss", "result_units": -1, "angles": ["public_fade"]},
             {"status": "loss", "result_units": -1}]
    a = learning.angle_summary(picks)
    assert a["public_fade"] == {"record": "1-1", "units": -0.1, "bets": 2}
    assert a["untagged"]["record"] == "0-1"
    assert learning.unknown_angles(["public_fade", "vibes"]) == ["vibes"]
    path = tmp_path / "lessons.md"
    learning.add_lesson(path, "2026-10-06", "Backup QB does not mean a slow game.", "x:y")
    learning.add_lesson(path, "2026-10-07", "Second lesson.")
    assert learning.recent_lessons(path, n=1) == ["- **2026-10-07**: Second lesson."]
    text = learning.learning_text(picks, path, today=__import__("datetime").date(2026, 10, 7))
    assert "Backup QB" in text and "Fewer than 30" not in text  # no win_probability -> no calibration


def test_cli_feedback_commands(tmp_path, monkeypatch):
    from kuick_analyst import cli
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "LESSONS", tmp_path / "data/lessons.md")
    f = tmp_path / "mlb.json"
    pick = {"game_id": "MIL@SD", "matchup": "Brewers @ Padres", "market": "moneyline", "side": "away",
            "selection": "Brewers ML", "odds": -104, "units": 1, "win_probability": 0.545,
            "angles": ["pitching_mismatch"]}
    f.write_text(json.dumps({"league": "mlb", "report_markdown": "x", "picks": [pick]}))
    assert cli.main(["record", str(f), "--date", "2026-10-07"]) == 0
    # Rerun with the pick changed and a second pick: pending pick is replaced, not duplicated.
    f.write_text(json.dumps({"league": "mlb", "report_markdown": "x", "picks": [
        {**pick, "units": 0.5}, {**pick, "game_id": "LAD@ATL", "selection": "Dodgers ML"}]}))
    assert cli.main(["record", str(f), "--date", "2026-10-07"]) == 0
    led = json.loads((tmp_path / "data/ledger.json").read_text())
    assert len(led) == 2 and led[0]["units"] == 0.5
    f.write_text(json.dumps({"league": "mlb", "report_markdown": "x", "picks": [pick]}))
    assert cli.main(["record", str(f), "--date", "2026-10-07"]) == 0
    assert len(json.loads((tmp_path / "data/ledger.json").read_text())) == 1
    assert cli.main(["close", "--date", "2026-10-07", "--game-id", "MIL@SD", "--odds", "-125"]) == 0
    assert cli.main(["tag", "--date", "2026-10-07", "--game-id", "MIL@SD", "--angles", "bullpen_edge,vibes"]) == 1
    assert cli.main(["tag", "--date", "2026-10-07", "--game-id", "MIL@SD", "--angles", "bullpen_edge"]) == 0
    assert cli.main(["settle", "--league", "mlb", "--game-id", "MIL@SD", "--home", "SD", "--away", "MIL",
                     "--home-score", "2", "--away-score", "5"]) == 0
    assert cli.main(["lesson", "Bullpen depth showed up.", "--date", "2026-10-08"]) == 0
    perf = (tmp_path / "reports/performance.md").read_text()
    assert "Beat the closing line on **100.0%**" in perf and "| bullpen_edge | 1-0 |" in perf
    assert "## Calibration" in perf
