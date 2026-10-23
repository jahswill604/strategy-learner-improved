"""Strategy memory: everything the AI learns is saved here as plain files.

Layout (one folder per trader + strategy):
    strategy.json   meta: status, focus, open questions, rules, notes
    concepts.json   every concept the AI has learned about
    examples.json   index of valid/invalid example images
    examples/       the example images themselves
    chat.jsonl      the full teaching conversation
    scores.json     per-concept accuracy from test charts
    corrections.jsonl  every correction the trader made
    signals.jsonl   every signal the engine produced
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

LIST_FIELDS = ("failure_cases", "looks_similar_but_doesnt_count", "timeframes")
TEXT_FIELDS = ("parent", "simple_definition", "valid_reason", "invalid_reason", "invalidation")
WINDOW = 20


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "unnamed"


class Strategy:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "examples").mkdir(exist_ok=True)

    # ---------- creation / loading ----------
    @classmethod
    def open(cls, base, key: str, market: str = "forex") -> "Strategy":
        """key looks like 'trader/strategy-name'."""
        parts = [slug(p) for p in key.split("/") if p.strip()]
        if len(parts) != 2:
            raise ValueError("Strategy must be written as trader/strategy-name")
        s = cls(Path(base) / parts[0] / parts[1])
        if not (s.root / "strategy.json").exists():
            s._write("strategy.json", {
                "name": parts[1], "trader": parts[0], "market": market,
                "status": "learning", "focus": None, "open_questions": [],
                "rules": {}, "summary": "", "notes": [],
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
        return s

    # ---------- raw io ----------
    def _read(self, fname, default):
        p = self.root / fname
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def _write(self, fname, data):
        (self.root / fname).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _append(self, fname, rec):
        with open(self.root / fname, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------- meta ----------
    def meta(self) -> dict:
        return self._read("strategy.json", {})

    def save_meta(self, m: dict):
        self._write("strategy.json", m)

    # ---------- concepts ----------
    def concepts(self) -> dict:
        return self._read("concepts.json", {})

    def upsert_concept(self, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            return {}
        cs = self.concepts()
        k = slug(name)
        c = cs.get(k) or {
            "name": name, "parent": "", "simple_definition": "", "valid_reason": "",
            "invalid_reason": "", "invalidation": "", "failure_cases": [],
            "looks_similar_but_doesnt_count": [], "timeframes": [],
            "judgment_call": False, "confirmed": False, "status": "learning",
        }
        before = c["simple_definition"]
        for f in TEXT_FIELDS:
            v = data.get(f)
            if isinstance(v, str) and v.strip():
                c[f] = v.strip()
        for f in LIST_FIELDS:
            for item in data.get(f) or []:
                if item and item not in c[f]:
                    c[f].append(item)
        if "judgment_call" in data:
            c["judgment_call"] = bool(data["judgment_call"])
        if c["simple_definition"] != before and before:
            # the meaning changed, so the trader must re-confirm
            c["confirmed"] = False
            c["status"] = "learning"
        cs[k] = c
        self._write("concepts.json", cs)
        return c

    def confirm(self, name: str):
        cs = self.concepts()
        k = slug(name)
        if k in cs:
            cs[k]["confirmed"] = True
            self._write("concepts.json", cs)

    def missing_for_learned(self, name: str) -> list[str]:
        c = self.concepts().get(slug(name))
        if not c:
            return ["the concept does not exist yet"]
        ex = self.examples().get(slug(name), [])
        missing = []
        if not c["simple_definition"]:
            missing.append("a simple definition")
        if not any(e["kind"] == "valid" for e in ex):
            missing.append("a valid example image")
        if not any(e["kind"] == "invalid" for e in ex):
            missing.append("an invalid example image")
        if not c["invalidation"]:
            missing.append("what makes it no longer valid")
        if not c["failure_cases"]:
            missing.append("how it can fail")
        if not c["confirmed"]:
            missing.append("the trader's confirmation of the explain-back")
        return missing

    def mark_learned(self, name: str):
        missing = self.missing_for_learned(name)
        if missing:
            return False, missing
        cs = self.concepts()
        cs[slug(name)]["status"] = "learned"
        self._write("concepts.json", cs)
        return True, []

    # ---------- examples ----------
    def examples(self) -> dict:
        return self._read("examples.json", {})

    def add_example(self, concept: str, kind: str, src, reason: str = "") -> dict:
        if kind not in ("valid", "invalid"):
            raise ValueError("kind must be 'valid' or 'invalid'")
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(f"Image not found: {src}")
        k = slug(concept)
        if k not in self.concepts():
            self.upsert_concept({"name": concept})
        folder = self.root / "examples" / k
        folder.mkdir(parents=True, exist_ok=True)
        n = len(list(folder.iterdir())) + 1
        dest = folder / f"{n:03d}_{kind}{src.suffix.lower() or '.png'}"
        shutil.copy2(src, dest)
        rec = {"file": str(dest.relative_to(self.root)), "kind": kind, "reason": reason}
        ex = self.examples()
        ex.setdefault(k, []).append(rec)
        self._write("examples.json", ex)
        return rec

    def example_paths(self, limit: int = 3) -> list[Path]:
        """A few valid example images, from different concepts."""
        out = []
        for recs in self.examples().values():
            for r in recs:
                if r["kind"] == "valid":
                    out.append(self.root / r["file"])
                    break
            if len(out) >= limit:
                break
        return out

    # ---------- chat ----------
    def add_chat(self, role: str, content: str):
        self._append("chat.jsonl", {"role": role, "content": content})

    def chat(self) -> list[dict]:
        p = self.root / "chat.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def chat_messages(self, limit: int = 30) -> list[dict]:
        """Recent chat, shaped so roles alternate and it starts with the user."""
        out: list[dict] = []
        for m in self.chat()[-limit:]:
            if out and out[-1]["role"] == m["role"]:
                out[-1]["content"] += "\n\n" + m["content"]
            else:
                out.append({"role": m["role"], "content": m["content"]})
        while out and out[0]["role"] != "user":
            out.pop(0)
        return out

    # ---------- corrections / signals ----------
    def log_correction(self, rec: dict):
        self._append("corrections.jsonl", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **rec})

    def log_signal(self, rec: dict):
        self._append("signals.jsonl", {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **rec})

    # ---------- scores ----------
    def scores(self) -> dict:
        return self._read("scores.json", {"events": {}, "charts": 0})

    def record_event(self, concept: str, ok: bool):
        s = self.scores()
        s["events"].setdefault(slug(concept), []).append(1 if ok else 0)
        self._write("scores.json", s)

    def count_chart(self):
        s = self.scores()
        s["charts"] += 1
        self._write("scores.json", s)

    def accuracy(self, concept: str):
        ev = self.scores()["events"].get(slug(concept), [])[-WINDOW:]
        return (sum(ev) / len(ev) if ev else 0.0), len(ev)

    def readiness(self, min_events: int = 10, min_acc: float = 0.85) -> dict:
        cs = self.concepts()
        report, ready = {}, bool(cs)
        for k, c in cs.items():
            acc, n = self.accuracy(c["name"])
            ok = c["status"] == "learned" and n >= min_events and acc >= min_acc
            report[c["name"]] = {"status": c["status"], "accuracy": round(acc, 2), "tested": n, "ready": ok}
            ready = ready and ok
        return {"ready": ready, "concepts": report, "charts_tested": self.scores()["charts"]}

    def refresh_status(self, min_events: int = 10, min_acc: float = 0.85) -> str:
        m = self.meta()
        cs = self.concepts()
        if m["status"] == "ready" and not self.readiness(min_events, min_acc)["ready"]:
            m["status"] = "taught"
        elif m["status"] in ("taught", "ready") and self.readiness(min_events, min_acc)["ready"]:
            m["status"] = "ready"
        elif m["status"] == "taught" and cs and any(c["status"] != "learned" for c in cs.values()):
            m["status"] = "learning"
        self.save_meta(m)
        return m["status"]

    # ---------- what gets shown to the model ----------
    def knowledge_text(self) -> str:
        m = self.meta()
        ex = self.examples()
        lines = [f"Trader: {m['trader']} | Strategy: {m['name']} | Market: {m['market']} | Status: {m['status']}"]
        if m.get("summary"):
            lines.append(f"Summary: {m['summary']}")
        if m.get("rules"):
            lines.append("Rules: " + json.dumps(m["rules"], ensure_ascii=False))
        if m.get("open_questions"):
            lines.append("Still unclear (open questions): " + "; ".join(m["open_questions"]))
        if m.get("focus"):
            lines.append(f"Currently discussing: {m['focus']}")
        for k, c in self.concepts().items():
            e = ex.get(k, [])
            lines.append(
                f"\n## {c['name']} [{c['status']}{'; confirmed' if c['confirmed'] else ''}"
                f"{'; JUDGMENT CALL' if c['judgment_call'] else ''}]"
            )
            for f in TEXT_FIELDS + LIST_FIELDS:
                if c.get(f):
                    lines.append(f"- {f}: {c[f]}")
            for r in e:
                lines.append(f"- {r['kind']} example image ({r['file']}): {r['reason']}")
        return "\n".join(lines)
