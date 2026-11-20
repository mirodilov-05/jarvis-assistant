"""V3: starts the tray icon, the mini capsule hotkey and the Telegram remote-control bot; voice commands for them."""

import core
from core import Ctx, skill


@core.on_start
def start_tray_and_bot() -> None:
    try:
        import tray
        tray.start()
    except Exception:  # noqa: BLE001
        core.log.exception("Tray failed to start")
    try:
        import remote_bot
        remote_bot.start()
    except Exception:  # noqa: BLE001
        core.log.exception("Telegram bot failed to start")


@skill("ui.capsule", title={"ru": "Мини-капсула поверх окон (Ctrl+Alt+Space)"},
       patterns={"ru": [r"(?:покажи|открой|включи|убери|спрячь|скрой) (?:мини )?капсул"]},
       examples={"ru": ["Покажи капсулу"]}, priority=8)
def capsule(ctx: Ctx) -> str:
    import tray
    tray.toggle_capsule()
    return "Капсула, сэр."


@skill("ui.tray", title={"ru": "Свернуть окно в трей"},
       patterns={"ru": [r"(?:сверни|спрячь|скрой|убери)(?: окно)?(?: джарвиса)? в трей", r"^(?:сверни|спрячь) окно$"]},
       examples={"ru": ["Сверни в трей"]}, priority=8)
def to_tray(ctx: Ctx) -> str:
    import tray
    return "Свернул в трей. Я на связи." if tray.hide_window() else "Окно и так закрыто, я работаю в фоне."


@skill("ui.window", title={"ru": "Показать окно Джарвиса"},
       patterns={"ru": [r"(?:покажи|открой|разверни) (?:свое |твое )?окно", r"^(?:покажи|открой) интерфейс$"]},
       examples={"ru": ["Покажи окно"]}, priority=8)
def show(ctx: Ctx) -> str:
    import tray
    tray.show_window()
    return "Готово."


@skill("ui.translate_live", title={"ru": "Живой переводчик экрана (вкл/выкл)"},
       patterns={"ru": [r"(?:включи|запусти|выключи|останови|отключи) (?:живой |постоянный )?(?:перевод|переводчик)"]},
       examples={"ru": ["Включи живой перевод", "Выключи переводчик"]}, priority=7)
def translate_live(ctx: Ctx) -> str:
    import pcx
    on = not any(w in ctx.norm for w in ("выключи", "останови", "отключи"))
    return pcx.translate_live(on)
