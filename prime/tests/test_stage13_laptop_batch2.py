"""Batch 2: laptop and music phrasings. Each phrase must be caught by one of its expected skills (first match,
catch-all skills skipped as in the live router). Nothing is opened or changed: only the matching is checked.
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
            if sk.name == "modes.toggle":
                modes = sys.modules.get("jarvis_plugin_modes")
                if not (modes and modes.find_feature(m.group(2))):
                    continue
            return sk.name
    return None


OPEN_VERBS = ["открой", "запусти", "включи", "открыть", "запустить"]
APPS = ["телеграм", "ватсап", "дискорд", "стим", "хром", "блокнот", "калькулятор", "проводник", "диспетчер задач", "яндекс браузер", "браузер", "ворд", "эксель", "паинт", "настройки", "загрузки", "telegram", "steam", "chrome"]
MUSIC_VERBS = ["включи", "поставь", "запусти"]
MUSIC_OBJ = ["музыку", "музыка", "песню", "трек"]
VOL_UP = ["громче", "погромче", "увеличь громкость", "прибавь громкость", "громкость больше"]
VOL_DOWN = ["тише", "потише", "уменьши громкость", "убавь громкость", "громкость меньше"]
EXPECT: dict[str, set[str]] = {}

for v, a in itertools.product(OPEN_VERBS, APPS):
    EXPECT[f"{v} {a}"] = {"apps.open", "games.launch", "apps.open_turn_on", "desktop.last_download"}
    if a == "загрузки":   # the Downloads folder: batch 3 opens it too
        EXPECT[f"{v} {a}"].add("batch3.folder")
    if a == "настройки":   # Jarvis settings window, not a program
        EXPECT[f"{v} {a}"].add("ui.settings")
for v, o in itertools.product(MUSIC_VERBS, MUSIC_OBJ):
    EXPECT[f"{v} {o}"] = {"music.play", "apps.music"}
for p in VOL_UP:
    EXPECT[p] = {"system.volume_up", "v3.app_volume", "v3.quieter", "desktop.volume_level", "more.louder_max"}
for p in VOL_DOWN:
    EXPECT[p] = {"system.volume_down", "v3.quieter", "v3.app_volume"}
for p in ("выключи звук", "без звука", "отключи звук"):
    EXPECT[p] = {"system.mute"}
for p in ("сделай скриншот", "скриншот", "сними скриншот экрана"):
    EXPECT[p] = {"system.screenshot"}
for p in ("заблокируй компьютер", "заблокируй ноут", "блокировка компьютера"):
    EXPECT[p] = {"system.lock"}
for p in ("сколько заряда", "какой заряд батареи", "заряд батареи"):
    EXPECT[p] = {"system.battery"}
for p in ("который час", "сколько времени"):
    EXPECT[p] = {"basics.time"}
for p in ("какое сегодня число", "какая сегодня дата"):
    EXPECT[p] = {"basics.date"}
for p in ("яркость 40", "яркость 70"):
    EXPECT[p] = {"desktop.brightness", "desktop.volume_level"}
for p in ("сверни все окна", "покажи рабочий стол"):
    EXPECT[p] = {"desktop.windows"}
for p in ("какие программы у меня есть", "список программ"):
    EXPECT[p] = {"apps.list"}
for p in ("закрой блокнот", "закрой калькулятор"):
    EXPECT[p] = {"apps.close"}
for p in ("какие у меня игры", "список игр"):
    EXPECT[p] = {"games.list"}


def test_every_laptop_phrase_is_caught_by_an_expected_skill():
    bad = []
    for phrase, expected in EXPECT.items():
        got = first_match(phrase)
        if got not in expected:
            bad.append((phrase, sorted(expected), got))
    assert not bad, bad
    assert len(EXPECT) >= 100, len(EXPECT)


def test_youtube_on_laptop_is_not_the_tv():
    assert first_match("открой ютуб") not in ("prime.tv", None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name, len(EXPECT) if name.startswith("test_every") else "")
