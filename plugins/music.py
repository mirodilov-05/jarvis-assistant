"""Music that really plays: finds the track / artist / mood and opens it already PLAYING, in front of you.

  «Включи музыку»                 — your default mix (⚙ or config [music] default_query) starts playing
  «Включи Imagine Dragons»        — the best match starts playing (then YouTube keeps playing similar songs)
  «Поставь трек Believer», «Включи музыку для работы», «Включи что-нибудь спокойное»
  «Открой музыку»                 — the same as «включи музыку»
Pause / next / previous / louder keep working with the media keys (system plugin).

Without a desktop music app on this PC a web page can't start sound by itself, so the player is YouTube in your
browser opened with autoplay. Settings [music]: service = "youtube" (plays at once) or "yandex" (opens Яндекс
Музыку, press ▶ yourself).
"""

from __future__ import annotations

import ctypes
import os
import re
import threading
import time
import urllib.parse

import core
from core import Ctx, skill

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "ru,en;q=0.8"}
MOODS = {
    "для работы": "музыка для работы и концентрации mix", "для учебы": "lofi музыка для учебы mix",
    "для учёбы": "lofi музыка для учебы mix", "спокойн": "спокойная музыка mix", "весел": "весёлая музыка хиты mix",
    "для игры": "music for gaming mix", "для спорта": "музыка для тренировки mix", "для сна": "музыка для сна",
    "грустн": "грустная музыка mix", "энергичн": "энергичная музыка mix", "lofi": "lofi hip hop mix",
    "лофи": "lofi hip hop mix", "русск": "русские хиты mix", "узбекск": "o'zbek qo'shiqlari mix",
}
_last = {"title": "", "url": ""}


def youtube_first(query: str) -> tuple[str, str] | None:
    """(video id, title) of the best YouTube match."""
    import requests
    r = requests.get("https://www.youtube.com/results", params={"search_query": query, "hl": "ru"}, headers=UA, timeout=8)
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"', r.text)
    if not m:   # the first results are a playlist or a shelf: take any video on the page
        m = re.search(r'"videoId":"([\w-]{11})".{0,4000}?"(?:title|accessibilityText)":(?:\{"runs":\[\{"text":|\{"simpleText":|)"(.*?)"',
                      r.text, re.S)
    if not m:
        return None
    title = m.group(2).encode("utf-8").decode("unicode_escape", errors="ignore") if "\\u" in m.group(2) else m.group(2)
    return m.group(1), title


def bring_browser_to_front(delay: float = 1.5) -> None:
    """The new tab should be on the screen, not hidden behind other windows."""
    def go():
        time.sleep(delay)
        try:
            import pcx
            u32 = ctypes.windll.user32
            hwnd, title, exe = pcx.foreground()
            if exe in pcx.BROWSERS:
                return
            found = []

            def cb(h, _l):
                if u32.IsWindowVisible(h):
                    buf = ctypes.create_unicode_buffer(256)
                    u32.GetWindowTextW(h, buf, 256)
                    if re.search(r"youtube|яндекс музык|yandex music", buf.value, re.I):
                        found.append(h)
                return True
            u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
            if found:
                u32.keybd_event(0x12, 0, 0, 0)      # a tap of Alt lets a background app bring a window forward
                u32.keybd_event(0x12, 0, 2, 0)
                u32.ShowWindow(found[0], 9)
                u32.SetForegroundWindow(found[0])
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=go, daemon=True).start()


WAVE_WORDS = re.compile(r"^(?:мою волну|волну|моя волна|что угодно|любую|на твой вкус|на ваш вкус|что нибудь|что-нибудь|"
                        r"сам выбери|выбери сам|рекомендации|мои рекомендации|радио)$", re.I)
_await: dict = {"until": 0.0}


