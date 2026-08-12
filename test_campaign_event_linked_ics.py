"""Tests for generic agenda-page to linked-ICS Campaign Events collection."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import unittest
import uuid
from unittest import mock
from urllib.request import Request

import campaign_event_linked_ics as linked_ics
from campaign_event_ics import parse_ics_events
from campaign_event_sources import normalize_campaign_event_source_registry
from http_fetch import HttpFetchResult


ROOT = Path(__file__).resolve().parent
OBSERVED_AT = "2026-08-10T16:00:00Z"
AGENDA_URL = "https://events.example/agenda"
EVENT_URL = "https://events.example/events/meeting-public"
ICS_URL = "https://events.example/downloads/meeting-public.ics"


def source_record(*, zero_result_valid: bool = True) -> dict[str, object]:
    source = {
        "source_id": "generic-party-calendar",
        "publisher": "Generic Party",
        "source_type": "party_first_party",
        "url": AGENDA_URL,
        "allowed_lanes": ["campaign_events"],
        "allowed_event_types": ["public_meeting", "other"],
        "enabled": True,
        "required": False,
        "refresh_class": "daily",
        "zero_result_valid": zero_result_valid,
        "organization": "Generic Party",
        "collection": {
            "discovery_method": "linked_event_pages",
            "parser_family": "ics",
            "attribution_policy": "explicit_participant",
            "collector_family": "linked-ics",
        },
    }
    return normalize_campaign_event_source_registry(
        {"schema_version": "2.0", "sources": [source]}
    )["sources"][0]


def html(*links: str) -> bytes:
    anchors = "".join(f'<a href="{link}">Event</a>' for link in links)
    return f"<!doctype html><html><body>{anchors}</body></html>".encode()


def ics(summary: str = "Meeting avec David Lisnard") -> bytes:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//FR27 Test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:stable-source-uid-42\r\n"
        "DTSTART:20260912T170000Z\r\n"
        f"SUMMARY:{summary}\r\n"
        "URL:https://events.example/events/meeting-public\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()


def fetch_result(
    url: str,
    body: bytes | None,
    *,
    success: bool = True,
    final_url: str | None = None,
    failure_message: str | None = None,
) -> HttpFetchResult:
    return HttpFetchResult(
        success=success,
        not_modified=False,
        status_code=200 if success else None,
        response_body=body,
        final_url=final_url or url,
        attempts=1,
        elapsed_ms=1,
        etag=None,
        last_modified=None,
        failure_category=None if success else "network_error",
        failure_message=failure_message,
        response_bytes=len(body) if body is not None else 0,
        retry_after_used=False,
    )


class RouteFetcher:
    def __init__(self, routes: dict[str, HttpFetchResult | bytes]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, int | None]] = []

    def __call__(
        self,
        url: str,
        *,
        max_response_bytes: int | None = None,
    ) -> HttpFetchResult:
        self.calls.append((url, max_response_bytes))
        supplied = self.routes.get(url)
        if supplied is None:
            return fetch_result(
                url,
                None,
                success=False,
                failure_message="missing mocked route",
            )
        if isinstance(supplied, HttpFetchResult):
            return supplied
        return fetch_result(url, supplied)


class CampaignEventLinkedIcsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_root = ROOT / (
            f".campaign-event-linked-ics-test-{uuid.uuid4().hex}"
        )
        self.temporary_root.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary_root, True)
        self.source = source_record()
        self.source_registry_path = self.temporary_root / "sources.json"
        self.source_registry_path.write_text(
            json.dumps(
                {"schema_version": "2.0", "sources": [self.source]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def collect(
        self,
        routes: dict[str, HttpFetchResult | bytes],
    ) -> tuple[linked_ics.LinkedIcsCollectorResult, RouteFetcher]:
        fetcher = RouteFetcher(routes)
        result = linked_ics.build_linked_ics_events(
            source=self.source,
            observed_at=OBSERVED_AT,
            fetch_callable=fetcher,
            candidate_registry_path=ROOT / "candidate_candidacy_status.json",
            source_registry_path=self.source_registry_path,
        )
        return result, fetcher

    def test_direct_ics_reuses_parser_and_builds_uid_observation(self):
        payload = ics()
        routes = {
            AGENDA_URL: html("/downloads/meeting-public.ics"),
            ICS_URL: payload,
        }
        with mock.patch.object(
            linked_ics,
            "parse_ics_events",
            wraps=parse_ics_events,
        ) as parser:
            result, fetcher = self.collect(routes)

        parser.assert_called_once_with(payload)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.attribution_rejected_records, 0)
        observation = result.observations[0]
        self.assertEqual(observation["candidate_ids"], ["david-lisnard"])
        self.assertEqual(observation["candidate_names"], ["David Lisnard"])
        self.assertEqual(observation["event_type"], "public_meeting")
        self.assertTrue(
            observation["event_key"].startswith(
                self.source["source_id"] + "-uid-"
            )
        )
        self.assertEqual(
            observation["evidence"][0]["source_url"],
            ICS_URL,
        )
        self.assertNotIn("participants", observation)
        self.assertEqual(
            [url for url, _maximum in fetcher.calls],
            [AGENDA_URL, ICS_URL],
        )
        self.assertEqual(
            [maximum for _url, maximum in fetcher.calls],
            [
                linked_ics.MAX_HTML_BYTES,
                linked_ics.MAX_ICS_BYTES,
            ],
        )

    def test_direct_agenda_ics_is_preferred_deduplicated_and_relative(self):
        routes = {
            AGENDA_URL: html(
                "/downloads/meeting-public.ics",
                "/events/meeting-public",
                "/downloads/meeting-public.ics",
            ),
            ICS_URL: ics(),
            EVENT_URL: html("/downloads/meeting-public.ics"),
        }

        result, fetcher = self.collect(routes)

        self.assertEqual(len(result.observations), 1)
        self.assertEqual(
            [url for url, _maximum in fetcher.calls],
            [AGENDA_URL, ICS_URL],
        )
        self.assertEqual(
            result.observations[0]["evidence"][0]["source_url"],
            ICS_URL,
        )

    def test_same_origin_non_ics_link_is_not_fetched(self):
        result, fetcher = self.collect(
            {
                AGENDA_URL: html("/events/meeting-public"),
                EVENT_URL: html("/downloads/meeting-public.ics"),
            }
        )

        self.assertEqual(result.observations, ())
        self.assertEqual(result.attribution_rejected_records, 0)
        self.assertEqual(fetcher.calls, [(AGENDA_URL, linked_ics.MAX_HTML_BYTES)])

    def test_off_domain_ics_link_is_ignored_without_fetching(self):
        result, fetcher = self.collect(
            {
                AGENDA_URL: html("https://outside.example/event.ics"),
            }
        )

        self.assertEqual(result.observations, ())
        self.assertEqual(fetcher.calls, [(AGENDA_URL, linked_ics.MAX_HTML_BYTES)])

    def test_unattributed_ics_event_does_not_gain_participants(self):
        payload = ics("Meeting public")
        self.assertEqual(parse_ics_events(payload)[0].participants, ())

        result, _fetcher = self.collect(
            {
                AGENDA_URL: html("/downloads/meeting-public.ics"),
                ICS_URL: payload,
            }
        )

        self.assertEqual(result.observations, ())
        self.assertEqual(result.attribution_rejected_records, 1)

    def test_malformed_ics_is_a_collection_failure_not_zero(self):
        with self.assertRaisesRegex(
            linked_ics.LinkedIcsCollectorError,
            "ICS payload is malformed",
        ):
            self.collect(
                {
                    AGENDA_URL: html("/downloads/meeting-public.ics"),
                    ICS_URL: b"not an iCalendar payload",
                }
            )

    def test_fetch_and_malformed_page_failures_are_not_zero_results(self):
        cases = (
            {
                AGENDA_URL: fetch_result(
                    AGENDA_URL,
                    None,
                    success=False,
                    failure_message="network unavailable",
                )
            },
            {AGENDA_URL: b"not an HTML document"},
        )
        for routes in cases:
            with self.subTest(routes=routes):
                with self.assertRaises(linked_ics.LinkedIcsCollectorError):
                    self.collect(routes)

    def test_agenda_with_only_html_links_returns_valid_zero(self):
        self.assertTrue(self.source["zero_result_valid"])

        result, fetcher = self.collect(
            {
                AGENDA_URL: html(
                    "/events/meeting-public",
                    "/about",
                ),
                EVENT_URL: html("/downloads/meeting-public.ics"),
            }
        )

        self.assertEqual(
            result,
            linked_ics.LinkedIcsCollectorResult(
                observations=(),
                attribution_rejected_records=0,
            ),
        )
        self.assertEqual(fetcher.calls, [(AGENDA_URL, linked_ics.MAX_HTML_BYTES)])

    def test_stable_ics_uid_preserves_source_owned_identity(self):
        first, _fetcher = self.collect(
            {
                AGENDA_URL: html("/downloads/meeting-public.ics"),
                ICS_URL: ics("Meeting avec David Lisnard"),
            }
        )
        second, _fetcher = self.collect(
            {
                AGENDA_URL: html("/downloads/meeting-public.ics"),
                ICS_URL: ics("Meeting public avec David Lisnard"),
            }
        )

        self.assertEqual(len(first.observations), 1)
        self.assertEqual(len(second.observations), 1)
        self.assertEqual(
            first.observations[0]["event_key"],
            second.observations[0]["event_key"],
        )
        self.assertEqual(
            first.observations[0]["event_id"],
            second.observations[0]["event_id"],
        )

    def test_incompatible_collection_shapes_fail_before_fetch(self):
        cases = (
            {"collector_family": None},
            {"discovery_method": "direct"},
            {"parser_family": "json_ld"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                source = copy.deepcopy(self.source)
                for field, value in changes.items():
                    if value is None:
                        source["collection"].pop(field)
                    else:
                        source["collection"][field] = value
                fetcher = RouteFetcher({AGENDA_URL: html()})
                with self.assertRaisesRegex(
                    linked_ics.LinkedIcsCollectorConfigurationError,
                    "linked-ics family",
                ):
                    linked_ics.build_linked_ics_events(
                        source=source,
                        observed_at=OBSERVED_AT,
                        fetch_callable=fetcher,
                    )
                self.assertEqual(fetcher.calls, [])

    def test_redirect_guard_allows_only_same_https_origin(self):
        handler = linked_ics._SameOriginRedirectHandler(
            hostname="events.example",
            port=443,
        )
        request = Request(AGENDA_URL)

        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://events.example/new-agenda",
        )
        self.assertEqual(
            redirected.full_url,
            "https://events.example/new-agenda",
        )

        for target in (
            "https://outside.example/new-agenda",
            "http://events.example/new-agenda",
            "https://events.example:444/new-agenda",
            "https://user@events.example/new-agenda",
        ):
            with self.subTest(target=target):
                with self.assertRaisesRegex(
                    linked_ics.LinkedIcsCollectorError,
                    "leaves the approved HTTPS origin",
                ):
                    handler.redirect_request(
                        request,
                        None,
                        302,
                        "Found",
                        {},
                        target,
                    )

    def test_production_fetch_installs_origin_locked_opener(self):
        with mock.patch.object(
            linked_ics,
            "fetch_news_route",
            return_value=fetch_result(AGENDA_URL, html()),
        ) as fetcher:
            linked_ics._fetch_body(
                AGENDA_URL,
                hostname="events.example",
                port=443,
                context="agenda page",
                maximum_bytes=linked_ics.MAX_HTML_BYTES,
                fetch_callable=fetcher,
            )

        self.assertIsInstance(
            fetcher.call_args.kwargs["opener"],
            linked_ics._OriginLockedOpener,
        )

    def test_off_domain_redirect_is_a_collection_failure(self):
        with self.assertRaisesRegex(
            linked_ics.LinkedIcsCollectorError,
            "redirected off the approved origin",
        ):
            self.collect(
                {
                    AGENDA_URL: fetch_result(
                        AGENDA_URL,
                        html(),
                        final_url="https://outside.example/agenda",
                    )
                }
            )


if __name__ == "__main__":
    unittest.main()
