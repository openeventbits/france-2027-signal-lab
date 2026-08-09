import importlib
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

from campaign_event_attribution import attribute_structured_events
from campaign_event_sources import load_campaign_event_source_registry
from campaign_event_structured import StructuredEventRecord
from http_fetch import HttpFetchResult
from la_lettre_expansion_adapter import (
    LA_LETTRE_EXPANSION_URL,
    LaLettreExpansionAdapterError,
    build_la_lettre_expansion_events,
    fetch_la_lettre_expansion,
    parse_la_lettre_expansion_html,
)

ROOT = Path(__file__).resolve().parent
OBSERVED_AT = "2026-08-08T18:30:00Z"
CURRENT_ITEM = (
    "<li><strong>Vendredi 28&nbsp;ao&ucirc;t.</strong> "
    "Universit&eacute;s d&rsquo;&eacute;t&eacute; du Laboratoire de la "
    "R&eacute;publique, le think tank de Jean-Michel Blanquer, "
    "&agrave; Sens, sous le titre &quot;Faire Sens ensemble&quot;. "
    "Avec comme invit&eacute;s Fran&ccedil;ois Baroin, Xavier Bertrand. "
    "Et en cl&ocirc;ture, le samedi 29&nbsp;ao&ucirc;t, "
    "un d&eacute;bat entre &Eacute;douard Philippe et Fran&ccedil;ois "
    "Hollande, retransmis sur LCI.</li>"
)


def page(item=CURRENT_ITEM):
    return (
        "<!doctype html><html><body><ol>"
        "<li>Autre événement sans rapport.</li>"
        + item
        + "<li>Autre événement le 29 août.</li>"
        "</ol></body></html>"
    )


def fetch_result(body, *, success=True, status_code=200, failure_message=None):
    return HttpFetchResult(
        success=success,
        not_modified=False,
        status_code=status_code,
        response_body=body,
        final_url=LA_LETTRE_EXPANSION_URL,
        attempts=1,
        elapsed_ms=1,
        etag=None,
        last_modified=None,
        failure_category=None if success else "network_error",
        failure_message=failure_message,
        response_bytes=len(body) if isinstance(body, bytes) else 0,
        retry_after_used=False,
    )


def source():
    registry = load_campaign_event_source_registry(ROOT / "campaign_event_sources.json")
    return next(
        item
        for item in registry["sources"]
        if item["source_id"] == "la-lettre-expansion-agenda"
    )


class LaLettreExpansionAdapterTests(unittest.TestCase):
    def test_exact_fixed_url(self):
        self.assertEqual(
            LA_LETTRE_EXPANSION_URL,
            "https://www.lalettredelexpansion.com/article/71583/agenda",
        )

    def test_bounded_item_yields_structured_html_date_record(self):
        records = parse_la_lettre_expansion_html(page())
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIsInstance(record, StructuredEventRecord)
        self.assertEqual(record.source_format, "structured_html")
        self.assertEqual(record.scheduled_start, "2026-08-29")
        self.assertEqual(record.time_precision, "date")
        self.assertEqual(record.timezone, "Europe/Paris")
        self.assertEqual(record.organization, "Laboratoire de la République")
        self.assertEqual(record.locality, "Sens")
        self.assertIn(
            "débat entre Édouard Philippe et François Hollande",
            record.description,
        )
        self.assertIn("retransmis sur LCI", record.description)

    def test_generic_multi_candidate_attribution_resolves_exact_pair(self):
        batch = attribute_structured_events(
            parse_la_lettre_expansion_html(page()), source=source()
        )
        self.assertEqual(batch.rejected_records, 0)
        self.assertEqual(len(batch.accepted), 1)
        attributed = batch.accepted[0]
        self.assertEqual(
            attributed.candidate_ids,
            ("francois-hollande", "edouard-philippe"),
        )
        self.assertEqual(
            attributed.candidate_names,
            ("François Hollande", "Édouard Philippe"),
        )
        self.assertEqual(attributed.attribution_basis, "explicit_participant")

    def test_build_fetches_once_and_builds_stage_2c_observation(self):
        fetch = mock.Mock(return_value=fetch_result(page().encode("utf-8")))
        result = build_la_lettre_expansion_events(
            source=source(), observed_at=OBSERVED_AT, fetch_callable=fetch
        )
        fetch.assert_called_once_with(LA_LETTRE_EXPANSION_URL)
        self.assertEqual(result.attribution_rejected_records, 0)
        self.assertEqual(len(result.observations), 1)
        observation = result.observations[0]
        self.assertEqual(observation["event_type"], "debate")
        self.assertEqual(observation["scheduled_start"], "2026-08-29")
        self.assertEqual(observation["time_precision"], "date")
        self.assertEqual(observation["last_verified_at"], OBSERVED_AT)
        self.assertEqual(
            observation["evidence"][0]["source_id"],
            "la-lettre-expansion-agenda",
        )
        self.assertEqual(
            observation["evidence"][0]["source_url"],
            LA_LETTRE_EXPANSION_URL,
        )

    def test_unrelated_list_items_are_ignored(self):
        html = page().replace(
            "<li>Autre événement sans rapport.</li>",
            "<li>François Hollande le 1 janvier 2030.</li>",
        )
        record = parse_la_lettre_expansion_html(html)[0]
        self.assertEqual(record.scheduled_start, "2026-08-29")
        self.assertNotIn("2030", record.description)

    def test_missing_candidate_date_lci_or_context_fails_closed(self):
        changes = (
            CURRENT_ITEM.replace(
                "&Eacute;douard Philippe et Fran&ccedil;ois Hollande",
                "&Eacute;douard Philippe",
            ),
            CURRENT_ITEM.replace("le samedi 29&nbsp;ao&ucirc;t", "à une date ultérieure"),
            CURRENT_ITEM.replace(", retransmis sur LCI", ""),
            CURRENT_ITEM.replace("Laboratoire de la R&eacute;publique", "un collectif"),
            CURRENT_ITEM.replace("&agrave; Sens", "en France"),
        )
        for item in changes:
            with self.subTest(item=item):
                with self.assertRaisesRegex(
                    LaLettreExpansionAdapterError, "Hollande-Philippe"
                ):
                    parse_la_lettre_expansion_html(page(item))

    def test_fetch_wrapper_requests_only_fixed_agenda_once(self):
        fetch = mock.Mock(return_value=fetch_result(page().encode("utf-8")))
        self.assertIn("Laboratoire", fetch_la_lettre_expansion(fetch_callable=fetch))
        fetch.assert_called_once_with(LA_LETTRE_EXPANSION_URL)

    def test_fetch_failure_fails_closed(self):
        fetch = mock.Mock(
            return_value=fetch_result(None, success=False, status_code=503, failure_message="offline")
        )
        with self.assertRaises(LaLettreExpansionAdapterError):
            fetch_la_lettre_expansion(fetch_callable=fetch)

    def test_parser_and_import_are_network_free(self):
        with mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("network forbidden")
        ):
            self.assertEqual(len(parse_la_lettre_expansion_html(page())), 1)
        original = sys.modules.get("la_lettre_expansion_adapter")
        try:
            sys.modules.pop("la_lettre_expansion_adapter", None)
            with mock.patch.object(
                socket, "create_connection", side_effect=AssertionError("network forbidden")
            ):
                module = importlib.import_module("la_lettre_expansion_adapter")
        finally:
            if original is not None:
                sys.modules["la_lettre_expansion_adapter"] = original
        self.assertTrue(callable(module.parse_la_lettre_expansion_html))


if __name__ == "__main__":
    unittest.main()
