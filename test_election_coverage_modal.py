import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ElectionCoverageModalTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = (
            ROOT
            / "assets"
            / "hybrid-dashboard.js"
        ).read_text(encoding="utf-8")

        cls.modal_js = (
            ROOT
            / "assets"
            / "election-coverage-modal.js"
        ).read_text(encoding="utf-8")

        cls.modal_css = (
            ROOT
            / "assets"
            / "election-coverage-modal.css"
        ).read_text(encoding="utf-8")

        cls.html = (
            ROOT
            / "index.html"
        ).read_text(encoding="utf-8")

    def css_rule(self, selector):
        match = re.search(
            re.escape(selector)
            + r"\s*\{(?P<body>[^}]*)\}",
            self.modal_css,
            re.DOTALL,
        )

        self.assertIsNotNone(
            match,
            f"Missing CSS rule for {selector}",
        )

        return match.group("body")

    def test_assets_load_before_dashboard(self):
        modal_position = self.html.index(
            "assets/election-coverage-modal.js"
        )

        dashboard_position = self.html.index(
            "assets/hybrid-dashboard.js"
        )

        self.assertLess(
            modal_position,
            dashboard_position,
        )

        self.assertIn(
            "assets/election-coverage-modal.css",
            self.html,
        )

    def test_trigger_is_truthful_modal_button(self):
        position = self.dashboard.index(
            "Browse recent coverage"
        )

        context = self.dashboard[
            position - 450:
            position + 120
        ]

        for contract in (
            'type="button"',
            "data-election-coverage-open",
            'aria-haspopup="dialog"',
            'aria-controls="election-coverage-modal"',
            'aria-expanded="false"',
        ):
            self.assertIn(contract, context)

        self.assertNotIn(
            'href="',
            context,
        )

        self.assertNotIn(
            "View all coverage",
            self.dashboard,
        )

    def test_existing_model_binding_remains(self):
        for contract in (
            "function bindElectionCoverageModal(",
            ".open(model, button)",
            "bindElectionCoverageModal(model)",
        ):
            self.assertIn(
                contract,
                self.dashboard,
            )

    def test_component_keeps_public_api(self):
        for contract in (
            "window.France2027ElectionCoverageModal",
            "open,",
            "close",
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

    def test_feed_fields_are_truthful(self):
        for field in (
            "item?.published_at",
            "item?.publisher",
            "item?.headline",
            "item?.url",
            "item?.candidate_names",
        ):
            self.assertIn(
                field,
                self.modal_js,
            )

        self.assertNotIn(
            "fetch(",
            self.modal_js,
        )

    def test_search_and_filters_exist(self):
        for contract in (
            "data-ecm-search",
            "data-ecm-publisher",
            "data-ecm-candidate",
            "data-ecm-sort",
            "All publishers",
            "All candidates",
            "Newest first",
            "Oldest first",
            "hasCandidateFilter",
            "without-candidate-filter",
            'aria-live="polite"',
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        self.assertNotIn(
            "No candidate metadata",
            self.modal_js,
        )
    def test_filtering_is_client_side(self):
        for contract in (
            "normalizeSearch",
            "filteredRecords",
            "record.searchText.includes(query)",
            "record.publisher !== state.publisher",
            "!record.candidates.includes(",
            'state.sort === "oldest"',
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        for forbidden in (
            "XMLHttpRequest",
            "axios",
            "import ",
            "require(",
        ):
            self.assertNotIn(
                forbidden,
                self.modal_js,
            )

    def test_empty_state_and_result_summary(self):
        self.assertIn(
            "No matching coverage",
            self.modal_js,
        )

        for contract in (
            "hasActiveCoverageFilters",
            "`All ${records.length}`",
            "`Showing ${count} of ${records.length}`",
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        self.assertIn(
            "data-ecm-result-summary",
            self.modal_js,
        )

    def test_coverage_feed_is_integrated_and_measured(self):
        self.assertNotIn(
            'class="ecm-coverage-summary"',
            self.modal_js,
        )

        for contract in (
            'class="ecm-feed-meta"',
            "Coverage window ·",
            'class="ecm-feed-results"',
            'title="${escapeAttribute(',
            "list.scrollTop = 0;",
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        readable_css = self.modal_css.split(
            "/* FR27 SHARED READABLE TYPOGRAPHY "
            "— COVERAGE MODAL — 2026-07 */",
            1,
        )[1]

        for contract in (
            "32px minmax(0, 1fr);",
            "48px minmax(0, 1fr);",
            "height: 60px;",
            "min-height: 60px;",
            "82px",
            "132px",
            "92px",
            "scrollbar-gutter: stable;",
            ".ecm-feed-list::-webkit-scrollbar-button",
            "opacity: .38;",
        ):
            self.assertIn(
                contract,
                readable_css,
            )

    def test_modal_uses_single_coverage_view(self):
        for contract in (
            'class="ecm-tab-panel ecm-coverage-panel"',
            'aria-label="Election coverage"',
            'class="ecm-feed-meta"',
            "renderToolbar()",
            "updateFeed()",
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        for removed in (
            "Coverage Intelligence",
            'role="tablist"',
            'role="tab"',
            "data-ecm-tab",
            "ecm-intelligence-panel",
            "renderIntelligence",
            "setActiveTab",
        ):
            self.assertNotIn(
                removed,
                self.modal_js,
            )

        terminal_marker = (
            "/* FR27 TABBED COVERAGE TERMINAL "
            "— 2026-07 */"
        )
        readable_marker = (
            "/* FR27 SHARED READABLE TYPOGRAPHY "
            "— COVERAGE MODAL — 2026-07 */"
        )
        terminal_css = (
            self.modal_css
            .split(terminal_marker, 1)[1]
            .split(readable_marker, 1)[0]
        )

        shell_start = terminal_css.index(
            ".ecm-shell {"
        )
        shell_end = terminal_css.index(
            "}",
            shell_start,
        )
        shell_rule = terminal_css[
            shell_start:shell_end + 1
        ]

        self.assertIn(
            "minmax(0, 1fr) 24px;",
            shell_rule,
        )

    def test_removed_old_dashboard_structures(self):
        for forbidden in (
            "ecm-stats",
            "ecm-overview",
            'class="ecm-card ecm-topics"',
            "ecm-status",
            "renderMetric",
            "renderCoverageOverview",
            "renderTopics",
        ):
            self.assertNotIn(
                forbidden,
                self.modal_js,
            )

        self.assertNotIn(
            "MANUAL MEDIA MODAL POLISH",
            self.modal_css,
        )

    def test_source_links_are_safe(self):
        for contract in (
            '["http:", "https:"]',
            'target="_blank"',
            'rel="noopener noreferrer"',
            "escapeHtml",
            "escapeAttribute",
            "safeUrl(record.url)",
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

        self.assertIn(
            "Source unavailable",
            self.modal_js,
        )

    def test_accessibility_and_focus_contract(self):
        for contract in (
            'role="dialog"',
            'aria-modal="true"',
            'aria-labelledby="ecm-title"',
            'aria-describedby="ecm-subtitle"',
            'event.key === "Escape"',
            "focusableElements",
            "returnFocus",
            "target.focus()",
            '"aria-expanded",',
        ):
            self.assertIn(
                contract,
                self.modal_js,
            )

    def test_desktop_feed_is_primary_scroller(self):
        feed = self.css_rule(
            ".ecm-feed-list"
        )

        body = self.css_rule(
            ".ecm-body"
        )

        workspace = self.css_rule(
            ".ecm-workspace"
        )

        self.assertIn(
            "overflow-y: auto;",
            feed,
        )

        self.assertIn(
            "overflow: hidden;",
            body,
        )

        self.assertIn(
            "overflow: hidden;",
            workspace,
        )

    def test_dialog_is_bounded(self):
        dialog = self.css_rule(
            ".ecm-dialog"
        )

        self.assertIn(
            "min(1080px, calc(100vw - 48px))",
            dialog,
        )

        self.assertIn(
            "min(720px, calc(100dvh - 48px))",
            dialog,
        )

        self.assertIn(
            "overflow: hidden;",
            dialog,
        )

    def test_mobile_uses_one_scroll_region(self):
        mobile = self.modal_css[
            self.modal_css.index(
                "@media (max-width: 768px)"
            ):
            self.modal_css.index(
                "@media (max-width: 430px)"
            )
        ]

        self.assertRegex(
            mobile,
            re.compile(
                r"\.ecm-body\s*\{[^}]*"
                r"overflow-y:\s*auto;",
                re.DOTALL,
            ),
        )

        self.assertRegex(
            mobile,
            re.compile(
                r"\.ecm-feed-list\s*\{[^}]*"
                r"overflow:\s*visible;",
                re.DOTALL,
            ),
        )

        self.assertIn(
            "flex-direction: column;",
            mobile,
        )

    def test_key_typography_is_readable(self):
        """Readability is checked against the final active override."""

        marker = (
            "/* FR27 SHARED READABLE TYPOGRAPHY "
            "— COVERAGE MODAL — 2026-07 */"
        )

        self.assertEqual(
            self.modal_css.count(marker),
            1,
        )

        readable_css = self.modal_css.split(
            marker,
            1,
        )[1]

        required_rules = (
            "font-size: 12.5px;",
            "font-size: 10.5px;",
            "font-size: 10px;",
            "font-size: 9px;",
            "font-size: 18px;",
        )

        for rule in required_rules:
            self.assertIn(
                rule,
                readable_css,
            )

        forbidden_reading_sizes = (
            "font-size: 6px;",
            "font-size: 6.5px;",
            "font-size: 6.8px;",
            "font-size: 7px;",
            "font-size: 7.5px;",
            "font-size: 8px;",
        )

        for rule in forbidden_reading_sizes:
            self.assertNotIn(
                rule,
                readable_css,
            )

    def test_no_article_images_or_external_assets(self):
        combined = (
            self.modal_js
            + "\n"
            + self.modal_css
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
            self.assertNotIn(
                forbidden,
                combined,
            )


    def test_terminal_block_is_single_scoped_and_readable(self):
        """The approved tabbed terminal and readability blocks are unique."""

        terminal_marker = (
            "/* FR27 TABBED COVERAGE TERMINAL "
            "— 2026-07 */"
        )

        readable_marker = (
            "/* FR27 SHARED READABLE TYPOGRAPHY "
            "— COVERAGE MODAL — 2026-07 */"
        )

        self.assertEqual(
            self.modal_css.count(terminal_marker),
            1,
        )

        self.assertEqual(
            self.modal_css.count(readable_marker),
            1,
        )

        self.assertLess(
            self.modal_css.index(terminal_marker),
            self.modal_css.index(readable_marker),
        )

        terminal_css = (
            self.modal_css
            .split(terminal_marker, 1)[1]
            .split(readable_marker, 1)[0]
        )

        self.assertIn(
            "min(780px, calc(100vw - 48px))",
            terminal_css,
        )

        self.assertIn(
            ".ecm-tabs",
            terminal_css,
        )

        self.assertIn(
            ".ecm-intelligence-grid",
            terminal_css,
        )

        self.assertIn(
            ".ecm-feed-list",
            terminal_css,
        )
