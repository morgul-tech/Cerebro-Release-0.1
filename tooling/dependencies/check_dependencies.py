#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements.txt"
REPORT_JSON = ROOT / "validation" / "dependency-report.json"
REPORT_TXT = ROOT / "validation" / "dependency-report.txt"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DEPENDENCY = 3

_IMPORT_NAMES = {
    "PyYAML": "yaml",
    "jsonschema": "jsonschema",
}


@dataclass(frozen=True)
class Requirement:
    distribution: str
    operator: str | None
    version: str | None


@dataclass(frozen=True)
class DependencyResult:
    distribution: str
    import_name: str
    required: str
    installed: str | None
    status: str
    details: str


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts)


def _meets(installed: str, operator: str | None, required: str | None) -> bool:
    if not operator or not required:
        return True
    left = _version_tuple(installed)
    right = _version_tuple(required)
    if operator == ">=":
        return left >= right
    if operator == "==":
        return left == right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    return False


def parse_requirement(line: str) -> Requirement | None:
    clean = line.split("#", 1)[0].strip()
    if not clean:
        return None
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*(>=|==|<=|>|<)?\s*([A-Za-z0-9_.+-]+)?", clean)
    if not match:
        raise ValueError(f"Unsupported requirement syntax: {line.rstrip()}")
    distribution, operator, version = match.groups()
    return Requirement(distribution, operator, version)


def load_requirements(path: Path = REQUIREMENTS) -> list[Requirement]:
    if not path.is_file():
        raise FileNotFoundError(f"requirements.txt not found: {path}")
    items: list[Requirement] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        requirement = parse_requirement(line)
        if requirement:
            items.append(requirement)
    return items


def inspect(requirements: Iterable[Requirement]) -> list[DependencyResult]:
    results: list[DependencyResult] = []
    for requirement in requirements:
        import_name = _IMPORT_NAMES.get(requirement.distribution, requirement.distribution.replace("-", "_"))
        required_text = (
            f"{requirement.operator}{requirement.version}"
            if requirement.operator and requirement.version
            else "installed"
        )
        try:
            installed = importlib.metadata.version(requirement.distribution)
        except importlib.metadata.PackageNotFoundError:
            results.append(DependencyResult(
                requirement.distribution,
                import_name,
                required_text,
                None,
                "missing",
                "Distribution is not installed.",
            ))
            continue

        if not _meets(installed, requirement.operator, requirement.version):
            results.append(DependencyResult(
                requirement.distribution,
                import_name,
                required_text,
                installed,
                "incompatible",
                "Installed version does not satisfy requirements.txt.",
            ))
            continue

        try:
            __import__(import_name)
        except Exception as exc:
            results.append(DependencyResult(
                requirement.distribution,
                import_name,
                required_text,
                installed,
                "broken",
                f"Distribution exists, but import failed: {exc}",
            ))
            continue

        results.append(DependencyResult(
            requirement.distribution,
            import_name,
            required_text,
            installed,
            "pass",
            "Installed and importable.",
        ))
    return results


def write_reports(results: list[DependencyResult]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    passed = all(item.status == "pass" for item in results)
    payload = {
        "schema": "cerebro-dependency-report/v0.1",
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "result": "pass" if passed else "fail",
        "dependencies": [asdict(item) for item in results],
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Cerebro Dependency Report",
        "==========================",
        f"Python: {sys.version.split()[0]}",
        f"Executable: {sys.executable}",
        "",
    ]
    for item in results:
        installed = item.installed or "not installed"
        lines.append(
            f"[{item.status.upper()}] {item.distribution} "
            f"(required: {item.required}; installed: {installed})"
        )
        if item.status != "pass":
            lines.append(f"  {item.details}")
    lines.extend(["", f"RESULT: {'PASS' if passed else 'FAIL'}", ""])
    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")


def print_results(results: list[DependencyResult]) -> bool:
    print()
    print("Cerebro environment check")
    print("==========================")
    print(f"Python {sys.version.split()[0]}")
    print(f"Executable: {sys.executable}")
    print()
    passed = True
    for item in results:
        installed = item.installed or "not installed"
        if item.status == "pass":
            print(f"[PASS] {item.distribution} {installed}")
        else:
            passed = False
            print(
                f"[FAIL] {item.distribution} "
                f"(required {item.required}; installed {installed})"
            )
            print(f"       {item.details}")
    print()
    if passed:
        print("[PASS] All required Python dependencies are available.")
    else:
        print("[FAIL] Required Python dependencies are missing or incompatible.")
        print("Run: python cerebro_tool.py install")
    return passed


def check() -> int:
    try:
        requirements = load_requirements()
        results = inspect(requirements)
    except Exception as exc:
        print(f"[FAIL] Dependency check could not run: {exc}")
        return EXIT_DEPENDENCY
    write_reports(results)
    return EXIT_OK if print_results(results) else EXIT_DEPENDENCY


def install() -> int:
    if not REQUIREMENTS.is_file():
        print(f"[FAIL] requirements.txt not found: {REQUIREMENTS}")
        return EXIT_DEPENDENCY

    print("Installing dependencies using the active Python interpreter:")
    print(sys.executable)
    print()
    process = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=ROOT,
    )
    if process.returncode != 0:
        print(f"[FAIL] pip returned exit code {process.returncode}.")
        return process.returncode

    print()
    print("Verifying installed dependencies...")
    return check()


def main() -> int:
    parser = argparse.ArgumentParser(description="Cerebro local dependency manager")
    parser.add_argument("command", choices=("check", "install"), nargs="?", default="check")
    args = parser.parse_args()
    return check() if args.command == "check" else install()


if __name__ == "__main__":
    raise SystemExit(main())
