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

    def test_post_rebase_regenerates_recent_changes_before_final_validation(self):
        rebase_start = self.text.index("git rebase origin/main")
        push_start = self.text.index("git push origin HEAD:main", rebase_start)
        post_rebase = self.text[rebase_start:push_start]
        recent_changes_start = post_rebase.index("python generate_recent_changes.py")
        candidate_signals_start = post_rebase.index("python -B build_candidate_signals.py")
        manifest_start = post_rebase.index("python -B build_publication_manifest.py")
        final_validation_start = post_rebase.index("git diff --exit-code")
        self.assertLess(recent_changes_start, candidate_signals_start)
        self.assertLess(recent_changes_start, manifest_start)
        self.assertLess(recent_changes_start, final_validation_start)
        self.assertIn("--news news_wire.json", post_rebase)
        self.assertIn("--claims claims_under_scrutiny.json", post_rebase)
        self.assertIn("--output recent_changes.json", post_rebase)
        reconciliation_start = post_rebase.index("if ! git diff --quiet")
        reconciliation_end = post_rebase.index(
            "if git diff --quiet origin/main..HEAD",
            reconciliation_start,
        )
        reconciliation = post_rebase[reconciliation_start:reconciliation_end]
        self.assertGreaterEqual(reconciliation.count("recent_changes.json"), 2)
        final_validation = post_rebase[final_validation_start:]
        self.assertIn("recent_changes.json", final_validation)

    def test_collector_diagnostics_are_summarized_without_publication(self):
        summary_start = self.text.index("- name: Summarize Claims collector diagnostics")
        validation_start = self.text.index(
            "- name: Validate and atomically stage fetched public data",
            summary_start,
        )
        summary = self.text[summary_start:validation_start]
        self.assertIn("if: always()", summary)
        self.assertIn("continue-on-error: true", summary)
        self.assertIn("/tmp/claims_under_scrutiny_diagnostics.json", summary)
        self.assertIn("diagnostics_path.exists()", summary)
        self.assertIn('os.environ["GITHUB_STEP_SUMMARY"]', summary)
        self.assertIn("candidate_query_count", summary)
        self.assertIn("query_status", summary)
        self.assertIn("excluded_unknown_hosts", summary)
        self.assertIn("invalid_reviews", summary)
        self.assertIn("unresolved_associations", summary)
        self.assertIn("deduplication", summary)
        self.assertIn("historical_evidence", summary)
        self.assertIn("final_counts", summary)
        self.assertIn('payload.get("failure")', summary)
        self.assertNotIn("upload-artifact", summary)
        commit_start = self.text.index("- name: Commit changed Claims Under Scrutiny data")
        self.assertNotIn(
            "claims_under_scrutiny_diagnostics.json",
            self.text[commit_start:],
        )


if __name__ == "__main__":
    unittest.main()
