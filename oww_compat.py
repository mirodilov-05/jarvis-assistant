"""Load openWakeWord without scikit-learn.

Windows Smart App Control blocks some scikit-learn DLLs on this machine.
openWakeWord imports scikit-learn only for training custom verifier models,
which we never use, so we register empty stand-in modules before importing it.
"""

import sys
import types


def _stub_sklearn() -> None:
    if "sklearn" in sys.modules:
        return

    class _Unavailable:  # pragma: no cover - never called
        def __init__(self, *a, **k):
            raise RuntimeError("scikit-learn is unavailable (blocked by Smart App Control)")

    def _unavailable(*a, **k):
        raise RuntimeError("scikit-learn is unavailable (blocked by Smart App Control)")

    pkg = types.ModuleType("sklearn")
    pkg.__path__ = []  # mark as package
    linear = types.ModuleType("sklearn.linear_model")
    linear.LogisticRegression = _Unavailable
    pipeline = types.ModuleType("sklearn.pipeline")
    pipeline.make_pipeline = _unavailable
    prep = types.ModuleType("sklearn.preprocessing")
    prep.FunctionTransformer = _Unavailable
    prep.StandardScaler = _Unavailable
    for name, mod in {
        "sklearn": pkg,
        "sklearn.linear_model": linear,
        "sklearn.pipeline": pipeline,
        "sklearn.preprocessing": prep,
    }.items():
        sys.modules[name] = mod


_stub_sklearn()

import openwakeword  # noqa: E402
from openwakeword.model import Model  # noqa: E402
from openwakeword.utils import download_models  # noqa: E402

__all__ = ["openwakeword", "Model", "download_models"]
