"""Wake-up relay: lets you switch on the TV (and try the laptop) from Telegram when the laptop is OFF.

Run it on a device that stays on all the time and is on the same Wi-Fi/LAN (a Raspberry Pi, a home router with
Python, an old PC). The laptop's own Jarvis bot cannot work while the laptop is off, so this relay answers then.

While the laptop answers on the network, the relay stays quiet and does not read Telegram, so the two never
compete for the same messages.

Setup (on the always-on device):
  1. pip install requests
  2. Copy relay_config.example.json to relay_config.json and fill in: bot token, your Telegram ID,
     the laptop's IP, and the MAC addresses of the TV and the laptop.
  3. python wake_relay.py

Commands (only from your Telegram ID, everything else is ignored):
  «включи телевизор» / «телик»  — Wake-on-LAN to the TV
  «включи ноутбук» / «компьютер» — Wake-on-LAN to the laptop (works only if the laptop supports it on Wi-Fi)
  «статус»                       — is the laptop on, and is the TV reachable
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "relay_config.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load_config(path: Path = CONFIG) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("token", "owner_id", "laptop_ip", "tv_mac", "laptop_mac"):
        if not cfg.get(key):
            raise SystemExit(f"relay_config.json: fill in «{key}»")
    return cfg


def magic_packet(mac: str) -> bytes:
    """The Wake-on-LAN packet: six 0xFF bytes, then the MAC address repeated 16 times."""
    raw = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(raw) != 12:
        raise ValueError(f"bad MAC address: {mac}")
    return bytes.fromhex("FF" * 6 + raw * 16)


def send_wake(mac: str, broadcast: str = "255.255.255.255") -> None:
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast, 9))
        s.sendto(packet, (broadcast, 7))


def laptop_on(ip: str) -> bool:
    """The laptop answers on its Jarvis port (or to ping) while it is on."""
    try:
        requests.get(f"http://{ip}:50778/api/telemetry", timeout=2)
        return True
    except requests.RequestException:
        pass
    creation = NO_WINDOW
    r = subprocess.run(["ping", "-n", "1", "-w", "800", ip], capture_output=True, creationflags=creation)
    return r.returncode == 0


def reply_for(text: str, cfg: dict) -> str:
    low = text.lower().strip()
    tv = re.search(r"телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|\bтв\b", low)
    laptop = re.search(r"ноут\w*|компьютер\w*|комп\b|пк\b", low)
    if "статус" in low:
        on = laptop_on(cfg["laptop_ip"])
        return "Ноутбук включён." if on else "Ноутбук выключен. Могу включить телевизор или попробовать ноутбук."
    if re.search(r"включ|вруби|запусти|разбуди", low):
        if tv:
            send_wake(cfg["tv_mac"])
            return "Включаю телевизор. Если не загорелся через минуту, проверьте в его настройках «Включение по сети»."
        if laptop:
            send_wake(cfg["laptop_mac"])
            return ("Пробую включить ноутбук. Через Wi-Fi это работает не на всех ноутбуках: "
                    "если не включился, включите его кнопкой.")
    return "Пока умею только: включить телевизор, попробовать включить ноутбук, статус. Остальное — когда ноутбук включён."


def poll_forever(cfg: dict) -> None:
    base = f"https://api.telegram.org/bot{cfg['token']}"
    offset = 0
    while True:
        try:
            if laptop_on(cfg["laptop_ip"]):
                time.sleep(30)              # the laptop's own bot is in charge; do not compete for messages
                continue
            r = requests.get(f"{base}/getUpdates", params={"timeout": 25, "offset": offset}, timeout=35).json()
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                if msg.get("from", {}).get("id") != int(cfg["owner_id"]):
                    continue                # strangers are ignored
                answer = reply_for(msg.get("text", ""), cfg)
                requests.post(f"{base}/sendMessage", data={"chat_id": msg["chat"]["id"], "text": answer}, timeout=15)
        except (requests.RequestException, ValueError, KeyError) as e:
            print("relay:", e, file=sys.stderr)
            time.sleep(10)


if __name__ == "__main__":
    poll_forever(load_config())
