#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "quality"
REPORT_JSON = REPORT_DIR / "quality-report.json"
REPORT_TXT = REPORT_DIR / "quality-report.txt"

FORBIDDEN_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "Thumbs.db",
    ".DS_Store",
}
FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
    ".swp",
    ".swo",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_generated_python_cache() -> None:
    for path in sorted(ROOT.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
    for suffix in ("*.pyc", "*.pyo"):
        for path in ROOT.rglob(suffix):
            if path.is_file():
                path.unlink()


def record(
    checks: list[dict[str, Any]],
    check_id: str,
    name: str,
    passed: bool,
    details: str,
) -> None:
    checks.append({
        "id": check_id,
        "name": name,
        "status": "pass" if passed else "fail",
        "details": details,
    })


def check_python_syntax(checks: list[dict[str, Any]]) -> None:
    errors = []
    files = sorted(ROOT.rglob("*.py"))

    for path in files:
        if any(part in FORBIDDEN_NAMES for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    record(
        checks,
        "QG-001",
        "Python Syntax",
        not errors,
        f"{len(files)} Python files compiled in memory"
        if not errors else "; ".join(errors),
    )


def check_yaml_json(checks: list[dict[str, Any]]) -> None:
    errors = []
    yaml_count = 0
    json_count = 0

    for path in sorted(ROOT.rglob("*.yaml")):
        yaml_count += 1
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    for path in sorted(ROOT.rglob("*.json")):
        json_count += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    record(
        checks,
        "QG-002",
        "YAML and JSON Parse",
        not errors,
        (
            f"{yaml_count} YAML and {json_count} JSON files parsed"
            if not errors else "; ".join(errors)
        ),
    )


def check_manifest(
    checks: list[dict[str, Any]],
    patch_root: Path,
) -> dict[str, Any]:
    errors = []
    manifest_path = patch_root / "PATCH_MANIFEST.yaml"
    manifest: dict[str, Any] = {}

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        schema = yaml.safe_load(
            (ROOT / "schemas/patch-manifest.schema.yaml").read_text(encoding="utf-8")
        )

        for issue in Draft202012Validator(schema).iter_errors(manifest):
            location = "/".join(str(part) for part in issue.path)
            errors.append(f"{location}: {issue.message}")

        seen_sources = set()
        seen_destinations = set()

        for item in manifest.get("files", []):
            source = item.get("source", "")
            destination = item.get("destination", "")

            if source in seen_sources:
                errors.append(f"Duplicate source: {source}")
            if destination in seen_destinations:
                errors.append(f"Duplicate destination: {destination}")

            seen_sources.add(source)
            seen_destinations.add(destination)

            path = patch_root / source
            if not path.is_file():
                errors.append(f"Missing payload: {source}")
            elif sha256(path) != item.get("sha256"):
                errors.append(f"Checksum mismatch: {source}")
    except Exception as exc:
        errors.append(str(exc))

    record(
        checks,
        "QG-003",
        "Patch Manifest",
        not errors,
        "Schema, uniqueness, payloads, and checksums valid"
        if not errors else "; ".join(errors),
    )
    return manifest


def check_repository_hygiene(checks: list[dict[str, Any]]) -> None:
    offenders = []

    for path in ROOT.rglob("*"):
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            offenders.append(str(path.relative_to(ROOT)))

    record(
        checks,
        "QG-004",
        "Repository Hygiene",
        not offenders,
        "No forbidden cache, temporary, backup, or editor files"
        if not offenders else ", ".join(offenders[:50]),
    )


def run_command(command: list[str]) -> tuple[bool, str]:
    resolved = [
        sys.executable if token == "{PYTHON}" else token
        for token in command
    ]
    process = subprocess.run(
        resolved,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    combined = (process.stdout + process.stderr).strip()
    return process.returncode == 0, combined[-4000:]


def check_smoke(checks: list[dict[str, Any]]) -> None:
    commands = [
        ["{PYTHON}", "cerebro_tool.py", "standards"],
        ["{PYTHON}", "cerebro_tool.py", "repository"],
        ["{PYTHON}", "cerebro_tool.py", "validate"],
    ]
    failures = []

    for command in commands:
        passed, details = run_command(command)
        if not passed:
            failures.append(f"{' '.join(command)}: {details}")

    record(
        checks,
        "QG-005",
        "Smoke Tests",
        not failures,
        "Standards, repository, and validation commands passed"
        if not failures else "; ".join(failures),
    )


def check_pipeline(
    checks: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    command = manifest.get("publication", {}).get("pipeline")

    if not isinstance(command, list) or not command:
        record(
            checks,
            "QG-006",
            "Selected Pipeline",
            False,
            "Publication pipeline command is missing",
        )
        return

    passed, details = run_command(command)
    record(
        checks,
        "QG-006",
        "Selected Pipeline",
        passed,
        "Selected publication pipeline passed" if passed else details,
    )


def check_approved_paths(
    checks: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    errors = []
    prefix = "{REPOSITORY_ROOT}/"
    approved = set()

    for item in manifest.get("files", []):
        destination = str(item.get("destination", "")).replace("\\", "/")
        if destination.startswith(prefix):
            approved.add(destination.removeprefix(prefix).strip("/"))

    for path in manifest.get("publication", {}).get("generated_paths", []):
        normalized = str(path).replace("\\", "/").strip("/")
        if not normalized:
            errors.append("Empty generated path")
        approved.add(normalized)

    for path in sorted(approved):
        if path.startswith("../") or "/../" in path or Path(path).is_absolute():
            errors.append(f"Unsafe approved path: {path}")

    record(
        checks,
        "QG-007",
        "Approved Publication Paths",
        bool(approved) and not errors,
        f"{len(approved)} approved paths are scoped and safe"
        if approved and not errors else "; ".join(errors) or "No approved paths",
    )


def write_reports(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item["id"] for item in checks if item["status"] != "pass"]
    report = {
        "schema": "cerebro-quality-report/v0.1",
        "artifact": "Cerebro Release 0.1",
        "result": "pass" if not failed else "fail",
        "ready_for_publication": not failed,
        "failed_checks": failed,
        "checks": checks,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "CEREBRO QUALITY GATE",
        "====================",
        "",
    ]
    for item in checks:
        lines.append(
            f"{item['id']} {item['name']:.<34} {item['status'].upper()}"
        )
        if item["status"] != "pass":
            lines.append(f"  {item['details']}")

    lines.extend([
        "",
        "READY FOR PUBLICATION"
        if report["ready_for_publication"]
        else "PUBLICATION BLOCKED",
        "",
    ])

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Cerebro Quality Gate")
    parser.add_argument("--patch-root", required=True)
    args = parser.parse_args()

    patch_root = Path(args.patch_root).resolve()
    checks: list[dict[str, Any]] = []

    # Remove only generated Python bytecode/cache artifacts before QA.
    remove_generated_python_cache()

    check_python_syntax(checks)
    check_yaml_json(checks)
    manifest = check_manifest(checks, patch_root)
    check_repository_hygiene(checks)
    check_smoke(checks)
    check_pipeline(checks, manifest)
    check_approved_paths(checks, manifest)

    report = write_reports(checks)
    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_publication"] else 9


if __name__ == "__main__":
    raise SystemExit(main())
