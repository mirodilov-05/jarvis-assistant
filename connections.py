"""Connected accounts: non-secret settings in data/connections.json, secrets
(passwords, API keys, tokens, private calendar links) in Windows Credential
Manager via keyring — never in plain files.
"""

from __future__ import annotations

import keyring

import core

SERVICE = "jarvis-assistant"
FILE = core.DATA / "connections.json"

DEFAULT = {
    "email": [],          # [{"address": "...", "imap_host": "imap.gmail.com", "name": "Работа"}]
    "telegram": {"api_id": ""},
    "whatsapp": {"enabled": False},
    "youtube": {"channels": []},   # ["@handle" or "UC..."]
    "calendar": {"count": 0},
    "ai": {"provider": "local", "model": "claude-opus-5-5"},
}


def load() -> dict:
    data = core.load_json(FILE, {})
    for k, v in DEFAULT.items():
        data.setdefault(k, v if not isinstance(v, (dict, list)) else (v.copy() if isinstance(v, dict) else list(v)))
    # migrate email/telegram from config.toml once
    cfg_mail = core.CONFIG.get("email", {})
    if cfg_mail.get("address") and not any(a["address"] == cfg_mail["address"] for a in data["email"]):
        data["email"].append({"address": cfg_mail["address"], "imap_host": cfg_mail.get("imap_host", "imap.gmail.com"),
                              "name": "Почта"})
        if cfg_mail.get("app_password"):
            set_secret(f"email:{cfg_mail['address']}", cfg_mail["app_password"].replace(" ", ""))
        save(data)
    return data


def save(data: dict) -> None:
    with core.file_lock:
        core.save_json(FILE, data)


def get_secret(name: str) -> str:
    try:
        return keyring.get_password(SERVICE, name) or ""
    except Exception:  # noqa: BLE001
        core.log.exception("keyring read failed")
        return ""


def set_secret(name: str, value: str) -> None:
    if value:
        keyring.set_password(SERVICE, name, value)
    else:
        try:
            keyring.delete_password(SERVICE, name)
        except keyring.errors.PasswordDeleteError:
            pass


def telegram_creds() -> tuple[str, str]:
    data = load()
    api_id = data["telegram"].get("api_id") or str(core.CONFIG.get("telegram", {}).get("api_id", ""))
    api_hash = get_secret("telegram:api_hash") or core.CONFIG.get("telegram", {}).get("api_hash", "")
    return api_id, api_hash
