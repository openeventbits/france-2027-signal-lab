import copy
import json
import os
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import fetch_claims_under_scrutiny as collector
from candidate_candidacy_status import active_candidate_ids, active_candidate_names
from generate_recent_changes import fact_check_entries
from test_candidate_active_monitoring_phase3a1 import registry_v2


ROOT = Path(__file__).resolve().parent
TRACKED_REGISTRY = ROOT / "candidate_candidacy_status.json"
DYNAMIC_REGISTRY = ROOT / "test_fixtures" / "candidate_candidacy_status_dynamic.json"
AS_OF = date(2026, 8, 11)


def v1_registry() -> dict:
    return json.loads(DYNAMIC_REGISTRY.read_text(encoding="utf-8"))


def v2_registry(*missing_ids: str) -> dict:
    return registry_v2(DYNAMIC_REGISTRY, *missing_ids)


def candidate_records(payload: dict) -> list[dict]:
    return payload["candidates"]


def api_claim(
    *,
    url="https://factuel.afp.com/politique/article?utm_source=x&id=7",
    claim_text="Alice Observée a fait cette déclaration",
    claimant="Alice Observée",
    review_date="2026-08-10T12:30:00Z",
    rating="Faux",
):
    return {
        "text": claim_text,
        "claimant": claimant,
        "claimReview": [
            {
                "url": url,
                "reviewDate": review_date,
                "textualRating": rating,
                "publisher": {"name": "Untrusted display label"},
            }
        ],
    }


def diagnostics():
    return {
        "excluded_unknown_hosts": [],
        "invalid_reviews": [],
        "unresolved_associations": [],
        "deduplication": {},
    }


def one_review(payload: dict, *, candidate_name="Alice Observée", claimant=None):
    return collector.flatten_claims(
        [
            api_claim(
                claim_text=f"{candidate_name} a fait cette déclaration",
                claimant=claimant or candidate_name,
            )
        ],
        candidate_records(payload),
        AS_OF,
        365,
        diagnostics(),
    )[0]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class RegistryRosterTests(unittest.TestCase):
    def test_query_roster_calls_shared_active_helper(self):
        payload = v1_registry()
        with mock.patch.object(
            collector,
            "active_candidate_records",
            wraps=collector.active_candidate_records,
        ) as helper:
            records = collector.candidate_query_records(payload)
        helper.assert_called_once_with(payload)
        self.assertEqual(
            [record["candidate_id"] for record in records],
            active_candidate_ids(payload),
        )

    def test_present_main_and_secondary_included_hidden_excluded(self):
        query = collector.build_candidate_query(v2_registry())
        self.assertIn("alice-observee", query["candidate_ids"])
        self.assertIn("chloe-potentielle", query["candidate_ids"])
        self.assertNotIn("david-retire", query["candidate_ids"])

    def test_temporarily_missing_is_excluded(self):
        query = collector.build_candidate_query(v2_registry("chloe-potentielle"))
        self.assertNotIn("chloe-potentielle", query["candidate_ids"])

    def test_unpolled_active_candidate_is_included(self):
        query = collector.build_candidate_query(v2_registry())
        self.assertIn("benoit-non-teste", query["candidate_ids"])

    def test_dynamic_counts_below_and_above_old_poll_roster_size(self):
        small = v1_registry()
        small["candidates"] = small["candidates"][:2]
        self.assertEqual(collector.build_candidate_query(small)["count"], 2)
        tracked = collector.load_candidacy_status(TRACKED_REGISTRY)
        self.assertGreater(collector.build_candidate_query(tracked)["count"], 14)

    def test_registry_order_is_preserved(self):
        payload = v2_registry()
        query = collector.build_candidate_query(payload)
        self.assertEqual(query["candidate_ids"], active_candidate_ids(payload))
        self.assertEqual(query["candidate_names"], active_candidate_names(payload))

    def test_poll_inputs_are_not_cli_options_or_collector_inputs(self):
        args = collector.parse_args([])
        self.assertFalse(hasattr(args, "polls"))
        self.assertFalse(hasattr(args, "candidate_window_days"))
        self.assertEqual(args.candidacy_status, Path("candidate_candidacy_status.json"))

    def test_schema_one_and_two_active_projection(self):
        self.assertEqual(collector.build_candidate_query(v1_registry())["count"], 3)
        self.assertEqual(
            collector.build_candidate_query(v2_registry("alice-observee"))["count"],
            2,
        )

    def test_malformed_registry_fails_without_poll_fallback(self):
        with self.assertRaises(collector.CollectorError):
            collector.candidate_query_records({"schema_version": "2.0"})


