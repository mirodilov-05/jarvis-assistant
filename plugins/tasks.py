"""To-do list with due times. Jarvis watches your tasks and reminds you:
- 10 minutes before and at the due time,
- again every few hours while a task is overdue,
- and periodically tells you how many tasks are still open.

Stored in data/tasks.json. Settings: [tasks] in config.toml / app Settings.
"""

import datetime as dt
import re
import time
import uuid

import core
from core import Ctx, plural_ru, skill

FILE = core.DATA / "tasks.json"


def _all() -> list[dict]:
    tasks = core.load_json(FILE, [])
    for t in tasks:
        t.setdefault("id", uuid.uuid4().hex[:8])
    return tasks


def open_tasks() -> list[dict]:
    items = [t for t in _all() if not t.get("done")]
    return sorted(items, key=lambda t: (t.get("due") or "9999", t.get("created", "")))


def add_task(text: str, due: dt.datetime | None = None, lang: str = "ru") -> dict:
    task = {"id": uuid.uuid4().hex[:8], "text": text, "done": False, "lang": lang,
            "created": core.now().isoformat(timespec="minutes"),
            "due": due.isoformat(timespec="minutes") if due else None}
    with core.file_lock:
        tasks = _all()
        tasks.append(task)
        core.save_json(FILE, tasks)
    return task


def update_task(task_id: str, **changes) -> dict | None:
    with core.file_lock:
        tasks = _all()
        for t in tasks:
            if t["id"] == task_id:
                t.update(changes)
                if changes.get("done"):
                    t["done_at"] = core.now().isoformat(timespec="minutes")
                core.save_json(FILE, tasks)
                return t
    return None


def delete_task(task_id: str) -> None:
    with core.file_lock:
        core.save_json(FILE, [t for t in _all() if t["id"] != task_id])


def _describe(t: dict, lang: str) -> str:
    if t.get("due"):
        return f"{t['text']} ({core.human_when(dt.datetime.fromisoformat(t['due']), lang)})"
    return t["text"]


def _restore_case(ctx: Ctx, item: str) -> str:
    words = item.split()
    if ctx.lang != "ru" or not words:
        return item
    pos = ctx.text.lower().find(words[0])
    if pos >= 0:
        tail = ctx.text[pos:].strip(" .!?")
        if len(tail) <= len(item) + 5 and tail.lower().replace("ё", "е").startswith(item[:10]):
            return tail
    return item


@skill(
    "tasks.add",
    title={"ru": "Записать дело (можно со сроком)", "uz": "Vazifa qo'shish (muddat bilan ham)"},
    patterns={
        "ru": [
            r"^(?:джарвис )?(?:добавь|запиши|создай|поставь|внеси)(?: мне| в список)?(?: новое| новую)? (?:дело|задачу|задание|в дела|в задачи)\s*(.+)$",
            r"^(?:джарвис )?напомни(?: мне)?(?: что| про| о| об)? (.+)$",
            r"^(?:джарвис )?(?:закинь|кинь|занеси|впиши|добавь|запиши)(?: мне)? в (?:список|дела|задачи|туду|список дел)(?: дел)? (.+)$",
            r"^(?:джарвис )?(?:мне )?(?:бы )?(?:надо|нужно|не забудь|не дай мне забыть|не забыть бы|не забыть) (?:бы )?(?:не забыть )?(.+)$",
        ],
        "uz": [
            r"^(?:jarvis )?(?:yangi )?(?:vazifa|ish)(?:ga)? (?:qosh|yoz|qoy|kirit)\w*\s+(.+)$",
            r"^(?:jarvis )?(.+?) (?:ni |ham )?(?:vazifa|ishlar|vazifalar)(?:ga|imga|larga|larimga) (?:qosh|yoz|qoy|kirit)\w*$",
        ],
    },
    examples={"ru": ["Добавь дело купить хлеб завтра в 10", "Напомни позвонить маме в 18:00"],
              "uz": ["Vazifa qo'sh ertaga soat 9 da non olish"]},
    priority=30,
)
def add(ctx: Ctx):
    item = ctx.group(1)
    if not item:
        return None
    due, item = core.parse_when(item)
    item = re.sub(r"^(что|про|о|об|то что)\s+", "", item).strip()
    if ctx.lang == "uz":
        item = re.sub(r"\s*(ni|ni ham)$", "", item).strip()
    item = _restore_case(ctx, item)
    if not item:
        return None
    add_task(item, due, ctx.lang)
    n = len(open_tasks())
    when = (" — " + core.human_when(due, ctx.lang)) if due else ""
    return ctx.t(f"Записал дело: {item}{when}. Открытых дел: {n}.",
                 f"Vazifa yozildi: {item}{when}. Ochiq vazifalar: {n} ta.")


