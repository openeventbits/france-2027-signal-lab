import copy
import importlib
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

from campaign_event_attribution import CandidateAttributionConfigurationError
from campaign_event_sources import load_campaign_event_source_registry
from campaign_event_structured import StructuredEventRecord
from candidate_candidacy_status import (
    active_candidate_ids,
    candidacy_status_by_id,
    load_candidate_candidacy_status,
)
from http_fetch import HttpFetchResult
from tf1_lci_adapter import (
    TF1_LCI_URL,
    Tf1LciAdapterError,
    attribute_tf1_lci_events,
    build_tf1_lci_events,
    fetch_tf1_lci,
    parse_tf1_lci_html,
)

ROOT = Path(__file__).resolve().parent
OBSERVED_AT = "2026-08-08T17:00:00Z"
ARTICLE_BODY = (
    "En route pour l’Élysée ! Le jeudi 27 août à 16h45, LCI diffusera "
    "en direct et en exclusivité le premier débat de la campagne "
    "présidentielle de 2027, organisé par le Medef dans le cadre de "
    "La Rencontre des entrepreneurs de France (REF) 2026, sur le court "
    "Philippe-Chatrier de Roland-Garros. "
    "Ce grand rendez-vous réunira Jean-Luc Mélenchon, fondateur de La "
    "France insoumise, Bruno Retailleau, président des Républicains, "
    "Gabriel Attal, secrétaire général du parti Renaissance, Marine Le Pen, "
    "présidente du groupe Rassemblement national à l’Assemblée nationale, "
    "Raphaël Glucksmann, coprésident de Place publique, Marine Tondelier, "
    "secrétaire nationale des Écologistes et Édouard Philippe, président "
    "du parti Horizons. "
    "Un débat Hollande-Philippe le 29 août. La rentrée politique se "
    "poursuivra sur LCI le 29 août avec la diffusion de deux temps forts "
    "de l'université d'été du Laboratoire de la République, à Sens. "
    "À 14h00, Darius Rochebin interrogera le Premier ministre Sébastien "
    "Lecornu et l'ancien ministre de l'Éducation nationale Jean-Michel "
    "Blanquer sur les enjeux de souveraineté. Puis à 16h45, il présentera "
    "un débat entre l’ancien président de la République François Hollande "
    "et l’ancien Premier ministre Édouard Philippe."
)


def page(*, article_body=ARTICLE_BODY, date_published="2026-08-08T08:00:00+02:00"):
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "datePublished": date_published,
        "articleBody": article_body,
    }
    return (
        "<!doctype html><html><head>"
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></head><body><p>Unrelated visible page text.</p></body></html>"
    )


