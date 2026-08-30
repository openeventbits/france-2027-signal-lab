import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
UI_JS = (ROOT / "assets" / "fr27-ui.js").read_text(encoding="utf-8")
UI_CSS = (ROOT / "assets" / "fr27-ui.css").read_text(encoding="utf-8")
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
HYBRID_CSS = (ROOT / "assets" / "hybrid-dashboard.css").read_text(
    encoding="utf-8"
)
CANDIDATES = (ROOT / "assets" / "candidate-signals-workspace.js").read_text(
    encoding="utf-8"
)
ELECTION_MODAL = (ROOT / "assets" / "election-coverage-modal.js").read_text(
    encoding="utf-8"
)
TOPIC_MODAL = (ROOT / "assets" / "topic-coverage-modal.js").read_text(
    encoding="utf-8"
)
TOOLTIP_SOURCES = [INDEX, HYBRID, CANDIDATES, ELECTION_MODAL, TOPIC_MODAL]


class UnifiedTooltipContractTests(unittest.TestCase):
    def test_frontend_does_not_emit_native_explanatory_titles(self):
        for source in TOOLTIP_SOURCES:
            self.assertIsNone(re.search(r"\s+title\s*=\s*[\"']", source))
            self.assertNotIn('setAttribute("title"', source)
            self.assertNotRegex(source, r'wikipediaSvgElement\(\s*["\']title["\']')

    def test_literal_tooltip_triggers_are_not_hidden_or_focus_contradictions(self):
        for source in TOOLTIP_SOURCES:
            for tag in re.findall(r"<[^>]+>", source):
                if "data-fr27-tooltip" not in tag:
                    continue
                self.assertNotIn('aria-hidden="true"', tag)
                self.assertFalse(
                    'tabindex="0"' in tag and 'aria-hidden="true"' in tag
                )

        chart_start = CANDIDATES.index("function wikipediaAttentionLineChart")
        marker_start = CANDIDATES.index(
            'const marker = wikipediaSvgElement(', chart_start
        )
        marker_block = CANDIDATES[
            marker_start : CANDIDATES.index('svg.append(marker);', marker_start)
        ]
        self.assertIn(
            'marker.setAttribute("aria-label", tooltip)',
            marker_block,
        )
        self.assertIn(
            'marker.setAttribute("data-fr27-tooltip", tooltip)',
            marker_block,
        )
        self.assertNotIn(
            'marker.setAttribute("aria-hidden", "true")',
            marker_block,
        )
        self.assertNotIn(
            'marker.setAttribute("tabindex"',
            marker_block,
        )

    def test_known_explanatory_terms_have_deliberate_focus_triggers(self):
        for target_id in ("context-poll-meta", "masthead-countdown"):
            tag = re.search(
                rf'<[^>]+id="{target_id}"[^>]+>', INDEX, re.S
            )
            self.assertIsNotNone(tag)
            self.assertIn("data-fr27-tooltip", tag.group(0))
            self.assertIn('tabindex="0"', tag.group(0))

        self.assertRegex(
            INDEX,
            r'class="runoff-evidence-label"[^>]+data-fr27-tooltip[^>]+tabindex="0"',
        )
        explanatory_helper = CANDIDATES[
            CANDIDATES.index("function explanatoryMetadata") :
            CANDIDATES.index("function hasValue")
        ]
        self.assertIn('setAttribute("data-fr27-tooltip"', explanatory_helper)
        self.assertIn('setAttribute("tabindex", "0")', explanatory_helper)
        for label in (
            "Agenda methodology",
            "Policy Issues methodology",
            "Schedule methodology",
            "Event evidence methodology",
        ):
            self.assertRegex(
                HYBRID,
                rf'<button[^>]+aria-label="{re.escape(label)}"[^>]+data-fr27-tooltip',
            )

    def test_semantic_metadata_avoids_repeated_passive_tooltips(self):
        helper = CANDIDATES[
            CANDIDATES.index("function semanticMetadata") :
            CANDIDATES.index("function explanatoryMetadata")
        ]
        self.assertIn('setAttribute("aria-label"', helper)
        self.assertNotIn("data-fr27-tooltip", helper)
        self.assertNotIn("tabindex", helper)

        self.assertNotIn('class="track"\n              aria-hidden="true"\n              data-fr27-tooltip', INDEX)
        self.assertNotIn("icon.dataset.fr27Tooltip", INDEX)
        self.assertNotRegex(
            HYBRID,
            r'class="hybrid-agenda-v6-publisher-icon"[^>]+data-fr27-tooltip',
        )
        self.assertNotRegex(
            HYBRID,
            r'data-agenda-(?:day-cell|activity-day)="true"[^>]+data-fr27-tooltip',
        )
        self.assertNotIn("data-fr27-tooltip", ELECTION_MODAL)
        self.assertNotIn("data-fr27-tooltip", TOPIC_MODAL)

    def test_info_glyph_font_size_is_at_least_ten_pixels(self):
        rules = [
            re.search(r"\.fr27-info-glyph\s*\{(?P<body>.*?)\n\}", UI_CSS, re.S),
            re.search(
                r"\.hybrid-agenda-v6-info\s*\{(?P<body>.*?)\n\}",
                HYBRID_CSS,
                re.S,
            ),
        ]
        for rule in rules:
            self.assertIsNotNone(rule)
            size = re.search(r"font-size:\s*([0-9.]+)px", rule.group("body"))
            self.assertIsNotNone(size)
            self.assertGreaterEqual(float(size.group(1)), 10.0)

    def test_shared_tooltip_visual_and_interaction_contract(self):
        tooltip_rule = re.search(r"\.fr27-tooltip\s*\{(?P<body>.*?)\n\}", UI_CSS, re.S)
        self.assertIsNotNone(tooltip_rule)
        tooltip_body = tooltip_rule.group("body")
        size = re.search(r"font-size:\s*([0-9.]+)px", tooltip_rule.group("body"))
        self.assertIsNotNone(size)
        self.assertGreaterEqual(float(size.group(1)), 10.0)
        for surface in (
            "background: #061623",
            "border: 1px solid rgba(53, 216, 255, 0.42)",
            "border-radius: 4px",
            "box-shadow: 0 10px 28px rgba(0, 0, 0, 0.46)",
        ):
            self.assertIn(surface, tooltip_body)
        for required in (
            "max-width: min(320px, calc(100vw - 20px))",
            "background: #061623",
            "role\", \"tooltip",
            'aria-describedby',
            'document.addEventListener("pointerover"',
            'document.addEventListener("focusin"',
            'event.pointerType === "touch"',
            "window.innerWidth - tooltipRect.width - viewportGap",
        ):
            self.assertIn(required, UI_CSS + UI_JS)

    def test_countdown_freshness_tooltip_gets_extra_right_edge_inset(self):
        self.assertIn('trigger.id === "masthead-countdown" ? 24 : 0', UI_JS)
        self.assertIn('window.innerWidth - tooltipRect.width - viewportGap - rightEdgeInset', UI_JS)

    def test_passive_tooltip_surface_has_no_workspace_override(self):
        local_styles = [
            HYBRID_CSS,
            (ROOT / "assets" / "final-dashboard-shell.css").read_text(
                encoding="utf-8"
            ),
            (ROOT / "assets" / "candidate-signals.css").read_text(
                encoding="utf-8"
            ),
            (ROOT / "assets" / "election-coverage-modal.css").read_text(
                encoding="utf-8"
            ),
            (ROOT / "assets" / "topic-coverage-modal.css").read_text(
                encoding="utf-8"
            ),
        ]
        for stylesheet in local_styles:
            self.assertNotIn(".fr27-tooltip", stylesheet)
            self.assertNotIn("fr27-shared-tooltip", stylesheet)

    def test_interactive_popovers_remain_popovers(self):
        self.assertIn('id="fr27-hud-contact-popover"', INDEX)
        self.assertIn('id="fr27-hud-info-popover"', INDEX)
        self.assertIn('aria-haspopup="dialog"', INDEX)
        self.assertIn("candidate-signals-scrutiny-popover", HYBRID)