class RelationshipTests(unittest.TestCase):
    def test_canonical_claimant_produces_by(self):
        associations, unresolved = collector.classify_candidate_associations(
            "Un autre texte", "Alice Observée", candidate_records(v2_registry())
        )
        self.assertEqual(associations[0]["relationship"], "by")
        self.assertEqual(unresolved, [])

    def test_stable_id_keyed_ruffin_alias_is_preserved(self):
        tracked = collector.load_candidacy_status(TRACKED_REGISTRY)
        ruffin = next(
            record for record in tracked["candidates"]
            if record["candidate_id"] == "francois-ruffin"
        )
        terms = collector.fact_check_query_terms(ruffin)
        self.assertEqual(terms, ("François Ruffin", "Le député François Ruffin"))
        associations, _ = collector.classify_candidate_associations(
            "Un autre texte", "Le député François Ruffin", [ruffin]
        )
        self.assertEqual(associations[0]["candidate_id"], "francois-ruffin")

    def test_previous_name_resolves_to_stable_current_identity(self):
        payload = v2_registry()
        candidate = payload["candidates"][0]
        old_name = candidate["candidate_name"]
        candidate["candidate_name"] = "Alice Nouvelle"
        candidate["previous_names"] = [old_name]
        payload["candidates"].sort(
            key=lambda item: (item["candidate_name"].casefold(), item["candidate_id"])
        )
        associations, _ = collector.classify_candidate_associations(
            "Un autre texte", old_name, candidate_records(payload)
        )
        self.assertEqual(associations[0]["candidate_id"], "alice-observee")
        self.assertEqual(associations[0]["candidate_name"], "Alice Nouvelle")

    def test_ambiguous_claimant_fails_closed(self):
        associations, unresolved = collector.classify_candidate_associations(
            "Alice Observée aurait annoncé ceci",
            "Non indiqué",
            candidate_records(v2_registry()),
        )
        self.assertEqual(associations, [])
        self.assertEqual(unresolved[0]["reason"], "relationship_unresolved")

    def test_mixed_by_and_about_associations(self):
        result = collector.flatten_claims(
            [
                api_claim(
                    claimant="Alice Observée",
                    claim_text="Alice Observée évoque Chloé Potentielle",
                )
            ],
            candidate_records(v2_registry()),
            AS_OF,
            365,
            diagnostics(),
        )
        self.assertEqual(
            [(item["candidate_id"], item["relationship"])
             for item in result[0]["candidate_associations"]],
            [("alice-observee", "by"), ("chloe-potentielle", "about")],
        )


