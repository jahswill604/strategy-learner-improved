import base64
import json

import numpy as np
import pandas as pd
import pytest

from strategy_learner.data import facts_text, previous_day_levels
from strategy_learner.memory import Strategy
from strategy_learner.models import FakeModel, extract_json
from strategy_learner.signals import run_once
from strategy_learner.teach import Teacher
from strategy_learner.tester import Tester

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def strat(tmp_path):
    return Strategy.open(tmp_path / "s", "ada/candle-range")


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(PNG)
    return p


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('blah {"a": 3} blah') == {"a": 3}
    assert extract_json("no json here") == {}


def test_learned_gate_blocks_until_everything_is_there(strat, png):
    strat.upsert_concept({"name": "FVG", "simple_definition": "a gap between candle 1 and 3"})
    ok, missing = strat.mark_learned("FVG")
    assert not ok and "a valid example image" in missing
    strat.add_example("FVG", "valid", png, "clean gap")
    strat.add_example("FVG", "invalid", png, "already filled")
    strat.upsert_concept({"name": "FVG", "invalidation": "price closes through it", "failure_cases": ["news spike"]})
    ok, missing = strat.mark_learned("FVG")
    assert not ok and missing == ["the trader's confirmation of the explain-back"]
    strat.confirm("FVG")
    assert strat.mark_learned("FVG") == (True, [])


def test_changing_definition_requires_reconfirmation(strat):
    strat.upsert_concept({"name": "Sweep", "simple_definition": "price takes a high"})
    strat.confirm("Sweep")
    strat.upsert_concept({"name": "Sweep", "simple_definition": "price takes a high and closes back inside"})
    c = strat.concepts()["sweep"]
    assert c["confirmed"] is False and c["status"] == "learning"


def test_teacher_applies_updates_and_reports_gate_failures(strat, png):
    reply = json.dumps({
        "say": "What is a key level?",
        "focus": "Key level",
        "concepts": [{"name": "Key level", "simple_definition": "an area price respects"}],
        "mark_learned": ["Key level"],
        "open_questions": ["what is an FVG"],
        "rules": {"no_trade": ["high impact news"], "entry": "sell after 1H BOS"},
    })
    model = FakeModel([reply, json.dumps({"say": "ok"})])
    t = Teacher(model, strat)
    assert t.turn("I sell after a sweep at a key level") == "What is a key level?"
    m = strat.meta()
    assert m["focus"] == "Key level"
    assert m["open_questions"] == ["what is an FVG"]
    assert m["rules"]["no_trade"] == ["high impact news"]
    assert "could not be marked learned" in m["notes"][0]
    # the rejection is passed to the model on the next turn, but not stored as the trader's words
    ok, _ = t.add_image("valid", png, "clean level")
    assert ok
    t.turn("here is one", [png])
    last = model.calls[-1]["messages"][-1]["content"]
    assert "system notes" in last and "still missing" in last
    assert model.calls[-1]["images"] == [png]


def test_add_image_without_focus_is_refused(strat, png):
    ok, msg = Teacher(FakeModel([]), strat).add_image("valid", png, "x")
    assert not ok


def test_resume_shows_last_question(strat):
    t = Teacher(FakeModel([json.dumps({"say": "Why?"})]), strat)
    t.opening()
    t.turn("hello")
    assert "Why?" in Teacher(FakeModel([]), strat).opening()


