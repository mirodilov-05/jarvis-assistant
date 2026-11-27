"""Chooses the brain for a request: Gemini (cloud), Ollama (local), or an offline message.

Gemini replaces Claude here: its key is read from the environment (GEMINI_API_KEY) or from the same
Windows Credential Manager entry the assistant already uses ("gemini:api_key"). The key is never printed.

Budget guard: paid calls stop when today's spend reaches the limit (Gemini free tier costs nothing).
Battery guard: on battery below 30 percent the saver mode is on and cloud calls are avoided.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("prime.router")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = "gemini-flash-latest"


def gemini_key() -> str:
    """GEMINI_API_KEY from the environment, else the key the assistant already stores. Empty if none."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        import keyring
        return (keyring.get_password("jarvis-assistant", "gemini:api_key") or "").strip()
    except Exception:  # noqa: BLE001 — no keyring means no key, and that is fine
        return ""


@dataclass
class Budget:
    limit_usd: float
    day: str = field(default_factory=lambda: dt.date.today().isoformat())
    spent: float = 0.0

    def _roll(self) -> None:
        today = dt.date.today().isoformat()
        if today != self.day:
            self.day, self.spent = today, 0.0

    def allows_paid(self) -> bool:
        self._roll()
        return self.spent < self.limit_usd

    def record(self, cost_usd: float) -> None:
        self._roll()
        self.spent += cost_usd


def battery_saver(percent: int | None, plugged: bool | None) -> bool:
    """True when the laptop should save energy: on battery and below 30 percent."""
    return percent is not None and plugged is False and percent < 30


class Router:
    def __init__(self, key: str, budget: Budget, ollama_url: str = "http://127.0.0.1:11434",
                 local_model: str = "qwen2.5:7b", model: str = GEMINI_MODEL) -> None:
        self.key = key
        self.budget = budget
        self.ollama_url = ollama_url
        self.local_model = local_model
        self.model = model
        self.saver = False

    def set_battery(self, percent: int | None, plugged: bool | None) -> None:
        was = self.saver
        self.saver = battery_saver(percent, plugged)
        if self.saver != was:
            log.warning("battery saver %s (%s%%, plugged=%s)", "ON" if self.saver else "off", percent, plugged)

    def pick(self, need_cloud: bool) -> str:
        """'gemini', 'local' or 'offline'. Cloud only for hard tasks, with a key, budget and battery allowing."""
        if need_cloud and self.key and not self.saver and self.budget.allows_paid():
            return "gemini"
        if self.local_available():
            return "local"
        return "offline"

    def local_available(self) -> bool:
        try:
            with urllib.request.urlopen(self.ollama_url + "/api/tags", timeout=1.5) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001 — Ollama being off is a normal situation
            return False

    async def complete(self, system: str, user: str, need_cloud: bool = False) -> tuple[str, str]:
        """Returns (reply, engine). Never raises: the worst case is the offline message."""
        engine = self.pick(need_cloud)
        try:
            if engine == "gemini":
                return await self._gemini(system, user), "gemini"
            if engine == "local":
                return await self._ollama(system, user), "local"
        except Exception as e:  # noqa: BLE001 — fall through to offline
            log.error("%s failed: %s", engine, type(e).__name__)
        return "Сейчас нет связи с мозгом. Простые команды работают: таймеры, дела, заметки.", "offline"

    async def _gemini(self, system: str, user: str) -> str:
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": 800, "temperature": 0.3},
        }).encode("utf-8")

        def call() -> dict:
            req = urllib.request.Request(GEMINI_URL.format(model=self.model), body,
                                         {"Content-Type": "application/json", "x-goog-api-key": self.key})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        data = await asyncio.to_thread(call)
        self.budget.record(0.0)                                  # free tier; still counted as a call
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()

    async def _ollama(self, system: str, user: str) -> str:
        def call() -> str:
            body = json.dumps({"model": self.local_model, "stream": False,
                               "messages": [{"role": "system", "content": system},
                                            {"role": "user", "content": user}]}).encode("utf-8")
            req = urllib.request.Request(self.ollama_url + "/api/chat", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["message"]["content"]
        return await asyncio.to_thread(call)
