import json
import re
import subprocess
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
            self.modal_js.index("coverageShiftTitle(),"),
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

    def test_race_coverage_terminology_is_mode_aware(self):
        self.assertIn(
            "raceCoverageMode =",
            self.modal_js,
        )
        self.assertIn(
            "mediaModel.raceCoverageMode === true",
            self.modal_js,
        )

        for current_label in (
            "Race-attention share",
            "Race Coverage shift",
            "Race Attention candidate comparison unavailable.",
            "Daily accepted France 2027 race coverage",
            "Comparable Race Attention percentage-point change.",
        ):
            self.assertIn(
                current_label,
                self.modal_js,
            )

        for legacy_label in (
            "Active-field candidate-linked share",
            "Active-field coverage shift",
            "Active-field candidate comparison unavailable.",
            "Daily accepted election coverage",
            "Comparable active-field percentage-point change.",
        ):
            self.assertIn(
                legacy_label,
                self.modal_js,
            )

        self.assertIn(
            "coverageShiftTitle(),",
            self.modal_js,
        )
        self.assertIn(
            "candidateShareLabel().toLowerCase()",
            self.modal_js,
        )
        self.assertIn(
            "dailyCoverageAriaLabel()",
            self.modal_js,
        )

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

    def test_candidate_module_honors_active_tiers_and_raw_differences(self):
        open_block = self.modal_js[
            self.modal_js.index("  const open = ("):
            self.modal_js.index(
                "  window.France2027TopicCoverageModal"
            )
        ]

        renderer = self.modal_js[
            self.modal_js.index(
                "const renderCoverageShiftRows"
            ):
            self.modal_js.index(
                "const renderTopicRows"
            )
        ]

        legend_start = self.modal_js.index(
            "const candidateShareLabel"
        )
        legend_end = self.modal_js.index(
            "const renderCoverageShiftRows",
            legend_start,
        )
        legend_source = self.modal_js[
            legend_start:legend_end
        ]

        render_body = self.modal_js[
            self.modal_js.index(
                "const renderBody ="
            ):
            self.modal_js.index(
                "const focusableElements"
            )
        ]

        for contract in (
            "mediaModel.candidateCoverage.map(normalizeCandidate)",
            'mediaModel.comparisonQuality?.status === "comparable"',
            'renderGroup("main", "MAIN FIELD")',
            'renderGroup("secondary", "SECONDARY FIELD")',
            'const candidateComparisonLabel',
            '"RAW Δ pp"',
            '"publisher panel changed"',
            "Raw arithmetic differences are current-minus-prior",
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        self.assertEqual(
            self.modal_js.count('"RAW Δ pp"'),
            1,
        )

        self.assertIn(
            "candidateComparisonLabel(),",
            render_body,
        )
        self.assertNotIn(
            "Active candidate-linked share",
            self.modal_js,
        )

        self.assertIn(
            "const rawDeltaAvailable",
            renderer,
        )
        self.assertIn(
            "item.latestShare - item.previousShare",
            renderer,
        )
        self.assertIn(
            "deltaArrow(displayedDelta)",
            renderer,
        )
        self.assertIn(
            "formatDelta(displayedDelta)",
            renderer,
        )
        self.assertIn(
            "deltaClass(displayedDelta)",
            renderer,
        )

        self.assertIn(
            'class="tcm-shift-row${displayedDelta === null ? " is-limited" : ""}${highlighted}"',
            renderer,
        )
        self.assertNotIn(
            'class="tcm-shift-row${item.changeAvailable ? "" : " is-limited"}',
            renderer,
        )

        self.assertIn(
            'class="tcm-delta ${displayedDelta === null ? "is-limited" : deltaClass(displayedDelta)}"',
            renderer,
        )

        self.assertIn(
            "Raw arithmetic difference ${deltaMarkup}",
            renderer,
        )
        self.assertNotIn(
            "Not comparable",
            renderer,
        )

        self.assertIn(
            'class="tcm-shift-track"',
            renderer,
        )
        self.assertIn(
            '<strong title="${escapeAttribute(item.name)}">${escapeHtml(item.name)}</strong>',
            renderer,
        )
        self.assertNotIn(
            "hybrid-status-chip",
            renderer,
        )
        self.assertNotIn(
            "item.tierLabel",
            renderer,
        )
        self.assertIn(
            "mediaModel.candidateCoverage",
            open_block,
        )
        self.assertNotIn(
            "mediaModel.activeFieldVisibility",
            open_block,
        )
        self.assertNotIn(
            "current_record_count",
            self.modal_js,
        )
        self.assertNotIn(
            "prior_record_count",
            self.modal_js,
        )
        self.assertNotIn(
            "current_exposure_count",
            self.modal_js,
        )
        self.assertNotIn(
            "prior_exposure_count",
            self.modal_js,
        )
        self.assertNotIn(
            "candidate_watch",
            open_block,
        )

        script = r"""
let candidateProjectionAvailable = true;
let candidateComparisonAvailable = false;
let candidateComparisonReason =
  "publisher_panel_changed";
let raceCoverageMode = false;
let latestPeriodLabel = "25–31 Jul";
let priorPeriodLabel = "18–24 Jul";
const escapeHtml = value => String(value);
const escapeAttribute = escapeHtml;
""" + legend_source + r"""
const invalid = renderPeriodLegend();

candidateComparisonAvailable = true;
candidateComparisonReason = "comparable";
const comparable = renderPeriodLegend();

raceCoverageMode = true;
const raceComparable = renderPeriodLegend();

process.stdout.write(
  JSON.stringify({
    invalid,
    comparable,
    raceComparable
  })
);
"""

        completed = subprocess.run(
            ["node", "-"],
            input=script,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        rendered = json.loads(
            completed.stdout
        )

        self.assertNotIn(
            "RAW Δ pp",
            rendered["invalid"],
        )
        self.assertNotIn(
            "data-tcm-candidate-comparison-quality",
            rendered["invalid"],
        )
        self.assertIn(
            "publisher panel changed",
            rendered["invalid"],
        )
        self.assertIn(
            "Raw arithmetic differences are current-minus-prior",
            rendered["invalid"],
        )
        self.assertIn(
            "Comparable active-field percentage-point change.",
            rendered["comparable"],
        )
        self.assertIn(
            "Active-field candidate-linked share.",
            rendered["comparable"],
        )

        self.assertIn(
            "Comparable Race Attention percentage-point change.",
            rendered["raceComparable"],
        )
        self.assertIn(
            "Race-attention share.",
            rendered["raceComparable"],
        )
        self.assertNotIn(
            "Active-field candidate-linked share.",
            rendered["raceComparable"],
        )

    def test_candidate_projection_fallback_is_module_scoped(self):
        renderer = self.modal_js[
            self.modal_js.index("const renderCoverageShiftRows"):
            self.modal_js.index("const renderTopicRows")
        ]
        self.assertIn("candidateProjectionAvailable", renderer)
        self.assertIn(
            "candidateComparisonUnavailableLabel()",
            renderer,
        )
        self.assertIn("const renderTopicRows", self.modal_js)
        self.assertIn("const renderPublisherRows", self.modal_js)
        self.assertIn("const renderDailyVolume", self.modal_js)

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
