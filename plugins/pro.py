"""Jarvis «Pro»: system doctor, clipboard intelligence, web answers, voice-created macros,
YouTube packer, Japanese breakdown, git commit & push. Everything here answers instantly by regex and uses the
cloud brain only for the text it has to write."""

from __future__ import annotations

import ctypes
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import core
from core import Ctx, ask_confirm, skill

NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _llm():
    return sys.modules.get("jarvis_plugin_llm")


WRITER = "Ты точный помощник. Строго следуй формату из запроса. Не выдумывай фактов."


def _write(prompt: str, max_tokens: int = 500) -> str:
    """Ask the brain for a piece of text in the requested format (not the short spoken character style)."""
    import cloud
    msgs = [{"role": "user", "content": prompt}]
    if cloud.enabled():
        try:
            return cloud.ask(WRITER, msgs, max_tokens).strip()
        except Exception as e:  # noqa: BLE001
            core.log.warning("pro writer cloud failed: %s", e)
            if not cloud.local_fallback():
                return "Нет связи с облачным мозгом, сэр."
    llm = _llm()
    if not llm:
        return ""
    try:
        if llm.provider() == "claude":
            return llm._ask_claude(WRITER, msgs, max_tokens).strip()
        return llm._ask_local(WRITER, msgs, max_tokens).strip()
    except Exception as e:  # noqa: BLE001
        return "Мозг недоступен: " + str(e)[:80]


def card(title: str, text: str, ttl: int = 0) -> None:
    core.emit({"type": "card", "title": title, "text": text, "ttl": ttl})


def _first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n])


# ---------------------------------------------------------------------------
# Clipboard helpers
# ---------------------------------------------------------------------------

def get_clipboard() -> str:
    import pcx
    return (pcx.clipboard() or "").strip()


def set_clipboard(text: str) -> bool:
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    data = text.encode("utf-16-le") + b"\0\0"
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(0x0042, len(data))       # GMEM_MOVEABLE | GMEM_ZEROINIT
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(13, h)                  # CF_UNICODETEXT
        return True
    finally:
        u32.CloseClipboard()


# ---------------------------------------------------------------------------
# System doctor
# ---------------------------------------------------------------------------

def diagnostics() -> tuple[str, str]:
    """(spoken summary, full card text)."""
    import psutil
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except Exception:  # noqa: BLE001
            pass
    cpu = psutil.cpu_percent(interval=0.6)
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            name = p.info["name"] or "?"
            if name.lower() in ("system idle process", "idle"):
                continue
            procs.append((p.cpu_percent(None) / psutil.cpu_count(), (p.info["memory_info"].rss if p.info["memory_info"] else 0) / 2**20, name))
        except Exception:  # noqa: BLE001
            continue
    by_cpu = sorted(procs, reverse=True)[:3]
    by_ram = sorted(procs, key=lambda x: x[1], reverse=True)[:3]
    ram = psutil.virtual_memory()
    disks = []
    for d in ("C:\\", "D:\\"):
        try:
            u = psutil.disk_usage(d)
            disks.append(f"{d[0]}: свободно {u.free / 2**30:.0f} из {u.total / 2**30:.0f} ГБ")
        except Exception:  # noqa: BLE001
            pass
    batt = psutil.sensors_battery()
    batt_s = f"{batt.percent:.0f}%{' · заряжается' if batt.power_plugged else ' · от батареи'}" if batt else "нет батареи"
    gpu_s = ""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3,
                             creationflags=NO_WINDOW).stdout.strip().splitlines()[0]
        util, used, total, temp = [x.strip() for x in out.split(",")]
        gpu_s = f"Видеокарта: {util}% · {int(used) / 1024:.1f} из {int(total) / 1024:.1f} ГБ · {temp}°C"
    except Exception:  # noqa: BLE001
        pass
    lines = [f"Процессор: {cpu:.0f}%", f"Память: {ram.percent:.0f}% ({ram.used / 2**30:.1f} из {ram.total / 2**30:.1f} ГБ)"]
    if gpu_s:
        lines.append(gpu_s)
    lines += disks + [f"Батарея: {batt_s}", "",
                      "Больше всего процессора: " + ", ".join(f"{n} {c:.0f}%" for c, _, n in by_cpu),
                      "Больше всего памяти: " + ", ".join(f"{n} {m:.0f} МБ" for _, m, n in by_ram)]
    worst = by_cpu[0] if by_cpu and by_cpu[0][0] > 15 else None
    spoken = f"Процессор {cpu:.0f}%, память {ram.percent:.0f}%. "
    spoken += f"Больше всего грузит {worst[2].replace('.exe', '')}, {worst[0]:.0f}% процессора." if worst else \
        f"Больше всего памяти у {by_ram[0][2].replace('.exe', '')}." if by_ram else ""
    low_disk = [d for d in disks if re.search(r"свободно (\d+)", d) and int(re.search(r"свободно (\d+)", d).group(1)) < 15]
    if low_disk:
        spoken += " Мало места: " + low_disk[0].split(":")[0] + "."
    return spoken, "\n".join(lines)