def _yandex_play(url: str, what: str) -> None:
    """Open Yandex Music in your browser and press its «Воспроизведение» button (like a person would)."""
    _play_run["id"] += 1
    run = _play_run["id"]

    def go():
        import comtypes
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        try:
            import uiclick
            old = [h for h in uiclick.windows_with_title(YANDEX_TITLE)]
            for h in old:                               # something is already playing there: don't play two songs at once
                try:
                    st = uiclick.player(h)
                    if st["playing"]:
                        uiclick.press(st["bar"])
                except Exception:  # noqa: BLE001
                    pass
            os.startfile(url)
            ok, why = _press_until_playing(url, run)
            core.log.info("Yandex Music «%s»: playing=%s (%s)", what, ok, why)
            if not ok and run == _play_run["id"]:
                core.speak(f"Яндекс Музыку открыл, но она не заиграла: {why}. Нажмите плей, сэр.", "ru")
        except Exception:  # noqa: BLE001
            core.log.exception("yandex music autoplay")
    threading.Thread(target=go, daemon=True, name="yandex-play").start()


YANDEX_TITLE = r"Яндекс Музык|Yandex Music"
_play_run: dict = {"id": 0}


def _press_until_playing(url: str, run: int, timeout: float = 40.0) -> tuple[bool, str]:
    """Press play on the page and CHECK that the player shows «Пауза»; press again if it doesn't.
    One blind press is not enough: the page shows its buttons a few seconds before they start working."""
    import uiclick
    want = urllib.parse.unquote(urllib.parse.urlsplit(url).query)      # «text=…» of a search; empty for My Wave
    why, end, presses, last_press, fronted, seen_at = "окно не нашёл", time.time() + timeout, 0, 0.0, False, 0.0
    before: str | None = None                           # what was loaded before: the same track again is not the music you asked for
    while time.time() < end:
        time.sleep(0.7)
        if run != _play_run["id"]:
            return False, "отменено новой командой"
        hwnd, st = None, None
        for h in uiclick.windows_with_title(YANDEX_TITLE):
            try:
                addr = urllib.parse.unquote(uiclick.page_url(h))
                if "music.yandex" in addr and want.replace("+", " ") in addr.replace("+", " "):
                    hwnd, st = h, uiclick.player(h)
                    break
            except Exception:  # noqa: BLE001 - the page is being rebuilt, look again
                continue
        if not hwnd:
            continue
        if not fronted:
            bring_browser_to_front(0.1)
            fronted, seen_at = True, time.time()
        if st["playing"] and presses:
            time.sleep(1.5)                              # it must stay playing, and it must be new music
            now_st = uiclick.player(hwnd)
            if now_st["playing"] and (not want or now_st["track"] != before):
                return True, f"нажатий: {presses}, трек: {now_st['track'] or '?'}"
            if not now_st["playing"]:
                continue
            why = "включился прошлый трек, а не то, что вы просили"
        if time.time() - last_press < 3.5:
            continue                                     # give the press time to work
        # The player bar appears 1–2 s before the results and would resume the OLD queue — never press it for a search.
        if want:
            target = st["items"][0] if len(st["items"]) >= 1 and st["bar"] else None
            missing = "по запросу ничего не нашлось"
        else:                                            # My Wave: its own button if another queue is loaded, else resume
            target = st["wave"] or (st["bar"] if st["items"] and time.time() - seen_at > 3 else None)
            missing = "на странице нет кнопки «Моя волна»"
        if not target or time.time() - seen_at < 2.0:
            why = missing
            continue
        if before is None:
            before = st["track"]
        why = "кнопку нажал, но плеер не включился — возможно, нужен вход в аккаунт"
        try:
            uiclick.press(target)
            presses, last_press = presses + 1, time.time()
        except Exception:  # noqa: BLE001
            continue
        if presses >= 5:
            time.sleep(4)
            break
    return False, why


