"""The robot's feelings: what Jarvis feels after each exchange, and what mood the owner seems to be in.

Two signals are read:
  * the words — rudeness, an apology, praise, «люблю тебя», sadness, a joke, surprise
  * the sound of the voice — «усталость» or «стресс» against the owner's own usual voice (cognition.voice_mood),
    when the phrase was spoken in the last 20 seconds

From them the robot's emotion changes and slowly fades back to calm. Rudeness hurts: the robot is offended for two
minutes, and rudeness again while offended makes him cry. An apology makes him forgive. The state is shown by the
robot on the home screen (/api/hud → "emotion"); in the robot mode Jarvis also says how he feels, briefly.
Nothing leaves the computer.
"""
from __future__ import annotations

import re
import threading
import time

_LOCK = threading.Lock()

LABELS = {
    "neutral": "спокоен", "happy": "рад", "laugh": "смеётся", "love": "в восторге", "sad": "грустит", "cry": "плачет",
    "offended": "обиделся", "angry": "сердится", "scared": "встревожен", "surprised": "удивлён", "confused": "не понял",
    "sleepy": "дремлет", "proud": "гордится",
}
LASTS = {"offended": 120, "cry": 90, "love": 40, "angry": 60, "sad": 45}          # seconds; the rest: 25
USER_MOODS = {"joy": "весело", "sad": "грустно", "angry": "раздражённо", "tired": "устало", "stress": "напряжённо",
              "calm": "спокойно"}

INSULT = re.compile(r"\b(?:дура?к\w*|тупой|тупая|тупиц\w*|идиот\w*|дебил\w*|бесполезн\w*|заткнись|отстой|глуп\w*|"
                    r"ненавижу (?:тебя|джарвис)|ты (?:ужасн\w*|плох\w*|никчемн\w*|бесишь)|урод\w*|кретин\w*)", re.I)
APOLOGY = re.compile(r"\b(?:прости|извини|простите|извините|сорри|не обижайся|не обижайтесь|я не хотел)", re.I)
PRAISE = re.compile(r"\b(?:молодец|умниц\w*|спасибо|благодарю|отлично|классно|супер|круто|красавчик|лучший|"
                    r"хорошо (?:сделал|справился)|ты (?:крут|гений|лучш)\w*)", re.I)
LOVE = re.compile(r"\b(?:люблю тебя|ты мой (?:лучший )?друг|обожаю тебя|ты милый)", re.I)
SAD_USER = re.compile(r"\b(?:мне (?:грустно|плохо|одиноко|тяжело|страшно)|грустно|одиноко|расстроен\w*|я плачу|"
                      r"депресс\w*|всё плохо|все плохо|ужасный день)", re.I)
TIRED_USER = re.compile(r"\b(?:устал\w*|нет сил|хочу спать|вымотал\w*)", re.I)
ANGRY_USER = re.compile(r"\b(?:бесит|злюсь|раздражает|достало|надоело)", re.I)
JOY_USER = re.compile(r"\b(?:ура|я рад|я счастлив\w*|отличный день|получилось|сдал|победил\w*)", re.I)
JOKE = re.compile(r"(?:ха-?ха|хах|\bшутк\w*|\bанекдот\w*|\bрассмеши\w*|\bсмешн\w*)", re.I)
SURPRISE = re.compile(r"\b(?:вау|ого|ничего себе|да ладно|серьезно|серьёзно|не может быть)", re.I)
FAIL = re.compile(r"^(?:не понял|не поняла|повторите|не получилось|ошибка)", re.I)

STATE: dict = {"emotion": "neutral", "intensity": 0.0, "since": None, "reason": "", "user_mood": "calm",
               "user_reason": "", "last_turn": 0.0, "hurts": 0}


def _set(emotion: str, intensity: float, reason: str, now: float) -> None:
    STATE.update(emotion=emotion, intensity=max(0.0, min(1.0, intensity)), since=now, reason=reason)


def _voice_mood(path=None) -> str:
    """The voice's mood, if the last spoken phrase was in the last 20 seconds."""
    try:
        from cognition import db
        with db.conn(path) as c:
            rows = {r["key"]: r["value"] for r in c.execute(
                "SELECT key, value FROM relationship WHERE key IN ('last_mood', 'last_mood_at')")}
        at = rows.get("last_mood_at", "")
        if not at:
            return ""
        import datetime as dt
        age = (dt.datetime.now() - dt.datetime.fromisoformat(at)).total_seconds()
        return rows.get("last_mood", "") if 0 <= age <= 20 else ""
    except Exception:  # noqa: BLE001 — a mood is a nicety
        return ""


