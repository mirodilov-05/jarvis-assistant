"""Voice ID: "запомни мой голос" (≈20 s of speech), "забудь мой голос", "ты узнаёшь мой голос?".

After enrollment Jarvis reacts only to the owner's voice (feature «Слушаться только моего голоса»; stricter in
games) and can be interrupted by voice while it talks (feature «Перебивать голосом»).
"""

import core
from core import Ctx, ask_confirm, skill


@skill(
    "voice_id.enroll",
    title={"ru": "Запомнить мой голос (Джарвис будет слушаться только вас)"},
    patterns={"ru": [r"(?:запомни|выучи|запиши|узнай|настрой)(?: заново)? (?:мой голос|меня по голосу|голос хозяина)"]},
    examples={"ru": ["Запомни мой голос"]},
    priority=5,
)
def enroll(ctx: Ctx) -> str:
    core.ENROLL_REQUEST.set()
    if ctx.source == "голос":
        return ""   # the listener explains what to do and starts at once
    return "Хорошо. Скажите что-нибудь вслух секунд двадцать — я запомню ваш голос."


@skill(
    "voice_id.forget",
    title={"ru": "Забыть мой голос"},
    patterns={"ru": [r"(?:забудь|удали|сотри) (?:мой голос|отпечаток голоса|голос хозяина)"]},
    examples={"ru": ["Забудь мой голос"]},
    priority=5,
)
def forget(ctx: Ctx) -> str:
    import voiceprint
    if not voiceprint.enrolled():
        return "Я и так не запоминал ваш голос."

    def do() -> str:
        voiceprint.forget()
        core.emit({"type": "settings"})
        return "Забыл. Теперь снова отвечаю любому голосу."

    return ask_confirm(ctx, "Забыть ваш голос? Тогда я буду отвечать любому голосу. Скажите да или нет.", do)


@skill(
    "voice_id.status",
    title={"ru": "Узнаёшь ли ты мой голос"},
    patterns={"ru": [r"(?:ты )?(?:узнаешь|знаешь|помнишь) мой голос", r"кто (?:я|с тобой говорит)"]},
    examples={"ru": ["Ты узнаёшь мой голос?"]},
    priority=6,
)
def status(ctx: Ctx) -> str:
    import voiceprint
    score = core.CONFIG.get("_last_voice_score")
    if not voiceprint.enrolled():
        return "Пока нет. Скажите «Запомни мой голос», и я буду слушаться только вас."
    if score is None:
        return "Ваш голос я помню."
    return f"Да, это вы. Сходство голоса {round(score * 100)} процентов." if score >= voiceprint.LENIENT \
        else f"Голос похож только на {round(score * 100)} процентов. Можно сказать «Запомни мой голос заново»."