@skill("pro.doctor", title={"ru": "Проверить систему: что грузит компьютер"},
       patterns={"ru": [r"(?:проверь|продиагностируй|диагностика) (?:систем\w*|компьютер\w*|комп\w*|ноутбук\w*|пк)",
                        r"что (?:грузит|тормозит|жрёт|жрет|ест) (?:комп\w*|систему|ноутбук|пк|процессор|память)",
                        r"почему (?:комп\w*|ноутбук|пк) (?:тормозит|лагает|греется)", r"^(?:диагностика|статус системы|состояние системы)$"]},
       examples={"ru": ["Проверь систему", "Что грузит комп?"]}, priority=5)
def doctor(ctx: Ctx) -> str:
    spoken, full = diagnostics()
    card("Диагностика системы", full, 40000)
    return spoken


@skill("pro.kill", title={"ru": "Закрыть зависшую программу (с подтверждением)"},
       patterns={"ru": [r"(?:убей|заверши|закрой принудительно|снять задачу|сними задачу)(?: процесс| программу)? (.+)$"]},
       examples={"ru": ["Убей процесс chrome"]}, priority=6)
def kill(ctx: Ctx) -> str:
    import psutil
    name = ctx.group(1).strip().lower().removesuffix(".exe")
    found = sorted({p.info["name"] for p in psutil.process_iter(["name"])
                    if p.info["name"] and name in p.info["name"].lower()})
    if not found:
        return f"Не нашёл процесс «{name}», сэр."
    if any(x.lower() in ("explorer.exe", "csrss.exe", "winlogon.exe", "svchost.exe", "lsass.exe") for x in found):
        return "Это системный процесс, его лучше не трогать, сэр."

    def do() -> str:
        r = subprocess.run(["taskkill", "/F", "/IM", found[0]], capture_output=True, text=True, creationflags=NO_WINDOW)
        return f"Закрыл {found[0]}." if r.returncode == 0 else f"Не получилось закрыть {found[0]}."

    return ask_confirm(ctx, f"Принудительно закрыть {found[0]}? Несохранённое пропадёт. Да или нет?", do)


# ---------------------------------------------------------------------------
# Clipboard intelligence (reads the clipboard only when you ask)
# ---------------------------------------------------------------------------

_BUF = r"(?:из буфера|в буфере|скопированн\w*|что я скопировал|буфер\w*)"


@skill("pro.clip_summary", title={"ru": "Вкратце: выжимка из скопированного текста"},
       patterns={"ru": [r"^(?:джарвис )?(?:вкратце|кратко|в двух словах)$", r"(?:сократи|перескажи|выжимк\w*|суть|кратко)\s*" + _BUF,
                        r"(?:сократи|перескажи) (?:текст|статью)$"]},
       examples={"ru": ["Вкратце", "Перескажи скопированное"]}, priority=5)
