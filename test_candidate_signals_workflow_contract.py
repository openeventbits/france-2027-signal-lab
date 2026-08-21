import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOWS = {
    "polls": ROOT / ".github/workflows/update-polls.yml",
    "news": ROOT / ".github/workflows/update-news-wire.yml",
    "claims": ROOT / ".github/workflows/update-claims-under-scrutiny.yml",
}
SCHEDULES = {
    "polls": 'cron: "17 */6 * * *"',
    "news": 'cron: "23 * * * *"',
    "claims": 'cron: "47 7,17 * * *"',
}
AUTHORITATIVE_MARKERS = {
    "polls": "current_path.write_bytes(fetched_path.read_bytes())",
    "news": "shutil.copyfile(\n                  TEMP_WIRE,\n                  CURRENT_WIRE,",
    "claims": "atomic_write_json(current_path, fetched)",
}


def step_block(workflow, name):
    marker = f"      - name: {name}"
    start = workflow.index(marker)
    end = workflow.find("\n      - name:", start + len(marker))
    return workflow[start:] if end == -1 else workflow[start:end]


class CandidateSignalsWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            name: path.read_text(encoding="utf-8")
            for name, path in WORKFLOWS.items()
        }

    def test_shared_concurrency_contract_is_unchanged(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertIn(
                    "concurrency:\n"
                    "  group: production-data-update\n"
                    "  cancel-in-progress: false",
                    workflow,
                )

    def test_existing_schedules_are_preserved(self):
        for name, expected_schedule in SCHEDULES.items():
            with self.subTest(workflow=name):
                self.assertIn(expected_schedule, self.workflows[name])

    def test_workflow_publishes_versioned_active_field_artifact(self):
        payload = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["schema_version"], "1.4")
        monitoring = payload["active_monitoring_field"]
        self.assertEqual(
            monitoring["counts"]["active"],
            len(monitoring["main"]) + len(monitoring["secondary"]),
        )

        active = payload["active_field_visibility"]
        self.assertEqual(
            active["method"],
            "share_of_active_candidate_linked_records",
        )
        self.assertEqual(
            active["denominator_scope"],
            "records_linked_to_at_least_one_active_monitoring_candidate",
        )
        self.assertEqual(
            active["status_as_of"],
            payload["presidential_field"]["status_as_of"],
        )
        for scope_name in ("primary", "general"):
            scope = active[scope_name]
            quality = scope["comparison_quality"]
            for prefix, period_name in (
                ("current", "current_period"),
                ("prior", "prior_period"),
            ):
                period = scope[period_name]
                self.assertIsInstance(period["record_count"], int)
                self.assertIsInstance(period["publisher_count"], int)
                self.assertGreaterEqual(period["record_count"], 0)
                self.assertGreaterEqual(period["publisher_count"], 0)
                self.assertEqual(
                    quality[f"{prefix}_record_count"],
                    period["record_count"],
                )
                self.assertEqual(
                    quality[f"{prefix}_publisher_count"],
                    period["publisher_count"],
                )
        for workflow in self.workflows.values():
            candidate = workflow.index("python -B build_candidate_signals.py")
            manifest = workflow.index("python -B build_publication_manifest.py")
            self.assertLess(candidate, manifest)

    def test_candidate_signals_runs_after_authoritative_source_decision(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                authoritative = workflow.index(
                    AUTHORITATIVE_MARKERS[name]
                )
                candidate = workflow.index(
                    "python -B build_candidate_signals.py"
                )
                self.assertLess(authoritative, candidate)

    def test_registry_is_validated_and_required_by_every_rebuild(self):
        validation = (
            "from candidate_candidacy_status import "
            "load_candidate_candidacy_status"
        )
        build = (
            "python -B build_candidate_signals.py "
            "--candidacy-status candidate_candidacy_status.json"
        )
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertGreaterEqual(
                    workflow.count(validation), workflow.count(build)
                )
                self.assertGreaterEqual(workflow.count(build), 2)
                positions = []
                cursor = 0
                while True:
                    candidate = workflow.find(build, cursor)
                    if candidate == -1:
                        break
                    prior_validation = workflow.rfind(validation, 0, candidate)
                    self.assertGreaterEqual(prior_validation, cursor)
                    self.assertLess(prior_validation, candidate)
                    positions.append(candidate)
                    cursor = candidate + len(build)
                self.assertTrue(positions)

    def test_registry_is_never_generated_rewritten_or_staged(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                for line in workflow.splitlines():
                    if "candidate_candidacy_status.json" in line:
                        self.assertNotIn("git add", line)
                        self.assertNotIn(">", line)
                        self.assertNotIn("write", line.lower())
                commit_start = workflow.index("      - name: Commit changed")
                commit_command = workflow.index("git commit", commit_start)
                stage_region = workflow[commit_start:commit_command]
                self.assertNotIn("candidate_candidacy_status.json", stage_region)

    def test_registry_authority_is_explicit_only_for_candidate_aware_collectors(self):
        self.assertNotIn(
            "--candidacy-status candidate_candidacy_status.json",
            step_block(self.workflows["polls"], "Fetch polls into temporary files"),
        )
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            step_block(self.workflows["news"], "Build temporary rolling news outputs"),
        )
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            step_block(
                self.workflows["claims"],
                "Fetch Claims Under Scrutiny into temporary files",
            ),
        )
        for name in ("polls", "claims"):
            recent = step_block(
                self.workflows[name],
                "Regenerate Recent Changes Ledger",
            )
            self.assertNotIn("candidate_candidacy_status", recent)

    def test_candidate_signals_precedes_publication_manifest(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                candidate = workflow.index(
                    "python -B build_candidate_signals.py"
                )
                manifest = workflow.index(
                    "python -B build_publication_manifest.py"
                )
                self.assertLess(candidate, manifest)

    def test_candidate_signals_change_is_independent_and_publishable(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                candidate_step = step_block(
                    workflow,
                    "Rebuild Candidate Signals",
                )
                self.assertIn("id: candidate_signals", candidate_step)
                self.assertIn(
                    "git diff --quiet -- candidate_signals.json",
                    candidate_step,
                )
                self.assertIn(
                    "candidate_signals_changed=true",
                    candidate_step,
                )
                self.assertIn(
                    "candidate_signals_changed=false",
                    candidate_step,
                )
                self.assertIn(
                    "steps.candidate_signals.outputs."
                    "candidate_signals_changed",
                    workflow,
                )
                manifest_step = step_block(
                    workflow,
                    "Rebuild and validate publication manifest",
                )
                self.assertIn("SOURCE_CHANGED", manifest_step)
                self.assertIn(
                    "CANDIDATE_SIGNALS_CHANGED",
                    manifest_step,
                )
                self.assertIn("||", manifest_step)

    def test_exact_data_staging_includes_derived_outputs(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                commit_start = workflow.index(
                    "      - name: Commit changed"
                )
                stage_start = workflow.index(
                    "git add --",
                    commit_start,
                )
                commit_command = workflow.index(
                    "git commit",
                    stage_start,
                )
                stage_block = workflow[stage_start:commit_command]
                self.assertIn("candidate_signals.json", stage_block)
                self.assertIn("publication_manifest.json", stage_block)

    def test_recent_changes_does_not_publish_candidate_signals(self):
        for name in ("polls", "claims"):
            with self.subTest(workflow=name):
                recent_step = step_block(
                    self.workflows[name],
                    "Regenerate Recent Changes Ledger",
                )
                self.assertNotIn("candidate_signals", recent_step)

    def test_candidate_step_has_no_network_collector_commands(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                candidate_step = step_block(
                    workflow,
                    "Rebuild Candidate Signals",
                )
                self.assertNotIn("fetch_", candidate_step)
                self.assertNotIn("curl ", candidate_step)
                self.assertNotIn(
                    "generate_recent_changes.py",
                    candidate_step,
                )

    def test_every_workflow_has_final_clean_prepush_rebuild(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                final_candidate = workflow.rindex(
                    "python -B build_candidate_signals.py"
                )
                final_manifest = workflow.rindex(
                    "python -B build_publication_manifest.py"
                )
                final_clean = workflow.rindex(
                    "git diff --exit-code --"
                )
                push = workflow.rindex("git push ")
                self.assertLess(final_candidate, final_manifest)
                self.assertLess(final_manifest, final_clean)
                self.assertLess(final_clean, push)
                final_block = workflow[final_candidate:push]
                self.assertIn("candidate_signals.json", final_block)
                self.assertIn("publication_manifest.json", final_block)

    def test_news_and_claims_rebuild_and_amend_after_rebase_only_if_needed(self):
        for name in ("news", "claims"):
            workflow = self.workflows[name]
            with self.subTest(workflow=name):
                rebase = workflow.index("git rebase ")
                push = workflow.index("git push ", rebase)
                post_rebase = workflow[rebase:push]
                candidate = post_rebase.index(
                    "python -B build_candidate_signals.py"
                )
                manifest = post_rebase.index(
                    "python -B build_publication_manifest.py"
                )
                conditional = post_rebase.index(
                    "if ! git diff --quiet --"
                )
                stage = post_rebase.index("git add --", conditional)
                amend = post_rebase.index(
                    "git commit --amend --no-edit",
                    stage,
                )
                condition_end = post_rebase.index(
                    "          fi",
                    amend,
                )
                final_candidate = post_rebase.rindex(
                    "python -B build_candidate_signals.py"
                )
                final_clean = post_rebase.rindex(
                    "git diff --exit-code --"
                )
                self.assertLess(candidate, manifest)
                self.assertLess(manifest, conditional)
                self.assertLess(conditional, stage)
                self.assertLess(stage, amend)
                self.assertLess(amend, condition_end)
                self.assertLess(condition_end, final_candidate)
                self.assertLess(final_candidate, final_clean)
                amend_block = post_rebase[conditional:condition_end]
                self.assertIn("candidate_signals.json", amend_block)
                self.assertIn("publication_manifest.json", amend_block)

    def test_polls_does_not_add_a_rebase_strategy(self):
        self.assertNotIn("git rebase", self.workflows["polls"])


if __name__ == "__main__":
    unittest.main()
