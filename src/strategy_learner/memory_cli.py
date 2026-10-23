"""Commands for saving what was learned. Used by the /trade skill, where Claude is the student.

They need no API key and no config file: they only read and write the strategy folder.
"""
from __future__ import annotations

import json
import sys

from .memory import Strategy
from .skills import build_skills

COMMANDS = ("save-concept", "add-example", "mark-learned", "save-rules", "build-skills")


def add_parsers(sub):
    p = sub.add_parser("save-concept", help="save/update a concept; JSON on stdin (see prompts.CONCEPT_SCHEMA)")
    p.add_argument("strategy")
    p = sub.add_parser("add-example", help="save a valid/invalid example image for a concept")
    p.add_argument("strategy"); p.add_argument("concept"); p.add_argument("kind", choices=["valid", "invalid"])
    p.add_argument("image"); p.add_argument("reason", nargs="?", default="")
    p = sub.add_parser("mark-learned", help="mark a concept learned (refused if anything is missing)")
    p.add_argument("strategy"); p.add_argument("concept")
    p.add_argument("--trader-confirmed", action="store_true", help="the trader said the explain-back was right")
    p = sub.add_parser("save-rules", help="save rules/summary/open questions; JSON on stdin")
    p.add_argument("strategy")
    p = sub.add_parser("build-skills", help="turn learned concepts into small skills")
    p.add_argument("strategy"); p.add_argument("--out", help="folder to write into (default: <strategy>/skills)")
    p.add_argument("--all", action="store_true", help="include concepts not fully learned yet")


def run(a, strat: Strategy):
    if a.cmd == "save-concept":
        c = strat.upsert_concept(json.load(sys.stdin))
        print(f"saved concept: {c.get('name', '(no name given)')}")
    elif a.cmd == "add-example":
        strat.add_example(a.concept, a.kind, a.image, a.reason)
        print(f"saved {a.kind} example for {a.concept}")
    elif a.cmd == "mark-learned":
        if a.trader_confirmed:
            strat.confirm(a.concept)
        ok, missing = strat.mark_learned(a.concept)
        if ok:
            build_skills(strat)
            print(f"{a.concept} is learned; skills updated")
        else:
            print(f"NOT learned yet. Still missing: {', '.join(missing)}")
            sys.exit(1)
    elif a.cmd == "save-rules":
        d = json.load(sys.stdin)
        m = strat.meta()
        for k, v in (d.get("rules") or {}).items():
            if k == "no_trade":
                cur = m["rules"].setdefault("no_trade", [])
                cur.extend(i for i in v if i not in cur)
            elif v:
                m["rules"][k] = v
        if "summary" in d:
            m["summary"] = d["summary"]
        if "open_questions" in d:
            m["open_questions"] = d["open_questions"]
        if "focus" in d:
            m["focus"] = d["focus"]
        strat.save_meta(m)
        print("saved rules")
    elif a.cmd == "build-skills":
        for p in build_skills(strat, a.out, include_unlearned=a.all):
            print(p)
