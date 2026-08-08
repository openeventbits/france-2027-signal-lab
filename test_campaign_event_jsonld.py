"""Tests for the network-free Schema.org Event JSON-LD parser."""

from __future__ import annotations

from dataclasses import fields
import importlib
import json
import socket
import unittest
from unittest import mock

import campaign_event_jsonld
from campaign_event_jsonld import parse_json_ld_events
from campaign_event_structured import StructuredEventParseError, StructuredEventRecord


ACTION_EVENT = {
    "@context": "https://schema.org",
    "@type": "Event",
    "@id": "https://actionpopulaire.fr/evenements/lancement-2027",
    "name": "Meeting national de lancement de la campagne présidentielle",
    "startDate": "2026-06-07T15:00:00+02:00",
    "endDate": "2026-06-07T18:00:00+02:00",
    "description": "Jean-Luc Mélenchon lance la campagne présidentielle.",
    "url": "https://actionpopulaire.fr/evenements/lancement-2027",
    "location": {
        "@type": "Place",
        "name": "Place de la Porte de Paris",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Place de la Porte de Paris",
            "postalCode": "93200",
            "addressLocality": "Saint-Denis",
            "addressCountry": "FR",
        },
    },
    "organizer": {
        "@type": "Organization",
        "name": "La France insoumise",
    },
}

AMFIS_EVENT = {
    "@context": "https://schema.org",
    "@type": "Event",
    "name": "AMFIS 2026",
    "startDate": "2026-08-20",
    "endDate": "2026-08-23",
    "description": "Université d'été ouverte au public.",
    "location": "Châteauneuf-sur-Isère",
}


def as_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


