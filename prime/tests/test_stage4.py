"""Stage 4 tests: URL safety, skill source checks, sandbox timeout, showman script in three languages."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domains.showman_agent import Stats, build_script  # noqa: E402
from domains.skill_forge import check_source, run_in_sandbox, save_candidate  # noqa: E402
from domains.web_agent import safe_url  # noqa: E402


def test_only_web_urls_are_allowed():
    assert safe_url("https://example.com/x") == "https://example.com/x"
    for bad in ("file:///C:/Windows", "javascript:alert(1)", "http://", "ftp://x.y"):
        try:
            safe_url(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_dangerous_skill_code_is_flagged():
    assert check_source("print(1+1)") == []
    assert any("subprocess" in p for p in check_source("import subprocess"))
    assert any("eval" in p for p in check_source("x = eval('1')"))
    assert any("служебный" in p for p in check_source("x = ().__class__"))
    assert check_source("def (") and "синтаксическая" in check_source("def (")[0]


def test_candidate_is_saved_but_not_run_and_sandbox_times_out():
    folder = Path(tempfile.mkdtemp())
    path, problems = save_candidate(folder, "loop", "while True:\n    pass\n")
    assert path.exists() and problems == []
    assert "дольше" in run_in_sandbox(path, timeout_s=1.0)


def test_sandbox_refuses_flagged_code():
    folder = Path(tempfile.mkdtemp())
    path, _ = save_candidate(folder, "bad", "import subprocess\nprint('x')\n")
    assert run_in_sandbox(path).startswith("не запущено")


def test_showman_script_in_three_languages():
    s = Stats(goals_done=3, tasks_done=12, words_learned=240, highlights=["Сдал проект."])
    for lang in ("ru", "en", "ja"):
        slides = build_script(s, lang)
        assert slides[0]["cue"] == "[SLIDE_TITLE]" and slides[-1]["cue"] == "[END]"
        assert any("240" in x["say"] for x in slides)
    assert "です" in build_script(s, "ja")[1]["say"] or "いたします" in build_script(s, "ja")[1]["say"]
    assert build_script(s, "xx")[0]["say"].startswith("Месячный отчёт")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
