"""Stage 32: the self-presentation, the full history, self-learning from mistakes and the brain's false «не понял».

Every test writes into a temporary folder: the owner's real history, memory and learning store are never touched.
"""
import json
import re
import sys
import tempfile
import threading
import time
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


def _tmp():
    return Path(tempfile.mkdtemp(prefix="jarvis32_"))


# ------------------------------------------------------------------ one path for every channel

def test_every_channel_is_kept_in_the_history():
    tmp = _tmp()
    with mock.patch.object(core, "DATA", tmp), mock.patch.object(core, "HISTORY_FILE", tmp / "history.jsonl"), \
            mock.patch.object(core, "route", return_value="Открываю."), mock.patch.object(core, "_after_turn"), \
            mock.patch.object(core, "_note_correction", return_value=False):
        for src in ("голос", "текст", "телеграм"):
            core.process("открой телеграм", "ru", src)
        rows = [json.loads(x) for x in (tmp / "history.jsonl").read_text(encoding="utf-8").splitlines()]
    check("voice, window and Telegram all reach the saved history", [r["source"] for r in rows] == ["голос", "текст", "телеграм"])
    check("each row keeps the request and the answer", all(r["user"] == "открой телеграм" and r["reply"] for r in rows))
    check("the day log is written too", any(tmp.joinpath("log").glob("*.md")))


def test_a_crash_is_answered_and_still_saved():
    tmp = _tmp()
    with mock.patch.object(core, "DATA", tmp), mock.patch.object(core, "HISTORY_FILE", tmp / "history.jsonl"), \
            mock.patch.object(core, "route", side_effect=RuntimeError("сломалось")), mock.patch.object(core, "_after_turn"), \
            mock.patch.object(core, "_note_correction", return_value=False):
        reply = core.process("сделай что-нибудь", "ru", "текст")
        rows = (tmp / "history.jsonl").read_text(encoding="utf-8").splitlines()
    check("a crash in a skill gets a readable answer", reply.startswith("Не получилось"))
    check("and the request is not lost", len(rows) == 1)


def test_telegram_paths_go_through_the_common_path():
    bot = (ROOT / "remote_bot.py").read_text(encoding="utf-8")
    saved = (ROOT / "plugins" / "tgsetup.py").read_text(encoding="utf-8")
    check("the Telegram bot answers through core.process", "core.process(text" in bot and "core.route(text" not in bot)
    check("«Избранное» answers through core.process", "core.process(cmd" in saved and "core.route(cmd" not in saved)
    app = (ROOT / "assistant.py").read_text(encoding="utf-8")
    check("the window's history is the saved file, not this session's events", '"history": core.read_history(80)' in app)
    pages = (ROOT / "web" / "pages.js").read_text(encoding="utf-8")
    check("the History tab reads /api/history", "/api/history?limit=" in pages)


# ------------------------------------------------------------------ self-learning

def test_a_failure_is_noted_and_a_rephrasing_is_learned():
    from learning import autolearn, store
    db = _tmp() / "learn.db"
    autolearn._LAST_FAIL.update(text="", reply="", at=0.0)
    r1 = autolearn.observe("самопрезентуй себя подробно", "Не понял, что именно сделать, сэр.", now=100.0, path=db)
    r2 = autolearn.observe("сделай самопрезентацию", "", skill="show.about", now=130.0, path=db)
    check("a failed answer is stored as a mistake at once", r1 == "mistake"
          and store.recent_feedback(10, db)[0]["comment"].startswith("сам"))
    check("the rephrasing that worked is learned", r2 == "learned")
    check("next time the first wording means the second", autolearn.resolve("Джарвис, самопрезентуй себя подробно!", db) == "сделай самопрезентацию")
    check("a lesson is written for the brain too", any("самопрезентуй" in x["trigger_text"] for x in store.lessons(10, db)))
    gone = autolearn.forget_last(db)
    check("«забудь последнее обучение» removes it", gone and autolearn.resolve("самопрезентуй себя подробно", db) is None)