class CampaignEventJsonLdTests(unittest.TestCase):
    def test_action_populaire_direct_event_extracts_source_facts_only(self):
        records = parse_json_ld_events(as_json(ACTION_EVENT))

        self.assertEqual(
            records,
            [
                StructuredEventRecord(
                    title=(
                        "Meeting national de lancement de la campagne "
                        "présidentielle"
                    ),
                    scheduled_start="2026-06-07T15:00:00+02:00",
                    time_precision="datetime",
                    timezone="Europe/Paris",
                    source_format="json_ld",
                    scheduled_end="2026-06-07T18:00:00+02:00",
                    description=(
                        "Jean-Luc Mélenchon lance la campagne présidentielle."
                    ),
                    location_name="Place de la Porte de Paris",
                    locality="Saint-Denis",
                    address=(
                        "Place de la Porte de Paris, 93200, Saint-Denis, FR"
                    ),
                    organization="La France insoumise",
                    event_url=(
                        "https://actionpopulaire.fr/evenements/lancement-2027"
                    ),
                    external_id=(
                        "https://actionpopulaire.fr/evenements/lancement-2027"
                    ),
                )
            ],
        )
        field_names = {field.name for field in fields(records[0])}
        self.assertTrue(
            {
                "candidate_id",
                "candidate_ids",
                "candidate_name",
                "candidate_names",
                "event_type",
                "evidence_status",
            }.isdisjoint(field_names)
        )

    def test_amfis_parses_without_candidate_reference(self):
        record = parse_json_ld_events(as_json(AMFIS_EVENT))[0]
        self.assertEqual(record.title, "AMFIS 2026")
        self.assertEqual(record.scheduled_start, "2026-08-20")
        self.assertEqual(record.scheduled_end, "2026-08-23")
        self.assertEqual(record.time_precision, "date")
        self.assertEqual(record.location_name, "Châteauneuf-sur-Isère")
        self.assertNotIn("Mélenchon", record.description or "")

    def test_event_inside_graph_is_discovered(self):
        payload = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "Agenda"},
                ACTION_EVENT,
            ],
        }
        self.assertEqual(len(parse_json_ld_events(as_json(payload))), 1)

    def test_item_list_nested_item_is_discovered(self):
        payload = {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "item": AMFIS_EVENT,
                }
            ],
        }
        self.assertEqual(
            [record.title for record in parse_json_ld_events(as_json(payload))],
            ["AMFIS 2026"],
        )

    def test_top_level_array_and_multiple_events_preserve_order(self):
        records = parse_json_ld_events(as_json([ACTION_EVENT, AMFIS_EVENT]))
        self.assertEqual(
            [record.title for record in records],
            [
                "Meeting national de lancement de la campagne présidentielle",
                "AMFIS 2026",
            ],
        )

    def test_type_list_containing_event_is_recognized(self):
        payload = {**AMFIS_EVENT, "@type": ["Thing", "Event"]}
        self.assertEqual(len(parse_json_ld_events(as_json(payload))), 1)

    def test_bounded_schema_org_event_type_urls_are_recognized(self):
        for event_type in (
            "Event",
            "http://schema.org/Event",
            "https://schema.org/Event",
            "https://schema.org/Event/",
        ):
            with self.subTest(event_type=event_type):
                payload = {**AMFIS_EVENT, "@type": event_type}
                self.assertEqual(
                    len(parse_json_ld_events(as_json(payload))),
                    1,
                )

    def test_foreign_event_type_uri_is_ignored(self):
        for event_type in (
            "https://example.org/Event",
            "https://other-vocabulary.test/types/Event",
        ):
            with self.subTest(event_type=event_type):
                payload = {**AMFIS_EVENT, "@type": event_type}
                self.assertEqual(parse_json_ld_events(as_json(payload)), [])

    def test_nested_foreign_event_looking_object_is_ignored(self):
        payload = {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "item": {
                        **AMFIS_EVENT,
                        "@type": "https://example.org/Event",
                    }
                }
            ],
        }
        self.assertEqual(parse_json_ld_events(as_json(payload)), [])


    def test_unrelated_article_and_webpage_are_ignored(self):
        payload = [
            {"@type": "Article", "name": "Event dans le texte"},
            {"@type": "WebPage", "name": "Agenda"},
        ]
        self.assertEqual(parse_json_ld_events(as_json(payload)), [])

    def test_html_json_ld_is_supported_and_dom_text_is_ignored(self):
        html = (
            "<!doctype html><html><body>"
            "<div>Fake Event 2027-01-01</div>"
            '<script type="application/ld+json">'
            f"{as_json(ACTION_EVENT)}"
            "</script></body></html>"
        )
        records = parse_json_ld_events(html)
        self.assertEqual(len(records), 1)
        self.assertNotIn("Fake Event", records[0].title)

    def test_utc_datetime_normalizes_to_paris(self):
        payload = {
            "@type": "Event",
            "name": "Discours de rentrée",
            "startDate": "2026-08-29T17:00:00Z",
            "endDate": "2026-08-29T19:00:00Z",
        }
        record = parse_json_ld_events(as_json(payload))[0]
        self.assertEqual(record.scheduled_start, "2026-08-29T19:00:00+02:00")
        self.assertEqual(record.scheduled_end, "2026-08-29T21:00:00+02:00")

    def test_offset_aware_datetime_normalizes_to_paris(self):
        payload = {
            "@type": "Event",
            "name": "Meeting",
            "startDate": "2026-06-07T13:00:00Z",
        }
        record = parse_json_ld_events(as_json(payload))[0]
        self.assertEqual(record.scheduled_start, "2026-06-07T15:00:00+02:00")

    def test_simple_location_and_organizer_shapes_are_supported(self):
        payload = {
            "@type": "Event",
            "name": "Meeting",
            "startDate": "2026-06-07",
            "location": "Saint-Denis",
            "organizer": "Mouvement",
        }
        record = parse_json_ld_events(as_json(payload))[0]
        self.assertEqual(record.location_name, "Saint-Denis")
        self.assertEqual(record.organization, "Mouvement")

    def test_missing_required_event_fields_fail_closed(self):
        cases = (
            ({"@type": "Event", "startDate": "2026-06-07"}, "name"),
            ({"@type": "Event", "name": "Meeting"}, "startDate"),
        )
        for payload, field in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(StructuredEventParseError, field):
                    parse_json_ld_events(as_json(payload))

    def test_malformed_event_start_date_fails_closed(self):
        payload = {
            "@type": "Event",
            "name": "Meeting",
            "startDate": "29 août 2026",
        }
        with self.assertRaisesRegex(StructuredEventParseError, "startDate"):
            parse_json_ld_events(as_json(payload))

    def test_naive_datetime_requires_explicit_default_timezone(self):
        payload = {
            "@type": "Event",
            "name": "Meeting",
            "startDate": "2026-06-07T15:00:00",
        }
        with self.assertRaisesRegex(StructuredEventParseError, "timezone"):
            parse_json_ld_events(as_json(payload))

        record = parse_json_ld_events(
            as_json(payload),
            default_timezone="Europe/Paris",
        )[0]
        self.assertEqual(record.scheduled_start, "2026-06-07T15:00:00+02:00")

    def test_invalid_default_timezone_fails_closed(self):
        payload = {
            "@type": "Event",
            "name": "Meeting",
            "startDate": "2026-06-07T15:00:00",
        }
        with self.assertRaisesRegex(StructuredEventParseError, "timezone"):
            parse_json_ld_events(
                as_json(payload),
                default_timezone="Mars/Olympus",
            )

    def test_malformed_unrelated_html_block_does_not_destroy_valid_event(self):
        html = (
            "<html><head>"
            '<script type="application/ld+json">'
            '{"@type":"Article", broken}'
            "</script>"
            '<script type="application/ld+json">'
            f"{as_json(AMFIS_EVENT)}"
            "</script></head></html>"
        )
        self.assertEqual(len(parse_json_ld_events(html)), 1)

    def test_malformed_event_bearing_html_block_fails_closed(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Event","name":"Broken",}'
            "</script>"
        )
        with self.assertRaisesRegex(
            StructuredEventParseError,
            "malformed Event",
        ):
            parse_json_ld_events(html)

    def test_malformed_raw_json_fails_closed(self):
        with self.assertRaisesRegex(StructuredEventParseError, "JSON"):
            parse_json_ld_events('{"@type":"Event",}')

    def test_nonexistent_or_ambiguous_default_wall_time_fails_closed(self):
        for value in ("2026-03-29T02:30:00", "2026-10-25T02:30:00"):
            payload = {
                "@type": "Event",
                "name": "Meeting",
                "startDate": value,
            }
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    StructuredEventParseError,
                    "nonexistent|ambiguous",
                ):
                    parse_json_ld_events(
                        as_json(payload),
                        default_timezone="Europe/Paris",
                    )

    def test_same_bytes_are_deterministic(self):
        supplied = as_json([ACTION_EVENT, AMFIS_EVENT]).encode("utf-8")
        self.assertEqual(
            parse_json_ld_events(supplied),
            parse_json_ld_events(supplied),
        )

    def test_parser_performs_no_network_access(self):
        with (
            mock.patch("urllib.request.urlopen", side_effect=AssertionError),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError,
            ),
        ):
            self.assertEqual(
                len(parse_json_ld_events(as_json(ACTION_EVENT))),
                1,
            )

    def test_module_import_performs_no_network_access(self):
        with (
            mock.patch("urllib.request.urlopen", side_effect=AssertionError),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError,
            ),
        ):
            importlib.reload(campaign_event_jsonld)


if __name__ == "__main__":
    unittest.main()

