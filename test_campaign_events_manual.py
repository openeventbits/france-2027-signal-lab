import copy
import json
import re
import unittest
from pathlib import Path

from campaign_event_institutional_seeds import (
    load_campaign_event_institutional_seeds,
)
from campaign_event_sources import manual_evidence_source_id
from campaign_events_contract import (
    CampaignEventsContractError,
    normalize_campaign_event_observations,
    normalize_campaign_events_artifact,
    validate_campaign_events_artifact,
)
from campaign_events_manual import (
    CampaignEventsManualError,
    load_campaign_events_manual,
    normalize_campaign_events_manual,
)


ROOT = Path(__file__).resolve().parent
EVENT_KEY = "manual-00000000000000000000000000000001"
SECOND_EVENT_KEY = "manual-00000000000000000000000000000002"
VERIFIED_AT = "2026-08-11T10:00:00Z"


def manual_event(**changes):
    event = {
        "event_key": EVENT_KEY,
        "title": "Grand débat présidentiel",
        "date": "2026-08-27",
        "event_type": "debate",
        "source_url": "https://example.com/politique/debat-2027",
        "source_publisher": "Example Média",
        "source_type": "reliable_media",
        "last_verified_at": VERIFIED_AT,
    }
    event.update(changes)
    return event


def manual_payload(*events):
    return {"schema_version": "1.0", "events": list(events)}


def artifact_for(events):
    return {
        "schema_version": "1.1",
        "generated_at": VERIFIED_AT,
        "data_as_of": VERIFIED_AT,
        "campaign_events": events,
        "institutional_milestones": [],
        "event_watch": [],
    }


