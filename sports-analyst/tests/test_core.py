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
