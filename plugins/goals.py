"""Goals, repeating reminders and app time limits — Jarvis helps you reach goals step by step.

  Goals:       «цель: выучить 50 слов японского», «цель: 3 ролика в неделю», «цель: 1 час кодинга в день»
               «сделал шаг по цели японский» / «+5 к цели японский», «мои цели», «план на сегодня», «удали цель …»
               Every morning (09:00) and every evening (20:00, if the daily step is not done) Jarvis says it out loud.
  Reminders:   «напоминай каждые 60 минут пить воду», «напоминай каждый день в 22:30 ложиться спать», «мои напоминания»,
               «убери напоминание …». Each one sounds (three beeps) and speaks.
  App limits:  «ограничь YouTube 1 час в день», «ограничь steam 90 минут», «какие ограничения», «сними ограничение …»
               Jarvis counts the time the app is in front. At 5 minutes left he warns; at the limit he asks it to close
               (WM_CLOSE — an app that has unsaved work will still ask you). Only programs you limited are touched.

Stored in data/goals.json, data/repeats.json, data/limits.json (+ data/limits_usage.json). Survive restarts.
"""

from __future__ import annotations

import datetime as dt
import random
import re
import threading
import time
import uuid
import winsound

import core
from core import Ctx, skill

GOALS = core.DATA / "goals.json"
REPEATS = core.DATA / "repeats.json"
LIMITS = core.DATA / "limits.json"
USAGE = core.DATA / "limits_usage.json"
DAILY_AT = (9, 0)
EVENING_AT = (20, 0)
_lock = threading.Lock()


# ---------------------------------------------------------------- helpers

def _today() -> str:
    return core.now().strftime("%Y-%m-%d")


def _beeps(n: int = 3) -> None:
    for _ in range(n):
        winsound.Beep(988, 180)
        time.sleep(0.08)


def _say(text: str, lang: str = "ru") -> None:
    _beeps()
    core.speak(text, lang, urgent=True)
    core.log_exchange("цели", lang, "-", text)


def _num_or_none(s: str | None) -> int | None:
    if not s:
        return None
    if s.isdigit():
        return int(s)
    return core.parse_number(s)


def _same_words(q: str, t: str) -> bool:
    """«роликов» finds «ролика»: words match by their first four letters (Russian endings change)."""
    if not q or not t:
        return False
    if q == t or q in t or t in q:
        return True
    tw = t.split()
    qw = [w for w in q.split() if len(w) >= 3]
    return bool(qw) and all(any(w[:4] == x[:4] for x in tw) for w in qw)


def _find_goal(goals: list[dict], text: str) -> dict | None:
    q = core.normalize(text, "ru")
    for g in goals:
        if _same_words(q, core.normalize(g["title"], "ru")):
            return g
    return None


# ---------------------------------------------------------------- goals

@skill("goals.add", title={"ru": "Новая цель (с шагами в день или неделю)"},
       patterns={"ru": [r"^(?:джарвис )?(?:добавь |поставь |создай |новая )?цел[ьи][:,]? (?P<t>.+?)(?: по (?P<n>\d+|[а-я]+) (?:в день|в неделю|раз в день|раз в неделю))?$",
                        r"^(?:джарвис )?(?:моя )?цель (?P<t>.+)$"]},
       examples={"ru": ["Цель: выучить 50 слов японского", "Цель 3 ролика в неделю"]}, priority=6)
def add_goal(ctx: Ctx) -> str:
    g = ctx.match.groupdict()
    title = (g.get("t") or "").strip(" .,!?")
    if not title:
        return "Какая цель, сэр?"
    per = _num_or_none(g.get("n"))
    weekly = bool(re.search(r"в неделю|раз в неделю", ctx.norm))
    goal = {"id": uuid.uuid4().hex[:8], "title": title[:120], "per_day": None if weekly else per,
            "per_week": per if weekly else None, "created": _today(), "log": {}}
    with _lock:
        goals = core.load_json(GOALS, [])
        goals.append(goal)
        core.save_json(GOALS, goals)
    step = (f" Шаг: {per} в неделю." if weekly and per else f" Шаг: {per} в день." if per else "")
    return f"Записал цель: {title}.{step} Отмечайте шаги голосом, я буду напоминать."


def _done_today(g: dict) -> int:
    return int(g.get("log", {}).get(_today(), 0))


def _done_week(g: dict) -> int:
    start = core.now().date() - dt.timedelta(days=core.now().weekday())
    return sum(v for d, v in g.get("log", {}).items() if dt.date.fromisoformat(d) >= start)