def clip_summary(ctx: Ctx) -> str:
    text = get_clipboard()
    if len(text) < 80:
        return "Скопируйте текст (Ctrl+C), сэр, и скажите «вкратце»."
    out = _write("Сделай выжимку текста ниже на русском: ровно три коротких главных тезиса, каждый с новой строки, "
                 "без нумерации и вступлений.\n\nТЕКСТ:\n" + text[:12000], 350)
    card("Вкратце", out, 60000)
    return out


@skill("pro.clip_translate", title={"ru": "Перевести скопированный текст"},
       patterns={"ru": [r"переведи\s*" + _BUF, r"переведи (?:то )?что (?:я )?скопировал"]},
       examples={"ru": ["Переведи из буфера"]}, priority=5)
def clip_translate(ctx: Ctx) -> str:
    text = get_clipboard()
    if not text:
        return "Буфер обмена пуст, сэр."
    russian = len(re.findall(r"[а-яё]", text.lower())) > len(text) * 0.4
    target = "английский" if russian else "русский"
    out = _write(f"Переведи текст на {target} язык. Выведи только перевод.\n\nТЕКСТ:\n{text[:8000]}", 900)
    card(f"Перевод на {target}", out, 0)
    return _first_sentences(out, 2) if len(out) > 220 else out


_ERRORS = re.compile(r"(traceback|error|exception|failed|fatal|ошибк|не удалось|errno|stack trace|cannot|undefined|denied)", re.I)


@skill("pro.clip_fix", title={"ru": "Как исправить скопированную ошибку"},
       patterns={"ru": [r"(?:как (?:это |её |ее )?исправить|что (?:это )?за ошибка|почему (?:ошибка|не работает)|как починить)\??$"]},
       examples={"ru": ["Как это исправить?"]}, priority=8)
def clip_fix(ctx: Ctx):
    text = get_clipboard()
    if not text or not _ERRORS.search(text):
        return None    # nothing error-like copied: let the brain / vision answer
    out = _write("Ниже ошибка из терминала или программы. По-русски: 1) в одной фразе — в чём причина; "
                 "2) точная команда или правка, которая её исправит. Коротко, без воды.\n\nОШИБКА:\n" + text[-6000:], 450)
    card("Как исправить", out, 0)
    return _first_sentences(out, 2)


@skill("pro.clip_link", title={"ru": "Сохранить скопированную ссылку"},
       patterns={"ru": [r"(?:сохрани|запомни|запиши) (?:эту |скопированную )?ссылку(?: из буфера)?$"]},
       examples={"ru": ["Сохрани ссылку"]}, priority=4)
def clip_link(ctx: Ctx) -> str:
    text = get_clipboard()
    m = re.search(r"https?://\S+", text)
    if not m:
        import tools.v3 as v3
        return v3.save_this()          # nothing copied: take the link from the browser on screen
    notes = sys.modules.get("jarvis_plugin_notes")
    if notes:
        notes.add_note("Ссылка: " + m.group(0))
    return "Ссылку сохранил, сэр."


