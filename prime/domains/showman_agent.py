"""Showman / presenter: builds a monthly report from real data and speaks it in RU, EN or JA.

The script is assembled from the database, not invented. Japanese uses polite Keigo (です/ます form).
Slide cues look like [NEXT_SLIDE] so a presentation controller can follow them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TITLES = {"ru": "Месячный отчёт", "en": "Monthly report", "ja": "月次報告"}
GREET = {"ru": "Всем здравствуйте. Я — Джарвис. Начинаем отчёт.",
         "en": "Good morning everyone. I am Jarvis. Let's begin the report.",
         "ja": "皆さん、こんにちは。私はジャービスです。月次報告を始めます。"}
CLOSE = {"ru": "Спасибо. Готов ответить на вопросы.",
         "en": "Thank you. I am ready for questions.",
         "ja": "ご清聴ありがとうございました。質問をお受けします。"}


@dataclass
class Stats:
    goals_done: int = 0
    tasks_done: int = 0
    words_learned: int = 0
    skills_added: int = 0
    notes_added: int = 0
    highlights: list[str] = field(default_factory=list)


def build_script(stats: Stats, lang: str = "ru") -> list[dict[str, str]]:
    """Slides as a list of {"cue": "...", "say": "..."}. Unknown languages fall back to Russian."""
    lang = lang if lang in TITLES else "ru"
    slides = [{"cue": "[SLIDE_TITLE]", "say": f"{TITLES[lang]}. {GREET[lang]}"}]
    if lang == "ja":
        slides.append({"cue": "[NEXT_SLIDE]", "say": f"今月の成果を簡単にご説明いたします。"
                                                       f"目標を{stats.goals_done}件達成、タスクを{stats.tasks_done}件完了しました。"})
    elif lang == "en":
        slides.append({"cue": "[NEXT_SLIDE]", "say": f"This month: {stats.goals_done} goals reached, {stats.tasks_done} tasks done."})
    else:
        slides.append({"cue": "[NEXT_SLIDE]", "say": f"За месяц: достигнуто целей — {stats.goals_done}, закрыто дел — {stats.tasks_done}."})
    if stats.words_learned:
        slides.append({"cue": "[NEXT_SLIDE]", "say": {
            "ja": f"学習した単語は{stats.words_learned}語です。",
            "en": f"Vocabulary: {stats.words_learned} words learned.",
            "ru": f"Выучено слов: {stats.words_learned}."}[lang]})
    for h in stats.highlights[:3]:
        slides.append({"cue": "[NEXT_SLIDE]", "say": h})
    slides.append({"cue": "[END]", "say": CLOSE[lang]})
    return slides


def stats_from_rows(goals: list[dict], tasks: list[dict], cards_learned: int, skills: int, notes: int) -> Stats:
    return Stats(goals_done=sum(1 for g in goals if g.get("progress", 0) >= 1.0),
                 tasks_done=sum(1 for t in tasks if t.get("done")),
                 words_learned=cards_learned, skills_added=skills, notes_added=notes)
