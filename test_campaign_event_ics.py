"""Tests for the network-free iCalendar structured-event parser."""

from __future__ import annotations

import importlib
import socket
import unittest
from unittest import mock

import campaign_event_ics
from campaign_event_ics import parse_ics_events
from campaign_event_structured import StructuredEventParseError, StructuredEventRecord


LISNARD_ICS = r"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:rentree-lisnard-2026@example.org
DTSTART:20260829T170000Z
DTEND:20260829T190000Z
SUMMARY:Discours de rentrée de David Lisnard
DESCRIPTION:Discours de rentrée à Cannes
LOCATION:Cannes\, Alpes-Maritimes
URL:https://example.org/evenements/rentree-lisnard
ORGANIZER;CN=Nouvelle Énergie:mailto:agenda@example.org
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""


def calendar(*properties: str, newline: str = "\n") -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT"]
    lines.extend(properties)
    lines.extend(("END:VEVENT", "END:VCALENDAR"))
    return newline.join(lines) + newline


class CampaignEventIcsTests(unittest.TestCase):
    def test_lisnard_utc_event_normalizes_to_paris(self):
        self.assertEqual(
            parse_ics_events(LISNARD_ICS),
            [
                StructuredEventRecord(
                    title="Discours de rentrée de David Lisnard",
                    scheduled_start="2026-08-29T19:00:00+02:00",
                    time_precision="datetime",
                    timezone="Europe/Paris",
                    source_format="ics",
                    scheduled_end="2026-08-29T21:00:00+02:00",
                    description="Discours de rentrée à Cannes",
                    location_name="Cannes, Alpes-Maritimes",
                    organization="Nouvelle Énergie",
                    event_url="https://example.org/evenements/rentree-lisnard",
                    external_id="rentree-lisnard-2026@example.org",
                    source_status="CONFIRMED",
                )
            ],
        )

    def test_tzid_paris_datetime_and_end_are_supported(self):
        record = parse_ics_events(
            calendar(
                "UID:paris-time",
                "DTSTART;TZID=Europe/Paris:20260829T190000",
                "DTEND;TZID=Europe/Paris:20260829T210000",
                "SUMMARY:Discours",
            )
        )[0]
        self.assertEqual(record.scheduled_start, "2026-08-29T19:00:00+02:00")
        self.assertEqual(record.scheduled_end, "2026-08-29T21:00:00+02:00")

    def test_date_only_values_remain_date_only(self):
        record = parse_ics_events(
            calendar(
                "UID:amfis",
                "DTSTART;VALUE=DATE:20260820",
                "DTEND;VALUE=DATE:20260824",
                "SUMMARY:AMFIS 2026",
            )
        )[0]
        self.assertEqual(record.scheduled_start, "2026-08-20")
        self.assertEqual(record.scheduled_end, "2026-08-24")
        self.assertEqual(record.time_precision, "date")

    def test_text_escapes_are_decoded_conservatively(self):
        record = parse_ics_events(
            calendar(
                "DTSTART:20260829T170000Z",
                r"SUMMARY:Discours\, débat\; rentrée\\été",
                r"DESCRIPTION:Ligne 1\nLigne 2\, suite\; fin\\",
                r"LOCATION:Cannes\, France",
            )
        )[0]
        self.assertEqual(record.title, r"Discours, débat; rentrée\été")
        self.assertEqual(record.description, "Ligne 1\nLigne 2, suite; fin\\")
        self.assertEqual(record.location_name, "Cannes, France")

    def test_missing_description_remains_none(self):
        record = parse_ics_events(
            calendar(
                "UID:no-description@example.org",
                "DTSTART:20260829T170000Z",
                "SUMMARY:Meeting public",
            )
        )[0]

        self.assertIsNone(record.description)

    def test_empty_description_is_treated_as_absent(self):
        record = parse_ics_events(
            calendar(
                "UID:empty-description@example.org",
                "DTSTART:20260829T170000Z",
                "DTEND:20260829T190000Z",
                "SUMMARY:Meeting public",
                "DESCRIPTION:",
                r"LOCATION:Paris\, France",
                "ORGANIZER;CN=Organisation:mailto:agenda@example.org",
                "URL:https://example.org/evenement",
            )
        )[0]

        self.assertIsNone(record.description)
        self.assertEqual(record.external_id, "empty-description@example.org")
        self.assertEqual(record.title, "Meeting public")
        self.assertEqual(record.scheduled_start, "2026-08-29T19:00:00+02:00")
        self.assertEqual(record.scheduled_end, "2026-08-29T21:00:00+02:00")
        self.assertEqual(record.location_name, "Paris, France")
        self.assertEqual(record.organization, "Organisation")
        self.assertEqual(record.event_url, "https://example.org/evenement")

    def test_normalization_empty_description_is_treated_as_absent(self):
        record = parse_ics_events(
            calendar(
                "DTSTART:20260829T170000Z",
                "SUMMARY:Meeting public",
                r"DESCRIPTION:\n   \n",
            )
        )[0]

        self.assertIsNone(record.description)

    def test_meaningful_description_remains_unchanged(self):
        record = parse_ics_events(
            calendar(
                "DTSTART:20260829T170000Z",
                "SUMMARY:Meeting public",
                "DESCRIPTION:Texte explicite",
            )
        )[0]

        self.assertEqual(record.description, "Texte explicite")

    def test_folded_lines_are_unfolded(self):
        raw = (
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
            "DTSTART:20260829T170000Z\r\n"
            "SUMMARY:Meeting national de lancement de la campagne \r\n"
            " présidentielle\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        self.assertEqual(
            parse_ics_events(raw)[0].title,
            "Meeting national de lancement de la campagne présidentielle",
        )

    def test_multiple_events_preserve_source_order(self):
        raw = (
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260829T170000Z\n"
            "SUMMARY:Premier\nUID:first\nEND:VEVENT\nBEGIN:VEVENT\n"
            "DTSTART:20260830T170000Z\nSUMMARY:Second\nUID:second\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        records = parse_ics_events(raw)
        self.assertEqual(
            [record.title for record in records],
            ["Premier", "Second"],
        )
        self.assertEqual(
            [record.external_id for record in records],
            ["first", "second"],
        )

    def test_calendar_level_properties_remain_accepted(self):
        raw = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Example//Agenda//FR\n"
            "CALSCALE:GREGORIAN\nMETHOD:PUBLISH\nBEGIN:VEVENT\n"
            "DTSTART:20260829T170000Z\nSUMMARY:Discours\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        self.assertEqual(len(parse_ics_events(raw)), 1)

    def test_valarm_is_ignored_inside_vevent(self):
        raw = calendar(
            "UID:event-with-alarm@example.org",
            "DTSTART;VALUE=DATE:20260815",
            "DTEND;VALUE=DATE:20260816",
            "SUMMARY:Tour NE Bas-Rhin — Haguenau",
            "DESCRIPTION:Outer event description",
            "LOCATION:Haguenau, Haguenau",
            "BEGIN:VALARM",
            "TRIGGER:-PT1H",
            "ACTION:DISPLAY",
            "DESCRIPTION:Rappel",
            "END:VALARM",
        )

        records = parse_ics_events(
            raw,
            default_timezone="Europe/Paris",
        )

        self.assertEqual(len(records), 1)
        record = records[0]

        self.assertEqual(
            record.title,
            "Tour NE Bas-Rhin — Haguenau",
        )
        self.assertEqual(
            record.description,
            "Outer event description",
        )
        self.assertEqual(
            record.external_id,
            "event-with-alarm@example.org",
        )
        self.assertEqual(
            record.source_format,
            "ics",
        )

    def test_valarm_description_does_not_fill_empty_event_description(self):
        record = parse_ics_events(
            calendar(
                "DTSTART;VALUE=DATE:20260815",
                "SUMMARY:Campaign event",
                "DESCRIPTION:",
                "BEGIN:VALARM",
                "TRIGGER:-PT1H",
                "ACTION:DISPLAY",
                "DESCRIPTION:Rappel",
                "END:VALARM",
            ),
            default_timezone="Europe/Paris",
        )[0]

        self.assertIsNone(record.description)

    def test_unknown_nested_vevent_component_still_fails_closed(self):
        raw = calendar(
            "DTSTART;VALUE=DATE:20260815",
            "SUMMARY:Campaign event",
            "BEGIN:VTODO",
            "SUMMARY:Nested task",
            "END:VTODO",
        )

        with self.assertRaisesRegex(
            StructuredEventParseError,
            "nested VEVENT components are unsupported",
        ):
            parse_ics_events(
                raw,
                default_timezone="Europe/Paris",
            )

    def test_property_before_vcalendar_fails_closed(self):
        with self.assertRaisesRegex(
            StructuredEventParseError,
            "outside VCALENDAR",
        ):
            parse_ics_events("PRODID:outside\n" + LISNARD_ICS)

    def test_property_after_vcalendar_fails_closed(self):
        with self.assertRaisesRegex(
            StructuredEventParseError,
            "outside VCALENDAR",
        ):
            parse_ics_events(LISNARD_ICS + "VERSION:outside\n")


    def test_crlf_lf_text_and_bytes_are_equivalent(self):
        crlf = LISNARD_ICS.replace("\n", "\r\n")
        self.assertEqual(parse_ics_events(LISNARD_ICS), parse_ics_events(crlf))
        self.assertEqual(
            parse_ics_events(LISNARD_ICS),
            parse_ics_events(crlf.encode("utf-8")),
        )

    def test_organizer_without_cn_uses_property_value(self):
        record = parse_ics_events(
            calendar(
                "DTSTART:20260829T170000Z",
                "SUMMARY:Discours",
                "ORGANIZER:Nouvelle Énergie",
            )
        )[0]
        self.assertEqual(record.organization, "Nouvelle Énergie")

    def test_cancelled_status_is_preserved_as_source_fact(self):
        record = parse_ics_events(
            calendar(
                "DTSTART:20260829T170000Z",
                "SUMMARY:Discours",
                "STATUS:CANCELLED",
            )
        )[0]
        self.assertEqual(record.source_status, "CANCELLED")

    def test_default_timezone_makes_naive_datetime_explicit(self):
        record = parse_ics_events(
            calendar("DTSTART:20260829T190000", "SUMMARY:Discours"),
            default_timezone="Europe/Paris",
        )[0]
        self.assertEqual(record.scheduled_start, "2026-08-29T19:00:00+02:00")

    def test_naive_datetime_without_default_timezone_fails_closed(self):
        with self.assertRaisesRegex(StructuredEventParseError, "timezone"):
            parse_ics_events(
                calendar("DTSTART:20260829T190000", "SUMMARY:Discours")
            )

    def test_invalid_timezone_fails_closed(self):
        with self.assertRaisesRegex(StructuredEventParseError, "timezone"):
            parse_ics_events(
                calendar(
                    "DTSTART;TZID=Mars/Olympus:20260829T190000",
                    "SUMMARY:Discours",
                )
            )

    def test_missing_required_properties_fail_closed(self):
        cases = (
            (calendar("SUMMARY:Sans date"), "DTSTART"),
            (calendar("DTSTART:20260829T170000Z"), "SUMMARY"),
        )
        for raw, field in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(StructuredEventParseError, field):
                    parse_ics_events(raw)

    def test_empty_required_or_unrelated_text_still_fails_closed(self):
        cases = (
            (calendar("DTSTART:20260829T170000Z", "SUMMARY:"), "SUMMARY"),
            (
                calendar(
                    "DTSTART:20260829T170000Z",
                    "SUMMARY:Meeting public",
                    "LOCATION:",
                ),
                "LOCATION",
            ),
        )
        for raw, field in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    StructuredEventParseError,
                    rf"{field} must be non-empty text",
                ):
                    parse_ics_events(raw)

    def test_duplicate_required_property_fails_closed(self):
        for duplicate in ("DTSTART:20260830T170000Z", "SUMMARY:Autre"):
            with self.subTest(duplicate=duplicate):
                with self.assertRaisesRegex(
                    StructuredEventParseError,
                    "duplicate",
                ):
                    parse_ics_events(
                        calendar(
                            "DTSTART:20260829T170000Z",
                            "SUMMARY:Discours",
                            duplicate,
                        )
                    )

    def test_recurrence_semantics_fail_closed(self):
        for property_line in (
            "RRULE:FREQ=WEEKLY",
            "RDATE:20260905T170000Z",
            "EXDATE:20260905T170000Z",
            "RECURRENCE-ID:20260829T170000Z",
        ):
            with self.subTest(property_line=property_line):
                with self.assertRaisesRegex(
                    StructuredEventParseError,
                    "recurrence",
                ):
                    parse_ics_events(
                        calendar(
                            "DTSTART:20260829T170000Z",
                            "SUMMARY:Discours",
                            property_line,
                        )
                    )

    def test_nonexistent_or_ambiguous_local_time_fails_closed(self):
        for value in ("20260329T023000", "20261025T023000"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    StructuredEventParseError,
                    "nonexistent|ambiguous",
                ):
                    parse_ics_events(
                        calendar(
                            f"DTSTART;TZID=Europe/Paris:{value}",
                            "SUMMARY:Discours",
                        )
                    )

    def test_malformed_utf8_fails_closed(self):
        with self.assertRaisesRegex(StructuredEventParseError, "UTF-8"):
            parse_ics_events(b"\xff\xfe")

    def test_parser_performs_no_network_access(self):
        with (
            mock.patch("urllib.request.urlopen", side_effect=AssertionError),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError,
            ),
        ):
            self.assertEqual(len(parse_ics_events(LISNARD_ICS)), 1)

    def test_module_import_performs_no_network_access(self):
        with (
            mock.patch("urllib.request.urlopen", side_effect=AssertionError),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError,
            ),
        ):
            importlib.reload(campaign_event_ics)


if __name__ == "__main__":
    unittest.main()

