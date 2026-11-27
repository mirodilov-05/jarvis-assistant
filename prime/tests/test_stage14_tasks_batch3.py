"""Batch 3: tasks, goals, notes and reminders phrasings. Each phrase must be caught by one of its expected skills
(first match, catch-all skills skipped as in the live router). Nothing is saved or changed: only matching is checked.
"""
import itertools
import sys
import tempfile
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import core  # noqa: E402

CATCH_ALL = {"music.choice", "macros.run"}
_loaded = {"done": False}


def _load() -> None:
    if _loaded["done"]:
        return
    t = Path(tempfile.mkdtemp())
    core.DATA, core.SETTINGS_FILE, core.PROFILES_FILE = t, t / "s.json", t / "p.json"
    core._profile_cache.clear()
    (t / "log").mkdir()
    (t / "dictations").mkdir()
    core.load_config()
    core.load_plugins()
    _loaded["done"] = True


def first_match(text: str) -> str | None:
    _load()
    n = core.normalize(text, "ru")
    for sk in sorted(core.SKILLS, key=lambda s: s.priority):
        if sk.name in CATCH_ALL:
            continue
        for pat in sk.patterns.get("ru", []):
            m = pat.search(n)
            if not m:
                continue
            if sk.name == "modes.toggle":          # returns nothing unless the object is a mode setting
                modes = sys.modules.get("jarvis_plugin_modes")
                if not (modes and modes.find_feature(m.group(2))):
                    continue
            return sk.name
    return None


EXPECT: dict[str, set[str]] = {}

# tasks: add
for verb, noun, obj in itertools.product(["добавь", "запиши", "создай", "внеси"], ["дело", "задачу"],
                                         ["купить хлеб", "позвонить маме", "сделать отчёт", "оплатить интернет"]):
    EXPECT[f"{verb} {noun} {obj}"] = {"tasks.add"}
for p in ("добавь дело купить хлеб завтра в 10", "запиши дело отправить документы"):
    EXPECT[p] = {"tasks.add"}
# tasks: list, day, week, overdue
for p in ("сколько у меня дел", "какие у меня дела", "покажи мои дела", "мои дела", "список дел", "мои задачи"):
    EXPECT[p] = {"tasks.list"}
for p in ("что у меня на завтра", "какие дела на завтра", "дела на послезавтра"):
    EXPECT[p] = {"tasks.day"}
for p in ("дела на неделю", "план на неделю", "недельный план"):
    EXPECT[p] = {"tasks.week"}
for p in ("какие дела просрочены", "просроченные дела"):
    EXPECT[p] = {"tasks.overdue"}
for p in ("есть дела про машину", "найди дела про врача"):
    EXPECT[p] = {"tasks.find"}
# tasks: done (numbers) — goal steps are separate
for verb, num in itertools.product(["выполнил", "выполнила", "отметь", "готово", "закончил"],
                                   ["дело номер два", "дело номер 2", "задачу номер три"]):
    EXPECT[f"{verb} {num}"] = {"tasks.done"}
for p in ("закрой дело номер два", "закрой задачу 3"):
    EXPECT[p] = {"tasks.done"}
# tasks: delete / move / clear
for p in ("удали дело номер три", "убери дело 2", "сотри задачу номер один"):
    EXPECT[p] = {"tasks.delete"}
for p in ("перенеси дело 2 на завтра в 10", "отложи дело номер три на пятницу"):
    EXPECT[p] = {"tasks.move"}
for p in ("очисти список дел", "удали все дела"):
    EXPECT[p] = {"tasks.clear"}
# goals
for p in ("цель выучить японский", "цель: 50 слов японского", "новая цель пробежать марафон", "моя цель читать книги"):
    EXPECT[p] = {"goals.add"}
for p in ("мои цели", "покажи цели", "какие цели", "прогресс", "прогресс по целям"):
    EXPECT[p] = {"goals.list"}
