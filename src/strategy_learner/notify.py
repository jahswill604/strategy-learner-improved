"""Send signals to the trader. Telegram if configured, otherwise print."""
from __future__ import annotations

import os


def send(text: str, image=None, cfg: dict | None = None) -> str:
    tg = (cfg or {}).get("notify", {}).get("telegram", {})
    token = os.environ.get(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
    chat = os.environ.get(tg.get("chat_id_env", "TELEGRAM_CHAT_ID"))
    if token and chat:
        import requests
        base = f"https://api.telegram.org/bot{token}"
        if image:
            with open(image, "rb") as f:
                r = requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": text[:1000]},
                                  files={"photo": f}, timeout=30)
        else:
            r = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text}, timeout=30)
        r.raise_for_status()
        return "telegram"
    print("\n=== SIGNAL ===\n" + text + (f"\n(chart: {image})" if image else "") + "\n==============")
    return "console"
