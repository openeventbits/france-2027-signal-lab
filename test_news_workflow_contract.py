import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-news-wire.yml"


class NewsWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_hourly_schedule_and_explicit_registry(self):
        self.assertIn('cron: "23 * * * *"', self.text)
        self.assertIn("workflow_dispatch:", self.text)
        fetch_start = self.text.index("python fetch_news_wire.py")
        fetch_end = self.text.index("python generate_recent_changes.py", fetch_start)
        fetch = self.text[fetch_start:fetch_end]
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            fetch,
        )
        self.assertIn("--polls polls.json", fetch)

    def test_post_rebase_reconciles_recent_changes_before_derived_outputs(self):
        rebase = 'git rebase "origin/$target_branch"'
        self.assertIn(rebase, self.text)

        post_rebase = self.text[self.text.index(rebase):]

        recent_changes = post_rebase.index(
            "python generate_recent_changes.py"
        )
        candidate_signals = post_rebase.index(
            "python -B build_candidate_signals.py"
        )
        history = post_rebase.index(
            "python -B build_candidate_visibility_history.py"
        )
        manifest = post_rebase.index(
            "python -B build_publication_manifest.py"
        )

        self.assertLess(
            recent_changes,
            candidate_signals,
        )
        self.assertLess(
            candidate_signals,
            history,
        )
        self.assertLess(
            history,
            manifest,
        )

        reconciliation = post_rebase[
            recent_changes:
        ]

        for required in (
            "--news news_wire.json",
            "--polls polls.json",
            "--runoff closest_tested_runoff.json",
            "--second-round second_round_polls.json",
            "--claims claims_under_scrutiny.json",
            "--output recent_changes.json",
        ):
            self.assertIn(
                required,
                reconciliation,
            )

        self.assertIn(
            "recent_changes.json candidate_signals.json candidate_visibility_history.json publication_manifest.json",
            reconciliation,
        )

        final_validation = reconciliation[
            reconciliation.index(
                "final_published_at="
            ):
        ]

        self.assertIn(
            "git diff --exit-code --",
            final_validation,
        )
        self.assertIn(
            "recent_changes.json candidate_signals.json candidate_visibility_history.json publication_manifest.json",
            final_validation,
        )


    def test_history_is_built_from_temporary_wire_before_promotion(self):
        build = self.text.index(
            "python -B build_candidate_visibility_history.py"
        )
        promotion = self.text.index(
            "- name: Validate and promote generated data"
        )

        self.assertLess(
            build,
            promotion,
        )

        temporary_build = self.text[
            build:promotion
        ]

        self.assertIn(
            "--news /tmp/news_wire.json",
            temporary_build,
        )
        self.assertIn(
            "--candidacy-status candidate_candidacy_status.json",
            temporary_build,
        )
        self.assertIn(
            "--output /tmp/candidate_visibility_history.json",
            temporary_build,
        )

        promotion_text = self.text[
            promotion:
        ]

        self.assertIn(
            "validate_candidate_visibility_history(",
            promotion_text,
        )
        self.assertIn(
            "current_history != history",
            promotion_text,
        )
        self.assertIn(
            "TEMP_HISTORY",
            promotion_text,
        )
        self.assertIn(
            "CURRENT_HISTORY",
            promotion_text,
        )


    def test_history_is_committed_with_news_derived_outputs(self):
        commit = self.text[
            self.text.index(
                "- name: Commit changed rolling news data"
            ):
        ]

        self.assertIn(
            "candidate_visibility_history.json",
            commit,
        )
        self.assertIn(
            "python -B build_candidate_visibility_history.py",
            commit,
        )


    def test_registry_is_not_published_by_news(self):
        commit = self.text[self.text.index("git add --"):]
        for line in commit.splitlines():
            if "git add" in line:
                self.assertNotIn("candidate_candidacy_status.json", line)


if __name__ == "__main__":
    unittest.main()