@skill("goals.tick", title={"ru": "Отметить шаг по цели"},
       patterns={"ru": [r"^(?:джарвис )?(?:сделал|сделала|выполнил|выполнила|прошёл|прошла|отметь) (?:шаг (?:по )?|по )?(?:цели )?(?P<t>.+?)(?: (?P<n>\d+|[а-я]+))?$",
                        r"^(?:джарвис )?(?P<n>\d+) к цели (?P<t>.+)$"]},
       examples={"ru": ["Сделал шаг по цели японский", "+5 к цели японский"]}, priority=45)
def tick(ctx: Ctx) -> str:
    g = ctx.match.groupdict()
    with _lock:
        goals = core.load_json(GOALS, [])
        goal = _find_goal(goals, g.get("t") or "")
        if not goal:
            return None          # «сделал скриншот» is not about a goal: let the other skills have it
        n = _num_or_none(g.get("n")) or 1
        goal["log"][_today()] = _done_today(goal) + n
        core.save_json(GOALS, goals)
    per = goal.get("per_day")
    if per:
        left = max(0, per - _done_today(goal))
        tail = "Дневной шаг выполнен, отлично!" if left == 0 else f"До дневного шага осталось {left}."
    elif goal.get("per_week"):
        left = max(0, goal["per_week"] - _done_week(goal))
        tail = "Недельный шаг выполнен!" if left == 0 else f"До недельного шага осталось {left}."
    else:
        tail = f"Всего сегодня: {_done_today(goal)}."
    return f"Записал. {tail}"


def _status_line(g: dict) -> str:
    if g.get("per_day"):
        return f"сегодня {_done_today(g)} из {g['per_day']}"
    if g.get("per_week"):
        return f"за неделю {_done_week(g)} из {g['per_week']}"
    return f"сегодня {_done_today(g)}"


@skill("goals.list", title={"ru": "Мои цели и прогресс"},
       patterns={"ru": [r"^(?:джарвис )?(?:мои |покажи |какие )?цели(?: и прогресс| прогресс)?$",
                        r"^(?:джарвис )?прогресс(?: по целям)?$",
                        r"^(?:джарвис )?(?:план|мой план) на (?:сегодня|день)$"]},
       examples={"ru": ["Мои цели", "План на сегодня"]}, priority=5)
def list_goals(ctx: Ctx) -> str:
    goals = core.load_json(GOALS, [])
    if not goals:
        return "Целей пока нет, сэр. Скажите: цель и название."
    lines = [f"{g['title']}: {_status_line(g)}" for g in goals]
    return "Ваши цели. " + ". ".join(lines) + "."


@skill("goals.delete", title={"ru": "Удалить цель"},
       patterns={"ru": [r"^(?:джарвис )?(?:удали|убери|забудь) цель (?P<t>.+)$"]},
       examples={"ru": ["Удали цель японский"]}, priority=5)
def delete_goal(ctx: Ctx) -> str:
    with _lock:
        goals = core.load_json(GOALS, [])
        goal = _find_goal(goals, ctx.match.group("t"))
        if not goal:
            return "Не нашёл такую цель, сэр."
        core.save_json(GOALS, [g for g in goals if g["id"] != goal["id"]])
    return f"Удалил цель: {goal['title']}."


def _goal_nudge(evening: bool) -> None:
    goals = core.load_json(GOALS, [])
    if not goals:
        return
    if evening:
        lazy = [g for g in goals if g.get("per_day") and _done_today(g) < g["per_day"]]
        if not lazy:
            return
        names = ", ".join(g["title"] for g in lazy[:3])
        _say(f"Сэр, сегодня ещё не выполнено: {names}. Есть время сделать шаг?")
    else:
        parts = [f"{g['title']}: сегодня нужно {g['per_day']}" for g in goals if g.get("per_day")]
        if parts:
            _say("Доброе утро, сэр. План на сегодня. " + ". ".join(parts) + ".")


# ---------------------------------------------------------------- repeating reminders

@skill("goals.repeat", title={"ru": "Повторяющееся напоминание: каждые N минут или каждый день в время"},
       patterns={"ru": [r"^(?:джарвис )?напоминай (?:мне )?(?:каждые|каждый) (?P<n>\d+|[а-я]+ ?[а-я]*) (?P<u>минут\w*|час\w*) (?P<t>.+)$",
                        r"^(?:джарвис )?напоминай (?:мне )?каждый день в (?P<h>\d{1,2})(?:[:.](?P<m>\d{2})| (?:часов )?(?P<m2>\d{2})?)? ?(?P<t>.+)$"]},
       examples={"ru": ["Напоминай каждые 60 минут пить воду", "Напоминай каждый день в 22:30 ложиться спать"]}, priority=6)
