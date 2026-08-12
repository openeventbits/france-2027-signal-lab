"""Phase 3A tests for stable candidate-registry identity and lifecycle."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import fetch_candidate_candidacy_status as collector
from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    active_candidate_ids,
    active_candidate_names,
    active_candidate_records,
    project_active_monitoring_field,
    project_display_tiers,
    semantic_sha256,
    validate_candidate_candidacy_status,
)
from test_fetch_candidate_candidacy_status import fixture_html


def revision(identifier: int = 100, day: int = 1):
    return collector.RevisionSnapshot(
        identifier,
        f"2026-08-{day:02d}T04:05:00Z",
    )


def article(page_id: int, title: str) -> dict:
    return {
        "page_id": page_id,
        "title": title,
        "url": collector._canonical_article_url(title),
    }


def resolver(mapping: dict[str, tuple[int, str]]):
    def resolve(requested_title: str) -> dict:
        page_id, canonical_title = mapping.get(
            requested_title,
            (
                10000 + sum(ord(character) for character in requested_title),
                requested_title,
            ),
        )
        return article(page_id, canonical_title)

    return resolve


def build(
    html: str,
    *,
    previous: dict | None = None,
    rev: collector.RevisionSnapshot | None = None,
    article_mapping: dict[str, tuple[int, str]] | None = None,
) -> dict:
    payload, _ = collector.build_payload(
        rev or revision(),
        html,
        previous_registry=previous,
        article_resolver=(
            resolver(article_mapping) if article_mapping is not None else None
        ),
    )
    return payload


def by_name(payload: dict, name: str) -> dict:
    return next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_name"] == name
    )


class LegacyMigrationTests(unittest.TestCase):
    def test_schema_1_previous_reconciles_directly_to_schema_2(self):
        previous = json.loads(
            (
                Path(__file__).resolve().parent
                / "test_fixtures"
                / "candidate_candidacy_status_dynamic.json"
            ).read_text(encoding="utf-8")
        )
        current = build(
            fixture_html(
                declared_names=("Alice Observée", "Benoît Non Testé"),
                primary_names=(),
                prospective_names=("Chloé Potentielle",),
                withdrawn_names=("David Retiré",),
                declined_names=("Élise Déclinée",),
            ),
            previous=previous,
            rev=revision(101, 2),
        )
        self.assertEqual(previous["schema_version"], "1.0")
        self.assertEqual(current["schema_version"], "2.0")
        self.assertEqual(
            [row["candidate_id"] for row in current["candidates"]],
            [row["candidate_id"] for row in previous["candidates"]],
        )
        self.assertTrue(
            all(row["upstream_presence"] == "present" for row in current["candidates"])
        )
        validate_candidate_candidacy_status(current)


class StableIdentityTests(unittest.TestCase):
    def test_unchanged_candidate_retains_id(self):
        previous = build(fixture_html())
        current = build(fixture_html(), previous=previous, rev=revision(101, 2))
        self.assertEqual(
            by_name(current, "Élodie Déclarée")["candidate_id"],
            by_name(previous, "Élodie Déclarée")["candidate_id"],
        )

    def test_accent_only_name_correction_retains_id_and_history(self):
        previous = build(fixture_html(declared_names=("Elodie Declaree",)))
        current = build(
            fixture_html(declared_names=("Élodie Déclarée",)),
            previous=previous,
            rev=revision(101, 2),
        )
        candidate = by_name(current, "Élodie Déclarée")
        self.assertEqual(candidate["candidate_id"], "elodie-declaree")
        self.assertEqual(candidate["previous_names"], ["Elodie Declaree"])

    def test_display_name_change_with_same_page_id_retains_id(self):
        previous = build(
            fixture_html(declared_names=("Alice Ancienne",)),
            article_mapping={"alice-ancienne": (55, "Alice Ancienne")},
        )
        current = build(
            fixture_html(declared_names=("Alice Nouvelle",)),
            previous=previous,
            rev=revision(101, 2),
            article_mapping={"alice-nouvelle": (55, "Alice Nouvelle")},
        )
        candidate = by_name(current, "Alice Nouvelle")
        self.assertEqual(candidate["candidate_id"], "alice-ancienne")
        self.assertEqual(candidate["previous_names"], ["Alice Ancienne"])

    def test_previous_names_persist_across_later_refreshes(self):
        first = build(
            fixture_html(declared_names=("Alice Ancienne",)),
            article_mapping={"alice-ancienne": (55, "Alice Ancienne")},
        )
        second = build(
            fixture_html(declared_names=("Alice Nouvelle",)),
            previous=first,
            rev=revision(101, 2),
            article_mapping={"alice-nouvelle": (55, "Alice Nouvelle")},
        )
        third = build(
            fixture_html(declared_names=("Alice Finale",)),
            previous=second,
            rev=revision(102, 3),
            article_mapping={"alice-finale": (55, "Alice Finale")},
        )
        self.assertEqual(
            by_name(third, "Alice Finale")["previous_names"],
            ["Alice Ancienne", "Alice Nouvelle"],
        )

    def test_exact_normalized_previous_current_name_retains_id(self):
        previous = build(fixture_html(declared_names=("Élodie Déclarée",)))
        current = build(
            fixture_html(declared_names=("Elodie Declaree",)),
            previous=previous,
            rev=revision(101, 2),
        )
        self.assertEqual(
            by_name(current, "Elodie Declaree")["candidate_id"],
            "elodie-declaree",
        )

    def test_unique_previous_name_alias_retains_id(self):
        first = build(fixture_html(declared_names=("Alice Ancienne",)))
        second = build(
            fixture_html(declared_names=("Alice Actuelle",)),
            previous=first,
            rev=revision(101, 2),
        )
        returned_alias = build(
            fixture_html(declared_names=("Alice Ancienne",)),
            previous=second,
            rev=revision(102, 3),
        )
        self.assertEqual(
            by_name(returned_alias, "Alice Ancienne")["candidate_id"],
            "alice-ancienne",
        )

    def test_conflicting_page_and_name_matches_fail_closed(self):
        previous = build(
            fixture_html(
                declared_names=("Alice Personne", "Béatrice Personne"),
            ),
            article_mapping={
                "alice-personne": (55, "Alice Personne"),
                "beatrice-personne": (56, "Béatrice Personne"),
            },
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "ambiguous previous candidate identity",
        ):
            build(
                fixture_html(declared_names=("Béatrice Personne",)),
                previous=previous,
                rev=revision(101, 2),
                article_mapping={
                    "beatrice-personne": (55, "Alice Personne"),
                },
            )

    def test_new_candidate_gets_existing_style_slug(self):
        payload = build(fixture_html(declared_names=("Élodie Nouvelle",)))
        self.assertEqual(
            by_name(payload, "Élodie Nouvelle")["candidate_id"],
            "elodie-nouvelle",
        )

    def test_v2_validator_accepts_stable_id_not_derived_from_name(self):
        payload = build(fixture_html())
        payload["candidates"][0]["candidate_id"] = "persistent-identity"
        payload["candidates"].sort(
            key=lambda candidate: (
                candidate["candidate_name"].casefold(),
                candidate["candidate_id"],
            )
        )
        validate_candidate_candidacy_status(payload)

    def test_duplicate_candidate_ids_reject(self):
        payload = build(fixture_html())
        payload["candidates"][1]["candidate_id"] = payload["candidates"][0][
            "candidate_id"
        ]
        with self.assertRaisesRegex(
            CandidateCandidacyStatusError,
            "duplicate candidate ID",
        ):
            validate_candidate_candidacy_status(payload)


class ArticleIdentityTests(unittest.TestCase):
    def test_linked_article_resolves_page_id_and_canonical_url(self):
        response = {
            "query": {
                "redirects": [
                    {"from": "Olivier Faure", "to": "Olivier Faure (homme politique)"}
                ],
                "pages": [
                    {
                        "pageid": 4242,
                        "ns": 0,
                        "title": "Olivier Faure (homme politique)",
                    }
                ],
            }
        }
        resolved = collector.resolve_wikipedia_article(
            "Olivier Faure",
            lambda _params: response,
        )
        self.assertEqual(resolved["page_id"], 4242)
        self.assertEqual(resolved["title"], "Olivier Faure (homme politique)")
        self.assertEqual(
            resolved["url"],
            "https://fr.wikipedia.org/wiki/Olivier_Faure_(homme_politique)",
        )

    def test_candidate_without_personal_article_is_null_and_valid(self):
        payload = build(fixture_html())
        candidate = by_name(payload, "Zoë Sans Article")
        self.assertIsNone(candidate["wikipedia_article"])
        validate_candidate_candidacy_status(payload)

    def test_malformed_article_resolution_fails_safely(self):
        for malformed in ({}, {"query": {}}, {"query": {"pages": []}}):
            with self.subTest(malformed=malformed):
                with self.assertRaises(
                    collector.CandidateCandidacyFetchError
                ):
                    collector.resolve_wikipedia_article(
                        "Alice Personne",
                        lambda _params, value=malformed: value,
                    )

    def test_article_page_id_participates_in_reconciliation(self):
        previous = build(
            fixture_html(declared_names=("Nom Ancien",)),
            article_mapping={"nom-ancien": (77, "Nom Ancien")},
        )
        current = build(
            fixture_html(declared_names=("Nom Entièrement Nouveau",)),
            previous=previous,
            rev=revision(101, 2),
            article_mapping={
                "nom-entierement-nouveau": (77, "Nom Entièrement Nouveau")
            },
        )
        self.assertEqual(
            by_name(current, "Nom Entièrement Nouveau")["candidate_id"],
            "nom-ancien",
        )


class LifecycleTests(unittest.TestCase):
    def test_present_candidate_remains_present(self):
        previous = build(fixture_html())
        current = build(fixture_html(), previous=previous, rev=revision(101, 2))
        self.assertEqual(
            by_name(current, "Élodie Déclarée")["upstream_presence"],
            "present",
        )

    def test_one_missing_candidate_is_retained_without_status_invention(self):
        previous = build(fixture_html())
        prior = by_name(previous, "Élodie Déclarée")
        current = build(
            fixture_html(declared_names=()),
            previous=previous,
            rev=revision(101, 2),
        )
        missing = by_name(current, "Élodie Déclarée")
        self.assertEqual(missing["candidate_id"], prior["candidate_id"])
        self.assertEqual(missing["status"], prior["status"])
        self.assertEqual(missing["display_tier"], prior["display_tier"])
        self.assertEqual(missing["upstream_presence"], "temporarily_missing")
        self.assertNotIn(missing["candidate_id"], active_candidate_ids(current))
        self.assertNotIn(
            missing["candidate_id"],
            project_display_tiers(current)["hidden"],
        )
        self.assertIn(
            missing["candidate_id"],
            project_display_tiers(current)["main"],
        )
        self.assertNotIn(
            missing["candidate_id"],
            project_active_monitoring_field(current)["main"],
        )
        self.assertEqual(len(current["candidates"]), len(previous["candidates"]))

    def test_candidate_returning_upstream_becomes_present_again(self):
        first = build(fixture_html())
        missing = build(
            fixture_html(declared_names=()),
            previous=first,
            rev=revision(101, 2),
        )
        returned = build(
            fixture_html(),
            previous=missing,
            rev=revision(102, 3),
        )
        candidate = by_name(returned, "Élodie Déclarée")
        self.assertEqual(candidate["upstream_presence"], "present")
        self.assertIn(candidate["candidate_id"], active_candidate_ids(returned))

    def test_explicit_withdrawal_preserves_identity_and_history(self):
        previous = build(fixture_html(declared_names=("Alice Candidate",)))
        current = build(
            fixture_html(
                declared_names=(),
                withdrawn_names=("Alice Candidate", "Clément Retiré"),
            ),
            previous=previous,
            rev=revision(101, 2),
        )
        candidate = by_name(current, "Alice Candidate")
        self.assertEqual(candidate["candidate_id"], "alice-candidate")
        self.assertEqual(candidate["status"], "withdrawn")
        self.assertEqual(candidate["display_tier"], "hidden")
        self.assertEqual(candidate["upstream_presence"], "present")

    def test_explicit_ruled_out_preserves_identity(self):
        previous = build(fixture_html(declared_names=("Alice Candidate",)))
        current = build(
            fixture_html(
                declared_names=(),
                declined_names=("Alice Candidate", "Agnès Déclinée"),
            ),
            previous=previous,
            rev=revision(101, 2),
        )
        candidate = by_name(current, "Alice Candidate")
        self.assertEqual(candidate["candidate_id"], "alice-candidate")
        self.assertEqual(candidate["status"], "ruled_out")
        self.assertEqual(candidate["upstream_presence"], "present")

    def test_active_projection_helpers_preserve_registry_order(self):
        payload = build(fixture_html())
        records = active_candidate_records(payload)
        self.assertEqual(
            active_candidate_ids(payload),
            [candidate["candidate_id"] for candidate in records],
        )
        self.assertEqual(
            active_candidate_names(payload),
            [candidate["candidate_name"] for candidate in records],
        )


class AnomalyGuardTests(unittest.TestCase):
    def test_empty_raw_extraction_fails(self):
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "no candidates|raw candidate extraction is empty",
        ):
            build(
                fixture_html(
                    declared_names=(),
                    primary_names=(),
                    prospective_names=(),
                    withdrawn_names=(),
                    declined_names=(),
                )
            )

    def test_catastrophic_total_shrink_fails(self):
        previous = build(
            fixture_html(
                withdrawn_names=("Hidden One", "Hidden Two", "Hidden Three", "Hidden Four"),
            )
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "catastrophic|unexpectedly became empty",
        ):
            build(
                fixture_html(withdrawn_names=("Hidden One",)),
                previous=previous,
                rev=revision(101, 2),
            )

    def test_catastrophic_active_shrink_fails(self):
        active_names = tuple(f"Active Candidate {index}" for index in range(1, 13))
        previous = build(fixture_html(declared_names=active_names))
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "active-candidate disappearance",
        ):
            build(
                fixture_html(declared_names=active_names[:-2]),
                previous=previous,
                rev=revision(101, 2),
            )

    def test_unexpectedly_emptied_populated_section_fails(self):
        previous = build(
            fixture_html(withdrawn_names=("Hidden One", "Hidden Two"))
        )
        with self.assertRaisesRegex(
            collector.CandidateCandidacyFetchError,
            "section unexpectedly became empty",
        ):
            build(
                fixture_html(withdrawn_names=()),
                previous=previous,
                rev=revision(101, 2),
            )

    def test_one_person_unexplained_absence_is_allowed(self):
        previous = build(fixture_html())
        current = build(
            fixture_html(declared_names=()),
            previous=previous,
            rev=revision(101, 2),
        )
        self.assertEqual(
            by_name(current, "Élodie Déclarée")["upstream_presence"],
            "temporarily_missing",
        )

    def test_already_missing_identity_is_not_counted_as_a_fresh_loss(self):
        initial = build(
            fixture_html(declared_names=("Alice One", "Alice Two"))
        )
        one_missing = build(
            fixture_html(declared_names=("Alice Two",)),
            previous=initial,
            rev=revision(101, 2),
        )
        two_missing = build(
            fixture_html(declared_names=()),
            previous=one_missing,
            rev=revision(102, 3),
        )
        self.assertEqual(
            {
                by_name(two_missing, "Alice One")["upstream_presence"],
                by_name(two_missing, "Alice Two")["upstream_presence"],
            },
            {"temporarily_missing"},
        )

    def test_explicit_withdrawal_and_decline_are_not_disappearances(self):
        previous = build(
            fixture_html(declared_names=("Alice One", "Alice Two"))
        )
        current = build(
            fixture_html(
                declared_names=(),
                withdrawn_names=("Alice One", "Clément Retiré"),
                declined_names=("Alice Two", "Agnès Déclinée"),
            ),
            previous=previous,
            rev=revision(101, 2),
        )
        self.assertEqual(by_name(current, "Alice One")["status"], "withdrawn")
        self.assertEqual(by_name(current, "Alice Two")["status"], "ruled_out")


class SemanticHashTests(unittest.TestCase):
    def test_revision_only_change_has_identical_semantic_hash(self):
        previous = build(fixture_html(), rev=revision(100, 1))
        current = build(
            fixture_html(),
            previous=previous,
            rev=revision(101, 2),
        )
        self.assertNotEqual(previous["source"], current["source"])
        self.assertEqual(semantic_sha256(previous), semantic_sha256(current))

    def test_status_and_tier_change_semantic_hash(self):
        previous = build(fixture_html(declared_names=("Alice Candidate",)))
        withdrawn = build(
            fixture_html(
                declared_names=(),
                withdrawn_names=("Alice Candidate", "Clément Retiré"),
            ),
            previous=previous,
            rev=revision(101, 2),
        )
        self.assertNotEqual(semantic_sha256(previous), semantic_sha256(withdrawn))

    def test_name_change_changes_hash_but_not_id(self):
        previous = build(
            fixture_html(declared_names=("Alice Ancienne",)),
            article_mapping={"alice-ancienne": (55, "Alice Ancienne")},
        )
        current = build(
            fixture_html(declared_names=("Alice Nouvelle",)),
            previous=previous,
            rev=revision(101, 2),
            article_mapping={"alice-nouvelle": (55, "Alice Nouvelle")},
        )
        self.assertEqual(
            by_name(previous, "Alice Ancienne")["candidate_id"],
            by_name(current, "Alice Nouvelle")["candidate_id"],
        )
        self.assertNotEqual(semantic_sha256(previous), semantic_sha256(current))

    def test_article_page_identity_change_changes_hash(self):
        previous = build(
            fixture_html(declared_names=("Alice Candidate",)),
            article_mapping={"alice-candidate": (55, "Alice Candidate")},
        )
        current = build(
            fixture_html(declared_names=("Alice Candidate",)),
            previous=previous,
            rev=revision(101, 2),
            article_mapping={"alice-candidate": (56, "Alice Candidate")},
        )
        self.assertNotEqual(semantic_sha256(previous), semantic_sha256(current))

    def test_previous_names_change_changes_hash(self):
        payload = build(fixture_html())
        changed = copy.deepcopy(payload)
        candidate = changed["candidates"][0]
        candidate["previous_names"] = ["A Former Name"]
        validate_candidate_candidacy_status(changed)
        self.assertNotEqual(semantic_sha256(payload), semantic_sha256(changed))

    def test_incidental_extraction_order_does_not_change_hash(self):
        first = build(fixture_html(declared_names=("Alpha One", "Beta Two")))
        second = build(fixture_html(declared_names=("Beta Two", "Alpha One")))
        self.assertEqual(semantic_sha256(first), semantic_sha256(second))


if __name__ == "__main__":
    unittest.main()
