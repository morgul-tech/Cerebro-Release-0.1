from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tooling.plc.controller import classify, record
import yaml
from jsonschema import Draft202012Validator


def event(result="FAILED_ROLLED_BACK", detail=""):
    return {"schema": "cerebro-patch-learning-event/v1", "patch": "0301", "result": result, "exit_code": 30, "timestamp": "2026-08-05T00:00:00Z", "detail": detail}


class PatchLearningControllerTests(unittest.TestCase):
    def test_success_continues_without_mutation(self):
        report = classify(event("SUCCESS"))
        self.assertEqual(report["recommended_outcome"], "CONTINUE")
        self.assertFalse(report["automatic_mutation_allowed"])

    def test_python_cache_signature(self):
        report = classify(event(detail="QG-004 tooling/patch/__pycache__/x.pyc"))
        self.assertEqual(report["signature"], "PLC-PY-CACHE-001")
        self.assertEqual(report["autonomy_level"], "A")

    def test_generated_report_signature_normalizes_windows_paths(self):
        report = classify(event(detail=r"Mismatch validation\standards-report.json"))
        self.assertEqual(report["signature"], "PLC-GENERATED-REPORT-001")

    def test_plan_inventory_requires_both_terms(self):
        report = classify(event(detail="integrity mismatch from local sprint-plan.yaml"))
        self.assertEqual(report["signature"], "PLC-LOCAL-PLAN-INTEGRITY-001")

    def test_unknown_is_observed_not_automated(self):
        report = classify(event(detail="new unexplained failure"))
        self.assertEqual(report["lifecycle"], "observed")
        self.assertFalse(report["automatic_mutation_allowed"])

    def test_record_writes_structured_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = record(event(detail="__pycache__"), Path(temporary))
            report = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "cerebro-patch-learning-report/v1")

    def test_event_and_report_schemas(self):
        root = Path(__file__).resolve().parents[2]
        event_schema = yaml.safe_load((root / "schemas/patch-learning-event.schema.yaml").read_text(encoding="utf-8"))
        report_schema = yaml.safe_load((root / "schemas/patch-learning-report.schema.yaml").read_text(encoding="utf-8"))
        self.assertFalse(list(Draft202012Validator(event_schema).iter_errors(event())))
        self.assertFalse(list(Draft202012Validator(report_schema).iter_errors(classify(event()))))

    def test_signature_registry_schema(self):
        root = Path(__file__).resolve().parents[2]
        schema = yaml.safe_load((root / "schemas/patch-learning-signatures.schema.yaml").read_text(encoding="utf-8"))
        registry = yaml.safe_load((root / "tooling/plc/signatures.yaml").read_text(encoding="utf-8"))
        self.assertFalse(list(Draft202012Validator(schema).iter_errors(registry)))


if __name__ == "__main__":
    unittest.main()
