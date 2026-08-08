import copy
import importlib
import json
import socket
import sys
import unittest
from unittest import mock

from http_fetch import HttpFetchResult
from rn_agenda_adapter import (
    RN_AGENDA_URL,
    RnAgendaAdapterError,
    build_rn_agenda_events,
    fetch_rn_agenda,
    parse_rn_agenda_html,
)


OBSERVED_AT = "2026-08-02T04:45:00Z"
CURRENT_DESCRIPTION = (
    "Marine Le Pen débattra en direct sur LCI à l'occasion d'un grand débat "
    "de la campagne présidentielle, organisé par le MEDEF, le jeudi "
    "27 août 2026 à partir de 16h45."
)
PROHIBITED_FIELDS = {
    "attendance",
    "broadcast_duration",
    "confidence",
    "department",
    "locality",
    "location",
    "location_name",
    "momentum",
    "participants",
    "prediction",
    "probability",
    "ranking",
    "scheduled_end",
    "sentiment",
    "viability",
}


def card(
    *,
    day="27",
    month="août",
    time="16h45",
    title="Marine Le Pen sur LCI",
    category="Medias",
    description=CURRENT_DESCRIPTION,
):
    title_html = "" if title is None else f"<h3>{title}</h3>"
    category_html = "" if category is None else f'<p class="category">{category}</p>'
    description_html = (
        ""
        if description is None
        else f'<p class="description">{description}</p>'
    )
    return f"""
    <article class="agenda-card">
      <div class="date">
        <h2>{day}</h2>
        <p class="month">{month}</p>
        <h3>{time}</h3>
      </div>
      <div class="details">
        {title_html}
        {category_html}
        {description_html}
      </div>
    </article>
    """


def page(*cards, include_h1=True, include_region=True):
    heading = "<h1>Agenda</h1>" if include_h1 else "<h2>Agenda</h2>"
    region = (
        f'<div class="agenda-events divide-y">{"".join(cards)}</div>'
        if include_region
        else '<div class="content-missing">Aucune région structurée</div>'
    )
    return f"""<!doctype html>
    <html lang="fr">
      <body>
        <header>
          <a>Jean-Paul Garraud - 01 août 2026</a>
          <a>Jean-Paul Garraud - 31 juillet 2026</a>
          <nav>Présidentielle 2022</nav>
        </header>
        <main><section>{heading}{region}</section></main>
        <footer>Programme du 28 février 2026 à 17h00</footer>
      </body>
    </html>"""


def fetch_result(
    body,
    *,
    success=True,
    status_code=200,
    failure_category=None,
    failure_message=None,
):
    return HttpFetchResult(
        success=success,
        not_modified=False,
        status_code=status_code,
        response_body=body,
        final_url=RN_AGENDA_URL,
        attempts=1,
        elapsed_ms=1,
        etag=None,
        last_modified=None,
        failure_category=failure_category,
        failure_message=failure_message,
        response_bytes=len(body) if isinstance(body, bytes) else 0,
        retry_after_used=False,
    )