def test_nothing_is_learned_from_unrelated_or_late_or_one_word_phrases():
    from learning import autolearn
    db = _tmp() / "learn.db"
    autolearn._LAST_FAIL.update(text="", reply="", at=0.0)
    autolearn.observe("абстером не понял повтори", "Не понял, повторите, пожалуйста.", now=0.0, path=db)
    check("an unrelated next command is not linked", autolearn.observe("открой дискорд", "Запускаю discord.", skill="apps.open", now=20.0, path=db) == "")
    autolearn.observe("включи телик в зале", "Не понял.", now=0.0, path=db)
    check("too late (after two minutes) is not linked", autolearn.observe("включи телевизор", "Готово.", skill="prime.tv", now=500.0, path=db) == "")
    autolearn.observe("угу", "Не понял, повторите, пожалуйста.", now=0.0, path=db)
    check("a one-word fragment is never learned", autolearn.observe("угу давай", "Хорошо.", skill="x", now=5.0, path=db) == "")
    check("no wording was learned at all", autolearn.aliases(10, db) == [])


def test_the_router_uses_a_learned_wording():
    hit = []
    fake = types.SimpleNamespace(name="weather.now", priority=1, patterns={"ru": [re.compile(r"^какая погода$")]},
                                 handler=lambda ctx: hit.append(ctx.text) or "Солнечно.")
    with mock.patch.object(core, "SKILLS", [fake]), mock.patch("learning.autolearn.resolve",
                                                               side_effect=lambda t: "какая погода" if "небе" in t else None):
        reply = core.route("что там на небе сегодня", "ru", "текст", {})
    check("a learned wording runs the command it means", reply == "Солнечно." and hit == ["какая погода"])


def test_reflection_catches_up_when_the_laptop_slept_at_night():
    import datetime as dt
    from learning import reflection
    with mock.patch.object(reflection, "_state", return_value={"day": "2000-01-01"}):
        check("at 10:00 a missed night is caught up", reflection.due_now(dt.datetime(2026, 11, 28, 10, 0)))
        check("before 02:30 it waits", not reflection.due_now(dt.datetime(2026, 11, 28, 1, 0)))
    with mock.patch.object(reflection, "_state", return_value={"day": "2026-11-28"}):
        check("only once a day", not reflection.due_now(dt.datetime(2026, 11, 28, 15, 0)))


# ------------------------------------------------------------------ the brain

def test_a_long_answer_about_himself_is_not_a_false_claim():
    import agent
    about = "Я умею открывать программы, включаю музыку, ставлю напоминания, управляю телевизором и читаю почту. " * 2
    check("a long explanation is not taken for a claimed action", not agent._claims_action("какие у тебя функции", about))
    check("a question about himself is never a claimed action", not agent._claims_action("что ты умеешь", "Включаю музыку и открываю программы."))
    check("a short «Открываю телеграм.» without a tool still is", agent._claims_action("телегу", "Открываю телеграм."))
    src = (ROOT / "agent.py").read_text(encoding="utf-8")
    check("the action line is not repeated", src.count('core.LAST_ACTION.update(skill="", tools=", ".join(n for n, _ in calls))') == 1)
    check("«подробно» lifts the three-sentence limit", bool(agent._DETAILED.search("подробно объясни")))


def test_what_can_you_do_is_a_short_spoken_summary():
    basics = load_plugin("basics")
    sk = next(s for s in core.SKILLS if s.name == "basics.help")
    norm = core.normalize("Какие функции у тебя есть?", "ru")
    check("«Какие функции у тебя есть» is understood", any(p.search(norm) for p in sk.patterns["ru"]))
    reply = basics.help_skill(core.Ctx(text="что ты умеешь", lang="ru", source="голос"))
    check("the voice answer is a summary, not a list of skill titles", "самопрезентация" in reply and "Запоминать, какими" not in reply)


# ------------------------------------------------------------------ the presentation