# ---------------------------------------------------------------------------
# Answers from the web (DuckDuckGo results + the brain)
# ---------------------------------------------------------------------------

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def gemini_search(question: str) -> tuple[str, list[tuple[str, str]]] | None:
    """Fresh answer from Gemini with Google Search grounding (needs the free Gemini key). -> (answer, [(title, url)])"""
    import cloud
    import requests
    if not cloud.has("gemini"):
        return None
    model = cloud.setting("gemini_model", "gemini-2.5-flash")
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": cloud.key("gemini"), "Content-Type": "application/json"},
                      json={"contents": [{"parts": [{"text": f"Сегодня {core.now():%d.%m.%Y}. Ответь по-русски одним-двумя "
                                                             f"предложениями, только проверенные факты: {question}"}]}],
                            "tools": [{"google_search": {}}]}, timeout=25)
    if r.status_code != 200:
        core.log.warning("gemini search %s: %s", r.status_code, r.text[:200])
        return None
    cand = (r.json().get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", [])).strip()
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    links = [(c["web"].get("title", ""), c["web"].get("uri", "")) for c in chunks if c.get("web")][:4]
    return (text, links) if text else None


def wiki_snippets(query: str, n: int = 3) -> list[tuple[str, str, str]]:
    import requests
    api = "https://ru.wikipedia.org/w/api.php"
    head = {"User-Agent": "JarvisAssistant/3.0 (personal voice assistant)"}
    found = requests.get(api, params={"action": "query", "list": "search", "srsearch": query, "format": "json",
                                      "srlimit": n}, headers=head, timeout=8).json()["query"]["search"]
    if not found:
        return []
    titles = "|".join(x["title"] for x in found)
    pages = requests.get(api, params={"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
                                      "titles": titles, "format": "json", "exchars": 1200}, headers=head,
                         timeout=8).json()["query"]["pages"].values()
    return [(p["title"], "https://ru.wikipedia.org/wiki/" + p["title"].replace(" ", "_"), p.get("extract", ""))
            for p in pages if p.get("extract")]


def web_snippets(query: str, n: int = 6) -> list[tuple[str, str, str]]:
    import html as h

    import requests
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "ru-ru"}, headers=UA, timeout=8)
    if r.status_code != 200:          # DuckDuckGo sometimes answers bots with a challenge page
        return wiki_snippets(query)
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
                         r.text, re.S):
        url, title, snip = m.groups()
        if "uddg=" in url:
            from urllib.parse import parse_qs, unquote, urlparse
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
        clean = lambda s: h.unescape(re.sub(r"<.*?>", "", s)).strip()
        out.append((clean(title), url, clean(snip)))
        if len(out) >= n:
            break
    return out or wiki_snippets(query)


@skill("pro.web_answer", title={"ru": "Узнать в интернете и ответить голосом"},
       patterns={"ru": [r"^(?:джарвис )?(?:узнай|выясни|разузнай|загугли|погугли)(?: в интернете| в сети)?,? (.+)$",
                        r"^(?:джарвис )?найди (?:в интернете |в сети )?(?:ответ|информацию|инфу)(?: на вопрос| о| про)? (.+)$"]},
       examples={"ru": ["Узнай, когда выходит GTA 6", "Найди ответ: высота Эвереста"]}, priority=6)
def web_answer(ctx: Ctx) -> str:
    q = ctx.group(1).strip(" ?.")
    try:
        g = gemini_search(q)
    except Exception as e:  # noqa: BLE001
        core.log.warning("gemini search failed: %s", e)
        g = None
    if g:
        text, links = g
        card("Из интернета · " + q[:40], text + "\n\n" + "\n".join(f"• {t}: {u}" for t, u in links), 60000)
        return _first_sentences(text, 2)
    try:
        res = web_snippets(q)
    except Exception as e:  # noqa: BLE001
        return f"Интернет не ответил: {str(e)[:80]}"
    if not res:
        return f"Ничего не нашёл про «{q}», сэр."
    src = "\n".join(f"[{i + 1}] {t} — {s} ({u})" for i, (t, u, s) in enumerate(res))
    out = _write(f"Вопрос: {q}\n\nРезультаты поиска на сегодня ({core.now():%d.%m.%Y}):\n{src}\n\n"
                 "Ответь по-русски одним-двумя предложениями только по этим результатам. Если в них нет ответа — так и скажи.", 220)
    card("Из интернета · " + q[:40], out + "\n\n" + "\n".join(f"• {t}: {u}" for t, u, _ in res[:4]), 60000)
    return out


# ---------------------------------------------------------------------------
# Macros created by voice
# ---------------------------------------------------------------------------

@skill("pro.macro_create", title={"ru": "Создать макрос голосом"},
       patterns={"ru": [r"(?:запомни|создай|сохрани|добавь) (?:команду|макрос) [«\"']?(.+?)[»\"']?\s*[:—–-]\s*(.+)$"]},
       examples={"ru": ["Запомни команду «Вечерний чилл»: открой ютуб, громкость 30, режим отдых"]}, priority=3)