class RnAgendaAdapterTests(unittest.TestCase):
    def parse(self, html=None, observed_at=OBSERVED_AT):
        return parse_rn_agenda_html(
            page(card()) if html is None else html,
            observed_at=observed_at,
        )

    def assert_parser_error(self, html, pattern=None):
        context = self.assertRaises(RnAgendaAdapterError)
        with context:
            self.parse(html)
        if pattern is not None:
            self.assertRegex(str(context.exception), pattern)

    def test_audited_listing_yields_exact_current_event(self):
        events = self.parse()
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0],
            {
                "event_key": (
                    "rn-agenda-marine-le-pen-2026-08-27-1645-debate"
                ),
                "event_id": "ce-de75c4df4e8c72a7cc486f26",
                "event_type": "debate",
                "title": "Marine Le Pen sur LCI",
                "candidate_ids": ["marine-le-pen"],
                "candidate_names": ["Marine Le Pen"],
                "scheduled_start": "2026-08-27T16:45:00+02:00",
                "time_precision": "datetime",
                "timezone": "Europe/Paris",
                "organization": "MEDEF",
                "status": "scheduled",
                "status_as_of": "2026-08-02",
                "evidence_status": "verified",
                "last_verified_at": OBSERVED_AT,
                "evidence": [
                    {
                        "source_id": "rn-agenda",
                        "source_url": RN_AGENDA_URL,
                        "source_publisher": "Rassemblement National",
                        "source_type": "party_first_party",
                        "evidence_type": "explicit_schedule",
                    }
                ],
            },
        )

    def test_global_header_and_footer_dates_are_ignored(self):
        event = self.parse()[0]
        self.assertEqual(event["scheduled_start"], "2026-08-27T16:45:00+02:00")
        serialized = json.dumps(event, ensure_ascii=False)
        self.assertNotIn("2026-08-01T", serialized)
        self.assertNotIn("2026-07-31T", serialized)
        self.assertNotIn("2026-02-28T", serialized)

    def test_header_day_month_uses_description_year_and_parses_aout(self):
        event = self.parse()[0]
        self.assertEqual(event["scheduled_start"][:10], "2026-08-27")
        self.assertEqual(event["scheduled_start"][-6:], "+02:00")

    def test_winter_date_uses_paris_standard_time(self):
        description = (
            "Marine Le Pen participera à un débat de la campagne présidentielle "
            "le 15 janvier 2027 à 19h30."
        )
        event = self.parse(
            page(
                card(
                    day="15",
                    month="janvier",
                    time="19h30",
                    title="Marine Le Pen en débat",
                    description=description,
                )
            )
        )[0]
        self.assertEqual(event["scheduled_start"], "2027-01-15T19:30:00+01:00")

    def test_nonexistent_paris_wall_time_is_rejected(self):
        description = (
            "Marine Le Pen participera à un débat de la campagne présidentielle "
            "le 28 mars 2027 à 02h30."
        )
        self.assert_parser_error(
            page(
                card(
                    day="28",
                    month="mars",
                    time="02h30",
                    description=description,
                )
            ),
            "nonexistent Europe/Paris local time",
        )

    def test_ambiguous_paris_wall_time_is_rejected(self):
        description = (
            "Marine Le Pen participera à un débat de la campagne présidentielle "
            "le 31 octobre 2027 à 02h30."
        )
        self.assert_parser_error(
            page(
                card(
                    day="31",
                    month="octobre",
                    time="02h30",
                    description=description,
                )
            ),
            "ambiguous Europe/Paris local time",
        )

    def test_header_description_date_mismatch_fails(self):
        self.assert_parser_error(
            page(card(day="26")),
            "date mismatch",
        )

    def test_displayed_description_time_mismatch_fails(self):
        self.assert_parser_error(
            page(card(time="16h30")),
            "time mismatch",
        )

    def test_missing_description_year_fails(self):
        description = (
            "Marine Le Pen débattra dans la campagne présidentielle "
            "le 27 août à 16h45."
        )
        self.assert_parser_error(page(card(description=description)), "full date")

    def test_missing_title_fails(self):
        self.assert_parser_error(page(card(title=None)), "title")

    def test_missing_description_fails(self):
        self.assert_parser_error(
            page(card(category=None, description=None)),
            "description",
        )

    def test_missing_h1_agenda_fails(self):
        self.assert_parser_error(page(card(), include_h1=False), "H1 Agenda")

    def test_missing_agenda_region_fails(self):
        self.assert_parser_error(
            page(card(), include_region=False),
            "content region",
        )

    def test_valid_empty_agenda_region_returns_empty(self):
        self.assertEqual(self.parse(page()), [])

    def test_valid_non_presidential_agenda_event_returns_empty(self):
        description = "Réunion publique du parti le 27 août 2026 à 16h45."
        self.assertEqual(self.parse(page(card(description=description))), [])

    def test_municipal_rn_event_is_excluded(self):
        description = (
            "Marine Le Pen assistera à une réunion de la campagne municipale "
            "le 27 août 2026 à 16h45."
        )
        self.assertEqual(self.parse(page(card(description=description))), [])

    def test_generic_media_appearance_is_excluded(self):
        description = (
            "Marine Le Pen répondra aux questions de LCI le 27 août 2026 "
            "à 16h45."
        )
        self.assertEqual(self.parse(page(card(description=description))), [])

    def test_surname_only_does_not_map_marine_le_pen(self):
        description = (
            "Le Pen participera à un débat de la campagne présidentielle "
            "le 27 août 2026 à 16h45."
        )
        self.assertEqual(
            self.parse(page(card(title="Le Pen sur LCI", description=description))),
            [],
        )

    def test_explicit_cancellation_text_fails_closed(self):
        for wording in (
            "annulé",
            "annulée",
            "annulés",
            "annulées",
            "annulation",
            "déprogrammé",
            "déprogrammée",
            "déprogrammés",
            "déprogrammées",
        ):
            with self.subTest(wording=wording):
                description = (
                    "Marine Le Pen participera à un débat de la campagne "
                    "présidentielle le 27 août 2026 à 16h45. "
                    f"Événement {wording}."
                )
                self.assert_parser_error(
                    page(card(description=description)),
                    "negative lifecycle",
                )

    def test_explicit_postponement_text_fails_closed(self):
        for wording in ("reporté", "reportée", "reportés", "reportées"):
            with self.subTest(wording=wording):
                description = (
                    "Marine Le Pen participera à un débat de la campagne "
                    "présidentielle le 27 août 2026 à 16h45. "
                    f"Émission {wording}."
                )
                self.assert_parser_error(
                    page(card(description=description)),
                    "negative lifecycle",
                )

    def test_negative_lifecycle_longer_token_near_miss_remains_scheduled(self):
        description = (
            "Marine Le Pen participera à un débat de la campagne "
            "présidentielle le 27 août 2026 à 16h45. "
            "Le code interne xannulés reste inchangé."
        )
        event = self.parse(page(card(description=description)))[0]
        self.assertEqual(event["status"], "scheduled")
        self.assertEqual(
            event["event_key"],
            "rn-agenda-marine-le-pen-2026-08-27-1645-debate",
        )

    def test_unsupported_canonical_candidate_fails_closed(self):
        description = (
            "Jordan Bardella participera à un débat de la campagne "
            "présidentielle le 27 août 2026 à 16h45."
        )
        self.assert_parser_error(
            page(card(title="Jordan Bardella sur LCI", description=description)),
            "unsupported canonical candidate",
        )

    def test_canonical_marine_le_pen_pair_is_accepted(self):
        registry = {
            "candidates": [
                {
                    "candidate_name": "Marine Le Pen",
                    "candidate_id": "marine-le-pen",
                }
            ]
        }
        with mock.patch(
            "rn_agenda_adapter.load_candidate_candidacy_status",
            return_value=registry,
        ):
            event = self.parse()[0]
        self.assertEqual(event["candidate_ids"], ["marine-le-pen"])

    def test_missing_canonical_marine_le_pen_pair_fails_closed(self):
        with mock.patch(
            "rn_agenda_adapter.load_candidate_candidacy_status",
            return_value={"candidates": []},
        ):
            self.assert_parser_error(page(card()), "must contain exactly")

    def test_wrong_canonical_marine_le_pen_id_fails_closed(self):
        registry = {
            "candidates": [
                {
                    "candidate_name": "Marine Le Pen",
                    "candidate_id": "wrong-candidate-id",
                }
            ]
        }
        with mock.patch(
            "rn_agenda_adapter.load_candidate_candidacy_status",
            return_value=registry,
        ):
            self.assert_parser_error(page(card()), "must contain exactly")

    def test_candidate_registry_loads_once_for_multiple_cards(self):
        registry = {
            "candidates": [
                {
                    "candidate_name": "Marine Le Pen",
                    "candidate_id": "marine-le-pen",
                }
            ]
        }
        winter_description = (
            "Marine Le Pen participera à un débat de la campagne présidentielle "
            "le 15 janvier 2027 à 19h30."
        )
        winter = card(
            day="15",
            month="janvier",
            time="19h30",
            title="Marine Le Pen en débat en janvier",
            description=winter_description,
        )
        with mock.patch(
            "rn_agenda_adapter.load_candidate_candidacy_status",
            return_value=registry,
        ) as loader:
            events = self.parse(page(card(), winter))
        self.assertEqual(len(events), 2)
        loader.assert_called_once()

    def test_multiple_eligible_events_are_deterministically_sorted(self):
        winter_description = (
            "Marine Le Pen participera à un débat de la campagne présidentielle "
            "le 15 janvier 2027 à 19h30."
        )
        winter = card(
            day="15",
            month="janvier",
            time="19h30",
            title="Marine Le Pen en débat en janvier",
            description=winter_description,
        )
        first = self.parse(page(winter, card()))
        second = self.parse(page(card(), winter))
        self.assertEqual(first, second)
        self.assertEqual(
            [event["scheduled_start"] for event in first],
            ["2026-08-27T16:45:00+02:00", "2027-01-15T19:30:00+01:00"],
        )

    def test_identical_duplicate_events_deduplicate(self):
        duplicate = card()
        self.assertEqual(len(self.parse(page(duplicate, duplicate))), 1)

    def test_conflicting_duplicate_identity_fails(self):
        self.assert_parser_error(
            page(card(), card(title="Marine Le Pen face aux partenaires sociaux")),
            "conflicting duplicate",
        )

    def test_parser_performs_no_network_access(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ):
            events = self.parse()
        self.assertEqual(len(events), 1)

    def test_module_import_performs_no_network_access(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ):
            original = sys.modules.pop("rn_agenda_adapter")
            try:
                module = importlib.import_module("rn_agenda_adapter")
            finally:
                sys.modules["rn_agenda_adapter"] = original
        self.assertTrue(callable(module.parse_rn_agenda_html))

    def test_fetch_wrapper_requests_only_the_agenda_once(self):
        fetch = mock.Mock(return_value=fetch_result(page(card()).encode("utf-8")))
        html = fetch_rn_agenda(fetch_callable=fetch)
        self.assertIn("<h1>Agenda</h1>", html)
        fetch.assert_called_once_with(RN_AGENDA_URL)

    def test_build_fetches_once_and_returns_event(self):
        fetch = mock.Mock(return_value=fetch_result(page(card()).encode("utf-8")))
        events = build_rn_agenda_events(
            observed_at=OBSERVED_AT,
            fetch_callable=fetch,
        )
        self.assertEqual(len(events), 1)
        fetch.assert_called_once_with(RN_AGENDA_URL)

    def test_fetch_failure_and_non_200_fail_closed(self):
        for result in (
            fetch_result(
                None,
                success=False,
                status_code=None,
                failure_category="network_error",
                failure_message="offline",
            ),
            fetch_result(
                None,
                success=False,
                status_code=503,
                failure_category="http_5xx",
                failure_message="HTTP 503",
            ),
        ):
            with self.subTest(status=result.status_code):
                with self.assertRaisesRegex(RnAgendaAdapterError, "fetch failed"):
                    fetch_rn_agenda(fetch_callable=lambda _url, value=result: value)

    def test_fetch_rejects_malformed_or_non_html_content(self):
        for body in (b"not html", b"\xff\xfe", b"<html>\x00</html>"):
            with self.subTest(body=body):
                with self.assertRaises(RnAgendaAdapterError):
                    fetch_rn_agenda(
                        fetch_callable=lambda _url, value=body: fetch_result(value)
                    )

    def test_invalid_observed_at_is_rejected(self):
        for value in (
            "2026-08-02",
            "2026-08-02T04:45:00+00:00",
            "2026-08-02T04:45:00.000Z",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RnAgendaAdapterError, "observed_at"):
                    self.parse(observed_at=value)

    def test_same_inputs_are_byte_equivalent_and_not_mutated(self):
        html = page(card())
        original = copy.deepcopy(html)
        first = self.parse(html)
        second = self.parse(html)
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, separators=(",", ":")),
            json.dumps(second, ensure_ascii=False, separators=(",", ":")),
        )
        self.assertEqual(html, original)

    def test_no_prohibited_analytical_or_invented_fields(self):
        event = self.parse()[0]
        self.assertTrue(PROHIBITED_FIELDS.isdisjoint(event))
        self.assertNotIn("source_published_at", event["evidence"][0])
        self.assertNotEqual(event.get("organization"), "LCI")

    def test_public_api_is_present(self):
        import rn_agenda_adapter

        for name in (
            "RnAgendaAdapterError",
            "parse_rn_agenda_html",
            "fetch_rn_agenda",
            "build_rn_agenda_events",
        ):
            self.assertIn(name, rn_agenda_adapter.__all__)


if __name__ == "__main__":
    unittest.main()
