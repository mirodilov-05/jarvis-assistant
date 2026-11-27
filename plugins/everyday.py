"""Everyday phrases that used to go wrong: «ты здесь?», «спасибо», browser tabs, Wi-Fi check.

  «Джарвис, ты здесь?»                         — «На месте, сэр.»
  «Закрой вкладку», «Закрой три вкладки», «Верни вкладку», «Новая вкладка», «Следующая вкладка»
  «Проверь вайфай», «Диагностика интернета»    — network, signal, ping, what is wrong
"""

from __future__ import annotations

import ctypes
import random
import re
import subprocess
import time

import core
from core import Ctx, skill

NO_WINDOW = 0x08000000
NUM = {"одну": 1, "один": 1, "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
       "девять": 9, "десять": 10}


@skill("everyday.here", title={"ru": "«Ты здесь?», «Спасибо»"},
       patterns={"ru": [r"^(?:джарвис )?(?:ты (?:здесь|тут|на связи|на месте|меня слышишь)|(?:слышишь|видишь) меня|на связи|прием)(?: джарвис)?$"]},
       examples={"ru": ["Джарвис, ты здесь?"]}, priority=4)
def here(ctx: Ctx) -> str:
    return random.choice(["На месте, сэр.", "Здесь, сэр. Слушаю.", "На связи, сэр.", "Всегда на связи, сэр."])


@skill("everyday.thanks", title={"ru": "«Спасибо» — короткий ответ"},
       patterns={"ru": [r"^(?:отлично |супер |круто )?(?:спасибо|благодарю|спс)(?: большое| тебе| джарвис| сэр)*$"]},
       examples={"ru": ["Спасибо, Джарвис"]}, priority=4)
def thanks(ctx: Ctx) -> str:
    return random.choice(["Всегда пожалуйста, сэр.", "Рад помочь, сэр.", "Обращайтесь, сэр."])


# ---------------------------------------------------------------------------
# Browser tabs
# ---------------------------------------------------------------------------

def browser_window() -> int | None:
    """The browser in front; if another program is in front, the topmost visible browser window."""
    import pcx
    hwnd, _, exe = pcx.foreground()
    if exe in pcx.BROWSERS:
        return hwnd
    u32 = ctypes.windll.user32
    found: list[tuple[bool, int]] = []

    def cb(h, _l):
        if u32.IsWindowVisible(h) and u32.GetWindowTextLengthW(h):
            pid = ctypes.c_ulong()
            u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            try:
                import psutil
                if psutil.Process(pid.value).name().lower() in pcx.BROWSERS:
                    found.append((bool(u32.IsIconic(h)), h))     # a minimised browser counts too, after the open ones
            except Exception:  # noqa: BLE001
                pass
        return True
    u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
    found.sort(key=lambda x: x[0])
    return found[0][1] if found else None


def to_front(hwnd: int) -> None:
    u32 = ctypes.windll.user32
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)          # SW_RESTORE: a minimised browser comes back first
        time.sleep(0.2)
    if u32.GetForegroundWindow() == hwnd:
        return
    u32.keybd_event(0x12, 0, 0, 0)      # a tap of Alt lets a background app bring a window forward
    u32.keybd_event(0x12, 0, 2, 0)
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.25)


def tabs(action: str, count: int = 1) -> str:
    import keyboard
    hwnd = browser_window()
    if not hwnd:
        return "Браузер не открыт, сэр."
    to_front(hwnd)
    if ctypes.windll.user32.GetForegroundWindow() != hwnd:
        return "Не смог переключиться на браузер, сэр. Вкладки не трогал."      # never press Ctrl+W in another program
    combo = {"close": "ctrl+w", "reopen": "ctrl+shift+t", "new": "ctrl+t", "next": "ctrl+tab", "prev": "ctrl+shift+tab"}[action]
    count = max(1, min(10, count))
    for _ in range(count):
        if ctypes.windll.user32.GetForegroundWindow() != hwnd:
            break
        keyboard.send(combo)
        time.sleep(0.15)
    if action == "close":
        n = "вкладку" if count == 1 else f"{count} вкладки" if 2 <= count <= 4 else f"{count} вкладок"
        return f"Закрыл {n}. Вернуть — «верни вкладку»."
    return {"reopen": "Вернул вкладку.", "new": "Новая вкладка.", "next": "Следующая.", "prev": "Предыдущая."}[action]


