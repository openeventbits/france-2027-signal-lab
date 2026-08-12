import json
import unittest
from pathlib import Path
from unittest.mock import patch

import build_candidate_signals as signals
import build_publication_manifest as manifest
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
    news["candidate_roster"] = {
        "source": "candidate_candidacy_status.json",
        "rule": "active_monitoring_field",
        "status_as_of": registry["status_as_of"],
        "count": len(active_names),
        "names": active_names,
    }
    polls = [poll_event(candidates=[("Alice Observée", 60), ("Poll Only Person", 40)])]
    claims = build_public_bundle(registry, [], 365, "2026-08-07T05:00:00Z")
    candidate_signals = signals.build_candidate_signals(polls, news, claims, registry)
    return registry, news, claims, candidate_signals


class PublicationManifestRegistryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.news, cls.claims, cls.signals = bundle()

    def test_signals_13_complete_and_active_projections_reconcile(self):
        self.assertEqual(self.signals["schema_version"], "1.3")
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

    def test_older_attention_11_projection_is_valid_downstream_lag(self):
        attention = build_payload(self.registry)
        manifest._validate_candidate_attention_parity(
            self.advanced_registry(), attention
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

    def test_news_active_roster_parity(self):
        manifest._validate_news_active_parity(self.registry, self.news)
        changed = json.loads(json.dumps(self.news))
        changed["candidate_roster"]["names"].reverse()
        with self.assertRaisesRegex(manifest.ManifestError, "active registry"):
            manifest._validate_news_active_parity(self.registry, changed)

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