@skill(
    "tasks.list",
    title={"ru": "Прочитать список дел", "uz": "Vazifalar ro'yxatini o'qish"},
    patterns={
        "ru": [r"(сколько|какие|покажи|прочитай|список|мои|что у меня)\b.*\b(дел|дела|задач|задачи|планы)\b",
               r"^(дела|задачи|мои дела)$", r"что (у меня )?(на сегодня|сегодня по плану|запланировано)"],
        "uz": [r"(nechta|qanday|qaysi|qancha) (vazifa|ish)", r"vazifalarim", r"vazifalar(ni|im)? (oqi|ayt|korsat|royxat)",
               r"^vazifalar$", r"bugun nima (qilishim|ishlarim|rejalarim)", r"bugungi (rejalar|vazifalar)"],
    },
    examples={"ru": ["Сколько у меня дел?", "Что у меня на сегодня?"], "uz": ["Nechta vazifam bor?"]},
    priority=31,
)
def list_tasks(ctx: Ctx) -> str:
    if "сегодня" in ctx.norm or "bugun" in ctx.norm:
        return day_listing(ctx, core.now().date())
    items = open_tasks()
    if not items:
        return ctx.t("Открытых дел нет. Свободный день, сэр.", "Ochiq vazifalar yo'q.")
    n = len(items)
    head = ctx.t(f"У вас {n} {plural_ru(n, 'дело', 'дела', 'дел')}.", f"Sizda {n} ta vazifa bor.")
    return f"{head} {by_days(items, ctx.lang, limit=12)}"


_WD_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_WD_UZ = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


def day_name(d: dt.date, lang: str) -> str:
    today = core.now().date()
    if d < today:
        return "Просрочено" if lang == "ru" else "Muddati o'tgan"
    if d == today:
        return "Сегодня" if lang == "ru" else "Bugun"
    if d == today + dt.timedelta(days=1):
        return "Завтра" if lang == "ru" else "Ertaga"
    wd = (_WD_RU if lang == "ru" else _WD_UZ)[d.weekday()]
    return f"{wd.capitalize()} {d:%d.%m}"


def by_days(items: list[dict], lang: str, limit: int = 12) -> str:
    """'Сегодня: 1. … в 10:00. Завтра: 2. …. Без срока: 3. …' — numbers match "выполнил дело N"."""
    all_open = open_tasks()
    number = {t["id"]: i for i, t in enumerate(all_open, 1)}
    groups: dict[str, list[str]] = {}
    for t in items[:limit]:
        if t.get("due"):
            due = dt.datetime.fromisoformat(t["due"])
            key = day_name(due.date(), lang)
            line = f"{number.get(t['id'], '?')}. {t['text']}" + (f" в {due:%H:%M}" if lang == "ru" else f" soat {due:%H:%M}")
        else:
            key = "Без срока" if lang == "ru" else "Muddatsiz"
            line = f"{number.get(t['id'], '?')}. {t['text']}"
        groups.setdefault(key, []).append(line)
    out = " ".join(f"{k}: " + "; ".join(v) + "." for k, v in groups.items())
    if len(items) > limit:
        out += (f" И ещё {len(items) - limit}." if lang == "ru" else f" Yana {len(items) - limit} ta.")
    return out


def day_listing(ctx: Ctx, day: dt.date) -> str:
    items = [t for t in open_tasks() if t.get("due") and dt.datetime.fromisoformat(t["due"]).date() == day]
    if day == core.now().date():   # today also shows overdue and undated tasks
        items = [t for t in open_tasks() if not t.get("due") or dt.datetime.fromisoformat(t["due"]).date() <= day]
    name = day_name(day, ctx.lang).lower()
    if not items:
        return ctx.t(f"На {name} дел нет.", f"{name.capitalize()} uchun vazifa yo'q.")
    return by_days(items, ctx.lang)


