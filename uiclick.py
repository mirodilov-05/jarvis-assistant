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
