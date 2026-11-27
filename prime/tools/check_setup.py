"""Shows what is ready and what is still missing. Prints only yes/no, never a secret value.

Run:  python prime\\tools\\check_setup.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.env import load_env, present  # noqa: E402
from domains.device_hub import load_devices  # noqa: E402


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def ollama_running() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5):
            return True
    except Exception:  # noqa: BLE001
        return False


def report() -> list[tuple[str, bool, str]]:
    load_env(ROOT / ".env")
    devices = load_devices(ROOT / "config" / "devices.yaml")
    tv = devices.get("tv_samsung", {})
    bt = devices.get("headphones", {})
    return [
        ("Claude API ключ", present("ANTHROPIC_API_KEY"), "нужен для сложных задач и анализа экрана"),
        ("Telegram токен", present("PRIME_TELEGRAM_TOKEN"), "пульт с телефона"),
        ("Telegram владелец (ID)", present("PRIME_TELEGRAM_OWNER"), "только этот ID получает ответы"),
        ("Home Assistant адрес", present("PRIME_HA_URL"), "свет, розетки, климат"),
        ("Home Assistant токен", present("PRIME_HA_TOKEN"), "доступ к умному дому"),
        ("Телевизор IP", bool(tv.get("ip")), "config\\devices.yaml → tv_samsung.ip"),
        ("Телевизор MAC", bool(tv.get("mac")), "config\\devices.yaml → tv_samsung.mac"),
        ("ntfy канал", present("PRIME_NTFY_TOPIC"), "уведомления на телефон и часы"),
        ("Bluetooth имя наушников", bool(bt.get("name_contains")), "config\\devices.yaml → headphones.name_contains"),
        ("Ollama запущена", ollama_running(), "запасной мозг без интернета (ollama.com)"),
        ("пакет mss", has_module("mss"), "снимок экрана"),
        ("пакет playwright", has_module("playwright"), "веб-агент"),
        ("пакет bleak", has_module("bleak"), "Bluetooth"),
        ("пакет edge_tts", has_module("edge_tts"), "голос для презентации"),
    ]


def main() -> int:
    rows = report()
    ready = sum(1 for _, ok, _ in rows if ok)
    for name, ok, why in rows:
        mark = "ГОТОВО " if ok else "НЕТ    "
        print(f"{mark} {name:<28} {why}")
    print(f"\nГотово {ready} из {len(rows)}. Подробности: prime\\SETUP.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
