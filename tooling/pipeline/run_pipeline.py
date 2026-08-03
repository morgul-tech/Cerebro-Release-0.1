#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "builder-pipeline.schema.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Cerebro Builder pipeline")
    parser.add_argument("pipeline", nargs="?", default="release")
    args = parser.parse_args()

    config_path = ROOT / "tooling" / "pipeline" / f"{args.pipeline}.yaml"
    if not config_path.is_file():
        print(f"[FAIL] Pipeline not found: {config_path}")
        return 4

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    issues = list(Draft202012Validator(schema).iter_errors(config))
    if issues:
        for issue in issues:
            location = "/".join(str(part) for part in issue.path)
            print(f"[FAIL] Pipeline schema: {location}: {issue.message}")
        return 4

    report = {
        "schema": "cerebro-builder-pipeline-report/v0.1",
        "pipeline": config["pipeline"]["id"],
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "result": "pass",
        "failed_stage": None,
        "stages": [],
    }

    for stage in config["stages"]:
        if not stage.get("enabled", True):
            report["stages"].append({
                "id": stage["id"],
                "name": stage["name"],
                "status": "skipped",
            })
            continue

        script = ROOT / stage["script"]
        print(f"\n=== {stage['id']} | {stage['name']} ===")

        if not script.is_file():
            code = 4
            details = f"Missing script: {stage['script']}"
        else:
            process = subprocess.run(
                [sys.executable, str(script), *stage.get("arguments", [])],
                cwd=ROOT,
            )
            code = process.returncode
            details = f"Exit code {code}"

        status = "pass" if code == 0 else "fail"
        report["stages"].append({
            "id": stage["id"],
            "name": stage["name"],
            "required": stage["required"],
            "status": status,
            "exit_code": code,
            "details": details,
        })

        if status == "fail" and stage["required"]:
            report["result"] = "fail"
            report["failed_stage"] = stage["id"]
            if config["pipeline"]["fail_fast"]:
                break

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report_path = ROOT / config["pipeline"]["report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if report["result"] == "pass":
        print("\nPIPELINE PASS")
        return 0

    print(f"\nPIPELINE FAIL at {report['failed_stage']}")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
