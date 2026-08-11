import copy
import json
import os
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from add_campaign_event import (
    CampaignEventCurationError,
    build_add_proposal,
    persist_manual_documents,
    serialize_manual_document,
)
from campaign_events_contract import campaign_event_id
from update_campaign_event import (
    KEEP,
    REMOVE,
    build_update_proposal,
    run_update_interactive,
    sorted_events_for_selection,
)


EVENT_TIMESTAMP = "2026-08-11T10:00:00Z"
UPDATE_TIMESTAMP = "2026-08-12T10:00:00Z"


class UUIDSequence:
    def __init__(self, start=1):
        self.value = start

    def __call__(self):
        generated = uuid.UUID(int=self.value)
        self.value += 1
        return generated


def empty_events():
    return {"schema_version": "1.0", "events": []}


def empty_updates():
    return {"schema_version": "1.0", "updates": []}


def initial_facts(**changes):
    facts = {
        "title": "Presidential debate at MEDEF",
        "date": "2026-08-27",
        "time": "16:45",
        "event_type": "debate",
        "participants": "Gabriel Attal, Bruno Retailleau",
        "organization": "MEDEF",
        "location_name": "Roland-Garros",
        "locality": "Paris",
        "department": "75",
        "source_url": "https://example.com/original",
        "source_publisher": "Example Média",
        "source_type": "reliable_media",
    }
    facts.update(changes)
    return facts


def initial_proposal(**changes):
    return build_add_proposal(
        empty_events(),
        empty_updates(),
        initial_facts(**changes),
        timestamp=EVENT_TIMESTAMP,
        uuid_factory=UUIDSequence(),
    )


def update_source(**changes):
    source = {
        "source_url": "https://updates.example/change",
        "source_publisher": "Updates Média",
        "source_type": "reliable_media",
    }
    source.update(changes)
    return source


def build_update(base, action="UPDATED", changes=None, timestamp=UPDATE_TIMESTAMP, **kwargs):
    return build_update_proposal(
        base.events_payload,
        base.updates_payload,
        event_key=base.event["event_key"],
        action=action,
        changes={} if changes is None else changes,
        headline=kwargs.pop("headline", base.event["title"]),
        source=kwargs.pop("source", update_source()),
        timestamp=timestamp,
        uuid_factory=kwargs.pop("uuid_factory", UUIDSequence(20)),
        **kwargs,
    )


class UpdateCampaignEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.events_path = Path(self.temp_dir.name) / "campaign_events_manual.json"
        self.updates_path = (
            Path(self.temp_dir.name) / "campaign_event_updates_manual.json"
        )
        self.base = initial_proposal()
        self.write_documents(self.base.events_payload, self.base.updates_payload)

    def write_documents(self, events, updates):
        self.events_path.write_bytes(serialize_manual_document(events))
        self.updates_path.write_bytes(serialize_manual_document(updates))

    def read_documents(self):
        return (
            json.loads(self.events_path.read_text(encoding="utf-8")),
            json.loads(self.updates_path.read_text(encoding="utf-8")),
        )

    def assert_completed_action_rejected(self, action):
        completed_events = copy.deepcopy(self.base.events_payload)
        completed_events["events"][0]["status"] = "completed"
        completed_updates = copy.deepcopy(self.base.updates_payload)
        self.write_documents(completed_events, completed_updates)
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        before_payload = copy.deepcopy(completed_events)

        with self.assertRaisesRegex(CampaignEventCurationError, "terminal"):
            build_update_proposal(
                completed_events,
                completed_updates,
                event_key=self.base.event["event_key"],
                action=action,
                changes={"title": "Attempted edit"} if action == "UPDATED" else {},
                headline="Attempted lifecycle change",
                source=update_source(),
                timestamp=UPDATE_TIMESTAMP,
                uuid_factory=UUIDSequence(20),
            )

        self.assertEqual(completed_events, before_payload)
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_completed_event_rejects_confirmed(self):
        self.assert_completed_action_rejected("CONFIRMED")

    def test_completed_event_rejects_updated(self):
        self.assert_completed_action_rejected("UPDATED")

    def test_completed_event_rejects_postponed(self):
        self.assert_completed_action_rejected("POSTPONED")

    def test_completed_event_rejects_cancelled(self):
        self.assert_completed_action_rejected("CANCELLED")

    def test_event_selection_and_confirmation_preserve_event_key(self):
        proposal = build_update(self.base, action="CONFIRMED")
        self.assertEqual(proposal.event["event_key"], self.base.event["event_key"])
        self.assertEqual(proposal.previous_event["event_key"], proposal.event["event_key"])

    def test_confirmed_creates_confirmed_update(self):
        proposal = build_update(self.base, action="CONFIRMED")
        self.assertEqual(proposal.event["status"], "scheduled")
        self.assertEqual(proposal.update["update_type"], "CONFIRMED")

    def test_updated_edits_only_supplied_facts(self):
        proposal = build_update(
            self.base,
            changes={"title": "Corrected debate title", "locality": "Lyon"},
        )
        self.assertEqual(proposal.event["title"], "Corrected debate title")
        self.assertEqual(proposal.event["locality"], "Lyon")
        self.assertEqual(proposal.event["date"], self.base.event["date"])
        self.assertEqual(proposal.event["participants"], self.base.event["participants"])

    def test_blank_keep_sentinel_retains_optional_value(self):
        proposal = build_update(
            self.base,
            changes={"time": KEEP, "location_name": KEEP, "organization": KEEP},
        )
        self.assertEqual(proposal.event["time"], "16:45")
        self.assertEqual(proposal.event["location_name"], "Roland-Garros")
        self.assertEqual(proposal.event["organization"], "MEDEF")

    def test_remove_sentinel_removes_optional_fields(self):
        proposal = build_update(
            self.base,
            changes={"time": REMOVE, "location_name": REMOVE, "participants": REMOVE},
        )
        self.assertNotIn("time", proposal.event)
        self.assertNotIn("location_name", proposal.event)
        self.assertNotIn("participants", proposal.event)
        self.assertEqual(proposal.normalized_event["time_precision"], "date")

    def test_schedule_change_preserves_event_key_and_public_id(self):
        before_id = campaign_event_id("campaign_events", self.base.event["event_key"])
        proposal = build_update(
            self.base,
            changes={"date": "2026-09-03", "time": "20:00"},
        )
        self.assertEqual(proposal.event["event_key"], self.base.event["event_key"])
        self.assertEqual(proposal.normalized_event["event_id"], before_id)

    def test_postponed_event_with_changed_date_returns_to_scheduled(self):
        postponed = build_update(self.base, action="POSTPONED")
        proposal = build_update_proposal(
            postponed.events_payload,
            postponed.updates_payload,
            event_key=self.base.event["event_key"],
            action="UPDATED",
            changes={"date": "2026-09-03"},
            headline="New date confirmed",
            source=update_source(source_url="https://updates.example/new-date"),
            timestamp="2026-08-13T10:00:00Z",
            uuid_factory=UUIDSequence(30),
        )
        self.assertEqual(proposal.event["status"], "scheduled")

    def test_postponed_event_with_non_schedule_edit_remains_postponed(self):
        postponed = build_update(self.base, action="POSTPONED")
        proposal = build_update_proposal(
            postponed.events_payload,
            postponed.updates_payload,
            event_key=self.base.event["event_key"],
            action="UPDATED",
            changes={"title": "Corrected title"},
            headline="Details corrected",
            source=update_source(),
            timestamp="2026-08-13T10:00:00Z",
            uuid_factory=UUIDSequence(30),
        )
        self.assertEqual(proposal.event["status"], "postponed")

    def test_postponed_event_with_removed_time_remains_postponed(self):
        postponed = build_update(self.base, action="POSTPONED")
        proposal = build_update_proposal(
            postponed.events_payload,
            postponed.updates_payload,
            event_key=self.base.event["event_key"],
            action="UPDATED",
            changes={"time": REMOVE},
            headline="Time removed pending a replacement schedule",
            source=update_source(),
            timestamp="2026-08-13T10:00:00Z",
            uuid_factory=UUIDSequence(30),
        )
        self.assertEqual(proposal.event["status"], "postponed")
        self.assertNotIn("time", proposal.event)

    def test_postponed_event_with_changed_concrete_time_returns_to_scheduled(self):
        postponed = build_update(self.base, action="POSTPONED")
        proposal = build_update_proposal(
            postponed.events_payload,
            postponed.updates_payload,
            event_key=self.base.event["event_key"],
            action="UPDATED",
            changes={"time": "18:00"},
            headline="Replacement time confirmed",
            source=update_source(),
            timestamp="2026-08-13T10:00:00Z",
            uuid_factory=UUIDSequence(30),
        )
        self.assertEqual(proposal.event["status"], "scheduled")
        self.assertEqual(proposal.event["time"], "18:00")

    def test_postponed_event_with_new_concrete_time_returns_to_scheduled(self):
        date_only = initial_proposal(time="")
        postponed = build_update(date_only, action="POSTPONED")
        proposal = build_update_proposal(
            postponed.events_payload,
            postponed.updates_payload,
            event_key=date_only.event["event_key"],
            action="UPDATED",
            changes={"time": "18:00"},
            headline="Event time confirmed",
            source=update_source(),
            timestamp="2026-08-13T10:00:00Z",
            uuid_factory=UUIDSequence(30),
        )
        self.assertEqual(proposal.event["status"], "scheduled")
        self.assertEqual(proposal.event["time"], "18:00")

    def test_cancelled_event_cannot_be_revived_with_updated(self):
        cancelled = build_update(self.base, action="CANCELLED")
        with self.assertRaisesRegex(CampaignEventCurationError, "revival"):
            build_update_proposal(
                cancelled.events_payload,
                cancelled.updates_payload,
                event_key=self.base.event["event_key"],
                action="UPDATED",
                changes={"date": "2026-09-03"},
                headline="New date",
                source=update_source(),
                timestamp="2026-08-13T10:00:00Z",
                uuid_factory=UUIDSequence(30),
            )

    def test_postponed_sets_status_and_creates_update(self):
        proposal = build_update(self.base, action="POSTPONED")
        self.assertEqual(proposal.event["status"], "postponed")
        self.assertEqual(proposal.update["update_type"], "POSTPONED")
        self.assertEqual(proposal.event["date"], self.base.event["date"])
        self.assertEqual(proposal.event["time"], self.base.event["time"])

    def test_cancelled_sets_status_and_creates_update(self):
        proposal = build_update(self.base, action="CANCELLED")
        self.assertEqual(proposal.event["status"], "cancelled")
        self.assertEqual(proposal.update["update_type"], "CANCELLED")

    def test_source_correction_preserves_event_identity(self):
        proposal = build_update(
            self.base,
            action="CONFIRMED",
            source=update_source(source_url="https://different.example/confirmation"),
        )
        self.assertEqual(proposal.event["event_key"], self.base.event["event_key"])
        self.assertEqual(
            proposal.normalized_event["event_id"],
            campaign_event_id("campaign_events", self.base.event["event_key"]),
        )
        self.assertEqual(
            proposal.event["source_url"], "https://different.example/confirmation"
        )

    def test_update_timestamp_is_shared(self):
        proposal = build_update(self.base, action="CONFIRMED")
        self.assertEqual(proposal.event["last_verified_at"], UPDATE_TIMESTAMP)
        self.assertEqual(proposal.update["observed_at"], UPDATE_TIMESTAMP)

    def test_rejected_confirmation_performs_no_write(self):
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        answers = iter(["1", "1", "", "", "", "", "n"])
        result = run_update_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda _message: None,
            now_factory=lambda: datetime(2026, 8, 12, 10, tzinfo=timezone.utc),
            uuid_factory=UUIDSequence(20),
            today=date(2026, 8, 11),
        )
        self.assertEqual(result, 0)
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_invalid_update_source_performs_no_write(self):
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        answers = iter(
            [
                "1",
                "4",
                "",
                "http://example.com/cancelled",
                "Publisher",
                "6",
            ]
        )
        result = run_update_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda _message: None,
            now_factory=lambda: datetime(2026, 8, 12, 10, tzinfo=timezone.utc),
            uuid_factory=UUIDSequence(20),
            today=date(2026, 8, 11),
        )
        self.assertEqual(result, 1)
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_simulated_second_write_failure_rolls_back(self):
        proposal = build_update(self.base, action="CANCELLED")
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated failure")
            os.replace(source, target)

        with self.assertRaisesRegex(CampaignEventCurationError, "transaction failed"):
            persist_manual_documents(
                proposal.events_payload,
                proposal.updates_payload,
                events_path=self.events_path,
                updates_path=self.updates_path,
                replace_func=fail_second,
            )
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_source_files_retain_insertion_order(self):
        confirmed = build_update(self.base, action="CONFIRMED")
        updated = build_update_proposal(
            confirmed.events_payload,
            confirmed.updates_payload,
            event_key=self.base.event["event_key"],
            action="UPDATED",
            changes={"title": "Corrected title"},
            headline="Corrected title",
            source=update_source(),
            timestamp="2026-08-13T10:00:00Z",
            uuid_factory=UUIDSequence(30),
        )
        self.assertEqual(
            [record["update_type"] for record in updated.updates_payload["updates"]],
            ["NEW", "CONFIRMED", "UPDATED"],
        )
        self.assertEqual(updated.events_payload["events"][0]["event_key"], self.base.event["event_key"])

    def test_malformed_existing_source_fails_without_modification(self):
        malformed = b'{"schema_version":"1.0","events":['
        self.events_path.write_bytes(malformed)
        before_updates = self.updates_path.read_bytes()
        result = run_update_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=lambda _prompt: self.fail("input must not be requested"),
            output_fn=lambda _message: None,
        )
        self.assertEqual(result, 1)
        self.assertEqual(self.events_path.read_bytes(), malformed)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_selection_order_prioritizes_future_scheduled_then_disrupted(self):
        events = [
            {"event_key": "past", "date": "2026-07-01", "status": "scheduled"},
            {"event_key": "cancelled", "date": "2026-09-01", "status": "cancelled"},
            {"event_key": "future", "date": "2026-10-01", "status": "scheduled"},
        ]
        ordered = sorted_events_for_selection(events, today=date(2026, 8, 11))
        self.assertEqual(
            [event["event_key"] for event in ordered],
            ["future", "cancelled", "past"],
        )


if __name__ == "__main__":
    unittest.main()
