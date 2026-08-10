"""Tests for deterministic Campaign Events observation construction."""

from __future__ import annotations

import importlib
import json
import shutil
import socket
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

from campaign_event_attribution import AttributedStructuredEvent
from campaign_event_observation import (
    CampaignEventObservationBatch,
    CampaignEventObservationConfigurationError,
    ClassifiedCampaignEvent,
    build_campaign_event_observation,
    build_campaign_event_observations,
    classify_campaign_event,
)
from campaign_event_sources import normalize_campaign_event_source_registry
from campaign_event_structured import (
    StructuredEventParseError,
    StructuredEventRecord,
)
from campaign_events_contract import normalize_campaign_event_observations


OBSERVED_AT = "2026-08-09T16:00:00Z"
ALL_CAMPAIGN_TYPES = [
    "rally",
    "public_meeting",
    "debate",
    "candidate_visit",
    "campaign_launch",
]


def attributed_event(
    title: str,
    *,
    description: str | None = None,
    candidate_ids: tuple[str, ...] = ("david-lisnard",),
    candidate_names: tuple[str, ...] = ("David Lisnard",),
    basis: str | None = "explicit_participant",
    scheduled_start: str = "2026-08-29T19:00:00+02:00",
    time_precision: str = "datetime",
    scheduled_end: str | None = None,
    organization: str | None = None,
    location_name: str | None = None,
    locality: str | None = None,
    event_url: str | None = "https://events.example/detail/one",
    external_id: str | None = None,
    source_status: str | None = None,
    participants: tuple[str, ...] = (),
) -> AttributedStructuredEvent:
    record = StructuredEventRecord(
        title=title,
        scheduled_start=scheduled_start,
        time_precision=time_precision,
        timezone="Europe/Paris",
        source_format="json_ld",
        scheduled_end=scheduled_end,
        description=description,
        organization=organization,
        location_name=location_name,
        locality=locality,
        event_url=event_url,
        external_id=external_id,
        source_status=source_status,
        participants=participants,
    )
    return AttributedStructuredEvent(
        structured_event=record,
        candidate_ids=candidate_ids,
        candidate_names=candidate_names,
        attribution_basis=basis,
    )


def source_record(
    *,
    source_type: str = "party_first_party",
    allowed_event_types: list[str] | None = None,
    candidate_owned: bool = False,
) -> dict[str, object]:
    source_id = "test-" + source_type.replace("_", "-")
    source: dict[str, object] = {
        "source_id": source_id,
        "publisher": "Test Campaign Publisher",
        "source_type": source_type,
        "url": f"https://{source_id}.example/agenda",
        "allowed_lanes": ["campaign_events"],
        "allowed_event_types": list(
            ALL_CAMPAIGN_TYPES
            if allowed_event_types is None
            else allowed_event_types
        ),
        "enabled": True,
        "required": False,
        "refresh_class": "daily",
        "zero_result_valid": True,
        "collection": {
            "discovery_method": "json_ld",
            "parser_family": "json_ld",
            "attribution_policy": (
                "candidate_owned_campaign"
                if candidate_owned
                else "explicit_participant"
            ),
        },
    }
    if source_type == "candidate_first_party":
        source["candidate_ids"] = ["gabriel-attal"]
    elif source_type in {"party_first_party", "organizer_first_party"}:
        source["organization"] = "Test Campaign Organization"
    return normalize_campaign_event_source_registry(
        {"schema_version": "2.0", "sources": [source]}
    )["sources"][0]


