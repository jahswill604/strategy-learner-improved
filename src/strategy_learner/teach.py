"""Teaching: the curious-child / scared-trader conversation."""
from __future__ import annotations

from pathlib import Path

from .memory import Strategy
from .models import Model, extract_json
from .prompts import TEACHER_SYSTEM
from .skills import build_skills

GREETING = (
    "Hi! I'm ready to learn your strategy. Explain it to me in your own words, "
    "as if you're teaching a friend who has never traded it. Don't worry about "
    "technical terms. I'll ask questions as we go."
)


class Teacher:
    def __init__(self, model: Model, strat: Strategy):
        self.model, self.strat = model, strat

    def opening(self) -> str:
        """What to show when a session starts or resumes."""
        chat = self.strat.chat()
        for m in reversed(chat):
            if m["role"] == "assistant":
                return "(Welcome back. Last time I asked:)\n" + m["content"]
        self.strat.add_chat("assistant", GREETING)
        return GREETING

    def system(self) -> str:
        return TEACHER_SYSTEM + "\n\n# WHAT YOU HAVE LEARNED SO FAR\n" + self.strat.knowledge_text()

    def add_image(self, kind: str, path: str, reason: str) -> tuple[bool, str]:
        """Save a valid/invalid example for the concept being discussed."""
        focus = self.strat.meta().get("focus")
        if not focus:
            return False, "I'm not discussing a specific concept yet. Tell me about it first, then send the picture."
        self.strat.add_example(focus, kind, path, reason)
        return True, focus

    def turn(self, text: str, images=()) -> str:
        notes = self.strat.meta().get("notes") or []
        self.strat.add_chat("user", text)
        msgs = self.strat.chat_messages()
        if notes:
            msgs[-1] = {"role": "user", "content": msgs[-1]["content"] +
                        "\n\n[system notes, not from the trader: " + " ".join(notes) + "]"}
        raw = self.model.complete(self.system(), msgs, list(images))
        data = extract_json(raw)
        say = (data.get("say") or "").strip() or raw.strip()
        self.apply(data)
        self.strat.add_chat("assistant", say)
        return say

    def apply(self, data: dict):
        s = self.strat
        m = s.meta()
        for c in data.get("concepts") or []:
            if isinstance(c, dict):
                s.upsert_concept(c)
        for n in data.get("trader_confirmed") or []:
            s.confirm(n)
        notes = []
        newly_learned = False
        for n in data.get("mark_learned") or []:
            ok, missing = s.mark_learned(n)
            newly_learned = newly_learned or ok
            if not ok:
                notes.append(f"'{n}' could not be marked learned; still missing: {', '.join(missing)}. Ask the trader for these.")
        if data.get("strategy_complete"):
            cs = s.concepts()
            open_q = data.get("open_questions", m.get("open_questions"))
            unlearned = [c["name"] for c in cs.values() if c["status"] != "learned"]
            if unlearned or open_q:
                notes.append("The strategy is not complete yet. Unlearned concepts: "
                             f"{', '.join(unlearned) or 'none'}. Open questions: {len(open_q or [])}.")
            else:
                m["status"] = "taught"
        if data.get("open_questions") is not None:
            m["open_questions"] = [q for q in data["open_questions"] if q]
        rules = data.get("rules")
        if isinstance(rules, dict):
            for k, v in rules.items():
                if k == "no_trade":
                    cur = m["rules"].setdefault("no_trade", [])
                    for item in v or []:
                        if item and item not in cur:
                            cur.append(item)
                elif v:
                    m["rules"][k] = v
        if data.get("summary"):
            m["summary"] = data["summary"]
        if "focus" in data:
            m["focus"] = data["focus"]
        m["notes"] = notes
        s.save_meta(m)
        if newly_learned:
            build_skills(s)  # every learned concept becomes its own small skill
