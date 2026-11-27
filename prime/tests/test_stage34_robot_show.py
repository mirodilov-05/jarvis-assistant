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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("stage34: all passed")
