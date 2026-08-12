import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from campaign_event_sources import manual_evidence_source_id
from campaign_event_updates_manual import (
    CampaignEventUpdatesManualError,
    campaign_event_update_id,
    load_campaign_event_updates_manual,
    normalize_campaign_event_updates_manual,
    validate_campaign_event_updates_manual,
)
from campaign_events_contract import campaign_event_id


ROOT = Path(__file__).resolve().parent
EVENT_KEY = "manual-00000000000000000000000000000001"
SECOND_EVENT_KEY = "manual-00000000000000000000000000000002"
UPDATE_KEY = "update-00000000000000000000000000000001"
SECOND_UPDATE_KEY = "update-00000000000000000000000000000002"


def manual_event(**changes):
    event = {
        "event_key": EVENT_KEY,
        "title": "Grand débat présidentiel",
        "date": "2026-08-27",
        "event_type": "debate",
        "source_url": "https://example.com/politique/debat-2027",
        "source_publisher": "Example Média",
        "source_type": "reliable_media",
        "last_verified_at": "2026-08-11T10:00:00Z",
    }
    event.update(changes)
    return event


def update_record(**changes):
    update = {
        "update_key": UPDATE_KEY,
        "event_key": EVENT_KEY,
        "update_type": "NEW",
        "headline": "Un grand débat présidentiel a été annoncé.",
        "source_url": "https://example.com/politique/debat-2027",
        "source_publisher": "Example Média",
        "source_type": "reliable_media",
        "observed_at": "2026-08-11T10:00:00Z",
    }
    update.update(changes)
    return update


def update_payload(*updates):
    return {"schema_version": "1.0", "updates": list(updates)}


class CampaignEventUpdatesManualTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.manual_events_path = Path(self.temp_dir.name) / "events.json"
        self.write_events(manual_event())

    def write_events(self, *events):
        self.manual_events_path.write_text(
            json.dumps({"schema_version": "1.0", "events": list(events)}),
            encoding="utf-8",
        )

    def normalize(self, *updates):
        return normalize_campaign_event_updates_manual(
            update_payload(*updates),
            manual_events_path=self.manual_events_path,
        )

    def assert_update_invalid(self, update, pattern=None):
        with self.assertRaisesRegex(
            CampaignEventUpdatesManualError,
            pattern or ".*",
        ):
            self.normalize(update)

    def test_empty_input_is_valid(self):
        self.assertEqual(self.normalize(), [])

        updates_path = Path(self.temp_dir.name) / "updates.json"
        updates_path.write_text(
            json.dumps(update_payload()),
            encoding="utf-8",
        )
        self.assertEqual(
            load_campaign_event_updates_manual(
                updates_path,
                manual_events_path=self.manual_events_path,
            ),
            [],
        )
        validate_campaign_event_updates_manual(
            update_payload(),
            manual_events_path=self.manual_events_path,
        )

    def test_valid_new_update(self):
        record = self.normalize(update_record())[0]
        self.assertEqual(record["update_type"], "NEW")
        self.assertEqual(record["event_key"], EVENT_KEY)
        self.assertEqual(
            set(record["evidence"][0]),
            {"source_id", "source_url", "source_publisher", "source_type"},
        )

    def test_valid_confirmed_update(self):
        record = self.normalize(update_record(update_type="CONFIRMED"))[0]
        self.assertEqual(record["update_type"], "CONFIRMED")

    def test_valid_updated_update(self):
        record = self.normalize(update_record(update_type="UPDATED"))[0]
        self.assertEqual(record["update_type"], "UPDATED")

    def test_valid_postponed_update(self):
        for status in ("scheduled", "postponed"):
            with self.subTest(status=status):
                self.write_events(manual_event(status=status))
                record = self.normalize(update_record(update_type="POSTPONED"))[0]
                self.assertEqual(record["update_type"], "POSTPONED")

    def test_valid_cancelled_update(self):
        for status in ("scheduled", "cancelled"):
            with self.subTest(status=status):
                self.write_events(manual_event(status=status))
                record = self.normalize(update_record(update_type="CANCELLED"))[0]
                self.assertEqual(record["update_type"], "CANCELLED")

    def test_unknown_event_key_fails(self):
        self.assert_update_invalid(
            update_record(
                event_key="manual-ffffffffffffffffffffffffffffffff"
            ),
            "does not reference",
        )

    def test_malformed_update_key_fails(self):
        for key in (
            "update-abc",
            "update-0000000000000000000000000000000G",
            "other-00000000000000000000000000000001",
            "update-000000000000000000000000000000001",
        ):
            with self.subTest(key=key):
                self.assert_update_invalid(update_record(update_key=key), "update_key")

    def test_duplicate_update_key_fails(self):
        with self.assertRaisesRegex(CampaignEventUpdatesManualError, "duplicate"):
            self.normalize(update_record(), update_record(headline="Titre corrigé"))

    def test_invalid_update_type_fails(self):
        self.assert_update_invalid(update_record(update_type="COMMENTARY"), "update_type")

    def test_malformed_observed_at_fails(self):
        for observed_at in (
            "2026-08-11T10:00Z",
            "2026-08-11T10:00:00+00:00",
            "2026-02-30T10:00:00Z",
            "2026-08-11 10:00:00Z",
        ):
            with self.subTest(observed_at=observed_at):
                self.assert_update_invalid(
                    update_record(observed_at=observed_at),
                    "observed_at",
                )

    def test_http_source_url_fails(self):
        self.assert_update_invalid(
            update_record(source_url="http://example.com/event"),
            "source_url",
        )

    def test_credentials_port_and_fragment_source_urls_fail(self):
        for url in (
            "https://user@example.com/event",
            "https://example.com:443/event",
            "https://example.com/event#details",
        ):
            with self.subTest(url=url):
                self.assert_update_invalid(update_record(source_url=url), "source_url")

    def test_source_id_is_deterministic(self):
        record = self.normalize(update_record())[0]
        expected = manual_evidence_source_id(
            "reliable_media",
            "Example Média",
            "https://example.com/another-path",
        )
        self.assertRegex(expected, r"\Amanual-[0-9a-f]{16}\Z")
        self.assertEqual(record["evidence"][0]["source_id"], expected)

    def test_update_id_is_deterministic(self):
        first = campaign_event_update_id(UPDATE_KEY)
        repeated = campaign_event_update_id(UPDATE_KEY)
        other = campaign_event_update_id(SECOND_UPDATE_KEY)
        self.assertRegex(first, r"\Acew-[0-9a-f]{24}\Z")
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other)

    def test_headline_correction_preserves_update_id(self):
        first = self.normalize(update_record())[0]
        corrected = self.normalize(update_record(headline="Titre factuel corrigé."))[0]
        self.assertEqual(first["update_id"], corrected["update_id"])

    def test_source_url_correction_preserves_update_id(self):
        first = self.normalize(update_record())[0]
        corrected = self.normalize(
            update_record(source_url="https://other.example/corrected")
        )[0]
        self.assertEqual(first["update_id"], corrected["update_id"])
        self.assertNotEqual(
            first["evidence"][0]["source_id"],
            corrected["evidence"][0]["source_id"],
        )

    def test_event_schedule_correction_preserves_update_id(self):
        first = self.normalize(update_record())[0]
        self.write_events(manual_event(date="2026-09-03", time="20:00"))
        corrected = self.normalize(update_record())[0]
        self.assertEqual(first["update_id"], corrected["update_id"])

    def test_input_order_normalizes_deterministically(self):
        self.write_events(
            manual_event(),
            manual_event(
                event_key=SECOND_EVENT_KEY,
                title="Meeting public",
                date="2026-09-03",
                event_type="public_meeting",
            ),
        )
        earlier = update_record(
            update_key=UPDATE_KEY,
            observed_at="2026-08-11T09:00:00Z",
        )
        later_high_id = update_record(
            update_key=SECOND_UPDATE_KEY,
            event_key=SECOND_EVENT_KEY,
            observed_at="2026-08-11T11:00:00Z",
        )
        later_low_id = update_record(
            update_key="update-00000000000000000000000000000000",
            event_key=SECOND_EVENT_KEY,
            observed_at="2026-08-11T11:00:00Z",
        )
        first = self.normalize(earlier, later_high_id, later_low_id)
        second = self.normalize(later_low_id, earlier, later_high_id)
        self.assertEqual(first, second)
        self.assertEqual(
            [record["update_id"] for record in first],
            sorted(
                [
                    campaign_event_update_id(SECOND_UPDATE_KEY),
                    campaign_event_update_id(
                        "update-00000000000000000000000000000000"
                    ),
                ]
            )
            + [campaign_event_update_id(UPDATE_KEY)],
        )

    def test_same_timestamp_latest_selection_uses_update_id(self):
        lower_key, higher_key = sorted(
            (UPDATE_KEY, SECOND_UPDATE_KEY),
            key=campaign_event_update_id,
        )
        lower_id_cancelled = update_record(
            update_key=lower_key,
            update_type="CANCELLED",
            headline="Lower-ID cancellation report",
            observed_at="2026-08-11T10:00:00Z",
        )
        higher_id_new = update_record(
            update_key=higher_key,
            update_type="NEW",
            headline="Higher-ID announcement",
            observed_at="2026-08-11T10:00:00Z",
        )

        first = self.normalize(lower_id_cancelled, higher_id_new)
        reversed_input = self.normalize(higher_id_new, lower_id_cancelled)

        self.assertEqual(first, reversed_input)
        self.assertEqual(
            [record["update_id"] for record in first],
            sorted(record["update_id"] for record in first),
        )

    def test_generated_event_id_matches_campaign_event_id(self):
        record = self.normalize(update_record())[0]
        self.assertEqual(
            record["event_id"],
            campaign_event_id("campaign_events", EVENT_KEY),
        )

    def test_unknown_source_type_fails(self):
        self.assert_update_invalid(
            update_record(source_type="social_media"),
            "source_type",
        )

    def test_empty_or_whitespace_headline_fails(self):
        for headline in ("", " \t\n "):
            with self.subTest(headline=headline):
                self.assert_update_invalid(update_record(headline=headline), "headline")

    def test_empty_publisher_fails(self):
        self.assert_update_invalid(
            update_record(source_publisher=" \t "),
            "source_publisher",
        )

    def test_status_consistency_is_lightweight_and_explicit(self):
        cases = (
            ("NEW", "completed"),
            ("CONFIRMED", "postponed"),
            ("UPDATED", "completed"),
            ("POSTPONED", "cancelled"),
            ("CANCELLED", "postponed"),
        )
        for update_type, status in cases:
            with self.subTest(update_type=update_type, status=status):
                self.write_events(manual_event(status=status))
                self.assert_update_invalid(
                    update_record(update_type=update_type),
                    "inconsistent",
                )

    def test_loader_recomputes_source_id_without_accepting_one(self):
        candidate = update_record()
        candidate["source_id"] = "manual-0000000000000000"
        self.assert_update_invalid(candidate, "unexpected")

    def test_input_objects_are_not_mutated(self):
        payload = update_payload(update_record())
        before = copy.deepcopy(payload)
        normalize_campaign_event_updates_manual(
            payload,
            manual_events_path=self.manual_events_path,
        )
        self.assertEqual(payload, before)


if __name__ == "__main__":
    unittest.main()
