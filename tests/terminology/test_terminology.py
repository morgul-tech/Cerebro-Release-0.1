from __future__ import annotations

import unittest
from collections import defaultdict
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


class TerminologyLevelZeroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.document = yaml.safe_load((cls.root / "core/terminology.yaml").read_text(encoding="utf-8"))

    def test_schema(self):
        schema = yaml.safe_load((self.root / "schemas/terminology.schema.yaml").read_text(encoding="utf-8"))
        self.assertFalse(list(Draft202012Validator(schema).iter_errors(self.document)))

    def test_required_level_zero_terms(self):
        required = {"cerebro", "cerebro_source", "cerebro_release", "working_source", "working_release", "published_source_baseline", "published_release_baseline", "cerebro_runtime", "synchronization"}
        self.assertTrue(required.issubset(self.document["terms"]))

    def test_user_aliases_are_unique(self):
        aliases = defaultdict(list)
        for identifier, term in self.document["terms"].items():
            for alias in term["aliases"]:
                aliases[alias.casefold()].append(identifier)
        self.assertEqual({}, {alias: owners for alias, owners in aliases.items() if len(owners) > 1})

    def test_policy_and_publication_authority_are_distinct(self):
        terms = self.document["terms"]
        self.assertEqual(terms["cerebro_source"]["authority_dimension"], "policy")
        self.assertEqual(terms["published_release_baseline"]["authority_dimension"], "published-implementation-bytes")

    def test_release_contexts_are_explicit(self):
        release = self.document["contextual_aliases"]["release"]
        self.assertEqual(release["local_file_validation_install"], "working_release")
        self.assertIn("published_release_baseline", release["github_remote_branch_commit"])


if __name__ == "__main__":
    unittest.main()
