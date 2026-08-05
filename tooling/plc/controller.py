#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SIGNATURES = Path(__file__).with_name("signatures.yaml")


def load_signatures(path: Path = SIGNATURES) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("signatures", []))


def _matches(signature: dict[str, Any], text: str) -> bool:
    lowered = text.lower().replace("\\", "/")
    any_terms = [str(term).lower() for term in signature.get("match_any", [])]
    all_terms = [str(term).lower() for term in signature.get("match_all", [])]
    return (not any_terms or any(term in lowered for term in any_terms)) and all(term in lowered for term in all_terms)


def classify(event: dict[str, Any], signatures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    result = str(event.get("result", "UNKNOWN"))
    if result in {"SUCCESS", "ALREADY_APPLIED"}:
        return {
            "schema": "cerebro-patch-learning-report/v1",
            "patch": str(event.get("patch", "unknown")),
            "result": result,
            "classification": "successful_execution",
            "signature": None,
            "lifecycle": "observed",
            "autonomy_level": "A",
            "recommended_outcome": "CONTINUE",
            "verification_profile": "focused",
            "automatic_mutation_allowed": False,
        }

    evidence = " ".join((result, str(event.get("detail", ""))))
    for signature in signatures or load_signatures():
        if signature.get("lifecycle") == "active" and _matches(signature, evidence):
            return {
                "schema": "cerebro-patch-learning-report/v1",
                "patch": str(event.get("patch", "unknown")),
                "result": result,
                "classification": signature["classification"],
                "signature": signature["id"],
                "lifecycle": "active",
                "autonomy_level": signature["autonomy_level"],
                "recommended_outcome": signature["outcome"],
                "verification_profile": signature["verification_profile"],
                "automatic_mutation_allowed": signature["autonomy_level"] in {"A", "B", "C"},
            }

    return {
        "schema": "cerebro-patch-learning-report/v1",
        "patch": str(event.get("patch", "unknown")),
        "result": result,
        "classification": "unknown_patch_event",
        "signature": None,
        "lifecycle": "observed",
        "autonomy_level": "C",
        "recommended_outcome": "CONTINUE",
        "verification_profile": "full",
        "automatic_mutation_allowed": False,
    }


def record(event: dict[str, Any], report_dir: Path) -> Path:
    report = classify(event)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = report_dir / f"{report['patch']}-{stamp}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a Cerebro patch event")
    parser.add_argument("event")
    parser.add_argument("--record-dir")
    args = parser.parse_args()
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    report = classify(event)
    if args.record_dir:
        record(event, Path(args.record_dir))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

