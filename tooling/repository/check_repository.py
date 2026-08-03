#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = ROOT / "validation" / "repository-report.json"
REPORT_TXT = ROOT / "validation" / "repository-report.txt"

EXIT_OK = 0
EXIT_INTEGRITY = 4


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def required_paths() -> list[str]:
    manifest_path = ROOT / "cerebro.yaml"
    required = [
        "cerebro.yaml",
        "cerebro_tool.py",
        "requirements.txt",
        "run_tests.py",
        "tooling/builder/build_release.py",
        "tooling/validator/validate.py",
        "tooling/dependencies/check_dependencies.py",
        "tooling/standards/validate_standards.py",
        "tooling/repository/check_repository.py",
        "tooling/patch/install_patch.py",
        "validation/release-criteria.yaml",
        "standards/standards.yaml",
    ]

    if manifest_path.is_file():
        manifest = load_yaml(manifest_path)
        for section in ("runtime", "core", "standards"):
            for value in manifest.get(section, {}).values():
                if isinstance(value, str):
                    required.append(value)
        for engine in manifest.get("engines", []):
            path = str(engine.get("path", "")).rstrip("/")
            if path:
                required.append(path)
                required.append(f"{path}/module.yaml")

    return sorted(set(required))


def check_repository() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing: list[str] = []

    for relative in required_paths():
        path = ROOT / relative
        exists = path.exists()
        checks.append({
            "path": relative.replace("\\", "/"),
            "status": "pass" if exists else "fail",
            "type": "directory" if path.is_dir() else "file",
        })
        if not exists:
            missing.append(relative.replace("\\", "/"))

    critical_dirs = [
        "core", "runtime", "engines", "standards", "schemas",
        "tooling", "tests", "validation",
    ]
    for relative in critical_dirs:
        path = ROOT / relative
        if not path.is_dir() and relative not in missing:
            missing.append(relative)
            checks.append({"path": relative, "status": "fail", "type": "directory"})

    return {
        "schema": "cerebro-repository-report/v0.1",
        "root": str(ROOT),
        "result": "pass" if not missing else "fail",
        "missing": sorted(set(missing)),
        "checks": checks,
    }


def write_reports(report: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Cerebro Repository Integrity Report",
        "===================================",
        f"Root: {report['root']}",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"[{check['status'].upper()}] {check['path']}")
    lines.extend(["", f"RESULT: {report['result'].upper()}", ""])
    if report["missing"]:
        lines.append("Missing:")
        lines.extend(f"- {item}" for item in report["missing"])
        lines.append("")
    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = check_repository()
    except Exception as exc:
        print(f"[FAIL] Repository check could not run: {exc}")
        return EXIT_INTEGRITY

    write_reports(report)
    print(json.dumps(report, indent=2))
    return EXIT_OK if report["result"] == "pass" else EXIT_INTEGRITY


if __name__ == "__main__":
    raise SystemExit(main())