class CampaignEventsManualTests(unittest.TestCase):
    def normalize(self, *events):
        return normalize_campaign_events_manual(manual_payload(*events))

    def assert_manual_invalid(self, event, pattern=None):
        with self.assertRaisesRegex(
            CampaignEventsManualError,
            pattern or ".*",
        ):
            self.normalize(event)

    def test_empty_manual_input_is_valid(self):
        self.assertEqual(normalize_campaign_events_manual(manual_payload()), [])
        self.assertEqual(
            load_campaign_events_manual(ROOT / "campaign_events_manual.json"),
            [],
        )

    def test_valid_dated_event(self):
        event = self.normalize(manual_event())[0]
        self.assertEqual(event["scheduled_start"], "2026-08-27")
        self.assertEqual(event["time_precision"], "date")
        self.assertEqual(event["timezone"], "Europe/Paris")
        self.assertEqual(event["status"], "scheduled")
        self.assertNotIn("participants", event)

    def test_valid_datetime_event(self):
        event = self.normalize(manual_event(time="18:30"))[0]
        self.assertEqual(event["scheduled_start"], "2026-08-27T18:30:00+02:00")
        self.assertEqual(event["time_precision"], "datetime")

    def test_date_only_never_becomes_midnight(self):
        event = self.normalize(manual_event())[0]
        self.assertEqual(event["scheduled_start"], "2026-08-27")
        self.assertNotIn("T00:00", json.dumps(event))

    def test_canonical_participant_links_correctly(self):
        event = self.normalize(manual_event(participants=["David Lisnard"]))[0]
        self.assertEqual(event["participants"], ["David Lisnard"])
        self.assertEqual(event["candidate_ids"], ["david-lisnard"])
        self.assertEqual(event["candidate_names"], ["David Lisnard"])

    def test_unknown_participant_survives_without_linkage(self):
        event = self.normalize(
            manual_event(participants=["Unknown Political Actor"])
        )[0]
        self.assertEqual(event["participants"], ["Unknown Political Actor"])
        self.assertEqual(event["candidate_ids"], [])
        self.assertEqual(event["candidate_names"], [])

    def test_mixed_canonical_and_unknown_participants(self):
        event = self.normalize(
            manual_event(
                participants=["Unknown Political Actor", "DAVID-LISNARD"]
            )
        )[0]
        self.assertEqual(
            event["participants"],
            ["DAVID-LISNARD", "Unknown Political Actor"],
        )
        self.assertEqual(event["candidate_ids"], ["david-lisnard"])
        self.assertEqual(event["candidate_names"], ["David Lisnard"])

    def test_surname_only_participant_is_retained_but_not_linked(self):
        event = self.normalize(manual_event(participants=["Lisnard"]))[0]
        self.assertEqual(event["participants"], ["Lisnard"])
        self.assertEqual(event["candidate_ids"], [])

    def test_invalid_event_key_fails(self):
        for key in (
            "manual-abc",
            "manual-0000000000000000000000000000000G",
            "other-00000000000000000000000000000001",
            "manual-000000000000000000000000000000001",
        ):
            with self.subTest(key=key):
                self.assert_manual_invalid(
                    manual_event(event_key=key),
                    "event_key",
                )

    def test_duplicate_event_key_fails(self):
        with self.assertRaisesRegex(CampaignEventsManualError, "duplicate"):
            self.normalize(manual_event(), manual_event(title="Corrected title"))

    def test_malformed_date_and_time_fail(self):
        cases = (
            {"date": "2026-8-27"},
            {"date": "2026-02-30"},
            {"time": "8:30"},
            {"time": "24:00"},
            {"date": "2026-03-29", "time": "02:30"},
            {"date": "2026-10-25", "time": "02:30"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assert_manual_invalid(manual_event(**changes))

    def test_invalid_and_http_source_urls_fail(self):
        for url in (
            "http://example.com/event",
            "example.com/event",
            "https://localhost/event",
            "https://bad_host.example/event",
        ):
            with self.subTest(url=url):
                self.assert_manual_invalid(manual_event(source_url=url), "source_url")

    def test_credentials_port_and_fragment_urls_fail(self):
        for url in (
            "https://user@example.com/event",
            "https://example.com:443/event",
            "https://example.com/event#details",
        ):
            with self.subTest(url=url):
                self.assert_manual_invalid(manual_event(source_url=url), "source_url")

    def test_manual_source_id_is_deterministic_and_origin_scoped(self):
        first = manual_evidence_source_id(
            "reliable_media",
            "Example Média",
            "https://EXAMPLE.com/one",
        )
        repeated = manual_evidence_source_id(
            "reliable_media",
            "example média",
            "https://example.com/two?x=1",
        )
        other_host = manual_evidence_source_id(
            "reliable_media",
            "Example Média",
            "https://other.example/two",
        )
        self.assertRegex(first, r"\Amanual-[0-9a-f]{16}\Z")
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other_host)

    def test_forged_manual_source_id_fails_final_contract(self):
        event = self.normalize(manual_event())[0]
        event["evidence"][0]["source_id"] = "manual-0000000000000000"
        with self.assertRaisesRegex(CampaignEventsContractError, "derived manual"):
            normalize_campaign_event_observations([event])

    def test_one_manual_reliable_media_source_is_sufficient(self):
        events = self.normalize(manual_event())
        normalized = normalize_campaign_events_artifact(artifact_for(events))
        self.assertEqual(len(normalized["campaign_events"]), 1)

    def test_one_registered_reliable_media_source_remains_insufficient(self):
        event = self.normalize(manual_event())[0]
        event["evidence"] = [
            {
                "source_id": "tf1-lci-debates",
                "source_url": (
                    "https://www.tf1info.fr/politique/"
                    "election-presidentielle-2027-lci-organisera-le-27-aout-"
                    "un-grand-debat-avec-sept-candidats-declares-ou-"
                    "pressentis-2455591.html"
                ),
                "source_publisher": "TF1 Info",
                "source_type": "reliable_media",
                "evidence_type": "explicit_schedule",
            }
        ]
        with self.assertRaisesRegex(
            CampaignEventsContractError,
            "two independent reliable-media",
        ):
            normalize_campaign_events_artifact(artifact_for([event]))

    def test_title_correction_preserves_event_id(self):
        first = self.normalize(manual_event())[0]
        corrected = self.normalize(manual_event(title="Titre corrigé"))[0]
        self.assertEqual(first["event_id"], corrected["event_id"])

    def test_source_url_correction_preserves_event_id(self):
        first = self.normalize(manual_event())[0]
        corrected = self.normalize(
            manual_event(source_url="https://other.example/corrected")
        )[0]
        self.assertEqual(first["event_id"], corrected["event_id"])
        self.assertNotEqual(
            first["evidence"][0]["source_id"],
            corrected["evidence"][0]["source_id"],
        )

    def test_participant_linkage_correction_preserves_event_id(self):
        first = self.normalize(manual_event(participants=["Unknown Actor"]))[0]
        corrected = self.normalize(manual_event(participants=["David Lisnard"]))[0]
        self.assertEqual(first["event_id"], corrected["event_id"])
        self.assertNotEqual(first["candidate_ids"], corrected["candidate_ids"])

    def test_location_correction_preserves_event_id(self):
        first = self.normalize(manual_event(location_name="Ancienne salle"))[0]
        corrected = self.normalize(manual_event(location_name="Nouvelle salle"))[0]
        self.assertEqual(first["event_id"], corrected["event_id"])

    def test_schedule_correction_preserves_event_id(self):
        first = self.normalize(manual_event(date="2026-08-27"))[0]
        corrected = self.normalize(
            manual_event(date="2026-09-03", time="20:00")
        )[0]
        self.assertEqual(first["event_id"], corrected["event_id"])

    def test_postponed_event_uses_status_update_evidence(self):
        event = self.normalize(manual_event(status="postponed"))[0]
        self.assertEqual(event["status"], "postponed")
        self.assertEqual(
            event["evidence"][0]["evidence_type"], "explicit_status_update"
        )

    def test_cancelled_event_uses_status_update_evidence(self):
        event = self.normalize(manual_event(status="cancelled"))[0]
        self.assertEqual(event["status"], "cancelled")
        self.assertEqual(
            event["evidence"][0]["evidence_type"], "explicit_status_update"
        )

    def test_completed_event_uses_status_update_evidence(self):
        event = self.normalize(manual_event(status="completed"))[0]
        self.assertEqual(event["status"], "completed")
        self.assertEqual(
            event["evidence"][0]["evidence_type"], "explicit_status_update"
        )

    def test_past_scheduled_event_is_unconfirmed_not_completed(self):
        event = self.normalize(
            manual_event(
                date="2026-08-01",
                last_verified_at="2026-08-02T10:00:00Z",
            )
        )[0]
        self.assertEqual(event["status"], "scheduled")
        self.assertEqual(event["evidence_status"], "past_unconfirmed")

    def test_input_ordering_normalizes_deterministically(self):
        later = manual_event(event_key=EVENT_KEY, date="2026-09-01")
        earlier = manual_event(
            event_key=SECOND_EVENT_KEY,
            title="Meeting public",
            date="2026-08-20",
            event_type="public_meeting",
        )
        first = self.normalize(later, earlier)
        second = self.normalize(earlier, later)
        self.assertEqual(first, second)
        self.assertEqual(
            [event["event_key"] for event in first],
            [SECOND_EVENT_KEY, EVENT_KEY],
        )

    def test_optional_fields_remain_absent_when_unknown(self):
        event = self.normalize(manual_event())[0]
        for field in (
            "participants",
            "organization",
            "location_name",
            "locality",
            "department",
        ):
            self.assertNotIn(field, event)

    def test_explicit_null_participants_are_rejected(self):
        self.assert_manual_invalid(
            manual_event(participants=None), "participants must be a list"
        )

    def test_institutional_milestone_validation_is_unchanged(self):
        seeds = load_campaign_event_institutional_seeds(
            ROOT / "campaign_event_institutional_seeds.json"
        )
        self.assertEqual(
            [seed["event_type"] for seed in seeds["seeds"]],
            ["first_round", "second_round"],
        )
        tracked = json.loads(
            (ROOT / "campaign_events.json").read_text(encoding="utf-8")
        )
        tracked["schema_version"] = "1.1"
        tracked["event_watch"] = []
        validate_campaign_events_artifact(tracked)

    def test_manual_source_id_cannot_enter_institutional_lane(self):
        tracked = json.loads(
            (ROOT / "campaign_events.json").read_text(encoding="utf-8")
        )
        tracked["schema_version"] = "1.1"
        tracked["event_watch"] = []
        milestone = copy.deepcopy(tracked["institutional_milestones"][0])
        evidence = milestone["evidence"][0]
        evidence["source_id"] = manual_evidence_source_id(
            evidence["source_type"],
            evidence["source_publisher"],
            evidence["source_url"],
        )
        candidate = copy.deepcopy(tracked)
        candidate["institutional_milestones"] = [milestone]
        with self.assertRaisesRegex(CampaignEventsContractError, "only allowed"):
            validate_campaign_events_artifact(candidate)


if __name__ == "__main__":
    unittest.main()
