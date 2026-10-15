"""Effective-dated candidacy decisions outrank persistent source listings."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import fetch_candidate_candidacy_status as collector
from build_candidate_signals import build_candidate_signals
from build_candidate_visibility_history import build_candidate_visibility_history
from candidate_candidacy_status import (
    active_candidate_ids,
    active_candidate_names,
    active_candidate_records,
    semantic_sha256,
)
from candidate_page_contract import project_candidate_page_lifecycle
from test_fetch_candidate_candidacy_status import fixture_html, supplemental_fixture_html


ROOT = Path(__file__).resolve().parent
EFFECTIVE = "2026-10-11T16:30:00Z"
BEFORE = "2026-10-11T16:29:59Z"
LOSERS = ("Olivier Faure", "Ségolène Royal", "Emmanuel Maurel", "Jérôme Guedj")
WINNER = "Raphaël Glucksmann"


class CandidateLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sources = tuple(
            source for source in collector.load_curated_candidacy_sources(
                ROOT / "candidate_candidacy_sources.json"
            ) if source.effective_at
        )
        self.html = fixture_html(declared_names=(WINNER,), primary_names=LOSERS)
        self.revision = collector.RevisionSnapshot(101, "2026-10-11T15:00:00Z")
        self.previous = collector.build_payload(self.revision, self.html, as_of=BEFORE)[0]
        self.supplemental = tuple(collector.extract_candidates(
            supplemental_fixture_html(official_names=(WINNER, *LOSERS)),
            section_rules=collector.SOCIALIST_PRIMARY_SECTION_RULES,
            source_page_title=collector.SOCIALIST_PRIMARY_PAGE_TITLE,
        ))
        # The main page no longer lists defeated participants. The persistent
        # supplemental page continues to list all five official participants.
        self.html = fixture_html(declared_names=(WINNER,), primary_names=())

    def build(self, *, as_of=EFFECTIVE, previous=None, sources=None, revision=None):
        source_revision = revision or self.revision
        return collector.build_payload(
            source_revision,
            self.html,
            previous_registry=previous or self.previous,
            supplemental_candidates=self.supplemental,
            supplemental_revision=collector.RevisionSnapshot(
                source_revision.revision_id + 1, source_revision.revision_timestamp,
                collector.SOCIALIST_PRIMARY_PAGE_TITLE,
            ),
            curated_sources=self.sources if sources is None else sources,
            as_of=as_of,
        )[0]

    def test_effective_boundary_and_all_canonical_projections(self):
        before = self.build(as_of=BEFORE)
        after = self.build()
        self.assertEqual(len(after["candidates"]), len(before["candidates"]))
        records = {row["candidate_name"]: row for row in after["candidates"]}
        for name in LOSERS:
            self.assertIn(name, active_candidate_names(before))
            self.assertEqual(records[name]["status"], "primary_eliminated")
            self.assertEqual(records[name]["display_tier"], "hidden")
            self.assertEqual(records[name]["upstream_presence"], "present")
            self.assertEqual(records[name]["status_as_of"], "2026-10-11")
            self.assertNotIn(records[name], active_candidate_records(after))
            self.assertNotIn(records[name]["candidate_id"], active_candidate_ids(after))
            self.assertNotIn(name, active_candidate_names(after))
        self.assertEqual(records[WINNER]["status"], "party_selected")
        self.assertIn(WINNER, active_candidate_names(after))
        self.assertEqual(records[WINNER]["source_publisher"], "LCP - Assemblée nationale")

    def test_refresh_is_idempotent_even_after_newer_wikipedia_edit(self):
        first = self.build()
        second = self.build(previous=first)
        self.assertEqual(collector.serialize_payload(first), collector.serialize_payload(second))
        newer = self.build(
            previous=second, as_of="2026-10-15T12:00:00Z",
            revision=collector.RevisionSnapshot(103, "2026-10-15T11:00:00Z"),
        )
        self.assertEqual(semantic_sha256(first), semantic_sha256(newer))
        for row in newer["candidates"]:
            if row["candidate_name"] in LOSERS:
                self.assertEqual(row["status"], "primary_eliminated")

    def test_later_authoritative_declaration_can_reactivate(self):
        eliminated = self.build()
        old_event = next(source for source in self.sources if source.candidate_name == LOSERS[0])
        declaration = replace(
            old_event, source_id="later-independent-declaration",
            status="declared", event_type="declaration",
            source_type="candidate_first_party", source_date="2026-10-20",
            status_as_of="2026-10-20", effective_at="2026-10-20T12:00:00Z",
            url="https://www.parti-socialiste.fr/candidature-independante",
            source_title="Test fixture: later independent candidacy",
            status_note="Announced an independent presidential candidacy.",
        )
        sources = (declaration, *reversed(self.sources))
        pending = self.build(previous=eliminated, sources=sources)
        self.assertNotIn(LOSERS[0], active_candidate_names(pending))
        reactivated = self.build(
            previous=eliminated, sources=sources, as_of=declaration.effective_at,
        )
        self.assertIn(LOSERS[0], active_candidate_names(reactivated))
        for row in reactivated["candidates"]:
            if row["candidate_name"] == LOSERS[0]:
                self.assertEqual(row["status"], "declared")
                self.assertEqual(row["source_url"], declaration.url)
        self.assertEqual(reactivated, self.build(
            previous=reactivated, sources=sources, as_of=declaration.effective_at,
        ))

    def test_visibility_observations_do_not_change_with_current_status(self):
        before = self.build(as_of=BEFORE)
        after = self.build()
        observations = [{
            "coverage_scope": "campaign", "published_at": "2026-10-10T10:00:00Z",
            "publisher": "Fixture publisher",
            "candidate_matches": [{"candidate": name} for name in LOSERS],
        }]
        def history(payload):
            return build_candidate_visibility_history(
                candidate_watch=observations, generated_at="2026-10-12T12:00:00Z",
                window_days=30, candidates=payload["candidates"],
            )
        self.assertEqual(history(before), history(after))
        rows = {row["candidate_name"]: row for row in history(after)["candidates"]}
        for name in LOSERS:
            series = rows[name]["campaign_attention"]["daily_series"]
            self.assertEqual(next(day for day in series if day["date"] == "2026-10-10")["record_count"], 1)

    def test_published_routes_are_retained_as_archives(self):
        lifecycle = project_candidate_page_lifecycle(self.build(), ROOT)
        for name in LOSERS:
            self.assertIn(collector.candidate_id(name), lifecycle["retained_archived_ids"])

    def test_downstream_signals_use_canonical_projection(self):
        registry = collector.load_previous_registry(ROOT / "candidate_candidacy_status.json")
        before = copy.deepcopy(registry)
        for row in before["candidates"]:
            if row["candidate_name"] in LOSERS:
                row.update(status="primary_contender", display_tier="main")
        after = copy.deepcopy(before)
        collector.apply_lifecycle_events(after["candidates"], self.sources, as_of=EFFECTIVE)
        def read(name):
            return json.loads((ROOT / name).read_text(encoding="utf-8"))
        inputs = (read("polls.json"), read("news_wire.json"), read("claims_under_scrutiny.json"))
        old_signals = build_candidate_signals(*inputs, before)
        signals = build_candidate_signals(*inputs, after)
        self.assertEqual(
            [row["candidate_id"] for row in signals["candidates"] if row["candidacy"]["active_field_eligible"]],
            active_candidate_ids(after),
        )
        self.assertEqual(len(signals["candidates"]), len(old_signals["candidates"]))
        self.assertEqual(
            old_signals["active_monitoring_field"]["counts"]["active"]
            - signals["active_monitoring_field"]["counts"]["active"], len(LOSERS),
        )

    def test_inventory_rejects_ambiguous_or_malformed_events(self):
        payload = json.loads((ROOT / "candidate_candidacy_sources.json").read_text(encoding="utf-8"))
        event = next(row for row in payload["sources"] if "effective_at" in row)
        variants = []
        for update in (
            {"effective_at": "2026-10-11"},
            {"effective_at": "2026-10-10T12:00:00Z"},
            {"event_type": "declaration"},
            {"event_type": []},
            {"status": "declared"},
        ):
            variants.append({**event, **update})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            for variant in variants:
                with self.subTest(variant=variant):
                    path.write_text(json.dumps({**payload, "sources": [variant]}), encoding="utf-8")
                    with self.assertRaises(collector.CandidateCandidacyFetchError):
                        collector.load_curated_candidacy_sources(path)
            path.write_text(json.dumps({**payload, "sources": [event, {**event, "source_id": "duplicate"}]}), encoding="utf-8")
            with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "simultaneous"):
                collector.load_curated_candidacy_sources(path)

    def test_inventory_accepts_multiple_ordered_events_for_one_candidate(self):
        payload = json.loads((ROOT / "candidate_candidacy_sources.json").read_text(encoding="utf-8"))
        event = next(row for row in payload["sources"] if row.get("status") == "primary_eliminated")
        declaration = {
            **event, "source_id": "later-declaration", "source_type": "candidate_first_party",
            "status": "declared", "event_type": "declaration",
            "source_date": "2026-10-20", "status_as_of": "2026-10-20",
            "effective_at": "2026-10-20T12:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps({**payload, "sources": [declaration, event]}), encoding="utf-8")
            sources = collector.load_curated_candidacy_sources(path)
        self.assertEqual([source.source_id for source in sources], [event["source_id"], "later-declaration"])

    def test_future_legacy_source_does_not_rewrite_historical_state(self):
        future = replace(
            self.sources[0], effective_at=None, event_type=None,
            source_type="candidate_first_party", status="withdrawn",
            status_as_of="2026-10-20", source_date="2026-10-20",
        )
        before = self.build(as_of=BEFORE, sources=(future,))
        self.assertIn(future.candidate_name, active_candidate_names(before))

    def test_unknown_event_identity_fails_closed(self):
        event = replace(self.sources[0], candidate_id="unknown-candidate")
        with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "registered identity"):
            self.build(sources=(event,))

    def test_historical_rebuild_rejects_inputs_from_after_the_event(self):
        with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "before the lifecycle event"):
            self.build(previous=self.build(), as_of=BEFORE)
        with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "source revisions"):
            self.build(as_of=BEFORE, revision=collector.RevisionSnapshot(103, EFFECTIVE))

    def test_public_reconciler_rejects_equal_time_conflicts_in_either_order(self):
        result = next(source for source in self.sources if source.status == "primary_eliminated")
        conflict = replace(
            result, source_id="conflicting-declaration", status="declared",
            event_type="declaration", source_type="candidate_first_party",
        )
        for sources in ((result, conflict), (conflict, result)):
            with self.subTest(order=[source.source_id for source in sources]):
                records = copy.deepcopy(self.previous["candidates"])
                with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "simultaneous"):
                    collector.apply_lifecycle_events(records, sources, as_of=EFFECTIVE)
                self.assertEqual(records, self.previous["candidates"])

    def test_previous_snapshot_from_later_same_day_is_rejected(self):
        future = copy.deepcopy(self.previous)
        future["source"]["revision_timestamp"] = EFFECTIVE
        with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "last-good registry revision"):
            self.build(previous=future, as_of=BEFORE)

    def test_supplemental_failure_preserves_last_good_registry(self):
        eliminated = self.build()
        original = copy.deepcopy(eliminated)
        def unavailable(_fetch_json, *, page_title=collector.PAGE_TITLE):
            if page_title == collector.SOCIALIST_PRIMARY_PAGE_TITLE:
                raise collector.CandidateCandidacyFetchError("supplemental unavailable")
            return self.revision
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "registry.json"
            collector.write_payload_atomic(eliminated, output)
            before_bytes = output.read_bytes()
            with (
                mock.patch.object(collector, "fetch_current_revision", side_effect=unavailable),
                mock.patch.object(collector, "fetch_parsed_revision", return_value=self.html),
                mock.patch.object(collector, "load_curated_candidacy_sources", return_value=self.sources),
            ):
                with self.assertRaisesRegex(collector.CandidateCandidacyFetchError, "supplemental unavailable"):
                    collector.main(["--previous", str(output), "--output", str(output)])
            self.assertEqual(output.read_bytes(), before_bytes)
        self.assertEqual(eliminated, original)
        for name in LOSERS:
            self.assertNotIn(name, active_candidate_names(eliminated))


if __name__ == "__main__":
    unittest.main()
