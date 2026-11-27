"""Startup checks and a simple health report. Failures are reported, never fatal by themselves."""
from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("prime.watchdog")


async def supervise(factory, name: str, max_delay: float = 60.0) -> None:
    """Run a background coroutine forever: if it crashes, log it and start it again after a growing pause.
    `factory` is a function that returns a new coroutine each time (a finished coroutine cannot be reused)."""
    delay = 1.0
    while True:
        started = asyncio.get_running_loop().time()
        try:
            await factory()
            log.warning("%s finished on its own; restarting", name)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the whole point: keep the rest of the system alive
            log.exception("%s crashed; restart in %.0f s", name, delay)
        if asyncio.get_running_loop().time() - started > 120:
            delay = 1.0                      # it ran for a while: the next crash is a new problem
        await asyncio.sleep(delay)
        delay = min(max_delay, delay * 2)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def battery_state() -> dict:
    """Laptop battery: percent and whether it is plugged in. Empty dict on desktops without a battery."""
    try:
        import psutil
        b = psutil.sensors_battery()
    except Exception:  # noqa: BLE001
        return {}
    if b is None:
        return {}
    return {"percent": round(b.percent), "plugged": bool(b.power_plugged)}


def preflight(root: Path) -> list[Check]:
    checks = [
        Check("python", sys.version_info >= (3, 11), f"{sys.version_info.major}.{sys.version_info.minor}, need 3.11+"),
    ]
    for folder in ("config", "core", "backups", "workspace/00_Inbox", "workspace/01_Goals_&_Plans"):
        p = root / folder
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append(Check(f"folder {folder}", True, "writable"))
        except OSError as e:
            checks.append(Check(f"folder {folder}", False, f"not writable: {e}"))
    bat = battery_state()
    if bat:
        low = bat["percent"] < 30 and not bat["plugged"]
        checks.append(Check("battery", not low, f"{bat['percent']}%, {'plugged in' if bat['plugged'] else 'on battery'}"))
    else:
        checks.append(Check("battery", True, "no battery (desktop) or not readable"))
    for line in checks:
        (log.info if line.ok else log.warning)("preflight %s: %s — %s", "OK" if line.ok else "FAIL", line.name, line.detail)
    return checks
