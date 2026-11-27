"""TV batch 1: about 150 phrasings (verbs x objects x words) must each reach exactly their TV action.

Checks the table in core/tv_intents.py. Nothing talks to a real TV; the tools are replaced by spies.
"""
import asyncio
import dataclasses
import itertools
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tv_intents import digit_keys, tv_intent  # noqa: E402
import main as prime_main  # noqa: E402

TMP = Path(tempfile.mkdtemp())
prime_main.SETTINGS = dataclasses.replace(prime_main.SETTINGS, db_path=TMP / "prime.db", backup_dir=TMP / "backups")
os.environ.pop("GEMINI_API_KEY", None)

NOUNS = ["телевизор", "телик", "ТВ", "телевизор пожалуйста", "на телевизоре"]
POWER_ON = ["включи", "включить", "вруби", "включай", "зажги", "запусти"]
POWER_OFF = ["выключи", "выключить", "выруби", "вырубай", "погаси", "отключи"]

CASES: dict[str, tuple[str, dict]] = {}
for verb, noun in itertools.product(POWER_ON, NOUNS):
    CASES[f"{verb} {noun}"] = ("tv_on", {})
for verb, noun in itertools.product(POWER_OFF, NOUNS):
    CASES[f"{verb} {noun}"] = ("tv_off", {})
for phrase in ("громче телевизор", "погромче телик", "прибавь громкость телевизор", "увеличь громкость телевизор",
               "громкость больше телевизор", "громкость вверх телевизор", "добавь громкость телик"):
    CASES[phrase] = ("tv_volume", {"direction": "up"})
for phrase in ("тише телевизор", "потише телик", "убавь громкость телевизор", "уменьши громкость телевизор",
               "громкость меньше телевизор", "громкость вниз телик", "убавь телевизор"):
    CASES[phrase] = ("tv_volume", {"direction": "down"})
for phrase in ("статус телевизора", "как там телевизор", "работает ли телевизор", "телевизор включен?",
               "телевизор включён ли", "что с телевизором", "состояние телевизора", "телевизор"):
    CASES[phrase] = ("tv_status", {})
for phrase in ("открой в телике ютуб", "открой ютуб на телевизоре", "включи ютуб на телевизоре",
               "запусти ютуб на телике", "телевизор ютуб", "открой youtube на телевизоре"):
    CASES[phrase] = ("tv_youtube", {})
for phrase in ("канал вверх телевизор", "следующий канал телевизор", "канал плюс телик", "переключи канал вверх телевизор"):
    CASES[phrase] = ("tv_key", {"key": "KEY_CHUP"})
for phrase in ("канал вниз телевизор", "предыдущий канал телевизор", "канал минус телик", "переключи канал вниз телевизор"):
    CASES[phrase] = ("tv_key", {"key": "KEY_CHDOWN"})
for phrase in ("без звука телевизор", "выключи звук телевизор", "отключи звук телик", "заглуши телевизор"):
    CASES[phrase] = ("tv_key", {"key": "KEY_MUTE"})
for phrase in ("включи звук телевизор", "верни звук телик"):
    CASES[phrase] = ("tv_key", {"key": "KEY_MUTE"})
for phrase in ("пауза телевизор", "останови телевизор", "поставь на паузу телик"):
    CASES[phrase] = ("tv_key", {"key": "KEY_PAUSE"})
for phrase in ("играй телевизор", "продолжи телевизор", "воспроизведи телик"):
    CASES[phrase] = ("tv_key", {"key": "KEY_PLAY"})
for phrase in ("домой телевизор", "главный экран телевизор"):
    CASES[phrase] = ("tv_key", {"key": "KEY_HOME"})
for phrase in ("назад телевизор", "вернись телевизор"):
    CASES[phrase] = ("tv_key", {"key": "KEY_RETURN"})
for phrase in ("меню телевизор", "открой меню телевизора"):
    CASES[phrase] = ("tv_key", {"key": "KEY_MENU"})
for phrase in ("источник телевизор", "смени вход телевизор", "hdmi телевизор"):
    CASES[phrase] = ("tv_key", {"key": "KEY_SOURCE"})
for phrase, key in (("вверх телевизор", "KEY_UP"), ("вниз телевизор", "KEY_DOWN"),
                    ("влево телевизор", "KEY_LEFT"), ("вправо телевизор", "KEY_RIGHT"),
                    ("ок телевизор", "KEY_ENTER"), ("выбери телевизор", "KEY_ENTER")):
    CASES[phrase] = ("tv_key", {"key": key})
CASES["канал 5 телевизор"] = ("tv_digits", {"digits": "5"})
CASES["переключи на канал 12 телевизор"] = ("tv_digits", {"digits": "12"})
CASES["12 канал телик"] = ("tv_digits", {"digits": "12"})


def test_table_routes_every_phrase_to_its_action():
    bad = []
    for phrase, expected in CASES.items():
        got = tv_intent(phrase.lower())
        if got != expected:
            bad.append((phrase, expected, got))
    assert not bad, bad[:10]
    assert len(CASES) >= 100, len(CASES)


def test_channel_number_becomes_digit_keys():
    assert digit_keys("12") == ["KEY_1", "KEY_2"]


def test_no_tv_word_means_not_a_tv_phrase():
    for phrase in ("включи музыку", "открой ютуб", "выключи компьютер", "канал вверх", "громче"):
        assert tv_intent(phrase) is None


def test_through_prime_every_case_calls_the_right_tool():
    async def run():
        p = prime_main.Prime()
        calls = []
        for name in ("tv_on", "tv_off", "tv_volume", "tv_status", "tv_youtube", "tv_key", "tv_digits", "ask_brain"):
            def make(n):
                async def spy(**kw):
                    calls.append((n, kw))
                    return "ok"
                return spy
            p.registry.tools[name].run = make(name)
        failures = []
        for phrase, (tool, args) in list(CASES.items())[::4]:      # a quarter of them, end to end
            calls.clear()
            await p.handle(phrase)
            if not calls or calls[0][0] != tool or (args and calls[0][1] != args):
                failures.append((phrase, tool, calls[:1]))
            if any(c[0] == "ask_brain" for c in calls):
                failures.append((phrase, "brain"))
        return failures
    assert not asyncio.run(run())



def test_spoken_variants_of_the_tv_word_and_youtube():
    for phrase in ("запусти ютюб в телеизоре", "запусти ютуб в телеизоре", "открой ютуб в телеизоре",
                   "включи ютуб на телевизоре", "запусти ютюб на телике"):
        assert tv_intent(phrase)[0] == "tv_youtube", phrase
    assert tv_intent("телеизоре громче")[0] == "tv_volume"
    assert tv_intent("почтовый ящик") is None

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name, len(CASES) if name == "test_table_routes_every_phrase_to_its_action" else "")
