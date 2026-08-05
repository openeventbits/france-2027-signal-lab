from pathlib import Path
import html
import json
import re
import unittest

ROOT = Path(__file__).resolve().parent
INDEX_TEXT = (ROOT / "index.html").read_text(encoding="utf-8")
RUNTIME_TEXT = (ROOT / "assets" / "localization.js").read_text(encoding="utf-8")
CATALOG_TEXT = (ROOT / "locales" / "en.js").read_text(encoding="utf-8")
TITLE_KEY = "page.france_2027_signal_lab_source_linked_election_signals"
TITLE_TEXT = "France 2027 Signal Lab — Source-Linked Election Signals"
DYNAMIC_KEYS = {
    "candidate.scrutiny.archive_by",
    "dashboard.candidate_portrait_alt",
    "dashboard.claims.review_count_label",
    "dashboard.news.campaign_agenda_unavailable",
    "dashboard.news.candidate_coverage_unavailable",
    "dashboard.news.relevant_news_unavailable",
    "dashboard.poll.partial_reported_field",
    "dashboard.runoff.smallest_reported_margin",
    "dashboard.source.open_category_source_from_publisher",
    "signal_board.claims.latest_review",
    "signal_board.media.latest_accepted_item",
}


def catalog_messages():
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        CATALOG_TEXT,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("English catalog object was not found")
    return json.loads(match.group(1))


class LocalizationFoundationTests(unittest.TestCase):
    def test_english_catalog_has_685_unique_keys(self):
        messages = catalog_messages()
        self.assertEqual(len(messages), 685)
        self.assertEqual(len(messages), len(set(messages)))
        self.assertIn(TITLE_KEY, messages)

    def test_complete_dynamic_message_keys_are_catalogued(self):
        messages = catalog_messages()
        self.assertEqual(len(DYNAMIC_KEYS), 11)
        self.assertTrue(DYNAMIC_KEYS.issubset(messages))
        self.assertEqual(
            messages["candidate.scrutiny.archive_by"],
            "Archive · BY",
        )

    def test_runtime_exposes_approved_foundation_api(self):
        for declaration in (
            "const t =",
            "const formatDate =",
            "const formatNumber =",
            "const formatPercent =",
            "const pluralCategory =",
            "const siteUrl =",
            "const buildLocaleUrl =",
            "const applyDocumentTitle =",
        ):
            self.assertIn(declaration, RUNTIME_TEXT)
        self.assertIn("global.FR27I18N = api;", RUNTIME_TEXT)

    def test_index_bootstraps_catalog_before_runtime(self):
        opening = re.search(r"<html\b[^>]*>", INDEX_TEXT, re.I)
        self.assertIsNotNone(opening)
        opening_tag = opening.group(0)
        self.assertIn("lang=\"en\"", opening_tag)
        self.assertIn("data-locale=\"en\"", opening_tag)
        self.assertIn("data-site-root=\"./\"", opening_tag)
        self.assertIn(
            "data-i18n-document-title=\"" + TITLE_KEY + "\"",
            opening_tag,
        )
        catalog_position = INDEX_TEXT.index(
            "src=\"locales/en.js\""
        )
        runtime_position = INDEX_TEXT.index(
            "src=\"assets/localization.js\""
        )
        self.assertLess(catalog_position, runtime_position)

    def test_title_migration_preserves_english_fallback(self):
        title_match = re.search(
            r"<title>(.*?)</title>",
            INDEX_TEXT,
            re.I | re.DOTALL,
        )
        self.assertIsNotNone(title_match)
        fallback_title = html.unescape(title_match.group(1).strip())
        messages = catalog_messages()
        self.assertEqual(fallback_title, TITLE_TEXT)
        self.assertEqual(messages[TITLE_KEY], TITLE_TEXT)


    def test_first_static_text_batch_is_keyed(self):
        targets = {
            "dashboard.what_changed": "WHAT CHANGED",
            "dashboard.source_linked_updates_loading": (
                "SOURCE-LINKED UPDATES LOADING"
            ),
            "dashboard.checking_for_source_linked_dashboard_signals": (
                "Checking for source-linked dashboard signals…"
            ),
            "dashboard.race_at_a_glance": "RACE AT A GLANCE",
            "dashboard.loading_candidate_scores": (
                "Loading candidate scores…"
            ),
            "dashboard.30_day_activity_14_day_recent": (
                "30-day activity · 14-day recent"
            ),
            "dashboard.loading_media_metrics": (
                "Loading media metrics…"
            ),
        }

        self.assertEqual(len(targets), 7)

        for key, english in targets.items():
            self.assertEqual(
                INDEX_TEXT.count(f'data-i18n="{key}"'),
                1,
            )
            self.assertEqual(INDEX_TEXT.count(english), 1)

    def test_first_static_aria_batch_is_keyed(self):
        targets = {
            "dashboard.first_round_election_countdown": (
                "First-round election countdown"
            ),
            "dashboard.top_briefing": "Top briefing",
            "dashboard.latest_first_round_poll_events": (
                "Latest first-round poll events"
            ),
            "dashboard.choose_a_reported_first_round_poll_scenario": (
                "Choose a reported first-round poll scenario"
            ),
            "dashboard.dashboard_context": "Dashboard context",
        }

        self.assertEqual(len(targets), 5)

        for key, english in targets.items():
            self.assertEqual(
                INDEX_TEXT.count(
                    f'data-i18n-aria-label="{key}"'
                ),
                1,
            )
            self.assertEqual(
                INDEX_TEXT.count(f'aria-label="{english}"'),
                1,
            )

    def test_static_runtime_preserves_updated_dynamic_content(self):
        for declaration in (
            "const fallbackMessageFor =",
            "const applyTextTranslations =",
            "const applyAttributeTranslations =",
            "const applyStaticTranslations =",
        ):
            self.assertIn(declaration, RUNTIME_TEXT)

        self.assertIn(
            "current === fallback.trim()",
            RUNTIME_TEXT,
        )
        self.assertIn(
            "current === fallback",
            RUNTIME_TEXT,
        )
        self.assertIn(
            '"DOMContentLoaded"',
            RUNTIME_TEXT,
        )


    def test_static_shell_context_batch_is_keyed(self):
        targets = {
            "dashboard.source_linked_signals_from_the_french_presidential_race": (
                "Source-linked signals from the French presidential race."
            ),
            "dashboard.next_milestone": "NEXT MILESTONE",
            "dashboard.latest_poll": "LATEST POLL",
            "dashboard.poll_coverage": "POLL COVERAGE",
            "dashboard.source_network": "SOURCE NETWORK",
        }

        self.assertEqual(len(targets), 5)

        for key, english in targets.items():
            self.assertEqual(
                INDEX_TEXT.count(f'data-i18n="{key}"'),
                1,
            )
            self.assertEqual(
                INDEX_TEXT.count(english),
                1,
            )


if __name__ == "__main__":
    unittest.main()
