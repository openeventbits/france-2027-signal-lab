import copy
import hashlib
import json
import shutil
import socket
import unittest
import uuid
from pathlib import Path
from unittest import mock
import campaign_events_contract as contract

from campaign_events_contract import (
    CampaignEventsContractError,
    campaign_event_id,
    normalize_campaign_events_artifact,
    serialize_campaign_events,
    validate_campaign_events_artifact,
)


GENERATED_AT = "2026-08-01T10:00:00Z"
DATA_AS_OF = "2026-08-01T09:00:00Z"
ROOT = Path(__file__).resolve().parent


def first_party_evidence(source_id="candidate-calendar"):
    return {
        "source_id": source_id,
        "source_url": f"https://{source_id}.example.org/events/meeting",
        "source_publisher": "Candidate Calendar",
        "source_type": "candidate_first_party",
        "evidence_type": "explicit_schedule",
        "source_published_at": "2026-07-30T08:00:00Z",
    }


def media_evidence(source_id, publisher):
    return {
        "source_id": source_id,
        "source_url": f"https://{source_id}.example.org/politics/event",
        "source_publisher": publisher,
        "source_type": "reliable_media",
        "evidence_type": "explicit_schedule",
        "source_published_at": "2026-07-31T07:00:00Z",
    }


def official_evidence(source_id="official-calendar"):
    return {
        "source_id": source_id,
        "source_url": f"https://{source_id}.example.org/election/calendar",
        "source_publisher": "Official Authority",
        "source_type": "official_structured",
        "evidence_type": "official_rule_derivation",
        "source_published_at": "2026-07-29T06:00:00Z",
    }


def organizer_evidence():
    return {
        "source_id": "organizer-calendar",
        "source_url": "https://organizer-calendar.example.org/events/meeting",
        "source_publisher": "Organizer Calendar",
        "source_type": "organizer_first_party",
        "evidence_type": "explicit_schedule",
        "source_published_at": "2026-07-30T08:00:00Z",
    }


def registered_source(
    source_id,
    publisher,
    source_type,
    *,
    hostname=None,
    allowed_lanes=None,
    allowed_event_types=None,
    enabled=True,
    candidate_ids=None,
    organization=None,
):
    lanes = allowed_lanes or ["campaign_events"]
    event_types = allowed_event_types or [
        "rally",
        "public_meeting",
        "debate",
        "candidate_visit",
        "campaign_launch",
    ]
    source = {
        "source_id": source_id,
        "publisher": publisher,
        "source_type": source_type,
        "url": f"https://{hostname or source_id + '.example.org'}/registry",
        "allowed_lanes": lanes,
        "allowed_event_types": event_types,
        "enabled": enabled,
        "required": False,
        "refresh_class": "daily",
        "zero_result_valid": True,
    }
    if "campaign_events" in lanes:
        source["collection"] = {
            "discovery_method": "structured_html",
            "parser_family": "structured_html",
            "attribution_policy": "explicit_participant",
        }
    if candidate_ids is not None:
        source["candidate_ids"] = candidate_ids
    if organization is not None:
        source["organization"] = organization
    return source


def campaign_event(
    event_key="bruno-rennes-meeting",
    *,
    event_type="public_meeting",
    title="Réunion publique à Rennes",
    candidate_ids=None,
    candidate_names=None,
    scheduled_start="2027-01-15",
    time_precision="date",
    evidence=None,
    **changes,
):
    if candidate_ids is None:
        candidate_ids = ["bruno-retailleau"]
    if candidate_names is None:
        candidate_names = ["Bruno Retailleau"]
    event = {
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "event_type": event_type,
        "title": title,
        "candidate_ids": candidate_ids,
        "candidate_names": candidate_names,
        "scheduled_start": scheduled_start,
        "time_precision": time_precision,
        "timezone": "Europe/Paris",
        "status": "scheduled",
        "status_as_of": "2026-08-01",
        "evidence_status": "verified",
        "last_verified_at": "2026-08-01T09:00:00Z",
        "evidence": [first_party_evidence()] if evidence is None else evidence,
    }
    event.update(changes)
    return event


