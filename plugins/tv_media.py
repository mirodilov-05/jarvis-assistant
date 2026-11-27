"""Music or a video on the TV: «поставь музыку на телевизоре», «включи Imagine Dragons в телевизоре».

The first YouTube result is found on this PC and played on the TV (a video link sent to the TV). The results are kept
as the TV's last search, so «запусти первое видео» afterwards plays on the TV too.
"""
import json
import re
import urllib.request

import core
from core import Ctx, skill

TV = r"(?:телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|тв)"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Accept-Language": "ru-RU,ru;q=0.9"}


def _search(query: str, n: int = 5) -> list[dict]:
    import requests
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": query, "hl": "ru"},
                         headers=_UA, timeout=8)
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for vid, raw in re.findall(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"', r.text):
        if vid in seen:
            continue
        seen.add(vid)
        try:
            title = json.loads('"' + raw + '"')
        except ValueError:
            title = raw
        out.append({"id": vid, "title": title})
        if len(out) >= n:
            break
    return out


def _prime(text: str) -> str:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8765/api/command", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return str(json.loads(r.read()).get("reply", "")).strip() or "Готово."
    except Exception:  # noqa: BLE001
        return "Система управления телевизором не запущена."


@skill(
    "tv.media",
    title={"ru": "Музыка или видео на телевизоре (первый результат YouTube)"},
    patterns={"ru": [
        rf"^(?:джарвис )?(?!.*(?:ютуб|youtube))(?:включи|поставь|запусти|вруби|сыграй)(?: мне)?(?: (?:музыку|песню|трек|клип|видео|ролик))?"
        rf"(?: (?P<q>.+?))? (?:на|в) {TV}$",
    ]},
    examples={"ru": ["Поставь музыку на телевизоре", "Включи Imagine Dragons в телевизоре"]},
    priority=3,
)
def tv_media(ctx: Ctx) -> str | None:
    q = (ctx.match.groupdict().get("q") or "").strip(" .!?,")
    if re.search(r"ютуб|youtube", q):
        return None                            # «включи ютуб в телевизоре»: the TV's YouTube command, not a search
    if re.search(r"первое|второе|третье|последнее|первый|второй|видео|ролик", q):
        # «запусти первое видео на телевизоре»: the last search's item, on the TV
        ordw = re.search(r"первое|второе|третье|последнее|первый|второй|третий", q)
        text = f"запусти {ordw.group(0) if ordw else 'первое'} видео"
        sk = next((x for x in core.SKILLS if x.name == "apps.result_open"), None)
        norm = core.normalize(text, ctx.lang)
        for pat in (sk.patterns.get(ctx.lang, []) if sk else []):
            m = pat.search(norm)
            if m:
                return sk.handler(Ctx(text=text, lang=ctx.lang, source=ctx.source, config=ctx.config, match=m, norm=norm))
        return None
    if not q or re.search(r"какой\s*-?\s*нибудь|что\s*-?\s*нибудь|любую|любой|музык\w*|песн\w*|трек\w*", q):
        q = "лучшие песни"
    items = _search(q)
    if not items:
        return ctx.t(f"Не нашёл «{q}» на YouTube. Скажите другое название.", "YouTube'da topilmadi.")
    core.set_results("youtube_tv", items)
    reply = _prime(f"открой видео {items[0]['id']} на телевизоре")
    return ctx.t(f"Ставлю на телевизоре: {items[0]['title']}. {reply}", f"Televizorda: {items[0]['title']}.")
