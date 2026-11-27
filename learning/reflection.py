"""Nightly reflection: today's corrections become lessons; the lessons are written into the next answers.

Runs once a day between 02:30 and 03:30 while the PC is on (or when the owner says «проведи ночную рефлексию»).
The model call goes through cloud.ask (Groq, then Gemini). Without a key nothing is lost: the corrections stay
in the store and the next run uses them.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from pathlib import Path

from learning import store

BASE = Path(__file__).resolve().parent.parent
EVOLVED = BASE / "config" / "system_prompt_evolved.md"
STATE = BASE / "data" / "learning_state.json"
PROMPT = """Ты — внутренний голос ассистента Джарвис. Ниже его сегодняшние диалоги с владельцем и моменты,
где владелец его поправил. Найди ошибки Джарвиса и сформулируй уроки.

Диалоги (владелец / Джарвис):
{dialogues}

Поправки владельца:
{corrections}

Верни ТОЛЬКО JSON такого вида, без пояснений:
{{"lessons": [{{"trigger": "что сказал владелец", "wrong": "что сделал Джарвис", "right": "что нужно было сделать", "context": "тема одним словом"}}],
  "facts": ["новый факт о владельце, если он проявился"]}}
Если ошибок не было, верни {{"lessons": [], "facts": []}}."""


def _today_history(since: str | None = None) -> list[dict]:
    import core
    day = since or dt.date.today().isoformat()
    return [h for h in core.read_history(600) if str(h.get("time", ""))[:10] >= day]


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"lessons": [], "facts": []}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {"lessons": [], "facts": []}
    lessons = [x for x in data.get("lessons", []) if isinstance(x, dict) and x.get("trigger") and x.get("right")]
    return {"lessons": lessons[:20], "facts": [str(f)[:200] for f in data.get("facts", []) if f][:10]}


def reflect(ask=None, path: Path | None = None) -> dict:
    """Builds lessons from today's corrections. `ask(system, messages) -> str` is injectable for tests."""
    corrections = [f for f in store.recent_feedback(400, path) if f["rating"] == -1 or f["severity"] > 0]
    # everything since the last reflection (yesterday's mistakes too, if the laptop was off at night)
    since = (_state().get("day") or (dt.date.today() - dt.timedelta(days=1)).isoformat()) if path is None else dt.date.today().isoformat()
    corrections = [c for c in corrections if c["timestamp"][:10] >= since]
    if not corrections:
        return {"ok": True, "lessons": 0, "message": "Новых поправок и ошибок нет, учить нечему."}
    dialogues = "\n".join(f"В: {h.get('user', '')}\nО: {h.get('reply', '')}" for h in _today_history(since)[-40:]) or "(нет)"
    fixes = "\n".join(f"- {c['user_text']}  (после ответа: {c['assistant_reply'][:120]})" for c in corrections[-30:])
    prompt = PROMPT.format(dialogues=dialogues[-6000:], corrections=fixes)
    if ask is None:
        import cloud
        if not cloud.has("groq") and not cloud.has("gemini"):
            return {"ok": False, "lessons": 0, "message": "Нет ключа Groq или Gemini: рефлексия отложена, поправки сохранены."}
        ask = lambda system, msgs: cloud.ask(system, msgs, max_tokens=900)  # noqa: E731
    result = _parse(ask("Ты анализируешь ошибки ассистента. Отвечаешь строго JSON.", [{"role": "user", "content": prompt}]))
    for x in result["lessons"]:
        worst = max(float(c["severity"]) for c in corrections)
        store.add_lesson(x["trigger"], x.get("wrong", ""), x["right"], x.get("context", ""), severity=max(0.3, min(1.0, worst)), path=path)
    write_evolved_prompt(path)
    return {"ok": True, "lessons": len(result["lessons"]), "facts": result["facts"],
            "message": f"Уроков сегодня: {len(result['lessons'])}."}


def write_evolved_prompt(path: Path | None = None) -> str:
    """config/system_prompt_evolved.md: the twenty most important lessons, written as rules for the next day."""
    rows = store.lessons(20, path)
    lines = ["# Уроки Джарвиса (пишется автоматически ночной рефлексией)", ""]
    lines += [f"- КОГДА «{r['trigger_text']}», НЕ ДЕЛАЙ: {r['wrong_action'] or '—'}. А ДЕЛАЙ: {r['right_action']}." for r in rows]
    text = "\n".join(lines) + "\n"
    EVOLVED.parent.mkdir(parents=True, exist_ok=True)
    EVOLVED.write_text(text, encoding="utf-8")
    return text


def hints_for(text: str, limit: int = 3, path: Path | None = None) -> list[str]:
    """Lessons that look like the current request: they are shown to the brain before it answers."""
    out = []
    for r in store.lessons(60, path):
        if store.similarity(r["trigger_text"], text) > 0.2 or (store.words(r["trigger_text"]) & store.words(text)):
            out.append(f"Раньше: «{r['trigger_text']}» — надо: {r['right_action']}")
        if len(out) >= limit:
            break
    return out


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def due_now(now: dt.datetime | None = None) -> bool:
    """Once a day, from 02:30. A laptop that sleeps at night catches up the first time it is on after that."""
    now = now or dt.datetime.now()
    return (now.hour, now.minute) >= (2, 30) and _state().get("day") != now.date().isoformat()


def run_scheduled(now: dt.datetime | None = None) -> None:
    now = now or dt.datetime.now()
    if _state().get("day") == now.date().isoformat():
        return
    res = reflect()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"day": now.date().isoformat(), "result": res.get("message", "")}, ensure_ascii=False), encoding="utf-8")


def start_scheduler() -> None:
    """A background thread: looks every ten minutes, reflects once a night."""
    def loop():
        while True:
            try:
                if due_now():
                    run_scheduled()
            except Exception:  # noqa: BLE001 — learning must never crash the assistant
                pass
            time.sleep(600)
    threading.Thread(target=loop, daemon=True, name="learning-reflection").start()
