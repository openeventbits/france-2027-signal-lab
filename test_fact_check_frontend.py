import json
import re
import shutil
import subprocess
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

        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("Node.js is required for Claims frontend tests")
        validator = cls.index[
            cls.index.index("function isValidClaimsDate("):
            cls.index.index("function claimsMetrics(")
        ]
        script = r'''
          function safeSourceUrl(value) {
            try {
              const url = new URL(value);
              return ["http:", "https:"].includes(url.protocol) ? value : "";
            } catch (error) {
              return "";
            }
          }
        ''' + validator + r'''
          function validReview(id = "review-1") {
            return {
              id,
              publisher_name: "AFP Factuel",
              review_date: "2026-08-12",
              claim_text: "A reviewed claim",
              claimant: "Candidate A",
              rating: "Faux",
              review_url: "https://factuel.afp.com/review-1",
              candidate_associations: [{
                candidate_id: "candidate-a",
                candidate_name: "Candidate A",
                relationship: "by"
              }]
            };
          }
          function payload(schemaVersion) {
            const value = {
              schema_version: schemaVersion,
              generated_at: "2026-08-13T07:47:00Z",
              counts: { reviews: 1 },
              reviews: [validReview()]
            };
            if (schemaVersion === 1) {
              value.candidate_roster = {
                count: 1,
                candidates: [{ candidate_name: "Candidate A" }]
              };
            } else {
              value.candidate_query = {
                count: 1,
                candidate_ids: ["candidate-a"],
                candidate_names: ["Candidate A"]
              };
            }
            return value;
          }
          function check(value) {
            try {
              const result = validateClaimsPayload(value);
              return {
                accepted: true,
                reviewCount: result.reviews.length,
                rosterCount: result.rosterCount,
                hasSkippedReviews: Object.hasOwn(result, "skippedReviews")
              };
            } catch (error) {
              return { accepted: false, error: error.message };
            }
          }

          const unsupported = payload(2);
          unsupported.schema_version = 3;
          const malformed = payload(2);
          malformed.reviews.push(validReview("review-2"));
          malformed.reviews[1].claimant = "";
          malformed.counts.reviews = 2;
          const mismatch = payload(2);
          mismatch.counts.reviews = 0;
          const negative = payload(2);
          negative.counts.reviews = -1;
          const fractional = payload(2);
          fractional.counts.reviews = 1.5;

          console.log(JSON.stringify({
            schema1: check(payload(1)),
            schema2: check(payload(2)),
            unsupported: check(unsupported),
            malformed: check(malformed),
            mismatch: check(mismatch),
            negative: check(negative),
            fractional: check(fractional)
          }));
        '''
        result = subprocess.run(
            [node, "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.validation = json.loads(result.stdout)

    def test_schema_one_claims_payload_is_accepted(self):
        self.assertTrue(self.validation["schema1"]["accepted"])

    def test_schema_two_claims_payload_is_accepted(self):
        self.assertTrue(self.validation["schema2"]["accepted"])

    def test_unsupported_claims_schema_is_rejected(self):
        self.assertFalse(self.validation["unsupported"]["accepted"])
        self.assertIn("unsupported schema", self.validation["unsupported"]["error"])

    def test_one_malformed_review_rejects_entire_claims_payload(self):
        self.assertFalse(self.validation["malformed"]["accepted"])
        self.assertIn("cannot be rendered safely", self.validation["malformed"]["error"])

    def test_claim_review_count_must_be_nonnegative_integer_and_match(self):
        for case in ("mismatch", "negative", "fractional"):
            with self.subTest(case=case):
                self.assertFalse(self.validation[case]["accepted"])

    def test_fully_valid_claims_payload_loads_without_skipped_state(self):
        result = self.validation["schema2"]
        self.assertTrue(result["accepted"])
        self.assertEqual(result["reviewCount"], 1)
        self.assertEqual(result["rosterCount"], 1)
        self.assertFalse(result["hasSkippedReviews"])

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
