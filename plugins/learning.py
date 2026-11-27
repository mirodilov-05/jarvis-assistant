"""Learning from corrections: «проведи ночную рефлексию», «как ты учишься», «что ты выучил»."""
from learning import autolearn, evaluation, reflection
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
    learned = len(autolearn.aliases(500))
    return (f"Поправок и своих ошибок было {m['corrections_detected']}, уроков {m['lessons_learned']}, "
            f"выученных фраз {learned}. Повторных ошибок {m['repeat_mistake_rate']} процентов. Чем ниже, тем лучше.")


@skill(
    "learning.aliases",
    title={"ru": "Какие фразы Джарвис выучил сам"},
    patterns={"ru": [r"^(?:джарвис )?(?:что ты выучил сам|какие фразы ты выучил|что ты запомнил из ошибок)$"]},
    examples={"ru": ["Что ты выучил сам"]},
    priority=4,
)
def aliases_say(ctx: Ctx) -> str:
    rows = autolearn.aliases(5)
    if not rows:
        return ("Пока ничего. Если я не пойму фразу, скажите то же другими словами: "
                "я запомню, что значила первая.")
    return "Я выучил: " + "; ".join(f"«{r['phrase']}» значит «{r['means']}»" for r in rows) + "."


@skill(
    "learning.forget_alias",
    title={"ru": "Забыть последнюю выученную фразу"},
    patterns={"ru": [r"^(?:джарвис )?(?:забудь|отмени) (?:последнее|это) (?:обучение|правило)$",
                     r"^(?:джарвис )?не запоминай (?:это|так)$"]},
    examples={"ru": ["Забудь последнее обучение"]},
    priority=4,
)
def forget_alias(ctx: Ctx) -> str:
    row = autolearn.forget_last()
    return f"Забыл: «{row['phrase']}»." if row else "Выученных фраз нет."
