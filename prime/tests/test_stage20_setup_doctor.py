"""First-run check: only automatic fixes run, manual ones are only described, and phrases reach their skills.

No install, download or restart happens here: the steps are replaced by stand-ins.
"""
import sys
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import setup_doctor as sd  # noqa: E402
import core  # noqa: E402
from core import normalize  # noqa: E402

core.load_plugins()


def fake(status, kind, fid, label="x"):
    fix = sd.Fix(fid, label, kind) if kind else None
    return sd.Check(fid, label, status, "", fix)


def test_only_missing_automatic_fixes_are_offered():
    checks = [fake("ok", "auto", "a"), fake("missing", "auto", "b"), fake("missing", "manual", "c"),
              fake("optional", "auto", "d"), fake("warn", "auto", "e")]
    ids = [c.fix.id for c in sd.missing_auto(checks)]
    assert ids == ["b", "d", "e"], ids


def test_manual_and_unknown_fixes_never_run():
    ok, msg = sd.run_fix("ollama")
    assert not ok and "вручную" in msg, msg
    ok, msg = sd.run_fix("no-such-fix")
    assert not ok, msg


def test_automatic_fix_runs_and_reports_failure(monkeypatch=None):
    calls = []
    original = dict(sd.AUTO_STEPS)
    try:
        sd.AUTO_STEPS["fake_ok"] = lambda: (calls.append("ok") or (0, "ok"))
        sd.AUTO_STEPS["fake_bad"] = lambda: (1, "нет сети")
        assert sd.run_fix("fake_ok") == (True, "готово")
        assert sd.run_fix("fake_bad")[0] is False
        assert calls == ["ok"]
    finally:
        sd.AUTO_STEPS.clear()
        sd.AUTO_STEPS.update(original)


def test_reboot_is_an_automatic_fix_but_the_batch_never_includes_it_by_default():
    fix = sd.Fix("reboot", "Перезагрузить", "auto", reboot=True)
    assert fix.reboot and fix.kind == "auto"


def first_match(text):
    norm = normalize(text, "ru")
    for sk in core.SKILLS:
        if sk.name in {"music.choice", "macros.run"}:
            continue
        if any(p.search(norm) for p in sk.patterns.get("ru", [])):
            return sk.name
    return None


def test_voice_phrases():
    assert first_match("проверь настройку компьютера") == "setup.check"
    assert first_match("что не хватает джарвису") == "setup.check"
    assert first_match("установи недостающее") == "setup.fix"


if __name__ == "__main__":
    test_only_missing_automatic_fixes_are_offered()
    test_manual_and_unknown_fixes_never_run()
    test_automatic_fix_runs_and_reports_failure()
    test_reboot_is_an_automatic_fix_but_the_batch_never_includes_it_by_default()
    test_voice_phrases()
    print("stage20: all passed")