class ReviewAndContractTests(unittest.TestCase):
    def test_url_normalization_removes_tracking_parameters(self):
        normalized, host = collector.normalize_review_url(
            "HTTPS://FACTUEL.AFP.COM:443/article?utm_source=x&b=2&fbclid=z&a=1#part"
        )
        self.assertEqual(normalized, "https://factuel.afp.com/article?a=1&b=2")
        self.assertEqual(host, "factuel.afp.com")

    def test_duplicate_url_associations_merge(self):
        duplicate = api_claim()
        result = collector.flatten_claims(
            [duplicate, copy.deepcopy(duplicate)],
            candidate_records(v2_registry()),
            AS_OF,
            365,
            diagnostics(),
        )
        self.assertEqual(len(result), 1)

    def test_no_evidence_candidate_creates_no_fake_review(self):
        self.assertEqual(
            collector.flatten_claims(
                [], candidate_records(v2_registry()), AS_OF, 365, diagnostics()
            ),
            [],
        )

    def test_hidden_candidate_historical_review_is_valid(self):
        payload = v2_registry()
        review = one_review(payload)
        hidden = next(
            item for item in payload["candidates"] if item["candidate_id"] == "alice-observee"
        )
        hidden["status"] = "withdrawn"
        hidden["display_tier"] = "hidden"
        bundle = collector.build_public_bundle(payload, [review], 365, "2026-08-11T00:00:00Z")
        collector.validate_public_bundle(bundle, candidacy_payload=payload)
        self.assertNotIn("alice-observee", bundle["candidate_query"]["candidate_ids"])
        self.assertEqual(bundle["reviews"][0]["candidate_associations"][0]["candidate_id"], "alice-observee")

    def test_temporarily_missing_historical_review_is_valid(self):
        payload = v2_registry("alice-observee")
        active_payload = v2_registry()
        review = one_review(active_payload)
        bundle = collector.build_public_bundle(payload, [review], 365, "2026-08-11T00:00:00Z")
        collector.validate_public_bundle(bundle, candidacy_payload=payload)

    def test_same_utc_date_generated_time_is_not_semantic(self):
        first = collector.build_public_bundle(v2_registry(), [], 365, "2026-08-11T00:00:00Z")
        later = copy.deepcopy(first)
        later["generated_at"] = "2026-08-11T12:00:00Z"
        self.assertEqual(
            collector.semantic_public_content(first),
            collector.semantic_public_content(later),
        )

    def test_next_utc_date_generated_time_is_semantic(self):
        first = collector.build_public_bundle(v2_registry(), [], 365, "2026-08-11T12:00:00Z")
        later = copy.deepcopy(first)
        later["generated_at"] = "2026-08-12T00:00:00Z"
        self.assertNotEqual(
            collector.semantic_public_content(first),
            collector.semantic_public_content(later),
        )

    def test_registry_query_change_is_semantic(self):
        first = collector.build_public_bundle(v2_registry(), [], 365, "2026-08-11T00:00:00Z")
        changed = collector.build_public_bundle(
            v2_registry("alice-observee"), [], 365, "2026-08-11T12:00:00Z"
        )
        self.assertNotEqual(
            collector.semantic_public_content(first),
            collector.semantic_public_content(changed),
        )

    def test_diagnostics_metadata_has_no_poll_window_semantics(self):
        payload = v2_registry()
        writes = []
        with (
            mock.patch.object(collector, "load_candidacy_status", return_value=payload),
            mock.patch.object(collector, "load_existing_reviews", return_value=[]),
            mock.patch.object(collector, "fetch_candidate_claims", return_value=([], 1)),
            mock.patch.object(collector, "atomic_write_json", side_effect=lambda path, value: writes.append((path, value))),
            mock.patch.dict(os.environ, {"GOOGLE_FACTCHECK_API_KEY": "test"}, clear=True),
        ):
            bundle = collector.collect(
                Path("registry.json"), Path("output.json"), Path("diagnostics.json"),
                365, AS_OF, "2026-08-11", None,
            )
        diagnostic = writes[0][1]
        self.assertEqual(diagnostic["candidate_source"], "candidate_candidacy_status.json")
        self.assertEqual(diagnostic["candidate_rule"], "active_monitoring_field")
        self.assertEqual(diagnostic["candidate_query_count"], 3)
        self.assertEqual(diagnostic["candidate_query_ids"], active_candidate_ids(payload))
        self.assertNotIn("candidate_window_days", diagnostic)
        self.assertNotIn("poll_cutoff", diagnostic)
        self.assertEqual(bundle["candidate_query"]["count"], 3)

    def test_current_tracked_schema_one_claims_still_validate(self):
        payload = json.loads((ROOT / "claims_under_scrutiny.json").read_text(encoding="utf-8"))
        collector.validate_public_bundle(payload)


