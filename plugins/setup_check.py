"""First-run check: «проверь настройку компьютера» and «установи недостающее» (each automatic fix needs your yes)."""
import threading

import core
import setup_doctor
from core import Ctx, skill


@core.on_start
def _first_run_hint():
    if setup_doctor.was_checked() or setup_doctor.was_hinted():
        return
    setup_doctor.mark_hinted()

    def hint():
        core.speak("Первый запуск. Я открыл окно анализа ноутбука: там видно, чего не хватает и что можно улучшить.", "ru")
    threading.Timer(40, hint).start()


@skill(
    "setup.check",
    title={"ru": "Проверить, готов ли компьютер к Джарвису"},
    patterns={"ru": [
        r"^(?:джарвис )?(?:проверь|проверить|проверка) (?:настройку|установку|систему джарвиса|компьютер для джарвиса)(?: компьютера)?$",
        r"^(?:джарвис )?что (?:не хватает|надо доустановить|нужно установить) (?:джарвису|для джарвиса)$",
    ]},
    examples={"ru": ["Проверь настройку компьютера"]},
    priority=4,
)
def setup_check(ctx: Ctx) -> str:
    checks = setup_doctor.check_all()
    setup_doctor.mark_checked()
    todo = setup_doctor.missing_auto(checks)
    manual = [c.fix.label for c in checks if c.fix and c.fix.kind == "manual" and c.status == "missing"]
    if not todo and not manual:
        return ctx.t("Всё готово, можно работать.", "Hammasi tayyor.")
    parts = []
    if todo:
        parts.append("Могу доустановить: " + ", ".join(c.fix.label for c in todo) + ". Скажите «установи недостающее».")
    if manual:
        parts.append("Сделайте сами: " + "; ".join(manual) + ".")
    return ctx.t(" ".join(parts), " ".join(parts))


@skill(
    "setup.fix",
    title={"ru": "Установить недостающее (с подтверждением)"},
    patterns={"ru": [r"^(?:джарвис )?(?:установи|доустанови|поставь) (?:всё |все )?недостающее$"]},
    examples={"ru": ["Установи недостающее"]},
    priority=4,
)
def setup_fix(ctx: Ctx) -> str:
    todo = [c for c in setup_doctor.missing_auto(setup_doctor.check_all()) if c.fix.id != "reboot"]
    if not todo:
        return ctx.t("Автоматически доустанавливать нечего.", "Avtomatik o'rnatish kerak emas.")
    names = ", ".join(f"{c.fix.label}{' (скачается ' + c.fix.size + ')' if c.fix.size else ''}" for c in todo)
    ids = [c.fix.id for c in todo]

    def start():
        def done():
            log = setup_doctor.last_run()["log"]
            bad = [e for e in log if not e["ok"]]
            core.speak("Установка закончена." if not bad else "Некоторое не получилось, список в окне Джарвиса.", "ru")
        if not setup_doctor.run_all_in_background(ids, on_done=done):
            return ctx.t("Установка уже идёт.", "O'rnatish davom etmoqda.")
        return ctx.t("Начал. Скажу, когда закончу.", "Boshladim.")
    return core.ask_confirm(ctx, ctx.t(f"Установлю: {names}. Это может занять время и потребует интернет. Начинаем? Скажите «да».",
                                       f"O'rnataman: {names}. Boshlaymi? «ha» deng."), start)
