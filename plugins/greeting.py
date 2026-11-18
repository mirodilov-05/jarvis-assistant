"""Greeting when Jarvis starts (Windows logon) and when you say hello.

"Добрый вечер, сэр. У вас 3 открытых дела... В Ташкенте 10 градусов. Чем займёмся?"
Settings: [assistant] greet_on_start, greeting_lang, honorific_ru, honorific_uz.
"""

import random
import time

import core
from core import Ctx, skill


def _part_of_day(lang: str) -> str:
    h = core.now().hour
    if lang == "ru":
        return "Доброе утро" if 5 <= h < 12 else "Добрый день" if h < 17 else "Добрый вечер" if h < 23 else "Доброй ночи"
    return "Xayrli tong" if 5 <= h < 12 else "Xayrli kun" if h < 17 else "Xayrli kech" if h < 23 else "Xayrli tun"


def _weather_line(lang: str) -> str:
    try:
        mod = __import__("jarvis_plugin_weather")
        city = core.CONFIG.get("weather", {}).get("city", "Tashkent")
        return " " + mod.short_weather(city, lang)
    except Exception:  # noqa: BLE001
        return ""


def greeting(lang: str, with_weather: bool = True) -> str:
    a = core.CONFIG.get("assistant", {})
    mode = core.mode()
    name = a.get("user_name", "")
    try:
        tasks = __import__("jarvis_plugin_tasks").summary(lang)
    except Exception:  # noqa: BLE001
        tasks = ""
    weather = _weather_line(lang) if with_weather and a.get("greeting_weather", True) else ""
    if mode == "work":   # just the facts
        return (f"На связи. {tasks}{weather}" if lang == "ru" else f"Aloqadaman. {tasks}{weather}").strip()
    if mode == "friend":
        if lang == "ru":
            hi = random.choice(["Привет", "Здорово", "Хей", "О, привет"]) + (f", {name}" if name else "")
            mood = random.choice(["У меня всё отлично, спасибо, что спросил.", "Всё супер, рад тебя слышать!",
                                  "Отлично! Как сам?", "Всё хорошо, на связи как всегда."])
            ask = random.choice(["Что делаем?", "Чем займёмся?", "Как твой день?", "Рассказывай, что нового?"])
            return f"{hi}! {mood} {tasks}{weather} {ask}"
        hi = "Salom" + (f", {name}" if name else "")
        return f"{hi}! Hammasi zo'r. {tasks}{weather} Nima qilamiz?"
    honor = a.get("honorific_ru", "сэр") if lang == "ru" else a.get("honorific_uz", "janob")
    if lang == "ru":
        ask = random.choice(["Чем займёмся сегодня?", "Что будем делать?", "Чем могу помочь?", "Готов к работе."])
        return f"{_part_of_day('ru')}, {honor}. Рад Вас видеть. {tasks}{weather} {ask}"
    ask = random.choice(["Bugun nima qilamiz?", "Qanday yordam bera olaman?", "Ishga tayyorman."])
    return f"{_part_of_day('uz')}, {honor}. Sizni ko'rganimdan xursandman. {tasks}{weather} {ask}"


@skill(
    "greeting.hello",
    title={"ru": "Поздороваться и рассказать план на день", "uz": "Salomlashish va kun rejasini aytish"},
    patterns={"ru": [r"^(привет|здравствуй\w*|доброе утро|добрый день|добрый вечер|хай)( джарвис)?$", r"^как дела"],
              "uz": [r"^(salom|assalomu alaykum|xayrli tong|xayrli kun|xayrli kech)( jarvis)?$", r"^qalaysan", r"^ishlar qalay"]},
    examples={"ru": ["Привет", "Как дела?"], "uz": ["Salom", "Qalaysan?"]},
    priority=3,
)
def hello(ctx: Ctx) -> str:
    return greeting(ctx.lang, with_weather=False)