def play(query: str = "", ask: bool = False) -> str:
    """Start music playing. query: artist / track / mood / «мою волну»; empty + ask -> Jarvis asks what you want."""
    q = re.sub(r"\b(?:в|на|из|через)\s+(?:яндекс\w*(?:\s+музык\w*)?|ютуб\w*(?:\s+музык\w*)?|youtube)\b", "", (query or ""), flags=re.I)
    q = re.sub(r"^(?:что[ -]?нибудь|какую[ -]?нибудь|какое[ -]?нибудь|чего[ -]?нибудь)\s+(?=\S)", "", q.strip(" .!?,"), flags=re.I)
    q = q.strip(" .!?,")
    low = q.lower()
    generic = not q or low in ("музыку", "музыка", "что нибудь послушать", "что-нибудь послушать")
    if generic and ask and core.setting("music", "ask_what", True):
        _await["until"] = time.time() + 60
        core.FOLLOWUP.set()          # the answer comes without «Джарвис» again
        return "Что включить, сэр: Мою волну, что-то под настроение — для работы, спокойное, для игры — или кого-то конкретного?"
    _await["until"] = 0.0          # music is starting: Jarvis is no longer waiting for an answer
    for k, v in MOODS.items():
        if k in low:
            q = v.replace(" mix", "")
            break
    wave = generic or bool(WAVE_WORDS.match(low))
    service = core.setting("music", "service", "yandex")
    if service == "yandex":
        if wave:
            _yandex_play("https://music.yandex.ru/", "Моя волна")
            return "Включаю Мою волну в Яндекс Музыке."
        _yandex_play(f"https://music.yandex.ru/search?text={urllib.parse.quote(q)}", q)
        return f"Включаю в Яндекс Музыке: {q}."
    if wave:
        q = core.setting("music", "default_query", "лучшие хиты mix")
    try:
        hit = youtube_first(q)
    except Exception as e:  # noqa: BLE001
        core.log.warning("music search failed: %s", e)
        hit = None
    if not hit:
        os.startfile(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}")
        return f"Не нашёл сразу, открыл поиск: {q}."
    vid, title = hit
    url = f"https://www.youtube.com/watch?v={vid}&autoplay=1"
    _last.update(title=title, url=url)
    os.startfile(url)
    bring_browser_to_front()
    return f"Включаю: {title[:80]}."


@skill("music.choice", title={"ru": "Ответ на «Что включить?»"},
       patterns={"ru": [r"^(?:джарвис )?(?:давай |включи |поставь |ну )?(.+)$"]}, examples={"ru": []}, priority=-1)
def choice(ctx: Ctx):
    if time.time() > _await["until"]:
        return None              # Jarvis didn't ask anything: not for us
    _await["until"] = 0.0
    if re.match(r"^(?:нет|не надо|ничего|отмена|стоп|не нужно)$", ctx.norm):
        return "Хорошо, без музыки."
    return play(ctx.group(1))


@skill("music.play", title={"ru": "Включить музыку: сразу играет (исполнитель, трек, настроение)"},
       patterns={"ru": [
           r"^(?:джарвис )?(?:включи|поставь|запусти|открой|сыграй|вруби|давай)(?: мне)?(?: какую нибудь| какую-нибудь)? (?:музыку|музыка|песню|песни|трек|треки|альбом|плейлист|группу|исполнителя)\s*(.*)$",
           r"^(?:джарвис )?(?:включи|поставь|вруби) (?:что нибудь|что-нибудь)(?: послушать)?\s*(.*)$",
           r"^(?:джарвис )?(?:включи|поставь|вруби) (.+?) (?:на|в) (?:ютубе|youtube|ютуб музык\w*|яндекс музык\w*|яндексе)$",
           r"^(?:джарвис )?(?:включи|поставь|вруби) (мою волну|волну|радио)$",
           r"^(?:джарвис )?(?:запусти|открой|включи) (?:яндекс|ютуб)\w*(?: музык\w*)? и (?:включи|поставь|запусти|найди)(?: мне)? (.+)$",
           r"^(?:джарвис )?(?:хочу послушать|давай послушаем|послушаем) (.+)$",
       ]},
       examples={"ru": ["Включи музыку", "Включи Imagine Dragons", "Включи музыку для работы", "Поставь трек Believer"]},
       priority=50)
def play_skill(ctx: Ctx) -> str:
    return play(ctx.group(1) or "", ask=True)


@skill("music.artist", title={"ru": "«Включи <исполнитель>» — сразу играет"},
       patterns={"ru": [r"^(?:джарвис )?(?:включи|поставь|вруби) ([a-zа-яё0-9][\w .'&-]{1,40})$"]},
       examples={"ru": ["Включи G-Eazy", "Поставь Скриптонит"]}, priority=90)
