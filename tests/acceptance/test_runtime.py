from __future__ import annotations
import copy
import unittest

from cerebro_runtime import CerebroRuntime


class RuntimeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = CerebroRuntime()

    def test_ac001_standard_mode(self):
        result = self.runtime.run({"input": "What is the status?"})
        self.assertEqual(result["dialog"]["work_mode"], "standard")
        self.assertFalse(result["project"]["active"])

    def test_ac002_collaboration_mode(self):
        result = self.runtime.run({"input": "Develop an option together"}, features={
            "dependent_steps": "some", "continuity_required": "yes",
            "deliverable_count": "one", "ambiguity_risk": "low", "duration": "single_response",
        })
        self.assertEqual(result["dialog"]["work_mode"], "collaboration")
        self.assertIn("collaboration", result["dialog"]["active_modules"])

    def test_ac003_project_mode(self):
        result = self.runtime.run({
            "input": "Build release", "goal": "Validated release",
            "deliverables": [{"id": "d1", "description": "runtime", "status": "pending", "requirement_refs": []}],
        }, features={
            "dependent_steps": "many", "continuity_required": "yes",
            "deliverable_count": "multiple", "ambiguity_risk": "medium", "duration": "extended",
        })
        self.assertEqual(result["dialog"]["work_mode"], "project")
        self.assertTrue(result["project"]["active"])
        self.assertIn("project-lite", result["dialog"]["active_modules"])

    def test_ac004_recommendation_not_decision(self):
        result = self.runtime.run({"input": "Recommend", "recommendation": "Option A"})
        types = [x["type"] for x in result["context"]["items"]]
        self.assertIn("recommendation", types)
        self.assertNotIn("decision", types)

    def test_ac005_approval_creates_decision(self):
        result = self.runtime.run({
            "input": "Approve", "recommendation": "Option A", "approve_recommendation": True,
        })
        decisions = [x for x in result["context"]["items"] if x["type"] == "decision"]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["source"]["type"], "user")

    def test_ac006_conflicting_decisions_stop(self):
        context = []
        for i, value in enumerate(({"key": "layout", "choice": "A"}, {"key": "layout", "choice": "B"}), 1):
            item = self.runtime._context_item(i, "decision", value, "user", 4)
            item["activation"] = {"activated_by": "user", "activation_reference": "test"}
            context.append(item)
        result = self.runtime.run({"input": "Continue", "context": context})
        self.assertEqual(result["runtime"]["status"], "blocked")
        self.assertEqual(result["dialog"]["control_stop"]["reason_code"], "conflicting_decisions")

    def test_ac007_noncritical_missing_detail_warns(self):
        result = self.runtime.run({"input": "Continue", "missing_noncritical_detail": True})
        self.assertEqual(result["quality"]["status"], "warning")
        self.assertIn("assumption", [x["type"] for x in result["context"]["items"]])

    def test_ac008_missing_required_goal_blocks(self):
        result = self.runtime.run({"input": "Run project", "goal_required": True}, features={
            "dependent_steps": "many", "continuity_required": "yes",
            "deliverable_count": "multiple", "ambiguity_risk": "high", "duration": "extended",
        })
        self.assertEqual(result["runtime"]["status"], "blocked")
        self.assertEqual(result["dialog"]["control_stop"]["reason_code"], "missing_required_goal")

    def test_ac009_repeated_execution_equivalent(self):
        task = {"input": "Repeat", "recommendation": "A"}
        first = self.runtime.run(copy.deepcopy(task))
        second = self.runtime.run(copy.deepcopy(task))
        self.assertEqual(self.runtime.state_hash(first), self.runtime.state_hash(second))

    def test_ac010_presentation_does_not_mutate_analysis(self):
        task = {"input": "Present result", "recommendation": "A"}
        text = self.runtime.run(copy.deepcopy(task), presentation_model="text")
        table = self.runtime.run(copy.deepcopy(task), presentation_model="table")
        for result in (text, table):
            result["presentation"] = {}
            result["trace"]["events"] = [e for e in result["trace"]["events"] if e["type"] != "presentation_selected"]
        self.assertEqual(self.runtime.state_hash(text), self.runtime.state_hash(table))


if __name__ == "__main__":
    unittest.main()