class LoadingSkeletonContractTests(unittest.TestCase):
    def test_shared_structural_patterns_and_reduced_motion_exist(self):
        for pattern in ("briefing", "race", "media", "events"):
            self.assertIn(f'pattern === "{pattern}"', UI_JS)
        self.assertIn('["workspace", "candidates"].includes(pattern)', UI_JS)
        self.assertIn('["agenda", "issues", "runoff"].includes(pattern)', UI_JS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", UI_CSS)
        self.assertIn("animation: none", UI_CSS)
        self.assertIn('aria-hidden="true"', UI_JS)

    def test_initial_hud_does_not_expose_stale_fallback_metrics(self):
        hud_slice = INDEX[INDEX.index('id="fr27-hud-news-value"') : INDEX.index("<!-- UTILITY -->")]
        for stale in (">941<", ">90<", ">510<", ">1342<"):
            self.assertNotIn(stale, hud_slice)
        self.assertEqual(hud_slice.count("fr27-hud-metric-loading"), 4)
        self.assertIn('classList.remove("fr27-hud-metric-loading")', INDEX)

    def test_initial_primary_regions_use_structural_skeletons(self):
        for required in (
            "fr27-skeleton-briefing",
            "fr27-skeleton-race",
            "fr27-skeleton-media",
            "fr27-skeleton-workspace",
            'skeletonElement("candidates"',
            'skeletonElement(\n          "runoff"',
            'skeletonElement(\n          "events"',
            'skeletonElement(\n          "agenda"',
            'skeletonElement(\n          "issues"',
        ):
            self.assertIn(required, INDEX + HYBRID + CANDIDATES)
        for crude in (
            "Preparing the Signal Board…",
            "Loading Media Pulse…",
            "Loading candidate scores…",
        ):
            self.assertNotIn(crude, INDEX)


if __name__ == "__main__":
    unittest.main()
