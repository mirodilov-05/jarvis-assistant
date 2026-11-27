"""Builds COMMANDS.md from the code: every voice skill with its title and example phrases, grouped by area.

Run:  .venv\\Scripts\\python.exe tools\\make_commands_list.py
The list is generated, so it always matches what the assistant really has.
"""
from __future__ import annotations

import collections
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core  # noqa: E402

AREAS = {
    "apps": "Программы и сайты", "system": "Компьютер", "desktop": "Экран, окна, файлы",
    "music": "Музыка", "games": "Игры", "tasks": "Дела", "goals": "Цели, напоминания, лимиты",
    "reminders": "Таймеры и напоминания", "notes": "Заметки", "modes": "Режимы и функции",
    "prime": "Телевизор", "v3": "Курсы, фильмы, режимы", "v3_skills": "Курсы, фильмы, режимы",
    "pro": "Помощник: буфер, git, японский, диагностика", "assist": "Печать и текст",
    "creator": "Контент и ролики", "weather": "Погода", "briefing": "Сводка и отчёт",
    "greeting": "Приветствие", "basics": "Основное: время, калькулятор, помощь",
    "messaging": "Сообщения", "telegram": "Telegram", "whatsapp": "WhatsApp",
    "email_imap": "Почта", "calendar_ics": "Календарь", "youtube": "YouTube",
    "recorder": "Запись голоса", "vision": "Экран: что видно", "voice_id": "Мой голос",
    "macros": "Макросы", "llm": "Вопросы и разговор", "appfinder": "Поиск программ",
    "wellbeing": "Самочувствие и перерывы", "notifier": "Уведомления", "remote_ui": "Окно Джарвиса",
    "tgsetup": "Настройка Telegram", "calendar": "Календарь", "email": "Почта",
    "everyday": "Вкладки браузера, сеть, общение", "ui": "Окно и капсула Джарвиса",
}


def main() -> int:
    t = Path(tempfile.mkdtemp())
    core.DATA, core.SETTINGS_FILE, core.PROFILES_FILE = t, t / "s.json", t / "p.json"
    core._profile_cache.clear()
    (t / "log").mkdir()
    (t / "dictations").mkdir()
    core.load_config()
    core.load_plugins()

    groups: dict[str, list] = collections.defaultdict(list)
    skipped = 0
    for sk in core.SKILLS:
        if sk.name in ("music.choice", "macros.run", "_template"):
            skipped += 1
            continue
        area = sk.name.split(".")[0]
        title = (sk.title or {}).get("ru") or sk.name
        examples = (sk.examples or {}).get("ru") or []
        groups[AREAS.get(area, "Другое")].append((sk.name, title, examples))

    lines = [
        "# Команды Джарвиса",
        "",
        f"Всего навыков: {len(core.SKILLS) - skipped}. Список собран из кода, поэтому совпадает с тем, что Джарвис понимает.",
        "Фразы можно говорить с именем «Джарвис» или без него. Примеры ниже — образцы, не полный набор формулировок.",
        "",
    ]
    for area in sorted(groups):
        lines.append(f"## {area}")
        lines.append("")
        for name, title, examples in sorted(groups[area], key=lambda x: x[0]):
            lines.append(f"**{title}** (`{name}`)")
            for ex in examples[:4]:
                lines.append(f"- «{ex}»")
            lines.append("")
    lines += [
        "## Телевизор (через Jarvis PRIME, работает по сети)",
        "",
        "Любая фраза со словом «телевизор», «телик» или «ТВ» идёт в телевизор, не на ноутбук.",
        "",
        "**Включить / выключить**",
        "- «включи телевизор» / «включи телик» / «выключи ТВ»",
        "",
        "**Громкость и звук**",
        "- «громче телевизор» / «тише телевизор» / «без звука телевизор» / «включи звук телевизор»",
        "",
        "**Каналы**",
        "- «канал вверх телевизор» / «канал вниз телевизор» / «канал 5 телевизор» / «12 канал телик»",
        "",
        "**Воспроизведение и навигация**",
        "- «пауза телевизор» / «играй телевизор» / «домой телевизор» / «назад телевизор» / «меню телевизор»",
        "- «источник телевизор» (вход, HDMI) / «вверх», «вниз», «влево», «вправо», «ок» + «телевизор»",
        "",
        "**YouTube и статус**",
        "- «открой в телике ютуб» / «открой ютуб на телевизоре» / «статус телевизора»",
        "",
    ]
    out = ROOT / "COMMANDS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("written", out, "skills:", len(core.SKILLS) - skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
