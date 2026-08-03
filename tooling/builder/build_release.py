#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "tooling" / "pipeline" / "run_pipeline.py"

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run(
            [sys.executable, str(PIPELINE), "release"],
            cwd=ROOT,
        ).returncode
    )