def fetch_result(body, *, success=True, status_code=200, failure_message=None):
    return HttpFetchResult(
        success=success,
        not_modified=False,
        status_code=status_code,
        response_body=body,
        final_url=TF1_LCI_URL,
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
    return next(item for item in registry["sources"] if item["source_id"] == "tf1-lci-debates")


def candidate_registry_views():
    registry = load_candidate_candidacy_status(
        ROOT / "candidate_candidacy_status.json"
    )
    return (
        copy.deepcopy(candidacy_status_by_id(registry)),
        list(active_candidate_ids(registry)),
    )


class Tf1LciAdapterTests(unittest.TestCase):
    def test_exact_fixed_url(self):
        self.assertEqual(
            TF1_LCI_URL,
            "https://www.tf1info.fr/politique/election-presidentielle-2027-lci-organisera-le-27-aout-un-grand-debat-avec-sept-candidats-declares-ou-pressentis-2455591.html",
        )

    def test_news_article_body_yields_two_structured_records(self):
        records = parse_tf1_lci_html(page())
        self.assertEqual(len(records), 2)
        self.assertTrue(all(isinstance(item, StructuredEventRecord) for item in records))
        self.assertEqual(
            [(item.scheduled_start, item.time_precision, item.source_format) for item in records],
            [
                ("2026-08-27T16:45:00+02:00", "datetime", "json_ld"),
                ("2026-08-29T16:45:00+02:00", "datetime", "json_ld"),
            ],
        )
        self.assertEqual(records[0].organization, "MEDEF")
        self.assertEqual(records[0].location_name, "Court Philippe-Chatrier, Roland-Garros")
        self.assertEqual(records[1].organization, "Laboratoire de la République")
        self.assertEqual(records[1].locality, "Sens")

    def test_bounded_custom_attribution_uses_canonical_active_identities(self):
        batch = attribute_tf1_lci_events(parse_tf1_lci_html(page()))
        self.assertEqual(batch.rejected_records, 0)
        self.assertEqual(len(batch.accepted), 2)
        self.assertTrue(
            all(item.attribution_basis == "explicit_participant" for item in batch.accepted)
        )
        self.assertEqual(
            set(batch.accepted[0].candidate_ids),
            {
                "bruno-retailleau",
                "edouard-philippe",
                "gabriel-attal",
                "jean-luc-melenchon",
                "marine-le-pen",
                "marine-tondelier",
                "raphael-glucksmann",
            },
        )
        self.assertEqual(
            set(batch.accepted[1].candidate_ids),
            {"edouard-philippe", "francois-hollande"},
        )
        for item in batch.accepted:
            self.assertEqual(
                list(zip(item.candidate_ids, item.candidate_names)),
                sorted(
                    zip(item.candidate_ids, item.candidate_names),
                    key=lambda pair: (pair[1].casefold(), pair[0]),
                ),
            )

    def attribute_with_registry_views(self, by_id, active_ids):
        with mock.patch(
            "tf1_lci_adapter.candidacy_status_by_id",
            return_value=by_id,
        ), mock.patch(
            "tf1_lci_adapter.active_candidate_ids",
            return_value=active_ids,
        ):
            return attribute_tf1_lci_events(parse_tf1_lci_html(page()))

    def test_inactive_seven_person_participant_is_filtered_normally(self):
        by_id, active_ids = candidate_registry_views()
        inactive_id = "marine-tondelier"
        active_ids.remove(inactive_id)

        batch = self.attribute_with_registry_views(by_id, active_ids)

        self.assertEqual(batch.rejected_records, 0)
        self.assertEqual(len(batch.accepted), 2)
        self.assertEqual(
            batch.accepted[0].candidate_ids,
            (
                "bruno-retailleau",
                "gabriel-attal",
                "jean-luc-melenchon",
                "marine-le-pen",
                "raphael-glucksmann",
                "edouard-philippe",
            ),
        )
        self.assertNotIn(inactive_id, batch.accepted[0].candidate_ids)
        self.assertEqual(
            list(zip(
                batch.accepted[0].candidate_ids,
                batch.accepted[0].candidate_names,
            )),
            sorted(
                zip(
                    batch.accepted[0].candidate_ids,
                    batch.accepted[0].candidate_names,
                ),
                key=lambda pair: (pair[1].casefold(), pair[0]),
            ),
        )

    def test_inactive_hollande_is_an_ordinary_record_rejection(self):
        by_id, active_ids = candidate_registry_views()
        active_ids.remove("francois-hollande")

        batch = self.attribute_with_registry_views(by_id, active_ids)

        self.assertEqual(len(batch.accepted), 1)
        self.assertEqual(
            batch.accepted[0].structured_event.scheduled_start,
            "2026-08-27T16:45:00+02:00",
        )
        self.assertEqual(batch.rejected_records, 1)

    def test_missing_audited_canonical_id_remains_fatal(self):
        by_id, active_ids = candidate_registry_views()
        by_id.pop("marine-tondelier")

        with self.assertRaisesRegex(
            CandidateAttributionConfigurationError,
            "marine-tondelier",
        ):
            self.attribute_with_registry_views(by_id, active_ids)

    def test_audited_canonical_name_mismatch_remains_fatal(self):
        by_id, active_ids = candidate_registry_views()
        by_id["marine-tondelier"]["candidate_name"] = "Wrong Canonical Name"

        with self.assertRaisesRegex(
            CandidateAttributionConfigurationError,
            "marine-tondelier",
        ):
            self.attribute_with_registry_views(by_id, active_ids)
    def test_build_fetches_once_and_builds_stage_2c_observations(self):
        fetch = mock.Mock(return_value=fetch_result(page().encode("utf-8")))
        result = build_tf1_lci_events(
            source=source(), observed_at=OBSERVED_AT, fetch_callable=fetch
        )
        fetch.assert_called_once_with(TF1_LCI_URL)
        self.assertEqual(len(result.observations), 2)
        self.assertEqual(result.attribution_rejected_records, 0)
        for observation in result.observations:
            self.assertEqual(observation["event_type"], "debate")
            self.assertEqual(observation["last_verified_at"], OBSERVED_AT)
            self.assertEqual(observation["evidence"][0]["source_id"], "tf1-lci-debates")
            self.assertEqual(observation["evidence"][0]["source_url"], TF1_LCI_URL)
            self.assertTrue(observation["event_key"].startswith("tf1-lci-debates-debate-"))

    def test_parser_uses_news_article_body_not_unrelated_dom_text(self):
        html = page().replace(
            "<p>Unrelated visible page text.</p>",
            "<p>Marine Le Pen 1 janvier 2030 00h00 faux débat.</p>",
        )
        records = parse_tf1_lci_html(html)
        self.assertEqual(len(records), 2)
        self.assertNotIn("2030", repr(records))

    def test_missing_article_body_fails_closed(self):
        payload = {"@type": "NewsArticle", "datePublished": "2026-08-08"}
        html = (
            "<!doctype html><html><head><script type=\"application/ld+json\">"
            + json.dumps(payload)
            + "</script></head></html>"
        )
        with self.assertRaisesRegex(Tf1LciAdapterError, "articleBody"):
            parse_tf1_lci_html(html)

    def test_missing_audited_candidate_or_schedule_fails_closed(self):
        changed = ARTICLE_BODY.replace(
            "Marine Tondelier, secrétaire nationale des Écologistes et ", ""
        )
        with self.assertRaisesRegex(Tf1LciAdapterError, "seven-candidate"):
            parse_tf1_lci_html(page(article_body=changed))
        changed = ARTICLE_BODY.replace("Puis à 16h45, il présentera", "Puis il présentera")
        with self.assertRaisesRegex(Tf1LciAdapterError, "Hollande-Philippe"):
            parse_tf1_lci_html(page(article_body=changed))

    def test_custom_attribution_rejects_unexpected_record_shape(self):
        records = list(parse_tf1_lci_html(page()))
        records[0] = StructuredEventRecord(
            title=records[0].title,
            scheduled_start="2026-08-27T17:45:00+02:00",
            time_precision="datetime",
            timezone="Europe/Paris",
            source_format="json_ld",
            organization="MEDEF",
        )
        with self.assertRaisesRegex(Tf1LciAdapterError, "unexpected event facts"):
            attribute_tf1_lci_events(records)

    def test_fetch_wrapper_requests_only_fixed_article_once(self):
        fetch = mock.Mock(return_value=fetch_result(page().encode("utf-8")))
        self.assertIn("articleBody", fetch_tf1_lci(fetch_callable=fetch))
        fetch.assert_called_once_with(TF1_LCI_URL)

    def test_fetch_failure_fails_closed(self):
        fetch = mock.Mock(
            return_value=fetch_result(None, success=False, status_code=503, failure_message="offline")
        )
        with self.assertRaises(Tf1LciAdapterError):
            fetch_tf1_lci(fetch_callable=fetch)

    def test_parser_and_import_are_network_free(self):
        with mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("network forbidden")
        ):
            self.assertEqual(len(parse_tf1_lci_html(page())), 2)
        original = sys.modules.get("tf1_lci_adapter")
        try:
            sys.modules.pop("tf1_lci_adapter", None)
            with mock.patch.object(
                socket, "create_connection", side_effect=AssertionError("network forbidden")
            ):
                module = importlib.import_module("tf1_lci_adapter")
        finally:
            if original is not None:
                sys.modules["tf1_lci_adapter"] = original
        self.assertTrue(callable(module.parse_tf1_lci_html))


if __name__ == "__main__":
    unittest.main()

