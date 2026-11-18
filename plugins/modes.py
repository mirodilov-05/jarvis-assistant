"""Conversation modes and personal profile.

work   — "Режим работа": strictly on topic, clear and short, no small talk.
friend — "Режим друг": warm, informal, keeps the conversation going.
polite — "Вежливый режим": courteous, "Вы" and "сэр".
"""

import core
from core import Ctx, skill

_SAY = {
    "work": {"ru": "Рабочий режим. Только по делу.", "uz": "Ish rejimi. Faqat ish bo'yicha."},
    "friend": {"ru": "Дружеский режим включён! Давай поболтаем.", "uz": "Do'stona rejim yoqildi! Gaplashamiz."},
    "polite": {"ru": "Вежливый режим включён. К Вашим услугам, сэр.", "uz": "Hurmatli rejim yoqildi. Xizmatingizdaman, janob."},
}


def _set(ctx: Ctx, m: str) -> str:
    core.save_setting("assistant", "mode", m)
    return _SAY[m][ctx.lang]


@skill(
    "modes.work",
    title={"ru": "Режим «Работа»: кратко и по теме", "uz": "«Ish» rejimi: qisqa va aniq"},
    patterns={"ru": [r"(режим работ\w*|рабочий режим|деловой режим|режим работа|давай по делу|включи режим работы)"],
              "uz": [r"(ish rejim\w*|ishchan rejim)"]},
    examples={"ru": ["Режим работа", "Давай по делу"], "uz": ["Ish rejimi"]},
    priority=1,
)
def work(ctx: Ctx) -> str:
    return _set(ctx, "work")


@skill(
    "modes.friend",
    title={"ru": "Режим «Друг»: дружеский разговор", "uz": "«Do'st» rejimi: samimiy suhbat"},
    patterns={"ru": [r"(режим друг\w*|дружеский режим|давай как друзья|будь (мне )?другом|режим общения|давай поболтаем)"],
              "uz": [r"(dost rejim\w*|dostona rejim|dostdek gaplash)"]},
    examples={"ru": ["Режим друг", "Давай поболтаем"], "uz": ["Do'st rejimi"]},
    priority=1,
)
def friend(ctx: Ctx) -> str:
    return _set(ctx, "friend")


@skill(
    "modes.polite",
    title={"ru": "Режим «Вежливый»: учтиво, на «Вы»", "uz": "«Hurmatli» rejim: odobli, «Siz» bilan"},
    patterns={"ru": [r"(вежливый режим|режим вежлив\w*|официальный режим|будь вежлив\w*)"],
              "uz": [r"(hurmatli rejim|odobli rejim|rasmiy rejim)"]},
    examples={"ru": ["Вежливый режим"], "uz": ["Hurmatli rejim"]},
    priority=1,
)
def polite(ctx: Ctx) -> str:
    return _set(ctx, "polite")


@skill(
    "modes.which",
    title={"ru": "Какой сейчас режим", "uz": "Hozir qaysi rejim"},
    patterns={"ru": [r"какой (сейчас )?режим", r"в каком (ты )?режиме"], "uz": [r"qaysi rejim"]},
    examples={"ru": ["Какой сейчас режим?"], "uz": ["Qaysi rejimdasan?"]},
    priority=2,
)
def which(ctx: Ctx) -> str:
    name = core.MODES[core.mode()][ctx.lang]
    return ctx.t(f"Сейчас {name} режим. Есть рабочий, дружеский и вежливый.",
                 f"Hozir {name} rejim. Ish, do'stona va hurmatli rejimlar bor.")


@skill(
    "modes.name",
    title={"ru": "Запомнить, как меня зовут", "uz": "Ismimni eslab qolish"},
    patterns={"ru": [r"^(?:джарвис )?(?:меня зовут|зови меня|называй меня|моё имя|мое имя) ([а-яa-z]+(?: [а-яa-z]+)?)$"],
              "uz": [r"^(?:jarvis )?(?:mening ismim|meni) ([a-z]+)(?: deb chaqir\w*)?$"]},
    examples={"ru": ["Меня зовут Мирод", "Называй меня босс"], "uz": ["Mening ismim Mirod"]},
    priority=3,
)
def set_name(ctx: Ctx) -> str:
    raw = ctx.group(1)
    pos = ctx.text.lower().find(raw.split()[0])
    name = ctx.text[pos:pos + len(raw)].strip(" .!") if pos >= 0 else raw
    name = name[:1].upper() + name[1:]
    core.save_setting("assistant", "user_name", name)
    return ctx.t(f"Приятно познакомиться, {name}! Запомнил.", f"Tanishganimdan xursandman, {name}! Eslab qoldim.")


@skill(
    "modes.whoami",
    title={"ru": "Как меня зовут", "uz": "Ismim nima"},
    patterns={"ru": [r"как меня зовут", r"ты знаешь как меня зовут"], "uz": [r"ismim nima", r"meni ismim"]},
    examples={"ru": ["Как меня зовут?"], "uz": ["Ismim nima?"]},
    priority=3,
)
def whoami(ctx: Ctx) -> str:
    name = core.CONFIG.get("assistant", {}).get("user_name", "")
    if not name:
        return ctx.t("Ты ещё не сказал. Скажи: «Меня зовут …».", "Hali aytmadingiz. «Mening ismim …» deng.")
    return ctx.t(f"Тебя зовут {name}.", f"Sizning ismingiz {name}.")
