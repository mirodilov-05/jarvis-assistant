"""Batch 3 of everyday commands: routes and the pure answers (conversion, days to the weekend).

Nothing is opened, created or sent: folders and the network are not touched.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import core  # noqa: E402
from core import Ctx, normalize  # noqa: E402

core.load_plugins()
CATCH = {"music.choice", "macros.run"}
ROUTES = {
    "открой загрузки": "batch3.folder",
    "покажи скриншоты": "batch3.folder",
    "открой последний файл в документах": "batch3.newest",
    "открой последний скриншот": "batch3.screenshot",
    "создай папку проекты на рабочем столе": "batch3.make_folder",
    "проверь интернет": "batch3.internet",
    "какой внешний ip": "batch3.public_ip",
    "сколько дней до выходных": "batch3.weekend",
    "переведи 10 км в мили": "batch3.convert",
}


def first_match(text):
    norm = normalize(text, "ru")
    for sk in core.SKILLS:
        if sk.name in CATCH:
            continue
        if any(p.search(norm) for p in sk.patterns.get("ru", [])):
            return sk.name
    return None


def _run(name, text):
    sk = next(s for s in core.SKILLS if s.name == name)
    norm = normalize(text, "ru")
    for p in sk.patterns["ru"]:
        m = p.search(norm)
        if m:
            return sk.handler(Ctx(text=text, lang="ru", source="тест", config=core.CONFIG, match=m, norm=norm))
    return None


def test_routes():
    bad = {t: (first_match(t), want) for t, want in ROUTES.items() if first_match(t) != want}
    assert not bad, bad


def test_unit_conversion():
    assert _run("batch3.convert", "переведи 10 км в мили") == "10 км — это 6.21 мили."


def test_days_to_weekend_is_positive_or_today():
    text = _run("batch3.weekend", "сколько дней до выходных")
    assert text and ("До выходных" in text or "Сегодня уже выходной" in text), text


if __name__ == "__main__":
    test_routes()
    test_unit_conversion()
    test_days_to_weekend_is_positive_or_today()
    print("stage26: all passed")
