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
    "standards": ROOT / "tooling/standards/validate_standards.py",
    "report": ROOT / "tooling/reporter/generate_report.py",
    "checksum": ROOT / "tooling/integrity/generate_checksums.py",
    "zip": ROOT / "tooling/packager/create_zip.py",
    "build": ROOT / "tooling/builder/build_release.py",
    "dependencies": ROOT / "tooling/dependencies/check_dependencies.py",
}

DEPENDENCY_REQUIRED = {
    "test",
    "validate",
    "standards",
    "report",
    "checksum",
    "zip",
    "build",
}


def run_script(script: Path, *args: str) -> int:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Local tooling for Cerebro Release 0.1")
    parser.add_argument(
        "command",
        choices=sorted((*COMMANDS.keys(), "install")),
    )
    args = parser.parse_args()

    dependency_script = COMMANDS["dependencies"]

    if args.command == "install":
        return run_script(dependency_script, "install")

    if args.command in DEPENDENCY_REQUIRED:
        dependency_result = run_script(dependency_script, "check")
        if dependency_result != 0:
            return dependency_result

    return run_script(COMMANDS[args.command])


if __name__ == "__main__":
    raise SystemExit(main())
