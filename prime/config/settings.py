"""Settings for JARVIS PRIME OS. Secrets are read from environment variables, never stored in files."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from config.env import load_env  # noqa: E402 — secrets from prime\.env, before the settings read the environment

load_env(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    db_path: Path = ROOT / "data" / "prime.db"
    backup_dir: Path = ROOT / "backups"
    battery_low_percent: int = 30
    max_agent_steps: int = 8                      # circuit breaker: an agent run stops after this many steps
    tool_timeout_s: float = 20.0                  # every tool call has a hard timeout
    daily_budget_usd: float = 1.0                 # paid API budget per day (the guard stops at this limit)
    telegram_token: str = field(default_factory=lambda: os.environ.get("PRIME_TELEGRAM_TOKEN", ""))
    telegram_owner_id: int = int(os.environ.get("PRIME_TELEGRAM_OWNER", "0") or 0)


SETTINGS = Settings()
