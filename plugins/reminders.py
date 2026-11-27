"""Reminders and timers that fire in the background and speak out loud.

"Напомни через 10 минут выпить воду", "Напомни в 18:30 позвонить маме",
"Поставь таймер на 5 минут", "10 daqiqadan keyin suv ichishni eslat".
"Напомни X" without a time adds X to the to-do list instead.
Stored in data/reminders.json, so they survive restarts.
"""

import datetime as dt
import time
import winsound

import core
from core import Ctx, skill

FILE = core.DATA / "reminders.json"

_UNITS = {
    "секунд": 1, "секунду": 1, "секунды": 1, "сек": 1,
    "минут": 60, "минуту": 60, "минуты": 60, "мин": 60,
    "час": 3600, "часа": 3600, "часов": 3600,
    "soniya": 1, "soniyadan": 1, "soniyaga": 1, "daqiqa": 60, "daqiqadan": 60, "daqiqaga": 60, "minut": 60,
    "minutdan": 60, "minutga": 60, "soat": 3600, "soatdan": 3600, "soatga": 3600,
}
_UNIT_RE = "|".join(sorted(_UNITS, key=len, reverse=True))


def _seconds(num_text: str, unit: str) -> int | None:
    if num_text.strip() in ("полчаса",):
        return 1800
    n = core.parse_number(num_text) if num_text.strip() else 1
    if n is None:
        return None
    return n * _UNITS[unit]


def _add(when: dt.datetime, text: str, lang: str, kind: str) -> None:
    with core.file_lock:
        items = core.load_json(FILE, [])
        items.append({"at": when.isoformat(timespec="seconds"), "text": text, "lang": lang, "kind": kind})
        core.save_json(FILE, items)


def _human(seconds: int, lang: str) -> str:
    if seconds % 3600 == 0:
        n = seconds // 3600
        return f"{n} " + (core.plural_ru(n, "час", "часа", "часов") if lang == "ru" else "soat")
    if seconds % 60 == 0:
        n = seconds // 60
        return f"{n} " + (core.plural_ru(n, "минуту", "минуты", "минут") if lang == "ru" else "daqiqa")
    return f"{seconds} " + ("сек." if lang == "ru" else "soniya")


@skill(
    "reminders.in",
    title={"ru": "Напомнить через время", "uz": "Ma'lum vaqtdan keyin eslatish"},
    patterns={
        "ru": [rf"напомни(?: мне)? через (\d+|[а-я]+(?: [а-я]+)?)? ?({_UNIT_RE})\w* (.+)$",
               rf"через (\d+|[а-я]+(?: [а-я]+)?)? ?({_UNIT_RE})\w* напомни(?: мне)? (.+)$"],
        "uz": [rf"(\d+|[a-z]+(?: [a-z]+)?) ({_UNIT_RE})\w* (?:keyin|song) (.+?)(?:ni|ni menga)? eslat\w*$"],
    },
    examples={"ru": ["Напомни через 10 минут выпить воду"], "uz": ["10 daqiqadan keyin suv ichishni eslat"]},
    priority=20,
)
def remind_in(ctx: Ctx):
    secs = _seconds(ctx.group(1), ctx.group(2))
    if not secs:
        return None
    text = ctx.group(3)
    _add(core.now() + dt.timedelta(seconds=secs), text, ctx.lang, "reminder")
    return ctx.t(f"Хорошо, напомню через {_human(secs, 'ru')}: {text}.",
                 f"Xo'p, {_human(secs, 'uz')}dan keyin eslataman: {text}.")


@skill(
    "reminders.at",
    title={"ru": "Напомнить в определённое время", "uz": "Belgilangan soatda eslatish"},
    patterns={
        "ru": [r"(?:разбуди меня|поставь будильник|заведи будильник)(?: завтра)? (?:в|на) (\d{1,2})(?::| )?(\d{2})? ?(?:часов|час|утра|вечера)?()$",
               r"напомни(?: мне)?(?: завтра)? в (\d{1,2})(?::| часов | час | )?(\d{2})? ?(?:часов|час|утра|вечера|дня)? (.+)$"],
        "uz": [r"(?:ertaga )?soat (\d{1,2})(?::| )?(\d{2})?(?: da|da)? (.+?)(?:ni|ni menga)? eslat\w*$"],
    },
    examples={"ru": ["Напомни в 18:30 позвонить маме"], "uz": ["Soat 18:30 da onamga qo'ng'iroq qilishni eslat"]},
    priority=21,
)
def remind_at(ctx: Ctx):
    hour = int(ctx.group(1))
    minute = int(ctx.group(2) or 0)
    text = ctx.group(3) or ctx.t("будильник, пора вставать", "turish vaqti")
    if "вечера" in ctx.norm and hour < 12:
        hour += 12
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    n = core.now()
    when = n.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when <= n or "завтра" in ctx.norm or "ertaga" in ctx.norm:
        when += dt.timedelta(days=1)
    _add(when, text, ctx.lang, "reminder")
    day = ctx.t("завтра " if when.date() > n.date() else "", "ertaga " if when.date() > n.date() else "")
    return ctx.t(f"Хорошо, напомню {day}в {when:%H:%M}: {text}.", f"Xo'p, {day}soat {when:%H:%M} da eslataman: {text}.")


