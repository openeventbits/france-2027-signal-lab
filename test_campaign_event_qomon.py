import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request

import campaign_event_qomon as qomon
from campaign_event_sources import normalize_campaign_event_source_registry
from http_fetch import HttpFetchResult


ROOT = Path(__file__).resolve().parent
HUB_URL = "https://agenda.example.org/fr/"
ACTION_A = "https://agenda.example.org/action/a1-first-action/"
ACTION_B = "https://agenda.example.org/action/b2-second-action/"
ICS_A = "https://action.qomon.org/a1-first-action/first-action.ics"
ICS_B = "https://action.qomon.org/b2-second-action/second-action.ics"
OBSERVED_AT = "2026-08-10T20:00:00Z"


def source():
    return {
        "source_id": "example-qomon",
        "publisher": "Example Party",
        "source_type": "party_first_party",
        "url": HUB_URL,
        "allowed_lanes": ["campaign_events"],
        "allowed_event_types": [
            "rally",
            "public_meeting",
            "debate",
            "candidate_visit",
            "campaign_launch",
            "other",
        ],
        "enabled": True,
        "required": False,
        "refresh_class": "daily",
        "zero_result_valid": True,
        "organization": "Example Party",
        "collection": {
            "discovery_method": "custom",
            "parser_family": "custom",
            "attribution_policy": "explicit_participant",
            "collector_family": "qomon",
        },
    }


def html(*links, body=""):
    anchors = "".join(f'<a href="{link}">link</a>' for link in links)
    return f"<!doctype html><html><body>{body}{anchors}</body></html>".encode()


def action_html(
    ics_url=ICS_A,
    *,
    description="Public page description",
    location=("4 Place du Palais Bourbon", "75007 Paris", "France"),
    organizer=None,
    participants=(),
    unrelated_paragraphs=(),
):
    participant_html = "".join(
        f'<span itemprop="performer">{name}</span>' for name in participants
    )
    description_html = (
        '<div class="font-body description-container">'
        f'<div class="my-6 mt-4 bodyText"><p>{description}</p></div>'
        "</div>"
        if description is not None
        else ""
    )
    location_lines = (location,) if isinstance(location, str) else location
    venue_html = ""
    if location_lines is not None:
        address_html = "".join(f"<p>{line}</p>" for line in location_lines)
        venue_html = (
            '<div class="flex w-full md:w-1/2 flex-col gap-y-4 '
            'bg-pinkLighted p-6 rounded-2xl justify-between">'
            "<h2>Where</h2>"
            '<div class="flex flex-col gap-y-4">'
            '<div class="flex flex-row gap-x-2"><span>pin</span><div>'
            f"{address_html}</div></div>"
            '<div class="flex flex-row gap-x-2 items-start pt-3">'
            '<p class="text-xs font-semibold">Access details</p>'
            '<p class="text-sm font-semibold">Venue label</p>'
            "</div></div>"
            '<a href="https://www.google.com/maps/search/?api=1&amp;query=1,2">'
            "Open in Google Maps</a></div>"
        )
    organizer_html = (
        f'<span itemprop="organizer">{organizer}</span>'
        if organizer is not None
        else ""
    )
    unrelated_html = "".join(
        f'<div class="ordinary-copy"><p>{value}</p></div>'
        for value in unrelated_paragraphs
    )
    body = (
        '<div id="bodyContainer" class="bodyContainer action-body-container">'
        '<h1 class="text-5xl mb-2 dynamicLabelColor">Public page title</h1>'
        f"{venue_html}{description_html}{organizer_html}{participant_html}"
        f"{unrelated_html}</div>"
    )
    return html(
        body=body
        + f'<a class="specialLink" href="{ics_url}">Add to calendar</a>'
    )