def _show_with_fake_voice():
    from cognition import show
    said = []
    busy = {"until": 0.0}

    def speak(text, lang):
        said.append((text, lang))
        busy["until"] = time.time() + 0.05
    patches = [mock.patch.object(core, "_speak_fn", speak), mock.patch.object(core, "_stop_fn", lambda: busy.update(until=0.0)),
               mock.patch.object(core, "_busy_fn", lambda: time.time() < busy["until"]),
               mock.patch.object(show, "_deck", lambda deck, lang: [{"title": f"{deck}{i}", "say": f"{lang} слайд {i}"} for i in range(3)]),
               mock.patch.object(show, "MIN_SLIDE_S", 0.05), mock.patch.object(show, "PAUSE_S", 0.02),
               mock.patch.object(core, "emit")]
    return show, said, patches


def test_auto_presentation_reads_each_slide_once_in_order():
    show, said, patches = _show_with_fake_voice()
    for p in patches:
        p.start()
    try:
        show.start("ja", "about", auto=True)
        end = time.time() + 5
        while show.public()["auto"] and time.time() < end:
            time.sleep(0.02)
        check("every slide is read once, in order, without repeats", [t for t, _ in said] == ["ja слайд 0", "ja слайд 1", "ja слайд 2"])
        check("in the chosen language", all(lg == "ja" for _, lg in said))
        check("it stops on the last slide", show.public()["i"] == 2 and not show.public()["auto"])
    finally:
        show.stop()
        for p in patches:
            p.stop()


def test_manual_steps_and_the_screen_agree():
    show, said, patches = _show_with_fake_voice()
    for p in patches:
        p.start()
    try:
        show.start("ru", "report", auto=False)
        check("a silent start does not talk", said == [])
        st = show.step(1)
        check("a button step moves the one shared position", st["i"] == 1 and show.public()["i"] == 1)
        show.step(1, speak=True)
        check("a voice step reads the new slide, not the old one", said == [("ru слайд 2", "ru")])
        st = show.switch("en")
        check("a language switch keeps the slide", st["i"] == 2 and st["lang"] == "en")
        check("the screen gets every slide to draw", len(show.public()["slides"]) == 3)
        show.stop()
        check("stop ends it for the screen too", not show.public()["active"])
    finally:
        show.stop()
        for p in patches:
            p.stop()


def test_voice_commands_of_the_presentation():
    cog = load_plugin("cognition")
    by = {s.name: s for s in core.SKILLS}

    def hits(name, phrase):
        n = core.normalize(phrase, "ru")
        return any(p.search(n) for p in by[name].patterns["ru"])
    check("«Сделай самопрезентацию» starts it", hits("show.about", "Сделай самопрезентацию."))
    check("«Ты можешь самопрезентовать себя…» starts it", hits("show.about", "Ты можешь самопрезентовать себя, что ты умеешь и так далее. Подробно объясни."))
    check("«расскажи о себе на японском» starts it", hits("show.about", "Расскажи о себе на японском"))
    check("«сохрани самопрезентацию в аудиофайл» is understood", hits("show.about", "Сохрани самопрезентацию в аудиофайл на японском"))
    check("«сделай презентацию про котов» is not taken", not hits("show.about", "сделай презентацию про котов в PowerPoint"))
    check("the language is taken from the phrase", cog._lang_of("на японском") == "ja" and cog._lang_of("на английском языке") == "en")
    check("long self-presentation phrases are allowed", "show.about" in core._LONG_OK)
    with mock.patch.object(cog.show, "public", return_value={"active": False}):
        ctx = core.Ctx(text="дальше", lang="ru", norm="дальше")
        check("«дальше» without a presentation stays the music command", cog.show_next(ctx) is None)
        ctx = core.Ctx(text="пауза", lang="ru", norm="пауза", match=re.match(r"(?P<a>пауза)", "пауза"))
        check("«пауза» without a presentation stays the music command", cog.show_play(ctx) is None)


def test_the_about_deck_is_complete_in_three_languages():
    import hud_data
    for lang in ("ru", "en", "ja"):
        d = hud_data.about_deck(lang)
        check(f"{lang}: twelve slides, each with a title, a headline and a spoken text",
              len(d) == 12 and all(s.get("title") and s.get("big") and s.get("say") for s in d))
    ru = " ".join(s["say"] for s in hud_data.about_deck("ru"))
    check("the Russian text is about Jarvis himself", "Меня зовут Джарвис" in ru and "учусь" in ru)
    ja = "".join(s["say"] for s in hud_data.about_deck("ja"))
    check("the Japanese text is Japanese", "ジャービス" in ja and not re.search(r"[а-яА-Я]", ja))


