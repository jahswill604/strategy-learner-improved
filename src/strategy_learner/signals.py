"""Signal engine: read live FX charts the way the trader taught, send signals."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import notify
from .charts import render_chart
from .data import facts_text, fetch, previous_day_levels
from .memory import Strategy
from .models import Model, extract_json
from .prompts import SIGNAL_SYSTEM


def scan_pair(model: Model, strat: Strategy, pair: str, cfg: dict, fetch_fn=fetch) -> dict:
    dcfg = cfg.get("data", {})
    scfg = cfg.get("signals", {})
    tfs = scfg.get("timeframes", ["1d", "4h", "1h", "15m"])
    day_hour = scfg.get("day_start_hour_utc", 0)
    frames = {tf: fetch_fn(pair, tf, scfg.get("bars", 150), dcfg.get("provider", "yfinance"), dcfg.get("csv_dir"))
              for tf in tfs}

    out_dir = strat.root / "scans"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    images = []
    for tf, df in frames.items():
        lv = previous_day_levels(df, day_hour)
        levels = {"prev day high": lv["high"], "prev day low": lv["low"]} if lv else None
        images.append(render_chart(df, out_dir / f"{pair}_{tf}_{stamp}.png", f"{pair} {tf}", levels))
    entry_chart = images[-1]
    images = list(images) + strat.example_paths(scfg.get("example_images", 3))

    user = (facts_text(pair, frames, day_hour) +
            "\n\nThe first images are the live charts, one per timeframe, in the order listed above. "
            "Any further images are the trader's own valid examples, for reference only. "
            "Decide if the trader's strategy has a valid setup right now. JSON only.")
    raw = model.complete(SIGNAL_SYSTEM + "\n\n# THE TRADER'S STRATEGY\n" + strat.knowledge_text(),
                         [{"role": "user", "content": user}], images)
    sig = extract_json(raw)
    sig.setdefault("signal", "none")
    sig["pair"] = sig.get("pair") or pair
    sig["chart"] = str(entry_chart)
    return sig


def format_signal(sig: dict, strategy_name: str) -> str:
    lines = [f"{sig['signal'].upper().replace('_', ' ')}: {sig['pair']} ({strategy_name})"]
    if sig["signal"] in ("buy", "sell"):
        lines.append(f"Entry {sig.get('entry')}  Stop {sig.get('stop')}  Targets {sig.get('targets')}")
    if sig.get("matched_rules"):
        lines.append("Matched: " + "; ".join(map(str, sig["matched_rules"])))
    if sig.get("missing_rules"):
        lines.append("Missing: " + "; ".join(map(str, sig["missing_rules"])))
    if sig.get("judgment_calls_to_check"):
        lines.append("Please check yourself: " + "; ".join(map(str, sig["judgment_calls_to_check"])))
    if sig.get("reasoning"):
        lines.append(sig["reasoning"])
    lines.append("This is a signal, not financial advice.")
    return "\n".join(lines)


def _key(sig: dict) -> str:
    try:
        entry = round(float(sig.get("entry") or 0), 4)
    except (TypeError, ValueError):
        entry = 0
    return f"{sig.get('pair')}|{sig.get('signal')}|{entry}"


def run_once(model: Model, strat: Strategy, cfg: dict, fetch_fn=fetch, notify_fn=notify.send) -> list[dict]:
    """Scan every configured pair once. Sends buy/sell signals (and near misses if enabled)."""
    scfg = cfg.get("signals", {})
    send_near = scfg.get("send_near_misses", False)
    seen_path = strat.root / "signals_seen.json"
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    results = []
    for pair in scfg.get("pairs", ["EURUSD"]):
        try:
            sig = scan_pair(model, strat, pair, cfg, fetch_fn)
        except Exception as e:  # keep scanning the other pairs
            print(f"[{pair}] scan failed: {e}")
            continue
        strat.log_signal(sig)
        results.append(sig)
        wanted = sig["signal"] in ("buy", "sell") or (send_near and sig["signal"] == "near_miss")
        if wanted and _key(sig) not in seen:
            notify_fn(format_signal(sig, strat.meta()["name"]), sig.get("chart"), cfg)
            seen.add(_key(sig))
        else:
            print(f"[{pair}] {sig['signal']}")
    seen_path.write_text(json.dumps(sorted(seen)))
    return results


def watch(model: Model, strat: Strategy, cfg: dict, fetch_fn=fetch):
    minutes = cfg.get("signals", {}).get("scan_every_minutes", 15)
    print(f"Watching every {minutes} minutes. Press Ctrl+C to stop.")
    while True:
        run_once(model, strat, cfg, fetch_fn)
        time.sleep(minutes * 60)
