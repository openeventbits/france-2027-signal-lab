import json
import os
import re
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from add_campaign_event import (
    CampaignEventCurationError,
    build_add_proposal,
    find_likely_duplicates,
    persist_manual_documents,
    run_add_interactive,
    serialize_manual_document,
)
from campaign_event_updates_manual import normalize_campaign_event_updates_manual
from campaign_events_manual import normalize_campaign_events_manual


TIMESTAMP = "2026-08-11T12:34:56Z"
NOW = datetime(2026, 8, 11, 12, 34, 56, 987654, tzinfo=timezone.utc)


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


def event_facts(**changes):
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
        "source_url": "https://example.com/politique/debat",
        "source_publisher": "Example Média",
        "source_type": "reliable_media",
    }
    facts.update(changes)
    return facts


def build_base(**fact_changes):
    return build_add_proposal(
        empty_events(),
        empty_updates(),
        event_facts(**fact_changes),
        timestamp=TIMESTAMP,
        uuid_factory=UUIDSequence(),
    )


class AddCampaignEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.events_path = Path(self.temp_dir.name) / "campaign_events_manual.json"
        self.updates_path = (
            Path(self.temp_dir.name) / "campaign_event_updates_manual.json"
        )
        self.write_documents(empty_events(), empty_updates())

    def write_documents(self, events, updates):
        self.events_path.write_bytes(serialize_manual_document(events))
        self.updates_path.write_bytes(serialize_manual_document(updates))

    def read_documents(self):
        return (
            json.loads(self.events_path.read_text(encoding="utf-8")),
            json.loads(self.updates_path.read_text(encoding="utf-8")),
        )

    def interactive_inputs(self, *, save="y", source_url=None):
        values = iter(
            [
                "Presidential debate at MEDEF",
                "2026-08-27",
                "16:45",
                "3",
                "Gabriel Attal, Bruno Retailleau",
                "MEDEF",
                "Roland-Garros",
                "Paris",
                "75",
                source_url or "https://example.com/politique/debat",
                "Example Média",
                "6",
                save,
            ]
        )
        return lambda _prompt: next(values)

    def test_generated_event_and_update_keys_have_correct_formats(self):
        proposal = build_base()
        self.assertRegex(proposal.event["event_key"], r"\Amanual-[0-9a-f]{32}\Z")
        self.assertRegex(proposal.update["update_key"], r"\Aupdate-[0-9a-f]{32}\Z")
        self.assertNotEqual(
            proposal.event["event_key"].removeprefix("manual-"),
            proposal.update["update_key"].removeprefix("update-"),
        )

    def test_one_captured_timestamp_is_shared(self):
        proposal = build_add_proposal(
            empty_events(),
            empty_updates(),
            event_facts(),
            now=NOW,
            uuid_factory=UUIDSequence(),
        )
        self.assertEqual(proposal.event["last_verified_at"], TIMESTAMP)
        self.assertEqual(proposal.update["observed_at"], TIMESTAMP)

    def test_optional_blanks_are_omitted(self):
        proposal = build_base(
            time="",
            participants="",
            organization=" ",
            location_name="",
            locality="",
            department="",
        )
        for field in (
            "time",
            "participants",
            "organization",
            "location_name",
            "locality",
            "department",
        ):
            self.assertNotIn(field, proposal.event)

    def test_participants_are_parsed_and_trimmed(self):
        proposal = build_base(
            participants="  Gabriel Attal , Bruno Retailleau  , "
        )
        self.assertEqual(
            proposal.event["participants"],
            ["Gabriel Attal", "Bruno Retailleau"],
        )

    def test_new_watch_record_is_generated_automatically(self):
        proposal = build_base()
        self.assertEqual(proposal.update["update_type"], "NEW")
        self.assertEqual(proposal.update["headline"], proposal.event["title"])
        self.assertEqual(proposal.update["event_key"], proposal.event["event_key"])
        for field in ("source_url", "source_publisher", "source_type"):
            self.assertEqual(proposal.update[field], proposal.event[field])

    def test_generated_documents_validate_through_step_1_and_step_2(self):
        proposal = build_base()
        normalized_events = normalize_campaign_events_manual(proposal.events_payload)
        normalized_updates = normalize_campaign_event_updates_manual(
            proposal.updates_payload,
            manual_events_payload=proposal.events_payload,
        )
        self.assertEqual(len(normalized_events), 1)
        self.assertEqual(len(normalized_updates), 1)

    def test_duplicate_same_date_and_title_is_warned(self):
        first = build_base()
        second = build_add_proposal(
            first.events_payload,
            first.updates_payload,
            event_facts(source_url="https://other.example/item"),
            timestamp="2026-08-11T12:35:00Z",
            uuid_factory=UUIDSequence(10),
        )
        matches = find_likely_duplicates(first.events_payload["events"], second.event)
        self.assertIn("same date and title", matches[0].reasons)

    def test_duplicate_same_date_and_source_is_warned(self):
        first = build_base()
        second = build_add_proposal(
            first.events_payload,
            first.updates_payload,
            event_facts(title="Different title", participants=""),
            timestamp="2026-08-11T12:35:00Z",
            uuid_factory=UUIDSequence(10),
        )
        matches = find_likely_duplicates(first.events_payload["events"], second.event)
        self.assertIn("same date and source URL", matches[0].reasons)

    def test_duplicate_same_date_type_and_participants_is_warned(self):
        first = build_base()
        second = build_add_proposal(
            first.events_payload,
            first.updates_payload,
            event_facts(
                title="Different title",
                source_url="https://other.example/item",
                participants="Bruno Retailleau, Gabriel Attal",
            ),
            timestamp="2026-08-11T12:35:00Z",
            uuid_factory=UUIDSequence(10),
        )
        matches = find_likely_duplicates(first.events_payload["events"], second.event)
        self.assertIn("same date, type, and participants", matches[0].reasons)

    def test_duplicate_override_allows_intentional_addition(self):
        first = build_base()
        self.write_documents(first.events_payload, first.updates_payload)
        answers = list(
            [
                "Presidential debate at MEDEF",
                "2026-08-27",
                "16:45",
                "3",
                "Gabriel Attal, Bruno Retailleau",
                "MEDEF",
                "Roland-Garros",
                "Paris",
                "75",
                "https://other.example/new-report",
                "Other Publisher",
                "6",
                "yes",
                "yes",
            ]
        )
        output = []
        result = run_add_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=lambda _prompt: answers.pop(0),
            output_fn=output.append,
            now_factory=lambda: datetime(2026, 8, 11, 13, tzinfo=timezone.utc),
            uuid_factory=UUIDSequence(20),
        )
        events, updates = self.read_documents()
        self.assertEqual(result, 0)
        self.assertEqual(len(events["events"]), 2)
        self.assertEqual(len(updates["updates"]), 2)
        self.assertIn("Possible duplicate found.", output)

    def test_rejected_confirmation_performs_no_write(self):
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        result = run_add_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=self.interactive_inputs(save="n"),
            output_fn=lambda _message: None,
            now_factory=lambda: NOW,
            uuid_factory=UUIDSequence(),
        )
        self.assertEqual(result, 0)
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_validation_failure_performs_no_write(self):
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        result = run_add_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=self.interactive_inputs(source_url="http://example.com/event"),
            output_fn=lambda _message: None,
            now_factory=lambda: NOW,
            uuid_factory=UUIDSequence(),
        )
        self.assertEqual(result, 1)
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_successful_transaction_changes_both_files(self):
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        result = run_add_interactive(
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=self.interactive_inputs(save="yes"),
            output_fn=lambda _message: None,
            now_factory=lambda: NOW,
            uuid_factory=UUIDSequence(),
        )
        self.assertEqual(result, 0)
        self.assertNotEqual(self.events_path.read_bytes(), before_events)
        self.assertNotEqual(self.updates_path.read_bytes(), before_updates)

    def test_second_file_failure_restores_first_file(self):
        proposal = build_base()
        before_events = self.events_path.read_bytes()
        before_updates = self.updates_path.read_bytes()
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second replacement failure")
            os.replace(source, target)

        with self.assertRaisesRegex(CampaignEventCurationError, "transaction failed"):
            persist_manual_documents(
                proposal.events_payload,
                proposal.updates_payload,
                events_path=self.events_path,
                updates_path=self.updates_path,
                expected_events_bytes=before_events,
                expected_updates_bytes=before_updates,
                replace_func=fail_second,
            )
        self.assertEqual(self.events_path.read_bytes(), before_events)
        self.assertEqual(self.updates_path.read_bytes(), before_updates)
        self.assertEqual(list(Path(self.temp_dir.name).glob("*.tmp")), [])

    def test_source_arrays_retain_insertion_order(self):
        first = build_base()
        second = build_add_proposal(
            first.events_payload,
            first.updates_payload,
            event_facts(
                title="Lyon campaign meeting",
                date="2026-09-02",
                source_url="https://other.example/lyon",
            ),
            timestamp="2026-08-12T10:00:00Z",
            uuid_factory=UUIDSequence(10),
        )
        self.assertEqual(
            [event["event_key"] for event in second.events_payload["events"]],
            [first.event["event_key"], second.event["event_key"]],
        )
        self.assertEqual(
            [update["update_key"] for update in second.updates_payload["updates"]],
            [first.update["update_key"], second.update["update_key"]],
        )


if __name__ == "__main__":
    unittest.main()