@skill(
    "reminders.timer",
    title={"ru": "Поставить таймер", "uz": "Taymer qo'yish"},
    patterns={
        "ru": [rf"(?:поставь|заведи|включи|запусти) (?:таймер|будильник) на (\d+|[а-я]+(?: [а-я]+)?)? ?({_UNIT_RE})"],
        "uz": [rf"(\d+|[a-z]+(?: [a-z]+)?) ({_UNIT_RE})\w* taymer", rf"taymer\w* (\d+|[a-z]+(?: [a-z]+)?) ({_UNIT_RE})"],
    },
    examples={"ru": ["Поставь таймер на 5 минут"], "uz": ["5 daqiqaga taymer qo'y"]},
    priority=19,
)
def timer(ctx: Ctx):
    secs = _seconds(ctx.group(1), ctx.group(2))
    if not secs:
        return None
    _add(core.now() + dt.timedelta(seconds=secs), "", ctx.lang, "timer")
    return ctx.t(f"Таймер на {_human(secs, 'ru')} запущен.", f"{_human(secs, 'uz')}ga taymer qo'yildi.")


@skill(
    "reminders.list",
    title={"ru": "Список напоминаний", "uz": "Eslatmalar ro'yxati"},
    patterns={
        "ru": [r"(какие|покажи|мои|прочитай) (напоминания|таймеры)", r"что ты (мне )?напомнишь"],
        "uz": [r"(eslatmalarim|eslatishlar|taymerlar)(ni)? ?(korsat|oqi|ayt)?$"],
    },
    examples={"ru": ["Какие напоминания?"], "uz": ["Eslatishlarni ko'rsat"]},
    priority=22,
)
def list_reminders(ctx: Ctx) -> str:
    items = sorted(core.load_json(FILE, []), key=lambda r: r["at"])
    if not items:
        return ctx.t("Напоминаний нет.", "Eslatmalar yo'q.")
    parts = []
    for r in items[:8]:
        at = dt.datetime.fromisoformat(r["at"])
        label = r["text"] or ctx.t("таймер", "taymer")
        parts.append(f"{at:%d.%m %H:%M} — {label}")
    return ctx.t("Напоминания: ", "Eslatmalar: ") + "; ".join(parts) + "."


@skill(
    "reminders.cancel",
    title={"ru": "Отменить все напоминания и таймеры", "uz": "Barcha eslatma va taymerlarni bekor qilish"},
    patterns={
        "ru": [r"(отмени|удали|сбрось|выключи) (все )?(напоминания|таймеры|таймер|напоминание)"],
        "uz": [r"(eslatma|eslatish|taymer)\w* (bekor qil|ochir)"],
    },
    examples={"ru": ["Отмени таймер"], "uz": ["Taymerni bekor qil"]},
    priority=18,
)
def cancel(ctx: Ctx) -> str:
    """«отмени таймер» removes only timers, «отмени напоминание» only reminders, «отмени все» both."""
    words = ctx.norm
    if "все" in words:
        drop = lambda r: True                              # noqa: E731
        what = ("Все напоминания и таймеры отменены.", "Barcha eslatma va taymerlar bekor qilindi.")
    elif "таймер" in words:
        drop = lambda r: r.get("kind") == "timer"          # noqa: E731
        what = ("Таймеры отменены.", "Taymerlar bekor qilindi.")
    else:
        drop = lambda r: r.get("kind") != "timer"          # noqa: E731
        what = ("Напоминания отменены.", "Eslatmalar bekor qilindi.")
    with core.file_lock:
        items = core.load_json(FILE, [])
        keep = [r for r in items if not drop(r)]
        core.save_json(FILE, keep)
    return ctx.t(*what)


@core.on_start
def scheduler() -> None:
    """Every 5 s fire due reminders (also ones missed while the PC was off)."""
    while True:
        try:
            now = core.now()
            with core.file_lock:
                items = core.load_json(FILE, [])
                due = [r for r in items if dt.datetime.fromisoformat(r["at"]) <= now]
                if due:
                    core.save_json(FILE, [r for r in items if r not in due])
            for r in due:
                for _ in range(3):
                    winsound.Beep(988, 180)
                    time.sleep(0.08)
                late = (now - dt.datetime.fromisoformat(r["at"])).total_seconds() > 300
                if r["kind"] == "timer":
                    msg = "Таймер сработал!" if r["lang"] == "ru" else "Taymer vaqti tugadi!"
                else:
                    prefix = ("Напоминание" + (" (пропущенное)" if late else "")) if r["lang"] == "ru" \
                        else ("Eslatma" + (" (o'tkazib yuborilgan)" if late else ""))
                    msg = f"{prefix}: {r['text']}"
                core.speak(msg, r["lang"], urgent=True)
                core.log_exchange("напоминание", r["lang"], "-", msg)
                if core.setting("remote", "notify_reminders", True):
                    try:
                        import remote_bot
                        remote_bot.notify("⏰ " + msg)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            core.log.exception("Reminder scheduler error")
        time.sleep(5)