for p in ("сделал шаг по цели японский", "выполнил шаг по цели японский", "отметь шаг по цели японский"):
    EXPECT[p] = {"goals.tick"}
for p in ("+5 к цели японский", "3 к цели японский"):
    EXPECT[p] = {"goals.tick"}
for p in ("удали цель японский", "убери цель марафон", "забудь цель книги"):
    EXPECT[p] = {"goals.delete"}
# repeating reminders (goals plugin)
for n, what in itertools.product(["30", "60", "90"], ["пить воду", "встать и размяться"]):
    EXPECT[f"напоминай каждые {n} минут {what}"] = {"goals.repeat"}
for t in ("08:00", "22:30", "7:15"):
    EXPECT[f"напоминай каждый день в {t} ложиться спать"] = {"goals.repeat"}
for p in ("убери напоминание про воду", "отмени напоминание про воду"):
    EXPECT[p] = {"goals.repeat_cancel", "reminders.cancel"}
for p in ("мои напоминания", "мои повторяющиеся напоминания"):
    EXPECT[p] = {"goals.repeat_list", "reminders.list"}
# limits (goals plugin)
for p in ("ограничь YouTube 1 час в день", "ограничь steam 90 минут", "ограничь discord 30 минут в день"):
    EXPECT[p] = {"goals.limit"}
for p in ("какие ограничения", "сколько осталось в программах"):
    EXPECT[p] = {"goals.limit_list"}
for p in ("сними ограничение с YouTube", "отмени ограничение на steam"):
    EXPECT[p] = {"goals.limit_cancel"}
# timers and reminders
for p in ("поставь таймер на 5 минут", "заведи таймер на 10 минут", "запусти таймер на 2 минуты"):
    EXPECT[p] = {"reminders.timer", "more.timer"}   # more.timer hands the same phrase to reminders.timer
for p in ("напомни через 10 минут выпить воду", "через 5 минут напомни проверить духовку"):
    EXPECT[p] = {"reminders.in"}
for p in ("напомни в 18:30 позвонить маме", "напомни завтра в 9 утра про встречу"):
    EXPECT[p] = {"reminders.at"}
for p in ("разбуди меня в 7",):
    EXPECT[p] = {"reminders.at", "more.alarm"}
for p in ("поставь будильник на 7", "заведи будильник на 6 30"):
    EXPECT[p] = {"reminders.at", "more.alarm"}
for p in ("какие напоминания", "покажи мои таймеры", "что ты мне напомнишь"):
    EXPECT[p] = {"reminders.list", "goals.repeat_list"}
for p in ("отмени таймер", "удали все напоминания", "сбрось таймер"):
    EXPECT[p] = {"reminders.cancel"}
# notes
for p in ("запиши заметку код от домофона 1234", "заметка купить молоко", "сохрани заметку номер телефона мамы"):
    EXPECT[p] = {"notes.add"}
for p in ("прочитай заметки", "мои заметки", "покажи заметки", "заметки за сегодня"):
    EXPECT[p] = {"notes.read", "more.notes_list"}
for p in ("найди в заметках домофон", "поищи в заметках вайфай", "что я записывал про машину"):
    EXPECT[p] = {"notes.search"}
for p in ("какой у меня пароль от вайфая", "какой у меня код от домофона"):
    EXPECT[p] = {"notes.recall"}
for p in ("удали последнюю заметку", "сотри заметку номер два"):
    EXPECT[p] = {"notes.delete"}
for p in ("очисти заметки", "сотри все заметки"):
    EXPECT[p] = {"notes.clear"}


def test_every_phrase_is_caught_by_an_expected_skill():
    bad = []
    for phrase, expected in EXPECT.items():
        got = first_match(phrase)
        if got not in expected:
            bad.append((phrase, sorted(expected), got))
    assert not bad, bad
    assert len(EXPECT) >= 100, len(EXPECT)


if __name__ == "__main__":
    test_every_phrase_is_caught_by_an_expected_skill()
    print("OK test_every_phrase_is_caught_by_an_expected_skill", len(EXPECT))
