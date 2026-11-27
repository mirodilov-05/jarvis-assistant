"""Television by voice, through JARVIS PRIME OS (prime\\), which talks to the TV over the local network.

Any phrase that names the TV («телевизор», «телик», «ТВ») together with a command goes to prime:
включить, выключить, громче, тише, статус, YouTube, канал вверх/вниз, пауза, домой, назад, меню, источник, без звука,
стрелки и ОК. Prime must be running (http://127.0.0.1:8765). If it is not, the voice says so.
"""
import json
import urllib.request

import core
from core import Ctx, skill

PRIME_URL = "http://127.0.0.1:8765/api/command"
TV = r"(?:телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|тв)"
ACTION = (r"(?:открой|открыть|открыв\w*|запусти\w*|поставь|включ\w*|выключ\w*|вруби\w*|выруби\w*|громч\w*|тиш\w*|статус\w*|ютуб\w*|канал\w*|пауз\w*|домой|назад|меню|"
          r"источник|вход|звук\w*|вверх|вниз|влево|вправо|ок|выбер\w*|играй|продолжи|воспроизв\w*|плей|останов\w*|вернись|mute|hdmi|программ\w*)")


def ask_prime(text: str) -> str:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(PRIME_URL, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return str(json.loads(r.read()).get("reply", "")).strip() or "Готово."
    except Exception:  # noqa: BLE001 — prime off or unreachable
        return "Система управления телевизором не запущена. Запустите Jarvis PRIME."


@skill(
    "prime.tv",
    title={"ru": "Телевизор: включить, выключить, громкость, YouTube, каналы, кнопки пульта, статус"},
    patterns={"ru": [
        rf"^(?:джарвис )?(?=.*(?<!\w){TV}(?!\w)).*$",          # any phrase that names the TV goes to prime's table
    ]},
    examples={"ru": ["Включи телевизор", "Громче телевизор", "Канал вверх телевизор", "Статус телевизора"]},
    priority=4,                      # lower number = tried earlier: before music and the rest
)
def tv(ctx: Ctx) -> str:
    return ask_prime(ctx.text)


core._LONG_OK.add("prime.tv")
