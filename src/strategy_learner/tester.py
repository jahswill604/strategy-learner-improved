"""Testing and correcting: label a fresh chart, get corrected, learn, relabel."""
from __future__ import annotations

from .memory import Strategy
from .models import Model, extract_json
from .prompts import CORRECTION_SYSTEM, TESTER_SYSTEM


def format_labels(labels: list[dict]) -> str:
    return "\n".join(
        f"{l['id']}. [{l.get('concept', '?')}] {l.get('where', '')}: {l.get('reason', '')}" for l in labels
    )


class Tester:
    def __init__(self, model: Model, strat: Strategy, min_events: int = 10, min_acc: float = 0.85):
        self.model, self.strat = model, strat
        self.min_events, self.min_acc = min_events, min_acc

    def _knowledge(self) -> str:
        return "\n\n# WHAT YOU HAVE LEARNED\n" + self.strat.knowledge_text()

    def label(self, chart) -> tuple[list[dict], str]:
        raw = self.model.complete(
            TESTER_SYSTEM + self._knowledge(),
            [{"role": "user", "content": "Label everything you have learned on this chart. JSON only."}],
            [chart],
        )
        data = extract_json(raw)
        labels = [l for l in data.get("labels") or [] if isinstance(l, dict)]
        for i, l in enumerate(labels, 1):
            l["id"] = i
        return labels, data.get("overall", "")

    def score(self, labels: list[dict], wrong: dict[int, str]):
        for l in labels:
            if l.get("concept"):
                self.strat.record_event(l["concept"], l["id"] not in wrong)
        self.strat.count_chart()

    def correct(self, chart, labels: list[dict], wrong: dict[int, str], missed: list[str]):
        """Score the labels, learn from the corrections, then relabel the same chart."""
        self.score(labels, wrong)
        self.strat.log_correction({
            "chart": str(chart),
            "labels": labels,
            "wrong": {str(k): v for k, v in wrong.items()},
            "missed": missed,
        })
        learned = ""
        if wrong or missed:
            feedback = "Your labels:\n" + format_labels(labels) + "\n\nThe trader's corrections:\n"
            feedback += "\n".join(f"- label {i} is wrong: {why}" for i, why in wrong.items())
            feedback += "".join(f"\n- you missed: {m}" for m in missed)
            raw = self.model.complete(
                CORRECTION_SYSTEM + self._knowledge(),
                [{"role": "user", "content": feedback}],
                [chart],
            )
            data = extract_json(raw)
            learned = data.get("learned", "")
            for c in data.get("concepts") or []:
                if isinstance(c, dict):
                    self.strat.upsert_concept(c)
            for e in data.get("examples") or []:
                if isinstance(e, dict) and e.get("concept") and e.get("kind") in ("valid", "invalid"):
                    self.strat.add_example(e["concept"], e["kind"], chart, e.get("reason", ""))
            for name in data.get("missed_concepts") or []:
                self.strat.record_event(name, False)
            rules = data.get("no_trade_rules") or []
            if rules:
                m = self.strat.meta()
                cur = m["rules"].setdefault("no_trade", [])
                cur.extend(r for r in rules if r not in cur)
                self.strat.save_meta(m)
        self.strat.refresh_status(self.min_events, self.min_acc)
        new_labels, overall = self.label(chart)
        return learned, new_labels, overall
