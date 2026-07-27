from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent


class CoverageAnalysisModalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(
            encoding="utf-8"
        )
        cls.dashboard = (
            ROOT / "assets" / "hybrid-dashboard.js"
        ).read_text(encoding="utf-8")
        cls.modal_js = (
            ROOT / "assets" / "topic-coverage-modal.js"
        ).read_text(encoding="utf-8")
        cls.modal_css = (
            ROOT / "assets" / "topic-coverage-modal.css"
        ).read_text(encoding="utf-8")

    def css_rule(self, selector):
        match = re.search(
            re.escape(selector) + r"\s*\{(?P<body>[^}]*)\}",
            self.modal_css,
            re.DOTALL,
        )
        self.assertIsNotNone(match, selector)
        return match.group("body")

    def test_assets_load_before_dashboard(self):
        modal_position = self.html.index(
            "assets/topic-coverage-modal.js"
        )
        dashboard_position = self.html.index(
            "assets/hybrid-dashboard.js"
        )
        self.assertLess(modal_position, dashboard_position)
        self.assertIn(
            "assets/topic-coverage-modal.css",
            self.html,
        )

    def test_modal_is_combined_coverage_analysis(self):
        for contract in (
            "Media Pulse / Coverage Analysis",
            'data-tcm-view="candidates"',
            'data-tcm-view="topics"',
            "Candidate shift",
            "Topic coverage",
        ):
            self.assertIn(contract, self.modal_js)

    def test_placeholder_and_redundant_controls_are_removed(self):
        for forbidden in (
            "Topic definition unavailable",
            "With supporting coverage",
            "All specific topics",
            "30-day window",
            "Source-day recurrence, not raw article volume",
            "Agenda activity is not public priority",
            "tcm-disclosure",
        ):
            self.assertNotIn(forbidden, self.modal_js)

    def test_candidate_data_is_backed_by_source_records(self):
        for contract in (
            "candidateCoverage",
            "latestItems",
            "previousItems",
            "latestCount",
            "previousCount",
            "latestShare",
            "previousShare",
            "changePp",
            "Source-linked coverage",
        ):
            self.assertIn(contract, self.modal_js)

    def test_topic_data_uses_real_supporting_items(self):
        for contract in (
            "supporting_items",
            "supportingItems",
            "Supporting coverage",
            "source-linked items",
        ):
            self.assertIn(contract, self.modal_js)

    def test_source_links_are_safe_and_open_separately(self):
        for contract in (
            '["http:", "https:"]',
            'target="_blank"',
            'rel="noopener noreferrer"',
            "Source unavailable",
        ):
            self.assertIn(contract, self.modal_js)

    def test_search_and_sort_change_with_active_view(self):
        for contract in (
            "candidates or coverage",
            "topics or coverage",
            "Sort: current share",
            "Sort: change",
            "Sort: current articles",
            "Sort: source-days",
            "Sort: publishers",
            "Sort: accepted items",
        ):
            self.assertIn(contract, self.modal_js)

    def test_top_panel_candidate_rows_open_dialog(self):
        for contract in (
            "data-hybrid-media-candidate",
            'aria-controls="topic-coverage-modal"',
            'aria-haspopup="dialog"',
            'aria-expanded="false"',
            "Open coverage analysis →",
        ):
            self.assertIn(contract, self.dashboard)

    def test_candidate_aliases_are_canonicalized_and_deduplicated(self):
        for contract in (
            "function buildMediaCandidateCanonicalizer",
            "canonicalizeCandidate",
            "suffixMatches",
            "candidateCoverage:",
            "new Map()",
        ):
            self.assertIn(contract, self.dashboard)

    def test_modal_binding_receives_media_and_agenda_models(self):
        for contract in (
            "function bindTopicCoverageModal(",
            "mediaModel,",
            "agendaModel",
            "initialView",
            "candidateName",
            "topicId",
            "bindTopicCoverageModal(model, agendaModel);",
        ):
            self.assertIn(contract, self.dashboard)

    def test_accessibility_and_focus_contract(self):
        for contract in (
            'role="dialog"',
            'aria-modal="true"',
            'aria-labelledby="tcm-title"',
            'event.key === "Escape"',
            "focusableElements",
            "returnFocus",
            '"aria-expanded", "true"',
            '"aria-expanded", "false"',
            "target.focus()",
        ):
            self.assertIn(contract, self.modal_js)

    def test_dialog_is_bounded_and_scrollable(self):
        dialog = self.css_rule(".tcm-dialog")
        workspace = self.css_rule(".tcm-workspace")
        self.assertIn(
            "min(1120px, calc(100vw - 48px))",
            dialog,
        )
        self.assertIn(
            "min(760px, calc(100dvh - 48px))",
            dialog,
        )
        self.assertIn("overflow: hidden;", dialog)
        self.assertIn("overflow: hidden;", workspace)
        self.assertRegex(
            self.modal_css,
            re.compile(
                r"\.tcm-ranking-list,\s*"
                r"\.tcm-detail\s*\{[^}]*"
                r"overflow-y:\s*auto;",
                re.DOTALL,
            ),
        )

    def test_mobile_uses_single_page_scroll_region(self):
        mobile = self.modal_css[
            self.modal_css.index("@media (max-width: 768px)"):
            self.modal_css.index("@media (max-width: 520px)")
        ]
        self.assertRegex(
            mobile,
            re.compile(
                r"\.tcm-body\s*\{[^}]*overflow-y:\s*auto;",
                re.DOTALL,
            ),
        )
        self.assertIn("display: block;", mobile)
        self.assertRegex(
            mobile,
            re.compile(
                r"\.tcm-ranking-list,\s*"
                r"\.tcm-detail,\s*"
                r"\.tcm-supporting-list\s*\{[^}]*"
                r"overflow:\s*visible;",
                re.DOTALL,
            ),
        )

    def test_no_article_images_or_external_visual_assets(self):
        combined = (
            self.modal_js + "\n" + self.modal_css
        ).lower()
        for forbidden in (
            "<img",
            "<picture",
            "thumbnail",
            "publisher-logo",
            "publisher_logo",
            "favicon",
            "background-image",
        ):
            self.assertNotIn(forbidden, combined)


    def test_empty_datasets_still_open_honest_empty_state(self):
        self.assertNotIn(
            "if (!candidates.length && !topics.length) return;",
            self.modal_js,
        )
        open_start = self.modal_js.index("  const open = (")
        open_end = self.modal_js.index(
            "window.France2027TopicCoverageModal",
            open_start,
        )
        open_contract = self.modal_js[open_start:open_end]
        self.assertLess(
            open_contract.index("ensureModal();"),
            open_contract.index("renderShell();"),
        )
        self.assertIn("modal.hidden = false;", open_contract)
        self.assertIn("No matching candidates", self.modal_js)
        self.assertIn("No matching topics", self.modal_js)

    def test_news_rerender_reconciles_focus_to_live_trigger(self):
        for contract in (
            "const reconcileReturnFocus = () => {",
            "document.contains(returnFocus)",
            "data-topic-coverage-open",
            "data-hybrid-media-topic",
            "data-hybrid-media-candidate",
            'returnFocus.setAttribute("aria-expanded", "true")',
            "reconcileReturnFocus();",
        ):
            self.assertIn(contract, self.modal_js)

        self.assertIn(
            "?.reconcileReturnFocus?.();",
            self.dashboard,
        )

    def test_terminal_block_is_single_scoped_and_readable(self):
        marker = (
            "FR27 TERMINAL MODAL SYSTEM — COVERAGE ANALYSIS"
        )
        self.assertEqual(self.modal_css.count(marker), 1)
        terminal = self.modal_css[
            self.modal_css.index(marker):
        ]

        for selector in (
            ".tcm-ranking-head strong",
            ".tcm-support-row h5",
            ".tcm-support-row p",
            ".tcm-support-copy",
        ):
            self.assertNotIn(selector, terminal)

        self.assertIn(".tcm-ranking-head > span", terminal)
        self.assertIn(".tcm-supporting-head > span", terminal)

        sizes = [
            float(value)
            for value in re.findall(
                r"font-size:\s*([0-9.]+)px",
                self.modal_css,
            )
        ]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 9)

        self.assertNotRegex(
            terminal,
            re.compile(r"(?m)^\s*(button|a|h2|\*)\s*\{"),
        )
        self.assertNotIn("!important", terminal)

    def test_terminal_block_reuses_existing_breakpoints(self):
        marker = (
            "FR27 TERMINAL MODAL SYSTEM — COVERAGE ANALYSIS"
        )
        pre_terminal, terminal = self.modal_css.split(marker, 1)
        breakpoint_pattern = r"@media \(max-width:\s*([0-9]+px)\)"
        existing = set(re.findall(breakpoint_pattern, pre_terminal))
        repeated = set(re.findall(breakpoint_pattern, terminal))
        self.assertTrue(repeated)
        self.assertTrue(repeated.issubset(existing))



    def test_compact_candidate_panel_suppresses_unavailable_numeric_delta(self):
        start = self.dashboard.index(
            "function renderTopMediaPulsePanel("
        )
        end = self.dashboard.index(
            "function renderTopMediaPulse(",
            start,
        )
        renderer = self.dashboard[start:end]
        self.assertIn(
            ': "Comparison unavailable";',
            renderer,
        )
        self.assertIn(
            '${direction ? `${direction} ` : ""}',
            renderer,
        )
        self.assertIn(
            "const deltaAvailable = item.changeAvailable === true;",
            renderer,
        )

    def test_candidate_modal_uses_one_shared_quality_warning(self):
        self.assertEqual(
            self.modal_js.count(
                "Comparison unavailable — publisher panel changed"
            ),
            1,
        )
        self.assertEqual(
            self.modal_js.count(
                "Comparison unavailable — insufficient prior evidence"
            ),
            1,
        )
        self.assertEqual(
            self.modal_js.count(
                "comparisonQualityMessage(comparisonQuality)"
            ),
            1,
        )
        self.assertIn(
            'candidate.changeAvailable ? "percentage points" : ""',
            self.modal_js,
        )
        self.assertNotIn(
            "formatDelta(candidate.changePp)",
            self.modal_js,
        )

    def test_candidate_share_label_is_truthful(self):
        self.assertIn(
            "Share of candidate-linked records",
            self.modal_js,
        )
        for forbidden in (
            "market share",
            "media share",
            "share of all election coverage",
            "exclusive share",
        ):
            self.assertNotIn(forbidden, self.modal_js.lower())


if __name__ == "__main__":
    unittest.main()
