"""TEMPLATE for a new Jarvis skill / Yangi ko'nikma uchun SHABLON.

How to add a new ability:
  1. Copy this file to plugins/<your_name>.py  (names starting with "_" are ignored).
  2. Write regex patterns for Russian ("ru") and Uzbek ("uz").
     Text is matched in lowercase without punctuation; Uzbek is Latin without
     apostrophes ("qo'sh" -> "qosh", "ko'rsat" -> "korsat").
  3. Return the reply text. Use ctx.t("по-русски", "o'zbekcha") to answer in the
     user's language. Return None to let other skills handle the phrase.
  4. Say "Перезагрузи навыки" / "Ko'nikmalarni qayta yukla" (or restart Jarvis).
     The new skill also appears in CAPABILITIES.md and in "Что ты умеешь?".

Useful things from core:
  ctx.text / ctx.norm / ctx.lang ("ru"/"uz") / ctx.source ("голос"/"текст")
  ctx.group(1)            - regex group from your pattern
  ctx.cfg("section")      - a [section] from config.toml
  ctx.say("...")          - speak immediately (e.g. "Ищу...")
  core.DATA               - folder for your files; core.load_json / core.save_json
  core.speak(text, lang)  - speak from a background thread
  @core.on_start          - run a background function when Jarvis starts
  core.parse_number("двадцать пять") -> 25

Example below: "Подбрось монетку" / "Tanga tashla".
"""

import random

from core import Ctx, skill


@skill(
    "example.coin",                                    # unique id
    title={"ru": "Подбросить монетку", "uz": "Tanga tashlash"},
    patterns={
        "ru": [r"(подбрось|кинь|брось) монет"],
        "uz": [r"tanga (tashla|ot)"],
    },
    examples={"ru": ["Подбрось монетку"], "uz": ["Tanga tashla"]},
    priority=50,                                       # lower = checked earlier
)
def coin(ctx: Ctx) -> str:
    heads = random.random() < 0.5
    return ctx.t("Орёл!" if heads else "Решка!", "Gerb!" if heads else "Raqam!")
