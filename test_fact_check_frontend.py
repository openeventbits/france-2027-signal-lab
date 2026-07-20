import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "index.html"
CLAIMS_PATH = ROOT / "claims_under_scrutiny.json"


class FactCheckFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX_PATH.read_text(encoding="utf-8")
        cls.claims = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))

        mapping_match = re.search(
            r"const claimRatingDisplay = Object\.freeze\(\{(?P<body>.*?)\n\s*\}\);",
            cls.index,
            re.DOTALL,
        )
        if not mapping_match:
            raise AssertionError("claimRatingDisplay mapping was not found in index.html")

        cls.rating_mapping = {
            source: {"label": label, "tone": tone}
            for source, label, tone in re.findall(
                r'"([^"]+)":\s*\{\s*label:\s*"([^"]+)",\s*tone:\s*"([^"]*)"\s*\}',
                mapping_match.group("body"),
            )
        }

    def test_every_current_source_rating_has_an_english_mapping(self):
        source_ratings = {review["rating"] for review in self.claims["reviews"]}
        missing = sorted(source_ratings - self.rating_mapping.keys())
        self.assertEqual([], missing, f"Unmapped publisher ratings: {missing}")

    def test_expected_english_rating_labels_are_locked(self):
        expected = {
            "C’est plus compliqué": "More complicated",
            "En partie vrai": "Partly true",
            "Faux": "False",
            "Manque de contexte": "Missing context",
            "Plutôt faux": "Mostly false",
            "Plutôt vrai": "Mostly true",
            "Trompeur": "Misleading",
            "Vidéo manipulée": "Manipulated video",
            "Vrai": "True",
        }
        actual = {
            source: self.rating_mapping[source]["label"]
            for source in expected
        }
        self.assertEqual(expected, actual)

    def test_rating_badge_renders_english_label_not_raw_source_wording(self):
        badge = re.search(
            r"function claimRatingBadge\(sourceRating\)\s*\{(?P<body>.*?)\n\s*\}",
            self.index,
            re.DOTALL,
        )
        self.assertIsNotNone(badge)
        body = badge.group("body")
        self.assertIn('label: "Unclassified"', body)
        self.assertIn('lang="en"', body)
        self.assertIn("${escapeHtml(display.label)}", body)
        self.assertNotIn("${escapeHtml(sourceRating)}", body)

    def test_newest_and_archive_views_share_claim_wire_renderer(self):
        self.assertEqual(1, self.index.count("function claimReviewRow("))
        self.assertEqual(1, self.index.count("function claimRowsMarkup("))
        self.assertIn('claimRowsMarkup(newestReviews, "signal")', self.index)
        self.assertIn('claimRowsMarkup(filtered, "archive")', self.index)
        self.assertNotIn("escapeHtml(review.rating)", self.index)

    def test_fact_check_view_keeps_canonical_claim_wire_columns(self):
        required_columns = (
            "<span>DATE</span>",
            "<span>CANDIDATE RELATIONSHIP(S)</span>",
            "<span>CLAIM REVIEWED</span>",
            "<span>RATING</span>",
            "<span>PUBLISHER</span>",
            "<span>SOURCE</span>",
        )
        render_start = self.index.index("function renderFactChecks()")
        render_end = self.index.index("function renderClaimWire()", render_start)
        renderer = self.index[render_start:render_end]

        for column in required_columns:
            self.assertIn(column, renderer)


if __name__ == "__main__":
    unittest.main()
