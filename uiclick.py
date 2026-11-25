"""Press buttons inside any window like a person would — via Windows UI Automation (no screen coordinates, no
browser extensions). Used to start Yandex Music in your browser: «Воспроизведение» is a real button on the page."""

from __future__ import annotations

import ctypes
import time

_uia: dict = {}


def _api():
    if "uia" not in _uia:
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        mod = comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        _uia["mod"] = mod
        _uia["uia"] = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
    return _uia["uia"], _uia["mod"]


def windows_with_title(pattern: str) -> list[int]:
    import re
    u32 = ctypes.windll.user32
    found = []

    def cb(h, _l):
        if u32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(512)
            u32.GetWindowTextW(h, buf, 512)
            if re.search(pattern, buf.value, re.I):
                found.append(h)
        return True
    u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
    return found


def click_named(hwnd: int, names: list[str], timeout: float = 12.0) -> str | None:
    """Find the first element in the window whose name is one of `names` and press it. Returns the name pressed."""
    import comtypes
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    uia, m = _api()
    root = uia.ElementFromHandle(hwnd)
    end = time.time() + timeout
    while time.time() < end:
        for name in names:
            cond = uia.CreatePropertyCondition(m.UIA_NamePropertyId, name)
            el = root.FindFirst(m.TreeScope_Descendants, cond)
            if el:
                try:
                    inv = el.GetCurrentPattern(m.UIA_InvokePatternId).QueryInterface(m.IUIAutomationInvokePattern)
                    inv.Invoke()
                    return name
                except Exception:  # noqa: BLE001 - not invokable: try a real click on its centre
                    r = el.CurrentBoundingRectangle
                    if r.right > r.left:
                        x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
                        u32 = ctypes.windll.user32
                        u32.SetCursorPos(x, y)
                        u32.mouse_event(0x0002, 0, 0, 0, 0)
                        u32.mouse_event(0x0004, 0, 0, 0, 0)
                        return name
        time.sleep(0.7)
    return None


def page_url(hwnd: int) -> str:
    """Address of the page shown in a Chromium window (Yandex Browser, Edge, Chrome)."""
    uia, m = _api()
    doc = uia.ElementFromHandle(hwnd).FindFirst(
        m.TreeScope_Descendants, uia.CreatePropertyCondition(m.UIA_ControlTypePropertyId, m.UIA_DocumentControlTypeId))
    if not doc:
        return ""
    try:
        return doc.GetCurrentPattern(m.UIA_ValuePatternId).QueryInterface(m.IUIAutomationValuePattern).CurrentValue or ""
    except Exception:  # noqa: BLE001 - the page is still loading
        return ""


def press(el) -> None:
    _, m = _api()
    el.GetCurrentPattern(m.UIA_InvokePatternId).QueryInterface(m.IUIAutomationInvokePattern).Invoke()


def player(hwnd: int) -> dict:
    """Yandex Music in this window: {"bar": the player's play/pause button or None, "playing": bool,
    "items": play buttons on the page itself, "wave": the «…включить Мою волну» button or None,
    "track": «artist — track» loaded in the player}."""
    uia, m = _api()
    root = uia.ElementFromHandle(hwnd)
    els = root.FindAll(m.TreeScope_Descendants,
                       uia.CreatePropertyCondition(m.UIA_ControlTypePropertyId, m.UIA_ButtonControlTypeId))
    out: dict = {"bar": None, "playing": False, "items": [], "wave": None, "track": ""}
    prev = ""
    for i in range(els.Length):
        e = els.GetElement(i)
        name = e.CurrentName or ""
        if prev in ("Предыдущая песня", "Previous track", "Previous song"):
            out["bar"] = e
            out["playing"] = name in ("Пауза", "Pause")
            break
        if name in ("Воспроизведение", "Слушать", "Play"):
            out["items"].append(e)
        elif "включить" in name and "волну" in name:      # «Сбросить <очередь> и включить Мою волну»
            out["wave"] = e
        prev = name
    links = root.FindAll(m.TreeScope_Descendants,
                         uia.CreatePropertyCondition(m.UIA_ControlTypePropertyId, m.UIA_HyperlinkControlTypeId))
    for i in range(links.Length):              # the player is at the end of the page: its track and artist come last
        n = (links.GetElement(i).CurrentName or "").strip()
        if n.startswith("Трек "):
            out["track"] = n[5:].strip()
        elif n.startswith("Артист ") and out["track"] and " — " not in out["track"]:
            out["track"] = n[7:].strip() + " — " + out["track"]
    return out
