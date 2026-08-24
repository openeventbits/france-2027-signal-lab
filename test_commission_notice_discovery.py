import copy
import json
import tempfile
import unittest
from pathlib import Path

from commission_notice_discovery import (
    CommissionNoticeError,
    FetchResult,
    atomic_write_registry,
    classify_listing,
    confirm_document_eligibility,
    discover_registry,
    empty_registry,
    extract_official_fieldwork_dates,
    load_registry,
    notice_identity,
    parse_notice_index,
    validate_registry,
)


INDEX_URL = "https://www.commission-des-sondages.fr/notices/"


def index_html(*rows):
    links = "".join(
        (
            '<p class="download-line">'
            f'<a class="pdf_download" href="{href}">{title}</a>'
            "</p>"
        )
        for href, title in rows
    )
    return (
        "<html><body><dl class='accordion'><dd>"
        "<h2 class='notices-mois-titre'>Juillet 2026</h2>"
        f"<div class='notices-elements'>{links}</div>"
        "</dd></dl></body></html>"
    )


class IndexParsingTests(unittest.TestCase):
    def test_document_order_relative_urls_and_listing_metadata(self):
        records = parse_notice_index(
            index_html(
                (
                    "/notices/medias/fichiers/add/2228",
                    "10223 Pres IV TOLUNA HARRIS INTERACTIVE RTL 8 juillet",
                ),
                (
                    "/notices/medias/fichiers/add/2241",
                    "10233 Pres Barometre stature vague 4 VERIAN "
                    "Le Figaro Magazine 23 juillet",
                ),
            )
        )

        self.assertEqual(
            [record["notice_id"] for record in records],
            ["commission:10223", "commission:10233"],
        )
        self.assertEqual(records[0]["listed_date"], "2026-07-08")
        self.assertEqual(records[0]["category"], "Pres")
        self.assertEqual(records[0]["institute"], "Harris Interactive")
        self.assertEqual(records[0]["commissioner"], "RTL")
        self.assertEqual(
            records[0]["listed_url"],
            INDEX_URL + "medias/fichiers/add/2228",
        )

    def test_duplicate_identical_listing_rows_deduplicate(self):
        row = (
            "/notices/medias/fichiers/add/2228",
            "10223 Pres IV TOLUNA HARRIS INTERACTIVE RTL 8 juillet",
        )
        records = parse_notice_index(index_html(row, row))
        self.assertEqual(len(records), 1)

    def test_conflicting_duplicate_notice_ids_fail(self):
        with self.assertRaisesRegex(
            CommissionNoticeError,
            "conflicting duplicate",
        ):
            parse_notice_index(
                index_html(
                    (
                        "/notices/medias/fichiers/add/2228",
                        "10223 Pres IV TOLUNA HARRIS INTERACTIVE RTL 8 juillet",
                    ),
                    (
                        "/notices/medias/fichiers/add/9999",
                        "10223 Pres different notice IFOP 9 juillet",
                    ),
                )
            )

    def test_lettered_visible_notice_designations_remain_distinct(self):
        records = parse_notice_index(
            index_html(
                (
                    "/notices/medias/fichiers/add/1",
                    "10153 a Mun Comprendre le vote IPSOS BVA 15 juillet",
                ),
                (
                    "/notices/medias/fichiers/add/2",
                    "10153 b Mun Sociologie IPSOS BVA 15 juillet",
                ),
            )
        )
        self.assertEqual(
            [record["notice_id"] for record in records],
            ["commission:10153a", "commission:10153b"],
        )

    def test_identity_uses_only_recognized_sources(self):
        self.assertEqual(
            notice_identity(
                "No visible identifier with year 2027 in its title",
                INDEX_URL + "medias/fichiers/add/2228",
            ),
            "commission-media:2228",
        )

    def test_off_origin_and_empty_indexes_fail(self):
        with self.assertRaisesRegex(CommissionNoticeError, "official origin"):
            parse_notice_index(
                index_html(
                    (
                        "https://example.test/notice",
                        "10223 Pres IV IFOP 8 juillet",
                    ),
                )
            )
        with self.assertRaisesRegex(CommissionNoticeError, "no recognizable"):
            parse_notice_index("<html><body><p>No notices</p></body></html>")


