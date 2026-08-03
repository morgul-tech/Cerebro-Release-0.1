#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, tempfile, zipfile
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "patch-manifest.schema.yaml"
EXIT_OK = 0
EXIT_VALIDATION = 4

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def validate_directory(patch_root: Path) -> dict[str, Any]:
    errors = []
    required = [
        "INSTALL_PATCH.bat", "PATCH_INSTALL.txt", "PATCH_CHANGELOG.txt",
        "PATCH_MANIFEST.yaml", "installer/patch_installer.py",
        "installer/locate_cerebro.py",
    ]
    for relative in required:
        if not (patch_root / relative).is_file():
            errors.append({"code": "missing_required_file", "path": relative})

    manifest = {}
    manifest_path = patch_root / "PATCH_MANIFEST.yaml"
    if manifest_path.is_file():
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
            for issue in Draft202012Validator(schema).iter_errors(manifest):
                errors.append({
                    "code": "manifest_schema_error",
                    "path": "/".join(str(x) for x in issue.path),
                    "details": issue.message,
                })
        except Exception as exc:
            errors.append({"code": "manifest_parse_error", "details": str(exc)})

    registered = set()
    for item in manifest.get("files", []):
        source = item.get("source")
        if not source:
            continue
        registered.add(source)
        path = patch_root / source
        if not path.is_file():
            errors.append({"code": "missing_payload_file", "path": source})
        elif sha256(path) != item.get("sha256"):
            errors.append({"code": "payload_checksum_mismatch", "path": source})

    actual = {
        str(path.relative_to(patch_root)).replace("\\", "/")
        for path in (patch_root / "repo").rglob("*")
        if path.is_file()
    } if (patch_root / "repo").is_dir() else set()

    for source in sorted(actual - registered):
        errors.append({"code": "unregistered_payload_file", "path": source})
    for source in sorted(registered - actual):
        errors.append({"code": "registered_payload_missing", "path": source})

    return {
        "schema": "cerebro-patch-validation-report/v0.1",
        "result": "pass" if not errors else "fail",
        "payload_files": len(actual),
        "errors": errors,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Cerebro patch")
    parser.add_argument("patch")
    args = parser.parse_args()
    supplied = Path(args.patch).resolve()
    temp = None
    try:
        if supplied.is_dir():
            patch_root = supplied
        elif supplied.is_file() and supplied.suffix.lower() == ".zip":
            temp = tempfile.TemporaryDirectory(prefix="cerebro-patch-")
            with zipfile.ZipFile(supplied, "r") as archive:
                archive.extractall(temp.name)
            patch_root = Path(temp.name)
        else:
            raise FileNotFoundError(supplied)
        report = validate_directory(patch_root)
    except Exception as exc:
        report = {"result": "fail", "errors": [{"code": "validator_failure", "details": str(exc)}]}
    print(json.dumps(report, indent=2))
    if temp is not None:
        temp.cleanup()
    return EXIT_OK if report["result"] == "pass" else EXIT_VALIDATION

if __name__ == "__main__":
    raise SystemExit(main())
