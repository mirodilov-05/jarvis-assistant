"""Push notifications to phone and watch through ntfy. Off unless PRIME_NTFY_TOPIC is set.

Uses only the standard library. A failed push is logged and never breaks the caller.
"""
from __future__ import annotations

import asyncio
import logging
import os
import urllib.request

log = logging.getLogger("prime.notify")
NTFY = "https://ntfy.sh"


def _post(topic: str, text: str, title: str, priority: str) -> None:
    req = urllib.request.Request(f"{NTFY}/{topic}", text.encode("utf-8"),
                                 {"Title": title.encode("utf-8").decode("latin-1", "ignore") or "Jarvis",
                                  "Priority": priority, "Tags": "robot"})
    with urllib.request.urlopen(req, timeout=8):
        pass


async def push(text: str, title: str = "Джарвис", priority: str = "default") -> bool:
    """Send one notification. Returns False when ntfy is not configured or the push failed."""
    topic = os.environ.get("PRIME_NTFY_TOPIC", "").strip()
    if not topic:
        return False
    try:
        await asyncio.to_thread(_post, topic, text, title, priority)
        return True
    except Exception as e:  # noqa: BLE001 — the network may be down; the assistant keeps working
        log.warning("ntfy push failed: %s", type(e).__name__)
        return False
