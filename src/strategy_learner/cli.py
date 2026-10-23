"""Command line: teach, test, status, scan, watch."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import memory_cli
from .memory import Strategy
from .models import get_model
from .signals import run_once, watch
from .teach import Teacher
from .tester import Tester, format_labels

HELP = (
    "Commands while teaching:\n"
    "  /valid <image path> <why it is valid>      send a valid example of the concept being discussed\n"
    "  /invalid <image path> <why it is invalid>  send an invalid example\n"
    "  /status                                    see what has been learned\n"
    "  /quit                                      save and leave (you can resume any time)\n"
)


def load_cfg(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        sys.exit(f"Config file '{path}' not found. Copy config.example.yaml to config.yaml and edit it.")
    return yaml.safe_load(p.read_text()) or {}


def open_strategy(cfg: dict, key: str) -> Strategy:
    return Strategy.open(cfg.get("storage", {}).get("dir", "strategies"), key)


def cmd_status(strat: Strategy, cfg: dict):
    th = cfg.get("readiness", {})
    strat.refresh_status(th.get("min_tests_per_concept", 10), th.get("min_accuracy", 0.85))
    m = strat.meta()
    print(f"\n{m['trader']} / {m['name']}  [{m['status']}]")
    if m.get("summary"):
        print(f"\nSummary: {m['summary']}")
    rep = strat.readiness(th.get("min_tests_per_concept", 10), th.get("min_accuracy", 0.85))
    for name, r in rep["concepts"].items():
        print(f"  {name}: {r['status']}, accuracy {r['accuracy']:.0%} over {r['tested']} tests"
              f"{'  READY' if r['ready'] else ''}")
    if m.get("open_questions"):
        print("\nStill unclear:")
        for q in m["open_questions"]:
            print(f"  - {q}")
    print(f"\nCharts tested: {rep['charts_tested']}")
    print("Ready to send signals." if rep["ready"] else "Not ready for signals yet (keep teaching and testing).")


def cmd_teach(strat: Strategy, cfg: dict):
    teacher = Teacher(get_model(cfg), strat)
    print(HELP)
    print("AI: " + teacher.opening() + "\n")
    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaved. See you next time.")
            return
        if not line:
            continue
        if line == "/quit":
            print("Saved. See you next time.")
            return
        if line == "/status":
            cmd_status(strat, cfg)
            continue
        images = []
        if line.startswith(("/valid", "/invalid")):
            kind = "valid" if line.startswith("/valid") else "invalid"
            parts = line.split(None, 2)
            if len(parts) < 2 or not Path(parts[1].strip('"')).exists():
                print("Usage: /valid <image path> <why>   (I could not find that image)")
                continue
            path, why = parts[1].strip('"'), (parts[2] if len(parts) > 2 else "")
            ok, info = teacher.add_image(kind, path, why)
            if not ok:
                print("AI: " + info)
                continue
            images = [path]
            line = f"[I am sending a {kind.upper()} example of '{info}'] {why or '(no reason given)'}"
        try:
            reply = teacher.turn(line, images)
        except Exception as e:
            print(f"Something went wrong talking to the model: {e}")
            continue
        print("\nAI: " + reply + "\n")


def cmd_test(strat: Strategy, cfg: dict, chart: str):
    th = cfg.get("readiness", {})
    tester = Tester(get_model(cfg), strat, th.get("min_tests_per_concept", 10), th.get("min_accuracy", 0.85))
    if not Path(chart).exists():
        sys.exit(f"Chart image '{chart}' not found.")
    labels, overall = tester.label(chart)
    while True:
        print("\nWhat I see:\n" + (format_labels(labels) or "  (nothing I recognise)"))
        if overall:
            print("\n" + overall)
        print("\nTell me what is wrong, one per line, like:\n  3: that gap was already filled\n"
              "  missed: there is also a sweep on the left\n"
              "Press Enter on an empty line when done. Type 'all good' if I got everything right.")
        wrong, missed = {}, []
        while True:
            line = input("> ").strip()
            if not line:
                break
            if line.lower() == "all good":
                break
            if line.lower().startswith("missed:"):
                missed.append(line[7:].strip())
            elif ":" in line and line.split(":", 1)[0].strip().isdigit():
                i, why = line.split(":", 1)
                wrong[int(i)] = why.strip()
            else:
                print("  (use '3: reason' or 'missed: what I missed')")
        learned, labels, overall = tester.correct(chart, labels, wrong, missed)
        if learned:
            print("\nWhat I learned: " + learned)
        if not wrong and not missed:
            break
        print("\nHere is my new attempt on the same chart.")
        again = input("Check it? (Enter to review, 'n' to stop): ").strip().lower()
        if again == "n":
            break
    cmd_status(strat, cfg)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="strategy-learner", description="Teach an AI your FX strategy, then get signals.")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, h in (("teach", "teach a strategy (starts or resumes)"), ("status", "show what has been learned"),
                    ("scan", "scan the market once"), ("watch", "scan the market on a loop")):
        p = sub.add_parser(name, help=h)
        p.add_argument("strategy", help="trader/strategy-name, e.g. ada/candle-range")
        if name in ("scan", "watch"):
            p.add_argument("--force", action="store_true", help="scan even if not marked ready")
    t = sub.add_parser("test", help="label a chart, correct the AI")
    t.add_argument("strategy")
    t.add_argument("chart", help="path to a chart image the AI has not seen")
    memory_cli.add_parsers(sub)
    a = ap.parse_args(argv)

    if a.cmd in memory_cli.COMMANDS:  # no model or API key needed
        cfg = yaml.safe_load(Path(a.config).read_text()) if Path(a.config).exists() else {}
        return memory_cli.run(a, open_strategy(cfg or {}, a.strategy))

    cfg = load_cfg(a.config)
    strat = open_strategy(cfg, a.strategy)
    if a.cmd == "teach":
        cmd_teach(strat, cfg)
    elif a.cmd == "status":
        cmd_status(strat, cfg)
    elif a.cmd == "test":
        cmd_test(strat, cfg, a.chart)
    else:
        th = cfg.get("readiness", {})
        strat.refresh_status(th.get("min_tests_per_concept", 10), th.get("min_accuracy", 0.85))
        if strat.meta()["status"] != "ready" and not a.force:
            sys.exit("This strategy is not marked ready yet. Keep teaching and testing, "
                     "or run with --force to scan anyway.")
        model = get_model(cfg)
        (run_once if a.cmd == "scan" else watch)(model, strat, cfg)


if __name__ == "__main__":
    main()
