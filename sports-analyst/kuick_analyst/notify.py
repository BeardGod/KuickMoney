"""Optional Telegram alert with the day's top picks."""

from __future__ import annotations

import os
from typing import Any

import requests


def send_telegram(date: str, picks: list[dict[str, Any]], limit: int = 10) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    top = sorted(picks, key=lambda p: -float(p.get("units") or 0))[:limit]
    lines = [f"KuickMoney card {date}: {len(picks)} pick(s)"]
    lines += [f"- {str(p.get('league', '')).upper()} {p.get('selection')} ({p.get('odds')}) "
              f"{p.get('units')}u - {p.get('summary', '')}" for p in top]
    resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": "\n".join(lines)[:4000]}, timeout=20)
    return resp.ok
