"""Basics: what can you do, time, date, calculator, reload skills."""

import re

import core
from core import Ctx, skill

_MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
_MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
              "sentabr", "oktabr", "noyabr", "dekabr"]
_WD_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_WD_UZ = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


@skill(
    "basics.help",
    title={"ru": "Рассказать, что я умею", "uz": "Nima qila olishimni aytish"},
    patterns={
        "ru": [r"(что|чего) (ты )?(умеешь|можешь)", r"твои (возможности|функции|команды)",
               r"(какие|какая) (у тебя )?(есть )?(функции|возможности|команды)", r"^(помощь|команды|справка)$"],
        "uz": [r"nima(lar)? qila olasan", r"nima qila olasiz", r"(qanday|qaysi) buyruqlar", r"imkoniyatlaring", r"^yordam$"],
    },
    examples={"ru": ["Что ты умеешь?"], "uz": ["Nima qila olasan?"]},
    priority=1,
)
def help_skill(ctx: Ctx) -> str:
    caps = core.capabilities(ctx.lang)
    if ctx.source in ("голос", "телеграм"):
        return ctx.t(
            "Я управляю компьютером голосом: открываю и закрываю программы, меняю громкость и яркость, ищу файлы. "
            "Веду дела, цели и напоминания. Управляю телевизором Samsung. Читаю и отправляю сообщения в Telegram "
            "и WhatsApp, читаю почту и календарь. Помню факты о вас, ищу в ваших документах и учусь на своих ошибках. "
            "Проверяю сеть и ускоряю ноутбук. Скажите «самопрезентация», и я подробно расскажу о себе на весь экран.",
            "Men kompyuterni ovoz bilan boshqaraman, vazifalar va eslatmalarni yuritaman, televizorni boshqaraman, "
            "Telegram va WhatsApp xabarlarini o'qiyman. To'liq ro'yxat CAPABILITIES.md faylida.")
    lines = [ctx.t("Я умею:", "Men qila olaman:")]
    for title, ex in caps:
        lines.append(f"• {title}" + (f" — «{ex[0]}»" if ex else ""))
    return "\n".join(lines)


@skill(
    "basics.time",
    title={"ru": "Сказать время", "uz": "Vaqtni aytish"},
    patterns={
        "ru": [r"(?!.*(?:компьютер|ноут|комп|пк))(который час|сколько (сейчас )?времени|какое (сейчас )?время)"],
        "uz": [r"soat (necha|nechchi|nechi)", r"hozir soat", r"vaqt (necha|qancha)"],
    },
    examples={"ru": ["Который час?"], "uz": ["Soat necha?"]},
    priority=5,
)
def time_skill(ctx: Ctx) -> str:
    n = core.now()
    return ctx.t(f"Сейчас {n:%H:%M}.", f"Hozir soat {n:%H:%M}.")


@skill(
    "basics.date",
    title={"ru": "Сказать дату и день недели", "uz": "Sana va hafta kunini aytish"},
    patterns={
        "ru": [r"(какое|какой) (сегодня )?(число|день|дата)", r"какая сегодня дата", r"какой сегодня день"],
        "uz": [r"bugun (nechanchi|necha|qaysi kun|qanaqa kun)", r"(bugungi )?sana(ni)? (ayt|qanday)", r"qaysi kun"],
    },
    examples={"ru": ["Какое сегодня число?"], "uz": ["Bugun nechanchi sana?"]},
    priority=5,
)
def date_skill(ctx: Ctx) -> str:
    n = core.now()
    return ctx.t(
        f"Сегодня {_WD_RU[n.weekday()]}, {n.day} {_MONTHS_RU[n.month - 1]} {n.year} года.",
        f"Bugun {_WD_UZ[n.weekday()]}, {n.year}-yil {n.day}-{_MONTHS_UZ[n.month - 1]}.",
    )


_OPS = {
    "плюс": "+", "минус": "-", "умножить на": "*", "умножить": "*", "разделить на": "/", "поделить на": "/",
    "разделить": "/", "в степени": "**", "qoshuv": "+", "plyus": "+", "ayiruv": "-", "minus": "-",
    "karra": "*", "kopaytir": "*", "kopaytirilgan": "*", "bolingan": "/", "bol": "/", "x": "*",
}


@skill(
    "basics.calc",
    title={"ru": "Посчитать пример", "uz": "Misolni hisoblash"},
    patterns={
        "ru": [r"^(сколько будет|посчитай|вычисли) (.+)$"],
        "uz": [r"^(.+?) (necha boladi|qancha boladi|nechchi boladi)$", r"^hisobla (.+)$"],
    },
    examples={"ru": ["Сколько будет 25 умножить на 4?"], "uz": ["25 karra 4 necha bo'ladi?"]},
    priority=20,
)
def calc_skill(ctx: Ctx):
    expr = ctx.group(2) if ctx.lang == "ru" and ctx.match.lastindex and ctx.match.lastindex >= 2 else ctx.group(1)
    raw = re.search(r"(?:будет|посчитай|вычисли)\s+(.+)$", ctx.text, re.I)   # normalised text has lost * / ( )
    if raw and re.search(r"[*/×÷()]", raw.group(1)):
        expr = raw.group(1).strip(" ?!.=").replace("×", "*").replace("÷", "/").lower()
    for word, op in sorted(_OPS.items(), key=lambda kv: -len(kv[0])):
        expr = re.sub(rf"\b{word}\b", f" {op} ", expr)
    expr = expr.replace(",", ".")
    if not re.fullmatch(r"[\d\s.+\-*/()]+", expr) or not re.search(r"\d", expr):
        return None  # not arithmetic -> let other skills / LLM answer
    try:
        value = eval(expr, {"__builtins__": {}}, {})  # only digits and operators reach here
    except Exception:  # noqa: BLE001
        return None
    if isinstance(value, float):
        value = round(value, 6)
        if value.is_integer():
            value = int(value)
    return ctx.t(f"Получается {value}.", f"Natija {value}.")


@skill(
    "basics.reload",
    title={"ru": "Перезагрузить навыки (после добавления плагина)", "uz": "Ko'nikmalarni qayta yuklash"},
    patterns={
        "ru": [r"перезагрузи (навыки|плагины|умения)", r"обнови (навыки|плагины)"],
        "uz": [r"konikmalarni (qayta yukla|yangila)", r"plaginlarni (qayta yukla|yangila)"],
    },
    examples={"ru": ["Перезагрузи навыки"], "uz": ["Ko'nikmalarni qayta yukla"]},
    priority=1,
)
def reload_skill(ctx: Ctx) -> str:
    errors = core.load_plugins()
    core.start_hooks()
    n = len(core.SKILLS)
    if errors:
        return ctx.t(f"Загружено навыков: {n}. Ошибки: ", f"{n} ta ko'nikma yuklandi. Xatolar: ") + "; ".join(errors)
    return ctx.t(f"Готово, загружено навыков: {n}.", f"Tayyor, {n} ta ko'nikma yuklandi.")
