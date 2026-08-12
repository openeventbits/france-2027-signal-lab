import json
import shutil
import socket
import unittest
import uuid
from pathlib import Path
from unittest import mock

import build_campaign_events as builder
from campaign_event_institutional_seeds import (
    load_campaign_event_institutional_seeds,
)
from campaign_events_contract import (
    campaign_event_id,
    validate_campaign_events_artifact,
)
from rn_agenda_adapter import RnAgendaAdapterError


ROOT = Path(__file__).resolve().parent
GENERATED_AT = "2026-08-01T12:34:56Z"


def rn_event(
    observed_at=GENERATED_AT,
    *,
    event_key="rn-agenda-marine-le-pen-2026-08-27-1645-debate",
    title="Marine Le Pen sur LCI",
    scheduled_start="2026-08-27T16:45:00+02:00",
):
    return {
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "event_type": "debate",
        "title": title,
        "candidate_ids": ["marine-le-pen"],
        "candidate_names": ["Marine Le Pen"],
        "scheduled_start": scheduled_start,
        "time_precision": "datetime",
        "timezone": "Europe/Paris",
        "organization": "MEDEF",
        "status": "scheduled",
        "status_as_of": observed_at[:10],
        "evidence_status": "verified",
        "last_verified_at": observed_at,
        "evidence": [
            {
                "source_id": "rn-agenda",
                "source_url": "https://rassemblementnational.fr/agenda",
                "source_publisher": "Rassemblement National",
                "source_type": "party_first_party",
                "evidence_type": "explicit_schedule",
            }
        ],
    }

def manual_event(*, event_key="manual-00000000000000000000000000000001", participants=None):
    event = {"event_key": event_key, "title": "Grand débat présidentiel", "date": "2026-08-27", "event_type": "debate", "source_url": "https://example.com/politique/debat-2027", "source_publisher": "Example Média", "source_type": "reliable_media", "last_verified_at": GENERATED_AT}
    if participants is not None:
        event["participants"] = participants
    return event


def manual_payload(*events):
    return {"schema_version": "1.0", "events": list(events)}


class BuildCampaignEventsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_root = ROOT / f".campaign-events-build-test-{uuid.uuid4().hex}"
        self.temporary_root.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary_root, True)
        self.output = self.temporary_root / "campaign_events.json"

    def build(self, **changes):
        arguments = {
            "generated_at": GENERATED_AT,
            "seed_path": ROOT / "campaign_event_institutional_seeds.json",
            "source_registry_path": ROOT / "campaign_event_sources.json",
            "candidate_registry_path": ROOT / "candidate_candidacy_status.json",
            "manual_events_path": ROOT / "campaign_events_manual.json",
            "output_path": self.output,
        }
        arguments.update(changes)
        return builder.build_from_paths(**arguments)

    def write_json(self, name, payload):
        target = self.temporary_root / name
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def production_seeds(self):
        return json.loads(
            (ROOT / "campaign_event_institutional_seeds.json").read_text(
                encoding="utf-8"
            )
        )

    def production_registry(self):
        return json.loads(
            (ROOT / "campaign_event_sources.json").read_text(encoding="utf-8")
        )

    def registry_with_rn(self, **changes):
        payload = self.production_registry()
        payload["sources"] = [
            item
            for item in payload["sources"]
            if "campaign_events" not in item["allowed_lanes"]
            or item["source_id"] == "rn-agenda"
        ]
        source = next(
            item for item in payload["sources"] if item["source_id"] == "rn-agenda"
        )
        source.update(changes)
        return self.write_json("changed-sources.json", payload)

    def assert_two_milestones(self, artifact):
        self.assertEqual(
            [
                event["event_type"]
                for event in artifact["institutional_milestones"]
            ],
            ["first_round", "second_round"],
        )
    def assert_last_good(self, action):
        sentinel = b'{"last_good":true}\n'
        self.output.write_bytes(sentinel)
        with self.assertRaises(builder.BuildCampaignEventsError):
            action()
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assertEqual(list(self.temporary_root.glob(".campaign_events.json.*.tmp")), [])



    def write_manual_events(self, *events):
        return self.write_json("manual-events.json", manual_payload(*events))

    def test_empty_manual_input_publishes_two_milestones(self):
        path = self.write_manual_events()
        with mock.patch.object(builder, "load_campaign_events_manual", wraps=builder.load_campaign_events_manual) as loader:
            artifact = self.build(manual_events_path=path)
        loader.assert_called_once_with(path, candidate_registry_path=ROOT / "candidate_candidacy_status.json", source_registry_path=ROOT / "campaign_event_sources.json")
        self.assertEqual(artifact["campaign_events"], [])
        self.assert_two_milestones(artifact)
        validate_campaign_events_artifact(artifact)

    def test_manual_event_publishes_with_persisted_key_and_deterministic_id(self):
        event = manual_event(participants=["David Lisnard"])
        artifact = self.build(manual_events_path=self.write_manual_events(event))
        published = artifact["campaign_events"][0]
        self.assert_two_milestones(artifact)
        self.assertEqual(published["event_key"], event["event_key"])
        self.assertEqual(published["event_id"], campaign_event_id("campaign_events", event["event_key"]))
        self.assertEqual(published["candidate_ids"], ["david-lisnard"])
        validate_campaign_events_artifact(artifact)

    def test_manual_participant_linkage_respects_candidate_visibility(self):
        artifact = self.build(manual_events_path=self.write_manual_events(manual_event(participants=["David Lisnard", "Benjamin Lucas-Lundy", "Unknown Political Actor"])))
        published = artifact["campaign_events"][0]
        self.assertEqual(published["participants"], ["Benjamin Lucas-Lundy", "David Lisnard", "Unknown Political Actor"])
        self.assertEqual(published["candidate_ids"], ["david-lisnard"])
        self.assertEqual(published["candidate_names"], ["David Lisnard"])

    def test_normal_build_never_dispatches_dynamic_collectors_or_network(self):
        path = self.write_manual_events(manual_event())
        with mock.patch.object(builder, "_collect_dynamic_campaign_events", side_effect=AssertionError("dynamic collection invoked")), mock.patch.object(builder, "_dispatch_campaign_event_collection", side_effect=AssertionError("collection dispatch invoked")), mock.patch.object(socket, "create_connection", side_effect=AssertionError("network access attempted")), mock.patch.object(socket, "socket", side_effect=AssertionError("network access attempted")):
            artifact = self.build(manual_events_path=path)
        self.assertEqual(len(artifact["campaign_events"]), 1)

    def test_malformed_manual_input_preserves_existing_artifact(self):
        path = self.write_json("malformed-manual-events.json", {"schema_version": "1.0", "events": "invalid"})
        self.assert_last_good(lambda: self.build(manual_events_path=path))

    def test_repeated_manual_build_is_byte_identical(self):
        path = self.write_manual_events(manual_event())
        self.build(manual_events_path=path); first = self.output.read_bytes()
        self.build(manual_events_path=path)
        self.assertEqual(self.output.read_bytes(), first)

    def test_manual_input_preserves_generated_at_when_semantics_match(self):
        path = self.write_manual_events(manual_event())
        existing = self.build(generated_at="2026-08-01T16:00:00Z", manual_events_path=path); existing_bytes = self.output.read_bytes()
        candidate_path = self.temporary_root / "candidate.json"
        candidate = self.build(generated_at="2026-08-02T16:00:00Z", manual_events_path=path, output_path=candidate_path, preserve_generated_at_from=self.output)
        self.assertEqual(candidate, existing)
        self.assertEqual(candidate_path.read_bytes(), existing_bytes)

    def test_bootstrap_empty_does_not_require_manual_input(self):
        artifact = self.build(seed_path=self.temporary_root / "missing-seeds.json", manual_events_path=self.temporary_root / "missing-manual-events.json", bootstrap_empty=True)
        self.assertEqual(artifact["campaign_events"], [])
        self.assertEqual(artifact["institutional_milestones"], [])
        self.assertEqual(artifact["data_as_of"], GENERATED_AT)

    def test_date_only_and_datetime_same_event_reconcile_to_datetime(self):
        tf1_key = "tf1-lci-2026-08-29-1645-hollande-philippe-debate"
        tf1 = {
            "event_key": tf1_key,
            "event_id": campaign_event_id("campaign_events", tf1_key),
            "event_type": "debate",
            "title": "François Hollande face à Édouard Philippe sur LCI",
            "candidate_ids": [
                "edouard-philippe",
                "francois-hollande",
            ],
            "candidate_names": [
                "Édouard Philippe",
                "François Hollande",
            ],
            "scheduled_start": "2026-08-29T16:45:00+02:00",
            "time_precision": "datetime",
            "timezone": "Europe/Paris",
            "organization": "Laboratoire de la République",
            "locality": "Sens",
            "status": "scheduled",
            "status_as_of": "2026-08-08",
            "evidence_status": "verified",
            "last_verified_at": "2026-08-08T17:00:00Z",
            "evidence": [
                {
                    "source_id": "tf1-lci-debates",
                    "source_url": "https://www.tf1info.fr/politique/election-presidentielle-2027-lci-organisera-le-27-aout-un-grand-debat-avec-sept-candidats-declares-ou-pressentis-2455591.html",
                    "source_publisher": "TF1 Info",
                    "source_type": "reliable_media",
                    "evidence_type": "explicit_schedule",
                }
            ],
        }

        organizer_key = "la-lettre-2026-08-29-hollande-philippe-debate"
        organizer = {
            "event_key": organizer_key,
            "event_id": campaign_event_id(
                "campaign_events",
                organizer_key,
            ),
            "event_type": "debate",
            "title": "Débat François Hollande – Édouard Philippe",
            "candidate_ids": [
                "edouard-philippe",
                "francois-hollande",
            ],
            "candidate_names": [
                "Édouard Philippe",
                "François Hollande",
            ],
            "scheduled_start": "2026-08-29",
            "time_precision": "date",
            "timezone": "Europe/Paris",
            "organization": "Laboratoire de la République",
            "locality": "Sens",
            "status": "scheduled",
            "status_as_of": "2026-08-08",
            "evidence_status": "verified",
            "last_verified_at": "2026-08-08T17:00:00Z",
            "evidence": [
                {
                    "source_id": "la-lettre-expansion-agenda",
                    "source_url": "https://www.lalettredelexpansion.com/article/71583/agenda",
                    "source_publisher": "La Lettre de l'Expansion",
                    "source_type": "reliable_media",
                    "evidence_type": "explicit_schedule",
                }
            ],
        }

        reconciled = builder._reconcile_campaign_event_observations(
            [organizer, tf1]
        )

        self.assertEqual(len(reconciled), 1)
        event = reconciled[0]
        self.assertEqual(
            event["scheduled_start"],
            "2026-08-29T16:45:00+02:00",
        )
        self.assertEqual(event["time_precision"], "datetime")
        self.assertEqual(
            event["event_key"],
            (
                "campaign-debate-2026-08-29-1645-"
                "laboratoire-de-la-republique"
            ),
        )
        self.assertEqual(
            {record["source_id"] for record in event["evidence"]},
            {
                "tf1-lci-debates",
                "la-lettre-expansion-agenda",
            },
        )
        artifact = builder.build_campaign_events_artifact(
            self.production_seeds(),
            generated_at=GENERATED_AT,
            campaign_events=reconciled,
        )
        self.assertEqual(len(artifact["campaign_events"]), 1)
        validate_campaign_events_artifact(artifact)

        for source_owned in (tf1, organizer):
            with self.subTest(source_id=source_owned["evidence"][0]["source_id"]):
                with self.assertRaisesRegex(
                    builder.BuildCampaignEventsError,
                    "two independent reliable-media",
                ):
                    builder.build_campaign_events_artifact(
                        self.production_seeds(),
                        generated_at=GENERATED_AT,
                        campaign_events=[source_owned],
                    )

    def test_cross_precision_reconciliation_requires_exact_candidate_set(self):
        datetime_key = "media-2026-08-29-1645-hollande-philippe"
        datetime_event = {
            "event_key": datetime_key,
            "event_id": campaign_event_id(
                "campaign_events",
                datetime_key,
            ),
            "event_type": "debate",
            "title": "Hollande face à Philippe",
            "candidate_ids": [
                "edouard-philippe",
                "francois-hollande",
            ],
            "candidate_names": [
                "Édouard Philippe",
                "François Hollande",
            ],
            "scheduled_start": "2026-08-29T16:45:00+02:00",
            "time_precision": "datetime",
            "timezone": "Europe/Paris",
            "organization": "Laboratoire de la République",
            "locality": "Sens",
            "status": "scheduled",
            "status_as_of": "2026-08-08",
            "evidence_status": "verified",
            "last_verified_at": "2026-08-08T17:00:00Z",
            "evidence": [
                {
                    "source_id": "media-source",
                    "source_url": "https://example.com/media",
                    "source_publisher": "Media",
                    "source_type": "reliable_media",
                    "evidence_type": "explicit_schedule",
                }
            ],
        }

        date_key = "organizer-2026-08-29-philippe"
        date_event = {
            "event_key": date_key,
            "event_id": campaign_event_id(
                "campaign_events",
                date_key,
            ),
            "event_type": "debate",
            "title": "Édouard Philippe à Sens",
            "candidate_ids": ["edouard-philippe"],
            "candidate_names": ["Édouard Philippe"],
            "scheduled_start": "2026-08-29",
            "time_precision": "date",
            "timezone": "Europe/Paris",
            "organization": "Laboratoire de la République",
            "locality": "Sens",
            "status": "scheduled",
            "status_as_of": "2026-08-08",
            "evidence_status": "verified",
            "last_verified_at": "2026-08-08T17:00:00Z",
            "evidence": [
                {
                    "source_id": "organizer-source",
                    "source_url": "https://example.com/organizer",
                    "source_publisher": "Organizer",
                    "source_type": "organizer_first_party",
                    "evidence_type": "explicit_schedule",
                }
            ],
        }

        reconciled = builder._reconcile_campaign_event_observations(
            [date_event, datetime_event]
        )

        self.assertEqual(len(reconciled), 2)

    def test_cross_precision_reconciliation_requires_same_calendar_date(self):
        datetime_key = "media-2026-08-29-1645-hollande-philippe"
        datetime_event = {
            "event_key": datetime_key,
            "event_id": campaign_event_id(
                "campaign_events",
                datetime_key,
            ),
            "event_type": "debate",
            "title": "Hollande face à Philippe",
            "candidate_ids": [
                "edouard-philippe",
                "francois-hollande",
            ],
            "candidate_names": [
                "Édouard Philippe",
                "François Hollande",
            ],
            "scheduled_start": "2026-08-29T16:45:00+02:00",
            "time_precision": "datetime",
            "timezone": "Europe/Paris",
            "organization": "Laboratoire de la République",
            "locality": "Sens",
            "status": "scheduled",
            "status_as_of": "2026-08-08",
            "evidence_status": "verified",
            "last_verified_at": "2026-08-08T17:00:00Z",
            "evidence": [
                {
                    "source_id": "media-source",
                    "source_url": "https://example.com/media",
                    "source_publisher": "Media",
                    "source_type": "reliable_media",
                    "evidence_type": "explicit_schedule",
                }
            ],
        }

        date_key = "organizer-2026-08-28-hollande-philippe"
        date_event = {
            **datetime_event,
            "event_key": date_key,
            "event_id": campaign_event_id(
                "campaign_events",
                date_key,
            ),
            "scheduled_start": "2026-08-28",
            "time_precision": "date",
            "evidence": [
                {
                    "source_id": "organizer-source",
                    "source_url": "https://example.com/organizer",
                    "source_publisher": "Organizer",
                    "source_type": "organizer_first_party",
                    "evidence_type": "explicit_schedule",
                }
            ],
        }

        reconciled = builder._reconcile_campaign_event_observations(
            [date_event, datetime_event]
        )

        self.assertEqual(len(reconciled), 2)

    def test_production_collector_map_is_exact(self):
        self.assertEqual(
            set(builder._PRODUCTION_COLLECTION_COLLECTORS),
            {
                "la-lettre-expansion",
                "linked-ics",
                "qomon",
                "rn-agenda",
                "tf1-lci-debates",
            },
        )
        self.assertEqual(
            builder._PRODUCTION_COLLECTION_COLLECTORS["linked-ics"].__name__,
            "_collect_linked_ics",
        )
        self.assertEqual(
            builder._PRODUCTION_COLLECTION_COLLECTORS["qomon"].__name__,
            "_collect_qomon",
        )
        self.assertEqual(
            builder._PRODUCTION_COLLECTION_COLLECTORS["rn-agenda"].__name__,
            "_collect_rn_agenda",
        )
        self.assertEqual(
            builder._PRODUCTION_COLLECTION_COLLECTORS[
                "tf1-lci-debates"
            ].__name__,
            "_collect_tf1_lci_debates",
        )
        self.assertEqual(
            builder._PRODUCTION_COLLECTION_COLLECTORS[
                "la-lettre-expansion"
            ].__name__,
            "_collect_la_lettre_expansion",
        )

    def test_nouvelle_energie_uses_generic_linked_ics_collector(self):
        source = next(
            item
            for item in builder.load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )["sources"]
            if item["source_id"] == "nouvelle-energie-agenda"
        )

        collector = builder._resolve_campaign_event_collector(
            source,
            collection_collectors=builder._PRODUCTION_COLLECTION_COLLECTORS,
        )

        self.assertIs(
            collector,
            builder._PRODUCTION_COLLECTION_COLLECTORS["linked-ics"],
        )

    def test_production_media_wrappers_return_strict_collection_results(self):
        sources = {
            source["source_id"]: source
            for source in builder.load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )["sources"]
        }
        cases = (
            (
                "tf1-lci-debates",
                "tf1-lci-debates",
                "build_tf1_lci_events",
                builder.Tf1LciAdapterResult,
                0,
            ),
            (
                "la-lettre-expansion-agenda",
                "la-lettre-expansion",
                "build_la_lettre_expansion_events",
                builder.LaLettreExpansionAdapterResult,
                3,
            ),
        )
        for source_id, family, builder_name, result_type, rejected in cases:
            with self.subTest(source_id=source_id):
                adapter = mock.Mock(
                    return_value=result_type(
                        observations=({"source_owned": source_id},),
                        attribution_rejected_records=rejected,
                    )
                )
                with mock.patch.object(builder, builder_name, adapter):
                    result = builder._dispatch_campaign_event_collection(
                        sources[source_id],
                        observed_at=GENERATED_AT,
                        collection_collectors=(
                            builder._PRODUCTION_COLLECTION_COLLECTORS
                        ),
                    )
                self.assertIn(family, builder._PRODUCTION_COLLECTION_COLLECTORS)
                self.assertEqual(
                    result,
                    builder.SourceCollectionResult(
                        observations=[{"source_owned": source_id}],
                        attribution_rejected_records=rejected,
                    ),
                )
                adapter.assert_called_once_with(
                    source=sources[source_id], observed_at=GENERATED_AT
                )

    def test_linked_ics_wrapper_returns_strict_collection_result(self):
        source = {
            "source_id": "generic-linked-ics",
            "collection": {
                "discovery_method": "linked_event_pages",
                "parser_family": "ics",
                "attribution_policy": "explicit_participant",
                "collector_family": "linked-ics",
            },
        }
        collected = builder.LinkedIcsCollectorResult(
            observations=({"source_owned": "generic-linked-ics"},),
            attribution_rejected_records=2,
        )
        with mock.patch.object(
            builder,
            "build_linked_ics_events",
            return_value=collected,
        ) as collector:
            result = builder._collect_linked_ics(
                source=source,
                observed_at=GENERATED_AT,
            )

        self.assertEqual(
            result,
            builder.SourceCollectionResult(
                observations=[{"source_owned": "generic-linked-ics"}],
                attribution_rejected_records=2,
            ),
        )
        collector.assert_called_once_with(
            source=source,
            observed_at=GENERATED_AT,
        )

    def test_linked_ics_dispatch_requires_explicit_collector_family(self):
        source = {
            "source_id": "generic-linked-ics",
            "collection": {
                "discovery_method": "linked_event_pages",
                "parser_family": "ics",
                "attribution_policy": "explicit_participant",
            },
        }
        with self.assertRaisesRegex(
            builder.CampaignEventCollectionConfigurationError,
            "family 'ics'",
        ):
            builder._resolve_campaign_event_collector(
                source,
                collection_collectors=builder._PRODUCTION_COLLECTION_COLLECTORS,
            )

    def test_linked_ics_dispatch_routes_explicit_collector_family(self):
        source = {
            "source_id": "generic-linked-ics",
            "collection": {
                "discovery_method": "linked_event_pages",
                "parser_family": "ics",
                "attribution_policy": "explicit_participant",
                "collector_family": "linked-ics",
            },
        }
        expected = builder.SourceCollectionResult(observations=[])
        collector = mock.Mock(return_value=expected)

        result = builder._dispatch_campaign_event_collection(
            source,
            observed_at=GENERATED_AT,
            collection_collectors={"linked-ics": collector},
        )

        self.assertIs(result, expected)
        collector.assert_called_once_with(
            source=source,
            observed_at=GENERATED_AT,
        )

    def test_qomon_dispatch_routes_explicit_collector_family(self):
        source = {
            "source_id": "generic-qomon",
            "collection": {
                "discovery_method": "custom",
                "parser_family": "custom",
                "attribution_policy": "explicit_participant",
                "collector_family": "qomon",
            },
        }
        expected = builder.SourceCollectionResult(observations=[])
        collector = mock.Mock(return_value=expected)

        result = builder._dispatch_campaign_event_collection(
            source,
            observed_at=GENERATED_AT,
            collection_collectors={"qomon": collector},
        )

        self.assertIs(result, expected)
        collector.assert_called_once_with(
            source=source,
            observed_at=GENERATED_AT,
        )

    def test_qomon_wrapper_returns_strict_collection_result(self):
        source = {
            "source_id": "generic-qomon",
            "collection": {
                "discovery_method": "custom",
                "parser_family": "custom",
                "attribution_policy": "explicit_participant",
                "collector_family": "qomon",
            },
        }
        collected = builder.QomonCollectorResult(
            observations=({"source_owned": "generic-qomon"},),
            attribution_rejected_records=3,
        )
        with mock.patch.object(
            builder,
            "build_qomon_events",
            return_value=collected,
        ) as collector:
            result = builder._collect_qomon(
                source=source,
                observed_at=GENERATED_AT,
            )

        self.assertEqual(
            result,
            builder.SourceCollectionResult(
                observations=[{"source_owned": "generic-qomon"}],
                attribution_rejected_records=3,
            ),
        )
        collector.assert_called_once_with(
            source=source,
            observed_at=GENERATED_AT,
        )

    def test_generic_dispatcher_routes_by_collector_family(self):
        source = next(
            item
            for item in builder.load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )["sources"]
            if item["source_id"] == "rn-agenda"
        )
        expected = builder.SourceCollectionResult(observations=[])
        collector = mock.Mock(return_value=expected)
        result = builder._dispatch_campaign_event_collection(
            source,
            observed_at=GENERATED_AT,
            collection_collectors={"rn-agenda": collector},
        )

        self.assertIs(result, expected)
        collector.assert_called_once_with(
            source=source,
            observed_at=GENERATED_AT,
        )

    def test_generic_dispatcher_routes_by_parser_family(self):
        source = next(
            item
            for item in builder.load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )["sources"]
            if item["source_id"] == "rn-agenda"
        )
        source["collection"] = {
            "discovery_method": "structured_html",
            "parser_family": "structured_html",
            "attribution_policy": "explicit_participant",
        }
        collector = mock.Mock(
            return_value=builder.SourceCollectionResult(observations=[])
        )
        builder._dispatch_campaign_event_collection(
            source,
            observed_at=GENERATED_AT,
            collection_collectors={"structured_html": collector},
        )
        collector.assert_called_once_with(
            source=source,
            observed_at=GENERATED_AT,
        )

    def test_unknown_collector_family_fails_closed(self):
        source = next(
            item
            for item in builder.load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )["sources"]
            if item["source_id"] == "rn-agenda"
        )
        source["collection"]["collector_family"] = "not-registered"
        with self.assertRaisesRegex(
            builder.BuildCampaignEventsError,
            "no Campaign Events collector registered",
        ):
            builder._dispatch_campaign_event_collection(
                source,
                observed_at=GENERATED_AT,
                collection_collectors={},
            )



    def test_custom_rn_collector_remains_supported(self):
        source = next(
            item
            for item in builder.load_campaign_event_source_registry(
                ROOT / "campaign_event_sources.json"
            )["sources"]
            if item["source_id"] == "rn-agenda"
        )
        with mock.patch.object(
            builder,
            "build_rn_agenda_events",
            return_value=[],
        ) as rn_builder:
            result = builder._dispatch_campaign_event_collection(
                source,
                observed_at=GENERATED_AT,
                collection_collectors=builder._PRODUCTION_COLLECTION_COLLECTORS,
            )
        self.assertEqual(
            result,
            builder.SourceCollectionResult(
                observations=[],
                attribution_rejected_records=0,
            ),
        )
        rn_builder.assert_called_once_with(observed_at=GENERATED_AT)



    def test_source_collection_result_rejects_negative_rejection_count(self):
        with self.assertRaisesRegex(
            builder.BuildCampaignEventsError,
            "attribution_rejected_records",
        ):
            builder.SourceCollectionResult(
                observations=[],
                attribution_rejected_records=-1,
            )

    def test_source_collection_result_rejects_malformed_observations(self):
        for observations in ({}, [object()]):
            with self.subTest(observations=observations):
                with self.assertRaisesRegex(
                    builder.BuildCampaignEventsError,
                    "observations",
                ):
                    builder.SourceCollectionResult(observations=observations)














    def test_successful_two_milestone_build(self):
        artifact = self.build()
        self.assertEqual(artifact["generated_at"], GENERATED_AT)
        self.assertEqual(artifact["data_as_of"], "2026-08-01T00:00:00Z")
        self.assertEqual(artifact["campaign_events"], [])
        self.assertEqual(len(artifact["institutional_milestones"]), 2)
        milestones = artifact["institutional_milestones"]
        self.assertEqual(
            [(item["event_type"], item["scheduled_start"]) for item in milestones],
            [("first_round", "2027-04-18"), ("second_round", "2027-05-02")],
        )
        for item in milestones:
            self.assertEqual(item["candidate_ids"], [])
            self.assertEqual(item["candidate_names"], [])
            self.assertEqual(item["time_precision"], "date")
            self.assertEqual(item["timezone"], "Europe/Paris")
            self.assertEqual(item["status"], "scheduled")
            self.assertEqual(item["evidence_status"], "verified")
        validate_campaign_events_artifact(
            artifact,
            source_registry_path=ROOT / "campaign_event_sources.json",
        )

    def test_stable_deterministic_ids_and_ordering(self):
        artifact = self.build()
        milestones = artifact["institutional_milestones"]
        self.assertEqual(
            [item["event_id"] for item in milestones],
            [
                campaign_event_id(
                    "institutional_milestones",
                    "presidential-2027-first-round",
                ),
                campaign_event_id(
                    "institutional_milestones",
                    "presidential-2027-second-round",
                ),
            ],
        )

    def test_exact_evidence_is_preserved_and_sorted(self):
        artifact = self.build()
        for item in artifact["institutional_milestones"]:
            self.assertEqual(
                [record["source_id"] for record in item["evidence"]],
                [
                    "interieur-presidential-calendar",
                    "vie-publique-presidential-calendar",
                ],
            )
            self.assertTrue(
                all(
                    record["evidence_type"] == "official_rule_derivation"
                    for record in item["evidence"]
                )
            )

    def test_repeated_build_is_byte_identical(self):
        self.build()
        first = self.output.read_bytes()
        self.build()
        self.assertEqual(self.output.read_bytes(), first)

    def test_valid_existing_artifact_prevents_requested_timestamp_churn(self):
        existing = self.build(generated_at="2026-08-01T16:00:00Z")
        existing_bytes = self.output.read_bytes()
        candidate_path = self.temporary_root / "candidate.json"
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            output_path=candidate_path,
            preserve_generated_at_from=self.output,
        )
        self.assertEqual(candidate["generated_at"], existing["generated_at"])
        self.assertEqual(candidate, existing)
        self.assertEqual(candidate_path.read_bytes(), existing_bytes)
        self.assertEqual(
            [event["event_id"] for event in candidate["institutional_milestones"]],
            [event["event_id"] for event in existing["institutional_milestones"]],
        )

    def test_genuine_seed_change_uses_new_requested_timestamp(self):
        existing = self.build(generated_at="2026-08-01T16:00:00Z")
        existing_bytes = self.output.read_bytes()
        payload = self.production_seeds()
        payload["seeds"][0]["title"] += " — mise à jour"
        changed_seed_path = self.write_json("changed-seeds.json", payload)
        candidate_path = self.temporary_root / "changed-candidate.json"
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            seed_path=changed_seed_path,
            output_path=candidate_path,
            preserve_generated_at_from=self.output,
        )
        self.assertEqual(candidate["generated_at"], "2026-08-02T16:00:00Z")
        self.assertNotEqual(candidate_path.read_bytes(), existing_bytes)
        self.assertNotEqual(candidate["institutional_milestones"], existing["institutional_milestones"])
        self.assertEqual(
            [event["event_id"] for event in candidate["institutional_milestones"]],
            [event["event_id"] for event in existing["institutional_milestones"]],
        )

    def test_invalid_existing_artifact_is_not_trusted(self):
        existing_path = self.temporary_root / "invalid-existing.json"
        existing_path.write_text("{not json", encoding="utf-8")
        candidate = self.build(
            generated_at="2026-08-02T16:00:00Z",
            preserve_generated_at_from=existing_path,
        )
        self.assertEqual(candidate["generated_at"], "2026-08-02T16:00:00Z")
        validate_campaign_events_artifact(
            candidate,
            source_registry_path=ROOT / "campaign_event_sources.json",
        )


    def test_explicit_timestamp_is_required_and_local_timezone_independent(self):
        artifact = self.build(generated_at="2026-12-15T01:02:03Z")
        first_bytes = self.output.read_bytes()
        self.assertEqual(artifact["generated_at"], "2026-12-15T01:02:03Z")
        with mock.patch.dict("os.environ", {"TZ": "Pacific/Kiritimati"}):
            second = self.build(generated_at="2026-12-15T01:02:03Z")
        self.assertEqual(second, artifact)
        self.assertEqual(self.output.read_bytes(), first_bytes)

    def test_invalid_registry_preserves_last_good(self):
        invalid_registry = self.write_json(
            "invalid-sources.json",
            {"schema_version": "1.0", "sources": "invalid"},
        )
        self.assert_last_good(
            lambda: self.build(source_registry_path=invalid_registry)
        )

    def test_invalid_and_missing_seed_round_preserve_last_good(self):
        payload = self.production_seeds()
        payload["seeds"][0]["scheduled_start"] = "not-a-date"
        invalid_seeds = self.write_json("invalid-seeds.json", payload)
        self.assert_last_good(lambda: self.build(seed_path=invalid_seeds))

        payload = self.production_seeds()
        payload["seeds"] = payload["seeds"][:1]
        missing_round = self.write_json("missing-round.json", payload)
        self.assert_last_good(lambda: self.build(seed_path=missing_round))

    def test_missing_second_round_preserves_last_good(self):
        payload = self.production_seeds()
        payload["seeds"] = payload["seeds"][1:]
        missing_round = self.write_json("missing-first-round.json", payload)
        self.assert_last_good(lambda: self.build(seed_path=missing_round))

    def test_serialization_failure_preserves_last_good(self):
        self.assert_last_good(
            lambda: self._build_with_serialization_failure()
        )

    def _build_with_serialization_failure(self):
        with mock.patch.object(
            builder,
            "serialize_campaign_events",
            side_effect=RuntimeError("simulated serialization failure"),
        ):
            self.build()

    def test_atomic_promotion_failure_preserves_last_good_and_cleans_temp(self):
        sentinel = b"last good\n"
        self.output.write_bytes(sentinel)
        with mock.patch.object(
            builder.os,
            "replace",
            side_effect=OSError("simulated promotion failure"),
        ):
            with self.assertRaises(builder.BuildCampaignEventsError):
                self.build()
        self.assertEqual(self.output.read_bytes(), sentinel)
        self.assertEqual(list(self.temporary_root.glob(".campaign_events.json.*.tmp")), [])

    def test_bootstrap_empty_requires_explicit_option(self):
        artifact = self.build(
            seed_path=self.temporary_root / "missing.json",
            bootstrap_empty=True,
        )
        self.assertEqual(artifact["institutional_milestones"], [])
        self.assertEqual(artifact["data_as_of"], GENERATED_AT)
        with self.assertRaises(builder.BuildCampaignEventsError):
            self.build(seed_path=self.temporary_root / "missing.json")

    def test_no_network_access_or_unrelated_writes(self):
        before = {path.name for path in self.temporary_root.iterdir()}
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ):
            self.build()
        after = {path.name for path in self.temporary_root.iterdir()}
        self.assertEqual(after - before, {"campaign_events.json"})

    def test_cli_returns_nonzero_without_required_seed_file(self):
        exit_code = builder.main(
            [
                "--generated-at",
                GENERATED_AT,
                "--seeds",
                str(self.temporary_root / "missing.json"),
                "--output",
                str(self.output),
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
