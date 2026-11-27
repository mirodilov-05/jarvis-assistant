"""JARVIS PRIME OS — main entry point.

Wires the event bus, memory, router, guard, orchestrator and domains together, runs the scheduler
(morning brief, evening check-in, battery watch, daily backup) and the interfaces that are enabled.

Run:  python prime/main.py            (from the assistant folder, with its .venv)
"""
from __future__ import annotations

import asyncio
import re
import datetime as dt
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import SETTINGS  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from core.memory_core import Memory  # noqa: E402
from core.orchestrator import Orchestrator, Registry, Tool  # noqa: E402
from core.router import Budget, Router  # noqa: E402
from core.security_guard import Guard, Level  # noqa: E402
from core.tv_intents import digit_keys, tv_intent  # noqa: E402
from core.watchdog import battery_state, preflight  # noqa: E402
from domains import device_hub, life_flow  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("prime")


def normalize_command(text: str) -> str:
    """Lower case, no punctuation, no «Джарвис» or «эй» in front: «Эй, Джарвис, включи телевизор!» -> «включи телевизор»."""
    import re
    low = re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е"))
    low = re.sub(r"\s+", " ", low).strip()
    low = re.sub(r"^(эй |хей )?(джарвис|jarvis|прайм|prime)\s+", "", low)
    return low.strip()


_TV = r"(?:телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|тв)"
_TV_ON = re.compile(rf"^(?:включи|включить|вруби)(?: мне)? {_TV}$|^{_TV} (?:включи|включить|вруби)$")
_TV_OFF = re.compile(rf"^(?:выключи|выключить|выруби)(?: мне)? {_TV}$|^{_TV} (?:выключи|выключить|выруби)$")
_TV_VOL_UP = re.compile(rf"^громче {_TV}$|^{_TV} громче$|^{_TV} громкость больше$")
_TV_VOL_DOWN = re.compile(rf"^тише {_TV}$|^{_TV} тише$|^{_TV} громкость меньше$")
_TV_YOUTUBE = re.compile(rf"^(?:открой ютуб на|включи ютуб на|ютуб на) {_TV}$|^{_TV} ютуб$")
_TV_STATUS = re.compile(rf"^(?:статус {_TV}|{_TV} статус|{_TV})$")
# remote-control keys: (phrase words, Samsung key). Checked only when the phrase also names the TV.
TV_KEYS = [
    (("канал вверх", "следующий канал", "канал плюс", "программа вверх"), "KEY_CHUP"),
    (("канал вниз", "предыдущий канал", "канал минус", "программа вниз"), "KEY_CHDOWN"),
    (("без звука", "выключи звук", "включи звук", "звук выключи", "звук включи", "мут", "mute"), "KEY_MUTE"),
    (("пауза", "останови", "приостанови"), "KEY_PAUSE"),
    (("играй", "продолжи", "воспроизведи", "плей"), "KEY_PLAY"),
    (("домой", "главный экран", "главное меню"), "KEY_HOME"),
    (("назад", "вернись"), "KEY_RETURN"),
    (("меню",), "KEY_MENU"),
    (("источник", "вход", "hdmi"), "KEY_SOURCE"),
    (("вверх",), "KEY_UP"), (("вниз",), "KEY_DOWN"), (("влево",), "KEY_LEFT"), (("вправо",), "KEY_RIGHT"),
    (("ок", "выбери", "выбрать", "подтверди"), "KEY_ENTER"),
]


def is_tv_phrase(low: str) -> bool:
    """The phrase names the TV (телевизор, телик, ТВ). Such phrases are always handled by the TV, never the laptop."""
    return bool(re.search(rf"\b{_TV}\b", low))


def tv_key_for(low: str) -> str | None:
    """Key for a remote-control phrase like «канал вверх телевизор». None if the phrase is not a key command."""
    if not re.search(rf"\b{_TV}\b", low):
        return None
    for words, key in TV_KEYS:
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
            return key
    return None