@skill(
    "tasks.day",
    title={"ru": "Дела на день (завтра, пятницу…)", "uz": "Kunlik vazifalar (ertaga, juma…)"},
    patterns={"ru": [r"(?:что|какие дела|какие планы|дела|планы|задачи)(?: у меня)? на (завтра|послезавтра|понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)"],
              "uz": [r"(ertaga|indinga|dushanba|seshanba|chorshanba|payshanba|juma|shanba|yakshanba)(?: kuni)?(?:gi)? (?:nima|qanday)? ?(?:ishlar|vazifa|reja)\w*"]},
    examples={"ru": ["Что у меня на завтра?", "Дела на пятницу"], "uz": ["Ertangi vazifalar"]},
    priority=28,
)
def tasks_day(ctx: Ctx) -> str:
    when, _ = core.parse_when(ctx.group(1))
    return day_listing(ctx, when.date() if when else core.now().date())


@skill(
    "tasks.week",
    title={"ru": "План на неделю по дням", "uz": "Haftalik reja kunlar bo'yicha"},
    patterns={"ru": [r"(дела|план\w*|задачи|расписание)(?: у меня)? на (неделю|эту неделю)", r"(недельный|недельные) (план|дела)"],
              "uz": [r"(haftalik|bu hafta\w*) (reja|vazifa|ishlar)\w*"]},
    examples={"ru": ["Дела на неделю"], "uz": ["Haftalik reja"]},
    priority=28,
)
def tasks_week(ctx: Ctx) -> str:
    end = core.now().date() + dt.timedelta(days=7)
    items = [t for t in open_tasks() if not t.get("due") or dt.datetime.fromisoformat(t["due"]).date() <= end]
    if not items:
        return ctx.t("На неделю дел нет.", "Bu haftaga vazifa yo'q.")
    return by_days(items, ctx.lang, limit=20)


@skill(
    "tasks.overdue",
    title={"ru": "Просроченные дела", "uz": "Muddati o'tgan vazifalar"},
    patterns={"ru": [r"просроч\w*"], "uz": [r"muddati otgan"]},
    examples={"ru": ["Какие дела просрочены?"], "uz": ["Muddati o'tgan vazifalar"]},
    priority=28,
)
def tasks_overdue(ctx: Ctx) -> str:
    now = core.now()
    items = [t for t in open_tasks() if t.get("due") and dt.datetime.fromisoformat(t["due"]) < now]
    if not items:
        return ctx.t("Просроченных дел нет, молодец!", "Muddati o'tgan vazifalar yo'q!")
    return by_days(items, ctx.lang)


@skill(
    "tasks.move",
    title={"ru": "Перенести дело на другое время", "uz": "Vazifani boshqa vaqtga ko'chirish"},
    patterns={"ru": [r"(?:перенеси|передвинь|отложи|сдвинь)(?: дело| задачу)?(?: номер)? " + core.NUM_RE + r" на (.+)$"],
              "uz": [core.NUM_RE + r"(?: chi| nchi| inchi)? vazifa\w* (.+?) (?:ga )?kochir\w*$"]},
    examples={"ru": ["Перенеси дело 2 на завтра в 10"], "uz": ["2-vazifani ertaga soat 10 ga ko'chir"]},
    priority=27,
)
def tasks_move(ctx: Ctx):
    num = core.parse_number(ctx.group(1))
    items = open_tasks()
    if num is None or not 1 <= num <= len(items):
        return ctx.t(f"Не нашёл дело с таким номером. Открытых дел: {len(items)}.", "Bunday raqamli vazifa yo'q.")
    when, _ = core.parse_when(" " + ctx.group(2) + " ")
    if not when:
        return ctx.t("Не понял, на когда перенести. Скажите, например: на завтра в 10.", "Qachonga ko'chirishni tushunmadim.")
    t = update_task(items[num - 1]["id"], due=when.isoformat(timespec="minutes"), notified=False, pre_notified=False, last_nag=None)
    return ctx.t(f"Перенёс «{t['text']}» на {core.human_when(when, 'ru')}.", f"«{t['text']}» {core.human_when(when, 'uz')}ga ko'chirildi.")


