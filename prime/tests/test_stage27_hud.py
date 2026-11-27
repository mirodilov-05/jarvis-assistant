"""Home screen: process list, protected processes, study cards, TV buttons, layout of the 30 widgets."""
import asyncio
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        raise SystemExit(1)


def jarvis_part():
    import os

    import hud_data
    import procs
    rows = procs.snapshot()
    check("process list has this process", any(r["pid"] == os.getpid() for r in rows))
    for pid, name in ((4, "System"), (os.getpid(), "cs2.exe"), (1, "lsass.exe"), (os.getpid(), "python.exe")):
        try:
            hud_data.action("kill", {"pid": pid, "name": name})
            check(f"kill {name} refused", False)
        except Exception:  # noqa: BLE001
            check(f"kill {name} refused", True)
    for kind, body in (("open", {"name": "evil.exe"}), ("project", {"path": "C:/Windows"}), ("settings", {"page": "cmd"}),
                       ("reveal", {"path": "C:/Windows/win.ini"}), ("nope", {})):
        try:
            hud_data.action(kind, body)
            check(f"{kind} refused", False)
        except ValueError:
            check(f"{kind} refused", True)
    js = (ROOT / "web" / "hud.js").read_text(encoding="utf-8")
    check("30 widgets", len(re.findall(r"^  \[\"[a-z]+\", \"", js, re.M)) == 30)
    check("page does not poll through commands", "статус телевизора" not in js and "hudTvStatus" not in js)


def prime_part():
    for m in [k for k in sys.modules if k == "core" or k.startswith("core.")]:
        del sys.modules[m]
    sys.path.insert(0, str(ROOT / "prime"))
    from core.memory_core import Memory
    from domains import study_cards
    from interfaces.web_command_center import TV_BUTTONS

    async def run():
        mem = Memory(Path(tempfile.mkdtemp()) / "t.db")
        await study_cards.add_deck(mem)
        n = (await study_cards.state(mem))["total"]
        check("starter deck", n == len(study_cards.N2_DECK))
        await study_cards.add_deck(mem)
        check("deck is not added twice", (await study_cards.state(mem))["total"] == n)
        c = (await study_cards.state(mem))["card"]
        await study_cards.review(mem, c["id"], 4)
        check("known card leaves today", (await study_cards.state(mem))["due"] == n - 1)
    asyncio.run(run())
    check("TV buttons", {"on", "off", "up", "down", "youtube"} <= set(TV_BUTTONS))


if __name__ == "__main__":
    jarvis_part()
    prime_part()
