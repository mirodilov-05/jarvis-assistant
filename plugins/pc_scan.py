"""Learn this computer (with the owner's consent) and answer questions about it.

«изучи мой компьютер» — the owner asks for it, so this counts as consent; reads names and facts only.
«что ты знаешь о моём компьютере» — answers from the saved profile.
"""
import core
import pc_profile
from core import Ctx, skill


@skill(
    "pc.scan",
    title={"ru": "Изучить этот компьютер (с согласия)"},
    patterns={"ru": [
        r"^(?:джарвис )?(?:изучи|просканируй|проанализируй|исследуй)(?: мой| этот| наш)? (?:компьютер|комп|ноутбук|ноут|пк|систему)$",
    ]},
    examples={"ru": ["Изучи мой компьютер"]},
    priority=20,
)
def pc_scan(ctx: Ctx) -> str:
    """The full study (programs, games, browser, music, file names, Russian names of programs), in the background."""
    import threading

    import personalize
    if personalize.STATE["running"]:
        return ctx.t("Уже изучаю компьютер, сэр. Скажу, когда закончу.", "Allaqachon o'rganyapman.")

    def go():
        r = personalize.run()
        core.speak(personalize.say_result(r), ctx.lang)
    threading.Thread(target=go, daemon=True, name="personalize-voice").start()
    return ctx.t("Изучаю компьютер: программы, игры, браузер и имена файлов. Это займёт минуту-две, скажу, когда закончу. "
                 "Файлы я не открываю, всё остаётся на этом компьютере.", "Kompyuterni o'rganyapman.")


@skill(
    "pc.index",
    title={"ru": "Изучить имена всех файлов (с согласия)"},
    patterns={"ru": [
        r"^(?:джарвис )?(?:изучи|проиндексируй|просканируй) (?:все |мои )?(?:файлы|диски|весь компьютер|все файлы)(?: на (?:компьютере|диске|дисках))?$",
    ]},
    examples={"ru": ["Изучи все файлы на компьютере"]},
    priority=20,
)
def pc_index_cmd(ctx: Ctx) -> str:
    import pc_index
    def start():
        if pc_index.running():
            return ctx.t("Я уже изучаю файлы, подождите.", "Fayllarni o'rganyapman.")
        def done():
            d = pc_index.info()
            core.speak(f"Закончил изучать файлы: {d.get('files', 0)} имён. Теперь ищу быстрее.", "ru")
        pc_index.start_background(on_done=done)
        return ctx.t("Начал изучать имена файлов в фоне. Скажу, когда закончу.", "Fayllarni o'rganishni boshladim.")
    return core.ask_confirm(ctx, ctx.t(
        "Изучу имена файлов на всех дисках и в папках пользователя. Содержимое файлов не читаю, ключи и пароли пропускаю. "
        "Это может занять несколько минут. Начинаем? Скажите «да».",
        "Barcha disklardagi fayl nomlarini o'rganaman. Mazmunini o'qimayman. Boshlaymi? Ayting «ha»."), start)


@skill(
    "pc.about",
    title={"ru": "Что Джарвис знает о компьютере"},
    patterns={"ru": [
        r"^(?:джарвис )?что (?:ты )?(?:знаешь|узнал|помнишь) (?:о|про|об) (?:моём|моем|этом|мой|моем) (?:компьютер\w*|ноут\w*|комп\w*|пк)$",
        r"^(?:джарвис )?что (?:у меня )?(?:установлено|стоит) на (?:компьютере|ноуте|ноутбуке|пк)$",
    ]},
    examples={"ru": ["Что ты знаешь о моём компьютере"]},
    priority=20,
)
def pc_about(ctx: Ctx) -> str:
    text = pc_profile.summary(max_chars=500)
    if not text:
        return ctx.t("Я ещё не изучал этот компьютер. Скажите «изучи мой компьютер», и я посмотрю программы и железо.",
                     "Men bu kompyuterni hali o'rganmadim.")
    return ctx.t(text, text)
