import copy
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from add_campaign_event import build_add_proposal, serialize_manual_document
from campaign_event_updates_manual import normalize_campaign_event_updates_manual
from import_campaign_events import (
    BatchImportError,
    build_batch_proposal,
    normalize_batch_payload,
    run_batch_import,
)


TIMESTAMP = "2026-08-11T12:34:56Z"
NOW = datetime(2026, 8, 11, 12, 34, 56, 999999, tzinfo=timezone.utc)


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


def new_event(**changes):
    event = {
        "title": "Presidential debate",
        "date": "2026-08-27",
        "time": "16:45",
        "event_type": "debate",
        "participants": ["Gabriel Attal", "Bruno Retailleau"],
        "organization": "Example organizer",
        "location_name": "Example venue",
        "locality": "Paris",
        "department": "75",
        "source_url": "https://example.com/events/debate",
        "source_publisher": "Example Média",
        "source_type": "reliable_media",
    }
    event.update(changes)
    return event


def update_record(event_key, action="CONFIRMED", **changes):
    update = {
        "event_key": event_key,
        "action": action,
        "headline": "Campaign event update",
        "source_url": "https://updates.example/events/change",
        "source_publisher": "Updates Média",
        "source_type": "reliable_media",
    }
    update.update(changes)
    return update


def batch(*, new_events=None, updates=None, **extra):
    value = {
        "schema_version": "1.0",
        "new_events": [] if new_events is None else new_events,
        "updates": [] if updates is None else updates,
    }
    value.update(extra)
    return value


def existing_documents(**changes):
    facts = new_event(**changes)
    return build_add_proposal(
        empty_events(),
        empty_updates(),
        facts,
        timestamp="2026-08-10T10:00:00Z",
        uuid_factory=UUIDSequence(),
    )


class ImportCampaignEventsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.events_path = root / "campaign_events_manual.json"
        self.updates_path = root / "campaign_event_updates_manual.json"
        self.payload_path = root / "batch.json"
        self.write_documents(empty_events(), empty_updates())

    def write_documents(self, events, updates):
        self.events_path.write_bytes(serialize_manual_document(events))
        self.updates_path.write_bytes(serialize_manual_document(updates))

    def read_documents(self):
        return (
            json.loads(self.events_path.read_text(encoding="utf-8")),
            json.loads(self.updates_path.read_text(encoding="utf-8")),
        )

    def install_existing(self, **changes):
        proposal = existing_documents(**changes)
        self.write_documents(proposal.events_payload, proposal.updates_payload)
        return proposal

    def proposal(self, raw_batch, *, events=None, updates=None, uuid_start=100):
        return build_batch_proposal(
            empty_events() if events is None else events,
            empty_updates() if updates is None else updates,
            normalize_batch_payload(raw_batch),
            timestamp=TIMESTAMP,
            uuid_factory=UUIDSequence(uuid_start),
        )

    def run_import(self, raw_batch, *, answer="yes", input_fn=None, **kwargs):
        self.payload_path.write_text(
            json.dumps(raw_batch, ensure_ascii=False), encoding="utf-8"
        )
        output = []
        result = run_batch_import(
            self.payload_path,
            events_path=self.events_path,
            updates_path=self.updates_path,
            input_fn=(lambda _prompt: answer) if input_fn is None else input_fn,
            output_fn=output.append,
            now_factory=lambda: NOW,
            uuid_factory=kwargs.pop("uuid_factory", UUIDSequence(100)),
            **kwargs,
        )
        return result, output

    def test_01_empty_batch_succeeds_without_write(self):
        before = (self.events_path.read_bytes(), self.updates_path.read_bytes())

        def unexpected_input(_prompt):
            self.fail("empty batch must not ask for confirmation")

        result, output = self.run_import(batch(), input_fn=unexpected_input)
        self.assertEqual(result, 0)
        self.assertIn("No Campaign Events changes proposed.", output)
        self.assertEqual(
            before, (self.events_path.read_bytes(), self.updates_path.read_bytes())
        )

    def test_02_one_new_event(self):
        proposal = self.proposal(batch(new_events=[new_event()]))
        self.assertEqual(len(proposal.events_payload["events"]), 1)
        self.assertEqual(proposal.events_payload["events"][0]["status"], "scheduled")

    def test_03_multiple_new_events(self):
        proposal = self.proposal(
            batch(
                new_events=[
                    new_event(),
                    new_event(
                        title="Lyon public meeting",
                        date="2026-09-02",
                        event_type="public_meeting",
                        source_url="https://example.com/events/lyon",
                    ),
                ]
            )
        )
        self.assertEqual(len(proposal.additions), 2)
        self.assertEqual(len(proposal.events_payload["events"]), 2)

    def test_04_automatic_new_watch_for_every_new_event(self):
        proposal = self.proposal(
            batch(
                new_events=[
                    new_event(),
                    new_event(
                        title="Second event",
                        date="2026-09-03",
                        source_url="https://example.com/events/second",
                    ),
                ]
            )
        )
        self.assertEqual(
            [value["update_type"] for value in proposal.updates_payload["updates"]],
            ["NEW", "NEW"],
        )
        self.assertEqual(
            [value["headline"] for value in proposal.updates_payload["updates"]],
            ["Presidential debate", "Second event"],
        )

    def test_05_confirmed_existing_event(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(updates=[update_record(base.event["event_key"])]),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertEqual(proposal.updates[0].update["update_type"], "CONFIRMED")
        self.assertEqual(proposal.updates[0].event["status"], "scheduled")

    def test_06_updated_existing_event(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(
                updates=[
                    update_record(
                        base.event["event_key"],
                        "UPDATED",
                        changes={"title": "Corrected title", "locality": "Lyon"},
                    )
                ]
            ),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertEqual(proposal.updates[0].event["title"], "Corrected title")
        self.assertEqual(proposal.updates[0].event["locality"], "Lyon")

    def test_07_postponed_existing_event(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(updates=[update_record(base.event["event_key"], "POSTPONED")]),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertEqual(proposal.updates[0].event["status"], "postponed")

    def test_08_cancelled_existing_event(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(updates=[update_record(base.event["event_key"], "CANCELLED")]),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertEqual(proposal.updates[0].event["status"], "cancelled")

    def test_09_mixed_new_events_and_updates(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(
                new_events=[
                    new_event(
                        title="Lyon meeting",
                        date="2026-09-02",
                        source_url="https://example.com/events/lyon",
                    )
                ],
                updates=[update_record(base.event["event_key"], "CONFIRMED")],
            ),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertEqual(len(proposal.additions), 1)
        self.assertEqual(len(proposal.updates), 1)

    def test_10_one_timestamp_shared_across_batch(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(
                new_events=[
                    new_event(
                        title="Lyon meeting",
                        date="2026-09-02",
                        source_url="https://example.com/events/lyon",
                    )
                ],
                updates=[update_record(base.event["event_key"], "CONFIRMED")],
            ),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        values = [proposal.additions[0].event["last_verified_at"]]
        values += [proposal.additions[0].update["observed_at"]]
        values += [proposal.updates[0].event["last_verified_at"]]
        values += [proposal.updates[0].update["observed_at"]]
        self.assertEqual(values, [TIMESTAMP] * 4)

    def test_11_opaque_unique_keys_for_all_new_records(self):
        proposal = self.proposal(
            batch(
                new_events=[
                    new_event(),
                    new_event(
                        title="Second event",
                        date="2026-09-02",
                        source_url="https://example.com/events/second",
                    ),
                ]
            )
        )
        event_keys = [item.event["event_key"] for item in proposal.additions]
        update_keys = [item.update["update_key"] for item in proposal.additions]
        self.assertEqual(len(set(event_keys + update_keys)), 4)
        self.assertTrue(all(key.startswith("manual-") for key in event_keys))
        self.assertTrue(all(key.startswith("update-") for key in update_keys))

    def test_12_unknown_event_key_fails(self):
        with self.assertRaisesRegex(BatchImportError, r"updates\[0\].*existed"):
            self.proposal(
                batch(updates=[update_record("manual-" + "f" * 32)])
            )

    def test_13_update_cannot_target_event_created_in_batch(self):
        generated_key = "manual-" + uuid.UUID(int=100).hex
        with self.assertRaisesRegex(BatchImportError, "created in the same batch"):
            self.proposal(
                batch(
                    new_events=[new_event()],
                    updates=[update_record(generated_key)],
                ),
                uuid_start=100,
            )

    def test_14_duplicate_update_targets_fail(self):
        base = existing_documents()
        with self.assertRaisesRegex(BatchImportError, "more than once"):
            self.proposal(
                batch(
                    updates=[
                        update_record(base.event["event_key"]),
                        update_record(base.event["event_key"]),
                    ]
                ),
                events=base.events_payload,
                updates=base.updates_payload,
            )

    def test_15_invalid_action_fails(self):
        with self.assertRaisesRegex(BatchImportError, r"updates\[0\].action"):
            normalize_batch_payload(
                batch(updates=[update_record("manual-" + "a" * 32, "MOVED")])
            )

    def test_16_new_action_inside_updates_fails(self):
        with self.assertRaisesRegex(BatchImportError, r"updates\[0\].action"):
            normalize_batch_payload(
                batch(updates=[update_record("manual-" + "a" * 32, "NEW")])
            )

    def test_17_changes_forbidden_for_confirmed(self):
        with self.assertRaisesRegex(BatchImportError, "forbidden for action CONFIRMED"):
            normalize_batch_payload(
                batch(
                    updates=[
                        update_record(
                            "manual-" + "a" * 32, changes={"title": "No"}
                        )
                    ]
                )
            )

    def test_18_changes_forbidden_for_postponed(self):
        with self.assertRaisesRegex(BatchImportError, "forbidden for action POSTPONED"):
            normalize_batch_payload(
                batch(
                    updates=[
                        update_record(
                            "manual-" + "a" * 32,
                            "POSTPONED",
                            changes={},
                        )
                    ]
                )
            )

    def test_19_changes_forbidden_for_cancelled(self):
        with self.assertRaisesRegex(BatchImportError, "forbidden for action CANCELLED"):
            normalize_batch_payload(
                batch(
                    updates=[
                        update_record(
                            "manual-" + "a" * 32,
                            "CANCELLED",
                            changes={},
                        )
                    ]
                )
            )

    def test_20_omitted_update_field_keeps_value(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(
                updates=[
                    update_record(
                        base.event["event_key"],
                        "UPDATED",
                        changes={"title": "Only title changes"},
                    )
                ]
            ),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertEqual(proposal.updates[0].event["time"], base.event["time"])
        self.assertEqual(
            proposal.updates[0].event["participants"], base.event["participants"]
        )

    def test_21_null_optional_update_field_removes_it(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(
                updates=[
                    update_record(
                        base.event["event_key"],
                        "UPDATED",
                        changes={"time": None, "organization": None},
                    )
                ]
            ),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertNotIn("time", proposal.updates[0].event)
        self.assertNotIn("organization", proposal.updates[0].event)

    def test_22_null_required_update_field_fails(self):
        with self.assertRaisesRegex(BatchImportError, r"changes.title may not be null"):
            normalize_batch_payload(
                batch(
                    updates=[
                        update_record(
                            "manual-" + "a" * 32,
                            "UPDATED",
                            changes={"title": None},
                        )
                    ]
                )
            )

    def test_23_empty_participants_removes_participants(self):
        base = existing_documents()
        proposal = self.proposal(
            batch(
                updates=[
                    update_record(
                        base.event["event_key"],
                        "UPDATED",
                        changes={"participants": []},
                    )
                ]
            ),
            events=base.events_payload,
            updates=base.updates_payload,
        )
        self.assertNotIn("participants", proposal.updates[0].event)

    def test_24_new_event_participants_array_validates(self):
        normalized = normalize_batch_payload(
            batch(new_events=[new_event(participants=[" Gabriel Attal "])])
        )
        self.assertEqual(
            normalized["new_events"][0]["participants"], ["Gabriel Attal"]
        )
        with self.assertRaisesRegex(BatchImportError, "JSON array"):
            normalize_batch_payload(
                batch(new_events=[new_event(participants="Gabriel Attal")])
            )

    def test_25_unknown_top_level_field_fails(self):
        with self.assertRaisesRegex(BatchImportError, "unexpected=.*extra"):
            normalize_batch_payload(batch(extra=True))

    def test_26_unknown_new_event_field_fails(self):
        with self.assertRaisesRegex(BatchImportError, "model_note"):
            normalize_batch_payload(
                batch(new_events=[new_event(model_note="ignore me")])
            )

    def test_27_unknown_update_field_fails(self):
        with self.assertRaisesRegex(BatchImportError, "model_note"):
            normalize_batch_payload(
                batch(
                    updates=[
                        update_record("manual-" + "a" * 32, model_note="ignore me")
                    ]
                )
            )

    def test_28_model_generated_fields_fail(self):
        forbidden_new = (
            "event_key",
            "event_id",
            "candidate_ids",
            "candidate_names",
            "source_id",
            "last_verified_at",
            "status",
            "evidence",
        )
        for field in forbidden_new:
            with self.subTest(section="new_events", field=field):
                with self.assertRaises(BatchImportError):
                    normalize_batch_payload(
                        batch(new_events=[new_event(**{field: "forged"})])
                    )
        for field in ("update_key", "update_id", "observed_at", "evidence"):
            with self.subTest(section="updates", field=field):
                with self.assertRaises(BatchImportError):
                    normalize_batch_payload(
                        batch(
                            updates=[
                                update_record(
                                    "manual-" + "a" * 32, **{field: "forged"}
                                )
                            ]
                        )
                    )

    def test_29_duplicate_against_existing_event_fails(self):
        base = existing_documents()
        with self.assertRaisesRegex(BatchImportError, "same date and title"):
            self.proposal(
                batch(new_events=[new_event()]),
                events=base.events_payload,
                updates=base.updates_payload,
            )

    def test_30_duplicate_between_new_batch_events_fails(self):
        with self.assertRaisesRegex(BatchImportError, r"new_events\[1\]"):
            self.proposal(
                batch(
                    new_events=[
                        new_event(),
                        new_event(source_url="https://other.example/duplicate"),
                    ]
                )
            )

    def test_31_invalid_second_item_causes_zero_writes(self):
        before = (self.events_path.read_bytes(), self.updates_path.read_bytes())
        result, output = self.run_import(
            batch(
                new_events=[
                    new_event(),
                    new_event(
                        title="Invalid second",
                        date="2026-09-02",
                        source_url="http://example.com/not-https",
                    ),
                ]
            )
        )
        self.assertEqual(result, 1)
        self.assertTrue(any("new_events[1]" in line for line in output))
        self.assertEqual(
            before, (self.events_path.read_bytes(), self.updates_path.read_bytes())
        )

    def test_32_declined_confirmation_performs_zero_writes(self):
        before = (self.events_path.read_bytes(), self.updates_path.read_bytes())
        result, output = self.run_import(
            batch(new_events=[new_event()]), answer="no"
        )
        self.assertEqual(result, 0)
        self.assertIn("No changes made.", output)
        self.assertEqual(
            before, (self.events_path.read_bytes(), self.updates_path.read_bytes())
        )

    def test_33_successful_confirmation_modifies_both_files(self):
        before = (self.events_path.read_bytes(), self.updates_path.read_bytes())
        result, _output = self.run_import(batch(new_events=[new_event()]))
        after = (self.events_path.read_bytes(), self.updates_path.read_bytes())
        self.assertEqual(result, 0)
        self.assertNotEqual(before[0], after[0])
        self.assertNotEqual(before[1], after[1])

    def test_34_concurrent_source_modification_is_detected(self):
        before_updates = self.updates_path.read_bytes()

        def modify_after_preview(_prompt):
            self.events_path.write_bytes(self.events_path.read_bytes() + b"\n")
            return "yes"

        result, output = self.run_import(
            batch(new_events=[new_event()]), input_fn=modify_after_preview
        )
        self.assertEqual(result, 1)
        self.assertTrue(any("changed during this transaction" in line for line in output))
        self.assertEqual(self.updates_path.read_bytes(), before_updates)

    def test_35_second_file_failure_rolls_back(self):
        before = (self.events_path.read_bytes(), self.updates_path.read_bytes())
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second replacement failure")
            os.replace(source, target)

        result, output = self.run_import(
            batch(new_events=[new_event()]), replace_func=fail_second
        )
        self.assertEqual(result, 1)
        self.assertTrue(any("transaction failed" in line for line in output))
        self.assertEqual(
            before, (self.events_path.read_bytes(), self.updates_path.read_bytes())
        )

    def test_36_batch_insertion_order_retained(self):
        base = self.install_existing()
        result, _output = self.run_import(
            batch(
                new_events=[
                    new_event(
                        title="First added",
                        date="2026-09-01",
                        source_url="https://example.com/events/first",
                    ),
                    new_event(
                        title="Second added",
                        date="2026-09-02",
                        source_url="https://example.com/events/second",
                    ),
                ],
                updates=[update_record(base.event["event_key"], "CONFIRMED")],
            )
        )
        events, updates = self.read_documents()
        self.assertEqual(result, 0)
        self.assertEqual(
            [event["title"] for event in events["events"]],
            ["Presidential debate", "First added", "Second added"],
        )
        self.assertEqual(
            [update["update_type"] for update in updates["updates"]],
            ["NEW", "NEW", "NEW", "CONFIRMED"],
        )

    def test_37_source_and_evidence_validation_applies(self):
        with self.assertRaisesRegex(BatchImportError, r"new_events\[0\].*HTTPS"):
            self.proposal(
                batch(new_events=[new_event(source_url="http://example.com/event")])
            )
        with self.assertRaisesRegex(BatchImportError, "source_type"):
            normalize_batch_payload(
                batch(new_events=[new_event(source_type="social_media")])
            )

    def test_38_candidate_linkage_is_derived_not_supplied(self):
        proposal = self.proposal(
            batch(new_events=[new_event(participants=["Gabriel Attal"])])
        )
        raw = proposal.additions[0].event
        normalized = proposal.additions[0].normalized_event
        self.assertNotIn("candidate_ids", raw)
        self.assertNotIn("candidate_names", raw)
        self.assertEqual(normalized["candidate_names"], ["Gabriel Attal"])

    def test_39_completed_event_lifecycle_safety_applies(self):
        base = existing_documents()
        completed_events = copy.deepcopy(base.events_payload)
        completed_events["events"][0]["status"] = "completed"
        with self.assertRaisesRegex(BatchImportError, "terminal"):
            self.proposal(
                batch(updates=[update_record(base.event["event_key"], "CANCELLED")]),
                events=completed_events,
                updates=empty_updates(),
            )

    def test_40_same_second_watch_order_remains_deterministic(self):
        proposal = self.proposal(
            batch(
                new_events=[
                    new_event(),
                    new_event(
                        title="Second event",
                        date="2026-09-02",
                        source_url="https://example.com/events/second",
                    ),
                ]
            )
        )
        first = normalize_campaign_event_updates_manual(
            proposal.updates_payload,
            manual_events_payload=proposal.events_payload,
        )
        second = normalize_campaign_event_updates_manual(
            copy.deepcopy(proposal.updates_payload),
            manual_events_payload=copy.deepcopy(proposal.events_payload),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [item["update_id"] for item in first],
            sorted(item["update_id"] for item in first),
        )


if __name__ == "__main__":
    unittest.main()