class Prime:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.mem = Memory(SETTINGS.db_path)
        self.budget = Budget(SETTINGS.daily_budget_usd)
        from core.router import gemini_key
        self.router = Router(gemini_key(), self.budget)
        self.guard = Guard()
        self.registry = Registry()
        self.orch = Orchestrator(self.registry, self.guard, trust=Level.SAFE_WRITE)
        self.stop_event = asyncio.Event()
        self._register_tools()

    # ---------- tools (each one knows its trust level)
    def _register_tools(self) -> None:
        mem = self.mem

        async def add_task(text: str, due: str | None = None) -> str:
            tid = await mem.add_task(text, due)
            await self.bus.publish("task.added", id=tid, text=text)
            return f"Записал дело: {text}."

        async def list_tasks() -> str:
            tasks = await mem.open_tasks()
            focus = life_flow.rule_of_three(tasks, dt.date.today().isoformat())
            return ("Главное: " + "; ".join(t["text"] for t in focus) + ".") if focus else "Открытых дел нет."

        async def finish_task(task_id: int) -> str:
            await mem.finish_task(task_id)
            await self.bus.publish("task.done", id=task_id)
            return "Отмечено выполненным."

        async def add_goal(title: str) -> str:
            gid = await mem.add_goal(title)
            return f"Записал цель: {title}. Номер {gid}."

        async def goals_progress() -> str:
            goals = await mem.goals()
            if not goals:
                return "Целей пока нет."
            pct = life_flow.rollup(goals)
            return "; ".join(f"{g['title']}: {round(pct[g['id']] * 100)}%" for g in goals) + "."

        async def add_note(text: str) -> str:
            await mem.add_note(text)
            return "Записал заметку."

        async def add_expense(amount: float, category: str) -> str:
            await mem.add_expense(amount, category)
            return f"Записал расход: {amount:g} ({category})."

        from config.settings import ROOT as _root
        from domains import tv_samsung as tv

        def tv_cfg() -> dict:
            return device_hub.load_devices(_root / "config" / "devices.yaml").get("tv_samsung", {})

        async def tv_on() -> str:
            st = await tv.status(tv_cfg())
            if st["online"] and st["power"] == "on":
                return "Телевизор уже включён."
            return await tv.wake(tv_cfg(), wait=8.0)

        async def tv_off() -> str:
            return await tv.press(tv_cfg(), [tv.POWER_OFF])

        async def tv_volume(direction: str) -> str:
            key = tv.VOLUME_UP if direction == "up" else tv.VOLUME_DOWN
            return await tv.press(tv_cfg(), [key] * 3)

        async def tv_status() -> str:
            st = await tv.status(tv_cfg())
            if not st["online"]:
                return "Телевизор не отвечает: он выключен или не в сети."
            return "Телевизор включён." if st["power"] == "on" else "Телевизор в режиме ожидания."

        async def tv_key(key: str) -> str:
            return await tv.press(tv_cfg(), [key])

        async def tv_digits(digits: str) -> str:
            return await tv.press(tv_cfg(), digit_keys(digits))

        async def tv_youtube() -> str:
            return await tv.open_youtube(tv_cfg())

        async def tv_app(name: str) -> str:
            return await tv.open_app(tv_cfg(), name)

        async def tv_video(video_id: str) -> str:
            await tv.open_youtube_video(tv_cfg(), video_id)
            return "Включаю видео на телевизоре."

        async def tv_volume_set(level: int) -> str:
            # the TV has no «set volume» key: go down to zero, then up to the level
            await tv.press(tv_cfg(), [tv.VOLUME_DOWN] * 40)
            if level:
                await tv.press(tv_cfg(), [tv.VOLUME_UP] * level)
            return f"Громкость телевизора: {level}."

        pending_off: list = []

        async def tv_off_later(minutes: int) -> str:
            async def later():
                await asyncio.sleep(minutes * 60)
                try:
                    await tv.press(tv_cfg(), [tv.POWER_OFF])
                except Exception:  # noqa: BLE001 — the TV may already be off
                    pass
            pending_off.append(asyncio.create_task(later()))
            return f"Выключу телевизор через {minutes} мин."

        async def ask_brain(question: str) -> str:
            reply, engine = await self.router.complete("Ты — Джарвис, краткий и точный помощник.", question, need_cloud=True)
            return reply

        for t in (
            Tool("add_task", Level.SAFE_WRITE, "Добавить дело", add_task),
            Tool("list_tasks", Level.READ_ONLY, "Главные дела на сегодня", list_tasks),
            Tool("finish_task", Level.SAFE_WRITE, "Отметить дело выполненным", finish_task),
            Tool("add_goal", Level.SAFE_WRITE, "Добавить цель", add_goal),
            Tool("goals_progress", Level.READ_ONLY, "Прогресс по целям", goals_progress),
            Tool("add_note", Level.SAFE_WRITE, "Записать заметку", add_note),
            Tool("add_expense", Level.SAFE_WRITE, "Записать расход", add_expense),
            Tool("tv_on", Level.SAFE_WRITE, "Включить телевизор по сети", tv_on, timeout_s=30),
            Tool("tv_off", Level.SAFE_WRITE, "Выключить телевизор", tv_off, timeout_s=30),
            Tool("tv_volume", Level.SAFE_WRITE, "Громкость телевизора", tv_volume, timeout_s=30),
            Tool("tv_youtube", Level.SAFE_WRITE, "Открыть YouTube на телевизоре", tv_youtube, timeout_s=30),
            Tool("tv_app", Level.SAFE_WRITE, "Открыть приложение на телевизоре по имени", tv_app, timeout_s=30),
            Tool("tv_key", Level.SAFE_WRITE, "Кнопка пульта телевизора", tv_key, timeout_s=20),
            Tool("tv_digits", Level.SAFE_WRITE, "Номер канала телевизора", tv_digits, timeout_s=20),
            Tool("tv_status", Level.READ_ONLY, "Статус телевизора", tv_status, timeout_s=15),
            Tool("tv_volume_set", Level.SAFE_WRITE, "Громкость телевизора числом", tv_volume_set, timeout_s=60),
            Tool("tv_video", Level.SAFE_WRITE, "Видео YouTube на телевизоре по id", tv_video, timeout_s=30),
            Tool("tv_off_later", Level.SAFE_WRITE, "Выключить телевизор через N минут", tv_off_later, timeout_s=20),
            Tool("ask_brain", Level.READ_ONLY, "Вопрос мозгу (Gemini или локальная модель)", ask_brain, timeout_s=45),
        ):
            self.registry.add(t)

    # ---------- one request from any interface
    async def handle(self, text: str) -> str:
        text = text.strip()
        await self.mem.log_turn("user", text)
        low = normalize_command(text)
        plan: list[tuple[str, dict]] = []
        tv_plan = tv_intent(low)
        if tv_plan and tv_plan[0] == "unknown":
            return ("Не понял команду для телевизора. Скажите: включи, выключи, громче, тише, канал вверх, "
                    "канал 5, пауза, домой, назад, ютуб или статус телевизора.")
        if tv_plan:
            plan = [tv_plan]
        elif low.startswith(("добавь дело ", "дело ")):
            plan = [("add_task", {"text": text.split(" ", 2)[-1]})]
        elif low.startswith(("цель ", "цель: ")):
            plan = [("add_goal", {"title": text.split(" ", 1)[1].lstrip(": ")})]
        elif low.startswith(("заметка ", "запомни ")):
            plan = [("add_note", {"text": text.split(" ", 1)[1]})]
        elif low in ("главное", "мои дела", "дела на сегодня", "какие дела"):
            plan = [("list_tasks", {})]
        elif low in ("прогресс", "мои цели", "прогресс по целям"):
            plan = [("goals_progress", {})]
        elif is_tv_phrase(low) and re.search(r"\b(ютуб\w*|ютюб\w*|ютьюб\w*|youtube)\b", low):
            plan = [("tv_youtube", {})]                       # «открой в телике ютуб» -> the TV, never the laptop
        elif tv_key_for(low):
            plan = [("tv_key", {"key": tv_key_for(low)})]
        elif _TV_ON.match(low):
            plan = [("tv_on", {})]
        elif _TV_OFF.match(low):
            plan = [("tv_off", {})]
        elif _TV_VOL_UP.match(low):
            plan = [("tv_volume", {"direction": "up"})]
        elif _TV_VOL_DOWN.match(low):
            plan = [("tv_volume", {"direction": "down"})]
        elif _TV_YOUTUBE.match(low):
            plan = [("tv_youtube", {})]
        elif _TV_STATUS.match(low):
            plan = [("tv_status", {})]
        elif is_tv_phrase(low):           # names the TV but no known action: say so, never ask the brain
            return ("Не понял команду для телевизора. Скажите: включи, выключи, громче, тише, канал вверх, "
                    "пауза, домой, назад, ютуб или статус телевизора.")
        elif low.startswith("подтверди "):
            code = low.split(" ", 1)[1]
            pending = self.guard.confirm(code)
            if pending is None:
                return "Код неверный или уже истёк."
            tool = self.registry.tools[pending.action]     # the owner confirmed it: run it now, once
            out = await tool.run(**pending.args)
            return str(out)
        else:
            plan = [("ask_brain", {"question": text})]
        steps = await self.orch.execute_plan(plan)
        reply = " ".join(s.result for s in steps if s.result) or "Готово."
        await self.mem.log_turn("jarvis", reply)
        return reply

    # ---------- background work
    async def scheduler(self) -> None:
        """Morning brief at 08:00, evening check-in at 21:30, battery check every minute, backup at 03:00."""
        done: set[str] = set()
        while not self.stop_event.is_set():
            now = dt.datetime.now()
            key = now.strftime("%Y-%m-%d")
            hhmm = now.strftime("%H:%M")
            for at, job in (("08:00", self.morning), ("21:30", self.evening), ("03:00", self.backup)):
                tag = f"{key}-{at}"
                if hhmm >= at and tag not in done:
                    done.add(tag)
                    try:
                        await job()
                    except Exception:  # noqa: BLE001 — a failed job must not stop the scheduler
                        log.exception("scheduled job %s failed", at)
            bat = battery_state()
            self.router.set_battery(bat.get("percent"), bat.get("plugged"))
            await asyncio.sleep(60)

    async def morning(self) -> None:
        tasks = await self.mem.open_tasks()
        focus = life_flow.rule_of_three(tasks, dt.date.today().isoformat())
        goals = await self.mem.goals()
        pct = life_flow.rollup(goals) if goals else {}
        brief = life_flow.morning_brief("", focus, [(g["title"], pct[g["id"]]) for g in goals if g["id"] in pct])
        await self.bus.publish("brief.morning", text=brief)

    async def evening(self) -> None:
        await self.bus.publish("checkin.evening", text="Вечерний чек-ин: что сделано сегодня? Отметьте дела.")

    async def backup(self) -> None:
        path = await self.mem.backup(SETTINGS.backup_dir)
        await self.bus.publish("backup.done", path=str(path))

    async def run(self) -> None:
        checks = preflight(ROOT)
        bad = [c.name for c in checks if not c.ok]
        if bad:
            log.warning("preflight problems: %s", ", ".join(bad))
        self.bus.start()
        self.bus.subscribe("brief.*", self._log_event)
        self.bus.subscribe("checkin.*", self._log_event)
        self.bus.subscribe("backup.*", self._log_event)
        from core.watchdog import supervise
        tasks = [asyncio.create_task(supervise(self.scheduler, "scheduler"), name="scheduler")]
        log.info("JARVIS PRIME OS started (cloud brain: %s)", "Gemini" if self.router.key else "none")
        await self.stop_event.wait()
        for t in tasks:
            t.cancel()
        await self.bus.stop()
        self.mem.close()

    async def _log_event(self, ev) -> None:
        log.info("%s: %s", ev.topic, ev.payload.get("text", ev.payload))


async def main() -> None:
    app = Prime()
    from interfaces.telegram_hub import run as telegram_run
    from interfaces.web_command_center import serve
    site = await serve(app, port=8765)
    from core.watchdog import supervise
    tg = asyncio.create_task(supervise(lambda: telegram_run(app, SETTINGS.telegram_token, SETTINGS.telegram_owner_id),
                                       "telegram"), name="telegram")
    try:
        await app.run()
    finally:
        tg.cancel()
        await site.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
