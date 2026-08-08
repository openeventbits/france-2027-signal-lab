import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-campaign-events.yml"


class CampaignEventsWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()

    def test_daily_schedule_and_manual_dispatch(self):
        self.assertIn('cron: "29 5 * * *"', self.text)
        self.assertEqual(len(re.findall(r"^\s*- cron:", self.text, re.MULTILINE)), 1)
        self.assertIn("workflow_dispatch:", self.text)

    def test_least_privilege_and_repository_python(self):
        self.assertIn("permissions:\n  contents: write", self.text)
        self.assertNotIn("pages: write", self.text)
        self.assertIn("actions/checkout@v7", self.text)
        self.assertIn("actions/setup-python@v6", self.text)
        self.assertIn('python-version: "3.12"', self.text)

    def test_targeted_validation_and_builders_run(self):
        self.assertIn("python -B -m unittest -v", self.text)
        for module in (
            "test_campaign_event_sources",
            "test_campaign_events_contract",
            "test_campaign_event_institutional_seeds",
            "test_rn_agenda_adapter",
            "test_build_campaign_events",
            "test_publication_manifest",
            "test_campaign_events_workflow_contract",
        ):
            with self.subTest(module=module):
                self.assertRegex(self.text, rf"\b{module}\b")
        self.assertNotIn("pytest", self.lower)
        self.assertNotIn("pip install", self.lower)
        self.assertNotIn("requirements", self.lower)
        self.assertIn("build_campaign_events.py", self.text)
        self.assertIn("validate_campaign_events_artifact", self.text)
        self.assertIn("build_publication_manifest.py", self.text)
        self.assertIn("--check", self.text)

    def test_one_canonical_timestamp_is_exported_and_reused(self):
        timestamp_step_start = self.text.index(
            "- name: Create canonical publication timestamp"
        )
        live_step_start = self.text.index(
            "- name: Validate and atomically publish Campaign Events",
            timestamp_step_start,
        )
        timestamp_step = self.text[timestamp_step_start:live_step_start]
        self.assertIn("id: campaign_timestamp", timestamp_step)
        self.assertEqual(timestamp_step.count("date -u"), 1)
        self.assertIn(
            'echo "value=$timestamp" >> "$GITHUB_OUTPUT"',
            timestamp_step,
        )
        self.assertEqual(self.text.count("date -u"), 1)

        manifest_step_start = self.text.index(
            "- name: Rebuild and validate publication manifest",
            live_step_start,
        )
        live_step = self.text[live_step_start:manifest_step_start]
        canonical_output = "${{ steps.campaign_timestamp.outputs.value }}"
        self.assertIn(
            f'--generated-at "{canonical_output}"',
            live_step,
        )
        self.assertNotIn("date -u", live_step)

        scope_step_start = self.text.index(
            "- name: Verify generated-file scope",
            manifest_step_start,
        )
        manifest_step = self.text[manifest_step_start:scope_step_start]
        self.assertIn(
            f"CAMPAIGN_TIMESTAMP: {canonical_output}",
            manifest_step,
        )
        self.assertIn('published_at="$CAMPAIGN_TIMESTAMP"', manifest_step)
        self.assertIn('published_at="$(python -B -c', manifest_step)
        self.assertIn(
            'open("publication_manifest.json", encoding="utf-8")',
            manifest_step,
        )
        self.assertIn('["published_at"]', manifest_step)
        self.assertNotIn("date -u", manifest_step)

    def test_single_live_acquisition_exact_promotion_and_post_rebase_validation(self):
        builder_calls = list(
            re.finditer(r"python -B build_campaign_events\.py", self.text)
        )
        self.assertEqual(len(builder_calls), 1)
        live_build = builder_calls[0].start()
        temporary_validation = self.text.index(
            'Path("/tmp/campaign_events.json")',
            live_build,
        )
        promotion = self.text.index(
            'atomic_write("campaign_events.json", candidate)',
            temporary_validation,
        )
        promoted_validation = self.text.index(
            "validate_campaign_events_artifact",
            promotion,
        )
        manifest_build = self.text.index(
            "python -B build_publication_manifest.py",
            promoted_validation,
        )
        rebase = self.text.index("git rebase origin/main", manifest_build)
        post_rebase_validation = self.text.index(
            "validate_campaign_events_artifact",
            rebase,
        )
        post_rebase_manifest = self.text.index(
            "python -B build_publication_manifest.py",
            post_rebase_validation,
        )
        self.assertLess(live_build, temporary_validation)
        self.assertLess(temporary_validation, promotion)
        self.assertLess(promotion, promoted_validation)
        self.assertLess(promoted_validation, manifest_build)
        self.assertLess(rebase, post_rebase_validation)
        self.assertLess(post_rebase_validation, post_rebase_manifest)
        self.assertEqual(
            self.text.count("--preserve-generated-at-from campaign_events.json"),
            1,
        )
        self.assertIn(
            'candidate = Path("/tmp/campaign_events.json").read_bytes()',
            self.text,
        )
        self.assertNotIn("--bootstrap-empty", self.text)
        self.assertNotRegex(
            self.lower,
            r"\b(rm|unlink)\b[^\n]*campaign_events\.json",
        )
    def test_generated_scope_and_commit_are_bounded(self):
        self.assertIn(
            "git add -- campaign_events.json publication_manifest.json",
            self.text,
        )
        self.assertIn("git diff --quiet", self.text)
        self.assertIn('if cmp --silent campaign_events.json /tmp/campaign_events.json', self.text)
        self.assertIn('CAMPAIGN_EVENTS_CHANGED" != "true"', self.text)
        self.assertIn('git commit -m "Update campaign events data"', self.text)
        self.assertIn("git push origin HEAD:main", self.text)
        self.assertNotIn("--force", self.text)
        self.assertEqual(
            self.text.count(
                "git add -- campaign_events.json publication_manifest.json"
            ),
            2,
        )
        self.assertNotRegex(
            self.text,
            r"git add --[^\n]*(news|polls|claims|candidate_signals|runoff)",
        )
        self.assertNotIn("git add -A", self.text)
        self.assertNotIn("git add --all", self.text)
        self.assertNotRegex(self.text, r"git add\s+\.\s*(?:\n|$)")

    def test_no_browser_or_unrelated_collector(self):
        for forbidden in (
            "playwright",
            "selenium",
            "chromium",
            "fetch_news_wire.py",
            "fetch_polls.py",
            "fetch_claims_under_scrutiny.py",
            "generate_recent_changes.py",
            "build_candidate_signals.py",
            "build_rn_agenda_events",
            "fetch_rn_agenda",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.lower)


if __name__ == "__main__":
    unittest.main()
