from __future__ import annotations

import unittest

from tooling.progress.decision import DecisionContext, Outcome, decide


class OperationalProgressDecisionTests(unittest.TestCase):
    def test_authorized_objective_continues_by_default(self):
        self.assertEqual(decide(DecisionContext(True)), Outcome.CONTINUE)

    def test_safety_has_highest_precedence(self):
        self.assertEqual(decide(DecisionContext(True, safety_block=True, qualified_remediation=True)), Outcome.SAFETY_BLOCK)

    def test_missing_authority_requires_user(self):
        self.assertEqual(decide(DecisionContext(True, missing_authority=True)), Outcome.USER_DECISION_REQUIRED)

    def test_missing_objective_requires_user(self):
        self.assertEqual(decide(DecisionContext(False)), Outcome.USER_DECISION_REQUIRED)

    def test_genuine_choice_requires_user(self):
        self.assertEqual(decide(DecisionContext(True, genuine_user_choice=True)), Outcome.USER_DECISION_REQUIRED)

    def test_qualified_problem_is_remediated(self):
        self.assertEqual(decide(DecisionContext(True, qualified_remediation=True)), Outcome.REMEDIATE_AND_CONTINUE)

    def test_retry_requires_progress_delta(self):
        self.assertEqual(decide(DecisionContext(True, retry_requested=True, progress_delta=True)), Outcome.RETRY)

    def test_identical_retry_is_blocked(self):
        self.assertEqual(decide(DecisionContext(True, retry_requested=True)), Outcome.SAFETY_BLOCK)


if __name__ == "__main__":
    unittest.main()
