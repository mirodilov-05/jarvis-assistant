"""Voice assistant routing: the first skill that matches each phrase must be the expected one.

Runs only the matching (no skill is executed, nothing is opened, nothing is sent).
"""
import sys
import tempfile
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import core  # noqa: E402

ROUTES = {
    # television: always the prime TV skill
    "включи телевизор": "prime.tv",
    "включи телик": "prime.tv",
    "выключи телевизор": "prime.tv",
    "громче телевизор": "prime.tv",
    "статус телевизора": "prime.tv",
    "открой в телике ютуб": "prime.tv",
    "открой ютуб на телевизоре": "prime.tv",
    "канал вверх телевизор": "prime.tv",
    "пауза телевизор": "prime.tv",
    # laptop YouTube and music: never the TV
    "открой ютуб": "apps.open",
    "включи музыку": "music.play",
    "поставь песню believer в ютуб": "music.youtube",
    "включи believer на ютубе": "music.youtube",
    "открой телеграм": "apps.open",
    "выключи компьютер": "system.shutdown",
}


# catch-all skills: they answer only in a special state (after a question, or for a saved macro name),
# and the live router already skips them when that state is not active. The test skips them too.
CATCH_ALL = {"music.choice", "macros.run"}


def first_match(text: str) -> str | None:
    n = core.normalize(text, "ru")
    for sk in sorted(core.SKILLS, key=lambda s: s.priority):
        if sk.name in CATCH_ALL:
            continue
        for pat in sk.patterns.get("ru", []):
            m = pat.search(n)
            if not m:
                continue
            if sk.name == "modes.toggle":            # returns nothing unless the object is a mode setting
                modes = sys.modules.get("jarvis_plugin_modes")
                if not (modes and modes.find_feature(m.group(2))):
                    continue
            return sk.name
    return None


def test_each_phrase_is_caught_by_its_own_skill():
    t = Path(tempfile.mkdtemp())
    core.DATA, core.SETTINGS_FILE, core.PROFILES_FILE = t, t / "s.json", t / "p.json"
    core._profile_cache.clear()
    (t / "log").mkdir()
    (t / "dictations").mkdir()
    core.load_config()
    core.load_plugins()
    bad = []
    for phrase, expected in ROUTES.items():
        got = first_match(phrase)
        if got != expected:
            bad.append((phrase, "expected", expected, "got", got))
    assert not bad, bad


if __name__ == "__main__":
    test_each_phrase_is_caught_by_its_own_skill()
    print("OK test_each_phrase_is_caught_by_its_own_skill")
