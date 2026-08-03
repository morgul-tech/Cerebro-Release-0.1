from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def run_python(script: Path, *args: str, cwd: Path) -> int:
    completed = subprocess.run([sys.executable, str(script), *args], cwd=cwd)
    return completed.returncode
