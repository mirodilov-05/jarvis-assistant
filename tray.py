"""Tray icon + mini capsule (V3).

Tray (bottom-right, next to the clock): left click — show/hide the Jarvis window; right click — menu.
Closing the window never stops Jarvis: he keeps listening and stays in the tray.

Mini capsule: a small always-on-top bar (Ctrl+Alt+Space, or the tray menu) with Jarvis's state, his last
answer and a box to type a command. It stays above windowed / borderless games; exclusive fullscreen games
draw over everything, so there use the voice.

Pure ctypes (Shell_NotifyIcon) and tkinter from the standard library — no extra packages.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
from ctypes import wintypes

import core

log = logging.getLogger("tray")
user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
WINDOW_TITLE = "Джарвис"
_hidden: dict = {"hwnd": None}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD)]


WM_TRAY = 0x0400 + 20
WM_COMMAND, WM_LBUTTONUP, WM_RBUTTONUP, WM_DESTROY = 0x0111, 0x0202, 0x0205, 0x0002
MENU = {1: "Показать / скрыть окно", 2: "Мини-капсула", 3: "Замолчать", 0: None, 4: "Перезапустить Джарвиса"}


# ---------------------------------------------------------------------------
# The Jarvis window (Edge app window titled «Джарвис»)
# ---------------------------------------------------------------------------

def _find_window() -> int:
    return user32.FindWindowW(None, WINDOW_TITLE) or 0


def _main():
    return sys.modules.get("__main__")


def show_window() -> None:
    hwnd = _hidden["hwnd"] or _find_window()
    if hwnd and user32.IsWindow(hwnd):
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        _hidden["hwnd"] = None
        return
    _hidden["hwnd"] = None
    m = _main()
    if m and hasattr(m, "open_app_window"):
        m.open_app_window()


def hide_window() -> bool:
    """«Свернуть в трей»: hide the window (Jarvis keeps working)."""
    hwnd = _find_window()
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 0)              # SW_HIDE
    _hidden["hwnd"] = hwnd
    return True


def toggle_window() -> None:
    hwnd = _find_window()
    if hwnd and user32.IsWindowVisible(hwnd) and not _hidden["hwnd"]:
        hide_window()
    else:
        show_window()


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------

_tray: dict = {}


def _on_menu(cmd: int) -> None:
    if cmd == 1:
        toggle_window()
    elif cmd == 2:
        toggle_capsule()
    elif cmd == 3:
        m = _main()
        if m and hasattr(m, "speaker"):
            m.speaker.stop()
    elif cmd == 4:
        log.info("Restart requested from the tray")
        os._exit(3)                         # the supervisor starts Jarvis again


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_TRAY:
        if lparam == WM_LBUTTONUP:
            threading.Thread(target=toggle_window, daemon=True).start()
        elif lparam == WM_RBUTTONUP:
            menu = user32.CreatePopupMenu()
            for cid, title in MENU.items():
                user32.AppendMenuW(menu, 0x0800 if title is None else 0, cid, title)   # MF_SEPARATOR / MF_STRING
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0020, pt.x, pt.y, 0, hwnd, None)   # RETURNCMD | BOTTOMALIGN
            user32.DestroyMenu(menu)
            if cmd:
                threading.Thread(target=_on_menu, args=(cmd,), daemon=True).start()
        return 0
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _tray_loop() -> None:
    hinst = kernel32.GetModuleHandleW(None)
    proc = WNDPROC(_wndproc)
    _tray["proc"] = proc                    # keep a reference, or Windows calls freed memory
    wc = WNDCLASSW(lpfnWndProc=proc, hInstance=hinst, lpszClassName="JarvisTray")
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, "JarvisTray", "JarvisTray", 0, 0, 0, 0, 0, None, None, hinst, None)
    icon = user32.LoadImageW(None, os.path.join(core.BASE, "web", "jarvis.ico"), 1, 0, 0, 0x0010) or \
        user32.LoadIconW(None, ctypes.c_void_p(32512))          # IDI_APPLICATION
    nid = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=hwnd, uID=1, uFlags=0x1 | 0x2 | 0x4,
                          uCallbackMessage=WM_TRAY, hIcon=icon, szTip="Джарвис — слушаю")
    shell32.Shell_NotifyIconW(0, ctypes.byref(nid))             # NIM_ADD
    _tray.update(hwnd=hwnd, nid=nid)
    import atexit
    atexit.register(lambda: shell32.Shell_NotifyIconW(2, ctypes.byref(nid)))   # NIM_DELETE
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def set_tip(text: str) -> None:
    nid = _tray.get("nid")
    if nid:
        nid.szTip = text[:120]
        shell32.Shell_NotifyIconW(1, ctypes.byref(nid))         # NIM_MODIFY


# ---------------------------------------------------------------------------
# Mini capsule (tkinter, its own thread)
# ---------------------------------------------------------------------------

_cap_q: queue.Queue = queue.Queue()
_cap: dict = {"thread": None, "visible": False, "mode": "", "hide_at": 0.0}
STATE_TEXT = {"listening": "жду «Джарвис»", "recording": "слушаю", "thinking": "думаю", "speaking": "говорю",
              "taping": "идёт запись", "starting": "запуск"}
STATE_COLOR = {"listening": "#4fd1ff", "recording": "#7fe3ff", "thinking": "#ffb547", "speaking": "#78aaff",
               "taping": "#ff5468", "starting": "#7890a0"}
ACTIVE = ("recording", "thinking", "speaking")


def _ensure_capsule() -> None:
    if not _cap["thread"] or not _cap["thread"].is_alive():
        _cap["thread"] = threading.Thread(target=_capsule_loop, daemon=True, name="capsule")
        _cap["thread"].start()


def toggle_capsule() -> None:
    """Hotkey / tray / voice: the full capsule with a box to type a command."""
    _ensure_capsule()
    _cap_q.put(("toggle", None))


def _window_in_front() -> bool:
    hwnd = _find_window()
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


def _capsule_loop() -> None:
    import time
    import tkinter as tk

    root = tk.Tk()
    root.title("Jarvis capsule")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.93)
    bg, fg, muted = "#0b141d", "#d6ecff", "#7b93a8"
    root.configure(bg=bg)
    W = 460
    frame = tk.Frame(root, bg=bg, highlightthickness=1, highlightbackground="#1f3445")
    frame.pack(fill="both", expand=True)
    dot = tk.Canvas(frame, width=14, height=14, bg=bg, highlightthickness=0)
    oval = dot.create_oval(2, 2, 12, 12, fill=STATE_COLOR["listening"], outline="")
    state = tk.Label(frame, text="ДЖАРВИС · жду «Джарвис»", bg=bg, fg=muted, font=("Segoe UI", 9))
    close = tk.Label(frame, text="✕", bg=bg, fg=muted, font=("Segoe UI", 10), cursor="hand2")
    reply = tk.Label(frame, text="", bg=bg, fg=fg, font=("Segoe UI", 10), anchor="w", justify="left")
    entry = tk.Entry(frame, bg="#13212d", fg=fg, insertbackground=fg, relief="flat", font=("Segoe UI", 10))
    trans = tk.Label(frame, text="", bg=bg, fg=fg, font=("Segoe UI", 11), anchor="nw", justify="left", wraplength=W - 28)
    root.withdraw()
    root.update_idletasks()
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    GWL_EXSTYLE, NOACTIVATE, TOOLWINDOW = -20, 0x08000000, 0x00000080

    def set_noactivate(on: bool) -> None:
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | TOOLWINDOW      # never in the taskbar
        style = style | NOACTIVATE if on else style & ~NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    def layout(mode: str, extra: int = 0) -> None:
        """manual: status + answer + a box to type; island: a slim bar with the dot and one line of subtitles."""
        _cap["mode"] = mode
        for wdg in (dot, state, close, reply, entry):
            wdg.place_forget()
        if mode == "island":
            w, h = 520, 40
            dot.place(x=12, y=13)
            state.place(x=32, y=10)
            reply.config(wraplength=0)
            reply.place(x=150, y=10, width=w - 162)
            set_noactivate(True)
        else:
            w, h = W, 70
            dot.place(x=12, y=12)
            state.place(x=32, y=8)
            close.place(x=w - 26, y=6)
            reply.config(wraplength=w - 210)
            reply.place(x=12, y=32, width=w - 200)
            entry.place(x=w - 186, y=34, width=170, height=24)
            set_noactivate(False)
        x = (root.winfo_screenwidth() - w) // 2
        root.geometry(f"{w}x{h + extra}+{x}+14")

    def show(mode: str) -> None:
        if not trans.cget("text"):
            layout(mode)
        root.deiconify()
        root.attributes("-topmost", True)
        _cap["visible"] = True
        if mode == "manual":
            entry.focus_force()

    def hide(_e=None):
        root.withdraw()
        _cap.update(visible=False, mode="", hide_at=0.0)

    def send(_e=None):
        text = entry.get().strip()
        if not text:
            return
        entry.delete(0, "end")
        reply.config(text="…")
        m = _main()
        if m and hasattr(m, "handle"):
            threading.Thread(target=m.handle, args=(text, "ru", "текст", bool(core.setting("voice", "speak_text_replies", False))),
                             daemon=True).start()

    entry.bind("<Return>", send)
    root.bind("<Escape>", hide)
    close.bind("<Button-1>", hide)
    drag = {}
    frame.bind("<ButtonPress-1>", lambda e: drag.update(x=e.x, y=e.y))
    frame.bind("<B1-Motion>", lambda e: root.geometry(f"+{root.winfo_x() + e.x - drag['x']}+{root.winfo_y() + e.y - drag['y']}"))

    def on_event(ev: dict) -> None:
        if ev.get("type") in ("status", "level", "message", "game", "translation", "translate_live"):
            _cap_q.put(("event", ev))

    core.subscribe(on_event)
    last = {"s": ""}

    def auto_ok() -> bool:
        """Show the island by itself only when you can't see the main window (a game, Cursor, a browser...)."""
        return bool(core.setting("ui", "capsule_auto", True)) and (bool(core.CONFIG.get("_game_mode")) or not _window_in_front())

    def pump():
        try:
            while True:
                kind, ev = _cap_q.get_nowait()
                if kind == "toggle":
                    if _cap["visible"] and _cap["mode"] == "manual":
                        hide()
                    else:
                        show("manual")
                    continue
                t = ev["type"]
                if t in ("status", "level"):
                    s = ev.get("state") or ev.get("s") or ""
                    if s and s != last["s"]:
                        last["s"] = s
                        dot.itemconfig(oval, fill=STATE_COLOR.get(s, "#4fd1ff"))
                        state.config(text="ДЖАРВИС · " + STATE_TEXT.get(s, s))
                        if s in ACTIVE:
                            _cap["hide_at"] = 0.0
                            if not _cap["visible"] and auto_ok():
                                reply.config(text="")
                                show("island")
                        elif s == "listening" and _cap["mode"] == "island":
                            _cap["hide_at"] = time.time() + 3.0      # disappears 3 s after the answer
                elif t == "message" and ev.get("role") != "user":
                    txt = ev.get("text", "")
                    limit = 70 if _cap["mode"] == "island" else 120
                    reply.config(text=txt if len(txt) < limit else txt[:limit - 3] + "…")
                elif t == "message" and _cap["mode"] == "island":
                    reply.config(text="— " + ev.get("text", "")[:60])
                elif t == "translation":
                    text = ev.get("text", "").strip()
                    trans.config(text=text[:900])
                    lines = sum(1 + len(x) // 60 for x in text.splitlines()) or 1
                    extra = min(350, 20 * lines + 8)
                    layout("manual", extra)
                    trans.place(x=12, y=64, width=W - 24, height=extra)
                    set_noactivate(True)          # a translation never takes the keyboard away from your game
                    root.deiconify()
                    root.attributes("-topmost", True)
                    _cap["visible"] = True
                elif t == "translate_live" and not ev.get("on"):
                    trans.place_forget()
                    trans.config(text="")
                    layout("manual")
                elif t == "game":
                    state.config(text="ДЖАРВИС · " + ("игровой режим" if ev.get("on") else "жду «Джарвис»"))
        except queue.Empty:
            pass
        if _cap["hide_at"] and time.time() > _cap["hide_at"] and _cap["mode"] == "island":
            hide()
        root.after(120, pump)

    pump()
    root.mainloop()


# ---------------------------------------------------------------------------

def start() -> None:
    if _tray.get("thread"):
        return
    _tray["thread"] = threading.Thread(target=_tray_loop, daemon=True, name="tray")
    _tray["thread"].start()
    try:
        import keyboard
        keyboard.add_hotkey(core.setting("hotkeys", "capsule", "ctrl+alt+space"), toggle_capsule)
    except Exception as e:  # noqa: BLE001
        log.warning("Capsule hotkey not set: %s", e)
    if core.setting("ui", "capsule_auto", True):
        _ensure_capsule()     # ready in the background: appears by itself when you talk to Jarvis from a game
