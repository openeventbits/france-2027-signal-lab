import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent

WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "update-candidate-attention.yml"
)


class CandidateAttentionWorkflowContractTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(
            encoding="utf-8"
        )
        cls.lower = cls.workflow.lower()

    def test_daily_schedule_and_manual_dispatch(self):
        self.assertEqual(
            self.workflow.count(
                'cron: "3 9 * * *"'
            ),
            1,
        )
        self.assertIn(
            "workflow_dispatch:",
            self.workflow,
        )

    def test_least_privilege_and_shared_lock(self):
        self.assertIn(
            "permissions:\n  contents: write",
            self.workflow,
        )
        self.assertNotIn(
            "pages: write",
            self.workflow,
        )
        self.assertIn(
            "group: production-data-update",
            self.workflow,
        )
        self.assertIn(
            "cancel-in-progress: false",
            self.workflow,
        )
        self.assertIn(
            "actions/checkout@v7",
            self.workflow,
        )
        self.assertIn(
            "actions/setup-python@v6",
            self.workflow,
        )
        self.assertIn(
            'python-version: "3.12"',
            self.workflow,
        )
        self.assertIn(
            "ref: main",
            self.workflow,
        )
        self.assertIn(
            "fetch-depth: 0",
            self.workflow,
        )

    def test_preferred_observation_date_is_yesterday(self):
        self.assertEqual(
            self.workflow.count(
                "date -u -d 'yesterday' +'%Y-%m-%d'"
            ),
            1,
        )
        self.assertIn(
            "/tmp/preferred_data_as_of",
            self.workflow,
        )
        self.assertEqual(
            self.workflow.count(
                '--end-date "$PREFERRED_DATA_AS_OF"'
            ),
            1,
        )

    def test_only_initial_build_enables_three_day_fallback(self):
        self.assertEqual(
            self.workflow.count("--fallback-days 3"),
            1,
        )
        self.assertEqual(
            self.workflow.count("--fallback-days"),
            1,
        )
        self.assertNotIn(
            "--fallback-days 1",
            self.workflow,
        )

        initial_build = self.workflow.index(
            "python -B build_candidate_attention.py"
        )
        fallback = self.workflow.index(
            "--fallback-days 3"
        )
        second_build = self.workflow.index(
            "python -B build_candidate_attention.py",
            initial_build + 1,
        )

        self.assertLess(initial_build, fallback)
        self.assertLess(fallback, second_build)

    def test_resolved_date_is_captured_and_bounded(self):
        self.assertIn(
            "resolved_data_as_of = candidate[",
            self.workflow,
        )
        self.assertIn(
            "preferred_date = date.fromisoformat(",
            self.workflow,
        )
        self.assertIn(
            "earliest_allowed_data_as_of = (",
            self.workflow,
        )
        self.assertIn(
            "- timedelta(days=3)",
            self.workflow,
        )
        self.assertIn(
            "resolved_date = date.fromisoformat(",
            self.workflow,
        )
        self.assertIn(
            "earliest_allowed_data_as_of\n"
            "              <= resolved_date\n"
            "              <= preferred_date",
            self.workflow,
        )
        self.assertNotIn(
            "previous_data_as_of",
            self.workflow,
        )
        self.assertNotIn(
            "resolved_data_as_of not in {",
            self.workflow,
        )
        self.assertIn(
            'f"resolved_data_as_of={resolved_data_as_of}\\n"',
            self.workflow,
        )
        self.assertIn(
            'Path("/tmp/resolved_data_as_of").write_text(',
            self.workflow,
        )

    def test_rebase_and_final_validation_use_resolved_date(self):
        self.assertEqual(
            self.workflow.count(
                '--end-date "$RESOLVED_DATA_AS_OF"'
            ),
            1,
        )
        self.assertIn(
            "RESOLVED_DATA_AS_OF: "
            "${{ steps.candidate_attention.outputs."
            "resolved_data_as_of }}",
            self.workflow,
        )
        self.assertIn(
            'resolved_data_as_of = os.environ[\n'
            '              "RESOLVED_DATA_AS_OF"',
            self.workflow,
        )
        self.assertIn(
            'resolved_data_as_of = Path(\n'
            '              "/tmp/resolved_data_as_of"',
            self.workflow,
        )
        self.assertGreaterEqual(
            self.workflow.count(
                '!= resolved_data_as_of'
            ),
            3,
        )

    def test_builds_only_to_temporary_paths(self):
        self.assertIn(
            "--output /tmp/candidate_attention.json",
            self.workflow,
        )
        self.assertIn(
            "--output /tmp/candidate_attention-rebase.json",
            self.workflow,
        )
        self.assertNotIn(
            "--output candidate_attention.json",
            self.workflow,
        )

        builder_calls = re.findall(
            r"python -B build_candidate_attention\.py",
            self.workflow,
        )

        self.assertEqual(
            len(builder_calls),
            2,
        )

    def test_semantic_comparison_uses_locked_stage2_helper(self):
        self.assertEqual(
            self.workflow.count(
                "serialize_semantic_payload(candidate)"
            ),
            2,
        )
        self.assertEqual(
            self.workflow.count(
                "serialize_semantic_payload(existing)"
            ),
            2,
        )
        self.assertNotIn(
            'pop("generated_at"',
            self.workflow,
        )
        self.assertNotIn(
            "del candidate",
            self.workflow,
        )

    def test_registry_input_and_schema_aware_active_parity_are_explicit(self):
        self.assertEqual(
            self.workflow.count(
                "--candidacy-status candidate_candidacy_status.json"
            ),
            2,
        )
        self.assertGreaterEqual(
            self.workflow.count("active_candidate_records(candidacy)"),
            5,
        )
        self.assertGreaterEqual(
            self.workflow.count('schema_version"] == "1.0"'),
            5,
        )
        self.assertIn("test_candidate_attention_registry_v2", self.workflow)
        self.assertEqual(
            self.workflow.count(
                "validate_candidate_attention(\n"
                "              existing\n"
                "          )"
            ),
            2,
        )

    def test_atomic_promotion_is_used_initially_and_after_rebase(self):
        self.assertEqual(
            self.workflow.count(
                "atomic_write_bytes("
            ),
            2,
        )
        self.assertGreaterEqual(
            self.workflow.count(
                '"candidate_attention.json"'
            ),
            8,
        )

    def test_manifest_rebuild_and_no_churn_are_explicit(self):
        self.assertGreaterEqual(
            self.workflow.count(
                "build_publication_manifest.py"
            ),
            5,
        )
        self.assertGreaterEqual(
            self.workflow.count(
                "--check"
            ),
            3,
        )
        self.assertIn(
            "CANDIDATE_ATTENTION_CHANGED:",
            self.workflow,
        )
        self.assertIn(
            "PUBLICATION_MANIFEST_CHANGED:",
            self.workflow,
        )
        self.assertIn(
            'manifest["schema_version"] != "1.3"',
            self.workflow,
        )

    def test_complete_generated_scope_is_guarded(self):
        self.assertGreaterEqual(
            self.workflow.count(
                "--porcelain=v1"
            ),
            4,
        )
        self.assertGreaterEqual(
            self.workflow.count(
                "--untracked-files=all"
            ),
            4,
        )
        self.assertGreaterEqual(
            self.workflow.count(
                '"candidate_attention.json",'
            ),
            5,
        )
        self.assertGreaterEqual(
            self.workflow.count(
                '"publication_manifest.json",'
            ),
            4,
        )
        self.assertRegex(
            self.workflow,
            (
                r'"git",\s*'
                r'"diff-tree",\s*'
                r'"--no-commit-id",\s*'
                r'"--name-only",\s*'
                r'"-r",\s*'
                r'"HEAD"'
            ),
        )

    def test_commit_rebase_rebuild_amend_push_order(self):
        first_build = self.workflow.index(
            "python -B build_candidate_attention.py"
        )

        commit = self.workflow.index(
            'git commit \\\n'
            '            -m "Update candidate attention data"'
        )

        fetch = self.workflow.index(
            "git fetch origin main",
            commit,
        )

        rebase = self.workflow.index(
            "git rebase origin/main",
            fetch,
        )

        second_build = self.workflow.index(
            "python -B build_candidate_attention.py",
            first_build + 1,
        )

        amend = self.workflow.index(
            "git commit --amend --no-edit",
            rebase,
        )

        push = self.workflow.index(
            "git push origin HEAD:main",
            amend,
        )

        self.assertLess(
            first_build,
            commit,
        )
        self.assertLess(
            commit,
            fetch,
        )
        self.assertLess(
            fetch,
            rebase,
        )
        self.assertLess(
            rebase,
            second_build,
        )
        self.assertLess(
            second_build,
            amend,
        )
        self.assertLess(
            amend,
            push,
        )

        self.assertNotIn(
            "--force",
            self.workflow,
        )

    def test_exact_publication_files_are_staged(self):
        self.assertIn(
            "git add -- \\\n"
            "            candidate_attention.json \\\n"
            "            publication_manifest.json",
            self.workflow,
        )

    def test_no_unrelated_work_or_extra_permissions(self):
        for forbidden in (
            "pip install",
            "playwright",
            "selenium",
            "chromium",
            "fetch_news_wire.py",
            "fetch_polls.py",
            "fetch_claims_under_scrutiny.py",
            "generate_recent_changes.py",
            "build_candidate_signals.py",
            "build_campaign_events.py",
            "pages build",
            "pages-build-deployment",
        ):
            with self.subTest(
                forbidden=forbidden
            ):
                self.assertNotIn(
                    forbidden,
                    self.lower,
                )


if __name__ == "__main__":
    unittest.main()
