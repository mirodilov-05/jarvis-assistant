"""Health helpers, switched per mode: break reminders and water reminders.

Break: after N minutes of continuous computer use (keyboard/mouse activity) — "Пора размяться".
Water: every N minutes while you're at the laptop.
Intervals: config.toml [wellbeing] break_minutes / water_minutes.
"""

import ctypes
import random
import time

import core
from core import Ctx, skill


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    li = _LastInput()
    li.cbSize = ctypes.sizeof(li)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
    return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0


_BREAK = ["Ты уже {m} минут за компьютером. Пора размяться: встань, потянись, посмотри вдаль.",
          "{m} минут без перерыва. Давай пять минут отдыха для глаз и спины.",
          "Время перерыва! Ты работаешь уже {m} минут."]
_WATER = ["Не забудь попить воды.", "Время сделать глоток воды.", "Напоминаю: стакан воды — и дальше в бой."]


@core.on_start
def loop() -> None:
    session_start = time.time()
    last_water = time.time()
    while True:
        try:
            cfg = core.CONFIG.get("wellbeing", {})
            brk = float(cfg.get("break_minutes", 50)) * 60
            water = float(cfg.get("water_minutes", 90)) * 60
            idle = idle_seconds()
            if idle > 300:          # away for 5+ minutes = you already had a break
                session_start = time.time()
            worked = time.time() - session_start
            if core.feature("break_reminders") and worked >= brk:
                core.speak(random.choice(_BREAK).format(m=int(worked // 60)), "ru")
                session_start = time.time()
            if idle > 300:
                last_water = min(last_water + 60, time.time())
            if core.feature("water_reminders") and time.time() - last_water >= water and idle < 120:
                core.speak(random.choice(_WATER), "ru")
                last_water = time.time()
        except Exception:  # noqa: BLE001
            core.log.exception("wellbeing loop")
        time.sleep(30)


@skill(
    "wellbeing.status",
    title={"ru": "Сколько я уже за компьютером"},
    patterns={"ru": [r"сколько (я )?(уже )?(сижу|работаю|за компьютером|за ноутбуком)"]},
    examples={"ru": ["Сколько я уже сижу за компьютером?"]},
    priority=20,
)
def status(ctx: Ctx) -> str:
    up = ctypes.windll.kernel32.GetTickCount64() / 1000 / 60
    h, m = divmod(int(up), 60)
    return f"Ноутбук включён {h} ч {m} мин." if h else f"Ноутбук включён {m} минут."