def artist_skill(ctx: Ctx):
    q = ctx.group(1).strip()
    # «включи свет / режим / фокус / звук …» are other commands — only names that aren't Jarvis's own words go here
    if re.match(r"(?:режим|фокус|звук|свет|переводчик|перевод|живой|диктовк|запис|таймер|будильник|компьютер|ноутбук|"
                r"телеграм|ватсап|ютуб|дискорд|стим|браузер|капсул|характер|игру|игровой|wifi|вайфай|блютуз|"
                r"напоминани|функци|озвучк|голос|экран|вентилятор|отчёт|отчет|погод|новост)", q.lower()):
        return None
    return play(q)


core._LONG_OK.update({"music.play", "music.artist"})


def _playing() -> bool:
    try:
        import os

        import pcx
        me = os.getpid()
        return any(s for s in pcx.playing_apps() if s not in ("python.exe", "pythonw.exe"))
    except Exception:  # noqa: BLE001
        return True      # can't tell: behave like the plain media key


@skill("music.pause", title={"ru": "Пауза / продолжить — умно (не включает музыку, если ничего не играет)"},
       patterns={"ru": [r"^(?:джарвис )?(?:пауза|поставь на паузу|стоп музыка|останови музыку|выключи музыку|выключи песню|хватит музыки)$",
                        r"^(?:джарвис )?(?:продолжи|продолжай|играй|сними с паузы|верни музыку)$"]},
       examples={"ru": ["Пауза", "Продолжи"]}, priority=3)
def pause(ctx: Ctx) -> str:
    import keyboard
    resume = bool(re.search(r"продолж|играй|сними с паузы|верни", ctx.norm))
    _play_run["id"] += 1                     # a start that is still in progress must not turn the music on after «стоп»
    try:                                     # Yandex Music in the browser: press its own button
        import uiclick
        import comtypes
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        for h in uiclick.windows_with_title(YANDEX_TITLE):
            st = uiclick.player(h)
            if st["bar"] and st["playing"] != resume:
                uiclick.press(st["bar"])
                return "Продолжаю." if resume else "Пауза."
    except Exception:  # noqa: BLE001
        core.log.exception("yandex pause")
    playing = any(_playing() or time.sleep(0.25) for _ in range(3))      # one quiet moment is not silence
    if resume and playing:
        return "Уже играет, сэр."
    if not resume and not playing:
        return "Сейчас ничего не играет, сэр."
    keyboard.send("play/pause media")
    return "Продолжаю." if resume else "Пауза."



@skill("music.yandex", title={"ru": "«Яндекс Музыка» — спросит, что включить, и включит"},
       patterns={"ru": [r"^(?:джарвис )?(?:открой |запусти |включи |давай )?(?:музыку |музыка )?(?:в |на )?яндекс(?: музык\w*)?$",
                        r"^(?:джарвис )?(?:включи |поставь |давай )?музык\w* (?:в|на|из) яндекс\w*(?: музык\w*)?$"]},
       examples={"ru": ["Яндекс Музыка", "Музыку в Яндекс Музыке"]}, priority=45)
def yandex(ctx: Ctx):
    if ctx.norm.strip() in ("яндекс", "открой яндекс", "запусти яндекс"):
        return None          # that's the browser
    core.save_setting("music", "service", "yandex")      # you said where you listen — remember it
    return play("", ask=True)


@skill("music.press_play", title={"ru": "«Нажми плей» — запустить музыку в открытом плеере"},
       patterns={"ru": [r"^(?:джарвис )?(?:нажми|жми|кликни|тыкни)(?: на)? (?:плей|play|плэй|старт|воспроизведение|кнопку плей)(?: в .+)?$"]},
       examples={"ru": ["Нажми плей"]}, priority=4)
def press_play(ctx: Ctx) -> str:
    import uiclick
    if _playing():
        return "Уже играет, сэр."
    found = uiclick.windows_with_title(r"Яндекс Музык|Yandex Music|YouTube")
    if found and uiclick.click_named(found[0], ["Воспроизведение", "Слушать", "Play", "Смотреть"], timeout=5):
        return "Нажал."
    import keyboard
    keyboard.send("play/pause media")
    return "Нажал плей."


core._LONG_OK.update({"music.press_play", "music.yandex", "music.choice", "music.pause"})
