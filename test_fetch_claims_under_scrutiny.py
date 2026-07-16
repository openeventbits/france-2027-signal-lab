import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import fetch_claims_under_scrutiny as collector


AS_OF = date(2026, 7, 16)


def poll_event(
    *,
    publication_date="2026-07-10",
    fieldwork_end="2026-07-09",
    round_name="first_round",
    candidates=None,
):
    return {
        "publication_date": publication_date,
        "fieldwork_end": fieldwork_end,
        "round": round_name,
        "candidates": candidates
        if candidates is not None
        else [{"name": "François Ruffin", "score": 7.5}],
    }


def roster(*names):
    return [
        {
            "candidate_id": collector.candidate_slug(name),
            "candidate_name": name,
            "last_qualifying_poll_date": "2026-07-10",
            "eligibility_basis": "publication_date",
        }
        for name in names
    ]


def api_claim(
    *,
    url="https://factuel.afp.com/politique/article?utm_source=x&id=7",
    claim_text="François Ruffin a fait cette déclaration",
    claimant="François Ruffin",
    review_date="2026-07-10T12:30:00Z",
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


class CandidateRosterTests(unittest.TestCase):
    def test_publication_date_is_used_when_available(self):
        result = collector.build_candidate_roster([poll_event()], AS_OF, 45)
        self.assertEqual(result[0]["last_qualifying_poll_date"], "2026-07-10")
        self.assertEqual(result[0]["eligibility_basis"], "publication_date")

    def test_fieldwork_end_is_used_only_when_publication_date_unavailable(self):
        result = collector.build_candidate_roster(
            [poll_event(publication_date=None, fieldwork_end="2026-07-09")], AS_OF, 45
        )
        self.assertEqual(result[0]["last_qualifying_poll_date"], "2026-07-09")
        self.assertEqual(result[0]["eligibility_basis"], "fieldwork_end")

    def test_invalid_publication_date_falls_back_to_fieldwork_end(self):
        result = collector.build_candidate_roster(
            [poll_event(publication_date="not-a-date", fieldwork_end="2026-07-08")],
            AS_OF,
            45,
        )
        self.assertEqual(result[0]["eligibility_basis"], "fieldwork_end")

    def test_day_45_is_eligible(self):
        result = collector.build_candidate_roster(
            [poll_event(publication_date="2026-06-01")], AS_OF, 45
        )
        self.assertEqual(len(result), 1)

    def test_day_46_is_ineligible(self):
        result = collector.build_candidate_roster(
            [poll_event(publication_date="2026-05-31")], AS_OF, 45
        )
        self.assertEqual(result, [])

    def test_second_round_event_is_ignored(self):
        result = collector.build_candidate_roster(
            [poll_event(round_name="second_round")], AS_OF, 45
        )
        self.assertEqual(result, [])

    def test_missing_or_nonnumeric_score_is_ignored(self):
        candidates = [
            {"name": "Missing"},
            {"name": "String", "score": "8"},
            {"name": "Boolean", "score": True},
            {"name": "Infinite", "score": float("inf")},
            {"name": "Valid", "score": 0},
        ]
        result = collector.build_candidate_roster(
            [poll_event(candidates=candidates)], AS_OF, 45
        )
        self.assertEqual([item["candidate_name"] for item in result], ["Valid"])

    def test_absent_candidates_are_never_synthesized(self):
        result = collector.build_candidate_roster(
            [poll_event(candidates=[{"name": "Marine Le Pen", "score": 34}])],
            AS_OF,
            45,
        )
        self.assertEqual([item["candidate_name"] for item in result], ["Marine Le Pen"])

    def test_valid_empty_roster_succeeds_without_api_key(self):
        writes = []
        with (
            mock.patch.object(collector, "load_polls", return_value=[]),
            mock.patch.object(
                collector,
                "atomic_write_json",
                side_effect=lambda path, payload: writes.append((path, payload)),
            ),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
                bundle = collector.collect(
                    Path("polls.json"),
                    Path("output.json"),
                    Path("diagnostics.json"),
                    45,
                    365,
                    AS_OF,
                    "2026-07-16",
                )
        self.assertEqual(bundle["candidate_roster"]["count"], 0)
        self.assertEqual(bundle["reviews"], [])
        self.assertEqual(
            [path for path, _payload in writes],
            [Path("diagnostics.json"), Path("output.json")],
        )

    def test_accented_candidate_slug_generation(self):
        self.assertEqual(collector.candidate_slug("François Ruffin"), "francois-ruffin")
        self.assertEqual(collector.candidate_slug("Édouard Philippe"), "edouard-philippe")

    def test_latest_date_tie_prefers_publication_date(self):
        events = [
            poll_event(publication_date=None, fieldwork_end="2026-07-10"),
            poll_event(publication_date="2026-07-10", fieldwork_end="2026-07-08"),
        ]
        result = collector.build_candidate_roster(events, AS_OF, 45)
        self.assertEqual(result[0]["eligibility_basis"], "publication_date")


class RelationshipTests(unittest.TestCase):
    def test_canonical_claimant_produces_by(self):
        associations, unresolved = collector.classify_candidate_associations(
            "Un autre texte", "François Ruffin", roster("François Ruffin")
        )
        self.assertEqual(associations[0]["relationship"], "by")
        self.assertEqual(unresolved, [])

    def test_exact_approved_ruffin_alias_produces_by(self):
        associations, _ = collector.classify_candidate_associations(
            "Un autre texte",
            "Le député François Ruffin",
            roster("François Ruffin"),
        )
        self.assertEqual(associations[0]["relationship"], "by")

    def test_candidate_collective_claimant_is_unresolved_not_about(self):
        associations, unresolved = collector.classify_candidate_associations(
            "François Ruffin aurait annoncé sa candidature",
            "François Ruffin et ses soutiens",
            roster("François Ruffin"),
        )
        self.assertEqual(associations, [])
        self.assertEqual(unresolved[0]["reason"], "relationship_unresolved")

    def test_candidate_title_wrapper_is_unresolved_not_about(self):
        associations, unresolved = collector.classify_candidate_associations(
            "François Ruffin aurait annoncé sa candidature",
            "Le candidat François Ruffin",
            roster("François Ruffin"),
        )
        self.assertEqual(associations, [])
        self.assertEqual(unresolved[0]["reason"], "relationship_unresolved")

    def test_different_usable_claimant_and_complete_name_produces_about(self):
        associations, _ = collector.classify_candidate_associations(
            "Une affirmation sur François Ruffin.",
            "Boris Vallaud",
            roster("François Ruffin"),
        )
        self.assertEqual(associations[0]["relationship"], "about")

    def test_missing_claimant_produces_unresolved_not_about(self):
        associations, unresolved = collector.classify_candidate_associations(
            "François Ruffin aurait annoncé sa candidature", "", roster("François Ruffin")
        )
        self.assertEqual(associations, [])
        self.assertEqual(unresolved[0]["reason"], "relationship_unresolved")

    def test_ambiguous_placeholder_produces_unresolved(self):
        for placeholder in ("unknown", "Non indiqué", "ANONYME"):
            with self.subTest(placeholder=placeholder):
                associations, unresolved = collector.classify_candidate_associations(
                    "François Ruffin aurait annoncé sa candidature",
                    placeholder,
                    roster("François Ruffin"),
                )
                self.assertEqual(associations, [])
                self.assertEqual(len(unresolved), 1)

    def test_same_candidate_is_not_both_by_and_about(self):
        associations, _ = collector.classify_candidate_associations(
            "François Ruffin parle de son programme",
            "François Ruffin",
            roster("François Ruffin"),
        )
        self.assertEqual([item["relationship"] for item in associations], ["by"])

    def test_mixed_attal_by_and_le_pen_about_is_one_review(self):
        candidates = roster("Gabriel Attal", "Marine Le Pen")
        result = collector.flatten_claims(
            [
                api_claim(
                    claimant="Gabriel Attal",
                    claim_text="Gabriel Attal affirme que Marine Le Pen a voté ce texte",
                )
            ],
            candidates,
            AS_OF,
            365,
            diagnostics(),
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(
            [(item["candidate_name"], item["relationship"]) for item in result[0]["candidate_associations"]],
            [("Gabriel Attal", "by"), ("Marine Le Pen", "about")],
        )

    def test_surname_only_claim_text_does_not_produce_about(self):
        associations, _ = collector.classify_candidate_associations(
            "Ruffin aurait annoncé sa candidature",
            "Un internaute",
            roster("François Ruffin"),
        )
        self.assertEqual(associations, [])


class ReviewProcessingTests(unittest.TestCase):
    def test_url_normalization_removes_tracking_parameters(self):
        normalized, host = collector.normalize_review_url(
            "HTTPS://FACTUEL.AFP.COM:443/article?utm_source=x&b=2&fbclid=z&a=1#part"
        )
        self.assertEqual(normalized, "https://factuel.afp.com/article?a=1&b=2")
        self.assertEqual(host, "factuel.afp.com")

    def test_tf1_bare_and_www_urls_normalize_identically(self):
        bare = collector.normalize_review_url("https://tf1info.fr/politique/article")
        www = collector.normalize_review_url("https://www.tf1info.fr/politique/article")
        self.assertEqual(bare, www)
        self.assertEqual(bare[1], "www.tf1info.fr")

    def test_franceinfo_bare_and_www_urls_normalize_identically(self):
        bare = collector.normalize_review_url("https://franceinfo.fr/replay-radio/article")
        www = collector.normalize_review_url("https://www.franceinfo.fr/replay-radio/article")
        self.assertEqual(bare, www)
        self.assertEqual(bare[1], "www.franceinfo.fr")

    def test_bare_and_www_review_instances_merge_with_one_publisher(self):
        bare = api_claim(url="https://tf1info.fr/politique/article")
        www = api_claim(url="https://www.tf1info.fr/politique/article")
        reviews = collector.flatten_claims(
            [bare, www], roster("François Ruffin"), AS_OF, 365, diagnostics()
        )
        bundle = collector.build_public_bundle(
            roster("François Ruffin"), reviews, AS_OF, 45, 365
        )
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["publisher_host"], "www.tf1info.fr")
        self.assertEqual(bundle["counts"]["publishers"], 1)

    def test_unknown_publisher_subdomain_is_excluded(self):
        diagnostic = diagnostics()
        result = collector.flatten_claims(
            [api_claim(url="https://factcheck.tf1info.fr/article")],
            roster("François Ruffin"),
            AS_OF,
            365,
            diagnostic,
        )
        self.assertEqual(result, [])
        self.assertEqual(
            diagnostic["excluded_unknown_hosts"][0]["host"],
            "factcheck.tf1info.fr",
        )

    def test_duplicate_url_associations_merge(self):
        duplicate = api_claim(url="https://factuel.afp.com/item?utm_medium=social")
        result = collector.flatten_claims(
            [duplicate, json.loads(json.dumps(duplicate))],
            roster("François Ruffin"),
            AS_OF,
            365,
            diagnostics(),
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["candidate_associations"]), 1)

    def test_conflicting_duplicate_core_fields_fail(self):
        first = api_claim(url="https://factuel.afp.com/item", rating="Faux")
        second = api_claim(url="https://factuel.afp.com/item#fragment", rating="Vrai")
        with self.assertRaises(collector.CollectorError):
            collector.flatten_claims(
                [first, second], roster("François Ruffin"), AS_OF, 365, diagnostics()
            )

    def test_365_day_boundary_is_retained(self):
        result = collector.flatten_claims(
            [api_claim(review_date="2025-07-16")],
            roster("François Ruffin"),
            AS_OF,
            365,
            diagnostics(),
        )
        self.assertEqual(len(result), 1)

    def test_366_day_old_review_is_excluded(self):
        result = collector.flatten_claims(
            [api_claim(review_date="2025-07-15")],
            roster("François Ruffin"),
            AS_OF,
            365,
            diagnostics(),
        )
        self.assertEqual(result, [])

    def test_unknown_host_is_excluded_by_hostname_not_display_name(self):
        diagnostic = diagnostics()
        result = collector.flatten_claims(
            [api_claim(url="https://example.com/fact-check")],
            roster("François Ruffin"),
            AS_OF,
            365,
            diagnostic,
        )
        self.assertEqual(result, [])
        self.assertEqual(diagnostic["excluded_unknown_hosts"][0]["host"], "example.com")

    def test_missing_claimant_is_diagnostic_unresolved_and_not_public(self):
        diagnostic = diagnostics()
        result = collector.flatten_claims(
            [api_claim(claimant="", claim_text="François Ruffin a annoncé ceci")],
            roster("François Ruffin"),
            AS_OF,
            365,
            diagnostic,
        )
        self.assertEqual(result, [])
        self.assertEqual(len(diagnostic["unresolved_associations"]), 1)

    def test_counts_match_records_and_associations(self):
        reviews = collector.flatten_claims(
            [
                api_claim(
                    claimant="Gabriel Attal",
                    claim_text="Gabriel Attal évoque Marine Le Pen",
                )
            ],
            roster("Gabriel Attal", "Marine Le Pen"),
            AS_OF,
            365,
            diagnostics(),
        )
        counts = collector.compute_counts(reviews)
        self.assertEqual(
            counts,
            {
                "reviews": 1,
                "by_associations": 1,
                "about_associations": 1,
                "candidates_covered": 2,
                "publishers": 1,
            },
        )

    def test_valid_bundle_passes_strict_validation(self):
        candidates = roster("François Ruffin")
        reviews = collector.flatten_claims(
            [api_claim()], candidates, AS_OF, 365, diagnostics()
        )
        bundle = collector.build_public_bundle(
            candidates, reviews, 45, 365, "2026-07-16T00:00:00Z"
        )
        collector.validate_public_bundle(bundle)


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
            [
                self.Response({"nextPageToken": "same"}),
                self.Response({"nextPageToken": "same"}),
            ]
        )
        with self.assertRaises(collector.CollectorError):
            collector.fetch_candidate_claims(
                "François Ruffin", "secret", opener=lambda *args, **kwargs: next(responses)
            )


if __name__ == "__main__":
    unittest.main()
