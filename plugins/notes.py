"""Notes: add, read (numbered), today's notes, search, delete, clear — all by voice.
Stored in data/notes.md (one "- YYYY-MM-DD HH:MM — text" line per note).
"""

import re

import core
from core import Ctx, ask_confirm, skill

FILE = core.DATA / "notes.md"


def all_notes() -> list[dict]:
    if not FILE.exists():
        return []
    out = []
    for ln in FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — (.*)$", ln)
        if m:
            out.append({"time": m.group(1), "text": m.group(2)})
        elif ln.startswith("- "):
            out.append({"time": "", "text": ln[2:]})
    return out


def save_all(notes: list[dict]) -> None:
    with core.file_lock:
        FILE.write_text("".join(f"- {n['time']} — {n['text']}\n" for n in notes), encoding="utf-8")
    core.emit({"type": "data", "file": FILE.name})


def add_note(text: str) -> None:
    with core.file_lock, open(FILE, "a", encoding="utf-8") as f:
        f.write(f"- {core.now():%Y-%m-%d %H:%M} — {text}\n")
    core.emit({"type": "data", "file": FILE.name})


def find(query: str, k: int = 3, min_score: float = 0.35) -> list[tuple[int, dict]]:
    """Notes about the query by meaning («пароль от интернета» finds «пароль от вайфая»), best first, 1-based."""
    import memory
    notes = all_notes()
    return [(i + 1, notes[i]) for i in memory.search(query, [n["text"] for n in notes], k, min_score)]


def _read(ctx: Ctx, items: list[tuple[int, dict]], empty: str) -> str:
    if not items:
        return empty
    return " ".join(f"{i}. {n['text']}." for i, n in items)


@skill(
    "notes.add",
    title={"ru": "Записать заметку", "uz": "Eslatma (qayd) yozish"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:запиши заметку|заметка|запомни|сохрани заметку|запиши себе|добавь заметку)\s*(?:что )?(.+)$"],
        "uz": [r"^(?:jarvis )?(?:qayd|zametka|eslatma) (?:yoz|qosh|qil)\w*\s+(.+)$", r"^(?:jarvis )?(?:eslab qol)\w*\s+(.+)$",
               r"^(.+?) (?:ni )?(?:eslab qol)\w*$"],
    },
    examples={"ru": ["Запиши заметку код от домофона 1234", "Запомни, что Ахмад любит чай"], "uz": ["Qayd yoz domofon kodi 1234"]},
    priority=40,
)
def add(ctx: Ctx):
    body = ctx.group(1)
    if not body:
        return None
    pos = ctx.text.lower().find(body.split()[0])
    if ctx.lang == "ru" and pos >= 0:
        body = ctx.text[pos:].strip(" .!")
    add_note(body)
    return ctx.t(f"Записал: {body}.", f"Yozib oldim: {body}.")


@skill(
    "notes.read",
    title={"ru": "Прочитать заметки (с номерами)", "uz": "Qaydlarni o'qish"},
    patterns={"ru": [r"(прочитай|покажи|какие|мои|список)\b.*\bзаметк", r"^(?:джарвис )?(?:мои )?заметки(?: за сегодня| сегодня| за день)?$",
                     r"заметки за (сегодня|день)"],
              "uz": [r"(qaydlar|zametkalar|yozganlarim)\w*\s*(ni)?\s*(oqi|korsat|ayt)?$"]},
    examples={"ru": ["Прочитай заметки", "Заметки за сегодня"], "uz": ["Qaydlarni o'qi"]},
    priority=41,
)
def read(ctx: Ctx) -> str:
    notes = list(enumerate(all_notes(), 1))
    if "сегодня" in ctx.norm or "bugun" in ctx.norm:
        today = core.now().strftime("%Y-%m-%d")
        notes = [(i, n) for i, n in notes if n["time"].startswith(today)]
        return _read(ctx, notes, ctx.t("Сегодня заметок нет.", "Bugun qaydlar yo'q."))
    return _read(ctx, notes[-7:], ctx.t("Заметок пока нет.", "Hozircha qaydlar yo'q."))


@skill(
    "notes.search",
    title={"ru": "Найти в заметках", "uz": "Qaydlardan qidirish"},
    patterns={"ru": [r"(?:найди|поищи|что я записывал|что я записал)(?: в заметках| в записях)? (?:про |о |об )?(.+?)(?: в заметках)?$"],
              "uz": [r"qaydlardan (.+?) (?:ni )?(?:top|qidir)\w*$"]},
    examples={"ru": ["Найди в заметках домофон"], "uz": ["Qaydlardan domofonni top"]},
    priority=39,
)
def search(ctx: Ctx):
    if "заметк" not in ctx.norm and "записыв" not in ctx.norm and "записал" not in ctx.norm and ctx.lang == "ru":
        return None   # plain "найди X" is a web search
    q = ctx.group(1).lower()
    hits = find(q, k=5, min_score=0.45)
    return _read(ctx, hits, ctx.t(f"В заметках ничего про «{q}».", f"Qaydlarda «{q}» haqida hech narsa yo'q."))


