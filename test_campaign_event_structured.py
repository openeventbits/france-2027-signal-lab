"""Tests for the shared structured Campaign Events record model."""

from __future__ import annotations

import unittest

from campaign_event_structured import (
    StructuredEventParseError,
    StructuredEventRecord,
)


def structured_event(**changes: object) -> StructuredEventRecord:
    values: dict[str, object] = {
        "title": "Meeting public",
        "scheduled_start": "2026-08-29T19:00:00+02:00",
        "time_precision": "datetime",
        "timezone": "Europe/Paris",
        "source_format": "json_ld",
    }
    values.update(changes)
    return StructuredEventRecord(**values)


class StructuredEventRecordTests(unittest.TestCase):
    def test_existing_constructor_defaults_to_no_participants(self):
        event = StructuredEventRecord(
            "Meeting public",
            "2026-08-29T19:00:00+02:00",
            "datetime",
            "Europe/Paris",
            "json_ld",
        )
        self.assertEqual(event.participants, ())

    def test_explicit_participants_are_preserved_as_an_immutable_tuple(self):
        event = structured_event(
            participants=("Unknown Political Actor", "Another Person")
        )
        self.assertEqual(
            event.participants,
            ("Unknown Political Actor", "Another Person"),
        )

    def test_participants_fail_closed_on_mutable_or_malformed_values(self):
        for participants in (
            ["Mutable Person"],
            ("",),
            (" padded ",),
            ("E\u0301lodie Martin",),
            ("Same Person", "Same Person"),
        ):
            with self.subTest(participants=participants):
                with self.assertRaisesRegex(
                    StructuredEventParseError,
                    "participants",
                ):
                    structured_event(participants=participants)


if __name__ == "__main__":
    unittest.main()
