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
            "function renderTopMediaPulsePanel(model)",
            self.js,
        )
        self.assertIn(
            "renderTopMediaPulsePanel(model)",
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


    def test_top_media_typography_is_one_step_below_neighbors(self):
        headline_start = self.html.index(
            ".top-media-coverage-headline"
        )
        headline_end = self.html.index(
            ".top-media-source-link",
            headline_start,
        )
        headline_css = self.html[
            headline_start:headline_end
        ]

        shift_start = self.html.index(
            ".top-media-shift-name"
        )
        shift_end = self.html.index(
            ".top-media-shift-row > strong",
            shift_start,
        )
        shift_css = self.html[
            shift_start:shift_end
        ]

        metadata_start = self.html.index(
            ".top-media-coverage-meta time"
        )
        metadata_end = self.html.index(
            ".top-media-coverage-meta strong",
            metadata_start,
        )
        metadata_css = self.html[
            metadata_start:metadata_end
        ]

        self.assertIn(
            "font-size: 10px;",
            headline_css,
        )
        self.assertIn(
            "font-size: 9px;",
            shift_css,
        )
        self.assertIn(
            "font-size: 8px;",
            metadata_css,
        )


    def test_top_media_renderer_limits_coverage_and_forbids_images(self):
        start = self.js.index(
            "function renderTopMediaPulsePanel("
        )
        end = self.js.index(
            "function renderTopMediaPulse(",
            start,
        )
        renderer = self.js[start:end]

        self.assertIn(
            ".slice(0, 5)",
            renderer,
        )
        self.assertIn(
            'class="top-media-coverage-row"',
            renderer,
        )
        self.assertIn(
            "Open source",
            renderer,
        )
        self.assertNotIn(
            "<img",
            renderer,
        )
        self.assertNotIn(
            "thumbnail",
            renderer.lower(),
        )
        self.assertNotIn(
            "portrait",
            renderer.lower(),
        )

    def test_top_media_header_contains_four_prominent_metrics(self):
        start = self.js.index(
            "function renderTopMediaPulse(model)"
        )
        end = self.js.index(
            "function bindPollCompareShortcut",
            start,
        )
        renderer = self.js[start:end]

        for label in (
            'label: "accepted news"',
            'label: "publishers"',
            'label: "recent (14d)"',
            'label: "candidate-watch"',
        ):
            self.assertIn(
                label,
                renderer,
            )

        self.assertIn(
            'class="top-media-header-metric"',
            renderer,
        )

    def test_media_model_derives_ranked_top_publishers(self):
        start = self.js.index(
            "function buildMediaViewModel()"
        )
        end = self.js.index(
            "function buildAgendaViewModel()",
            start,
        )
        model = self.js[start:end]

        self.assertIn(
            "const publisherCounts =",
            model,
        )
        self.assertIn(
            "const topPublishers =",
            model,
        )
        self.assertIn(
            ".slice(0, 5);",
            model,
        )
        self.assertIn(
            "topPublishers,",
            model,
        )

    def test_top_media_contains_mockup_sections(self):
        start = self.js.index(
            "function renderTopMediaPulsePanel("
        )
        end = self.js.index(
            "function renderTopMediaPulse(",
            start,
        )
        renderer = self.js[start:end]

        for label in (
            "Latest election coverage",
            "Coverage shift",
            "Topic coverage",
            "Top publishers",
        ):
            self.assertIn(
                label,
                renderer,
            )


if __name__ == "__main__":
    unittest.main()
