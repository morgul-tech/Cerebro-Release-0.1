#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "standards" / "standards.yaml"
SCHEMA_PATH = ROOT / "schemas" / "standard-document.schema.yaml"
REPORT_PATH = ROOT / "validation" / "standards-report.json"

EXIT_OK = 0
EXIT_VALIDATION = 4


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_standards() -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not MANIFEST_PATH.is_file():
        errors.append({"code": "missing_manifest", "path": str(MANIFEST_PATH.relative_to(ROOT))})
        return {"result": "fail", "errors": errors, "validated": []}

    if not SCHEMA_PATH.is_file():
        errors.append({"code": "missing_schema", "path": str(SCHEMA_PATH.relative_to(ROOT))})
        return {"result": "fail", "errors": errors, "validated": []}

    manifest = load_yaml(MANIFEST_PATH)
    schema = load_yaml(SCHEMA_PATH)
    validator = Draft202012Validator(schema)

    documents = manifest.get("documents", [])
    registered_paths = {item.get("path") for item in documents}
    registered_ids: set[str] = set()
    validated: list[str] = []

    for entry in documents:
        standard_id = entry.get("id")
        relative = entry.get("path")
        required = bool(entry.get("required", False))

        if not standard_id or not relative:
            errors.append({"code": "invalid_registry_entry", "path": str(relative)})
            continue

        path = ROOT / relative
        if not path.is_file():
            if required:
                errors.append({"code": "missing_required_standard", "path": relative})
            continue

        try:
            document = load_yaml(path)
        except Exception as exc:
            errors.append({"code": "yaml_parse_error", "path": relative, "details": str(exc)})
            continue

        for issue in validator.iter_errors(document):
            location = "/".join(str(part) for part in issue.path)
            errors.append({
                "code": "schema_error",
                "path": f"{relative}:{location}",
                "details": issue.message,
            })

        document_id = document.get("standard", {}).get("id")
        if document_id != standard_id:
            errors.append({
                "code": "registry_id_mismatch",
                "path": relative,
                "details": f"registry={standard_id}; document={document_id}",
            })

        if document_id in registered_ids:
            errors.append({"code": "duplicate_standard_id", "path": relative, "details": document_id})
        registered_ids.add(document_id)

        rule_ids = [rule.get("id") for rule in document.get("rules", [])]
        if len(rule_ids) != len(set(rule_ids)):
            errors.append({"code": "duplicate_rule_id", "path": relative})

        validated.append(relative)

    actual_standard_files = {
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "standards").glob("*.yaml")
        if path.name != "standards.yaml"
    }
    unregistered = sorted(actual_standard_files - registered_paths)
    for relative in unregistered:
        errors.append({"code": "unregistered_standard", "path": relative})

    return {
        "schema": "cerebro-standards-report/v0.1",
        "result": "pass" if not errors else "fail",
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
        "validated": sorted(validated),
        "errors": errors,
    }


def main() -> int:
    report = validate_standards()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return EXIT_OK if report["result"] == "pass" else EXIT_VALIDATION


if __name__ == "__main__":
    raise SystemExit(main())