def test_tester_scores_corrects_and_saves_example(strat, png):
    strat.upsert_concept({"name": "FVG", "simple_definition": "gap"})
    first = {"labels": [{"concept": "FVG", "where": "left", "reason": "gap"},
                        {"concept": "FVG", "where": "right", "reason": "gap"}], "overall": "o"}
    fix = {"learned": "filled gaps do not count",
           "concepts": [{"name": "FVG", "invalidation": "filled by a later candle"}],
           "examples": [{"concept": "FVG", "kind": "invalid", "reason": "already filled"}],
           "missed_concepts": ["Sweep"]}
    again = {"labels": [{"concept": "FVG", "where": "left", "reason": "gap"}], "overall": "o2"}
    model = FakeModel([json.dumps(first), json.dumps(fix), json.dumps(again)])
    t = Tester(model, strat)
    labels, _ = t.label(png)
    assert [l["id"] for l in labels] == [1, 2]
    learned, new_labels, _ = t.correct(png, labels, {2: "already filled"}, ["a sweep on the left"])
    assert "filled" in learned and len(new_labels) == 1
    assert strat.scores()["events"]["fvg"] == [1, 0]
    assert strat.scores()["events"]["sweep"] == [0]
    assert strat.concepts()["fvg"]["invalidation"] == "filled by a later candle"
    assert strat.examples()["fvg"][0]["kind"] == "invalid"
    assert strat.scores()["charts"] == 1
    assert (strat.root / "corrections.jsonl").exists()


def test_readiness_needs_learned_and_accuracy(strat, png):
    strat.upsert_concept({"name": "FVG", "simple_definition": "gap", "invalidation": "filled", "failure_cases": ["x"]})
    strat.add_example("FVG", "valid", png)
    strat.add_example("FVG", "invalid", png)
    strat.confirm("FVG")
    strat.mark_learned("FVG")
    for ok in [1] * 9 + [0]:
        strat.record_event("FVG", bool(ok))
    assert strat.readiness(10, 0.85)["ready"] is True
    strat.record_event("FVG", False)
    strat.record_event("FVG", False)
    assert strat.readiness(10, 0.85)["ready"] is False


def make_df(days=3):
    idx = pd.date_range("2026-10-12", periods=24 * days, freq="h")
    base = np.linspace(1.08, 1.09, len(idx))
    return pd.DataFrame({"open": base, "high": base + 0.001, "low": base - 0.001, "close": base + 0.0002}, index=idx)


def test_previous_day_levels_and_facts():
    df = make_df()
    lv = previous_day_levels(df)
    assert lv["date"] == "2026-10-13"
    assert lv["high"] == pytest.approx(df[df.index.date == pd.Timestamp("2026-10-13").date()]["high"].max())
    txt = facts_text("EURUSD", {"1h": df})
    assert "previous day (2026-10-13)" in txt and "EURUSD" in txt


def test_scan_sends_signal_once_and_logs(strat, png, tmp_path):
    strat.upsert_concept({"name": "FVG", "simple_definition": "gap"})
    sig = {"signal": "sell", "pair": "EURUSD", "entry": 1.0850, "stop": 1.0880, "targets": [1.08],
           "matched_rules": ["sweep"], "reasoning": "r"}
    model = FakeModel([json.dumps(sig), json.dumps(sig)])
    sent = []
    cfg = {"signals": {"pairs": ["EURUSD"], "timeframes": ["1h", "15m"]}}
    fetch_fn = lambda pair, tf, bars, provider, csv_dir: make_df()
    notify_fn = lambda text, image, cfg: sent.append((text, image))
    run_once(model, strat, cfg, fetch_fn, notify_fn)
    run_once(model, strat, cfg, fetch_fn, notify_fn)
    assert len(sent) == 1  # the same signal is not sent twice
    assert "SELL: EURUSD" in sent[0][0] and "not financial advice" in sent[0][0]
    assert len((strat.root / "signals.jsonl").read_text().splitlines()) == 2
    assert len(model.calls[0]["images"]) == 2  # one chart per timeframe, no examples yet


def test_none_signal_is_not_sent(strat):
    model = FakeModel([json.dumps({"signal": "none", "reasoning": "no setup"})])
    sent = []
    run_once(model, strat, {"signals": {"pairs": ["EURUSD"], "timeframes": ["1h"]}},
             lambda *a: make_df(), lambda *a: sent.append(a))
    assert sent == []