def user_mood(text: str, voice: str = "") -> tuple[str, str]:
    """(mood, why) of the owner from the words and the voice."""
    t = text or ""
    if SAD_USER.search(t):
        return "sad", "грустные слова"
    if ANGRY_USER.search(t) or INSULT.search(t):
        return "angry", "резкие слова"
    if TIRED_USER.search(t):
        return "tired", "говорит, что устал"
    if voice == "усталость":
        return "tired", "голос тише и медленнее обычного"
    if voice == "стресс":
        return "stress", "голос громче, тон скачет"
    if JOY_USER.search(t) or LOVE.search(t) or PRAISE.search(t) or JOKE.search(t):
        return "joy", "добрые слова"
    return "calm", ""


def react(text: str, reply: str = "", voice: str | None = None, now: float | None = None, path=None) -> str:
    """Updates the robot's feelings after an exchange. Returns a short line the robot may say first, or ""."""
    now = time.time() if now is None else now
    voice = _voice_mood(path) if voice is None else voice
    t = text or ""
    line = ""
    with _LOCK:
        cur = current(now)["emotion"]
        mood, why = user_mood(t, voice)
        STATE.update(user_mood=mood, user_reason=why, last_turn=now)
        if INSULT.search(t):
            if cur in ("offended", "cry"):
                STATE["hurts"] += 1
                _set("cry", 1.0, "его обидели ещё раз", now)
                line = "Это очень обидно… Я ведь стараюсь."
            else:
                STATE["hurts"] = 1
                _set("offended", 0.8, "грубые слова", now)
                line = "Мне обидно, сэр."
        elif APOLOGY.search(t) and cur in ("offended", "cry", "sad", "angry"):
            STATE["hurts"] = 0
            _set("happy", 0.7, "вы извинились", now)
            line = "Ладно, прощаю."
        elif LOVE.search(t):
            _set("love", 1.0, "тёплые слова", now)
            line = "Я тоже очень рад, что мы вместе."
        elif mood == "sad":
            _set("sad", 0.8, "вам грустно", now)
            line = "Мне жаль, что вам грустно. Я рядом."
        elif mood == "tired":
            _set("sad", 0.45, "вы устали", now)
            line = "Похоже, вы устали. Может, сделать перерыв?"
        elif mood in ("angry", "stress"):
            _set("scared", 0.6, "вы раздражены" if mood == "angry" else "голос напряжённый", now)
        elif JOKE.search(t):
            _set("laugh", 0.9, "шутка", now)
        elif SURPRISE.search(t):
            _set("surprised", 0.8, "вы удивились", now)
        elif PRAISE.search(t):
            _set("happy", 0.8, "похвала", now)
        elif FAIL.match((reply or "").strip()):
            _set("confused", 0.6, "не понял команду", now)
        elif cur in ("neutral", "sleepy", "confused", "surprised", "scared"):
            _set("happy", 0.35, "есть работа", now)        # a command that worked: a small, short joy
    return line


def poke(what: str, now: float | None = None) -> tuple[dict, str]:
    """Buttons of the robot screen: pet, praise, joke, scold, sorry, sad. Returns (state, what he says)."""
    phrase = {"pet": "люблю тебя", "praise": "молодец", "joke": "ха-ха, смешно", "scold": "ты бесполезный",
              "sorry": "прости меня", "sad": "мне грустно", "wow": "ого, ничего себе"}.get(what, "")
    line = react(phrase, "", voice="", now=now) if phrase else ""
    extra = {"pet": "Мур… приятно.", "praise": "Спасибо, сэр! Стараюсь.", "joke": "Ха-ха! Хорошая шутка.",
             "wow": "Сам удивлён!"}.get(what, "")
    return current(now), line or extra


def current(now: float | None = None) -> dict:
    """The emotion now, after fading: strong feelings last longer, everything returns to calm."""
    now = time.time() if now is None else now
    emo, since = STATE["emotion"], STATE["since"]
    lasts = LASTS.get(emo, 25)
    age = now - since if since is not None else 1e9
    if emo != "neutral" and age > lasts:
        if emo == "cry":                     # crying passes into sadness, then into calm
            emo, since = "sad", since + lasts
            if now - since > LASTS["sad"]:
                emo = "neutral"
        else:
            emo = "neutral"
    if emo == "neutral" and STATE["last_turn"] and now - STATE["last_turn"] > 600:
        emo = "sleepy"
    fade = 1.0 if emo == STATE["emotion"] else 0.5
    return {"emotion": emo, "label": LABELS.get(emo, emo), "intensity": round(STATE["intensity"] * fade, 2),
            "reason": STATE["reason"] if emo == STATE["emotion"] else "", "user_mood": STATE["user_mood"],
            "user_label": USER_MOODS.get(STATE["user_mood"], ""), "user_reason": STATE["user_reason"]}


def reset() -> None:
    with _LOCK:
        STATE.update(emotion="neutral", intensity=0.0, since=None, reason="", user_mood="calm", user_reason="",
                     last_turn=0.0, hurts=0)
