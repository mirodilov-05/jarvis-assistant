"""Study cards for the HUD: the next due card, a review (SM-2), a new card, and a starter N2 deck."""
from __future__ import annotations

import datetime as dt
from typing import Any

from domains.second_brain import sm2

# JLPT N2 words: front is the word, back is reading and meaning.
N2_DECK = [
    ("影響", "えいきょう — влияние"), ("改善", "かいぜん — улучшение"), ("努力", "どりょく — усилие, старание"),
    ("状況", "じょうきょう — обстановка, ситуация"), ("対象", "たいしょう — объект, предмет (внимания)"),
    ("評価", "ひょうか — оценка"), ("協力", "きょうりょく — сотрудничество"), ("拡大", "かくだい — расширение"),
    ("減少", "げんしょう — уменьшение"), ("増加", "ぞうか — увеличение"), ("現象", "げんしょう — явление"),
    ("責任", "せきにん — ответственность"), ("条件", "じょうけん — условие"), ("結論", "けつろん — вывод, заключение"),
    ("矛盾", "むじゅん — противоречие"), ("発展", "はってん — развитие"), ("維持", "いじ — поддержание, сохранение"),
    ("契約", "けいやく — договор"), ("訂正", "ていせい — исправление"), ("省略", "しょうりゃく — сокращение, пропуск"),
    ("含む", "ふくむ — содержать, включать"), ("防ぐ", "ふせぐ — предотвращать"), ("支える", "ささえる — поддерживать"),
    ("求める", "もとめる — требовать, искать"), ("従う", "したがう — следовать, подчиняться"),
    ("避ける", "さける — избегать"), ("備える", "そなえる — готовиться, быть оснащённым"),
    ("述べる", "のべる — излагать"), ("占める", "しめる — занимать (долю)"), ("招く", "まねく — приглашать; вызывать"),
    ("鋭い", "するどい — острый"), ("乏しい", "とぼしい — скудный, недостаточный"), ("著しい", "いちじるしい — заметный, значительный"),
    ("曖昧", "あいまい — неясный, двусмысленный"), ("慎重", "しんちょう — осторожный, осмотрительный"),
    ("徐々に", "じょじょに — постепенно"), ("一般に", "いっぱんに — вообще, обычно"), ("たとえ〜ても", "даже если"),
    ("〜に伴って", "にともなって — вместе с, по мере"), ("〜にすぎない", "не более чем, всего лишь"),
]


async def state(mem: Any) -> dict[str, Any]:
    due = await mem.cards_due(dt.date.today().isoformat())
    total = await mem.cards_count()
    card = due[0] if due else None
    return {"total": total, "due": len(due),
            "card": {"id": card["id"], "front": card["front"], "back": card["back"], "interval": card["interval_days"]} if card else None}


async def add(mem: Any, front: str, back: str) -> str:
    front, back = front.strip(), back.strip()
    if not front or not back:
        raise ValueError("нужны слово и перевод")
    await mem.save_card(None, front, back, 2.5, 0, dt.date.today().isoformat())
    return "Карточка добавлена."


async def add_deck(mem: Any) -> str:
    have = {c["front"] for c in await mem.cards_due("9999-12-31")}
    new = [(f, b) for f, b in N2_DECK if f not in have]
    for f, b in new:
        await mem.save_card(None, f, b, 2.5, 0, dt.date.today().isoformat())
    return f"Добавлено карточек: {len(new)}."


async def review(mem: Any, card_id: int, quality: int) -> str:
    card = next((c for c in await mem.cards_due("9999-12-31") if c["id"] == card_id), None)
    if card is None:
        raise ValueError("карточка не найдена")
    r = sm2(card["ease"], card["interval_days"], quality, dt.date.today())
    await mem.save_card(card_id, card["front"], card["back"], r.ease, r.interval, r.due)
    return f"Следующий показ через {r.interval} дн."
