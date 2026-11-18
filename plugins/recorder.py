"""Voice recorder: "Джарвис, запись" -> records everything (audio file) until you
say "стоп" -> saves data/recordings/<date>.wav plus a text transcript (.txt).
Also from the app (Записи tab). Different from dictation, which saves only text.
"""

import core
from core import Ctx, skill


@skill(
    "recorder.start",
    title={"ru": "Запись голоса (до слова «стоп»)", "uz": "Ovozni yozib olish («to'xtat» gacha)"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:запись|начни запись|включи запись|начать запись|включи диктофон|диктофон|"
               r"запиши (?:голос|звук|аудио|разговор|встречу|лекцию|меня)|записывай)$"],
        "uz": [r"^(?:jarvis )?(?:yozuv|yozib ol|ovoz yoz\w*|diktofon\w*|yozishni boshla|yozib olishni boshla)$"],
    },
    examples={"ru": ["Запись", "Включи диктофон", "Запиши встречу"], "uz": ["Yozib ol", "Diktofonni yoq"]},
    priority=6,
)
def start(ctx: Ctx) -> str:
    core.RECORD_LANG["lang"] = ctx.lang
    core.RECORD_STOP.clear()
    core.RECORD_REQUEST.set()
    if ctx.source == "голос":
        return ""  # the recorder itself announces the start
    return ctx.t("Начинаю запись. Скажите «стоп» или нажмите «Остановить».", "Yozib olish boshlandi.")


@skill(
    "recorder.list",
    title={"ru": "Мои записи", "uz": "Yozuvlarim"},
    patterns={"ru": [r"(какие|покажи|мои|сколько) (у меня )?(записи|записей)"], "uz": [r"yozuvlarim"]},
    examples={"ru": ["Покажи мои записи"], "uz": ["Yozuvlarim"]},
    priority=7,
)
def list_records(ctx: Ctx) -> str:
    files = sorted((core.DATA / "recordings").glob("*.wav"), reverse=True) if (core.DATA / "recordings").exists() else []
    if not files:
        return ctx.t("Записей пока нет. Скажите «запись», чтобы начать.", "Hozircha yozuvlar yo'q.")
    names = ", ".join(f.stem.replace("_", " ") for f in files[:5])
    return ctx.t(f"Записей: {len(files)}. Последние: {names}. Слушать их можно в окне Джарвиса, вкладка «Записи».",
                 f"Yozuvlar: {len(files)} ta. Oxirgilari: {names}.")
