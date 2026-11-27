"""Gaps found by the 300-phrase check: each phrase is handed to the skill that already does the job."""
import shutil

import core
from core import Ctx, skill


def _delegate(skill_name: str, text: str, ctx: Ctx):
    sk = next((s for s in core.SKILLS if s.name == skill_name), None)
    if sk is None:
        return None
    norm = core.normalize(text, ctx.lang)
    for pat in sk.patterns.get(ctx.lang, []):
        m = pat.search(norm)
        if m:
            return sk.handler(Ctx(text=text, lang=ctx.lang, source=ctx.source, config=ctx.config, match=m, norm=norm))
    return None


@skill("batch2.system", title={"ru": "Статус системы и что тормозит"},
       patterns={"ru": [r"^(?:джарвис )?(?:покажи )?статус системы$", r"^(?:джарвис )?что тормозит$"]},
       examples={"ru": ["Покажи статус системы", "Что тормозит"]}, priority=3)
def system_status(ctx: Ctx):
    return _delegate("pro.doctor", "проверь систему", ctx)


@skill("batch2.disk", title={"ru": "Сколько свободного места на дисках"},
       patterns={"ru": [r"^(?:джарвис )?сколько (?:у меня )?свободного места(?: на диске)?$"]},
       examples={"ru": ["Сколько свободного места на диске"]}, priority=3)
def disk_free(ctx: Ctx) -> str:
    parts = []
    for d in ("C:\\", "D:\\"):
        try:
            u = shutil.disk_usage(d)
            parts.append(f"{d[0]}: свободно {u.free / 2 ** 30:.0f} из {u.total / 2 ** 30:.0f} ГБ")
        except OSError:
            pass
    return ctx.t("; ".join(parts) or "Диски не найдены.", "; ".join(parts))


@skill("batch2.plan", title={"ru": "Какой план на сегодня"},
       patterns={"ru": [r"^(?:джарвис )?какой план на сегодня$"]},
       examples={"ru": ["Какой план на сегодня"]}, priority=3)
def plan_today(ctx: Ctx):
    return _delegate("tasks.list", "какие у меня дела", ctx)


@skill("batch2.pause_hour", title={"ru": "Сделать паузу на час"},
       patterns={"ru": [r"^(?:джарвис )?сделай паузу на (час|час времени|полчаса)$"]},
       examples={"ru": ["Сделай паузу на час"]}, priority=3)
def pause_hour(ctx: Ctx):
    minutes = 30 if ctx.group(1) == "полчаса" else 60
    return _delegate("reminders.timer", f"поставь таймер на {minutes} минут", ctx)


@skill("batch2.activity", title={"ru": "Статистика активности"},
       patterns={"ru": [r"^(?:джарвис )?покажи статистику активности$"]},
       examples={"ru": ["Покажи статистику активности"]}, priority=3)
def activity_stats(ctx: Ctx):
    return _delegate("activity.summary", "что я сегодня делал", ctx)


@skill("batch2.messages", title={"ru": "Кто мне писал (мессенджеры)"},
       patterns={"ru": [r"^(?:джарвис )?кто (?:мне )?писал$", r"^(?:джарвис )?кто мне написал$"]},
       examples={"ru": ["Кто мне писал"]}, priority=3)
def who_wrote(ctx: Ctx):
    return _delegate("whatsapp.unread", "что нового в ватсапе", ctx)


@skill("batch2.remember_recall", title={"ru": "Что я запоминал про …"},
       patterns={"ru": [r"^(?:джарвис )?что я запоминал (?:про|о|об) (.+)$"]},
       examples={"ru": ["Что я запоминал про ключ"]}, priority=3)
def remember_recall(ctx: Ctx):
    return _delegate("notes.search", f"что я записывал про {ctx.group(1)}", ctx)


core._LONG_OK.update({"batch2.system", "batch2.disk", "batch2.plan", "batch2.pause_hour", "batch2.activity",
                      "batch2.messages", "batch2.remember_recall"})