class LifecycleCollectionTests(unittest.TestCase):
    def run_collect(self, payload: dict, existing: dict | None = None):
        calls = []
        writes = []
        retained = [] if existing is None else [
            collector._canonicalize_existing_review(review, payload)
            for review in existing["reviews"]
        ]
        with (
            mock.patch.object(collector, "load_candidacy_status", return_value=payload),
            mock.patch.object(collector, "load_existing_reviews", return_value=retained),
            mock.patch.object(
                collector,
                "fetch_candidate_claims",
                side_effect=lambda term, _key: (calls.append(term) or [], 1),
            ),
            mock.patch.object(
                collector,
                "atomic_write_json",
                side_effect=lambda path, value: writes.append((path, value)),
            ),
            mock.patch.dict(os.environ, {"GOOGLE_FACTCHECK_API_KEY": "test"}, clear=True),
        ):
            bundle = collector.collect(
                Path("registry.json"), Path("output.json"), Path("diagnostics.json"),
                365, AS_OF, "2026-08-11", None,
            )
        return bundle, calls, writes[0][1]

    def test_only_active_candidates_generate_queries(self):
        payload = v2_registry("chloe-potentielle")
        _bundle, calls, _diagnostic = self.run_collect(payload)
        self.assertIn("Alice Observée", calls)
        self.assertIn("Benoît Non Testé", calls)
        self.assertNotIn("Chloé Potentielle", calls)
        self.assertNotIn("David Retiré", calls)

    def test_existing_schema_two_query_change_does_not_delete_evidence(self):
        active = v2_registry()
        existing = collector.build_public_bundle(
            active,
            [one_review(active)],
            365,
            "2026-08-10T00:00:00Z",
        )
        hidden = copy.deepcopy(active)
        candidate = next(
            item for item in hidden["candidates"]
            if item["candidate_id"] == "alice-observee"
        )
        candidate["status"] = "withdrawn"
        candidate["display_tier"] = "hidden"
        path = mock.Mock(spec=Path)
        path.exists.return_value = True
        path.read_text.return_value = json.dumps(existing, ensure_ascii=False)
        retained = collector.load_existing_reviews(path, hidden, AS_OF, 365)
        self.assertEqual(len(retained), 1)
        self.assertEqual(
            retained[0]["candidate_associations"][0]["candidate_id"],
            "alice-observee",
        )

    def test_historical_query_transition_accepts_old_and_requires_new_projection(self):
        previous = v2_registry()
        existing = collector.build_public_bundle(
            previous,
            [one_review(previous)],
            365,
            "2026-08-10T00:00:00Z",
        )
        current = copy.deepcopy(previous)
        candidate = next(
            item for item in current["candidates"]
            if item["candidate_id"] == "alice-observee"
        )
        candidate["status"] = "withdrawn"
        candidate["display_tier"] = "hidden"

        collector.validate_public_bundle(
            existing,
            expected_archive_window_days=365,
            candidacy_payload=None,
        )
        path = mock.Mock(spec=Path)
        path.exists.return_value = True
        path.read_text.return_value = json.dumps(existing, ensure_ascii=False)
        retained = collector.load_existing_reviews(path, current, AS_OF, 365)
        generated = collector.build_public_bundle(
            current,
            retained,
            365,
            "2026-08-11T00:00:00Z",
        )

        collector.validate_public_bundle(generated, candidacy_payload=current)
        self.assertNotEqual(existing["candidate_query"], generated["candidate_query"])
        self.assertEqual(
            generated["candidate_query"],
            collector.build_candidate_query(current),
        )
        self.assertEqual(
            generated["reviews"][0]["candidate_associations"][0]["candidate_id"],
            "alice-observee",
        )

    def test_historical_review_for_deleted_identity_is_rejected(self):
        previous = v2_registry()
        existing = collector.build_public_bundle(
            previous,
            [one_review(previous)],
            365,
            "2026-08-10T00:00:00Z",
        )
        current = copy.deepcopy(previous)
        current["candidates"] = [
            candidate for candidate in current["candidates"]
            if candidate["candidate_id"] != "alice-observee"
        ]
        path = mock.Mock(spec=Path)
        path.exists.return_value = True
        path.read_text.return_value = json.dumps(existing, ensure_ascii=False)

        with self.assertRaisesRegex(
            collector.CollectorError,
            "absent from canonical registry",
        ):
            collector.load_existing_reviews(path, current, AS_OF, 365)

    def test_active_to_hidden_stops_query_and_preserves_review(self):
        active = v2_registry()
        review = one_review(active)
        existing = collector.build_public_bundle(
            active, [review], 365, "2026-08-10T00:00:00Z"
        )
        hidden = copy.deepcopy(active)
        candidate = next(
            item for item in hidden["candidates"] if item["candidate_id"] == "alice-observee"
        )
        candidate["status"] = "withdrawn"
        candidate["display_tier"] = "hidden"
        bundle, calls, diagnostic = self.run_collect(hidden, existing)
        self.assertNotIn("Alice Observée", calls)
        self.assertEqual(len(bundle["reviews"]), 1)
        self.assertEqual(diagnostic["historical_evidence"]["retained_existing_reviews"], 1)

    def test_returning_candidate_resumes_query_with_same_id(self):
        missing = v2_registry("alice-observee")
        _bundle, missing_calls, _ = self.run_collect(missing)
        returned = v2_registry()
        _bundle, returned_calls, _ = self.run_collect(returned)
        self.assertNotIn("Alice Observée", missing_calls)
        self.assertIn("Alice Observée", returned_calls)
        self.assertIn("alice-observee", active_candidate_ids(returned))

    def test_transient_api_failure_fails_closed(self):
        payload = v2_registry()
        with (
            mock.patch.object(collector, "load_candidacy_status", return_value=payload),
            mock.patch.object(collector, "load_existing_reviews", return_value=[]),
            mock.patch.object(
                collector,
                "fetch_candidate_claims",
                side_effect=collector.CollectorError("Fact Check API request failed after retries"),
            ),
            mock.patch.object(collector, "atomic_write_json"),
            mock.patch.dict(os.environ, {"GOOGLE_FACTCHECK_API_KEY": "test"}, clear=True),
        ):
            with self.assertRaises(collector.CollectorError):
                collector.collect(
                    Path("registry.json"), Path("output.json"), Path("diagnostics.json"),
                    365, AS_OF, "2026-08-11", None,
                )


