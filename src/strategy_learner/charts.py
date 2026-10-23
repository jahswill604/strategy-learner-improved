"""Draw simple candlestick chart images for the model to look at."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def render_chart(df, path, title: str = "", levels: dict | None = None):
    fig, ax = plt.subplots(figsize=(11, 6), dpi=110)
    for i, (_, r) in enumerate(df.iterrows()):
        up = r["close"] >= r["open"]
        color = "#1a9850" if up else "#d73027"
        ax.vlines(i, r["low"], r["high"], color=color, linewidth=1)
        lo, hi = sorted((r["open"], r["close"]))
        ax.bar(i, max(hi - lo, 1e-9), bottom=lo, color=color, width=0.7)
    for label, price in (levels or {}).items():
        ax.axhline(price, color="#4575b4", linestyle="--", linewidth=1)
        ax.text(0, price, f" {label}", color="#4575b4", va="bottom", fontsize=8)
    n = len(df)
    step = max(n // 8, 1)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.index[i])[5:16] for i in range(0, n, step)], rotation=30, fontsize=8)
    ax.set_title(title)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
