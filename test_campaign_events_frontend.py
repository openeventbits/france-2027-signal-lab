import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
DASHBOARD = ROOT / "assets" / "hybrid-dashboard.js"
CSS = ROOT / "assets" / "hybrid-dashboard.css"
ARTIFACT = ROOT / "campaign_events.json"


class CampaignEventsFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text(encoding="utf-8")
        cls.dashboard = DASHBOARD.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")
        cls.artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_public_artifact_has_frontend_lanes(self):
        self.assertEqual(self.artifact["schema_version"], "1.1")
        self.assertIsInstance(self.artifact["campaign_events"], list)
        self.assertIsInstance(self.artifact["institutional_milestones"], list)
        self.assertIsInstance(self.artifact["event_watch"], list)

    def test_event_watch_references_campaign_events(self):
        event_ids = {
            event["event_id"]
            for event in self.artifact["campaign_events"]
        }
        self.assertTrue(event_ids)
        for update in self.artifact["event_watch"]:
            self.assertIn(update["event_id"], event_ids)

    def test_campaign_events_uses_central_dashboard_state(self):
        self.assertIn("campaignEvents: null", self.index)
        self.assertIn('campaignEvents: "loading"', self.index)
        self.assertIn(
            'markDataset(\n            "campaignEvents",\n            "loaded"',
            self.index,
        )
        self.assertIn('markDataset("campaignEvents", "error")', self.index)

    def test_public_artifact_is_fetched_once_outside_hybrid_renderer(self):
        needle = 'fetch("campaign_events.json", { cache: "no-store" })'
        self.assertEqual(self.index.count(needle), 1)
        self.assertNotIn('fetch("campaign_events.json"', self.dashboard)
        self.assertIn("loadCampaignEvents();", self.index)

    def test_frontend_validator_preserves_locked_public_contract(self):
        validator_start = self.index.index(
            "function validateCampaignEventsPayload("
        )
        loader_start = self.index.index(
            "function loadCampaignEvents(",
            validator_start,
        )
        validator = self.index[validator_start:loader_start]
        for value in (
            '"1.1"',
            '"scheduled"',
            '"postponed"',
            '"cancelled"',
            '"completed"',
            '"NEW"',
            '"CONFIRMED"',
            '"UPDATED"',
            '"POSTPONED"',
            '"CANCELLED"',
            "institutional_milestones",
            "event_watch",
        ):
            with self.subTest(value=value):
                self.assertIn(value, validator)

    def test_events_view_model_and_operations_console_are_wired(self):
        self.assertIn("function buildEventsViewModel()", self.dashboard)
        self.assertIn(
            'viewModelState("campaignEvents")',
            self.dashboard,
        )
        self.assertIn(
            'events: safelyBuildViewModel("events", buildEventsViewModel)',
            self.dashboard,
        )
        self.assertIn(
            "${renderEventsPanel(models.events)}",
            self.dashboard,
        )
        for heading in (
            "Campaign Events operations console",
            "12-WEEK SCHEDULE",
            "UPCOMING",
            "EVENT DOSSIER",
            "SOURCE EVIDENCE",
            "SCHEDULE HISTORY",
            "SCHEDULE WATCH",
            "LATEST CHANGES",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.dashboard)

        self.assertIn("campaignEventTypeFilter", self.dashboard)
        self.assertIn('button[data-hybrid-event-id]', self.dashboard)
        self.assertIn('button[data-hybrid-week-select]', self.dashboard)
        self.assertIn('button[data-hybrid-events-filter]', self.dashboard)
        self.assertIn("selectedUpdates", self.dashboard)
        self.assertIn("eventWatch", self.dashboard)
        self.assertIn("hybrid-events-upcoming-row", self.dashboard)
        self.assertIn("hybrid-events-upcoming-week", self.dashboard)
        self.assertIn("hybrid-events-ops-marker", self.dashboard)
        self.assertIn("hybrid-events-schedule-watch-item", self.dashboard)
        self.assertIn("EVENT DETAILS", self.dashboard)
        self.assertIn("PARTICIPANTS", self.dashboard)
        for forbidden in (
            "ELECTION ANCHORS",
            "PARTICIPATION MATRIX",
            "CHANGE FEED",
            "EVENT PULSE",
            "12-WEEK EVENT STRIP",
            "NEXT SIGNALS",
            "EVENT MONITOR",
            "SCHEDULE HORIZON",
            "SELECTED WEEK",
            "CAMPAIGN SCHEDULE",
            "EVENT CALENDAR",
            "EVENT STREAM",
            "12-WEEK HORIZON",
            "NOT INVITED",
            "LIKELY",
            "TENTATIVE",
            "Reliability HIGH",
            "CALENDAR UPDATES",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.dashboard)


    def test_past_scheduled_events_are_not_silently_completed(self):
        self.assertIn("past_unconfirmed", self.dashboard)
        self.assertIn("PAST · UNCONFIRMED", self.dashboard)
        self.assertIn(
            "Past scheduled rows are not treated as completed",
            self.dashboard,
        )

    def test_renderer_does_not_surface_opaque_identifiers(self):
        renderer_start = self.dashboard.index(
            "function campaignEventTypeLabel("
        )
        renderer_end = self.dashboard.index(
            "function filteredClaimReviews(",
            renderer_start,
        )
        renderer = self.dashboard[renderer_start:renderer_end]
        for label in ("event_key", "update_key", "source_id"):
            with self.subTest(label=label):
                self.assertNotIn(label, renderer)

    def test_events_css_is_scoped_and_responsive(self):
        self.assertIn(
            "/* CAMPAIGN EVENTS WORKSPACE V1 */",
            self.css,
        )
        self.assertIn(".hybrid-events-workspace", self.css)
        self.assertIn("@media (max-width: 1100px)", self.css)
        self.assertIn("@media (max-width: 760px)", self.css)
        events_marker = self.css.index("/* CAMPAIGN EVENTS WORKSPACE V1 */")
        runoff_marker = self.css.index("/* RUNOFF WORKSPACE REDESIGN V1")
        self.assertLess(events_marker, runoff_marker)
        events_css = self.css[events_marker:runoff_marker]
        for selector in (
            ".hybrid-events-workspace",
            ".hybrid-events-ops-rail",
            ".hybrid-events-upcoming",
            ".hybrid-events-dossier",
            ".hybrid-events-schedule-watch",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, events_css)

    def test_events_typography_uses_audited_readability_floor(self):
        events_marker = self.css.index("/* CAMPAIGN EVENTS WORKSPACE V1 */")
        runoff_marker = self.css.index("/* RUNOFF WORKSPACE REDESIGN V1", events_marker)
        events_css = self.css[events_marker:runoff_marker]
        for token in (
            "--hybrid-events-panel-title: 13px",
            "--hybrid-events-primary: 12.5px",
            "--hybrid-events-body: 10.5px",
            "--hybrid-events-meta-size: 9.5px",
            "--hybrid-events-micro: 8.5px",
        ):
            with self.subTest(token=token):
                self.assertIn(token, events_css)
        explicit_sizes = [
            float(value)
            for value in re.findall(r"font-size:\s*([0-9.]+)px", events_css)
        ]
        self.assertTrue(explicit_sizes)
        self.assertGreaterEqual(min(explicit_sizes), 8.5)

    def test_hybrid_javascript_syntax(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for frontend syntax checks")
        subprocess.run(
            [node, "--check", str(DASHBOARD)],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_inline_dashboard_javascript_syntax(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for frontend syntax checks")

        scripts = re.findall(
            r"<script>(.*?)</script>",
            self.index,
            flags=re.DOTALL,
        )
        self.assertTrue(scripts)
        source = max(scripts, key=len)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            encoding="utf-8",
            delete=False,
        ) as handle:
            handle.write(source)
            path = Path(handle.name)

        try:
            subprocess.run(
                [node, "--check", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
