"""Reads prime\\.env (KEY=VALUE lines) into os.environ without overwriting real environment variables.

No extra package needed. Values are never printed anywhere.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env(path: Path) -> int:
    """Load the file if it exists. Returns how many variables were set."""
    if not path.exists():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def present(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())
