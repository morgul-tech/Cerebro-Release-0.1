#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COMMANDS = {
    "test": ROOT / "tooling/tests/run_tests.py",
    "validate": ROOT / "tooling/validator/validate.py",
    "valider": ROOT / "tooling/validation/valider.py",
    "mcp": ROOT / "tooling/control/mcp.py",
    "standards": ROOT / "tooling/standards/validate_standards.py",
    "repository": ROOT / "tooling/repository/check_repository.py",
    "report": ROOT / "tooling/reporter/generate_report.py",
    "checksum": ROOT / "tooling/integrity/generate_checksums.py",
    "zip": ROOT / "tooling/packager/create_zip.py",
    "build": ROOT / "tooling/builder/build_release.py",
    "pipeline": ROOT / "tooling/pipeline/run_pipeline.py",
    "dependencies": ROOT / "tooling/dependencies/check_dependencies.py",
    "patch-build": ROOT / "tooling/patch/build_patch.py",
    "patch-validate": ROOT / "tooling/patch/validate_patch.py",
    "quality": ROOT / "tooling/quality/quality_gate.py",
}

DEPENDENCY_REQUIRED = set(COMMANDS) - {"dependencies", "valider", "mcp"}


def run_script(script: Path, *arguments: str) -> int:
    if not script.is_file():
        print(f"[FAIL] Required tooling file is missing: {script}")
        return 4
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Local tooling for Cerebro Release 0.1")
    parser.add_argument("command", choices=sorted((*COMMANDS.keys(), "install")))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.command == "install":
        return run_script(COMMANDS["dependencies"], "install")

    if args.command in DEPENDENCY_REQUIRED:
        status = run_script(COMMANDS["dependencies"], "check")
        if status != 0:
            return status

    return run_script(COMMANDS[args.command], *args.arguments)


if __name__ == "__main__":
    raise SystemExit(main())
