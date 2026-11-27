"""Learning from corrections: «проведи ночную рефлексию», «как ты учишься», «что ты выучил»."""
from learning import evaluation, reflection
from core import Ctx, skill, on_start


@on_start
def _start_learning():
    reflection.start_scheduler()


@skill(
    "learning.reflect",
    title={"ru": "Ночная рефлексия: разобрать поправки за сегодня"},
    patterns={"ru": [r"^(?:джарвис )?(?:проведи|запусти|сделай) (?:ночную )?рефлексию$"]},
    examples={"ru": ["Проведи ночную рефлексию"]},
    priority=4,
)
def reflect_now(ctx: Ctx) -> str:
    return reflection.reflect()["message"]


@skill(
    "learning.metrics",
    title={"ru": "Учится ли Джарвис на поправках"},
    patterns={"ru": [r"^(?:джарвис )?(?:как ты учишься|учишься ли|что ты выучил|метрики обучения|статистика обучения)$"]},
    examples={"ru": ["Как ты учишься"]},
    priority=4,
)
def metrics_say(ctx: Ctx) -> str:
    m = evaluation.metrics()
    return (f"Поправок было {m['corrections_detected']}, уроков {m['lessons_learned']}. "
            f"Повторных ошибок {m['repeat_mistake_rate']} процентов. Чем ниже, тем лучше.")
