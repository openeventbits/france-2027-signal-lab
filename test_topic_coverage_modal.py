import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class TopicCoverageModalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = (
            ROOT / "assets" / "hybrid-dashboard.js"
        ).read_text(encoding="utf-8")
        cls.modal_js = (
            ROOT / "assets" / "topic-coverage-modal.js"
        ).read_text(encoding="utf-8")
        cls.modal_css = (
            ROOT / "assets" / "topic-coverage-modal.css"
        ).read_text(encoding="utf-8")
        cls.html = (
            ROOT / "index.html"
        ).read_text(encoding="utf-8")

    def test_assets_load_before_dashboard(self):
        topic_position = self.html.index(
            "assets/topic-coverage-modal.js"
        )
        dashboard_position = self.html.index(
            "assets/hybrid-dashboard.js"
        )
        self.assertLess(
            topic_position,
            dashboard_position,
        )
        self.assertIn(
            "assets/topic-coverage-modal.css",
            self.html,
        )

    def test_dashboard_trigger_keeps_accessible_dialog_contract(self):
        position = self.dashboard.index(
            "Open coverage analysis"
        )
        context = self.dashboard[
            position - 700:position + 120
        ]

        for contract in (
            'type="button"',
            "data-topic-coverage-open",
            'aria-haspopup="dialog"',
            'aria-controls="topic-coverage-modal"',
            'aria-expanded="false"',
        ):
            self.assertIn(contract, context)

    def test_modal_is_a_four_module_terminal(self):
        order = [
            self.modal_js.index('"Coverage shift"'),
            self.modal_js.index('"Topic coverage"'),
            self.modal_js.index('"Top publishers"'),
            self.modal_js.index('"Daily volume"'),
        ]
        self.assertEqual(order, sorted(order))

        for contract in (
            "tcm-intelligence-grid",
            "renderCoverageShiftRows",
            "renderTopicRows",
            "renderPublisherRows",
            "renderDailyVolume",
        ):
            self.assertIn(contract, self.modal_js)

    def test_old_reader_controls_and_article_detail_are_removed(self):
        for forbidden in (
            "Candidate shift</button>",
            "Topic coverage</button>",
            "data-tcm-search",
            "data-tcm-sort",
            "tcm-view-tabs",
            "tcm-toolbar",
            "Supporting coverage",
            "Source-linked coverage",
            "renderCoverageRows",
            "View all publishers",
            "View all topics",
            "See full coverage shift",
            "View volume details",
        ):
            self.assertNotIn(forbidden, self.modal_js)

    def test_complete_model_arrays_feed_scrollable_modules(self):
        for contract in (
            "mediaModel.candidateCoverage",
            "agendaModel.topics",
            "mediaModel.publisherRanking",
            "mediaModel.dailyActivity",
        ):
            self.assertIn(contract, self.modal_js)

        self.assertIn(
            "publisherRanking,",
            self.dashboard,
        )
        self.assertIn(
            "publisherRanking.slice(0, 5);",
            self.dashboard,
        )

    def test_three_lists_scroll_but_daily_volume_fits_without_scrolling(self):
        for contract in (
            'class="tcm-shift-list tcm-scroll-y"',
            'class="tcm-topic-list tcm-scroll-y"',
            'class="tcm-publisher-list tcm-scroll-y"',
            ".tcm-scroll-y",
            "overflow-y: scroll;",
            "scrollbar-width: thin;",
        ):
            self.assertIn(contract, self.modal_js + self.modal_css)

        for contract in (
            'class="tcm-volume-wrap"',
            ".tcm-volume-wrap",
            "grid-template-columns: repeat(14, minmax(0, 1fr));",
            "overflow: hidden;",
        ):
            self.assertIn(contract, self.modal_js + self.modal_css)

        self.assertNotIn("overflow-x: auto;", self.modal_css)
        self.assertNotIn('class="tcm-volume-scroll"', self.modal_js)

        for contract in (
            "scrollbar-gutter: stable;",
            "renderDailyVolumeMeta",
            "formatVolumeDay",
            'class="tcm-volume-wrap"',
        ):
            self.assertIn(contract, self.modal_js + self.modal_css)

    def test_candidate_shift_uses_names_without_rank_column(self):
        shift_start = self.modal_js.index(
            "const renderCoverageShiftRows"
        )
        shift_end = self.modal_js.index(
            "const renderTopicRows",
            shift_start,
        )
        shift_renderer = self.modal_js[shift_start:shift_end]

        self.assertNotIn(
            '<span class="tcm-rank">',
            shift_renderer,
        )
        self.assertIn(
            'title="${escapeAttribute(item.name)}"',
            shift_renderer,
        )

    def test_dialog_matches_compact_mockup_geometry(self):
        self.assertRegex(
            self.modal_css,
            re.compile(
                r"\.tcm-dialog\s*\{[^}]*"
                r"width:\s*min\(800px,\s*"
                r"calc\(100vw - 48px\)\);[^}]*"
                r"height:\s*min\(690px,\s*"
                r"calc\(100dvh - 48px\)\);",
                re.DOTALL,
            ),
        )

        self.assertRegex(
            self.modal_css,
            re.compile(
                r"\.tcm-intelligence-grid\s*\{[^}]*"
                r"grid-template-columns:\s*"
                r"minmax\(0,\s*1fr\)\s*"
                r"minmax\(0,\s*1fr\);[^}]*"
                r"grid-template-rows:\s*"
                r"minmax\(0,\s*1fr\)\s*"
                r"minmax\(0,\s*1fr\);",
                re.DOTALL,
            ),
        )

    def test_modal_keeps_public_api_and_focus_safety(self):
        for contract in (
            "window.France2027TopicCoverageModal",
            "open,",
            "close,",
            "reconcileReturnFocus",
            'event.key === "Escape"',
            'event.key !== "Tab"',
            'aria-modal="true"',
        ):
            self.assertIn(contract, self.modal_js)

    def test_modal_uses_no_fetch_or_external_visual_assets(self):
        combined = (
            self.modal_js + "\n" + self.modal_css
        ).lower()

        for forbidden in (
            "fetch(",
            "<img",
            "<picture",
            "thumbnail",
            "publisher-logo",
            "background-image",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
