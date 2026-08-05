from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from tooling.status.project_status import build_status


class ProjectStatusTests(unittest.TestCase):
    def workspace(self, root: Path) -> Path:
        (root / "Reports/Planning").mkdir(parents=True)
        (root / "Source/Cerebro_Source_v1.0").mkdir(parents=True)
        (root / "Client/Cerebro-Release-0.1").mkdir(parents=True)
        roadmap = {"current_phase": "terminology", "phases": [{"id": "PHASE-X", "name": "Terminology", "status": "IN_PROGRESS"}], "next_action": {"action": "Define level one", "blocker": "none"}}
        (root / "Reports/Planning/Cerebro_Roadmap_v1.yaml").write_text(yaml.safe_dump(roadmap), encoding="utf-8")
        return root

    def test_default_standard_shape_and_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = build_status(self.workspace(Path(temporary)))
            schema = yaml.safe_load((Path(__file__).resolve().parents[2] / "schemas/project-status.schema.yaml").read_text(encoding="utf-8"))
            self.assertFalse(list(Draft202012Validator(schema).iter_errors(report)))

    def test_brief_has_one_recommendation(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = build_status(self.workspace(Path(temporary)), "brief")
            self.assertEqual(len(report["recommendations"]), 1)

    def test_deep_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(build_status(self.workspace(Path(temporary)), "deep")["depth"], "deep")

    def test_scope_is_independent_from_depth(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = build_status(self.workspace(Path(temporary)), "standard", "PLC")
            self.assertEqual(report["scope"], "PLC")
            self.assertEqual(report["depth"], "standard")

    def test_recommendations_are_weighted_high_to_low(self):
        with tempfile.TemporaryDirectory() as temporary:
            weights = [item["weight"] for item in build_status(self.workspace(Path(temporary)))["recommendations"]]
            self.assertEqual(weights, [3, 2, 1])

    def test_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.workspace(Path(temporary))
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
            build_status(root)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

