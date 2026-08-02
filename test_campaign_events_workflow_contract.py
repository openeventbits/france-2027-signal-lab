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

    def test_tested_timestamp_preservation_and_promotion_order(self):
        builder_calls = [
            match.start()
            for match in re.finditer(
                r"python -B build_campaign_events\.py",
                self.text,
            )
        ]
        self.assertGreaterEqual(len(builder_calls), 3)
        temporary_build = builder_calls[0]
        temporary_validation = self.text.index(
            'Path("/tmp/campaign_events.json")',
            temporary_build,
        )
        production_build = builder_calls[1]
        manifest_build = self.text.index(
            "python -B build_publication_manifest.py",
            production_build,
        )
        self.assertLess(temporary_build, temporary_validation)
        self.assertLess(temporary_validation, production_build)
        self.assertLess(production_build, manifest_build)
        self.assertGreaterEqual(
            self.text.count("--preserve-generated-at-from campaign_events.json"),
            3,
        )
        self.assertIn("date -u +'%Y-%m-%dT%H:%M:%SZ'", self.text)
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
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.lower)


if __name__ == "__main__":
    unittest.main()