def repeat(ctx: Ctx) -> str:
    g = ctx.match.groupdict()
    text = (g.get("t") or "").strip(" .!?")
    if "u" in g and g.get("u") is not None:
        n = _num_or_none(g["n"]) or 60
        minutes = n * (60 if g["u"].startswith("час") else 1)
        if minutes < 5:
            return "Чаще пяти минут не напоминаю, сэр."
        rule = {"every_min": minutes}
        when = f"каждые {minutes} минут"
    else:
        h = int(g["h"]); m = int(g.get("m") or g.get("m2") or 0)
        if not (0 <= h < 24 and 0 <= m < 60):
            return "Не понял время, сэр."
        rule = {"daily": f"{h:02d}:{m:02d}"}
        when = f"каждый день в {h:02d}:{m:02d}"
    item = {"id": uuid.uuid4().hex[:8], "text": text, "rule": rule, "last": 0}
    with _lock:
        items = core.load_json(REPEATS, [])
        items.append(item)
        core.save_json(REPEATS, items)
    return f"Буду напоминать {when}: {text}."


def _due_repeat(item: dict, now: dt.datetime) -> bool:
    if "every_min" in item["rule"]:
        return time.time() - item.get("last", 0) >= item["rule"]["every_min"] * 60 - 5
    hhmm = item["rule"]["daily"]
    return now.strftime("%H:%M") == hhmm and item.get("last_day") != now.strftime("%Y-%m-%d")


@skill("goals.repeat_list", title={"ru": "Мои повторяющиеся напоминания"},
       patterns={"ru": [r"^(?:джарвис )?мои (?:повторяющиеся )?напоминания$", r"^(?:джарвис )?какие напоминания$"]},
       examples={"ru": ["Мои напоминания"]}, priority=5)
def repeat_list(ctx: Ctx) -> str:
    items = core.load_json(REPEATS, [])
    if not items:
        return "Повторяющихся напоминаний нет, сэр."
    out = []
    for it in items:
        r = it["rule"]
        when = f"каждые {r['every_min']} минут" if "every_min" in r else f"каждый день в {r['daily']}"
        out.append(f"{it['text']} — {when}")
    return "; ".join(out) + "."


@skill("goals.repeat_cancel", title={"ru": "Убрать повторяющееся напоминание"},
       patterns={"ru": [r"^(?:джарвис )?(?:убери|отмени|выключи|удали) напоминание (?P<t>.+)$"]},
       examples={"ru": ["Убери напоминание про воду"]}, priority=5)
def repeat_cancel(ctx: Ctx) -> str:
    q = re.sub(r"^(?:про|о|об) ", "", core.normalize(ctx.match.group("t"), "ru"))
    with _lock:
        items = core.load_json(REPEATS, [])
        keep = [i for i in items if not _same_words(q, core.normalize(i["text"], "ru"))]
        if len(keep) == len(items):
            return "Не нашёл такое напоминание, сэр."
        core.save_json(REPEATS, keep)
    return "Убрал напоминание."


# ---------------------------------------------------------------- app time limits

@skill("goals.limit", title={"ru": "Ограничить время в программе (в день)"},
       patterns={"ru": [r"^(?:джарвис )?ограничь (?P<a>.+?) (?P<n>\d+|[а-я]+(?: [а-я]+)?) (?P<u>минут\w*|час\w*)(?: в день)?$"]},
       examples={"ru": ["Ограничь YouTube 1 час в день", "Ограничь steam 90 минут"]}, priority=6)
def limit(ctx: Ctx) -> str:
    g = ctx.match.groupdict()
    app = g["a"].strip()
    n = _num_or_none(g["n"]) or 60
    minutes = n * (60 if g["u"].startswith("час") else 1)
    if minutes < 5:
        return "Меньше пяти минут не ставлю, сэр."
    import pcx
    exes = sorted(pcx.match_exes(app))
    if not exes:
        return f"Не понял, какая программа «{app}»."
    with _lock:
        items = core.load_json(LIMITS, [])
        items = [i for i in items if i["app"] != app]
        items.append({"app": app, "exes": exes, "minutes": minutes})
        core.save_json(LIMITS, items)
    return f"Ограничил «{app}»: {minutes} минут в день. За пять минут до конца предупрежу."


