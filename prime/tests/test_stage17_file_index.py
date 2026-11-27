"""File-name index: secrets are skipped, search works, folders like node_modules are not walked.

Works on a temporary folder with its own database; the real disks and the real index are not touched.
"""
import sys
import tempfile
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import pc_index  # noqa: E402


def make_tree(root: Path) -> None:
    (root / "Договоры").mkdir(parents=True)
    (root / "Договоры" / "договор аренды.docx").write_text("content must never be read", encoding="utf-8")
    (root / "фото отпуск.jpg").write_bytes(b"x")
    (root / ".env").write_text("OPENAI=secret", encoding="utf-8")                 # secret by name: skipped
    (root / "passwords_backup.txt").write_text("hunter2", encoding="utf-8")       # secret by name: skipped
    (root / "id_rsa").write_text("PRIVATE", encoding="utf-8")                     # secret by name: skipped
    proj = root / "my-app"
    (proj / ".git").mkdir(parents=True)
    (proj / "package.json").write_text("{}", encoding="utf-8")
    (proj / "index.js").write_text("console.log(1)", encoding="utf-8")
    (proj / "node_modules" / "lib").mkdir(parents=True)
    (proj / "node_modules" / "lib" / "skipme.js").write_text("x", encoding="utf-8")


def test_index_names_only_and_skip_secrets(tmp=None):
    base = Path(tempfile.mkdtemp())
    root = base / "files"
    make_tree(root)
    original_db = pc_index.DB
    pc_index.DB = base / "pc_index.db"
    try:
        d = pc_index.build([root])
        # stored: договор аренды.docx, фото отпуск.jpg, package.json, index.js (4 names)
        assert d["built"] and d["files"] == 4, d
        assert pc_index.search("договор", 10) == [str(root / "Договоры" / "договор аренды.docx")]
        assert pc_index.search("фото отпуск", 10) == [str(root / "фото отпуск.jpg")]
        for secret in [".env", "passwords_backup", "id_rsa"]:
            assert pc_index.search(secret, 10) == [], secret
        assert pc_index.search("skipme", 10) == [], "node_modules must not be walked"
        projects = d["projects"]
        assert any(p.endswith("my-app") for p in projects), projects
        assert d["skipped_secret"] == 3, d
        text = pc_index.summary()
        assert "файлов" in text and "my-app" in text and "PRIVATE" not in text
    finally:
        pc_index.DB = original_db


def test_search_needs_every_word():
    base = Path(tempfile.mkdtemp())
    root = base / "files"
    make_tree(root)
    original_db = pc_index.DB
    pc_index.DB = base / "pc_index.db"
    try:
        pc_index.build([root])
        assert pc_index.search("договор аренды", 10) != []
        assert pc_index.search("договор отпуск", 10) == []
    finally:
        pc_index.DB = original_db


if __name__ == "__main__":
    test_index_names_only_and_skip_secrets()
    test_search_needs_every_word()
    print("stage17: all passed")
