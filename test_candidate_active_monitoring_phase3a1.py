"""Cross-system contracts for stored tiers and effective active monitoring."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import build_candidate_signals as signals
import campaign_event_attribution
import fetch_candidate_candidacy_status as registry_fetcher
import fetch_news_wire
import tf1_lci_adapter
from candidate_candidacy_status import (
    active_candidate_ids,
    active_candidate_names,
    active_candidate_records,
    project_active_monitoring_field,
    project_display_tiers,
    validate_candidate_candidacy_status,
)
from test_build_candidate_signals import (
    claims_fixture,
    news_fixture,
    poll_event,
    visibility_metric,
)
from test_candidate_signals_frontend import run_candidate_module
from test_candidate_signals_workspace import run_workspace


ROOT = Path(__file__).resolve().parent
DYNAMIC_REGISTRY = ROOT / "test_fixtures" / "candidate_candidacy_status_dynamic.json"
TRACKED_REGISTRY = ROOT / "candidate_candidacy_status.json"


def registry_v2(source_path: Path, *missing_ids: str) -> dict:
    """Promote a valid v1 fixture to v2 and mark selected identities absent."""

    source = json.loads(source_path.read_text(encoding="utf-8"))
    status_as_of = source["status_as_of"]
    revision = registry_fetcher.RevisionSnapshot(1, f"{status_as_of}T04:05:00Z")
    candidates = []
    for candidate in source["candidates"]:
        record = copy.deepcopy(candidate)
        record.update(
            {
                "upstream_presence": (
                    "temporarily_missing"
                    if record["candidate_id"] in missing_ids
                    else "present"
                ),
                "wikipedia_article": None,
                "previous_names": [],
            }
        )
        candidates.append(record)
    payload = {
        "schema_version": "2.0",
        "status_as_of": status_as_of,
        "source": {
            "publisher": "French Wikipedia",
            "page_title": registry_fetcher.PAGE_TITLE,
            "page_url": registry_fetcher.PAGE_URL,
            "revision_id": revision.revision_id,
            "revision_timestamp": revision.revision_timestamp,
            "revision_url": revision.permanent_url,
        },
        "candidates": candidates,
    }
    validate_candidate_candidacy_status(payload)
    return payload


def phase3a1_signals_payload() -> dict:
    registry = registry_v2(DYNAMIC_REGISTRY, "alice-observee")
    polls = [
        poll_event(
            candidates=[
                ("Alice Observée", 60),
                ("Personne Hors Registre", 40),
            ]
        )
    ]
    news = news_fixture(
        primary_metrics=[visibility_metric("Alice Observée", "primary")],
        general_metrics=[],
        candidate_watch=[],
        roster_names=active_candidate_names(registry),
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
    return signals.build_candidate_signals(
        polls,
        news,
        claims_fixture(reviews=[]),
        registry,
    )


class RegistryActiveProjectionTests(unittest.TestCase):
    def test_stored_and_effective_projections_are_distinct_and_in_parity(self):
        registry = registry_v2(DYNAMIC_REGISTRY, "chloe-potentielle")
        stored = project_display_tiers(registry)
        active = project_active_monitoring_field(registry)

        self.assertIn("chloe-potentielle", stored["secondary"])
        self.assertNotIn("chloe-potentielle", active["secondary"])
        self.assertEqual(
            active["main"] + active["secondary"],
            active_candidate_ids(registry),
        )
        self.assertEqual(
            active_candidate_ids(registry),
            [record["candidate_id"] for record in active_candidate_records(registry)],
        )
        self.assertEqual(
            active_candidate_names(registry),
            [record["candidate_name"] for record in active_candidate_records(registry)],
        )

    def test_v1_presence_defaults_to_present(self):
        registry = json.loads(DYNAMIC_REGISTRY.read_text(encoding="utf-8"))
        active = project_active_monitoring_field(registry)
        stored = project_display_tiers(registry)
        self.assertEqual(active["main"], stored["main"])
        self.assertEqual(active["secondary"], stored["secondary"])

    def test_presence_and_tier_matrix(self):
        registry = registry_v2(
            DYNAMIC_REGISTRY,
            "alice-observee",
            "chloe-potentielle",
        )
        active_ids = set(active_candidate_ids(registry))
        self.assertNotIn("alice-observee", active_ids)
        self.assertIn("benoit-non-teste", active_ids)
        self.assertNotIn("chloe-potentielle", active_ids)
        self.assertNotIn("david-retire", active_ids)
        self.assertNotIn("elise-declinee", active_ids)


class CandidateSignalsActiveProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = phase3a1_signals_payload()
        cls.by_id = {
            candidate["candidate_id"]: candidate
            for candidate in cls.payload["candidates"]
        }

    def test_complete_and_stored_fields_retain_temporarily_missing_candidate(self):
        self.assertEqual(self.payload["schema_version"], "1.5")
        self.assertEqual(len(self.payload["candidates"]), 5)
        self.assertIn(
            "alice-observee",
            self.payload["presidential_field"]["main"],
        )
        self.assertEqual(self.payload["presidential_field"]["counts"]["total"], 5)

    def test_effective_fields_exclude_temporarily_missing_candidate(self):
        candidate = self.by_id["alice-observee"]
        self.assertEqual(candidate["candidacy"]["display_tier"], "main")
        self.assertEqual(
            candidate["candidacy"]["upstream_presence"],
            "temporarily_missing",
        )
        self.assertFalse(candidate["candidacy"]["active_field_eligible"])
        active = self.payload["active_monitoring_field"]
        self.assertNotIn("alice-observee", active["main"])
        for lane in ("primary", "general"):
            visibility_ids = {
                row["candidate_id"]
                for tier in ("main", "secondary")
                for row in self.payload["active_field_visibility"][lane][tier]
            }
            self.assertNotIn("alice-observee", visibility_ids)

    def test_present_candidates_and_dynamic_counts_remain_valid(self):
        self.assertIn(
            "benoit-non-teste",
            self.payload["active_monitoring_field"]["main"],
        )
        self.assertIn(
            "chloe-potentielle",
            self.payload["active_monitoring_field"]["secondary"],
        )
        self.assertEqual(
            self.payload["active_monitoring_field"]["counts"],
            {"main": 1, "secondary": 1, "active": 2},
        )
        self.assertEqual(
            self.by_id["benoit-non-teste"]["polling"]["evidence_state"],
            "not_observed",
        )

    def test_invalid_active_field_membership_is_rejected(self):
        invalid = copy.deepcopy(self.payload)
        invalid["active_monitoring_field"]["main"].append(
            "alice-observee"
        )
        invalid["active_monitoring_field"]["counts"]["main"] = 2
        invalid["active_monitoring_field"]["counts"]["active"] = 3
        with self.assertRaises(signals.CandidateSignalsError):
            signals.validate_candidate_signals(invalid)

    def test_invalid_active_eligibility_is_rejected(self):
        invalid = copy.deepcopy(self.payload)
        candidate = next(
            row
            for row in invalid["candidates"]
            if row["candidate_id"] == "alice-observee"
        )
        candidate["candidacy"]["active_field_eligible"] = True
        with self.assertRaises(signals.CandidateSignalsError):
            signals.validate_candidate_signals(invalid)


class FrontendAndWorkspaceActiveProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = phase3a1_signals_payload()

    def test_schema_13_normalizer_accepts_stored_effective_distinction(self):
        state = run_candidate_module("api.normalize(input.payload)", self.payload)
        self.assertEqual(state["status"], "ready")
        self.assertEqual(
            state["metadata"]["activeMonitoringField"]["counts"]["active"],
            2,
        )

    def test_normalizer_rejects_missing_candidate_marked_active(self):
        invalid = copy.deepcopy(self.payload)
        candidate = next(
            row
            for row in invalid["candidates"]
            if row["candidate_id"] == "alice-observee"
        )
        candidate["candidacy"]["active_field_eligible"] = True
        state = run_candidate_module("api.normalize(input.payload)", invalid)
        self.assertEqual(state["status"], "unavailable")
        self.assertEqual(state["reason"], "invalid_payload")

    def test_workspace_uses_only_effective_active_candidates(self):
        all_candidates = run_workspace(self.payload)
        self.assertEqual(all_candidates["status"], "ready")
        self.assertEqual(
            set(all_candidates["candidateOrder"]),
            {"benoit-non-teste", "chloe-potentielle"},
        )
        self.assertNotIn("alice-observee", all_candidates["candidateOrder"])
        self.assertNotIn("david-retire", all_candidates["candidateOrder"])

        main_only = run_workspace(self.payload, action="main-only")
        self.assertEqual(
            set(main_only["visibleCandidateOrder"]),
            {"benoit-non-teste"},
        )
        self.assertNotIn("chloe-potentielle", main_only["visibleCandidateOrder"])

        search = run_workspace(
            self.payload,
            action={"type": "search", "term": "Alice Observée"},
        )
        self.assertEqual(search["visibleCandidateOrder"], [])

    def test_schema_12_tracked_artifact_remains_compatible(self):
        tracked = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )
        state = run_candidate_module("api.normalize(input.payload)", tracked)
        self.assertEqual(state["status"], "ready")


class NewsAndEventsActiveProjectionTests(unittest.TestCase):
    def test_news_roster_and_metadata_are_presence_aware(self):
        registry = registry_v2(DYNAMIC_REGISTRY, "chloe-potentielle")
        active_records = active_candidate_records(registry)
        self.assertEqual(
            fetch_news_wire.active_news_candidate_roster(registry),
            ["Alice Observée", "Benoît Non Testé"],
        )
        self.assertEqual(
            [record["candidate_id"] for record in active_records],
            ["alice-observee", "benoit-non-teste"],
        )
        self.assertEqual(
            [record["candidate_name"] for record in active_records],
            ["Alice Observée", "Benoît Non Testé"],
        )
        metadata = fetch_news_wire.candidate_roster_metadata(registry)
        self.assertEqual(metadata["count"], 2)
        self.assertEqual(metadata["rule"], "active_monitoring_field")
        self.assertEqual(metadata["names"], active_candidate_names(registry))
        self.assertNotIn("Chloé Potentielle", metadata["names"])
        self.assertNotIn("David Retiré", metadata["names"])

    def test_campaign_attribution_excludes_temporarily_missing(self):
        registry = registry_v2(DYNAMIC_REGISTRY, "chloe-potentielle")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            candidates, by_id = campaign_event_attribution._load_active_candidates(
                path
            )
        self.assertEqual(
            [candidate.candidate_id for candidate in candidates],
            ["alice-observee", "benoit-non-teste"],
        )
        self.assertNotIn("chloe-potentielle", by_id)

    def test_tf1_active_projection_excludes_temporarily_missing(self):
        registry = registry_v2(TRACKED_REGISTRY, "francois-hollande")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            resolved, active_ids = tf1_lci_adapter._canonical_candidates(path)
        self.assertIn("francois-hollande", resolved)
        self.assertNotIn("francois-hollande", active_ids)


if __name__ == "__main__":
    unittest.main()