def test_the_presentation_api_and_screen_are_wired():
    app = (ROOT / "assistant.py").read_text(encoding="utf-8")
    check("GET /api/show exists", 'web.get("/api/show", show_get)' in app)
    check("the audio file can be downloaded, only by its own name", "jarvis_(?:about|report)_(?:ru|en|ja)\\.mp3" in app)
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    check("the screen follows the server, not its own counter", "applyShow(" in js and "SL.i = Math.min" not in js)
    check("the screen buttons drive the server", 'showOp("next")' in js and 'showOp("prev")' in js)


# ------------------------------------------------------------------ failures found in the owner's own history

def test_focus_shield_closes_store_apps_and_owner_words():
    import pcx
    with mock.patch.object(core, "setting", side_effect=lambda s, k, d=None: "discord" if (s, k) == ("focus", "extra") else d):
        check("the Instagram app from the Store is a distraction", pcx._distracting("Instagram", "ApplicationFrameHost.exe"))
        check("an app named Instagram.exe is a distraction", pcx._distracting("Лента", "Instagram.exe"))
        check("an Instagram tab in a browser is a distraction", pcx._distracting("(3) Instagram", "browser.exe"))
        check("a word the owner added counts too", pcx._distracting("Discord", "Discord.exe"))
        check("Word is not a distraction", not pcx._distracting("Отчёт.docx - Word", "WINWORD.EXE"))
    v3 = load_plugin("v3_skills")
    sk = next(s for s in core.SKILLS if s.name == "v3.focus_add")
    for phrase, word in [("Добавь режим фокуса, закрыть Instagram тоже.", "instagram"), ("Закрывай инстаграм в режиме фокуса", "инстаграм")]:
        n = core.normalize(phrase, "ru")
        m = next((p.search(n) for p in sk.patterns["ru"] if p.search(n)), None)
        check(f"«{phrase}» adds {word} to the focus shield", bool(m) and word in m.group("w"))
    check("the focus list command takes long phrases", "v3.focus_add" in core._LONG_OK and v3 is not None)


def test_open_several_programs_in_one_phrase():
    apps = load_plugin("apps")
    opened = []
    with mock.patch.object(apps, "open_target", side_effect=lambda ctx, t: opened.append(t) or f"Запускаю {t}."):
        ctx = core.Ctx(text="Открой Counter-Strike, Discord и Telegram", lang="ru",
                       match=re.match(r"(.+)", "counter strike discord и telegram"))
        apps.open_app(ctx)
    check("«открой A, B и C» opens all three", opened == ["counter strike", "discord", "telegram"])


def test_music_on_the_tv_is_not_an_app_name():
    load_plugin("tv_media")
    sk = next(s for s in core.SKILLS if s.name == "tv.media")
    for phrase in ("Поставь музыку в телевизоре.", "Запусти музыку в телевизор", "Включи Imagine Dragons на телевизоре"):
        n = core.normalize(phrase, "ru")
        check(f"«{phrase}» is music on the TV", any(p.search(n) for p in sk.patterns["ru"]))
    tv_skill = next((s for s in core.SKILLS if s.name == "prime.tv"), None)
    check("music on the TV is tried before the TV app table", tv_skill is None or sk.priority < tv_skill.priority)


def test_telegram_login_errors_are_plain_russian():
    tg = load_plugin("telegram")
    SendCodeUnavailableError = type("SendCodeUnavailableError", (Exception,), {})
    FloodWaitError = type("FloodWaitError", (Exception,), {"seconds": 600})
    check("«all code options used» becomes advice in Russian", "чат «Telegram»" in tg.explain(SendCodeUnavailableError("Returned when all available options")))
    check("a flood wait says how long to wait", "10 мин" in tg.explain(FloodWaitError("x")))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("stage32: all passed")
    threading.Event().wait(0.1)
