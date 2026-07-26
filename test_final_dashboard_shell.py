from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
HYBRID_JS = ROOT / "assets" / "hybrid-dashboard.js"


class FinalDashboardShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.js = HYBRID_JS.read_text(encoding="utf-8")

    def test_top_row_contains_three_primary_panels(self):
        changed = self.html.index(
            'class="panel what-changed"'
        )
        race = self.html.index(
            'class="panel race-glance"'
        )
        media = self.html.index(
            'class="panel top-media-pulse"'
        )
        context = self.html.index(
            'class="context-strip"'
        )

        self.assertLess(changed, race)
        self.assertLess(race, media)
        self.assertLess(media, context)

    def test_top_media_mount_uses_existing_media_model(self):
        self.assertIn(
            'id="top-media-pulse-content"',
            self.html,
        )
        self.assertIn(
            "function renderTopMediaPulse(model)",
            self.js,
        )
        self.assertIn(
            "renderMediaPanel(model)",
            self.js,
        )
        self.assertIn(
            "renderTopMediaPulse(models.media);",
            self.js,
        )

    def test_summary_cards_are_removed_from_primary_render(self):
        start = self.js.index(
            "function renderAll()"
        )
        end = self.js.index(
            "function handleSignalHashChange",
            start,
        )
        renderer = self.js[start:end]

        self.assertIn(
            "renderFocusWorkspace(models)",
            renderer,
        )
        self.assertNotIn(
            "renderSummaryGrid(models)",
            renderer,
        )
        self.assertNotIn(
            "Four summaries",
            renderer,
        )

    def test_media_topic_navigation_supports_top_mount(self):
        self.assertIn(
            "function bindMediaTopicLinks(root = mount)",
            self.js,
        )
        self.assertIn(
            "bindMediaTopicLinks(topMediaMount);",
            self.js,
        )

    def test_module_navigation_includes_poll_compare(self):
        self.assertIn(
            "data-hybrid-poll-compare",
            self.js,
        )
        self.assertIn(
            ">POLL COMPARE</button>",
            self.js,
        )
        self.assertIn(
            '"polling-evidence-lab"',
            self.js,
        )

    def test_three_column_and_five_module_layout_are_locked(self):
        self.assertIn(
            "/* FINAL DASHBOARD V2 SHELL */",
            self.html,
        )
        self.assertIn(
            "max-width: 1780px;",
            self.html,
        )
        self.assertIn(
            "minmax(470px, .98fr)",
            self.html,
        )
        self.assertIn(
            "minmax(560px, 1.24fr);",
            self.html,
        )
        self.assertIn(
            "minmax(250px, 1.08fr);",
            self.html,
        )
        self.assertIn(
            "repeat(5, minmax(0, 1fr));",
            self.html,
        )


if __name__ == "__main__":
    unittest.main()
