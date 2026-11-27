"""«Проанализируй ноутбук», «оптимизируй ноутбук», «отмени оптимизацию»."""
import threading

import core
import optimizer
from core import Ctx, skill

PC = r"(?:мой |мою |этот )?(?:ноут\w*|компьютер\w*|комп\w{0,2}|пк|систему)"


@skill(
    "pc.analyze",
    title={"ru": "Полный анализ ноутбука"},
    patterns={"ru": [rf"^(?:джарвис )?(?:полностью |сделай (?:полный )?)?(?:проанализируй|анализируй|анализ|диагностика) (?:полностью )?{PC}$",
                     r"^(?:джарвис )?чего не хватает (?:моему |этому )?(?:ноут\w*|компьютер\w*|комп\w{0,2})$"]},
    examples={"ru": ["Проанализируй ноутбук", "Чего не хватает ноутбуку"]},
    priority=4,
)
def analyze(ctx: Ctx) -> str:
    def work():
        a = optimizer.analyze()
        bad = [p for p in a["problems"] if p["sev"] != "info"]
        text = f"Оценка {a['score']} из 100, компьютер {a['tier_name']}. "
        text += ("Мешает: " + "; ".join(p["title"] for p in bad[:3]) + ". ") if bad else "Серьёзных проблем нет. "
        n = len([s for s in a["plan"] if s["default"]])
        text += f"Могу улучшить пунктов: {n}. Скажите «оптимизируй ноутбук»." if n else "Оптимизировать нечего."
        core.speak(text, ctx.lang)
        core.emit({"type": "wizard"})
    threading.Thread(target=work, daemon=True, name="pc-analyze").start()
    return "Анализирую, это около тридцати секунд."


@skill(
    "pc.optimize",
    title={"ru": "Оптимизация ноутбука (с вашего согласия)"},
    patterns={"ru": [rf"^(?:джарвис )?(?:оптимизируй|оптимизировать|ускорь|сделай оптимизацию) {PC}$"]},
    examples={"ru": ["Оптимизируй ноутбук"]},
    priority=4,
)
def optimize(ctx: Ctx) -> str:
    plan = [s for s in optimizer.analyze()["plan"] if s["default"]]
    if not plan:
        return "Всё уже настроено, оптимизировать нечего."

    def go() -> str:
        res = optimizer.apply([s["id"] for s in plan])
        bad = [r for r in res if not r["ok"]]
        return "Готово. " + ". ".join(f"{r['title']}: {r['message']}" for r in res if r["ok"]) + (f". Не получилось: {len(bad)}." if bad else ".")
    return core.ask_confirm(ctx, "Сделаю: " + "; ".join(s["title"] for s in plan) + ". Делать? Скажите «да».", go)


@skill(
    "pc.optimize_undo",
    title={"ru": "Вернуть настройки до оптимизации"},
    patterns={"ru": [r"^(?:джарвис )?(?:отмени|откати|верни) оптимизацию$", r"^(?:джарвис )?верни (?:всё |все )?как было до оптимизации$"]},
    examples={"ru": ["Отмени оптимизацию"]},
    priority=4,
)
def optimize_undo(ctx: Ctx) -> str:
    done = optimizer.undo()
    return f"Вернул настроек: {len(done)}. Удалённые временные файлы не возвращаются." if done else "Возвращать нечего."
