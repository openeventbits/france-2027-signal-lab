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


if __name__ == "__main__":
    unittest.main()