def ics(
    uid="qomon-a@qomon.com",
    *,
    title="Meeting public avec David Lisnard",
    start="20260827T143000Z",
    end="20260827T180000Z",
    location="Europe/Paris",
    action_id="110480",
):
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Qomon//Action//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART:{start}\r\n"
        f"DTEND:{end}\r\n"
        f"SUMMARY:{title}\r\n"
        "DESCRIPTION:ICS description\r\n"
        "ORGANIZER:Example Party\r\n"
        f"LOCATION:{location}\r\n"
        f"URL:https://qomon.app.link/action?id={action_id}\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT30M\r\n"
        "ACTION:DISPLAY\r\n"
        "DESCRIPTION:Reminder\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()


def fetch_result(url, body, *, final_url=None):
    return HttpFetchResult(
        success=True,
        not_modified=False,
        status_code=200,
        response_body=body,
        final_url=final_url or url,
        attempts=1,
        elapsed_ms=1,
        etag=None,
        last_modified=None,
        failure_category=None,
        failure_message=None,
        response_bytes=len(body),
        retry_after_used=False,
    )


class Fetcher:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, *, max_response_bytes):
        self.calls.append((url, max_response_bytes))
        supplied = self.routes[url]
        if isinstance(supplied, HttpFetchResult):
            return supplied
        return fetch_result(url, supplied)


