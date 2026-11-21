"""Brain tools: viral short videos on a topic, a script in the user's style, send results to Telegram."""

from tools import run_skill, tool

S = {"type": "string"}


@tool("viral_videos", "Найти, какие короткие видео (Reels, Shorts, TikTok) по теме залетели за сутки или за неделю.",
      {"topic": S, "period": {**S, "enum": ["day", "week"]}}, ["topic"])
def viral_videos(topic: str, period: str = "day") -> str:
    return run_skill("creator.trends", f"найди какие рилсы про {topic} залетели {'за неделю' if period == 'week' else 'за ночь'}")


@tool("write_script", "Написать сценарий короткого ролика в стиле пользователя (хук берётся у самого залетевшего ролика).",
      {"topic": {**S, "description": "Тема; пусто — тема последнего поиска трендов"}})
def write_script(topic: str = "") -> str:
    return run_skill("creator.script", f"напиши сценарий про {topic}" if topic else "пиши сценарий под меня")


@tool("send_to_telegram", "Отправить пользователю в Telegram последний результат (сценарий, список, ответ).")
def send_to_telegram() -> str:
    return run_skill("creator.send_tg", "скинь мне в телегу")
