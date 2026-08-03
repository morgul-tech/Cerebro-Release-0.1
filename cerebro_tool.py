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
    "report": ROOT / "tooling/reporter/generate_report.py",
    "checksum": ROOT / "tooling/integrity/generate_checksums.py",
    "zip": ROOT / "tooling/packager/create_zip.py",
    "build": ROOT / "tooling/builder/build_release.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local tooling for Cerebro Release 0.1")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args()
    return subprocess.run([sys.executable, str(COMMANDS[args.command])], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
