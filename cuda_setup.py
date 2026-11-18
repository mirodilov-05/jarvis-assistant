"""Make the pip-installed NVIDIA cuBLAS/cuDNN DLLs visible to CTranslate2 (Whisper on GPU)."""

import os
import sys
from pathlib import Path


def setup() -> None:
    root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if not root.exists():
        return
    for bin_dir in root.glob("*/bin"):
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


setup()
