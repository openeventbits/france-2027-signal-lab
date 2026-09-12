"""Analytics foundation contracts for FR27."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
ENGLISH_INDEX = (ROOT / "en" / "index.html").read_text(encoding="utf-8")
ANALYTICS = (ROOT / "assets" / "fr27-analytics.js").read_text(encoding="utf-8")
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
CANDIDATES = (
    ROOT / "assets" / "candidate-signals-workspace.js"
).read_text(encoding="utf-8")


class AnalyticsFoundationTests(unittest.TestCase):
    def test_both_language_entrypoints_load_single_adapter(self):
        tag = '<script src="assets/fr27-analytics.js"></script>'

        self.assertEqual(INDEX.count(tag), 1)
        self.assertEqual(ENGLISH_INDEX.count(tag), 1)

    def test_posthog_is_eu_and_production_only(self):
        self.assertIn(
            'const PRODUCTION_HOST = "france2027.app";',
            ANALYTICS,
        )
        self.assertIn(
            'const API_HOST = "https://eu.i.posthog.com";',
            ANALYTICS,
        )
        self.assertIn(
            "window.location.hostname === PRODUCTION_HOST",
            ANALYTICS,
        )
        self.assertNotIn(
            "app.posthog.com",
            ANALYTICS,
        )
        self.assertNotIn(
            "us.i.posthog.com",
            ANALYTICS,
        )

    def test_posthog_capture_configuration_is_deliberate(self):
        required = (
            'person_profiles: "identified_only"',
            'persistence: "localStorage+cookie"',
            "autocapture: false",
            "disable_session_recording: true",
            "capture_pageview: true",
            "capture_pageleave: true",
        )

        for contract in required:
            with self.subTest(contract=contract):
                self.assertIn(contract, ANALYTICS)

    def test_consent_is_explicit_and_persistent(self):
        self.assertIn(
            'const CONSENT_KEY = "fr27_analytics_consent";',
            ANALYTICS,
        )
        self.assertIn(
            'value === "granted"',
            ANALYTICS,
        )
        self.assertIn(
            'value === "denied"',
            ANALYTICS,
        )
        self.assertIn(
            'return "unknown";',
            ANALYTICS,
        )
        self.assertIn(
            'readConsent() !== "granted"',
            ANALYTICS,
        )
        self.assertIn(
            "window.posthog.opt_in_capturing()",
            ANALYTICS,
        )
        self.assertIn(
            "window.posthog.opt_out_capturing()",
            ANALYTICS,
        )
        self.assertRegex(
            ANALYTICS,
            r'button\.id\s*=\s*"fr27-analytics-settings";',
        )
        self.assertIn(
            'panel.id = "fr27-analytics-consent"',
            ANALYTICS,
        )

    def test_product_event_allowlist_is_complete(self):
        expected = (
            "workspace_open",
            "candidate_dossier_open",
            "poll_detail_open",
            "evidence_open",
            "campaign_event_open",
            "outbound_source_click",
            "share_action",
            "professional_conversion",
        )

        for event in expected:
            with self.subTest(event=event):
                self.assertRegex(
                    ANALYTICS,
                    rf"\b{re.escape(event)}\s*:",
                )

    def test_semantic_product_hooks_are_present(self):
        self.assertIn(
            '"workspace_open"',
            HYBRID,
        )
        self.assertIn(
            '"candidate_dossier_open"',
            HYBRID,
        )
        self.assertIn(
            '"campaign_event_open"',
            HYBRID,
        )
        self.assertIn(
            '"poll_detail_open"',
            CANDIDATES,
        )
        self.assertIn(
            '"evidence_open"',
            CANDIDATES,
        )
        self.assertIn(
            '"professional_conversion"',
            INDEX,
        )

    def test_workspace_retention_contract_has_initial_and_navigation_sources(self):
        self.assertIn(
            "let workspaceExposureTracked = false;",
            HYBRID,
        )
        self.assertIn(
            '"fr27:analytics-ready"',
            HYBRID,
        )
        self.assertIn(
            '? "navigation"',
            HYBRID,
        )
        self.assertIn(
            ': "initial"',
            HYBRID,
        )
        self.assertIn(
            '"fr27:analytics-ready"',
            ANALYTICS,
        )

    def test_outbound_source_tracking_uses_approved_selectors(self):
        selectors = (
            "a.candidate-signals-source-link[href]",
            "a.candidate-signals-scrutiny-source[href]",
            "a.hybrid-events-dossier-source[href]",
            "a.hybrid-runoff-source[href]",
            "a.pe-source-link[href]",
            "a.freshness-source[href]",
            ".top-media-source-link a[href]",
            "a#race-source[href]",
        )

        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, ANALYTICS)

        self.assertIn(
            '"outbound_source_click"',
            ANALYTICS,
        )

    def test_campaign_parameters_are_allowlisted(self):
        for parameter in (
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
        ):
            with self.subTest(parameter=parameter):
                self.assertIn(
                    f'"{parameter}"',
                    ANALYTICS,
                )

    def test_product_code_does_not_call_posthog_directly(self):
        forbidden_files = [
            ROOT / "index.html",
            ROOT / "en" / "index.html",
        ]

        forbidden_files.extend(
            path
            for path in (ROOT / "assets").glob("*.js")
            if path.name != "fr27-analytics.js"
        )

        offenders = []

        for path in forbidden_files:
            source = path.read_text(encoding="utf-8")

            if "posthog.capture" in source:
                offenders.append(
                    str(path.relative_to(ROOT))
                )

        self.assertEqual(
            offenders,
            [],
            "Direct posthog.capture calls outside adapter: "
            + ", ".join(offenders),
        )

    def test_vendor_bootstrap_is_not_embedded_in_entrypoints(self):
        for html in (INDEX, ENGLISH_INDEX):
            self.assertNotIn(
                "eu.i.posthog.com",
                html,
            )
            self.assertNotIn(
                "posthog.init(",
                html,
            )
            self.assertNotIn(
                "phc_",
                html,
            )


if __name__ == "__main__":
    unittest.main()