class DownstreamCompatibilityTests(unittest.TestCase):
    def test_legacy_frontend_accepts_schema_two_and_filters_from_evidence(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("payload.candidate_query", source)
        self.assertIn("const evidenceCandidateNames = new Set(validReviews.flatMap", source)
        self.assertNotIn("trackedCandidateNames", source)
        self.assertIn("const candidates = [...metrics.candidates.entries()]", source)
        self.assertNotIn("rolling 45-day polling eligibility rule", source)

    def test_hybrid_frontend_candidates_are_review_association_derived(self):
        source = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")
        self.assertIn("review.candidate_associations.forEach(association =>", source)
        self.assertIn("const candidates = [...candidateMap.values()]", source)

    def test_recent_changes_does_not_filter_claims_by_active_query_roster(self):
        payload = v2_registry()
        review = one_review(payload)
        entries = fact_check_entries(
            {
                "generated_at": "2026-08-11T00:00:00Z",
                "candidate_query": {
                    "candidate_ids": [],
                    "candidate_names": [],
                    "count": 0,
                },
                "reviews": [review],
            },
            {},
            datetime(2026, 8, 11, tzinfo=timezone.utc),
            Counter(),
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["candidate_ids"], ["alice-observee"])


class ApiTests(unittest.TestCase):
    class Response:
        def __init__(self, payload):
            self.payload = json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.payload

    def test_pagination_follows_all_pages(self):
        responses = iter(
            [
                self.Response({"claims": [{"text": "one"}], "nextPageToken": "next"}),
                self.Response({"claims": [{"text": "two"}]}),
            ]
        )
        claims, pages = collector.fetch_candidate_claims(
            "François Ruffin", "secret", opener=lambda *args, **kwargs: next(responses)
        )
        self.assertEqual([item["text"] for item in claims], ["one", "two"])
        self.assertEqual(pages, 2)

    def test_repeated_pagination_token_fails(self):
        responses = iter(
            [self.Response({"nextPageToken": "same"}), self.Response({"nextPageToken": "same"})]
        )
        with self.assertRaises(collector.CollectorError):
            collector.fetch_candidate_claims(
                "François Ruffin", "secret", opener=lambda *args, **kwargs: next(responses)
            )

    def test_nontransient_http_failure_is_not_empty_evidence(self):
        def opener(*_args, **_kwargs):
            raise HTTPError("url", 404, "not found", {}, None)

        with self.assertRaisesRegex(collector.CollectorError, "HTTP status 404"):
            collector.fetch_candidate_claims("Alice Observée", "secret", opener=opener)


if __name__ == "__main__":
    unittest.main()
