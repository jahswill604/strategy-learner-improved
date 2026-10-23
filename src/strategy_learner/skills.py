"""Turn what was learned into skills: one small skill per concept, plus one for the whole strategy.

Each concept skill is a folder with a SKILL.md and its own copy of the trader's
valid/invalid example images, so it works on its own.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .memory import Strategy, slug


def _fm(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {json.dumps(description[:1000])}\n---\n\n"


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- (none recorded yet)"


def concept_skill_name(strategy_name: str, concept_name: str) -> str:
    return slug(f"{strategy_name}-{concept_name}")[:64].strip("-")


def build_skills(strat: Strategy, out_dir=None, include_unlearned: bool = False) -> list[Path]:
    """Write the skills and return the SKILL.md paths. Safe to run again; it rewrites them."""
    meta = strat.meta()
    out = Path(out_dir) if out_dir else strat.root / "skills"
    out.mkdir(parents=True, exist_ok=True)
    examples = strat.examples()
    written, listing = [], []

    for k, c in strat.concepts().items():
        if c["status"] != "learned" and not include_unlearned:
            continue
        name = concept_skill_name(meta["name"], c["name"])
        folder = out / name
        if folder.exists():
            shutil.rmtree(folder)
        (folder / "examples").mkdir(parents=True)

        lines = []
        for r in examples.get(k, []):
            src = strat.root / r["file"]
            if src.exists():
                dest = folder / "examples" / src.name
                shutil.copy2(src, dest)
                lines.append(f"- **{r['kind'].upper()}**: `examples/{src.name}`. {r.get('reason') or ''}".rstrip())

        desc = (f"{c['name']} as defined by trader {meta['trader']} in the {meta['name']} FX strategy. "
                f"Use when labeling, judging or scanning for {c['name']} on a forex chart, "
                f"or when a rule of this strategy mentions it.")
        body = [_fm(name, desc), f"# {c['name']}\n"]
        if c.get("parent"):
            body.append(f"Part of: **{c['parent']}**\n")
        if c["status"] != "learned":
            body.append("> Not fully learned yet. Treat with care and ask the trader.\n")
        if c.get("judgment_call"):
            body.append("> **Judgment call.** The trader could not reduce this to exact rules. "
                        "Never decide it alone: flag it for the trader to check.\n")
        body.append(f"## In simple words\n{c['simple_definition'] or '(not recorded)'}\n")
        if c.get("valid_reason"):
            body.append(f"## Why a valid one is valid\n{c['valid_reason']}\n")
        if c.get("invalid_reason"):
            body.append(f"## Why an invalid one is invalid\n{c['invalid_reason']}\n")
        body.append(f"## It stops being valid when\n{c['invalidation'] or '(not recorded)'}\n")
        body.append(f"## Looks similar but does NOT count\n{_bullets(c['looks_similar_but_doesnt_count'])}\n")
        body.append(f"## How it can fail\n{_bullets(c['failure_cases'])}\n")
        if c["timeframes"]:
            body.append(f"## Timeframes\n{', '.join(c['timeframes'])}\n")
        body.append("## The trader's example images\n" + ("\n".join(lines) or "- (none)") +
                    "\n\nLook at these images before judging a chart.\n")
        (folder / "SKILL.md").write_text("\n".join(body), encoding="utf-8")
        written.append(folder / "SKILL.md")
        listing.append((c["name"], name, c))

    # the strategy skill ties the small ones together
    sname = slug(meta["name"])[:64]
    folder = out / sname
    folder.mkdir(parents=True, exist_ok=True)
    rules = meta.get("rules", {})
    desc = (f"Trader {meta['trader']}'s {meta['name']} FX strategy: its rules, when not to trade, and the "
            f"concept skills it is made of. Use when analysing forex charts or looking for signals for this strategy.")
    body = [_fm(sname, desc), f"# {meta['name']} (trader: {meta['trader']}, market: {meta['market']})\n"]
    body.append(f"Status: {meta['status']}\n")
    if meta.get("summary"):
        body.append(f"## Summary\n{meta['summary']}\n")
    body.append("## Rules")
    for key in ("pairs", "sessions", "timeframes", "entry", "stop_loss", "take_profit", "risk"):
        if rules.get(key):
            body.append(f"- **{key.replace('_', ' ').title()}**: {rules[key]}")
    body.append("\n## When NOT to trade\n" + _bullets(rules.get("no_trade")) + "\n")
    body.append("## Concept skills: read EVERY one before any analysis or decision")
    body.append("Before looking at any chart or price, open and read each of these small skills in full, "
                "including their example images. Never skip one, and never use your general idea of a term "
                "like \"sweep\" or \"FVG\": this trader's meaning is the only one that counts.\n")
    for cname, skill_name, c in listing:
        flag = " (judgment call)" if c.get("judgment_call") else ""
        body.append(f"- `{skill_name}`: {cname}{flag}. {c['simple_definition']}")
    if meta.get("open_questions"):
        body.append("\n## Still unclear\n" + _bullets(meta["open_questions"]))
    body.append(
        "\n## How to analyse a chart with this strategy\n"
        "0. Read every concept skill listed above. If a term comes up that has no skill, say so and ask the "
        "trader instead of guessing.\n"
        "1. Go top-down through the timeframes the trader uses, using exact prices from real candle data.\n"
        "2. For each concept, follow its skill and example images, then decide: PRESENT, ABSENT or UNSURE, "
        "with the exact evidence. Use the trader's definition exactly. Do not invent rules.\n"
        "3. Check every no-trade rule first. If one applies, there is no signal.\n"
        "4. Before deciding, ask \"how could I lose on this?\" and go through each concept's failure cases.\n"
        "5. Anything marked judgment call or UNSURE is flagged for the trader to check.\n"
        "6. Give: signal (buy / sell / none / near miss), entry, stop, targets, which rules matched, which are missing. "
        "This is a signal for the trader to decide on, not financial advice.\n"
    )
    (folder / "SKILL.md").write_text("\n".join(body), encoding="utf-8")
    written.append(folder / "SKILL.md")
    return written