@skill("everyday.tabs", title={"ru": "Вкладки браузера: закрыть, вернуть, новая, следующая"},
       patterns={"ru": [
           r"^(?:джарвис )?(?P<a>закрой|убери) (?:(?:эту|текущую|последнюю|последние) )?(?:(?P<n>\d+|одну|две|три|четыре|пять|шесть|семь|восемь|девять|десять) )?вкладк\w*(?: (?:в|из) .+)?$",
           r"^(?:джарвис )?(?P<a>верни|восстанови|открой) (?:(?:последнюю|закрытую) ){1,2}вкладк\w*$",
           r"^(?:джарвис )?(?P<a>верни|восстанови) (?:(?P<n>\d+|две|три|четыре|пять) )?вкладк\w*$",
           r"^(?:джарвис )?(?P<a>новая|открой новую|следующая|предыдущая) вкладк\w*$"]},
       examples={"ru": ["Закрой вкладку", "Закрой три вкладки", "Верни вкладку", "Следующая вкладка"]}, priority=5)
def tabs_skill(ctx: Ctx) -> str:
    g = ctx.match.groupdict()
    a, n = g["a"], g.get("n")
    count = int(n) if n and n.isdigit() else NUM.get(n or "", 1)
    action = ("close" if a in ("закрой", "убери") else "reopen" if a in ("верни", "восстанови", "открой")
              else "new" if "нов" in a else "next" if a.startswith("след") else "prev")
    return tabs(action, count)


# ---------------------------------------------------------------------------
# Wi-Fi / internet check
# ---------------------------------------------------------------------------

def _run(*cmd: str, timeout: int = 12) -> str:
    try:
        return subprocess.run(list(cmd), capture_output=True, timeout=timeout, creationflags=NO_WINDOW).stdout.decode("cp866", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _ping(host: str) -> tuple[int | None, int]:
    """(average ms, lost %) of 4 pings."""
    out = _run("ping", "-n", "4", "-w", "1500", host)
    ms = [int(x) for x in re.findall(r"(?:время|time)[=<](\d+)", out)]
    return (round(sum(ms) / len(ms)) if ms else None), round(100 * (4 - len(ms)) / 4)


def network_report() -> str:
    out = _run("netsh", "wlan", "show", "interfaces")
    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
    signal = re.search(r"(\d+)%", out)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(3) as ex:
        net, gw = ex.submit(_ping, "1.1.1.1"), None
        m = re.search(r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", _run("route", "print", "-4", "0.0.0.0"))
        if m:
            gw = ex.submit(_ping, m[1])
        dns_ok = ex.submit(_dns)
        ms, lost = net.result()
        gw_ms, gw_lost = gw.result() if gw else (None, 100)
        dns = dns_ok.result()
    parts = []
    if ssid:
        parts.append(f"Вайфай «{ssid[1].strip()}»" + (f", сигнал {signal[1]} процентов" if signal else ""))
    else:
        parts.append("Вайфай не подключён" + (", но есть кабель" if gw_ms is not None else ""))
    if ms is not None:
        parts.append(f"интернет отвечает за {ms} миллисекунд" + (f", потерь {lost} процентов" if lost else ", без потерь"))
    else:
        parts.append("интернет не отвечает")
    if ms is None and gw_ms is not None:
        parts.append("роутер работает, проблема у провайдера")
    elif ms is None:
        parts.append("роутер тоже не отвечает: проверьте вайфай или перезагрузите роутер")
    elif not dns:
        parts.append("сайты не открываются по имени, проблема с DNS")
    elif gw_ms is not None and gw_ms > 40:
        parts.append(f"до роутера {gw_ms} миллисекунд — это много, подойдите ближе к роутеру")
    elif signal and int(signal[1]) < 45:
        parts.append("сигнал слабый, подойдите ближе к роутеру")
    elif ms > 150 or lost:
        parts.append("связь неустойчивая")
    else:
        parts.append("всё в порядке")
    return ". ".join(p[0].upper() + p[1:] for p in parts) + "."


def _dns() -> bool:
    import socket
    try:
        socket.getaddrinfo("ya.ru", 443)
        return True
    except OSError:
        return False


@skill("everyday.network", title={"ru": "Проверить вайфай и интернет"},
       patterns={"ru": [r"(?:проверь|диагностик\w*|проверка|что с|как там)\s(?:\w+ )?(?:вайфа\w*|вай фа\w*|wi fi|wifi|wi-fi|интернет\w*|сет[ьи]|пинг\w*)",
                        r"(?:почему|что).{0,20}(?:интернет|вайфай|wi fi|wifi).{0,15}(?:не работает|тормозит|медленн\w*|плох\w*|лагает)",
                        r"^(?:какой )?пинг$",
                        r"^(?:почему )?(?:тормозит|лагает|медленно работает|медленный) (?:интернет|вайфай|вай фай|wi fi|wifi|сеть)$"]},
       examples={"ru": ["Проверь вайфай", "Почему тормозит интернет"]}, priority=5)
def network(ctx: Ctx) -> str:
    return network_report()


core._LONG_OK.update({"everyday.tabs", "everyday.network"})
