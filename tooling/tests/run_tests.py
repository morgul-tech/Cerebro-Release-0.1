#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT_IMPORT = Path(__file__).resolve().parents[2]
if str(ROOT_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_IMPORT))
import subprocess
import sys
from tooling.common.paths import ROOT


def main() -> int:
    result = subprocess.run([sys.executable, "run_tests.py"], cwd=ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