@skill(
    "tasks.delete",
    title={"ru": "Удалить дело", "uz": "Vazifani o'chirish"},
    patterns={"ru": [r"(?:удали|убери|сотри)(?: дело| задачу)(?: номер)? " + core.NUM_RE],
              "uz": [core.NUM_RE + r"(?: chi| nchi| inchi)? vazifa\w* (?:ochir|olib tashla)\w*"]},
    examples={"ru": ["Удали дело номер 3"], "uz": ["3-vazifani o'chir"]},
    priority=26,
)
def tasks_delete(ctx: Ctx):
    num = core.parse_number(ctx.group(1))
    items = open_tasks()
    if num is None or not 1 <= num <= len(items):
        return ctx.t(f"Не нашёл дело с таким номером. Открытых дел: {len(items)}.", "Bunday raqamli vazifa yo'q.")
    t = items[num - 1]

    def do() -> str:
        delete_task(t["id"])
        return ctx.t(f"Удалил дело: {t['text']}.", f"O'chirildi: {t['text']}.")

    return core.ask_confirm(ctx, f"Удалить дело «{t['text']}»? Скажите да или нет.", do)


@skill(
    "tasks.done",
    title={"ru": "Отметить дело выполненным", "uz": "Vazifani bajarilgan deb belgilash"},
    patterns={
        "ru": [r"(?:выполнил|выполнила|сделал|сделала|отметь|вычеркни|закрой|готово|закончил|закончила)(?: как выполненное)?(?: дело| задачу)?(?: номер)? " + core.NUM_RE],
        "uz": [
            core.NUM_RE + r"(?: chi| nchi| inchi)? (?:vazifa|ish)\w* (?:bajarildi|bajardim|tugadi|tayyor)",
            r"(?:vazifa|ish) (?:raqam )?" + core.NUM_RE + r" (?:bajarildi|bajardim|tugadi|tayyor)",
        ],
    },
    examples={"ru": ["Выполнил дело номер два"], "uz": ["Ikkinchi vazifa bajarildi"]},
    priority=32,
)
def done(ctx: Ctx):
    num = core.parse_number(ctx.group(1))
    if num is None:
        return None
    items = open_tasks()
    if not 1 <= num <= len(items):
        return ctx.t(f"Дела номер {num} нет. Открытых дел: {len(items)}.",
                     f"{num}-vazifa yo'q. Ochiq vazifalar: {len(items)} ta.")
    task = update_task(items[num - 1]["id"], done=True)
    left = len(open_tasks())
    return ctx.t(f"Отлично, сэр. Выполнено: {task['text']}. Осталось дел: {left}.",
                 f"Ajoyib. Bajarildi: {task['text']}. Qolgan vazifalar: {left} ta.")


@skill(
    "tasks.clear",
    title={"ru": "Закрыть все дела", "uz": "Barcha vazifalarni yopish"},
    patterns={
        "ru": [r"(очисти|удали все|закрой все)\b.*(дел|задач)"],
        "uz": [r"(barcha|hamma) vazifa\w* (ochir|tozala|bajarildi)", r"vazifalarni tozala"],
    },
    examples={"ru": ["Очисти список дел"], "uz": ["Hamma vazifalarni o'chir"]},
    priority=29,
)
def clear(ctx: Ctx) -> str:
    for t in open_tasks():
        update_task(t["id"], done=True)
    return ctx.t("Отметил все дела выполненными.", "Barcha vazifalar bajarildi deb belgilandi.")


def summary(lang: str) -> str:
    """Short spoken summary used by the greeting and periodic nudges."""
    items = open_tasks()
    if not items:
        return "Открытых дел нет." if lang == "ru" else "Ochiq vazifalar yo'q."
    n = len(items)
    today = core.now().date()
    due_today = [t for t in items if t.get("due") and dt.datetime.fromisoformat(t["due"]).date() <= today]
    first = _describe(items[0], lang)
    if lang == "ru":
        s = f"У вас {n} {plural_ru(n, 'открытое дело', 'открытых дела', 'открытых дел')}"
        if due_today:
            s += f", из них на сегодня {len(due_today)}"
        return s + f". Ближайшее: {first}."
    s = f"Sizda {n} ta ochiq vazifa bor"
    if due_today:
        s += f", bugun uchun {len(due_today)} ta"
    return s + f". Eng yaqini: {first}."