def macro_create(ctx: Ctx) -> str:
    raw = ctx.text
    m = re.search(r"(?:команду|макрос)\s+[«\"']?(.+?)[»\"']?\s*[:—–-]\s*(.+)$", raw, re.I)
    phrase, body = (m.group(1), m.group(2)) if m else (ctx.group(1), ctx.group(2))
    steps = [s.strip(" .") for s in re.split(r",|;|\s+(?:и|а потом|потом|затем)\s+", body) if s.strip(" .")]
    if not steps:
        return "Скажите так: запомни команду «название»: действие, действие."
    actions = []
    for s in steps:
        vol = re.fullmatch(r"(?:убавь |поставь |сделай )?громкост\w*(?: до| на)? (\d+)%?", s.lower())
        actions.append({"type": "volume", "value": vol.group(1)} if vol else {"type": "command", "value": s})
    macros = sys.modules.get("jarvis_plugin_macros")
    if not macros:
        return "Макросы сейчас недоступны."
    macros.upsert({"phrase": phrase.strip(), "reply": "", "actions": actions})
    return f"Запомнил команду «{phrase.strip()}»: {len(actions)} действий. Скажите её — выполню."


# ---------------------------------------------------------------------------
# YouTube packer
# ---------------------------------------------------------------------------

@skill("pro.youtube_pack", title={"ru": "Упаковать видео для YouTube: заголовок, описание, теги в буфер"},
       patterns={"ru": [r"(?:упакуй|оформи|подготовь упаковку|сделай упаковку)(?: для)? (?:видео|ролик\w*|шортс\w*|shorts|клип\w*)\s*(?:про|о|об|на тему)?\s*(.+)$"]},
       examples={"ru": ["Упакуй видео про мой сетап для CS2"]}, priority=5)
def youtube_pack(ctx: Ctx) -> str:
    topic = ctx.group(1).strip(" .")
    shorts = bool(re.search(r"шортс|shorts", ctx.norm))
    out = _write(
        f"You are a YouTube growth expert. Video topic (described in Russian): «{topic}». "
        f"{'It is a YouTube Shorts video. ' if shorts else ''}"
        "Write in ENGLISH, exactly in this format and nothing else:\n"
        "TITLE: <one clickable title, 60–95 characters, no clickbait lies, no quotes>\n"
        "DESCRIPTION:\n<SEO description: 2 short paragraphs (hook + what viewers get), then 3–5 relevant hashtags>\n"
        "TAGS: <15–20 comma-separated search tags, most important first>", 700)
    title = re.search(r"TITLE:\s*(.+)", out)
    set_clipboard(out.strip())
    card("YouTube · упаковка (уже в буфере)", out, 0)
    return ("Готово, сэр. Заголовок: " + title.group(1).strip() + ". Всё в буфере обмена, вставляйте Ctrl+V.") if title \
        else "Упаковка в буфере обмена, сэр."


# ---------------------------------------------------------------------------
# Japanese breakdown (clipboard text or the screen)
# ---------------------------------------------------------------------------

JP_GUIDE = ("Ты учитель японского для русскоговорящего ученика уровня N4→N3. Для японского текста выведи по-русски:\n"
            "1) Текст и чтение хираганой.\n2) Кандзи: каждый — чтение и значение.\n"
            "3) Грамматика уровня N3–N2, которая тут встречается, — коротко.\n4) Перевод на русский.\n"
            "Без лишних слов. Если японского текста нет — так и скажи.")


@skill("pro.japanese", title={"ru": "Разобрать японскую фразу (кандзи, чтение, грамматика)"},
       patterns={"ru": [r"(?:разбери|объясни|разжуй) (?:эту |этот )?(?:японск\w* )?(?:фразу|предложение|текст|кандзи|иероглиф\w*)(?: на экране| из буфера)?$",
                        r"разбери японский"]},
       examples={"ru": ["Разбери эту фразу", "Разбери японский"]}, priority=5)
