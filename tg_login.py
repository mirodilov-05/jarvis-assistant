"""One-time Telegram login for the Jarvis assistant (reading your chats).

Telegram will send you a login code; type it here yourself. The session is
stored only on this computer in data/telegram.session — keep it private,
it gives access to your Telegram account. Delete it to log out.
"""

import sys
import tomllib
from pathlib import Path

BASE = Path(__file__).resolve().parent
cfg = tomllib.load(open(BASE / "config.toml", "rb")).get("telegram", {})
if not cfg.get("api_id") or not cfg.get("api_hash"):
    print("Сначала впишите api_id и api_hash в config.toml (раздел [telegram]).")
    print("Их выдают на https://my.telegram.org -> API development tools.")
    input("Enter — закрыть")
    sys.exit(1)

from telethon.sync import TelegramClient  # noqa: E402

(BASE / "data").mkdir(exist_ok=True)
with TelegramClient(str(BASE / "data" / "telegram"), int(cfg["api_id"]), cfg["api_hash"]) as client:
    me = client.get_me()
    print(f"Готово! Вошли как {me.first_name}. Джарвис теперь может читать ваши чаты.")
input("Enter — закрыть")