class CampaignEventObservationTests(unittest.TestCase):
    def test_structured_html_is_the_only_new_structured_source_format(self):
        common = {
            "title": "Débat entre deux candidats",
            "scheduled_start": "2026-08-29",
            "time_precision": "date",
            "timezone": "Europe/Paris",
        }
        self.assertEqual(
            StructuredEventRecord(
                **common,
                source_format="structured_html",
            ).source_format,
            "structured_html",
        )
        for existing in ("json_ld", "ics"):
            with self.subTest(existing=existing):
                self.assertEqual(
                    StructuredEventRecord(
                        **common,
                        source_format=existing,
                    ).source_format,
                    existing,
                )
        with self.assertRaisesRegex(
            StructuredEventParseError,
            "source_format is not allowed",
        ):
            StructuredEventRecord(**common, source_format="custom")

    def setUp(self) -> None:
        self.temporary_root = Path(__file__).parent / (
            f".campaign-event-observation-test-{uuid.uuid4().hex}"
        )
        self.temporary_root.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary_root, True)
        self.registry_path = self.temporary_root / "sources.json"

    def write_registry(self, source: dict[str, object]) -> Path:
        payload = normalize_campaign_event_source_registry(
            {"schema_version": "2.0", "sources": [source]}
        )
        self.registry_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.registry_path

    def build(
        self,
        event: AttributedStructuredEvent,
        *,
        source: dict[str, object] | None = None,
        evidence_url: str | None = None,
        observed_at: str = OBSERVED_AT,
    ) -> dict[str, object] | None:
        active_source = source or source_record()
        self.write_registry(active_source)
        return build_campaign_event_observation(
            event,
            source=active_source,
            observed_at=observed_at,
            evidence_url=(
                evidence_url
                if evidence_url is not None
                else str(active_source["url"])
            ),
            source_registry_path=self.registry_path,
        )

    def test_campaign_launch_classification_is_bounded(self):
        accepted = (
            "Lancement de la campagne présidentielle",
            "Lancement de campagne présidentielle",
            "Lancement de la campagne",
            "Meeting national de lancement de la campagne présidentielle",
        )
        for title in accepted:
            with self.subTest(title=title):
                result = classify_campaign_event(attributed_event(title))
                self.assertIsInstance(result, ClassifiedCampaignEvent)
                self.assertEqual(result.event_type, "campaign_launch")

        for title in (
            "Lancement du nouveau site internet",
            "Inauguration du local",
            "Lancement de la rentrée politique",
        ):
            with self.subTest(title=title):
                self.assertIsNone(classify_campaign_event(attributed_event(title)))

    def test_debate_and_paired_debate_classification(self):
        for event in (
            attributed_event("Débat présidentiel avec David Lisnard"),
            attributed_event(
                "François Hollande face à Édouard Philippe",
                candidate_ids=("francois-hollande", "edouard-philippe"),
                candidate_names=("François Hollande", "Édouard Philippe"),
            ),
        ):
            with self.subTest(title=event.structured_event.title):
                result = classify_campaign_event(event)
                self.assertIsNotNone(result)
                self.assertEqual(result.event_type, "debate")

    def test_retransmission_interview_and_generic_discussion_are_not_debates(self):
        for title in (
            "Retransmission du débat avec David Lisnard",
            "Projection du débat",
            "Watch party du débat",
            "Interview de David Lisnard",
            "Entretien avec David Lisnard",
            "Discussion avec David Lisnard",
            "Table ronde avec David Lisnard",
        ):
            with self.subTest(title=title):
                event = attributed_event(title, basis="candidate_owned_campaign")
                self.assertIsNone(classify_campaign_event(event))

    def test_public_meeting_classification_is_bounded(self):
        for title in (
            "Meeting avec Nathalie Arthaud",
            "Meeting de campagne",
            "Meeting politique avec David Lisnard",
            "Grand meeting de campagne",
            "Réunion publique avec David Lisnard",
            "Réunion électorale avec David Lisnard",
        ):
            with self.subTest(title=title):
                result = classify_campaign_event(attributed_event(title))
                self.assertIsNotNone(result)
                self.assertEqual(result.event_type, "public_meeting")

        for title in (
            "Réunion avec David Lisnard",
            "Réunion interne avec David Lisnard",
            "Réunion départementale Nouvelle Énergie",
            "Réunion de bureau",
            "Réunion des adhérents",
            "Comité local de soutien",
            "Réunion de soutien à David Lisnard",
            "Meeting de soutien à Gabriel Attal",
            "Grand meeting de soutien à Gabriel Attal",
        ):
            with self.subTest(title=title):
                self.assertIsNone(
                    classify_campaign_event(
                        attributed_event(title, basis="candidate_owned_campaign")
                    )
                )

    def test_rally_classification_is_conservative(self):
        for title in (
            "Rassemblement avec David Lisnard",
            "Grand rassemblement de campagne",
            "Rallye de campagne présidentielle",
        ):
            with self.subTest(title=title):
                result = classify_campaign_event(attributed_event(title))
                self.assertIsNotNone(result)
                self.assertEqual(result.event_type, "rally")

        for title in (
            "Mobilisation pour David Lisnard",
            "Manifestation nationale",
            "Soirée de soutien à David Lisnard",
            "Rallye automobile",
        ):
            with self.subTest(title=title):
                self.assertIsNone(classify_campaign_event(attributed_event(title)))

    def test_candidate_visit_requires_campaign_context_for_explicit_basis(self):
        accepted = attributed_event(
            "David Lisnard en visite à Lille",
            description="Déplacement dans le cadre de la campagne présidentielle.",
        )
        result = classify_campaign_event(accepted)
        self.assertIsNotNone(result)
        self.assertEqual(result.event_type, "candidate_visit")

        for event in (
            attributed_event("David Lisnard en visite officielle comme ministre"),
            attributed_event(
                "Déplacement ministériel de David Lisnard",
                description="Agenda ministériel à Lille.",
            ),
            attributed_event("Visite guidée du musée avec David Lisnard"),
        ):
            with self.subTest(title=event.structured_event.title):
                self.assertIsNone(classify_campaign_event(event))

    def test_candidate_owned_visit_still_requires_visit_semantics(self):
        visit = attributed_event(
            "Gabriel Attal se rendra à Lille",
            candidate_ids=("gabriel-attal",),
            candidate_names=("Gabriel Attal",),
            basis="candidate_owned_campaign",
        )
        result = classify_campaign_event(visit)
        self.assertIsNotNone(result)
        self.assertEqual(result.event_type, "candidate_visit")

        committee = attributed_event(
            "Comité local",
            candidate_ids=("gabriel-attal",),
            candidate_names=("Gabriel Attal",),
            basis="candidate_owned_campaign",
        )
        self.assertIsNone(classify_campaign_event(committee))
    def test_candidate_owned_basis_must_match_source_policy(self):
        party_source = source_record()
        owned_event = attributed_event(
            "Meeting de campagne",
            basis="candidate_owned_campaign",
        )
        with self.assertRaisesRegex(
            CampaignEventObservationConfigurationError,
            "attribution basis",
        ):
            self.build(owned_event, source=party_source)

        candidate_source = source_record(
            source_type="candidate_first_party",
            candidate_owned=True,
        )
        explicit_event = attributed_event(
            "Meeting de campagne",
            candidate_ids=("gabriel-attal",),
            candidate_names=("Gabriel Attal",),
        )
        with self.assertRaisesRegex(
            CampaignEventObservationConfigurationError,
            "attribution basis",
        ):
            self.build(explicit_event, source=candidate_source)



    def test_attribution_or_speech_alone_does_not_create_taxonomy(self):
        for event in (
            attributed_event("Discours de rentrée de David Lisnard"),
            attributed_event("AMFIS 2026", basis="candidate_owned_campaign"),
        ):
            with self.subTest(title=event.structured_event.title):
                self.assertIsNone(classify_campaign_event(event))

    def test_representative_launch_meeting_and_debate_cases(self):
        cases = (
            (
                attributed_event(
                    "Meeting national de lancement de la campagne présidentielle",
                    candidate_ids=("jean-luc-melenchon",),
                    candidate_names=("Jean-Luc Mélenchon",),
                ),
                "campaign_launch",
            ),
            (
                attributed_event(
                    "Meeting avec Nathalie Arthaud",
                    candidate_ids=("nathalie-arthaud",),
                    candidate_names=("Nathalie Arthaud",),
                ),
                "public_meeting",
            ),
            (
                attributed_event(
                    "François Hollande face à Édouard Philippe",
                    candidate_ids=("francois-hollande", "edouard-philippe"),
                    candidate_names=("François Hollande", "Édouard Philippe"),
                ),
                "debate",
            ),
        )
        for event, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    classify_campaign_event(event).event_type,
                    expected,
                )

    def test_classification_precedence_is_explicit(self):
        event = attributed_event(
            "Meeting débat de lancement de la campagne présidentielle"
        )
        self.assertEqual(
            classify_campaign_event(event).event_type,
            "campaign_launch",
        )

    def test_source_allowed_event_types_are_enforced(self):
        source = source_record(allowed_event_types=["debate"])
        event = attributed_event(
            "Meeting national de lancement de la campagne présidentielle"
        )
        with self.assertRaisesRegex(
            CampaignEventObservationConfigurationError,
            "allowed_event_types",
        ):
            self.build(event, source=source)

    def test_first_party_unclassified_event_uses_allowed_other_fallback(self):
        source = source_record(
            source_type="party_first_party",
            allowed_event_types=[*ALL_CAMPAIGN_TYPES, "other"],
        )
        event = attributed_event("Discours de rentrée de David Lisnard")
        self.assertIsNone(classify_campaign_event(event))

        observation = self.build(event, source=source)

        self.assertIsNotNone(observation)
        self.assertEqual(observation["event_type"], "other")

    def test_first_party_unclassified_event_is_rejected_without_other(self):
        source = source_record(source_type="party_first_party")
        self.write_registry(source)
        batch = build_campaign_event_observations(
            (attributed_event("Discours de rentrée de David Lisnard"),),
            source=source,
            observed_at=OBSERVED_AT,
            evidence_url=str(source["url"]),
            source_registry_path=self.registry_path,
        )

        self.assertEqual(batch.observations, ())
        self.assertEqual(batch.relevance_rejected_records, 1)

    def test_reliable_media_does_not_receive_other_fallback(self):
        source = source_record(
            source_type="reliable_media",
            allowed_event_types=[*ALL_CAMPAIGN_TYPES, "other"],
        )
        self.write_registry(source)
        batch = build_campaign_event_observations(
            (attributed_event("Discours de rentrée de David Lisnard"),),
            source=source,
            observed_at=OBSERVED_AT,
            evidence_url=str(source["url"]),
            source_registry_path=self.registry_path,
        )

        self.assertEqual(batch.observations, ())
        self.assertEqual(batch.relevance_rejected_records, 1)

    def test_recognized_first_party_event_precedes_other_fallback(self):
        source = source_record(
            source_type="party_first_party",
            allowed_event_types=[*ALL_CAMPAIGN_TYPES, "other"],
        )
        observation = self.build(
            attributed_event("Meeting avec David Lisnard"),
            source=source,
        )

        self.assertEqual(observation["event_type"], "public_meeting")

    def test_observation_maps_contract_fields_and_normalizes(self):
        source = source_record()
        event = attributed_event(
            "Meeting politique avec David Lisnard",
            scheduled_end="2026-08-29T21:00:00+02:00",
            organization="Nouvelle Énergie",
            location_name="Palais des Festivals",
            locality="Cannes",
            external_id="event-42",
        )
        observation = self.build(event, source=source)
        self.assertEqual(observation["event_type"], "public_meeting")
        self.assertEqual(observation["candidate_ids"], ["david-lisnard"])
        self.assertEqual(observation["candidate_names"], ["David Lisnard"])
        self.assertEqual(
            observation["scheduled_start"],
            "2026-08-29T19:00:00+02:00",
        )
        self.assertEqual(
            observation["scheduled_end"],
            "2026-08-29T21:00:00+02:00",
        )
        self.assertEqual(observation["time_precision"], "datetime")
        self.assertEqual(observation["timezone"], "Europe/Paris")
        self.assertEqual(observation["organization"], "Nouvelle Énergie")
        self.assertEqual(observation["location_name"], "Palais des Festivals")
        self.assertEqual(observation["locality"], "Cannes")
        self.assertEqual(observation["status"], "scheduled")
        self.assertEqual(observation["status_as_of"], "2026-08-09")
        self.assertEqual(observation["last_verified_at"], OBSERVED_AT)
        self.assertEqual(observation["evidence_status"], "verified")
        self.assertEqual(
            normalize_campaign_event_observations(
                [observation],
                source_registry_path=self.registry_path,
            ),
            [observation],
        )

    def test_explicit_structured_participants_are_copied_to_observation(self):
        observation = self.build(
            attributed_event(
                "Meeting avec David Lisnard",
                participants=("Unknown Political Actor",),
            )
        )
        self.assertEqual(
            observation["participants"],
            ["Unknown Political Actor"],
        )

    def test_unlinked_explicit_participant_builds_public_meeting_observation(self):
        observation = self.build(
            attributed_event(
                "Meeting public",
                candidate_ids=(),
                candidate_names=(),
                basis=None,
                participants=("Unknown Political Actor",),
            )
        )

        self.assertEqual(observation["event_type"], "public_meeting")
        self.assertEqual(observation["candidate_ids"], [])
        self.assertEqual(observation["candidate_names"], [])
        self.assertEqual(
            observation["participants"],
            ["Unknown Political Actor"],
        )

    def test_unlinked_unclassified_event_uses_bounded_other_fallback(self):
        event = attributed_event(
            "Discours de rentrée",
            candidate_ids=(),
            candidate_names=(),
            basis=None,
            participants=("Unknown Political Actor",),
        )
        source = source_record(
            source_type="party_first_party",
            allowed_event_types=[*ALL_CAMPAIGN_TYPES, "other"],
        )

        observation = self.build(event, source=source)

        self.assertEqual(observation["event_type"], "other")
        self.assertEqual(observation["candidate_ids"], [])

    def test_unlinked_unclassified_event_is_rejected_without_other(self):
        event = attributed_event(
            "Discours de rentrée",
            candidate_ids=(),
            candidate_names=(),
            basis=None,
            participants=("Unknown Political Actor",),
        )
        source = source_record(source_type="party_first_party")
        self.write_registry(source)

        batch = build_campaign_event_observations(
            (event,),
            source=source,
            observed_at=OBSERVED_AT,
            evidence_url=str(source["url"]),
            source_registry_path=self.registry_path,
        )

        self.assertEqual(batch.observations, ())
        self.assertEqual(batch.relevance_rejected_records, 1)

    def test_unlinked_observation_rejects_reliable_media_source(self):
        source = source_record(source_type="reliable_media")
        with self.assertRaisesRegex(
            CampaignEventObservationConfigurationError,
            "unlinked attribution",
        ):
            self.build(
                attributed_event(
                    "Meeting public",
                    candidate_ids=(),
                    candidate_names=(),
                    basis=None,
                    participants=("Unknown Political Actor",),
                ),
                source=source,
            )

    def test_absent_structured_participants_preserve_public_shape(self):
        observation = self.build(
            attributed_event("Meeting avec David Lisnard")
        )
        self.assertNotIn("participants", observation)

    def test_date_precision_is_preserved(self):
        observation = self.build(
            attributed_event(
                "Meeting avec David Lisnard",
                scheduled_start="2026-08-29",
                time_precision="date",
                event_url=None,
            )
        )
        self.assertEqual(observation["scheduled_start"], "2026-08-29")
        self.assertEqual(observation["time_precision"], "date")

    def test_status_mapping_is_bounded(self):
        for source_status, expected_status, expected_evidence in (
            (None, "scheduled", "explicit_schedule"),
            ("CONFIRMED", "scheduled", "explicit_schedule"),
            ("TENTATIVE", "scheduled", "explicit_schedule"),
            ("CANCELLED", "cancelled", "explicit_status_update"),
            (
                "https://schema.org/EventCancelled",
                "cancelled",
                "explicit_status_update",
            ),
            (
                "https://schema.org/EventPostponed",
                "postponed",
                "explicit_status_update",
            ),
        ):
            with self.subTest(source_status=source_status):
                observation = self.build(
                    attributed_event(
                        "Meeting avec David Lisnard",
                        source_status=source_status,
                    )
                )
                self.assertEqual(observation["status"], expected_status)
                self.assertEqual(
                    observation["evidence"][0]["evidence_type"],
                    expected_evidence,
                )

        with self.assertRaisesRegex(
            CampaignEventObservationConfigurationError,
            "source_status",
        ):
            self.build(
                attributed_event(
                    "Meeting avec David Lisnard",
                    source_status="https://example.org/EventCancelled",
                )
            )

    def test_evidence_uses_explicit_provenance_and_exact_source_identity(self):
        source = source_record(source_type="organizer_first_party")
        evidence_url = "https://test-organizer-first-party.example/events/42"
        observation = self.build(
            attributed_event("Meeting avec David Lisnard"),
            source=source,
            evidence_url=evidence_url,
        )
        self.assertEqual(
            observation["evidence"],
            [
                {
                    "source_id": source["source_id"],
                    "source_url": evidence_url,
                    "source_publisher": source["publisher"],
                    "source_type": source["source_type"],
                    "evidence_type": "explicit_schedule",
                }
            ],
        )

    def test_evidence_url_is_required_and_never_inferred(self):
        source = source_record()
        self.write_registry(source)
        event = attributed_event(
            "Meeting avec David Lisnard",
            event_url="https://test-party-first-party.example/events/in-record",
        )
        for evidence_url in (None, "http://events.example/insecure"):
            with self.subTest(evidence_url=evidence_url):
                with self.assertRaises(
                    CampaignEventObservationConfigurationError
                ):
                    build_campaign_event_observation(
                        event,
                        source=source,
                        observed_at=OBSERVED_AT,
                        evidence_url=evidence_url,
                        source_registry_path=self.registry_path,
                    )

    def test_event_key_is_source_owned_deterministic_and_uid_sensitive(self):
        source = source_record()
        first = self.build(
            attributed_event(
                "Meeting avec David Lisnard",
                external_id="uid-one",
            ),
            source=source,
        )
        repeated = self.build(
            attributed_event(
                "Meeting avec David Lisnard",
                external_id="uid-one",
            ),
            source=source,
            observed_at="2026-08-10T16:00:00Z",
        )
        rescheduled = self.build(
            attributed_event(
                "Meeting avec David Lisnard",
                external_id="uid-one",
                scheduled_start="2026-09-12T20:00:00+02:00",
                source_status="POSTPONED",
            ),
            source=source,
        )
        retitled_and_relocated = self.build(
            attributed_event(
                "Grand meeting de campagne",
                external_id="uid-one",
                location_name="Grand Palais",
                locality="Lille",
            ),
            source=source,
        )
        changed_roster_and_taxonomy = self.build(
            attributed_event(
                "Débat présidentiel",
                external_id="uid-one",
                candidate_ids=("nathalie-arthaud",),
                candidate_names=("Nathalie Arthaud",),
            ),
            source=source,
        )
        second_uid = self.build(
            attributed_event(
                "Meeting avec David Lisnard",
                external_id="uid-two",
            ),
            source=source,
        )
        self.assertEqual(first["event_key"], repeated["event_key"])
        self.assertEqual(first["event_id"], repeated["event_id"])
        self.assertEqual(first["event_key"], rescheduled["event_key"])
        self.assertEqual(first["event_id"], rescheduled["event_id"])
        self.assertEqual(
            first["event_key"],
            retitled_and_relocated["event_key"],
        )
        self.assertEqual(
            first["event_key"],
            changed_roster_and_taxonomy["event_key"],
        )
        self.assertNotEqual(first["event_key"], second_uid["event_key"])
        self.assertTrue(
            first["event_key"].startswith(source["source_id"] + "-uid-")
        )
        self.assertFalse(first["event_key"].startswith("campaign-"))

    def test_event_key_without_external_id_uses_deterministic_fallback(self):
        source = source_record()
        first = self.build(
            attributed_event("Meeting de campagne", external_id=None),
            source=source,
        )
        repeated = self.build(
            attributed_event("Meeting de campagne", external_id=None),
            source=source,
        )
        rescheduled = self.build(
            attributed_event(
                "Meeting de campagne",
                external_id=None,
                scheduled_start="2026-09-12T20:00:00+02:00",
            ),
            source=source,
        )
        self.assertEqual(first["event_key"], repeated["event_key"])
        self.assertEqual(first["event_id"], repeated["event_id"])
        self.assertNotEqual(first["event_key"], rescheduled["event_key"])

    def test_observed_at_and_internal_identity_defects_fail_closed(self):
        source = source_record()
        for observed_at in (
            None,
            "2026-08-09",
            "2026-08-09T16:00:00+00:00",
            "2026-02-30T16:00:00Z",
        ):
            with self.subTest(observed_at=observed_at):
                with self.assertRaisesRegex(
                    CampaignEventObservationConfigurationError,
                    "observed_at",
                ):
                    self.build(
                        attributed_event("Meeting avec David Lisnard"),
                        source=source,
                        observed_at=observed_at,
                    )

        malformed_source = dict(source)
        del malformed_source["publisher"]
        self.write_registry(source)
        with self.assertRaises(CampaignEventObservationConfigurationError):
            build_campaign_event_observation(
                attributed_event("Meeting avec David Lisnard"),
                source=malformed_source,
                observed_at=OBSERVED_AT,
                evidence_url=str(source["url"]),
                source_registry_path=self.registry_path,
            )

        with self.assertRaises(CampaignEventObservationConfigurationError):
            self.build(
                attributed_event(
                    "Meeting avec David Lisnard",
                    candidate_names=("Not David Lisnard",),
                ),
                source=source,
            )

    def test_each_campaign_source_type_can_build_without_new_ownership_rules(self):
        for source_type in (
            "official_structured",
            "official_unstructured",
            "candidate_first_party",
            "party_first_party",
            "organizer_first_party",
            "reliable_media",
        ):
            with self.subTest(source_type=source_type):
                candidate_owned = source_type == "candidate_first_party"
                source = source_record(
                    source_type=source_type,
                    candidate_owned=candidate_owned,
                )
                event = attributed_event(
                    "Meeting de campagne",
                    candidate_ids=(
                        ("gabriel-attal",)
                        if candidate_owned
                        else ("david-lisnard",)
                    ),
                    candidate_names=(
                        ("Gabriel Attal",)
                        if candidate_owned
                        else ("David Lisnard",)
                    ),
                    basis=(
                        "candidate_owned_campaign"
                        if candidate_owned
                        else "explicit_participant"
                    ),
                )
                observation = self.build(event, source=source)
                self.assertEqual(
                    observation["evidence"][0]["source_type"],
                    source_type,
                )

    def test_reliable_media_observation_normalizes_before_reconciliation(self):
        source = source_record(source_type="reliable_media")
        observation = self.build(
            attributed_event("Débat présidentiel avec David Lisnard"),
            source=source,
        )
        self.assertEqual(observation["event_type"], "debate")
        self.assertEqual(len(observation["evidence"]), 1)

    def test_batch_counts_relevance_rejections_and_preserves_observations(self):
        source = source_record()
        self.write_registry(source)
        launch = attributed_event(
            "Meeting national de lancement de la campagne présidentielle",
            external_id="launch-1",
        )
        speech = attributed_event("Discours de rentrée de David Lisnard")
        meeting = attributed_event(
            "Meeting avec David Lisnard",
            external_id="meeting-1",
            scheduled_start="2026-09-01T19:00:00+02:00",
        )
        batch = build_campaign_event_observations(
            (launch, speech, meeting),
            source=source,
            observed_at=OBSERVED_AT,
            evidence_url=str(source["url"]),
            source_registry_path=self.registry_path,
        )
        self.assertIsInstance(batch, CampaignEventObservationBatch)
        self.assertEqual(batch.relevance_rejected_records, 1)
        self.assertEqual(len(batch.observations), 2)
        self.assertEqual(
            {record["event_type"] for record in batch.observations},
            {"campaign_launch", "public_meeting"},
        )

    def test_batch_does_not_reconcile_or_add_internal_fields(self):
        source = source_record()
        self.write_registry(source)
        events = (
            attributed_event(
                "Meeting avec David Lisnard",
                external_id="one",
            ),
            attributed_event(
                "Grand meeting avec David Lisnard",
                external_id="two",
            ),
        )
        batch = build_campaign_event_observations(
            events,
            source=source,
            observed_at=OBSERVED_AT,
            evidence_url=str(source["url"]),
            source_registry_path=self.registry_path,
        )
        self.assertEqual(len(batch.observations), 2)
        for observation in batch.observations:
            self.assertNotIn("attribution_basis", observation)
            self.assertNotIn("relevance_rejected_records", observation)
            self.assertNotIn("collection_health", observation)

    def test_batch_and_classification_models_fail_closed(self):
        event = attributed_event("Meeting avec David Lisnard")
        with self.assertRaises(CampaignEventObservationConfigurationError):
            ClassifiedCampaignEvent(event, "interview")
        with self.assertRaises(CampaignEventObservationConfigurationError):
            CampaignEventObservationBatch(({"not": "an observation"},), 0)
        with self.assertRaises(CampaignEventObservationConfigurationError):
            CampaignEventObservationBatch((), -1)
        with self.assertRaises(CampaignEventObservationConfigurationError):
            classify_campaign_event("not an attributed event")

    def test_repeated_calls_are_deterministic(self):
        source = source_record()
        event = attributed_event(
            "Meeting avec David Lisnard",
            external_id="deterministic-1",
        )
        first = self.build(event, source=source)
        second = self.build(event, source=source)
        self.assertEqual(first, second)

    def test_builder_performs_no_network_access(self):
        source = source_record()
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("network access attempted"),
        ):
            observation = self.build(
                attributed_event("Meeting avec David Lisnard"),
                source=source,
            )
        self.assertEqual(observation["event_type"], "public_meeting")

    def test_module_import_performs_no_network_access(self):
        module_name = "_campaign_event_observation_import_test"
        module_path = Path(__file__).with_name("campaign_event_observation.py")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        imported = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = imported
        try:
            with (
                mock.patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError("network access attempted"),
                ),
                mock.patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network access attempted"),
                ),
            ):
                spec.loader.exec_module(imported)
        finally:
            sys.modules.pop(module_name, None)
        self.assertTrue(
            hasattr(imported, "build_campaign_event_observations")
        )


if __name__ == "__main__":
    unittest.main()
