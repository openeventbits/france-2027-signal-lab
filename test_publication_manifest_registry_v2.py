import json
import unittest
from pathlib import Path
from unittest.mock import patch

import build_candidate_signals as signals
import build_publication_manifest as manifest
import fetch_news_wire
from fetch_claims_under_scrutiny import build_public_bundle, stable_review_id
from test_build_candidate_signals import news_fixture, poll_event
from test_candidate_active_monitoring_phase3a1 import registry_v2
from test_candidate_attention_registry_v2 import build_payload
from test_candidate_registry_v2 import build as build_registry, revision
from test_fetch_candidate_candidacy_status import fixture_html


ROOT = Path(__file__).resolve().parent
DYNAMIC_REGISTRY = ROOT / "test_fixtures" / "candidate_candidacy_status_dynamic.json"


def bundle():
    registry = registry_v2(DYNAMIC_REGISTRY, "benoit-non-teste")
    active_names = [
        row["candidate_name"]
        for row in manifest.active_candidate_records(registry)
    ]
    news = news_fixture(
        primary_metrics=[],
        general_metrics=[],
        candidate_watch=[],
        roster_names=active_names,
    )
    news["candidate_roster"] = fetch_news_wire.candidate_roster_metadata(
        registry
    )
    news["policy_agenda"] = {
        "window_days": 30,
        "evolution": {
            "period_start": "2026-06-30",
            "period_end": "2026-07-29",
        },
        "topics": [
            {
                "id": definition["id"],
                "candidate_counts": [],
            }
            for definition in fetch_news_wire.POLICY_AGENDA_TOPICS
        ],
    }
    news["relevant_news"] = []
    polls = [poll_event(candidates=[("Alice Observée", 60), ("Poll Only Person", 40)])]
    claims = build_public_bundle(registry, [], 365, "2026-08-07T05:00:00Z")
    candidate_signals = signals.build_candidate_signals(polls, news, claims, registry)
    return registry, news, claims, candidate_signals


class PublicationManifestRegistryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.news, cls.claims, cls.signals = bundle()

    def test_signals_15_complete_and_active_projections_reconcile(self):
        self.assertEqual(self.signals["schema_version"], "1.5")
        manifest._validate_candidate_signals_public(self.signals)
        manifest._validate_candidacy_status_parity(self.registry, self.signals)
        self.assertEqual(len(self.signals["candidates"]), 5)
        self.assertEqual(self.signals["active_monitoring_field"]["counts"]["active"], 2)

    def advanced_registry(self):
        return build_registry(
            fixture_html(
                declared_names=("Alice Observée", "Benoît Non Testé"),
                primary_names=(),
                prospective_names=("Chloé Potentielle",),
                withdrawn_names=("David Retiré",),
                declined_names=("Élise Déclinée",),
            ),
            previous=self.registry,
            rev=revision(2, 2),
        )

    def same_day_advanced_registry(
        self,
        *,
        revision_id=2,
        revision_timestamp="2026-08-01T19:27:07Z",
    ):
        advanced = build_registry(
            fixture_html(
                declared_names=("Alice Observée", "Benoît Non Testé"),
                primary_names=(),
                prospective_names=("Chloé Potentielle",),
                withdrawn_names=("David Retiré",),
                declined_names=("Élise Déclinée",),
            ),
            previous=self.registry,
            rev=revision(revision_id, 1),
        )
        advanced["source"]["revision_timestamp"] = revision_timestamp
        return advanced

    def test_older_attention_11_projection_is_valid_downstream_lag(self):
        attention = build_payload(self.registry)
        manifest._validate_candidate_attention_parity(
            self.advanced_registry(), attention
        )

    def test_same_day_older_attention_projection_is_valid_downstream_lag(self):
        attention = build_payload(self.registry)
        advanced = self.same_day_advanced_registry()
        manifest._validate_candidate_attention_parity(
            advanced, attention
        )

    def test_same_day_current_attention_snapshot_requires_exact_parity(self):
        attention = build_payload(self.registry)
        advanced = self.same_day_advanced_registry()
        attention["candidate_universe"]["source_revision_id"] = (
            advanced["source"]["revision_id"]
        )
        attention["candidate_universe"]["source_revision_timestamp"] = (
            advanced["source"]["revision_timestamp"]
        )
        with self.assertRaisesRegex(manifest.ManifestError, "candidacy parity"):
            manifest._validate_candidate_attention_parity(
                advanced, attention
            )

    def test_same_day_older_claims_query_is_valid_downstream_lag(self):
        claims = json.loads(json.dumps(self.claims))
        advanced = self.same_day_advanced_registry()
        self.assertEqual(
            manifest._validate_claims_public(claims, advanced),
            0,
        )

    def test_same_day_current_claims_query_requires_exact_parity(self):
        claims = json.loads(json.dumps(self.claims))
        advanced = self.same_day_advanced_registry()
        claims["candidate_query"]["source_revision_id"] = (
            advanced["source"]["revision_id"]
        )
        claims["candidate_query"]["source_revision_timestamp"] = (
            advanced["source"]["revision_timestamp"]
        )
        with self.assertRaisesRegex(manifest.ManifestError, "active registry"):
            manifest._validate_claims_public(claims, advanced)

    def test_real_claims_transition_accepts_old_snapshot_after_new_revision(self):
        claims = json.loads(json.dumps(self.claims))
        claims["generated_at"] = "2026-08-25T08:24:26Z"
        claims["candidate_query"]["status_as_of"] = "2026-08-24"
        claims["candidate_query"]["source_revision_id"] = 238893112
        claims["candidate_query"]["source_revision_timestamp"] = (
            "2026-08-24T00:07:22Z"
        )
        advanced = self.same_day_advanced_registry(
            revision_id=238917344,
            revision_timestamp="2026-08-24T19:27:07Z",
        )
        advanced["status_as_of"] = "2026-08-24"

        self.assertEqual(
            manifest._validate_claims_public(claims, advanced),
            0,
        )

    def test_generated_at_does_not_change_older_claims_reconciliation(self):
        advanced = self.same_day_advanced_registry()
        for generated_at in (
            "2026-08-01T03:00:00Z",
            "2026-08-02T08:24:26Z",
        ):
            with self.subTest(generated_at=generated_at):
                claims = json.loads(json.dumps(self.claims))
                claims["generated_at"] = generated_at
                self.assertEqual(
                    manifest._validate_claims_public(claims, advanced),
                    0,
                )

    def test_older_claims_2_query_is_valid_downstream_lag(self):
        self.assertEqual(
            manifest._validate_claims_public(
                self.claims, self.advanced_registry()
            ),
            0,
        )

    def test_older_news_roster_is_valid_downstream_lag(self):
        manifest._validate_news_active_parity(
            self.advanced_registry(), self.news
        )

    def test_attention_11_uses_active_not_complete_parity(self):
        attention = build_payload(self.registry)
        manifest._validate_candidate_attention_public(attention)
        manifest._validate_candidate_attention_parity(self.registry, attention)
        self.assertEqual(attention["schema_version"], "1.1")
        self.assertEqual(len(attention["candidates"]), 2)
        self.assertEqual(attention["validation"]["unavailable_candidate_count"], 2)

    def test_claims_2_query_parity_does_not_require_evidence_parity(self):
        self.assertEqual(self.claims["schema_version"], 2)
        self.assertEqual(self.claims["reviews"], [])
        self.assertEqual(manifest._validate_claims_public(self.claims, self.registry), 0)
        self.assertEqual(self.claims["candidate_query"]["count"], 2)

    def test_claims_historical_hidden_evidence_remains_valid(self):
        review_url = "https://factuel.afp.com/historical-hidden"
        review = {
            "id": stable_review_id(review_url),
            "review_url": review_url,
            "publisher_name": "AFP Factuel",
            "publisher_host": "factuel.afp.com",
            "review_date": "2026-08-06",
            "claim_text": "Historical claim involving David Retiré",
            "claimant": "David Retiré",
            "rating": "Faux",
            "language": "fr",
            "candidate_associations": [{
                "candidate_id": "david-retire",
                "candidate_name": "David Retiré",
                "relationship": "by",
            }],
        }
        claims = build_public_bundle(
            self.registry, [review], 365, "2026-08-07T05:00:00Z"
        )
        self.assertEqual(manifest._validate_claims_public(claims, self.registry), 1)
        self.assertNotIn(
            "david-retire", claims["candidate_query"]["candidate_ids"]
        )

    def test_claims_2_lane_exposes_query_metadata(self):
        source = {
            "available": True,
            "byte_size": 1,
            "sha256": "0" * 64,
            "payload": self.claims,
            "error": None,
        }
        with patch.object(manifest, "_read_source", return_value=source):
            lane, _sources = manifest._build_lane(Path("fixture"), "claims")
        self.assertEqual(lane["candidate_query_source"], "candidate_candidacy_status.json")
        self.assertEqual(lane["candidate_query_rule"], "active_monitoring_field")
        self.assertEqual(lane["candidate_query_count"], 2)

    def test_fresh_news_active_roster_parity(self):
        manifest._validate_news_active_parity(self.registry, self.news)
        self.assertEqual(
            self.news["candidate_roster"]["rule"],
            "active_monitoring_field",
        )
        self.assertEqual(
            self.news["candidate_roster"]["names"],
            manifest.active_candidate_names(self.registry),
        )

    def test_same_day_older_news_registry_snapshot_is_valid_downstream_lag(self):
        news = json.loads(json.dumps(self.news))
        advanced = self.same_day_advanced_registry()

        manifest._validate_news_active_parity(advanced, news)

    def test_same_day_news_current_snapshot_still_requires_exact_parity(self):
        news = json.loads(json.dumps(self.news))
        news["candidate_roster"]["names"] = ["Alice Observée"]
        news["candidate_roster"]["count"] = 1

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "active registry",
        ):
            manifest._validate_news_active_parity(self.registry, news)

    def test_same_date_news_roster_mutations_remain_strictly_rejected(self):
        mutations = {}

        wrong_rule = json.loads(json.dumps(self.news))
        wrong_rule["candidate_roster"]["rule"] = "descriptive prose"
        mutations["wrong rule token"] = wrong_rule

        wrong_count = json.loads(json.dumps(self.news))
        wrong_count["candidate_roster"]["count"] += 1
        mutations["wrong candidate count"] = wrong_count

        wrong_names = json.loads(json.dumps(self.news))
        wrong_names["candidate_roster"]["names"].reverse()
        mutations["wrong candidate names"] = wrong_names

        stale_membership = json.loads(json.dumps(self.news))
        stale_membership["candidate_roster"]["names"] = ["Alice Observée"]
        stale_membership["candidate_roster"]["count"] = 1
        mutations["stale same-date membership"] = stale_membership

        for label, changed in mutations.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    manifest.ManifestError,
                    "active registry",
                ):
                    manifest._validate_news_active_parity(
                        self.registry,
                        changed,
                    )

    def test_revision_provenance_ordering_fails_closed(self):
        cases = {
            "same id with different timestamp": (
                2,
                "2026-08-01T03:05:00Z",
                "identity is inconsistent",
            ),
            "lower id with later timestamp": (
                1,
                "2026-08-01T20:27:07Z",
                "identity is inconsistent",
            ),
            "higher id with earlier timestamp": (
                3,
                "2026-08-01T03:05:00Z",
                "identity is inconsistent",
            ),
            "newer id with newer timestamp": (
                3,
                "2026-08-01T20:27:07Z",
                "newer than the registry",
            ),
        }
        registry = self.same_day_advanced_registry()
        for label, (revision_id, revision_timestamp, message) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(manifest.ManifestError, message):
                    manifest._projection_predates_registry_snapshot(
                        "2026-08-01",
                        registry,
                        source_revision_id=revision_id,
                        source_revision_timestamp=revision_timestamp,
                    )

    def test_revision_provenance_structure_fails_closed(self):
        cases = {
            "missing id": (None, "2026-08-01T04:05:00Z", "include both"),
            "missing timestamp": (1, None, "include both"),
            "both missing": (None, None, "is required"),
            "string id": ("1", "2026-08-01T04:05:00Z", "positive integer"),
            "boolean id": (True, "2026-08-01T04:05:00Z", "positive integer"),
            "zero id": (0, "2026-08-01T04:05:00Z", "positive integer"),
            "negative id": (-1, "2026-08-01T04:05:00Z", "positive integer"),
            "malformed timestamp": (1, "not-a-timestamp", "UTC ISO-8601"),
            "non-UTC timestamp": (1, "2026-08-01T05:05:00+01:00", "UTC offset"),
        }
        registry = self.same_day_advanced_registry()
        for label, (revision_id, revision_timestamp, message) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(manifest.ManifestError, message):
                    manifest._projection_predates_registry_snapshot(
                        "2026-08-01",
                        registry,
                        source_revision_id=revision_id,
                        source_revision_timestamp=revision_timestamp,
                    )

    def test_older_revision_cannot_claim_newer_status_date(self):
        with self.assertRaisesRegex(manifest.ManifestError, "newer status date"):
            manifest._projection_predates_registry_snapshot(
                "2026-08-02",
                self.same_day_advanced_registry(),
                source_revision_id=self.registry["source"]["revision_id"],
                source_revision_timestamp=(
                    self.registry["source"]["revision_timestamp"]
                ),
            )

    def test_news_registry_v1_compatibility_remains_supported(self):
        registry = json.loads(DYNAMIC_REGISTRY.read_text(encoding="utf-8"))
        news = json.loads(json.dumps(self.news))
        news["candidate_roster"] = fetch_news_wire.candidate_roster_metadata(
            registry
        )

        manifest._validate_news_active_parity(registry, news)

    def test_registry_v2_lane_metadata_is_dynamic_and_provenanced(self):
        source = {
            "available": True,
            "byte_size": 1,
            "sha256": "0" * 64,
            "payload": self.registry,
            "error": None,
        }
        with patch.object(manifest, "_read_source", return_value=source):
            lane, _sources = manifest._build_lane(Path("fixture"), "candidacy_status")
        self.assertEqual(lane["candidate_total"], 5)
        self.assertEqual(lane["active_total"], 2)
        self.assertEqual(lane["temporarily_missing_total"], 1)
        self.assertEqual(
            lane["wikipedia_revision_id"], self.registry["source"]["revision_id"]
        )
        self.assertTrue(lane["canonical_source_url"].startswith("https://fr.wikipedia.org/"))


if __name__ == "__main__":
    unittest.main()