@skill("goals.limit_list", title={"ru": "Какие ограничения стоят и сколько осталось"},
       patterns={"ru": [r"^(?:джарвис )?(?:какие|мои|покажи) ограничени\w*$", r"^(?:джарвис )?сколько (?:времени )?осталось(?: в программах)?$"]},
       examples={"ru": ["Какие ограничения"]}, priority=5)
def limit_list(ctx: Ctx) -> str:
    items = core.load_json(LIMITS, [])
    if not items:
        return "Ограничений нет, сэр."
    usage = core.load_json(USAGE, {}).get(_today(), {})
    parts = []
    for i in items:
        used = usage.get(i["app"], 0) / 60
        parts.append(f"{i['app']}: осталось {max(0, round(i['minutes'] - used))} из {i['minutes']} минут")
    return "; ".join(parts) + "."


@skill("goals.limit_cancel", title={"ru": "Снять ограничение с программы"},
       patterns={"ru": [r"^(?:джарвис )?(?:сними|убери|отмени) ограничени[ея] (?:с |на )?(?P<a>.+)$"]},
       examples={"ru": ["Сними ограничение с YouTube"]}, priority=5)
def limit_cancel(ctx: Ctx) -> str:
    app = ctx.match.group("a").strip()
    with _lock:
        items = core.load_json(LIMITS, [])
        keep = [i for i in items if core.normalize(i["app"], "ru") != core.normalize(app, "ru")]
        if len(keep) == len(items):
            return "Такого ограничения нет, сэр."
        core.save_json(LIMITS, keep)
    return f"Снял ограничение с «{app}»."


def _close_later(hwnd: int, exes: set) -> None:
    import pcx
    time.sleep(60)
    if pcx.foreground()[2] in exes:          # still in front: ask it to close (it may ask you to save first)
        pcx.close_window(hwnd)


def _limit_check() -> None:
    """Called every 20 seconds: count time in front, warn at 5 minutes left, close at the limit."""
    import pcx
    items = core.load_json(LIMITS, [])
    if not items:
        return
    try:
        hwnd, title, exe = pcx.foreground()
    except Exception:  # noqa: BLE001
        return
    day = _today()
    usage = core.load_json(USAGE, {})
    usage = {d: v for d, v in usage.items() if d == day}          # keep only today
    today = usage.setdefault(day, {})
    for i in items:
        if exe not in set(i["exes"]):
            continue
        today[i["app"]] = today.get(i["app"], 0) + 20
        used_min, limit_min = today[i["app"]] / 60, i["minutes"]
        warned = today.setdefault("_warned", {})
        if limit_min - used_min <= 5 and not warned.get(i["app"]) and used_min < limit_min:
            warned[i["app"]] = True
            _say(f"Сэр, «{i['app']}» осталось пять минут из {limit_min}. Заканчивайте.")
        if used_min >= limit_min and not today.get(i["app"] + "_closed"):
            today[i["app"] + "_closed"] = True
            _say(f"Лимит на «{i['app']}» исчерпан. Закрою через минуту, сохраните работу.")
            threading.Thread(target=_close_later, args=(hwnd, set(i["exes"])), daemon=True).start()
    core.save_json(USAGE, usage)


# ---------------------------------------------------------------- the background scheduler

@core.on_start
def scheduler() -> None:
    """Every 20 s: limits, repeating reminders; morning and evening goal talk once a day."""
    last_daily = last_evening = ""
    while True:
        time.sleep(20)
        try:
            now = core.now()
            _limit_check()
            with _lock:
                items = core.load_json(REPEATS, [])
                changed = False
                for it in items:
                    if _due_repeat(it, now):
                        it["last"] = time.time()
                        it["last_day"] = now.strftime("%Y-%m-%d")
                        changed = True
                        _say(f"Напоминание: {it['text']}")
                if changed:
                    core.save_json(REPEATS, items)
            day = now.strftime("%Y-%m-%d")
            if now.strftime("%H:%M") >= "%02d:%02d" % DAILY_AT and last_daily != day:
                last_daily = day
                _goal_nudge(evening=False)
            if now.strftime("%H:%M") >= "%02d:%02d" % EVENING_AT and last_evening != day:
                last_evening = day
                _goal_nudge(evening=True)
        except Exception:  # noqa: BLE001
            core.log.exception("goals scheduler")


core._LONG_OK.update({"goals.add", "goals.tick", "goals.delete", "goals.repeat", "goals.repeat_cancel", "goals.limit",
                       "goals.limit_cancel", "goals.list", "goals.repeat_list", "goals.limit_list"})