class EligibilityTests(unittest.TestCase):
    def record(self, title, category="Pres"):
        return {"title": title, "category": category}

    def test_listing_level_positive_negative_and_ambiguous_gates(self):
        positive = classify_listing(
            self.record("10223 Pres Intention de vote PR2027 IFOP")
        )
        negative = classify_listing(
            self.record("10233 Pres Baromètre stature VERIAN")
        )
        ambiguous = classify_listing(self.record("10226 Pres ELABE"))
        municipal = classify_listing(
            self.record("10250 Mun intention de vote Paris", "Mun")
        )

        self.assertTrue(positive.inspect_document)
        self.assertTrue(positive.strongly_eligible)
        self.assertEqual(negative.classification, "excluded_non_voting")
        self.assertFalse(negative.inspect_document)
        self.assertEqual(ambiguous.classification, "ambiguous")
        self.assertTrue(ambiguous.inspect_document)
        self.assertEqual(municipal.classification, "excluded_non_voting")

    def test_document_confirmation_preserves_first_and_second_rounds(self):
        eligible, rounds, reason = confirm_document_eligibility(
            """
            Intentions de vote à l'élection présidentielle de 2027.
            Si le 1er tour avait lieu dimanche, pour qui voteriez-vous ?
            Si le second tour avait lieu dimanche, pour qui voteriez-vous ?
            """
        )
        self.assertTrue(eligible)
        self.assertEqual(rounds, ["first_round", "second_round"])
        self.assertIn("confirms", reason)

    def test_candidate_names_alone_do_not_confirm_eligibility(self):
        eligible, rounds, _ = confirm_document_eligibility(
            "Image et popularité de Jordan Bardella et Édouard Philippe"
        )
        self.assertFalse(eligible)
        self.assertEqual(rounds, [])


class FieldworkExtractionTests(unittest.TestCase):
    def assert_fieldwork(self, text, start, end):
        self.assertEqual(
            extract_official_fieldwork_dates(text),
            {"fieldwork_start": start, "fieldwork_end": end},
        )

    def test_normal_date_range(self):
        self.assert_fieldwork(
            "Enquête réalisée du 9 au 10 juillet 2026 en ligne.",
            "2026-07-09",
            "2026-07-10",
        )

    def test_standalone_methodology_label_ignores_publication_date(self):
        self.assert_fieldwork(
            "Méthodologie. Réalisée du 8 au 10 juillet 2026. "
            "Enquête réalisée pour L'Hémicycle et publiée le 10 juillet 2026.",
            "2026-07-08",
            "2026-07-10",
        )

    def test_accented_french_month(self):
        self.assert_fieldwork(
            "Dates de réalisation : du 18 au 19 août 2026.",
            "2026-08-18",
            "2026-08-19",
        )

    def test_first_day_ordinal(self):
        self.assert_fieldwork(
            "Les interviews ont été réalisées du 1er au 6 février 2026.",
            "2026-02-01",
            "2026-02-06",
        )

    def test_single_day_survey(self):
        self.assert_fieldwork(
            "Enquête réalisée le 22 mars 2026.",
            "2026-03-22",
            "2026-03-22",
        )

    def test_harris_parenthetical_interruption(self):
        self.assert_fieldwork(
            "Enquête réalisée du 7 (après l'annonce des résultats) "
            "au 8 juillet 2026.",
            "2026-07-07",
            "2026-07-08",
        )

    def test_current_terrain_wins_over_unanchored_previous_wave(self):
        self.assert_fieldwork(
            "Rappel : l'enquête précédente couvrait du 2 au 3 juin 2026. "
            "Dates de réalisation du terrain : du 8 au 10 juillet 2026.",
            "2026-07-08",
            "2026-07-10",
        )

    def test_conflicting_contextual_ranges_fail_closed(self):
        self.assertIsNone(
            extract_official_fieldwork_dates(
                "Dates de réalisation : vague A du 8 au 9 juillet 2026, "
                "vague B du 9 au 10 juillet 2026."
            )
        )


