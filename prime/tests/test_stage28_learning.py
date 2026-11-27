"""Learning core: corrections are noticed, lessons are merged, the nightly review is parsed, the metrics are right."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from learning import correction_detector as cd  # noqa: E402
from learning import evaluation, reflection, store  # noqa: E402


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    assert ok, name


def test_detector():
    assert cd.detect("нет, я имел в виду музыку")["lang"] == "ru"
    assert cd.detect("bu noto'g'ri")["lang"] == "uz"
    assert cd.detect("no, i meant the music") ["lang"] == "en"
    assert cd.detect("включи телевизор") is None
    assert cd.detect("ты опять не так понял, почему всегда") ["severity"] > cd.detect("это неправильно")["severity"]
    check("corrections recognised in ru, uz, en; plain commands ignored", True)


def test_store_and_merge():
    p = Path(tempfile.mkdtemp()) / "c.db"
    a = store.add_lesson("громкость на 50 во время музыки", "поставил системную", "поставить громкость плеера", path=p)
    b = store.add_lesson("громкость на 50 во время музыки сейчас", "то же", "громкость плеера", path=p)
    assert a == b, "a near-identical lesson must merge, not duplicate"
    rows = store.lessons(path=p)
    assert len(rows) == 1 and rows[0]["occurrence_count"] == 2
    store.add_feedback("вопрос", "ответ", rating=-1, path=p)
    assert store.recent_feedback(path=p)[0]["rating"] == -1
    check("lessons merge by wording, feedback saved", True)


def test_reflection_parses_model_json_and_writes_rules():
    p = Path(tempfile.mkdtemp()) / "r.db"
    store.add_feedback("включи музыку", "открываю видео", rating=-1, severity=0.6, path=p)
    answer = 'Вот разбор: {"lessons":[{"trigger":"включи музыку","wrong":"открыл видео","right":"открыть Яндекс Музыку","context":"музыка"}],"facts":["любит рок"]}'
    res = reflection.reflect(ask=lambda s, m: answer, path=p)
    assert res["ok"] and res["lessons"] == 1, res
    assert store.lessons(path=p)[0]["right_action"] == "открыть Яндекс Музыку"
    hints = reflection.hints_for("включи музыку", path=p)
    assert hints and "Яндекс" in hints[0]
    check("nightly review: JSON parsed, lessons stored, hint returned", True)


def test_reflection_without_corrections_does_nothing():
    p = Path(tempfile.mkdtemp()) / "e.db"
    called = []
    res = reflection.reflect(ask=lambda s, m: called.append(1) or "{}", path=p)
    assert not called and res["lessons"] == 0
    check("no corrections today: no model call", True)


def test_metrics():
    p = Path(tempfile.mkdtemp()) / "m.db"
    store.add_feedback("включи музыку", "x", rating=-1, path=p)
    store.add_feedback("включи музыку снова", "y", rating=-1, path=p)
    store.add_feedback("погода", "z", rating=1, path=p)
    m = evaluation.metrics(path=p)
    assert m["thumbs_up"] == 1 and m["thumbs_down"] == 2 and m["corrections_detected"] == 2
    assert m["repeats"] == 1 and m["repeat_mistake_rate"] == 50.0, m
    check("metrics: repeat_mistake_rate 50 % for one repeat out of two corrections", True)


if __name__ == "__main__":
    test_detector(); test_store_and_merge(); test_reflection_parses_model_json_and_writes_rules()
    test_reflection_without_corrections_does_nothing(); test_metrics()
