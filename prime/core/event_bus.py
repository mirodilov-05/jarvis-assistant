"""Async publish/subscribe bus: interfaces and domains never call each other directly."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

log = logging.getLogger("prime.bus")
Handler = Callable[["Event"], Awaitable[None]]


@dataclass(frozen=True)
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
        self._task: asyncio.Task | None = None

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    async def publish(self, topic: str, **payload: Any) -> None:
        """Queue an event. Drops the oldest event instead of blocking if the queue is full."""
        ev = Event(topic, payload)
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            log.warning("event queue full, dropped oldest event")
        await self._queue.put(ev)

    async def _dispatch(self, ev: Event) -> None:
        handlers = [h for pattern, hs in self._subs.items() if _match(pattern, ev.topic) for h in hs]
        for h in handlers:
            try:
                await asyncio.wait_for(h(ev), timeout=10)
            except asyncio.TimeoutError:
                log.error("handler %s timed out on %s", h.__name__, ev.topic)
            except Exception:  # noqa: BLE001 — one broken subscriber must not stop the others
                log.exception("handler %s failed on %s", h.__name__, ev.topic)

    async def _run(self) -> None:
        while True:
            ev = await self._queue.get()
            await self._dispatch(ev)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="event-bus")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


def _match(pattern: str, topic: str) -> bool:
    """'task.*' matches 'task.done'; '*' matches everything; otherwise exact match."""
    if pattern == "*" or pattern == topic:
        return True
    return pattern.endswith(".*") and topic.startswith(pattern[:-1])