class RegistryDiscoveryTests(unittest.TestCase):
    def test_pre_pass_b_registry_validates_without_mutating_legacy_coverage(
        self,
    ):
        payload = load_registry("commission_notice_registry.json")
        relevant = [
            notice
            for notice in payload["notices"]
            if notice["classification"] in {"eligible", "unsupported"}
        ]
        for notice in relevant:
            notice.pop("coverage", None)

        validate_registry(payload)

        self.assertTrue(relevant)
        self.assertTrue(all("coverage" not in notice for notice in relevant))

    def test_malformed_present_coverage_still_fails_registry_validation(self):
        payload = load_registry("commission_notice_registry.json")
        relevant = next(
            notice
            for notice in payload["notices"]
            if notice["classification"] in {"eligible", "unsupported"}
        )
        relevant["coverage"] = {"state": "unresolved"}

        with self.assertRaisesRegex(
            CommissionNoticeError,
            "coverage has an unexpected contract",
        ):
            validate_registry(payload)

    def test_irrelevant_notice_cannot_carry_coverage(self):
        payload = load_registry("commission_notice_registry.json")
        irrelevant = next(
            notice
            for notice in payload["notices"]
            if notice["classification"] not in {"eligible", "unsupported"}
        )
        irrelevant["coverage"] = {
            "state": "unresolved",
            "matched_event_ids": [],
            "method": "not_yet_reconciled",
        }

        with self.assertRaisesRegex(
            CommissionNoticeError,
            "is not relevant and must not have coverage state",
        ):
            validate_registry(payload)

    def setUp(self):
        self.eligible_url = INDEX_URL + "medias/fichiers/add/2228"
        self.excluded_url = INDEX_URL + "medias/fichiers/add/2241"
        self.index = index_html(
            (
                "/notices/medias/fichiers/add/2228",
                "10223 Pres IV TOLUNA HARRIS INTERACTIVE RTL 8 juillet",
            ),
            (
                "/notices/medias/fichiers/add/2241",
                "10233 Pres Barometre stature VERIAN Le Figaro 23 juillet",
            ),
        ).encode()

    def fetch(self, url, method):
        if url == INDEX_URL:
            return FetchResult(self.index, INDEX_URL, "text/html")
        if url == self.eligible_url:
            body = (
                "<html><body>Intentions de vote à l'élection "
                "présidentielle de 2027. Si le 1er tour avait lieu "
                "dimanche, pour qui voteriez-vous ? Enquête réalisée "
                "du 7 au 8 juillet 2026.</body></html>"
            ).encode()
            return FetchResult(
                body,
                "http://www.commission-des-sondages.fr/notices/files/"
                "notices/2026/juillet/10223-pres-iv.pdf",
                "text/html",
            )
        if url == self.excluded_url and method == "HEAD":
            raise OSError("popularity notice is temporarily unavailable")
        raise AssertionError((url, method))

    def test_merge_retains_old_records_and_stable_discovery_timestamp(self):
        old = {
            "notice_id": "commission:10000",
            "listed_date": "2025-12-01",
            "category": "Pres",
            "title": "10000 Pres old retained notice",
            "institute": None,
            "commissioner": None,
            "listed_url": INDEX_URL + "medias/fichiers/add/100",
            "resolved_url": INDEX_URL + "medias/fichiers/add/100",
            "classification": "excluded_non_voting",
            "classification_reason": "previously classified",
            "first_discovered_at": "2026-01-01T00:00:00Z",
            "content_sha256": None,
            "confirmed_rounds": [],
        }
        existing = empty_registry()
        existing["notices"] = [old]

        result = discover_registry(
            existing,
            fetch=self.fetch,
            discovered_at="2026-07-24T12:00:00Z",
        )
        by_id = {
            notice["notice_id"]: notice
            for notice in result.registry["notices"]
        }

        self.assertEqual(
            by_id["commission:10223"]["classification"],
            "eligible",
        )
        self.assertEqual(
            by_id["commission:10223"]["confirmed_rounds"],
            ["first_round"],
        )
        self.assertEqual(
            by_id["commission:10223"]["survey_metadata"],
            {
                "fieldwork_start": "2026-07-07",
                "fieldwork_end": "2026-07-08",
            },
        )
        self.assertEqual(
            by_id["commission:10223"]["first_discovered_at"],
            "2026-07-24T12:00:00Z",
        )
        self.assertEqual(
            by_id["commission:10000"]["first_discovered_at"],
            "2026-01-01T00:00:00Z",
        )
        self.assertEqual(
            by_id["commission:10233"]["classification"],
            "excluded_non_voting",
        )
        self.assertTrue(result.diagnostics)

    def test_ambiguous_fetch_failure_fails_discovery(self):
        ambiguous_index = index_html(
            (
                "/notices/medias/fichiers/add/2231",
                "10226 Pres ELABE 11 juillet",
            )
        ).encode()

        def failing_fetch(url, method):
            if url == INDEX_URL:
                return FetchResult(ambiguous_index, INDEX_URL, "text/html")
            raise OSError("document unavailable")

        with self.assertRaisesRegex(
            CommissionNoticeError,
            "ambiguous notice could not be inspected",
        ):
            discover_registry(empty_registry(), fetch=failing_fetch)

    def test_successful_inspection_removes_stale_conflicting_metadata(self):
        existing = discover_registry(empty_registry(), fetch=self.fetch).registry
        previous = next(
            notice
            for notice in existing["notices"]
            if notice["notice_id"] == "commission:10223"
        )
        self.assertIn("survey_metadata", previous)

        def conflicting_fetch(url, method):
            if url == INDEX_URL:
                return FetchResult(self.index, INDEX_URL, "text/html")
            if url == self.eligible_url:
                body = (
                    "<html><body>Intentions de vote à l'élection "
                    "présidentielle de 2027. Si le 1er tour avait lieu "
                    "dimanche, pour qui voteriez-vous ? "
                    "Dates de réalisation : vague A du 8 au 9 juillet 2026, "
                    "vague B du 9 au 10 juillet 2026.</body></html>"
                ).encode()
                return FetchResult(
                    body,
                    "http://www.commission-des-sondages.fr/notices/files/"
                    "notices/2026/juillet/10223-pres-iv.pdf",
                    "text/html",
                )
            raise AssertionError((url, method))

        refreshed = discover_registry(existing, fetch=conflicting_fetch)
        notice = next(
            notice
            for notice in refreshed.registry["notices"]
            if notice["notice_id"] == "commission:10223"
        )
        self.assertNotIn("survey_metadata", notice)

    def test_existing_eligible_fetch_failure_fails_discovery(self):
        existing = load_registry("commission_notice_registry.json")
        ifop = next(
            notice
            for notice in existing["notices"]
            if notice["notice_id"] == "commission:10211"
        )
        single_index = index_html(
            (ifop["listed_url"], ifop["title"])
        ).encode()

        def failing_fetch(url, method):
            if url == INDEX_URL:
                return FetchResult(single_index, INDEX_URL, "text/html")
            raise OSError("document unavailable")

        with self.assertRaisesRegex(
            CommissionNoticeError,
            "existing eligible notice could not be fetched",
        ):
            discover_registry(existing, fetch=failing_fetch)

    def test_atomic_write_is_idempotent_and_schema_validated(self):
        payload = load_registry("commission_notice_registry.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            self.assertTrue(atomic_write_registry(path, payload))
            first = path.read_bytes()
            self.assertFalse(atomic_write_registry(path, copy.deepcopy(payload)))
            self.assertEqual(path.read_bytes(), first)

        invalid = json.loads(json.dumps(payload))
        invalid["notices"][0]["classification"] = "maybe"
        with self.assertRaisesRegex(CommissionNoticeError, "classification"):
            validate_registry(invalid)


if __name__ == "__main__":
    unittest.main()
