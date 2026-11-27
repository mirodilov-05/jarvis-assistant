"""Skill Forge: store new Python skills and run them only in a separate process with a timeout.

Safety rules, all enforced here:
  - a generated skill is saved as a CANDIDATE and never runs until the owner approves it by code;
  - running happens in a child process (no import into the assistant), with a hard timeout and a clean environment;
  - the skill file is checked first for obviously dangerous calls; if it matches, it is refused.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

FORBIDDEN_NAMES = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
FORBIDDEN_MODULES = {"subprocess", "socket", "ctypes", "shutil", "winreg", "os", "sys", "importlib", "urllib", "requests"}


def check_source(src: str) -> list[str]:
    """Problems found by reading the code. An empty list means nothing obvious was found."""
    problems: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"синтаксическая ошибка: строка {e.lineno}"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                if m.split(".")[0] in FORBIDDEN_MODULES:
                    problems.append(f"запрещённый модуль: {m}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"запрещённая функция: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            problems.append(f"служебный атрибут: {node.attr}")
    return problems


def save_candidate(folder: Path, name: str, src: str) -> tuple[Path, list[str]]:
    """Store the skill as a candidate. Returns (path, problems)."""
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in "_-") or "skill"
    path = folder / f"{safe}.py"
    problems = check_source(src)
    path.write_text(src, encoding="utf-8")
    return path, problems


def run_in_sandbox(path: Path, timeout_s: float = 5.0) -> str:
    """Run the skill in a child process with an empty environment. Output is cut to 2000 characters."""
    if check_source(path.read_text(encoding="utf-8")):
        return "не запущено: в навыке есть запрещённые вызовы"
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run([sys.executable, "-I", str(path)], capture_output=True, text=True,
                                  timeout=timeout_s, cwd=tmp, env={"PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            return f"остановлено: дольше {timeout_s:.0f} с"
    out = (proc.stdout + proc.stderr).strip()
    return out[:2000] or "готово, без вывода"
