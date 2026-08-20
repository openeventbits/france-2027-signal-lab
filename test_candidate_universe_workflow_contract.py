import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "update-candidate-universe.yml"
)
COLLECTOR_PATH = ROOT / "fetch_candidate_candidacy_status.py"


def step_block(workflow: str, name: str) -> str:
    marker = f"      - name: {name}"
    start = workflow.index(marker)
    end = workflow.find("\n      - name:", start + len(marker))
    return workflow[start:] if end == -1 else workflow[start:end]


class CandidateUniverseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.collector = COLLECTOR_PATH.read_text(encoding="utf-8")

    def test_daily_schedule_dispatch_permissions_and_concurrency(self):
        self.assertEqual(self.workflow.count('cron: "5 4 * * *"'), 1)
        self.assertEqual(
            len(re.findall(r"^\s*- cron:", self.workflow, re.MULTILINE)),
            1,
        )
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("permissions:\n  contents: write", self.workflow)
        self.assertIn(
            "concurrency:\n"
            "  group: production-data-update\n"
            "  cancel-in-progress: false",
            self.workflow,
        )

    def test_checkout_and_runtime_match_production_conventions(self):
        self.assertIn("actions/checkout@v7", self.workflow)
        self.assertIn("ref: main", self.workflow)
        self.assertIn("fetch-depth: 0", self.workflow)
        self.assertIn("actions/setup-python@v6", self.workflow)
        self.assertIn('python-version: "3.12"', self.workflow)
        self.assertIn('PYTHONDONTWRITEBYTECODE: "1"', self.workflow)
        self.assertNotIn("pip install", self.workflow)

    def test_generation_uses_previous_and_temporary_output(self):
        generation = step_block(
            self.workflow,
            "Fetch and reconcile exact Wikipedia revision",
        )
        self.assertIn("fetch_candidate_candidacy_status.py", generation)
        self.assertIn("--previous candidate_candidacy_status.json", generation)
        self.assertIn(
            "--output /tmp/candidate_candidacy_status.json",
            generation,
        )
        self.assertNotIn(
            "--output candidate_candidacy_status.json",
            generation,
        )

    def test_collector_pins_exact_revision_and_guards_before_output(self):
        metadata = self.collector.index("def fetch_current_revision(")
        pinned_parse = self.collector.index("def fetch_parsed_revision(")
        self.assertLess(metadata, pinned_parse)
        self.assertIn('"oldid": str(revision_id)', self.collector)
        self.assertIn("parsed_revision_id != revision_id", self.collector)
        build = self.collector.index("def _build_payload_details(")
        guard = self.collector.index(
            "validate_extraction_anomalies(", build
        )
        output = self.collector.index("def write_payload_atomic(")
        self.assertLess(guard, output)

    def test_semantic_compare_and_no_op_preserve_tracked_bytes(self):
        validation = step_block(
            self.workflow,
            "Validate candidate and promote semantic change atomically",
        )
        self.assertIn("semantic_sha256(previous)", validation)
        self.assertIn("semantic_sha256(candidate)", validation)
        self.assertIn("previous_path.read_bytes()", validation)
        self.assertIn(
            "semantic no-op changed the tracked Candidate Registry",
            validation,
        )
        self.assertIn("write_payload_atomic(candidate, previous_path)", validation)
        self.assertLess(
            validation.index("semantic_changed ="),
            validation.index("write_payload_atomic(candidate, previous_path)"),
        )

    def test_same_run_derived_builds_are_change_gated_and_temporary_first(self):
        campaign_events = step_block(
            self.workflow,
            "Rebuild Campaign Events on registry change",
        )
        signals = step_block(
            self.workflow,
            "Rebuild Candidate Signals on registry change",
        )
        visibility_history = step_block(
            self.workflow,
            "Rebuild Candidate Visibility History on registry change",
        )
        manifest = step_block(
            self.workflow,
            "Rebuild publication manifest on registry change",
        )

        change_gate = "if: steps.registry.outputs.changed == 'true'"

        self.assertIn(change_gate, campaign_events)
        self.assertIn("python -B build_campaign_events.py", campaign_events)
        self.assertIn(
            "--candidates candidate_candidacy_status.json",
            campaign_events,
        )
        self.assertIn(
            "--preserve-generated-at-from campaign_events.json",
            campaign_events,
        )
        self.assertIn(
            "--output /tmp/campaign_events.json",
            campaign_events,
        )
        self.assertIn(
            "from build_campaign_events import atomic_write",
            campaign_events,
        )
        self.assertIn(
            'atomic_write(tracked, candidate_bytes)',
            campaign_events,
        )

        self.assertIn(change_gate, signals)
        self.assertIn("--output /tmp/candidate_signals.json", signals)
        self.assertIn("validate_candidate_signals", signals)
        self.assertIn("atomic_write(", signals)

        self.assertIn(change_gate, visibility_history)
        self.assertIn(
            "python -B build_candidate_visibility_history.py",
            visibility_history,
        )
        self.assertIn(
            "--news news_wire.json",
            visibility_history,
        )
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            visibility_history,
        )
        self.assertIn(
            "--output /tmp/candidate_visibility_history.json",
            visibility_history,
        )
        self.assertIn(
            "validate_candidate_visibility_history",
            visibility_history,
        )
        self.assertIn(
            "atomic_write_bytes",
            visibility_history,
        )

        self.assertIn(change_gate, manifest)
        self.assertIn("/tmp/publication_manifest.json", manifest)
        self.assertIn("validate_manifest", manifest)

        campaign_position = self.workflow.index(
            "Rebuild Campaign Events on registry change"
        )
        signals_position = self.workflow.index(
            "Rebuild Candidate Signals on registry change"
        )
        visibility_history_position = self.workflow.index(
            "Rebuild Candidate Visibility History on registry change"
        )
        manifest_position = self.workflow.index(
            "Rebuild publication manifest on registry change"
        )

        self.assertLess(campaign_position, signals_position)
        self.assertLess(
            signals_position,
            visibility_history_position,
        )
        self.assertLess(
            visibility_history_position,
            manifest_position,
        )

    def test_campaign_events_rebuild_preserves_no_churn_semantics(self):
        campaign_events = step_block(
            self.workflow,
            "Rebuild Campaign Events on registry change",
        )

        self.assertIn(
            "if: steps.registry.outputs.changed == 'true'",
            campaign_events,
        )
        self.assertIn(
            '--generated-at "$campaign_events_generated_at"',
            campaign_events,
        )
        self.assertIn(
            "--preserve-generated-at-from campaign_events.json",
            campaign_events,
        )
        self.assertIn(
            'summary["campaign_events_rebuilt"] = True',
            campaign_events,
        )
        self.assertIn(
            'summary["campaign_events_changed"] = (',
            campaign_events,
        )

    def test_generated_scope_and_stage_scope_are_exact(self):
        scope = step_block(
            self.workflow,
            "Verify bounded generated-file scope",
        )
        allowed_pattern = (
            "^(candidate_candidacy_status|candidate_signals|"
            "candidate_visibility_history|campaign_events|"
            "publication_manifest)\\.json$"
        )
        self.assertIn(allowed_pattern, scope)

        commit = step_block(
            self.workflow,
            "Commit, rebase, validate, and push candidate universe",
        )
        stage = commit[
            commit.index("git add --"):
            commit.index("git commit -m")
        ]

        for required in (
            "candidate_candidacy_status.json",
            "campaign_events.json",
            "candidate_signals.json",
            "candidate_visibility_history.json",
            "publication_manifest.json",
        ):
            self.assertIn(required, stage)

        for forbidden in (
            "candidate_attention.json",
            "claims_under_scrutiny.json",
            "news_wire.json",
            "polls.json",
            "recent_changes.json",
            "git add -A",
            "git add --all",
        ):
            self.assertNotIn(forbidden, stage)

        self.assertIn("git diff --cached --check", commit)
        self.assertIn(
            'git commit -m "Update candidate universe"',
            commit,
        )

    def test_rebase_push_is_non_forcing_and_revalidates_derived_artifacts(self):
        commit = step_block(
            self.workflow,
            "Commit, rebase, validate, and push candidate universe",
        )

        self.assertIn("git fetch origin main", commit)
        self.assertIn("git rebase origin/main", commit)
        self.assertIn("build_from_paths(", commit)
        self.assertIn(
            "build_visibility_history_from_payloads(",
            commit,
        )
        self.assertIn("build_manifest(", commit)
        self.assertIn("git push origin HEAD:main", commit)
        self.assertNotIn("--force", commit)

        rebase_position = commit.index(
            "git rebase origin/main"
        )
        campaign_position = commit.index(
            "python -B build_campaign_events.py",
            rebase_position,
        )
        signals_position = commit.index(
            "build_from_paths(",
            campaign_position,
        )
        visibility_history_position = commit.index(
            "build_visibility_history_from_payloads(",
            signals_position,
        )
        manifest_position = commit.index(
            "build_manifest(",
            visibility_history_position,
        )

        self.assertLess(rebase_position, campaign_position)
        self.assertLess(campaign_position, signals_position)
        self.assertLess(
            signals_position,
            visibility_history_position,
        )
        self.assertLess(
            visibility_history_position,
            manifest_position,
        )

        post_rebase = commit[campaign_position:]

        self.assertIn(
            "--candidates candidate_candidacy_status.json",
            post_rebase,
        )
        self.assertIn(
            "--preserve-generated-at-from campaign_events.json",
            post_rebase,
        )
        self.assertIn(
            "--output /tmp/campaign_events-rebase.json",
            post_rebase,
        )
        self.assertIn(
            "campaign_events.json",
            post_rebase,
        )
        self.assertIn(
            "candidate_visibility_history.json",
            post_rebase,
        )
        self.assertIn(
            "build_visibility_history_from_payloads(",
            post_rebase,
        )
        self.assertIn(
            "git commit --amend --no-edit",
            post_rebase,
        )

    def test_no_unrelated_downstream_collectors_are_invoked(self):
        self.assertEqual(
            self.workflow.count(
                "python -B build_campaign_events.py"
            ),
            2,
        )
        self.assertEqual(
            self.workflow.count(
                "python -B build_candidate_visibility_history.py"
            ),
            1,
        )

        for forbidden in (
            "fetch_news_wire.py",
            "fetch_claims_under_scrutiny.py",
            "build_candidate_attention.py",
            "fetch_polls.py",
            "generate_recent_changes.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow)

    def test_readiness_and_registry_contract_tests_run_before_generation(self):
        test_step = step_block(
            self.workflow,
            "Run candidate-universe publication tests",
        )
        generation_position = self.workflow.index(
            "Fetch and reconcile exact Wikipedia revision"
        )
        self.assertLess(self.workflow.index(test_step), generation_position)
        for module in (
            "test_fetch_candidate_candidacy_status",
            "test_candidate_candidacy_status",
            "test_candidate_registry_v2",
            "test_candidate_active_monitoring_phase3a1",
            "test_candidate_visibility_history_contract",
            "test_build_candidate_visibility_history",
            "test_publication_manifest_registry_v2",
            "test_candidate_universe_workflow_contract",
            "test_candidate_attention_workflow_contract",
            "test_claims_workflow_contract",
            "test_news_workflow_contract",
            "test_campaign_events_workflow_contract",
            "test_candidate_signals_workflow_contract",
        ):
            self.assertIn(module, test_step)

    def test_success_and_failure_summaries_are_present(self):
        self.assertIn("Write candidate-universe summary", self.workflow)
        self.assertIn("if: success()", self.workflow)
        self.assertIn("Write failure summary", self.workflow)
        self.assertIn("if: failure()", self.workflow)
        for marker in (
            "revision_id",
            "revision_timestamp",
            "semantic_changed",
            "previous_semantic_sha256",
            "candidate_semantic_sha256",
            "candidate_total",
            "active_total",
            "temporarily_missing_total",
            "new_candidates",
            "status_tier_transitions",
            "returned_candidates",
            "renamed_identities",
            "campaign_events_rebuilt",
            "campaign_events_changed",
            "candidate_signals_rebuilt",
            "candidate_visibility_history_rebuilt",
            "manifest_rebuilt",
            "published_commit",
        ):
            self.assertIn(marker, self.workflow)


if __name__ == "__main__":
    unittest.main()
