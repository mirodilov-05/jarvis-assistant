"""Voice briefing: everything important in one report, plus advice.

Spoken when the laptop starts (Windows logon) and on request:
"Джарвис, отчёт" / "сводка" / "что нового?" / "Jarvis, hisobot".
Sources (each only if connected): tasks, calendar, weather, email, Telegram,
WhatsApp, YouTube. Then: what to do first.
"""

import datetime as dt
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import core
from core import Ctx, skill


def _mod(name: str):
    return sys.modules.get(f"jarvis_plugin_{name}")


def _part_of_day(lang: str) -> str:
    h = core.now().hour
    if lang == "ru":
        return "Доброе утро" if 5 <= h < 12 else "Добрый день" if h < 17 else "Добрый вечер" if h < 23 else "Доброй ночи"
    return "Xayrli tong" if 5 <= h < 12 else "Xayrli kun" if h < 17 else "Xayrli kech" if h < 23 else "Xayrli tun"


def collect(lang: str) -> dict:
    city = core.CONFIG.get("weather", {}).get("city", "Tashkent")
    jobs = {
        "tasks": lambda: _mod("tasks").summary(lang),
        "calendar": lambda: _mod("calendar_ics").summary(lang),
        "weather": lambda: _mod("weather").short_weather(city, lang),
        "email": lambda: _mod("email_imap").summary(lang, detailed=True),
        "telegram": lambda: _mod("telegram").summary(lang, detailed=True),
        "whatsapp": lambda: _mod("whatsapp").summary(lang, detailed=True),
        "youtube": lambda: _mod("youtube").report(lang, detailed=True),
    }
    out = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futures = {k: ex.submit(fn) for k, fn in jobs.items() if _mod({"tasks": "tasks", "calendar": "calendar_ics",
                   "weather": "weather", "email": "email_imap", "telegram": "telegram", "whatsapp": "whatsapp",
                   "youtube": "youtube"}[k])}
        for k, f in futures.items():
            try:
                out[k] = f.result(timeout=25) or ""
            except Exception as e:  # noqa: BLE001
                core.log.warning("briefing source %s failed: %s", k, e)
                out[k] = ""
    return out


def rule_advice(lang: str) -> str:
    tasks = _mod("tasks").open_tasks() if _mod("tasks") else []
    now = core.now()
    overdue = [t for t in tasks if t.get("due") and dt.datetime.fromisoformat(t["due"]) < now]
    today = [t for t in tasks if t.get("due") and dt.datetime.fromisoformat(t["due"]).date() == now.date()
             and t not in overdue]
    steps = []
    if overdue:
        steps.append(("сначала закройте просроченное: " if lang == "ru" else "avval muddati o'tganlarni bajaring: ")
                     + overdue[0]["text"])
    if today:
        steps.append(("на сегодня главное: " if lang == "ru" else "bugungi asosiy ish: ") + today[0]["text"])
    elif tasks and not overdue:
        steps.append(("займитесь делом: " if lang == "ru" else "shu ishni qiling: ") + tasks[0]["text"])
    if not steps:
        return ""
    return ("Мой совет: " if lang == "ru" else "Maslahatim: ") + ", затем ".join(steps) + "."


def build(lang: str, greet: bool = True) -> str:
    a = core.CONFIG.get("assistant", {})
    honor = a.get("honorific_ru", "сэр") if lang == "ru" else a.get("honorific_uz", "janob")
    data = collect(lang)
    parts = []
    if greet:
        n = core.now()
        if lang == "ru":
            parts.append(f"{_part_of_day('ru')}, {honor}. Сейчас {n:%H:%M}. Вот ваша сводка.")
        else:
            parts.append(f"{_part_of_day('uz')}, {honor}. Hozir soat {n:%H:%M}. Mana sizning hisobotingiz.")
    for key in ("weather", "calendar", "tasks", "email", "telegram", "whatsapp", "youtube"):
        if data.get(key):
            parts.append(data[key])
    report = " ".join(parts)
    core.CONFIG["_last_brief"] = {"time": core.now().strftime("%H:%M"), "text": report}

    advice = ""
    llm = _mod("llm")
    if llm and llm.provider() == "claude":
        advice = llm.ask("Вот моя сводка: " + report + "\nДай 2–3 конкретных совета, что сделать в первую очередь, одним абзацем."
                         if lang == "ru" else
                         "Mana hisobotim: " + report + "\nAvval nima qilishim kerakligi haqida 2–3 aniq maslahat ber.",
                         lang, max_tokens=300, use_history=False)
    if not advice:
        advice = rule_advice(lang)
    if advice:
        report += " " + advice
    if greet:
        report += " " + (random.choice(["Чем займёмся?", "С чего начнём?", "Готов к работе."]) if lang == "ru"
                         else random.choice(["Nimadan boshlaymiz?", "Ishga tayyorman."]))
    return report


@skill(
    "briefing.report",
    title={"ru": "Голосовой отчёт: дела, почта, сообщения, YouTube, советы",
           "uz": "Ovozli hisobot: vazifalar, pochta, xabarlar, YouTube, maslahatlar"},
    patterns={"ru": [r"^(?:джарвис )?(?:дай |сделай |давай )?(отчет|сводк\w*|брифинг|доклад|доложи\w*|доложи обстановку)$",
                     r"^(?:джарвис )?(что нового|что я пропустил|какая обстановка|утренняя сводка)",
                     r"(какие|что) (у меня )?(планы|новости) на (сегодня|день)", r"(план на день|утренняя сводка)"],
              "uz": [r"^(?:jarvis )?(hisobot|xulosa|yangiliklar|nima yangilik\w*|bugungi reja|kun rejasi)\w*$"]},
    examples={"ru": ["Джарвис, отчёт", "Что нового?", "Какие планы на сегодня?"], "uz": ["Jarvis, hisobot", "Nima yangiliklar?"]},
    priority=2,
)
def report_skill(ctx: Ctx) -> str:
    return build(ctx.lang, greet=True)


@core.on_start
def brief_on_start() -> None:
    a = core.CONFIG.get("assistant", {})
    if not core.feature("greeting") or not a.get("greet_on_start", True):
        return
    time.sleep(6)
    if core.CONFIG.get("_game_mode"):
        return  # you're playing: don't talk over the game
    lang = a.get("greeting_lang", "ru")
    if core.feature("briefing") and a.get("briefing_on_start", True):
        core.speak(build(lang, greet=True), lang)
    else:
        core.speak(_mod("greeting").greeting(lang), lang)
