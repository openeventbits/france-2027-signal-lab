import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-claims-under-scrutiny.yml"


class ClaimsWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_and_registry_query_source(self):
        self.assertIn('cron: "47 7,17 * * *"', self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            self.text,
        )
        self.assertIn("--existing-claims claims_under_scrutiny.json", self.text)

    def test_poll_roster_arguments_are_removed(self):
        fetch_start = self.text.index("python fetch_claims_under_scrutiny.py")
        fetch_end = self.text.index("- name: Validate", fetch_start)
        fetch = self.text[fetch_start:fetch_end]
        self.assertNotIn("--polls", fetch)
        self.assertNotIn("--candidate-window-days", fetch)
        self.assertNotIn("candidate_roster", self.text)

    def test_fetched_claims_validate_against_registry(self):
        self.assertIn("load_candidate_candidacy_status", self.text)
        fetched_start = self.text.index("fetched = load_json(fetched_path)")
        current_start = self.text.index("if current_path.exists():", fetched_start)
        fetched_validation = self.text[fetched_start:current_start]
        self.assertIn("candidacy_payload=candidacy", fetched_validation)
        self.assertIn("fetched['candidate_query']['count']", self.text)
        self.assertIn("test_claims_workflow_contract.py", self.text)

    def test_existing_claims_validate_as_historical_snapshot(self):
        current_start = self.text.index("if current_path.exists():")
        comparison_start = self.text.index("changed = semantic_public_content", current_start)
        current_validation = self.text[current_start:comparison_start]
        self.assertIn("candidacy_payload=None", current_validation)
        self.assertNotIn("candidacy_payload=candidacy", current_validation)

    def test_publication_safety_contract_is_preserved(self):
        self.assertIn("semantic_public_content", self.text)
        self.assertIn("atomic_write_json(current_path, fetched)", self.text)
        self.assertIn("build_publication_manifest.py", self.text)
        self.assertIn("git rebase origin/", self.text)
        self.assertNotIn("--force", self.text)


if __name__ == "__main__":
    unittest.main()
