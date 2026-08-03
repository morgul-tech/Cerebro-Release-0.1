#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_IMPORT = Path(__file__).resolve().parents[2]
if str(ROOT_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_IMPORT))

from tooling.common.paths import ROOT

STEPS = [
    ("Repository", ROOT / "tooling/repository/check_repository.py", []),
    ("Environment", ROOT / "tooling/dependencies/check_dependencies.py", ["check"]),
    ("Standards", ROOT / "tooling/standards/validate_standards.py", []),
    ("Tests", ROOT / "tooling/tests/run_tests.py", []),
    ("Checksums", ROOT / "tooling/integrity/generate_checksums.py", []),
    ("Validation", ROOT / "tooling/validator/validate.py", []),
    ("Report", ROOT / "tooling/reporter/generate_report.py", []),
    ("Package", ROOT / "tooling/packager/create_zip.py", []),
]


def preflight() -> tuple[bool, list[str]]:
    missing = []
    for _, script, _ in STEPS:
        if not script.is_file():
            missing.append(str(script.relative_to(ROOT)).replace("\\", "/"))
    return not missing, missing


def main() -> int:
    ok, missing = preflight()
    if not ok:
        print("\nBUILD PREFLIGHT FAILED")
        print("======================")
        for path in missing:
            print(f"[FAIL] Missing required build component: {path}")
        print("\nRestore the missing files before running Build Release.")
        return 4

    for name, script, arguments in STEPS:
        print(f"\n=== {name} ===")
        result = subprocess.run(
            [sys.executable, str(script), *arguments],
            cwd=ROOT,
        )
        if result.returncode != 0:
            print(f"\nBUILD FAILED at: {name}")
            return result.returncode

    print("\nBUILD PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
