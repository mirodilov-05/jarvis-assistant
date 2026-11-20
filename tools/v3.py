"""Jarvis V3 tools: per-app volume, Focus Shield, screen translator, window-aware «сохрани это / тише»,
crypto & currency rates, movies & media seek, AI code pilot."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

import core
from tools import tool

S = {"type": "string"}
N = {"type": "number"}


def _notes():
    return sys.modules.get("jarvis_plugin_notes")


# ---------------------------------------------------------------------------
# Sound of a single app
# ---------------------------------------------------------------------------

@tool("app_volume", "Громкость отдельной программы, не трогая остальные: игра, браузер, дискорд, музыка, телеграм… "
      "level — новая громкость 0–100; или change — на сколько изменить (-30 тише, +20 громче); mute — выключить звук.",
      {"app": {**S, "description": "Программа: «игра», «браузер», «дискорд», «музыка» или имя .exe"},
       "level": N, "change": N, "mute": {"type": "boolean"}}, ["app"])
def app_volume(app: str, level: float | None = None, change: float | None = None, mute: bool | None = None) -> str:
    import pcx

    exes = pcx.match_exes(app)
    if not exes:
        return "Не понял, у какой программы менять звук."
    if level is None and change is None and mute is None:
        change = -30
    done = pcx.app_volume(exes, level=None if level is None else level / 100, delta=None if change is None else change / 100,
                          mute=mute)
    if not done:
        return f"«{app}» сейчас не издаёт звук, сэр."
    if mute:
        return "Звук выключен: " + ", ".join(done) + "."
    return "Готово, громкость изменена: " + ", ".join(d.replace(".exe", "") for d in done) + "."


# ---------------------------------------------------------------------------
# Focus Shield
# ---------------------------------------------------------------------------

@tool("focus_shield", "Фокус-щит (анти-прокрастинация): на время работы/учёбы закрывает YouTube, TikTok, Steam и т. п. "
      "start — включить на minutes минут (по умолчанию 50), stop — выключить.",
      {"action": {"type": "string", "enum": ["start", "stop"]}, "minutes": N}, ["action"])
def focus_shield(action: str, minutes: float = 50) -> str:
    import pcx

    return pcx.focus_start(minutes or 50) if action == "start" else pcx.focus_stop()


# ---------------------------------------------------------------------------
# Screen translator
# ---------------------------------------------------------------------------

@tool("translate_screen", "Перевести на русский весь текст в активном окне (игра, документация, японский текст) — "
      "перевод появится плавающей карточкой на экране Джарвиса.")
def translate_screen() -> str:
    import pcx

    try:
        return pcx.translate_screen()
    except Exception as e:  # noqa: BLE001
        return f"Не получилось перевести: {str(e)[:120]}"


# ---------------------------------------------------------------------------
# Context of the active window
# ---------------------------------------------------------------------------

@tool("save_this", "«Сохрани это»: сохранить то, что сейчас на экране, с учётом программы — в браузере ссылку на "
      "страницу, в редакторе кода выделенный фрагмент, в остальных — заголовок окна и скопированный текст.")
def save_this() -> str:
    import pcx

    hwnd, title, exe = pcx.foreground()
    k = pcx.kind(exe)
    notes = _notes()
    if not notes:
        return "Заметки сейчас недоступны."
    if k == "browser":
        url = pcx.copy_from_app(["ctrl+l", "ctrl+c", "esc"])
        if not url.startswith("http"):
            return "Не смог взять ссылку из браузера."
        notes.add_note(f"Ссылка: {title.split(' - ')[0][:120]} — {url}")
        return "Ссылку сохранил, сэр."
    if k == "ide":
        code = pcx.copy_from_app(["ctrl+c"])
        if not code.strip():
            return "Выделите код, сэр, и скажите ещё раз."
        notes.add_note(f"Код из «{title[:80]}»:\n{code[:3000]}")
        return f"Фрагмент кода сохранил, {len(code.splitlines())} строк."
    text = pcx.copy_from_app(["ctrl+c"])
    notes.add_note(f"Из окна «{title[:100]}»" + (f": {text[:2000]}" if text.strip() else ""))
    return "Сохранил, сэр."


@tool("quieter_here", "«Тише» с учётом того, что на экране: в игре убавляет звук только игры, если играет "
      "музыка/видео — только его, иначе — общую громкость.")
def quieter_here() -> str:
    import pcx

    hwnd, title, exe = pcx.foreground()
    target = None
    if core.CONFIG.get("_game_mode") and core.CONFIG.get("_game_exe"):
        target = {core.CONFIG["_game_exe"].lower()}
    elif exe in pcx.playing_apps():
        target = {exe}
    else:
        playing = [p for p in pcx.playing_apps() if p != "python.exe" and p != "pythonw.exe"]
        if playing:
            target = set(playing[:1])
    if target and pcx.app_volume(target, delta=-0.3):
        return "Тише: " + ", ".join(t.replace(".exe", "") for t in target) + "."
    from tools import run_skill
    return run_skill("system.volume_down", "тише")


# ---------------------------------------------------------------------------
# Crypto and currency rates
# ---------------------------------------------------------------------------

def _num(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}".replace(",", " ")


_RATE_CACHE: dict = {}


@tool("rates", "Курсы прямо сейчас: биткоин, эфир, USDT (в долларах) и доллар в рублях и сумах.",
      {"what": {**S, "description": "Что интересует: bitcoin, ethereum, usdt, usd, все (по умолчанию все)"}})
def rates(what: str = "") -> str:
    import concurrent.futures as cf

    import requests

    w = (what or "").lower()
    coins = [c for c, keys in (("bitcoin", ("btc", "бит", "bitcoin")), ("ethereum", ("eth", "эфир", "ether")),
                               ("tether", ("usdt", "тезер", "tether"))) if any(k in w for k in keys)]
    crypto_all = not w or any(x in w for x in ("крипт", "все"))
    want_crypto = crypto_all or bool(coins)
    want_fiat = not w or any(x in w for x in ("usd", "доллар", "рубл", "сум", "uzs", "rub", "все", "валют"))
    coins = coins or ["bitcoin", "ethereum", "tether"]

    def crypto():
        js = requests.get("https://api.coingecko.com/api/v3/simple/price",
                          params={"ids": ",".join(coins), "vs_currencies": "usd", "include_24hr_change": "true"},
                          timeout=4).json()
        out = []
        for cid, name in (("bitcoin", "Биткоин"), ("ethereum", "Эфир"), ("tether", "USDT")):
            if cid in js:
                ch = js[cid].get("usd_24h_change") or 0
                out.append(f"{name} {_num(js[cid]['usd'], 2 if cid == 'tether' else 0)} $"
                           + ("" if cid == "tether" else f" ({'+' if ch >= 0 else ''}{ch:.1f}% за сутки)"))
        return out

    def cached(name, fn, ttl=6 * 3600):   # central-bank rates change once a day
        hit = _RATE_CACHE.get(name)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        val = fn()
        _RATE_CACHE[name] = (time.time(), val)
        return val

    def rub():
        return cached("rub", _rub)

    def uzs():
        return cached("uzs", _uzs)

    def _rub():
        v = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=4).json()["Valute"]["USD"]["Value"]
        return [f"доллар {v:.2f} ₽ по ЦБ РФ"]

    def _uzs():
        v = float(requests.get("https://cbu.uz/ru/arkhiv-kursov-valyut/json/USD/", timeout=4).json()[0]["Rate"])
        return [f"{_num(v)} сумов по ЦБ Узбекистана"]

    jobs = ([crypto] if want_crypto else []) + ([rub, uzs] if want_fiat else [])
    parts = []
    with cf.ThreadPoolExecutor(len(jobs) or 1) as ex:      # all sources at once: the answer takes ~0.5 s, not 9
        for fut in [ex.submit(j) for j in jobs]:
            try:
                parts += fut.result(timeout=5)
            except Exception:  # noqa: BLE001
                pass
    return ("; ".join(parts) + ".") if parts else "Не удалось получить курсы, сэр."


# ---------------------------------------------------------------------------
# Movies & media
# ---------------------------------------------------------------------------

@tool("watch_movie", "Найти фильм или сериал, чтобы посмотреть (откроет поиск на Кинопоиске).", {"title": S}, ["title"])
def watch_movie(title: str) -> str:
    webbrowser.open("https://www.kinopoisk.ru/index.php?kp_query=" + urllib.parse.quote(title))
    return f"Ищу «{title}» на Кинопоиске."


@tool("media_seek", "Перемотать видео/музыку в активном окне вперёд (forward) или назад (back).",
      {"direction": {"type": "string", "enum": ["forward", "back"]}}, ["direction"])
def media_seek(direction: str) -> str:
    import keyboard

    import pcx

    hwnd, title, exe = pcx.foreground()
    if "youtube" in title.lower():
        keyboard.send("l" if direction == "forward" else "j")   # YouTube: 10 seconds
    else:
        keyboard.send("right" if direction == "forward" else "left")
    return "Вперёд." if direction == "forward" else "Назад."


# ---------------------------------------------------------------------------
# AI code pilot (works only inside the workspace folder; running code is confirmed first)
# ---------------------------------------------------------------------------

PILOT = {"last_file": "", "last_output": "", "last_fix": ""}


def workspace() -> Path:
    p = Path(core.setting("codepilot", "workspace", "") or (core.BASE.parent / "workspace"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(path: str) -> Path:
    ws = workspace().resolve()
    p = (ws / path).resolve()
    if ws not in p.parents and p != ws:
        raise ValueError("файл должен быть внутри папки workspace")
    return p


def _gen_code(task: str, filename: str, context: str = "") -> str:
    import re

    import cloud

    out = cloud.ask("Ты опытный программист. Верни ТОЛЬКО содержимое файла целиком, без пояснений и без ``` .",
                    [{"role": "user", "content": f"Файл: {filename}\nЗадача: {task}\n{context}"}], max_tokens=3000)
    return re.sub(r"^```\w*\n|\n```\s*$", "", out.strip())


@tool("code_create_file", "Код-пилот: написать новый файл с кодом в папке workspace по описанию задачи.",
      {"filename": {**S, "description": "Имя файла, например «parser.py»"},
       "task": {**S, "description": "Что должен делать код"}}, ["filename", "task"])
def code_create_file(filename: str, task: str) -> str:
    p = _safe(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_gen_code(task, filename), encoding="utf-8")
    PILOT["last_file"] = str(p)
    core.emit({"type": "code", "file": str(p), "action": "created"})
    return f"Файл {p.name} готов: {len(p.read_text(encoding='utf-8').splitlines())} строк. Запустить?"


@tool("code_run", "Код-пилот: запустить скрипт из папки workspace (python, node, powershell) и прочитать вывод/ошибку.",
      {"filename": {**S, "description": "Имя файла; пусто — последний созданный"}}, tier="confirm",
      confirm_text=lambda filename="": f"запустить {filename or Path(PILOT['last_file']).name or 'скрипт'}")
def code_run(filename: str = "") -> str:
    p = _safe(filename) if filename else Path(PILOT["last_file"] or "")
    if not p.is_file():
        return "Не нашёл такой файл в workspace."
    cmd = {".py": [sys.executable.replace("pythonw.exe", "python.exe"), str(p)], ".js": ["node", str(p)],
           ".ps1": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(p)]}.get(p.suffix)
    if not cmd:
        return "Такие файлы я не запускаю."
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=p.parent, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)
        out, ok = (r.stdout + r.stderr)[-4000:], r.returncode == 0
    except subprocess.TimeoutExpired:
        out, ok = "Превышено время 60 с.", False
    PILOT.update(last_file=str(p), last_output=out)
    core.emit({"type": "code", "file": str(p), "action": "run", "ok": ok, "output": out[-1500:]})
    if ok:
        return f"Выполнено за {time.time() - t0:.1f} с без ошибок."
    last = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or ["неизвестная ошибка"]
    return f"Ошибка: {last[0][:160]}. Сказать, как исправить?"


@tool("code_fix", "Код-пилот: разобрать последнюю ошибку запуска и исправить файл (исправление записывается после подтверждения).",
      tier="confirm", confirm_text=lambda: "исправить файл " + (Path(PILOT["last_file"]).name or ""))
def code_fix() -> str:
    p = Path(PILOT["last_file"] or "")
    if not p.is_file() or not PILOT["last_output"]:
        return "Сначала запустите скрипт, сэр."
    old = p.read_text(encoding="utf-8")
    new = _gen_code("Исправь ошибку, не меняя остальное поведение.", p.name,
                    f"Текущий код:\n{old}\n\nВывод запуска:\n{PILOT['last_output'][-2500:]}")
    p.with_suffix(p.suffix + ".bak").write_text(old, encoding="utf-8")
    p.write_text(new, encoding="utf-8")
    core.emit({"type": "code", "file": str(p), "action": "fixed"})
    return f"Исправил {p.name}, старая версия в {p.name}.bak. Запустить снова?"