def institutional_event(
    event_key="first-round-2027",
    *,
    event_type="first_round",
    scheduled_start="2027-04-11",
    evidence=None,
    **changes,
):
    event = {
        "event_key": event_key,
        "event_id": campaign_event_id("institutional_milestones", event_key),
        "event_type": event_type,
        "title": "Premier tour",
        "candidate_ids": [],
        "candidate_names": [],
        "scheduled_start": scheduled_start,
        "time_precision": "date",
        "timezone": "Europe/Paris",
        "status": "scheduled",
        "status_as_of": "2026-08-01",
        "evidence_status": "verified",
        "last_verified_at": "2026-08-01T09:00:00Z",
        "evidence": [official_evidence()] if evidence is None else evidence,
    }
    event.update(changes)
    return event


def artifact(campaign_events=None, institutional_milestones=None, **changes):
    payload = {
        "schema_version": "1.0",
        "generated_at": GENERATED_AT,
        "data_as_of": DATA_AS_OF,
        "campaign_events": [] if campaign_events is None else campaign_events,
        "institutional_milestones": (
            [] if institutional_milestones is None else institutional_milestones
        ),
    }
    payload.update(changes)
    return payload


class CampaignEventsContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary_root = ROOT / f".campaign-events-contract-test-{uuid.uuid4().hex}"
        self.temporary_root.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary_root, True)
        self.registry_path = self.write_registry(
            "approved-sources.json",
            [
                registered_source(
                    "a-media", "A Media", "reliable_media"
                ),
                registered_source(
                    "candidate-calendar",
                    "Candidate Calendar",
                    "candidate_first_party",
                    candidate_ids=["bruno-retailleau", "david-lisnard"],
                ),
                registered_source(
                    "disabled-media",
                    "Disabled Media",
                    "reliable_media",
                    enabled=False,
                ),
                registered_source(
                    "official-calendar",
                    "Official Authority",
                    "official_structured",
                    allowed_lanes=["institutional_milestones"],
                    allowed_event_types=[
                        "sponsorship_deadline",
                        "official_candidate_list",
                        "campaign_period_boundary",
                        "first_round",
                        "second_round",
                    ],
                ),
                registered_source(
                    "one-media", "One Media", "reliable_media"
                ),
                registered_source(
                    "organizer-calendar",
                    "Organizer Calendar",
                    "organizer_first_party",
                    organization="Organizer",
                ),
                registered_source(
                    "rally-only-calendar",
                    "Rally Calendar",
                    "candidate_first_party",
                    allowed_event_types=["rally"],
                    candidate_ids=["bruno-retailleau"],
                ),
                registered_source(
                    "two-media", "Two Media", "reliable_media"
                ),
                registered_source(
                    "z-media", "Z Media", "reliable_media"
                ),
            ],
        )
        self.empty_registry_path = self.write_registry(
            "empty-sources.json",
            [],
        )

    def write_registry(self, name, sources):
        target = self.temporary_root / name
        payload = {
            "schema_version": "2.0",
            "sources": sorted(sources, key=lambda source: source["source_id"]),
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def assert_invalid(self, payload, pattern=None, source_registry_path=None):
        context = self.assertRaises(CampaignEventsContractError)
        with context:
            normalize_campaign_events_artifact(
                payload,
                source_registry_path=source_registry_path or self.registry_path,
            )
        if pattern is not None:
            self.assertRegex(str(context.exception), pattern)

    def canonical(self, payload, source_registry_path=None):
        return normalize_campaign_events_artifact(
            payload,
            source_registry_path=source_registry_path or self.registry_path,
        )

    def serialize(self, payload, source_registry_path=None):
        return serialize_campaign_events(
            payload,
            source_registry_path=source_registry_path or self.registry_path,
        )

    def validate(self, payload, source_registry_path=None):
        validate_campaign_events_artifact(
            payload,
            source_registry_path=source_registry_path or self.registry_path,
        )

    def test_single_media_observation_can_normalize_before_reconciliation(self):
        event = campaign_event(
            event_key="media-observation-2026-08-27-1645-debate",
            event_type="debate",
            title="Présidentielle 2027 : débat sur LCI",
            scheduled_start="2026-08-27T16:45:00+02:00",
            time_precision="datetime",
            evidence=[media_evidence("a-media", "A Media")],
        )

        with self.assertRaises(CampaignEventsContractError):
            normalize_campaign_events_artifact(
                artifact(campaign_events=[event]),
                source_registry_path=self.registry_path,
            )

        normalized = contract.normalize_campaign_event_observations(
            [event],
            source_registry_path=self.registry_path,
        )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["event_key"], event["event_key"])
        self.assertEqual(
            normalized[0]["evidence"][0]["source_id"],
            "a-media",
        )

    def test_deterministic_event_id_uses_exact_algorithm(self):
        lane = "campaign_events"
        event_key = "bruno-rennes-meeting"
        digest = hashlib.sha256(
            b"campaign-events:v1\0campaign_events\0bruno-rennes-meeting"
        ).hexdigest()
        expected = "ce-" + digest[:24]
        self.assertEqual(campaign_event_id(lane, event_key), expected)
        self.assertEqual(campaign_event_id(lane, event_key), expected)
        self.assertNotEqual(
            campaign_event_id("institutional_milestones", event_key),
            expected,
        )

    def test_event_id_is_recomputed_and_mismatches_are_rejected(self):
        event = campaign_event()
        event["event_id"] = "ce-" + "0" * 24
        self.assert_invalid(artifact([event]), "does not match")

    def test_stable_artifact_serialization(self):
        payload = artifact(
            [campaign_event()],
            [institutional_event()],
        )
        first = self.serialize(payload)
        second = self.serialize(copy.deepcopy(payload))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertIn("Réunion".encode("utf-8"), first)
        self.assertNotIn(b"\\u00e9", first)

    def test_exact_top_level_keys(self):
        missing = artifact()
        missing.pop("data_as_of")
        self.assert_invalid(missing, "exact allowed keys")
        extra = artifact(extra=True)
        self.assert_invalid(extra, "unexpected")

    def test_exact_event_keys(self):
        missing = campaign_event()
        missing.pop("status")
        self.assert_invalid(artifact([missing]), "missing")
        extra = campaign_event(confidence=0.9)
        self.assert_invalid(artifact([extra]), "unexpected")

    def test_exact_evidence_keys(self):
        missing_evidence = first_party_evidence()
        missing_evidence.pop("source_url")
        self.assert_invalid(
            artifact([campaign_event(evidence=[missing_evidence])]),
            "missing",
        )
        extra_evidence = first_party_evidence()
        extra_evidence["metadata"] = {}
        self.assert_invalid(
            artifact([campaign_event(evidence=[extra_evidence])]),
            "unexpected",
        )

    def test_empty_arrays_are_valid(self):
        payload = artifact()
        normalized = self.canonical(payload, self.empty_registry_path)
        self.assertEqual(normalized, payload)
        self.validate(payload, self.empty_registry_path)
        self.assertEqual(normalize_campaign_events_artifact(payload), payload)

    def test_nonempty_artifact_with_empty_registry_is_rejected(self):
        self.assert_invalid(
            artifact([campaign_event()]),
            "not in the approved source registry",
            self.empty_registry_path,
        )

    def test_default_production_registry_rejects_unregistered_artifact(self):
        with self.assertRaisesRegex(
            CampaignEventsContractError,
            "not in the approved source registry",
        ):
            normalize_campaign_events_artifact(artifact([campaign_event()]))

    def test_default_production_registry_accepts_official_milestone(self):
        evidence = [
            {
                "source_id": "interieur-presidential-calendar",
                "source_url": "https://www.elections.interieur.gouv.fr/scrutins/lelection-presidentielle",
                "source_publisher": "Ministère de l’Intérieur",
                "source_type": "official_unstructured",
                "evidence_type": "official_rule_derivation",
            },
            {
                "source_id": "vie-publique-presidential-calendar",
                "source_url": "https://www.vie-publique.fr/en-bref/303896-election-presidentielle-2027-les-dates-sont-connues",
                "source_publisher": "Vie publique",
                "source_type": "official_unstructured",
                "evidence_type": "official_rule_derivation",
            },
        ]
        event = institutional_event(
            event_key="presidential-2027-first-round",
            scheduled_start="2027-04-18",
            evidence=evidence,
        )
        normalized = normalize_campaign_events_artifact(
            artifact(institutional_milestones=[event])
        )
        self.assertEqual(
            normalized["institutional_milestones"][0]["scheduled_start"],
            "2027-04-18",
        )

    def test_unknown_and_disabled_sources_are_rejected(self):
        unknown = first_party_evidence()
        unknown.update(
            {
                "source_id": "fabricated-source",
                "source_url": "https://fabricated-source.example.org/event",
                "source_publisher": "Fabricated Source",
            }
        )
        self.assert_invalid(
            artifact([campaign_event(evidence=[unknown])]),
            "not in the approved source registry",
        )
        disabled = media_evidence("disabled-media", "Disabled Media")
        self.assert_invalid(
            artifact([campaign_event(evidence=[disabled])]),
            "disabled",
        )

    def test_source_type_and_publisher_must_match_registry(self):
        wrong_type = first_party_evidence()
        wrong_type["source_type"] = "party_first_party"
        self.assert_invalid(
            artifact([campaign_event(evidence=[wrong_type])]),
            "source_type does not match",
        )
        wrong_publisher = first_party_evidence()
        wrong_publisher["source_publisher"] = "Candidate Calendar Alias"
        self.assert_invalid(
            artifact([campaign_event(evidence=[wrong_publisher])]),
            "source_publisher does not match",
        )

    def test_registry_lane_and_event_type_permissions_are_enforced(self):
        candidate_source = first_party_evidence()
        self.assert_invalid(
            artifact(
                institutional_milestones=[
                    institutional_event(evidence=[candidate_source])
                ]
            ),
            "not approved for lane",
        )
        rally_only = first_party_evidence()
        rally_only.update(
            {
                "source_id": "rally-only-calendar",
                "source_url": "https://rally-only-calendar.example.org/event",
                "source_publisher": "Rally Calendar",
            }
        )
        self.assert_invalid(
            artifact([campaign_event(evidence=[rally_only])]),
            "not approved for event_type",
        )

    def test_registry_hostname_requires_exact_match_but_not_exact_path(self):
        wrong_hostname = first_party_evidence()
        wrong_hostname["source_url"] = (
            "https://events.candidate-calendar.example.org/event"
        )
        self.assert_invalid(
            artifact([campaign_event(evidence=[wrong_hostname])]),
            "hostname does not exactly match",
        )
        evidence = first_party_evidence()
        self.assertNotEqual(evidence["source_url"].split("/", 3)[-1], "registry")
        normalized = self.canonical(
            artifact([campaign_event(evidence=[evidence])])
        )
        self.assertEqual(
            normalized["campaign_events"][0]["evidence"][0]["source_url"],
            evidence["source_url"],
        )

    def test_candidate_first_party_ownership_must_relate_to_event(self):
        unrelated = campaign_event(
            candidate_ids=["gabriel-attal"],
            candidate_names=["Gabriel Attal"],
        )
        self.assert_invalid(
            artifact([unrelated]),
            "unrelated to every event candidate",
        )
        related_multi_candidate = campaign_event(
            candidate_ids=["gabriel-attal", "bruno-retailleau"],
            candidate_names=["Gabriel Attal", "Bruno Retailleau"],
        )
        self.canonical(artifact([related_multi_candidate]))

    def test_source_registry_validation_performs_no_network_access(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ):
            normalized = self.canonical(artifact([campaign_event()]))
        self.assertEqual(len(normalized["campaign_events"]), 1)

    def test_campaign_events_require_candidates(self):
        event = campaign_event(candidate_ids=[], candidate_names=[])
        self.assert_invalid(artifact([event]), "at least one candidate")

    def test_institutional_milestones_are_candidate_free(self):
        event = institutional_event(
            candidate_ids=["bruno-retailleau"],
            candidate_names=["Bruno Retailleau"],
        )
        self.assert_invalid(
            artifact(institutional_milestones=[event]),
            "candidate-free",
        )

    def test_candidate_identity_requires_registry_parity(self):
        wrong_name = campaign_event(candidate_names=["B. Retailleau"])
        self.assert_invalid(artifact([wrong_name]), "canonical identity")
        unknown = campaign_event(
            candidate_ids=["unknown-person"],
            candidate_names=["Unknown Person"],
        )
        self.assert_invalid(artifact([unknown]), "not canonical")

    def test_multi_candidate_events_are_supported_and_pairs_are_sorted(self):
        event = campaign_event(
            candidate_ids=["david-lisnard", "bruno-retailleau"],
            candidate_names=["David Lisnard", "Bruno Retailleau"],
        )
        normalized = self.canonical(artifact([event]))
        stored = normalized["campaign_events"][0]
        self.assertEqual(
            stored["candidate_ids"],
            ["bruno-retailleau", "david-lisnard"],
        )
        self.assertEqual(
            stored["candidate_names"],
            ["Bruno Retailleau", "David Lisnard"],
        )
        self.validate(normalized)

    def test_duplicate_candidates_are_rejected(self):
        event = campaign_event(
            candidate_ids=["bruno-retailleau", "bruno-retailleau"],
            candidate_names=["Bruno Retailleau", "Bruno Retailleau"],
        )
        self.assert_invalid(artifact([event]), "duplicate candidate IDs")

    def test_date_only_events_remain_date_only(self):
        payload = artifact([campaign_event(scheduled_start="2027-02-03")])
        normalized = self.canonical(payload)
        self.assertEqual(
            normalized["campaign_events"][0]["scheduled_start"],
            "2027-02-03",
        )
        self.assertNotIn(b"2027-02-03T00:00:00", self.serialize(payload))

    def test_datetime_events_accept_correct_winter_and_summer_offsets(self):
        winter = campaign_event(
            "winter-meeting",
            scheduled_start="2027-01-15T19:30:00+01:00",
            time_precision="datetime",
        )
        summer = campaign_event(
            "summer-meeting",
            scheduled_start="2027-07-15T19:30:00+02:00",
            time_precision="datetime",
        )
        normalized = self.canonical(artifact([summer, winter]))
        self.assertEqual(len(normalized["campaign_events"]), 2)

    def test_invalid_paris_dst_offsets_are_rejected(self):
        for timestamp in (
            "2027-01-15T19:30:00+02:00",
            "2027-07-15T19:30:00+01:00",
            "2027-03-28T02:30:00+02:00",
        ):
            with self.subTest(timestamp=timestamp):
                self.assert_invalid(
                    artifact(
                        [
                            campaign_event(
                                scheduled_start=timestamp,
                                time_precision="datetime",
                            )
                        ]
                    ),
                    "Europe/Paris",
                )

    def test_invalid_dates_and_timestamps_are_rejected(self):
        self.assert_invalid(
            artifact([campaign_event(scheduled_start="2027-02-30")]),
            "valid canonical",
        )
        self.assert_invalid(
            artifact(
                [
                    campaign_event(
                        scheduled_start="2027-01-15T19:30+01:00",
                        time_precision="datetime",
                    )
                ]
            ),
            "with seconds",
        )
        for field, value in (
            ("generated_at", "2026-08-01T10:00:00.000Z"),
            ("data_as_of", "2026-08-01T11:00:00+02:00"),
        ):
            with self.subTest(field=field):
                self.assert_invalid(artifact(**{field: value}), "UTC RFC 3339")
        event = campaign_event(last_verified_at="2026-08-01")
        self.assert_invalid(artifact([event]), "last_verified_at")

    def test_unknown_time_cannot_be_synthesized_as_midnight(self):
        event = campaign_event(
            scheduled_start="2027-02-03T00:00:00",
            time_precision="date",
        )
        self.assert_invalid(artifact([event]), "YYYY-MM-DD")

    def test_scheduled_end_requires_matching_precision_and_order(self):
        wrong_precision = campaign_event(
            scheduled_end="2027-01-16T10:00:00+01:00",
        )
        self.assert_invalid(artifact([wrong_precision]), "YYYY-MM-DD")
        before = campaign_event(scheduled_end="2027-01-14")
        self.assert_invalid(artifact([before]), "must not precede")
        valid_datetime = campaign_event(
            scheduled_start="2027-01-15T19:30:00+01:00",
            scheduled_end="2027-01-15T21:00:00+01:00",
            time_precision="datetime",
        )
        normalized = self.canonical(artifact([valid_datetime]))
        self.assertEqual(
            normalized["campaign_events"][0]["scheduled_end"],
            "2027-01-15T21:00:00+01:00",
        )

    def test_event_type_vocabularies_are_lane_specific(self):
        campaign_types = (
            "rally",
            "public_meeting",
            "debate",
            "candidate_visit",
            "campaign_launch",
        )
        institutional_types = (
            "sponsorship_deadline",
            "official_candidate_list",
            "campaign_period_boundary",
            "first_round",
            "second_round",
        )
        for event_type in campaign_types:
            with self.subTest(event_type=event_type):
                self.canonical(artifact([campaign_event(event_type=event_type)]))
        for event_type in institutional_types:
            with self.subTest(event_type=event_type):
                self.canonical(
                    artifact(
                        institutional_milestones=[
                            institutional_event(event_type=event_type)
                        ]
                    )
                )
        self.assert_invalid(
            artifact([campaign_event(event_type="first_round")]),
            "not allowed",
        )

    def test_lifecycle_status_and_evidence_status_are_controlled(self):
        for status in ("scheduled", "postponed", "cancelled", "completed"):
            self.canonical(artifact([campaign_event(status=status)]))
        for evidence_status in ("verified", "stale", "past_unconfirmed"):
            self.canonical(
                artifact([campaign_event(evidence_status=evidence_status)])
            )
        self.assert_invalid(
            artifact([campaign_event(status="rumoured")]),
            "status is not allowed",
        )
        self.assert_invalid(
            artifact([campaign_event(evidence_status="likely")]),
            "evidence_status is not allowed",
        )

    def test_evidence_source_and_evidence_types_are_controlled(self):
        bad_source = first_party_evidence()
        bad_source["source_type"] = "social_media"
        self.assert_invalid(
            artifact([campaign_event(evidence=[bad_source])]),
            "source_type is not allowed",
        )
        bad_evidence = first_party_evidence()
        bad_evidence["evidence_type"] = "inferred_date"
        self.assert_invalid(
            artifact([campaign_event(evidence=[bad_evidence])]),
            "evidence_type is not allowed",
        )
        organizer = organizer_evidence()
        self.canonical(artifact([campaign_event(evidence=[organizer])]))

    def test_evidence_urls_must_be_valid_absolute_https(self):
        for url in (
            "http://source.example.org/event",
            "/event",
            "https://bad_host.example.org/event",
        ):
            evidence = first_party_evidence()
            evidence["source_url"] = url
            with self.subTest(url=url):
                self.assert_invalid(
                    artifact([campaign_event(evidence=[evidence])]),
                    "source_url",
                )

    def test_evidence_must_be_unique(self):
        evidence = first_party_evidence()
        self.assert_invalid(
            artifact([campaign_event(evidence=[evidence, copy.deepcopy(evidence)])]),
            "duplicate record",
        )
        second = copy.deepcopy(evidence)
        second["source_id"] = "different-id"
        self.assert_invalid(
            artifact([campaign_event(evidence=[evidence, second])]),
            "duplicate source URL",
        )

    def test_evidence_ordering_is_deterministic(self):
        a = media_evidence("a-media", "A Media")
        z = media_evidence("z-media", "Z Media")
        event = campaign_event(evidence=[z, a])
        normalized = self.canonical(artifact([event]))
        self.assertEqual(
            [
                item["source_id"]
                for item in normalized["campaign_events"][0]["evidence"]
            ],
            ["a-media", "z-media"],
        )

    def test_official_milestones_require_official_evidence(self):
        self.canonical(
            artifact(institutional_milestones=[institutional_event()])
        )
        media_registry = self.write_registry(
            "institutional-media.json",
            [
                registered_source(
                    "one-media",
                    "One Media",
                    "reliable_media",
                    allowed_lanes=["institutional_milestones"],
                    allowed_event_types=["first_round"],
                )
            ],
        )
        self.assert_invalid(
            artifact(
                institutional_milestones=[
                    institutional_event(
                        evidence=[media_evidence("one-media", "One Media")]
                    )
                ]
            ),
            "official evidence",
            media_registry,
        )

    def test_first_party_campaign_evidence_is_sufficient(self):
        normalized = self.canonical(artifact([campaign_event()]))
        self.assertEqual(len(normalized["campaign_events"]), 1)

    def test_two_independent_media_sources_are_sufficient(self):
        event = campaign_event(
            evidence=[
                media_evidence("one-media", "One Media"),
                media_evidence("two-media", "Two Media"),
            ]
        )
        self.canonical(artifact([event]))

    def test_single_or_nonindependent_media_source_is_insufficient(self):
        single = campaign_event(
            evidence=[media_evidence("one-media", "One Media")]
        )
        self.assert_invalid(artifact([single]), "two independent")
        same_publisher_registry = self.write_registry(
            "same-publisher-media.json",
            [
                registered_source(
                    "one-media", "Same Publisher", "reliable_media"
                ),
                registered_source(
                    "two-media", "Same Publisher", "reliable_media"
                ),
            ],
        )
        same_publisher = campaign_event(
            evidence=[
                media_evidence("one-media", "Same Publisher"),
                media_evidence("two-media", "Same Publisher"),
            ]
        )
        self.assert_invalid(
            artifact([same_publisher]),
            "two independent",
            same_publisher_registry,
        )

    def test_fabricated_source_aliases_cannot_manufacture_independence(self):
        fabricated_alias = media_evidence("one-media-alias", "Alias Media")
        event = campaign_event(
            evidence=[
                media_evidence("one-media", "One Media"),
                fabricated_alias,
            ]
        )
        self.assert_invalid(
            artifact([event]),
            "not in the approved source registry",
        )

    def test_source_publication_timestamp_is_not_the_event_date(self):
        evidence = first_party_evidence()
        evidence["source_published_at"] = "2026-01-02T03:04:05Z"
        event = campaign_event(
            scheduled_start="2027-05-06",
            evidence=[evidence],
        )
        normalized = self.canonical(artifact([event]))
        stored = normalized["campaign_events"][0]
        self.assertEqual(stored["scheduled_start"], "2027-05-06")
        self.assertEqual(
            stored["evidence"][0]["source_published_at"],
            "2026-01-02T03:04:05Z",
        )

    def test_duplicate_event_keys_are_rejected_across_lanes(self):
        campaign = campaign_event("shared-event-key")
        milestone = institutional_event("shared-event-key")
        self.assert_invalid(
            artifact([campaign], [milestone]),
            "duplicate event_key",
        )

    def test_duplicate_event_ids_are_rejected(self):
        event = campaign_event()
        self.assert_invalid(
            artifact([event, copy.deepcopy(event)]),
            "duplicate event_id",
        )

    def test_campaign_event_type_order_is_deterministic(self):
        event_types = [
            "rally",
            "public_meeting",
            "debate",
            "candidate_visit",
            "campaign_launch",
        ]
        events = [
            campaign_event(
                f"same-time-{event_type.replace('_', '-')}",
                event_type=event_type,
                scheduled_start="2027-05-01T18:00:00+02:00",
                time_precision="datetime",
            )
            for event_type in reversed(event_types)
        ]
        normalized = self.canonical(artifact(events))
        self.assertEqual(
            [event["event_type"] for event in normalized["campaign_events"]],
            event_types,
        )

    def test_event_ordering_is_deterministic(self):
        later = campaign_event("later-event", scheduled_start="2027-05-02")
        date_only = campaign_event("date-only", scheduled_start="2027-05-01")
        timed = campaign_event(
            "timed-event",
            scheduled_start="2027-05-01T18:00:00+02:00",
            time_precision="datetime",
        )
        normalized = self.canonical(artifact([later, date_only, timed]))
        self.assertEqual(
            [event["event_key"] for event in normalized["campaign_events"]],
            ["timed-event", "date-only", "later-event"],
        )
        self.validate(normalized)

    def test_optional_fields_are_validated(self):
        event = campaign_event(
            organization="Campaign Organization",
            location_name="Salle municipale",
            locality="Rennes",
            department="35",
        )
        normalized = self.canonical(artifact([event]))
        self.assertEqual(normalized["campaign_events"][0]["department"], "35")
        for field in ("organization", "location_name", "locality"):
            for value in (None, "", " padded "):
                with self.subTest(field=field, value=value):
                    self.assert_invalid(
                        artifact([campaign_event(**{field: value})]),
                        field,
                    )
        for department in ("20", "2a", "96", "975", 35, None):
            with self.subTest(department=department):
                self.assert_invalid(
                    artifact([campaign_event(department=department)]),
                    "INSEE department code",
                )

    def test_null_empty_and_placeholder_optional_values_are_not_serialized(self):
        stored = self.canonical(artifact([campaign_event()]))["campaign_events"][0]
        for field in (
            "scheduled_end",
            "organization",
            "location_name",
            "locality",
            "department",
        ):
            self.assertNotIn(field, stored)
        self.assert_invalid(
            artifact([campaign_event(scheduled_end=None)]),
            "scheduled_end",
        )

    def test_scoring_inference_and_llm_fields_are_rejected(self):
        for field, value in (
            ("confidence", 0.8),
            ("probability", 0.7),
            ("ranking", 1),
            ("inferred_date", "2027-01-15"),
            ("synthetic_score", 10),
            ("llm_rationale", "model output"),
        ):
            with self.subTest(field=field):
                self.assert_invalid(
                    artifact([campaign_event(**{field: value})]),
                    "unexpected",
                )
        evidence = first_party_evidence()
        evidence["raw_article_text"] = "not allowed"
        self.assert_invalid(
            artifact([campaign_event(evidence=[evidence])]),
            "unexpected",
        )

    def test_serialization_is_byte_identical_for_fixed_timestamps(self):
        payload = artifact(
            [
                campaign_event("z-event", scheduled_start="2027-06-02"),
                campaign_event("a-event", scheduled_start="2027-06-01"),
            ]
        )
        first = self.serialize(payload)
        second = self.serialize(copy.deepcopy(payload))
        self.assertEqual(first, second)

    def test_normalization_and_serialization_do_not_mutate_input(self):
        payload = artifact(
            [
                campaign_event(
                    candidate_ids=["david-lisnard", "bruno-retailleau"],
                    candidate_names=["David Lisnard", "Bruno Retailleau"],
                    evidence=[
                        media_evidence("z-media", "Z Media"),
                        media_evidence("a-media", "A Media"),
                    ],
                )
            ]
        )
        original = copy.deepcopy(payload)
        self.canonical(payload)
        self.serialize(payload)
        self.assertEqual(payload, original)


if __name__ == "__main__":
    unittest.main()
