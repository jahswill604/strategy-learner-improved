import base64

import pytest

from strategy_learner.memory import Strategy
from strategy_learner.skills import build_skills

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def strat(tmp_path):
    s = Strategy.open(tmp_path / "s", "ada/candle-range")
    img = tmp_path / "a.png"
    img.write_bytes(PNG)
    for name, parent in (("FVG", "Key level"), ("Sweep", "")):
        s.upsert_concept({"name": name, "parent": parent, "simple_definition": f"{name} in plain words",
                          "invalidation": "filled", "failure_cases": ["news"]})
        s.add_example(name, "valid", img, "clean")
        s.add_example(name, "invalid", img, "filled")
        s.confirm(name)
        s.mark_learned(name)
    s.upsert_concept({"name": "Order block", "simple_definition": "half taught"})
    return s


def test_one_small_skill_per_learned_concept_plus_strategy_skill(strat, tmp_path):
    out = tmp_path / "skills"
    paths = build_skills(strat, out)
    names = sorted(p.parent.name for p in paths)
    assert names == ["candle-range", "candle-range-fvg", "candle-range-sweep"]  # unlearned concept is left out
    fvg = (out / "candle-range-fvg" / "SKILL.md").read_text()
    assert fvg.startswith("---\nname: candle-range-fvg\n")
    assert (out / "candle-range-fvg" / "examples" / "001_valid.png").exists()  # its own copy of the pictures


def test_strategy_skill_forces_reading_every_concept_skill(strat, tmp_path):
    out = tmp_path / "skills"
    build_skills(strat, out)
    text = (out / "candle-range" / "SKILL.md").read_text()
    assert "read EVERY one before any analysis" in text
    assert "candle-range-fvg" in text and "candle-range-sweep" in text
    assert "no skill" in text  # unknown terms must be asked about, not guessed
