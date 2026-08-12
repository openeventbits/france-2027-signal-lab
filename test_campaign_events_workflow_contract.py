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

    def test_validation_only_triggers(self):
        self.assertIn("push:", self.text)
        self.assertIn("pull_request:", self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("schedule:", self.text)
        self.assertNotIn("cron:", self.text)

        for path in (
            "campaign_events_manual.json",
            "campaign_event_updates_manual.json",
            "campaign_events.json",
            "publication_manifest.json",
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.text)

        for dependency_path in (
            "campaign_event_*.py",
            "candidate_candidacy_status.py",
            "la_lettre_expansion_adapter.py",
            "rn_agenda_adapter.py",
            "tf1_lci_adapter.py",
        ):
            with self.subTest(dependency_path=dependency_path):
                self.assertEqual(
                    self.text.count(f'- "{dependency_path}"'),
                    2,
                )

    def test_read_only_permissions_and_repository_python(self):
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertNotIn("contents: write", self.text)
        self.assertNotIn("pages: write", self.text)
        self.assertIn("actions/checkout@v7", self.text)
        self.assertIn("actions/setup-python@v6", self.text)
        self.assertIn('python-version: "3.12"', self.text)
        self.assertNotIn("pip install", self.lower)
        self.assertNotIn("requirements", self.lower)

    def test_manual_campaign_events_stack_is_validated(self):
        self.assertIn("python -B -m unittest -v", self.text)

        for module in (
            "test_campaign_event_sources",
            "test_campaign_events_contract",
            "test_campaign_event_institutional_seeds",
            "test_campaign_events_manual",
            "test_campaign_event_updates_manual",
            "test_add_campaign_event",
            "test_update_campaign_event",
            "test_import_campaign_events",
            "test_build_campaign_events",
            "test_publication_manifest",
            "test_campaign_events_workflow_contract",
        ):
            with self.subTest(module=module):
                self.assertRegex(self.text, rf"\b{module}\b")

    def test_authoritative_build_inputs_are_explicit(self):
        self.assertEqual(
            len(re.findall(r"python -B build_campaign_events\.py", self.text)),
            1,
        )

        for argument in (
            "--seeds campaign_event_institutional_seeds.json",
            "--sources campaign_event_sources.json",
            "--candidates candidate_candidacy_status.json",
            "--manual-events campaign_events_manual.json",
            "--event-updates campaign_event_updates_manual.json",
            "--preserve-generated-at-from campaign_events.json",
            "--output /tmp/campaign_events.json",
        ):
            with self.subTest(argument=argument):
                self.assertIn(argument, self.text)

        self.assertIn('--generated-at "2099-01-01T00:00:00Z"', self.text)
        self.assertNotIn("--bootstrap-empty", self.text)

    def test_generated_outputs_are_checked_not_published(self):
        self.assertIn(
            "cmp --silent campaign_events.json /tmp/campaign_events.json",
            self.text,
        )
        self.assertIn(
            "campaign_events.json is not synchronized with its authoritative inputs.",
            self.text,
        )
        self.assertIn("build_publication_manifest.py", self.text)
        self.assertIn("--check", self.text)
        self.assertIn(
            "rebuilt = build_manifest(Path.cwd(), published_at=published_at)",
            self.text,
        )
        self.assertIn("if rebuilt != tracked:", self.text)
        self.assertIn(
            "publication_manifest.json is not synchronized with repository inputs.",
            self.text,
        )
        self.assertIn("git diff --exit-code", self.text)

        self.assertNotIn("atomic_write", self.text)
        self.assertNotIn("github-actions[bot]", self.text)

    def test_workflow_cannot_mutate_repository(self):
        for forbidden in (
            "git add ",
            "git commit",
            "git push",
            "git rebase",
            "git fetch",
            "git reset",
            "git checkout --",
            "git clean",
            "contents: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.lower)

    def test_no_discovery_or_browser_automation(self):
        for forbidden in (
            "playwright",
            "selenium",
            "chromium",
            "test_rn_agenda_adapter",
            "build_rn_agenda_events",
            "fetch_rn_agenda",
            "campaign_event_qomon.py",
            "campaign_event_linked_ics.py",
            "fetch_news_wire.py",
            "fetch_polls.py",
            "fetch_claims_under_scrutiny.py",
            "build_candidate_signals.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.lower)


if __name__ == "__main__":
    unittest.main()