def japanese(ctx: Ctx) -> str:
    text = get_clipboard()
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text or "") and "экран" not in ctx.norm:
        out = _write(JP_GUIDE + "\n\nТЕКСТ:\n" + text[:2000], 900)
    else:
        import base64

        import cloud
        import vision
        title, img = vision.capture()
        if vision._is_blank(img):
            return "Окно для меня чёрное, сэр. Скопируйте фразу (Ctrl+C) и скажите ещё раз."
        try:
            out = cloud.look(JP_GUIDE, "Разбери японский текст на экране.",
                             base64.b64encode(vision.png(vision.shrink(img))).decode(), max_tokens=900)
        except Exception as e:  # noqa: BLE001
            return f"Для экрана нужен ключ Gemini. Или скопируйте фразу и скажите «разбери эту фразу». ({str(e)[:60]})"
    card("Японский · разбор", out, 0)
    plain = re.sub(r"[*#_`]+", "", out)
    tr = re.search(r"Перевод[^\n:]*:\s*(.+)", plain) or re.search(r"Перевод[^\n]*\n\s*(.+)", plain)
    return ("Разбор в окне, сэр. Перевод: " + tr.group(1).strip()[:200]) if tr else "Разбор в окне, сэр."


# ---------------------------------------------------------------------------
# Git: commit & push by voice (always confirmed)
# ---------------------------------------------------------------------------

def repo_dir() -> Path:
    return Path(core.setting("codepilot", "repo", "") or core.BASE)


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_dir(), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW)


@skill("pro.git", title={"ru": "Git: коммит и пуш голосом (с подтверждением)"},
       patterns={"ru": [r"(?:сделай|создай) коммит(?: и (?:пуш|запушь|отправь))?", r"закомм?ить(?: и (?:запушь|отправь))?",
                        r"^(?:джарвис )?(?:запушь|пушни)(?: код| изменения)?$"]},
       examples={"ru": ["Сделай коммит и пуш"]}, priority=5)
def git_commit(ctx: Ctx) -> str:
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return f"Папка {repo_dir()} — не git-репозиторий. Укажите репозиторий в config.toml → [codepilot] repo."
    status = _git("status", "--porcelain").stdout.strip()
    push = bool(re.search(r"пуш|запуш|отправ", ctx.norm))
    if not status:
        if push:
            ahead = _git("rev-list", "--count", "@{u}..HEAD").stdout.strip()
            if ahead and ahead != "0":
                return ask_confirm(ctx, f"Изменений нет, но {ahead} коммитов не отправлено. Отправить? Да или нет?",
                                   lambda: _push())
        return "Нечего коммитить, всё чисто, сэр."
    diff = (_git("diff", "HEAD", "--stat").stdout + "\n" + _git("diff", "HEAD").stdout)[:7000]
    untracked = [ln[3:] for ln in status.splitlines() if ln.startswith("??")][:20]
    msg = _write("Write one git commit message in English for these changes: a short imperative subject line "
                 "(max 72 chars), then an empty line, then up to 4 bullet points. Output only the message.\n\n"
                 f"New files: {untracked}\n\nDIFF:\n{diff}", 220).strip().strip("`")
    if not msg:
        return "Не получилось составить сообщение коммита."
    subject = msg.splitlines()[0][:90]
    files = len(status.splitlines())

    def do() -> str:
        _git("add", "-A")
        r = _git("commit", "-m", msg)
        if r.returncode != 0:
            return "Коммит не прошёл: " + (r.stderr or r.stdout)[-200:]
        return "Закоммитил. " + (_push() if push else "Пуш — по команде «запушь».")

    card("Git · коммит", f"{repo_dir()}\nФайлов: {files}\n\n{msg}", 0)
    return ask_confirm(ctx, f"Коммит «{subject}», файлов {files}{' и пуш' if push else ''}. Да или нет?", do)


def _push() -> str:
    r = _git("push", timeout=120)
    return "Отправил в репозиторий." if r.returncode == 0 else "Пуш не прошёл: " + (r.stderr or r.stdout)[-200:]


# ---------------------------------------------------------------------------

core._LONG_OK.update({"pro.web_answer", "pro.macro_create", "pro.youtube_pack", "pro.kill", "pro.japanese"})
