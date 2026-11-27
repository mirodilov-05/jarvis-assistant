"""Telegram hub: a phone remote for Prime. Plain Bot API over HTTPS (no extra packages).

Only the owner (PRIME_TELEGRAM_OWNER) gets answers. Everyone else is ignored without a reply.
Set PRIME_TELEGRAM_TOKEN and PRIME_TELEGRAM_OWNER in the environment; without them the hub stays off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request

log = logging.getLogger("prime.telegram")
API = "https://api.telegram.org/bot{token}/{method}"


def _call(token: str, method: str, timeout: float = 35, **params) -> dict:
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(API.format(token=token, method=method), data, timeout=timeout) as r:
        return json.loads(r.read())


async def run(prime, token: str, owner_id: int) -> None:
    """Long-poll for messages and answer the owner. Errors back off instead of crashing."""
    if not token or not owner_id:
        log.info("telegram hub off: no token or owner id in the environment")
        await asyncio.Event().wait()          # stay idle (a returned task would be restarted over and over)
        return
    offset = 0
    delay = 1.0
    while not prime.stop_event.is_set():
        try:
            res = await asyncio.to_thread(_call, token, "getUpdates", timeout=30, offset=offset, timeout_s=25)
            delay = 1.0
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat", {}).get("id")
                sender = msg.get("from", {}).get("id")
                text = msg.get("text", "")
                if not text or sender != owner_id:
                    continue                                   # strangers get no answer at all
                reply = await prime.handle(text)
                await asyncio.to_thread(_call, token, "sendMessage", chat_id=chat, text=reply[:4000])
        except Exception as e:  # noqa: BLE001 — network down: wait and try again
            log.warning("telegram: %s; retry in %.0f s", type(e).__name__, delay)
            await asyncio.sleep(delay)
            delay = min(60.0, delay * 2)