class QomonCollectorTests(unittest.TestCase):
    def test_existing_custom_source_contract_accepts_qomon_family(self):
        normalized = normalize_campaign_event_source_registry(
            {"schema_version": "2.0", "sources": [source()]},
            candidate_registry_path=ROOT / "candidate_candidacy_status.json",
        )
        self.assertEqual(
            normalized["sources"][0]["collection"],
            {
                "discovery_method": "custom",
                "parser_family": "custom",
                "attribution_policy": "explicit_participant",
                "collector_family": "qomon",
            },
        )

    def test_production_fetch_installs_origin_locked_opener(self):
        body = html()
        with mock.patch.object(
            qomon,
            "fetch_news_route",
            return_value=fetch_result(HUB_URL, body),
        ) as fetcher:
            qomon._fetch_body(
                HUB_URL,
                hostname="agenda.example.org",
                port=443,
                context="Qomon hub page",
                maximum_bytes=qomon.MAX_HTML_BYTES,
                fetch_callable=fetcher,
            )
        self.assertIsInstance(
            fetcher.call_args.kwargs["opener"], qomon._OriginLockedOpener
        )

    def test_semantic_address_with_line_breaks_is_normalized(self):
        page = qomon._page_facts(
            html(
                ICS_A,
                body=(
                    "<h1>Title</h1><address>4 Place du Palais Bourbon<br>"
                    "75007 Paris<br>France</address>"
                ),
            ),
            context="Qomon action page",
        )
        self.assertEqual(
            page.location_name,
            "4 Place du Palais Bourbon 75007 Paris France",
        )

    def test_live_qomon_description_and_venue_components_are_extracted(self):
        description = (
            "Ce sera l’occasion de soutenir notre candidat, Bruno Retailleau, "
            "et de suivre le débat ensemble."
        )
        page = qomon._page_facts(
            action_html(
                description=description,
                location=(
                    "4 Place du Palais Bourbon",
                    "75007 Paris",
                    "France",
                ),
                unrelated_paragraphs=(
                    "Navigation paragraph",
                    "99 Avenue extérieure 75000 Paris",
                    "Footer legal copy",
                ),
            ),
            context="Qomon action page",
        )

        self.assertEqual(page.title, "Public page title")
        self.assertEqual(page.description, description)
        self.assertEqual(
            page.location_name,
            "4 Place du Palais Bourbon 75007 Paris France",
        )
        self.assertNotIn("Navigation", page.description)
        self.assertNotIn("Avenue extérieure", page.location_name)
        self.assertEqual(page.organization, None)
        self.assertEqual(page.participants, ())
        self.assertEqual(page.ics_url, ICS_A)

    def test_unsupported_ordinary_paragraphs_do_not_create_page_facts(self):
        page = qomon._page_facts(
            action_html(
                description=None,
                location=None,
                unrelated_paragraphs=(
                    "Ordinary event prose",
                    "10 Rue ordinaire 75000 Paris France",
                ),
            ),
            context="Qomon action page",
        )

        self.assertIsNone(page.description)
        self.assertIsNone(page.location_name)
        self.assertEqual(page.participants, ())

    def test_ics_organizer_survives_without_page_organizer(self):
        page = qomon._page_facts(
            action_html(organizer=None),
            context="Qomon action page",
        )
        parsed = qomon.parse_ics_events(ics())[0]
        self.assertEqual(parsed.organization, "Example Party")

        merged = qomon._merged_record(parsed, page)

        self.assertEqual(merged.organization, "Example Party")
        self.assertEqual(
            merged.location_name,
            "4 Place du Palais Bourbon 75007 Paris France",
        )
        self.assertEqual(merged.participants, ())

    def extract(self, routes, *, supplied_source=None):
        fetcher = Fetcher(routes)
        events, actions, parsed = qomon._extract_qomon_events(
            source=supplied_source or source(), fetch_callable=fetcher
        )
        return events, actions, parsed, fetcher

    def build(self, routes, *, supplied_source=None):
        supplied_source = supplied_source or source()
        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "sources.json"
            registry_path.write_text(
                json.dumps(
                    {"schema_version": "2.0", "sources": [supplied_source]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            fetcher = Fetcher(routes)
            result = qomon.build_qomon_events(
                source=supplied_source,
                observed_at=OBSERVED_AT,
                fetch_callable=fetcher,
                source_registry_path=registry_path,
            )
        return result, fetcher

    def test_structural_action_discovery_is_deduplicated_and_bounded(self):
        hub = html(
            "/about/",
            "/action/a1-first-action/",
            "/action/a1-first-action/?tracking=1",
            "https://outside.example/action/x1-outside/",
            "/fr/action/not-the-route/",
        )
        events, actions, parsed, fetcher = self.extract(
            {HUB_URL: hub, ACTION_A: action_html(), ICS_A: ics()}
        )

        self.assertEqual((actions, parsed, len(events)), (1, 1, 1))
        self.assertEqual(
            [url for url, _maximum in fetcher.calls],
            [HUB_URL, ACTION_A, ICS_A],
        )

    def test_arbitrary_and_off_origin_hub_links_are_never_fetched(self):
        events, actions, parsed, fetcher = self.extract(
            {
                HUB_URL: html(
                    "/ordinary-page/",
                    "https://outside.example/action/x1-outside/",
                )
            }
        )

        self.assertEqual((events, actions, parsed), ((), 0, 0))
        self.assertEqual(fetcher.calls, [(HUB_URL, qomon.MAX_HTML_BYTES)])

    def test_action_page_final_url_must_remain_on_hub_origin(self):
        fetcher = Fetcher(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: fetch_result(
                    ACTION_A,
                    action_html(),
                    final_url="https://outside.example/action/a1-first-action/",
                ),
            }
        )
        with self.assertRaisesRegex(qomon.QomonCollectorError, "redirected off"):
            qomon._extract_qomon_events(source=source(), fetch_callable=fetcher)
        self.assertEqual(len(fetcher.calls), 2)

    def test_literal_trusted_calendar_link_is_accepted(self):
        events, _actions, _parsed, fetcher = self.extract(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: action_html(),
                ICS_A: ics(),
            }
        )
        self.assertEqual(events[0].ics_url, ICS_A)
        self.assertEqual(fetcher.calls[-1], (ICS_A, qomon.MAX_ICS_BYTES))

    def test_untrusted_calendar_urls_fail_before_fetch(self):
        invalid_urls = (
            "https://outside.example/event.ics",
            "http://action.qomon.org/event.ics",
            "https://action.qomon.org:444/event.ics",
            "https://user@action.qomon.org/event.ics",
        )
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                fetcher = Fetcher(
                    {
                        HUB_URL: html("/action/a1-first-action/"),
                        ACTION_A: action_html(invalid_url),
                    }
                )
                with self.assertRaisesRegex(
                    qomon.QomonCollectorError, "trusted Qomon calendar origin"
                ):
                    qomon._extract_qomon_events(
                        source=source(), fetch_callable=fetcher
                    )
                self.assertEqual(
                    [url for url, _maximum in fetcher.calls],
                    [HUB_URL, ACTION_A],
                )

    def test_redirect_guards_allow_only_their_exact_https_origin(self):
        cases = (
            ("agenda.example.org", Request(ACTION_A)),
            (qomon.QOMON_CALENDAR_HOSTNAME, Request(ICS_A)),
        )
        for hostname, request in cases:
            with self.subTest(hostname=hostname):
                handler = qomon._SameOriginRedirectHandler(
                    hostname=hostname, port=443
                )
                allowed = f"https://{hostname}/new-path"
                redirected = handler.redirect_request(
                    request, None, 302, "Found", {}, allowed
                )
                self.assertEqual(redirected.full_url, allowed)
                for target in (
                    "https://outside.example/new-path",
                    f"http://{hostname}/new-path",
                    f"https://{hostname}:444/new-path",
                    f"https://user@{hostname}/new-path",
                ):
                    with self.assertRaisesRegex(
                        qomon.QomonCollectorError, "leaves the approved HTTPS origin"
                    ):
                        handler.redirect_request(
                            request, None, 302, "Found", {}, target
                        )

    def test_malformed_ics_is_collection_failure(self):
        with self.assertRaisesRegex(qomon.QomonCollectorError, "malformed"):
            self.extract(
                {
                    HUB_URL: html("/action/a1-first-action/"),
                    ACTION_A: action_html(),
                    ICS_A: b"not an iCalendar document",
                }
            )

    def test_missing_action_calendar_does_not_fabricate_event(self):
        with self.assertRaisesRegex(qomon.QomonCollectorError, "no literal"):
            self.extract(
                {
                    HUB_URL: html("/action/a1-first-action/"),
                    ACTION_A: action_html().replace(ICS_A.encode(), b"/about/"),
                }
            )

    def test_page_and_ics_merge_precedence_and_action_identity(self):
        events, _actions, _parsed, _fetcher = self.extract(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: action_html(
                    description="Richer page description",
                    location="4 Place du Palais Bourbon 75007 Paris France",
                    organizer="Explicit Organizer",
                ),
                ICS_A: ics(),
            }
        )
        merged = events[0]

        self.assertEqual(merged.record.external_id, "qomon-a@qomon.com")
        self.assertEqual(merged.record.scheduled_start, "2026-08-27T16:30:00+02:00")
        self.assertEqual(merged.record.scheduled_end, "2026-08-27T20:00:00+02:00")
        self.assertEqual(merged.record.title, "Meeting public avec David Lisnard")
        self.assertEqual(merged.record.description, "Richer page description")
        self.assertEqual(
            merged.record.location_name,
            "4 Place du Palais Bourbon 75007 Paris France",
        )
        self.assertEqual(merged.record.organization, "Explicit Organizer")
        self.assertEqual(merged.raw_ics_location, "Europe/Paris")
        self.assertEqual(merged.action_id, "110480")

    def test_timezone_like_ics_location_is_not_used_as_physical_venue(self):
        page = qomon._PageFacts(None, None, None, None, (), ICS_A)
        record = qomon.parse_ics_events(ics())[0]
        merged = qomon._merged_record(record, page)
        self.assertIsNone(merged.location_name)

    def test_structural_participant_evidence_reaches_attribution(self):
        result, _fetcher = self.build(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: action_html(participants=("David Lisnard",)),
                ICS_A: ics(title="Meeting public"),
            }
        )

        self.assertEqual(result.attribution_rejected_records, 0)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0]["candidate_ids"], ["david-lisnard"])
        self.assertEqual(result.observations[0]["participants"], ["David Lisnard"])
        self.assertEqual(
            result.observations[0]["evidence"][0]["source_url"], ACTION_A
        )

    def test_prose_candidate_mention_does_not_become_participant(self):
        description = "Nous soutenons Bruno Retailleau pendant le débat."
        events, _actions, _parsed, _fetcher = self.extract(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: action_html(description=description),
                ICS_A: ics(title="Campagne présidentielle 2027 - Débat public"),
            }
        )
        self.assertEqual(events[0].record.description, description)
        self.assertEqual(events[0].record.participants, ())

        result, _fetcher = self.build(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: action_html(description=description),
                ICS_A: ics(title="Campagne présidentielle 2027 - Débat public"),
            }
        )
        self.assertEqual(result.observations, ())
        self.assertEqual(result.attribution_rejected_records, 1)

    def test_ics_uid_drives_stable_source_owned_identity(self):
        routes = {
            HUB_URL: html("/action/a1-first-action/"),
            ACTION_A: action_html(participants=("David Lisnard",)),
            ICS_A: ics(title="Meeting public"),
        }
        first, _fetcher = self.build(routes)
        changed_routes = dict(routes)
        changed_routes[ACTION_A] = action_html(
            description="Changed enrichment",
            location="Another physical venue",
            participants=("David Lisnard",),
        )
        second, _fetcher = self.build(changed_routes)

        self.assertEqual(
            first.observations[0]["event_key"], second.observations[0]["event_key"]
        )
        self.assertEqual(
            first.observations[0]["event_id"], second.observations[0]["event_id"]
        )
        self.assertIn("-uid-", first.observations[0]["event_key"])

    def test_deterministic_output_ordering(self):
        routes = {
            HUB_URL: html(
                "/action/b2-second-action/", "/action/a1-first-action/"
            ),
            ACTION_A: action_html(ICS_A, participants=("David Lisnard",)),
            ACTION_B: action_html(ICS_B, participants=("David Lisnard",)),
            ICS_A: ics(uid="z-uid@qomon.com", title="Meeting public A"),
            ICS_B: ics(uid="a-uid@qomon.com", title="Meeting public B"),
        }
        result, fetcher = self.build(routes)
        action_calls = [url for url, _maximum in fetcher.calls if "/action/" in url]

        self.assertEqual(action_calls, [ACTION_A, ACTION_B])
        self.assertEqual(
            list(result.observations),
            sorted(result.observations, key=lambda item: item["event_key"]),
        )

    def test_conflicting_duplicate_uid_fails_closed(self):
        with self.assertRaisesRegex(
            qomon.QomonCollectorError, "conflicting duplicate Qomon source identity"
        ):
            self.extract(
                {
                    HUB_URL: html(
                        "/action/a1-first-action/", "/action/b2-second-action/"
                    ),
                    ACTION_A: action_html(ICS_A, location="First venue"),
                    ACTION_B: action_html(ICS_B, location="Second venue"),
                    ICS_A: ics(uid="same@qomon.com"),
                    ICS_B: ics(uid="same@qomon.com"),
                }
            )

    def test_incompatible_configuration_fails_before_network(self):
        for field, value in (
            ("discovery_method", "direct"),
            ("parser_family", "ics"),
            ("attribution_policy", "custom"),
            ("collector_family", "linked-ics"),
        ):
            with self.subTest(field=field):
                invalid = source()
                invalid["collection"][field] = value
                fetcher = Fetcher({})
                with self.assertRaises(qomon.QomonCollectorConfigurationError):
                    qomon._extract_qomon_events(
                        source=invalid, fetch_callable=fetcher
                    )
                self.assertEqual(fetcher.calls, [])

    def test_result_diagnostics_are_deterministic(self):
        result, _fetcher = self.build(
            {
                HUB_URL: html("/action/a1-first-action/"),
                ACTION_A: action_html(),
                ICS_A: ics(),
            }
        )
        self.assertEqual(
            (
                result.actions_discovered,
                result.action_pages_attempted,
                result.ics_urls_discovered,
                result.ics_records_parsed,
                result.merged_records,
            ),
            (1, 1, 1, 1, 1),
        )


if __name__ == "__main__":
    unittest.main()
