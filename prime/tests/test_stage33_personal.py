"""Stage 33: a downloaded Jarvis carries nobody's personal data and fits each new owner by studying their computer.

Everything here runs on temporary files: no real profile, settings or index are read or written.
"""
import json
import re
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import core  # noqa: E402


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    assert ok, name


def load_plugin(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{name}", ROOT / "plugins" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PROFILE = {"scanned_at": "2026-01-01T10:00:00", "browser": "Google Chrome",
           "installed": ["Google Chrome", "Telegram Desktop", "Discord", "Spotify", "Microsoft Word", "Steam"],
           "apps": ["Telegram Desktop", "OBS Studio"], "hardware": {"os": "Windows 11", "ram_gb": 16}, "folders": {}}


def _temp_profile(data=None):
    p = Path(tempfile.mkdtemp(prefix="jarvis33_")) / "pc_profile.json"
    if data is not None:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_the_shared_code_has_no_personal_defaults():
    tracked = subprocess.run(["git", "ls-files", "*.py", "*.toml", "*.js"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if not tracked:                     # not a git checkout (a ZIP): read the files directly
        tracked = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py") if ".venv" not in p.parts]
    bad = []
    for rel in tracked:
        if "tests" in rel:
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        if re.search(r"Яндекс Браузер; игры|игры — CS2|\"Tashkent\"|'Tashkent'", text):
            bad.append(rel)
    check("no owner's browser, games or city are written into the code", bad == [])
    cfg = (ROOT / "config.toml").read_text(encoding="utf-8")
    check("the default city is empty: a new owner is asked", re.search(r'^city = ""', cfg, re.M) is not None)
    check("no one's name, mail or Telegram keys in config.toml",
          re.search(r'^user_name = ""', cfg, re.M) and re.search(r'^address = ""', cfg, re.M) and re.search(r'^api_id = ""', cfg, re.M))


def test_before_the_study_jarvis_assumes_nothing():
    import agent
    import personalize
    import pc_profile
    with mock.patch.object(pc_profile, "PROFILE", _temp_profile(None)), \
            mock.patch.object(core, "setting", side_effect=lambda s, k, d=None: d):
        prefs = agent.preferences()
        check("no browser or games are claimed before the study", "браузер" not in prefs and "игры" not in prefs)
        check("music defaults to YouTube, which works for everyone", "YouTube" in prefs)
        check("the speech hint has no programs yet", personalize.speech_hint() == "")


def test_after_the_study_jarvis_knows_this_owner():
    import agent
    import personalize
    import pc_profile
    data = dict(PROFILE, games=["Minecraft", "Dota 2"], messengers=["Telegram", "Discord"], personalized_at="2026-01-01T10:01:00")
    with mock.patch.object(pc_profile, "PROFILE", _temp_profile(data)), \
            mock.patch.object(core, "setting", side_effect=lambda s, k, d=None: d):
        prefs = agent.preferences()
        check("the brain knows this owner's browser", "браузер — Google Chrome" in prefs)
        check("…and the games on this PC", "Minecraft" in prefs and "Dota 2" in prefs)
        hint = personalize.speech_hint()
        check("speech recognition listens for this PC's programs and games", "Telegram Desktop" in hint and "Minecraft" in hint)
    found = personalize.detect(PROFILE)
    check("music and messengers are found from the programs", found["music"] == "Spotify" and found["messengers"] == ["Telegram", "Discord"])


def test_the_study_runs_every_part_and_survives_a_failure():
    import personalize
    import pc_profile
    prof_path = _temp_profile(None)
    games = types.SimpleNamespace(all_games=lambda refresh=False: [{"name": "Minecraft"}, {"name": "Counter-Strike 2"}, {"name": "Steam"}])
    finder = types.SimpleNamespace(learn_all=lambda: (_ for _ in ()).throw(RuntimeError("нет ключа")))
    saved = {}
    with mock.patch.object(pc_profile, "PROFILE", prof_path), mock.patch.object(pc_profile, "scan", return_value=dict(PROFILE)), \
            mock.patch.dict(sys.modules, {"jarvis_plugin_games": games, "jarvis_plugin_appfinder": finder}), \
            mock.patch("pc_index.build", return_value={"built": True, "files": 1234}), \
            mock.patch.object(core, "save_setting", side_effect=lambda s, k, v: saved.__setitem__((s, k), v)), \
            mock.patch.object(core, "load_json", side_effect=lambda p, d: d if "settings" in str(p) else json.loads(Path(p).read_text(encoding="utf-8"))), \
            mock.patch.object(core, "emit"):
        r = personalize.run()
        stored = json.loads(prof_path.read_text(encoding="utf-8"))
    check("programs, games and files are counted", r["programs"] >= 6 and r["games"] == 2 and r["files"] == 1234)
    check("the browser and messengers are reported", r["browser"] == "Google Chrome" and "Discord" in r["messengers"])
    check("a part that fails (no key) is reported, the rest still done", any("Русские названия" in f for f in r["failed"]))
    check("the games are kept in the profile, a store like Steam is not a game", stored["games"] == ["Counter-Strike 2", "Minecraft"])
    check("without Yandex Music on the PC the music service is YouTube", saved.get(("music", "service")) == "youtube")
    check("the spoken result is clear", "Изучил компьютер" in personalize.say_result(r) and "Google Chrome" in personalize.say_result(r))
    check("the state says it finished", not personalize.STATE["running"])


def test_the_owner_choice_of_music_is_never_overwritten():
    import personalize
    import pc_profile
    saved = {}
    with mock.patch.object(pc_profile, "PROFILE", _temp_profile(None)), mock.patch.object(pc_profile, "scan", return_value=dict(PROFILE)), \
            mock.patch.dict(sys.modules, {"jarvis_plugin_games": None, "jarvis_plugin_appfinder": None}), \
            mock.patch("pc_index.build", return_value={}), \
            mock.patch.object(core, "save_setting", side_effect=lambda s, k, v: saved.__setitem__((s, k), v)), \
            mock.patch.object(core, "load_json", side_effect=lambda p, d: {"music": {"service": "yandex"}} if "settings" in str(p) else d), \
            mock.patch.object(core, "emit"):
        personalize.run()
    check("a service the owner chose stays", ("music", "service") not in saved)


def test_weather_asks_for_the_city_and_remembers_it():
    w = load_plugin("weather")
    ctx = core.Ctx(text="какая погода", lang="ru", config={"weather": {"city": ""}}, match=None, norm="какая погода")
    with mock.patch.object(w, "_geocode", side_effect=AssertionError("no city must not be looked up")):
        reply = w.weather(ctx)
    check("no city: Jarvis asks instead of guessing one", "мой город" in reply)
    sk = next(s for s in core.SKILLS if s.name == "weather.set_city")
    n = core.normalize("Мой город Самарканд", "ru")
    m = next(p.search(n) for p in sk.patterns["ru"] if p.search(n))
    saved = {}
    with mock.patch.object(w, "_geocode", return_value=(39.6, 66.9, "Самарканд")), \
            mock.patch.object(core, "save_setting", side_effect=lambda s, k, v: saved.__setitem__((s, k), v)):
        reply = w.set_city(core.Ctx(text="Мой город Самарканд", lang="ru", match=m, norm=n))
    check("«мой город Самарканд» is remembered", saved.get(("weather", "city")) == "Самарканд" and "Запомнил" in reply)
    check("the morning line skips the weather without a city", w.short_weather("", "ru") == "")


def test_first_run_studies_the_computer():
    js = (ROOT / "web" / "pages.js").read_text(encoding="utf-8")
    check("the first run has five steps, the last one studies the PC", '"Ваш город", "Ваш компьютер"' in js and "/api/personalize" in js)
    check("the voice step can be skipped (no microphone yet)", 'id="onbSkip"' in js)
    check("Settings can study the PC again", 'id="btnStudy"' in js)
    app = (ROOT / "assistant.py").read_text(encoding="utf-8")
    check("the study has its API, started only from Jarvis's own window", 'web.post("/api/personalize", personalize_post)' in app
          and "_own_page(r)\n        import personalize" in app)
    check("speech recognition uses this PC's names", "initial_prompt=_prompt(lg)" in app)
    scan = (ROOT / "plugins" / "pc_scan.py").read_text(encoding="utf-8")
    check("«изучи мой компьютер» runs the full study", "personalize.run()" in scan)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("stage33: all passed")