@skill(
    "notes.recall",
    title={"ru": "Вспомнить то, что я просил запомнить"},
    patterns={"ru": [r"(?:какой|какая|какое|какие|напомни|скажи|подскажи)(?: у меня| мой| моя| мне)? "
                     r"(пароль|код|номер|адрес|логин|пин|пинкод|день рождения|дату|почту)\w* ?(.*)$",
                     r"(?!.*\b(?:записывал|записал) (?:про|о|об|насчет)\b)(?:что|какой|какую|какие) я (?:тебе )?(?:говорил|просил запомнить|записывал|просил записать|сохранял)"
                     r" ?(?:про |о |об |насчет )?(.*)$",
                     r"(?:что|о чем|про что|какую идею) я (?:хотел|собирался|планировал|придумал)(?: тебе)? ?(.*)$",
                     r"(?:ты )?помнишь(?: ли)?(?: что| про| о)? (.+)$"]},
    examples={"ru": ["Какой у меня пароль от вайфая?", "Что я говорил про Ахмада?"]},
    priority=38,
)
def recall(ctx: Ctx) -> str:
    query = " ".join(x for x in (ctx.match.groups() if ctx.match else []) if x).strip()
    if len(query) < 3:
        return None
    hits = find(ctx.text, k=2, min_score=0.3)   # the whole question carries the meaning («какой пароль от интернета»)
    if not hits:
        return ctx.t(f"Ты мне ничего не говорил про «{query}». Скажи «запомни …», и я сохраню.", "Bu haqida eslatma yo'q.")
    # "пароль от почты" vs a note "пароль от вайфая": same kind of thing, different object — say so honestly
    import memory
    obj = re.search(r"\b(?:от|для|к) (\w{3,})", ctx.norm)
    if obj and not any(memory.mentions(n["text"], obj.group(1)) for _, n in hits):
        return f"Этого ты мне не говорил. Есть только похожее: {hits[0][1]['text']}."
    return " ".join(n["text"] + "." for _, n in hits)


@skill(
    "notes.delete",
    title={"ru": "Удалить заметку (номер или последнюю)", "uz": "Qaydni o'chirish"},
    patterns={"ru": [r"(?:удали|сотри|убери) (?:последнюю )?заметку(?: номер)? ?" + core.NUM_RE + r"?$",
                     r"(?:удали|сотри|убери) последнюю заметку"],
              "uz": [r"(?:oxirgi )?qayd\w* (?:ochir|olib tashla)\w*", core.NUM_RE + r"(?: chi| nchi| inchi)? qayd\w* ochir\w*"]},
    examples={"ru": ["Удали последнюю заметку", "Удали заметку 2"], "uz": ["Oxirgi qaydni o'chir"]},
    priority=38,
)
def delete(ctx: Ctx) -> str:
    notes = all_notes()
    if not notes:
        return ctx.t("Заметок нет.", "Qaydlar yo'q.")
    num = None
    if ctx.match and ctx.match.lastindex and "последн" not in ctx.norm and "oxirgi" not in ctx.norm:
        num = core.parse_number(ctx.group(ctx.match.lastindex) or "")
    idx = (num - 1) if num else len(notes) - 1
    if not 0 <= idx < len(notes):
        return ctx.t(f"Заметки номер {num} нет. Всего заметок: {len(notes)}.", f"{num}-qayd yo'q.")
    target = notes[idx]

    def do() -> str:
        cur = all_notes()
        if target in cur:
            cur.remove(target)
            save_all(cur)
        return ctx.t(f"Удалил заметку: {target['text']}.", f"O'chirildi: {target['text']}.")

    return ask_confirm(ctx, f"Удалить заметку «{target['text']}»? Скажите да или нет.", do)


@skill(
    "notes.clear",
    title={"ru": "Очистить все заметки (с подтверждением)", "uz": "Barcha qaydlarni tozalash"},
    patterns={"ru": [r"(?:очисти|удали все|сотри все) заметки"], "uz": [r"(?:barcha|hamma) qayd\w* (?:ochir|tozala)\w*"]},
    examples={"ru": ["Очисти заметки"], "uz": ["Hamma qaydlarni o'chir"]},
    priority=37,
)
def clear(ctx: Ctx) -> str:
    n = len(all_notes())
    if not n:
        return ctx.t("Заметок и так нет.", "Qaydlar yo'q.")

    def do() -> str:
        save_all([])
        return ctx.t("Все заметки удалены.", "Barcha qaydlar o'chirildi.")

    return ask_confirm(ctx, ctx.t(f"Удалить все {n} заметок? Скажите да или нет.", f"{n} ta qaydni o'chiraymi? Ha yoki yo'q."), do)
