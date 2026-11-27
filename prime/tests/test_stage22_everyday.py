"""Everyday commands: each phrase reaches its own skill, and the dangerous ones only ask (nothing is executed).

Runs in the Jarvis root (the Jarvis skills), no sound, no shutdown, no recycle bin emptied.
"""
import sys
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import core  # noqa: E402
from core import Ctx, normalize  # noqa: E402

core.load_plugins()
CATCH_ALL = {"music.choice", "macros.run"}

ROUTES = {
    "будильник на 6 30": "more.alarm",
    "разбуди меня в 8": "more.alarm",
    "таймер на 10 минут": "more.timer",
    "засеки 5 минут": "more.timer",
    "помодоро": "more.timer",
    "сделай паузу": "more.timer",
    "сколько осталось до конца дня": "more.until_day_end",
    "сделай заметку что завтра встреча": "more.note",
    "что у меня в заметках": "more.notes_list",
    "курс евро": "more.euro",
    "подними громкость": "more.louder_max",
    "максимальная громкость": "more.louder_max",
    "положи ноутбук спать": "more.sleep",
    "сколько памяти свободно": "more.memory",
    "очисти корзину": "more.recycle",
    "какой ip адрес у компьютера": "more.ip",
    "построй маршрут до центра": "more.route",
    "выключи блютуз": "more.wifi_bt",
    "подбрось монетку": "more.coin",
    "выбери чай или кофе": "more.choose",
    "случайное число от 1 до 10": "more.random_number",
    "будет ли сегодня дождь": "more.rain",
    "какой завтра праздник": "more.holiday",
    "расскажи новости": "more.news",
    "выключи компьютер через 30 минут": "more.shutdown_later",
    "что в буфере обмена": "more.clipboard",
    "покажи мои файлы": "more.my_files",
    "отметь дело купить хлеб выполненным": "more.task_done_by_name",
    "сделай громче": "system.volume_up",
    "который час": "basics.time",
    "какая погода": "weather.now",
    "напомни через 2 часа выпить воды": "reminders.in",
    "покажи мои напоминания": "reminders.list",
    "прочитай мои заметки": "notes.read",
    "какие у меня дела": "tasks.list",
}


def first_match(text):
    norm = normalize(text, "ru")
    for sk in core.SKILLS:
        if sk.name in CATCH_ALL:
            continue
        if any(p.search(norm) for p in sk.patterns.get("ru", [])):
            return sk.name
    return None


def test_everyday_phrases_reach_their_skill():
    bad = {t: (first_match(t), want) for t, want in ROUTES.items() if first_match(t) != want}
    assert not bad, bad


def _run(skill_name, text):
    norm = normalize(text, "ru")
    sk = next(s for s in core.SKILLS if s.name == skill_name)
    for p in sk.patterns["ru"]:
        m = p.search(norm)
        if m:
            return sk.handler(Ctx(text=text, lang="ru", source="тест", config=core.CONFIG, match=m, norm=norm))
    return None


def test_dangerous_commands_only_ask(monkeypatch=None):
    core.PENDING.clear()
    question = _run("more.recycle", "очисти корзину")
    assert "Скажите «да»" in question and core.PENDING, question
    core.PENDING.clear()
    question = _run("more.shutdown_later", "выключи компьютер через 30 минут")
    assert "через 30 минут" in question and core.PENDING, question
    core.PENDING.clear()


def test_answers_that_need_no_device():
    text = _run("more.random_number", "случайное число от 1 до 10")
    assert text and text.startswith("Выпало ")
    assert _run("more.days_to_new_year", "сколько дней до нового года").startswith("До Нового года")
    assert _run("more.wifi_bt", "выключи блютуз").startswith("Wi-Fi и Bluetooth")


if __name__ == "__main__":
    test_everyday_phrases_reach_their_skill()
    test_dangerous_commands_only_ask()
    test_answers_that_need_no_device()
    print("stage22: all passed")
