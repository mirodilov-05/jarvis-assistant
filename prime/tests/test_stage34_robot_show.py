"""Stage 34: the robot's feelings, the twelve-slide talk, and speech cut into sentences for the Microsoft voices."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    assert ok, name


def test_rudeness_hurts_and_an_apology_heals():
    from cognition import emotion as e
    e.reset()
    e.react("ты тупой", "", voice="", now=100)
    check("rudeness offends him", e.current(101)["emotion"] == "offended")
    e.react("ты бесполезный", "", voice="", now=105)
    check("rudeness again makes him cry", e.current(106)["emotion"] == "cry")
    check("the owner seems irritated", e.current(106)["user_mood"] == "angry")
    line = e.react("прости меня", "", voice="", now=110)
    check("an apology: he forgives", e.current(111)["emotion"] == "happy" and "прощаю" in line)
    e.react("мне грустно", "", voice="", now=200)
    check("your sadness makes him sad", e.current(201)["emotion"] == "sad")
    e.react("сделай громче", "", voice="усталость", now=300)
    check("a tired voice is heard", e.current(301)["user_mood"] == "tired")
    check("feelings fade back to calm", e.current(300 + 400)["emotion"] == "neutral")
    check("after ten quiet minutes he dozes", e.current(300 + 700)["emotion"] == "sleepy")
    e.reset()


def test_the_talk_has_twelve_slides_in_three_languages():
    import presentation
    n = dict(skills=222, tools=67, commands=131, lessons=2, learned=1, tests=34)
    kinds = None
    for lang in ("ru", "en", "ja"):
        d = presentation.deck(lang, n)
        check(f"{lang}: twelve slides with a headline and a spoken text", len(d) == 12 and all(s["big"] and s["say"] for s in d))
        k = [s["kind"] for s in d]
        kinds = kinds or k
        check(f"{lang}: the same layouts in the same order", k == kinds)
    check("each idea has its own layout", len(set(kinds)) >= 10)
    ja = " ".join(s["say"] for s in presentation.deck("ja", n))
    check("the Japanese talk has no Russian letters", not re.search(r"[а-яА-Я]", ja))
    ru = presentation.deck("ru", n)[9]["say"]
    check("Russian numbers agree", "222 навыка" in ru and "131 команда уже выполнена" in ru)


def test_speech_is_cut_into_sentences():
    src = (ROOT / "assistant.py").read_text(encoding="utf-8")
    start, end = src.index("_SENT_END"), src.index("class Speaker")
    ns = {"re": re}
    exec(src[start:end], ns)
    parts = ns["_sentences"]("一つ目です。" * 30, 90)
    check("a long Japanese text becomes short pieces", len(parts) > 1 and all(len(p) <= 180 for p in parts))
    check("nothing is lost", "".join(parts).replace(" ", "") == "一つ目です。" * 30)
    check("no fixed 6-second limit for the whole text any more", "timeout = 1.5 if lang == \"ru\" else 6" not in src)
    check("English and Japanese never fall back to the Russian voice", "_sapi_lang(" in src)


def test_five_capsule_looks_move_with_the_voice():
    import tray

    class Canvas:                     # records what would be drawn
        def __init__(self):
            self.items = []

        def delete(self, *_):
            self.items = []

        def __getattr__(self, name):
            return lambda *a, **k: self.items.append((name, a))
    check("five looks of the capsule", tray.STYLES == ("wave", "orb", "pulse", "scanner", "dots"))
    for style in tray.STYLES:
        c = Canvas()
        tray.draw_style(c, style, 62, 26, 0.4, 0.9, "speaking", "#78aaff")
        check(f"{style}: draws its sign", len(c.items) > 0)
    loud, quiet = Canvas(), Canvas()
    tray.draw_style(loud, "wave", 62, 26, 0.4, 1.0, "speaking", "#78aaff")
    tray.draw_style(quiet, "wave", 62, 26, 0.4, 0.05, "speaking", "#78aaff")
    height = lambda cv: sum(a[3] - a[1] for n, a in cv.items if n == "create_rectangle")  # noqa: E731
    check("the wave bars grow with a louder voice", height(loud) > height(quiet) * 2)
    check("integer coordinates: crisp bars", all(all(isinstance(v, int) for v in a[:4]) for n, a in loud.items if n == "create_rectangle"))
    js = (ROOT / "web" / "pages.js").read_text(encoding="utf-8")
    check("Settings has the capsule section with the five looks", '["capsule", "Мини-капсула"' in js and "capsule_style" in js)


def test_a_new_laptop_hears_its_name_without_a_key_or_nvidia():
    src = (ROOT / "assistant.py").read_text(encoding="utf-8")
    check("NVIDIA is detected, not assumed", "ctranslate2.get_cuda_device_count()" in src and 'return "cuda" if want == "cuda" and has_cuda() else "cpu"' in src)
    check("on the processor the main model is the light one", 'cfg("voice", "whisper_model_cpu", "small")' in src)
    check("the name is checked by the tiny model without a key on the processor",
          'use_tiny = cfg("cloud", "local_spotting", True) and (cloud.stt_enabled() or stt_device() == "cpu")' in src)
    inst = (ROOT / "install.ps1").read_text(encoding="utf-8")
    check("the installer downloads the speech models in advance", 'download_model as d; [d(m) for m in ("tiny", "small")]' in inst)
    js = (ROOT / "web" / "pages.js").read_text(encoding="utf-8")
    check("Settings → Голос shows the microphone live and what to fix", "Слышит ли меня Джарвис" in js and "Разрешить классическим приложениям" in js)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("stage34: all passed")
