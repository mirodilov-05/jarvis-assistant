"""Tool registry for the agent brain (Jarvis V2).

A tool = a function the language model may call, with a JSON schema for its
arguments and a safety tier:
  "auto"    — runs right away (open, read, search, add a task…)
  "confirm" — Jarvis asks "Выполнить …? да/нет" first (delete, power off…)
  "self"    — the underlying skill asks for confirmation itself (sending messages)

Tools reuse the tested skill code: run_skill(name, phrase) feeds a canonical
phrase to one specific skill, so behaviour stays identical to V1.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable

import core


@dataclass
class Tool:
    name: str
    description: str
    params: dict
    required: list[str]
    fn: Callable[..., str]
    tier: str = "auto"
    confirm_text: Callable[..., str] | None = None
    tags: list[str] = field(default_factory=list)


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, params: dict | None = None, required: list[str] | None = None,
         tier: str = "auto", confirm_text: Callable[..., str] | None = None):
    def deco(fn):
        TOOLS[name] = Tool(name, description, params or {}, required or [], fn, tier, confirm_text)
        return fn
    return deco


def run_skill(skill_name: str, phrase: str, source: str = "агент") -> str:
    """Run one specific V1 skill with a canonical phrase."""
    for sk in core.SKILLS:
        if sk.name != skill_name:
            continue
        norm = core.normalize(phrase, "ru")
        for pat in sk.patterns.get("ru", []):
            m = pat.search(norm)
            if m:
                ctx = core.Ctx(text=phrase, lang="ru", source=source, config=core.CONFIG, match=m, norm=norm)
                reply = sk.handler(ctx)
                if reply is not None:
                    return reply
        core.log.warning("tool: skill %s did not accept %r", skill_name, phrase)
        return ""
    return ""


def ollama_schemas() -> list[dict]:
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description,
        "parameters": {"type": "object", "properties": t.params, "required": t.required}}}
        for t in TOOLS.values()]


def anthropic_schemas() -> list[dict]:
    return [{"name": t.name, "description": t.description,
             "input_schema": {"type": "object", "properties": t.params, "required": t.required}}
            for t in TOOLS.values()]


def execute(name: str, args: dict) -> str:
    t = TOOLS.get(name)
    if not t:
        return ""
    clean = {k: v for k, v in (args or {}).items() if k in t.params and v not in (None, "")}
    try:
        out = t.fn(**clean)
    except TypeError as e:   # model sent wrong/missing arguments
        core.log.warning("tool %s bad args %s: %s", name, clean, e)
        return ""
    except Exception:  # noqa: BLE001
        core.log.exception("tool %s failed", name)
        return f"Не получилось выполнить «{name}»."
    core.log.info("Tool %s(%s) -> %s", name, clean, (out or "")[:120])
    return out or ""


def load_all() -> int:
    TOOLS.clear()
    for mod in pkgutil.iter_modules(__path__):
        if not mod.name.startswith("_"):
            importlib.reload(importlib.import_module(f"{__name__}.{mod.name}"))
    return len(TOOLS)
