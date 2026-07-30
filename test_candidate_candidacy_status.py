"""Contract tests for the source-backed candidacy-status registry."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    candidacy_status_by_id,
    load_candidate_candidacy_status,
    project_display_tiers,
    validate_candidate_candidacy_status,
)


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "candidate_candidacy_status.json"
CANDIDATE_SIGNALS_PATH = ROOT / "candidate_signals.json"

TOP_LEVEL_KEYS = {
    "schema_version",
    "status_as_of",
    "candidates",
}
CANDIDATE_KEYS = {
    "candidate_id",
    "candidate_name",
    "status",
    "display_tier",
    "status_as_of",
    "source_date",
    "source_url",
    "source_title",
    "source_publisher",
    "status_note",
}
STATUS_TO_TIER = {
    "declared": "main",
    "party_selected": "main",
    "primary_contender": "main",
    "active_potential": "secondary",
    "conditional": "secondary",
    "ruled_out": "hidden",
    "withdrawn": "hidden",
    "historical_poll_only": "hidden",
}
LOCKED_STATUSES = {
    "bruno-retailleau": "declared",
    "david-lisnard": "declared",
    "dominique-de-villepin": "active_potential",
    "fabien-roussel": "primary_contender",
    "francois-hollande": "active_potential",
    "francois-ruffin": "declared",
    "gabriel-attal": "declared",
    "gerald-darmanin": "active_potential",
    "jean-luc-melenchon": "declared",
    "jordan-bardella": "conditional",
    "marine-le-pen": "declared",
    "marine-tondelier": "declared",
    "nathalie-arthaud": "declared",
    "nicolas-dupont-aignan": "declared",
    "olivier-faure": "active_potential",
    "raphael-glucksmann": "active_potential",
    "sarah-knafo": "ruled_out",
    "sebastien-lecornu": "ruled_out",
    "edouard-philippe": "declared",
    "eric-zemmour": "conditional",
}
LOCKED_TIERS = {
    "bruno-retailleau": "main",
    "david-lisnard": "main",
    "dominique-de-villepin": "secondary",
    "fabien-roussel": "main",
    "francois-hollande": "secondary",
    "francois-ruffin": "main",
    "gabriel-attal": "main",
    "gerald-darmanin": "secondary",
    "jean-luc-melenchon": "main",
    "jordan-bardella": "secondary",
    "marine-le-pen": "main",
    "marine-tondelier": "main",
    "nathalie-arthaud": "main",
    "nicolas-dupont-aignan": "main",
    "olivier-faure": "secondary",
    "raphael-glucksmann": "secondary",
    "sarah-knafo": "hidden",
    "sebastien-lecornu": "hidden",
    "edouard-philippe": "main",
    "eric-zemmour": "secondary",
}


class CandidateCandidacyStatusTests(unittest.TestCase):
    def setUp(self):
        self.payload = load_candidate_candidacy_status(REGISTRY_PATH)

    def assert_invalid(self, payload, pattern=None, candidate_universe=None):
        with self.assertRaisesRegex(
            CandidateCandidacyStatusError,
            pattern or ".+",
        ):
            validate_candidate_candidacy_status(
                payload,
                candidate_universe=candidate_universe,
            )

    @staticmethod
    def candidate_universe():
        with CANDIDATE_SIGNALS_PATH.open("r", encoding="utf-8") as source:
            return json.load(source)["candidates"]

    def test_tracked_json_is_valid_utf8_json(self):
        raw = REGISTRY_PATH.read_bytes()
        decoded = raw.decode("utf-8")
        self.assertEqual(json.loads(decoded), self.payload)

    def test_exact_top_level_key_set(self):
        self.assertEqual(set(self.payload), TOP_LEVEL_KEYS)
        for key in ("schema_version", "status_as_of", "candidates"):
            changed = copy.deepcopy(self.payload)
            changed.pop(key)
            self.assert_invalid(changed, "exact keys")
        changed = copy.deepcopy(self.payload)
        changed["unexpected"] = True
        self.assert_invalid(changed, "exact keys")

    def test_exact_candidate_key_set(self):
        self.assertTrue(self.payload["candidates"])
        for candidate in self.payload["candidates"]:
            self.assertEqual(set(candidate), CANDIDATE_KEYS)
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0].pop("status_note")
        self.assert_invalid(changed, "exact keys")
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0]["party"] = "not allowed"
        self.assert_invalid(changed, "exact keys")

    def test_payload_and_entries_must_be_plain_dicts(self):
        class DictSubclass(dict):
            pass

        self.assert_invalid(DictSubclass(self.payload), "plain dict")
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0] = DictSubclass(changed["candidates"][0])
        self.assert_invalid(changed, "plain dict")

    def test_schema_version_is_exact(self):
        self.assertEqual(self.payload["schema_version"], "1.0")
        for invalid in ("1", "1.1", 1.0, None):
            changed = copy.deepcopy(self.payload)
            changed["schema_version"] = invalid
            self.assert_invalid(changed, "exactly '1.0'")

    def test_all_eight_statuses_are_accepted(self):
        for status, tier in STATUS_TO_TIER.items():
            with self.subTest(status=status):
                changed = copy.deepcopy(self.payload)
                candidate = next(
                    item
                    for item in changed["candidates"]
                    if item["display_tier"] == tier
                )
                candidate["status"] = status
                validate_candidate_candidacy_status(changed)

    def test_unknown_status_is_rejected(self):
        for invalid in ("likely", None, []):
            with self.subTest(status=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["status"] = invalid
                self.assert_invalid(changed, "status is not allowed")

    def test_all_three_display_tiers_are_accepted(self):
        self.assertEqual(
            {
                candidate["display_tier"]
                for candidate in self.payload["candidates"]
            },
            {"main", "secondary", "hidden"},
        )
        validate_candidate_candidacy_status(self.payload)

    def test_unknown_display_tier_is_rejected(self):
        for invalid in ("archive", None, []):
            with self.subTest(tier=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["display_tier"] = invalid
                self.assert_invalid(changed, "display_tier is not allowed")

    def test_every_status_to_tier_combination_is_enforced(self):
        all_tiers = {"main", "secondary", "hidden"}
        for status, expected_tier in STATUS_TO_TIER.items():
            for wrong_tier in all_tiers - {expected_tier}:
                with self.subTest(status=status, tier=wrong_tier):
                    changed = copy.deepcopy(self.payload)
                    candidate = next(
                        item
                        for item in changed["candidates"]
                        if item["display_tier"] == expected_tier
                    )
                    candidate["status"] = status
                    candidate["display_tier"] = wrong_tier
                    self.assert_invalid(changed, "requires display_tier")

    def test_dates_must_be_canonical_iso_dates(self):
        for field, invalid in (
            ("status_as_of", "2026-7-30"),
            ("status_as_of", "2026-02-30"),
            ("source_date", "July 30, 2026"),
            ("source_date", 20260730),
        ):
            with self.subTest(field=field, invalid=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0][field] = invalid
                self.assert_invalid(changed, "canonical ISO")
        changed = copy.deepcopy(self.payload)
        changed["status_as_of"] = "2026-7-30"
        self.assert_invalid(changed, "canonical ISO")

    def test_entry_status_date_cannot_precede_source_date(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0]["status_as_of"] = "2026-02-11"
        self.assert_invalid(changed, "cannot precede source_date")

    def test_top_level_date_cannot_precede_entry_dates(self):
        changed = copy.deepcopy(self.payload)
        changed["status_as_of"] = "2026-07-29"
        self.assert_invalid(changed, "top-level status_as_of")

    def test_absolute_http_and_https_source_urls_are_accepted(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0]["source_url"] = (
            "http://www.reuters.com/verified-source"
        )
        validate_candidate_candidacy_status(changed)
        validate_candidate_candidacy_status(self.payload)

    def test_relative_and_unsafe_source_url_schemes_are_rejected(self):
        for invalid in (
            "/relative/source",
            "ftp://www.reuters.com/source",
            "javascript:alert(1)",
            "data:text/plain,source",
            "file:///source",
        ):
            with self.subTest(url=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["source_url"] = invalid
                self.assert_invalid(changed, "HTTP or HTTPS")

    def test_missing_source_url_hosts_are_rejected(self):
        for invalid in ("https:///source", "https://", "https://[invalid"):
            with self.subTest(url=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["source_url"] = invalid
                self.assert_invalid(changed, "non-empty host|well-formed")

    def test_localhost_example_and_placeholder_urls_are_rejected(self):
        for invalid in (
            "https://localhost/source",
            "https://news.localhost/source",
            "https://example.com/source",
            "https://news.example.com/source",
            "https://placeholder.invalid/source",
            "https://your-source.example.org/source",
        ):
            with self.subTest(url=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["source_url"] = invalid
                self.assert_invalid(changed, "placeholder")

    def test_source_urls_cannot_have_surrounding_whitespace(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0]["source_url"] = (
            f" {changed['candidates'][0]['source_url']}"
        )
        self.assert_invalid(changed, "trimmed")

    def test_source_text_fields_are_trimmed_and_nonempty(self):
        for field in ("source_title", "source_publisher", "status_note"):
            for invalid in ("", " ", " leading", "trailing "):
                with self.subTest(field=field, value=invalid):
                    changed = copy.deepcopy(self.payload)
                    changed["candidates"][0][field] = invalid
                    self.assert_invalid(changed, "trimmed")

    def test_status_notes_reject_analytical_or_recommendation_language(self):
        for prohibited in (
            "Has a high probability of winning.",
            "Polling gives the candidate momentum.",
            "We recommend treating the candidate as viable.",
            "The candidate ranks first by score.",
            "This is a prediction.",
        ):
            with self.subTest(note=prohibited):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["status_note"] = prohibited
                self.assert_invalid(changed, "prohibited")

    def test_candidate_ids_must_be_lowercase_ascii_kebab_case(self):
        for invalid in (
            "Bruno-Retailleau",
            "bruno_retailleau",
            "brûno-retailleau",
            "-bruno-retailleau",
            "bruno--retailleau",
            "",
        ):
            with self.subTest(candidate_id=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["candidate_id"] = invalid
                self.assert_invalid(changed, "lowercase ASCII kebab-case")

    def test_candidate_id_must_match_shared_identity_contract(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0]["candidate_id"] = "different-person"
        self.assert_invalid(changed, "does not match candidate_name")

    def test_candidate_names_must_be_canonical(self):
        for invalid in (
            " Bruno Retailleau",
            "Bruno  Retailleau",
            "Bruno\tRetailleau",
        ):
            with self.subTest(name=invalid):
                changed = copy.deepcopy(self.payload)
                changed["candidates"][0]["candidate_name"] = invalid
                self.assert_invalid(changed, "must be canonical")

    def test_duplicate_candidate_ids_are_rejected(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][1]["candidate_id"] = (
            changed["candidates"][0]["candidate_id"]
        )
        self.assert_invalid(changed, "duplicate candidate ID")

    def test_duplicate_canonical_names_are_rejected(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][1]["candidate_name"] = (
            changed["candidates"][0]["candidate_name"]
        )
        self.assert_invalid(changed, "duplicate canonical candidate name")

    def test_normalized_identity_collisions_are_rejected(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][1]["candidate_name"] = "Bruno-Retailleau"
        changed["candidates"][1]["candidate_id"] = "bruno-retailleau"
        self.assert_invalid(changed, "normalized candidate identity collision")

    def test_current_registry_contains_exactly_twenty_candidates(self):
        self.assertEqual(len(self.payload["candidates"]), 20)
        changed = copy.deepcopy(self.payload)
        changed["candidates"].pop()
        self.assert_invalid(changed, "exactly 20")

    def test_current_projection_has_locked_counts(self):
        counts = project_display_tiers(self.payload)["counts"]
        self.assertEqual(
            counts,
            {
                "main": 11,
                "secondary": 7,
                "hidden": 2,
                "active": 18,
                "total": 20,
            },
        )

    def test_current_hidden_ids_are_exact(self):
        self.assertEqual(
            set(project_display_tiers(self.payload)["hidden"]),
            {"sarah-knafo", "sebastien-lecornu"},
        )

    def test_all_locked_candidate_statuses_are_exact(self):
        actual = {
            candidate["candidate_id"]: candidate["status"]
            for candidate in self.payload["candidates"]
        }
        self.assertEqual(actual, LOCKED_STATUSES)

    def test_all_locked_display_tiers_are_exact(self):
        actual = {
            candidate["candidate_id"]: candidate["display_tier"]
            for candidate in self.payload["candidates"]
        }
        self.assertEqual(actual, LOCKED_TIERS)

    def test_registry_order_is_deterministic(self):
        expected = sorted(
            self.payload["candidates"],
            key=lambda candidate: (
                candidate["candidate_name"].casefold(),
                candidate["candidate_id"],
            ),
        )
        self.assertEqual(self.payload["candidates"], expected)
        changed = copy.deepcopy(self.payload)
        changed["candidates"][0], changed["candidates"][1] = (
            changed["candidates"][1],
            changed["candidates"][0],
        )
        self.assert_invalid(changed, "ordered by")

    def test_project_display_tiers_preserves_neutral_registry_order(self):
        projection = project_display_tiers(self.payload)
        for tier in ("main", "secondary", "hidden"):
            expected = [
                candidate["candidate_id"]
                for candidate in self.payload["candidates"]
                if candidate["display_tier"] == tier
            ]
            self.assertEqual(projection[tier], expected)
        self.assertEqual(projection["status_as_of"], "2026-07-30")

    def test_candidacy_status_by_id_indexes_all_entries(self):
        indexed = candidacy_status_by_id(self.payload)
        self.assertEqual(set(indexed), set(LOCKED_STATUSES))
        self.assertEqual(indexed["sarah-knafo"]["candidate_name"], "Sarah Knafo")

    def test_missing_candidate_universe_ids_are_rejected(self):
        universe = copy.deepcopy(self.candidate_universe())
        universe.pop()
        self.assert_invalid(
            self.payload,
            "missing registry IDs",
            candidate_universe=universe,
        )

    def test_unknown_candidate_universe_ids_are_rejected(self):
        universe = copy.deepcopy(self.candidate_universe())
        universe[0]["candidate_id"] = "unknown-person"
        self.assert_invalid(
            self.payload,
            "unknown candidate IDs",
            candidate_universe=universe,
        )

    def test_candidate_universe_name_mismatch_is_rejected(self):
        universe = copy.deepcopy(self.candidate_universe())
        universe[0]["candidate_name"] = "Different Person"
        self.assert_invalid(
            self.payload,
            "canonical name mismatch",
            candidate_universe=universe,
        )

    def test_duplicate_candidate_universe_ids_are_rejected(self):
        universe = copy.deepcopy(self.candidate_universe())
        universe[1]["candidate_id"] = universe[0]["candidate_id"]
        self.assert_invalid(
            self.payload,
            "duplicate candidate ID",
            candidate_universe=universe,
        )

    def test_candidate_universe_requires_complete_twenty_person_coverage(self):
        universe = copy.deepcopy(self.candidate_universe())
        universe.append(
            {
                "candidate_id": "unknown-person",
                "candidate_name": "Unknown Person",
            }
        )
        self.assert_invalid(
            self.payload,
            "unknown candidate IDs",
            candidate_universe=universe,
        )

    def test_shared_source_url_with_identical_metadata_is_accepted(self):
        changed = copy.deepcopy(self.payload)
        source = changed["candidates"][0]
        reused = changed["candidates"][1]
        reused["source_url"] = source["source_url"]
        for key in ("source_date", "source_title", "source_publisher"):
            reused[key] = source[key]
        validate_candidate_candidacy_status(changed)

    def test_shared_source_url_with_conflicting_metadata_is_rejected(self):
        changed = copy.deepcopy(self.payload)
        changed["candidates"][1]["source_url"] = (
            changed["candidates"][0]["source_url"]
        )
        self.assert_invalid(changed, "conflicting source metadata")

    def test_validation_does_not_mutate_source_records(self):
        original = copy.deepcopy(self.payload)
        validate_candidate_candidacy_status(self.payload)
        project_display_tiers(self.payload)
        candidacy_status_by_id(self.payload)
        self.assertEqual(self.payload, original)

    def test_repeated_loads_are_semantically_identical(self):
        first = load_candidate_candidacy_status(REGISTRY_PATH)
        second = load_candidate_candidacy_status(REGISTRY_PATH)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_tracked_registry_validates_against_candidate_signals_universe(self):
        validate_candidate_candidacy_status(
            self.payload,
            candidate_universe=self.candidate_universe(),
        )

    def test_d1_production_modules_do_not_import_registry(self):
        for filename in (
            "fetch_polls.py",
            "fetch_news_wire.py",
            "fetch_claims_under_scrutiny.py",
            "generate_recent_changes.py",
            "build_candidate_signals.py",
        ):
            with self.subTest(filename=filename):
                source = (ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("candidate_candidacy_status", source)

    def test_d1_workflows_do_not_reference_registry(self):
        for filename in (
            ".github/workflows/update-polls.yml",
            ".github/workflows/update-news-wire.yml",
            ".github/workflows/update-claims-under-scrutiny.yml",
        ):
            with self.subTest(filename=filename):
                source = (ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("candidate_candidacy_status", source)

    def test_d1_javascript_does_not_reference_registry(self):
        for filename in (
            "assets/candidate-signals.js",
            "assets/election-coverage-modal.js",
            "assets/hybrid-dashboard.js",
            "assets/topic-coverage-modal.js",
        ):
            with self.subTest(filename=filename):
                source = (ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("candidate_candidacy_status", source)


if __name__ == "__main__":
    unittest.main()
