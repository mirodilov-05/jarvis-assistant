"""Tasks, reminders, notes, time, calculator."""

import re

import core
from tools import run_skill, tool

S = {"type": "string"}
WHEN = {**S, "description": "Когда, как сказал пользователь: «завтра в 10», «в пятницу», «через 2 часа», «сегодня в 18:30»"}
NUM = {"type": "integer", "description": "Номер дела из списка дел"}


@tool("add_task", "Добавить дело в список дел (можно со сроком). Используй для «надо», «не забыть», «запиши в дела».",
      {"text": {**S, "description": "Что сделать, коротко"}, "when": WHEN}, ["text"])
def add_task(text: str, when: str = "") -> str:
    return run_skill("tasks.add", f"добавь дело {text} {when}".strip())


@tool("list_tasks", "Показать дела. period: today, tomorrow, week, overdue, all, или день недели (monday…sunday).",
      {"period": {"type": "string", "enum": ["today", "tomorrow", "week", "overdue", "all", "monday", "tuesday",
                                              "wednesday", "thursday", "friday", "saturday", "sunday"]}})
def list_tasks(period: str = "all") -> str:
    days = {"monday": "понедельник", "tuesday": "вторник", "wednesday": "среду", "thursday": "четверг",
            "friday": "пятницу", "saturday": "субботу", "sunday": "воскресенье"}
    if period == "today":
        return run_skill("tasks.list", "какие у меня дела на сегодня")
    if period == "tomorrow":
        return run_skill("tasks.day", "что у меня на завтра")
    if period == "week":
        return run_skill("tasks.week", "дела на неделю")
    if period == "overdue":
        return run_skill("tasks.overdue", "какие дела просрочены")
    if period in days:
        return run_skill("tasks.day", f"дела на {days[period]}")
    return run_skill("tasks.list", "сколько у меня дел")


@tool("complete_task", "Отметить дело выполненным по номеру.", {"number": NUM}, ["number"])
def complete_task(number: int) -> str:
    return run_skill("tasks.done", f"выполнил дело {int(number)}")


@tool("move_task", "Перенести дело на другое время.", {"number": NUM, "when": WHEN}, ["number", "when"])
def move_task(number: int, when: str) -> str:
    return run_skill("tasks.move", f"перенеси дело {int(number)} на {when}")


@tool("delete_task", "Удалить дело (без отметки о выполнении).", {"number": NUM}, ["number"],
      tier="self")   # the skill itself asks "Удалить дело …? да/нет"
def delete_task(number: int) -> str:
    return run_skill("tasks.delete", f"удали дело номер {int(number)}")


@tool("set_reminder", "Напомнить голосом в определённое время: «через 20 минут», «в 18:30», «завтра в 9».",
      {"text": {**S, "description": "О чём напомнить"}, "when": WHEN}, ["text", "when"])
def set_reminder(text: str, when: str) -> str:
    w = when.strip().lower()
    if w.startswith("через") or re.match(r"^(завтра )?в \d", w):
        out = run_skill("reminders.in" if w.startswith("через") else "reminders.at", f"напомни {w} {text}")
        if out:
            return out
    return add_task(text, when)   # e.g. "в пятницу" -> a task with a due date (it reminds too)


@tool("set_timer", "Поставить таймер.", {"minutes": {"type": "number"}, "seconds": {"type": "number"}})
def set_timer(minutes: float = 0, seconds: float = 0) -> str:
    if seconds and not minutes:
        return run_skill("reminders.timer", f"поставь таймер на {int(seconds)} секунд")
    return run_skill("reminders.timer", f"поставь таймер на {int(minutes or 1)} минут")


@tool("set_alarm", "Будильник на время, например «7:00» или «6:30».", {"time": {**S, "description": "ЧЧ:ММ"}}, ["time"])
def set_alarm(time: str) -> str:
    return run_skill("reminders.at", f"разбуди меня в {time}")


@tool("list_reminders", "Список напоминаний и таймеров.")
def list_reminders() -> str:
    return run_skill("reminders.list", "какие напоминания")


@tool("cancel_reminders", "Отменить все напоминания и таймеры.", tier="confirm",
      confirm_text=lambda: "отменить все напоминания и таймеры")
def cancel_reminders() -> str:
    return run_skill("reminders.cancel", "отмени все напоминания")


@tool("remember", "Запомнить факт, идею или заметку (код, пароль от вайфая, идея для видео, что любит человек).",
      {"text": S}, ["text"])
def remember(text: str) -> str:
    return run_skill("notes.add", f"запиши заметку {text}")


@tool("search_notes", "Найти в заметках/памяти по теме.", {"query": S}, ["query"])
def search_notes(query: str) -> str:
    return run_skill("notes.search", f"найди в заметках {query}")


@tool("read_notes", "Прочитать заметки: recent — последние, today — за сегодня.",
      {"period": {"type": "string", "enum": ["recent", "today"]}})
def read_notes(period: str = "recent") -> str:
    return run_skill("notes.read", "заметки за сегодня" if period == "today" else "прочитай заметки")


@tool("delete_note", "Удалить заметку по номеру или последнюю (number=0).", {"number": {"type": "integer"}},
      tier="self")
def delete_note(number: int = 0) -> str:
    return run_skill("notes.delete", f"удали заметку {int(number)}" if number else "удали последнюю заметку")


@tool("get_datetime", "Текущее время и дата.")
def get_datetime() -> str:
    return run_skill("basics.time", "который час") + " " + run_skill("basics.date", "какое сегодня число")


@tool("calculate", "Посчитать арифметику: «25*4», «1500/3+20».", {"expression": S}, ["expression"])
def calculate(expression: str) -> str:
    expr = expression.replace("×", "*").replace("÷", "/").replace(",", ".")
    if not re.fullmatch(r"[\d\s.+\-*/()%]+", expr):
        return ""
    try:
        value = eval(expr, {"__builtins__": {}}, {})  # digits/operators only, checked above
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(value, float):
        value = round(value, 6)
        value = int(value) if value.is_integer() else value
    return f"Получается {value}."