def in_quiet_hours(hour: int) -> bool:
    """Quiet hours (no nudges/repeats), e.g. 22 → 8 wraps over midnight.
    Due-time reminders still fire — you set those times yourself."""
    cfg = core.CONFIG.get("tasks", {})
    if "quiet_from" in cfg or "quiet_to" in cfg:
        qf, qt = int(cfg.get("quiet_from", 22)), int(cfg.get("quiet_to", 9))
    else:  # legacy keys: active_from/active_to; if from > to the user meant quiet hours
        af, at = int(cfg.get("active_from", 9)), int(cfg.get("active_to", 22))
        qf, qt = (af, at) if af > at else (at, af)
    if qf == qt:
        return False
    return (qf <= hour or hour < qt) if qf > qt else (qf <= hour < qt)


@core.on_start
def watcher() -> None:
    """Background task tracker: due reminders, overdue nags, periodic nudges."""
    last_nudge = time.time()
    while True:
        try:
            cfg = core.CONFIG.get("tasks", {})
            before = int(cfg.get("remind_before_min", 10))
            nag_h = float(cfg.get("overdue_repeat_hours", 2))
            nudge_h = float(cfg.get("nudge_hours", 3))
            honor_ru = core.CONFIG.get("assistant", {}).get("honorific_ru", "сэр")
            n = core.now()
            active = not in_quiet_hours(n.hour) and not core.CONFIG.get("_game_mode")
            for t in open_tasks():
                if not t.get("due"):
                    continue
                due = dt.datetime.fromisoformat(t["due"])
                lang = t.get("lang", "ru")
                if not core.feature("due_reminders"):
                    continue
                if not t.get("pre_notified") and before and dt.timedelta(0) < due - n <= dt.timedelta(minutes=before):
                    update_task(t["id"], pre_notified=True)
                    mins = max(1, int((due - n).total_seconds() // 60))
                    core.speak(f"{honor_ru.capitalize()}, через {mins} мин.: {t['text']}." if lang == "ru"
                               else f"{mins} daqiqadan keyin: {t['text']}.", lang, urgent=True)
                elif due <= n and not t.get("notified"):
                    update_task(t["id"], notified=True, last_nag=n.isoformat(timespec="minutes"))
                    core.speak(f"{honor_ru.capitalize()}, пора: {t['text']}." if lang == "ru"
                               else f"Vaqt bo'ldi: {t['text']}.", lang, urgent=True)
                elif due <= n and active and nag_h > 0:
                    last = dt.datetime.fromisoformat(t.get("last_nag") or t["due"])
                    if n - last >= dt.timedelta(hours=nag_h):
                        update_task(t["id"], last_nag=n.isoformat(timespec="minutes"))
                        core.speak(f"{honor_ru.capitalize()}, напоминаю: дело «{t['text']}» ещё не выполнено." if lang == "ru"
                                   else f"Eslatma: «{t['text']}» hali bajarilmagan.", lang)
            if nudge_h > 0 and active and core.feature("task_nudges") and time.time() - last_nudge >= nudge_h * 3600:
                last_nudge = time.time()
                if open_tasks():
                    lang = core.CONFIG.get("assistant", {}).get("greeting_lang", "ru")
                    core.speak((f"{honor_ru.capitalize()}, напоминаю. " if lang == "ru" else "Eslatma. ") + summary(lang), lang)
        except Exception:  # noqa: BLE001
            core.log.exception("Task watcher error")
        time.sleep(20)



def find(query: str, k: int = 3, min_score: float = 0.35) -> list[dict]:
    """Open tasks about the query by meaning («что у меня по машине» finds «записаться на ТО»)."""
    import memory
    items = open_tasks()
    return [items[i] for i in memory.search(query, [t["text"] for t in items], k, min_score)]


@skill(
    "tasks.find",
    title={"ru": "Найти дело по смыслу"},
    patterns={"ru": [r"(?:найди|есть ли|есть|какие|какое) (?:у меня )?(?:дел\w*|задач\w*) (?:про|о|об|по|насчет|связанн\w* с) (.+)$",
                     r"^что у меня (?:по|насчет|с) (.+?)\??$"]},
    examples={"ru": ["Есть дела про машину?", "Что у меня по учёбе?"]},
    priority=30,
)
def find_skill(ctx: Ctx) -> str:
    q = ctx.group(1).strip(" ?")
    hits = find(q, k=4, min_score=0.3)
    if not hits:
        return f"Открытых дел про «{q}» нет, сэр."
    return "По этой теме: " + "; ".join(t["text"] + (f" (срок {t['due'].replace('T', ' ')})" if t.get("due") else "")
                                         for t in hits) + "."
