"""The Jarvis window as a native desktop app (Edge WebView2 through pywebview): no browser frame or address bar,
its own icon, remembers size. Opened by the shortcut / Ctrl+Alt+J; Jarvis itself keeps running in the background.
Falls back to an Edge --app window when pywebview can't start (assistant.open_app_window)."""

import json
import sys
from pathlib import Path

import webview

BASE = Path(__file__).resolve().parent
STATE = BASE / "data" / "window.json"
URL = "http://127.0.0.1:50778/"


def main() -> None:
    try:
        geo = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        geo = {"width": 1180, "height": 780}
    win = webview.create_window("Джарвис", URL, width=geo.get("width", 1180), height=geo.get("height", 780),
                                min_size=(720, 520), background_color="#03060b", text_select=True)

    def remember(*_a):
        try:
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(json.dumps({"width": win.width, "height": win.height}), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    win.events.closing += remember
    if "--selftest" in sys.argv:
        import threading
        import time

        def stop():
            time.sleep(4)
            print("window ok", win.width, win.height, flush=True)
            win.destroy()
        threading.Thread(target=stop, daemon=True).start()
    icon = BASE / "web" / "jarvis.ico"
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(BASE / "data" / "webview"),
                  icon=str(icon) if icon.exists() else None)


if __name__ == "__main__":
    main()
