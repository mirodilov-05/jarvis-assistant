"""Three levels of trust for every action the assistant takes.

READ_ONLY   - reads only (files, status, plans). Runs at once.
SAFE_WRITE  - creates tasks, notes, switches devices. Runs at once.
CRITICAL    - deletes, shell, sending anything outside. Blocked until the owner confirms with a code.
"""
from __future__ import annotations

import enum
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("prime.security")


class Level(enum.IntEnum):
    READ_ONLY = 0
    SAFE_WRITE = 1
    CRITICAL = 2


@dataclass
class Pending:
    code: str
    action: str
    args: dict[str, Any]
    expires: float


@dataclass
class Guard:
    """Holds CRITICAL actions until confirmed. Codes expire after ttl_s seconds and work once."""
    pending: dict[str, Pending] = field(default_factory=dict)
    ttl_s: float = 120.0

    def ask(self, action: str, args: dict[str, Any]) -> str:
        """Park a CRITICAL action; returns the short code the owner must send to confirm it."""
        self._purge()
        code = secrets.token_hex(3)
        self.pending[code] = Pending(code, action, args, time.time() + self.ttl_s)
        log.warning("CRITICAL action %s parked under code %s", action, code)
        return code

    def confirm(self, code: str) -> Pending | None:
        self._purge()
        return self.pending.pop(code.strip().lower(), None)

    def cancel(self, code: str) -> bool:
        return self.pending.pop(code.strip().lower(), None) is not None

    def _purge(self) -> None:
        now = time.time()
        for k in [k for k, p in self.pending.items() if p.expires < now]:
            self.pending.pop(k, None)


def check(level: Level, requested: Level) -> bool:
    """True when an action of `requested` level may run immediately at trust level `level`.
    CRITICAL actions never run directly: they always need a confirmation code."""
    return requested < Level.CRITICAL and requested <= level
