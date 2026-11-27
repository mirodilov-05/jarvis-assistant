"""Agent loop: tools are checked by the guard, timed out, and counted.

Circuit breaker: at most MAX_STEPS tool calls per request. A tool that times out or fails is reported
back instead of crashing the loop.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.security_guard import Guard, Level, check

log = logging.getLogger("prime.orchestrator")
MAX_STEPS = 8


@dataclass
class Tool:
    name: str
    level: Level
    description: str
    run: Callable[..., Awaitable[str]]
    timeout_s: float = 20.0


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def add(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool {tool.name} already registered")
        self.tools[tool.name] = tool


@dataclass
class Step:
    tool: str
    status: str        # done | blocked | timeout | error | unknown | limit
    result: str = ""


class Orchestrator:
    def __init__(self, registry: Registry, guard: Guard, trust: Level = Level.SAFE_WRITE) -> None:
        self.registry = registry
        self.guard = guard
        self.trust = trust

    async def run_tool(self, name: str, /, **args: Any) -> Step:
        tool = self.registry.tools.get(name)
        if tool is None:
            return Step(name, "unknown", f"нет такого инструмента: {name}")
        if not check(self.trust, tool.level):
            code = self.guard.ask(name, args)
            return Step(name, "blocked", f"нужно подтверждение: отправьте код «{code}»")
        try:
            out = await asyncio.wait_for(tool.run(**args), timeout=tool.timeout_s)
            return Step(name, "done", str(out))
        except asyncio.TimeoutError:
            log.error("tool %s timed out after %.0f s", name, tool.timeout_s)
            return Step(name, "timeout", f"{name}: не ответил за {tool.timeout_s:.0f} с")
        except RuntimeError as e:          # a readable reason written for the owner (e.g. the TV is off)
            log.warning("tool %s refused: %s", name, e)
            return Step(name, "error", str(e))
        except Exception as e:  # noqa: BLE001 - the loop must survive a broken tool
            log.exception("tool %s failed", name)
            return Step(name, "error", f"{name}: ошибка {type(e).__name__}")

    async def execute_plan(self, plan: list[tuple[str, dict[str, Any]]]) -> list[Step]:
        """Run (tool, args) pairs in order. Stops at MAX_STEPS (circuit breaker)."""
        steps: list[Step] = []
        for i, (name, args) in enumerate(plan):
            if i >= MAX_STEPS:
                steps.append(Step(name, "limit", f"остановлено: больше {MAX_STEPS} шагов"))
                log.warning("circuit breaker: stopped at %d steps", MAX_STEPS)
                break
            steps.append(await self.run_tool(name, **args))
        return steps
