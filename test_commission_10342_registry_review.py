"""10342 extends only the authenticated registry delta, never polling coverage."""

import copy
import gzip
import hashlib
import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

import commission_notice_coverage as coverage
import commission_notice_discovery as discovery
import test_commission_reconciliation_review as reconciliation
from test_commission_notice_coverage import _authenticate_historical_polling_corpus
from test_commission_notice_discovery import index_html


ROOT = Path(__file__).parent
NOTICE_ID = "commission:10342"
PDF_SHA256 = "08dd618195a23f1523099488a224440efd87c7f6dc96176e32a32c21f888bc3d"
RECORD_SHA256 = "6e636e49c9ecf15cfcd010d055b6adb876581aeb2580d37e71c40d5a407ac1a8"


class Commission10342RegistryReviewTests(unittest.TestCase):
    def setUp(self):
        self.review = reconciliation._load_10342_registry_review()
        self.record = self.review["original_record"]
        self.pdf = ROOT / self.review["source_document"]["fixture"]
        # Every negative test starts from an independently authenticated success.
        self.registry = reconciliation._archival_registry_with_10342()
        historical, self.summary = reconciliation._authenticate_registry_baseline(self.registry)
        self.assertEqual((len(self.registry["notices"]), len(historical["notices"])), (177, 173))

    def test_archival_176_plus_exact_original_record_passes_without_mutation(self):
        fixture = self.review["archival_registry"]
        raw = gzip.decompress((ROOT / fixture["fixture"]).read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["uncompressed_sha256"])
        archive = json.loads(raw)
        self.assertEqual(len(archive["notices"]), 176)
        self.assertNotIn(NOTICE_ID, {n["notice_id"] for n in archive["notices"]})
        before = copy.deepcopy(self.registry)
        historical, summary = reconciliation._authenticate_registry_baseline(self.registry)
        self.assertEqual(coverage._canonical_sha256(historical),
                         "a2963a840d0d60adfd232c5af6d63dab970d5ffa2b90c35bf2f61175995243d9")
        self.assertEqual(coverage.coverage_summary(archive), summary)
        self.assertEqual(coverage.coverage_summary(self.registry), summary)
        self.assertEqual(self.registry, before)

    def test_original_historical_digest_and_three_earlier_pins_are_unchanged(self):
        self.assertEqual(reconciliation._HISTORICAL_REGISTRY_SHA256,
                         "a2963a840d0d60adfd232c5af6d63dab970d5ffa2b90c35bf2f61175995243d9")
        self.assertEqual(reconciliation._REVIEWED_REGISTRY_ADDITIONS, {
            "commission:10306": "ff4b757c3b67165a92a1d9068c754af5e84f9d080bb22017b997c645320670cc",
            "commission:10339": "e93b81651a458882500cf932191deabf96cd13ac9ee4eb09f1a228f6eced2d57",
            "commission:10340": "e6e1e78e047d569b15de8d834e499d77e38df5160f90086be5decd0bbad5954d",
        })
        for notice_id, expected in reconciliation._REVIEWED_REGISTRY_ADDITIONS.items():
            record = next(n for n in self.registry["notices"] if n["notice_id"] == notice_id)
            self.assertEqual(coverage._canonical_sha256(record), expected)

    def test_original_pdf_bytes_and_all_seven_pages_support_exclusion(self):
        self.assertEqual(hashlib.sha256(self.pdf.read_bytes()).hexdigest(), PDF_SHA256)
        self.assertEqual(self.pdf.stat().st_size, 259627)
        pages = [page.extract_text() for page in PdfReader(self.pdf).pages]
        self.assertEqual(len(pages), 7)
        self.assertEqual([p["page"] for p in self.review["classification_review"]["pages"]], list(range(1, 8)))
        text = "\n".join(pages)
        self.assertEqual(discovery.confirm_document_eligibility(text), (
            False, ["first_round", "second_round"],
            "document lacks 2027 presidential context and voting-intention language"))
        self.assertEqual(discovery.extract_official_fieldwork_dates(text), {
            "fieldwork_start": "2026-10-27", "fieldwork_end": "2026-10-28"})
        for page, marker in zip(pages, ("BFMTV", "Q1.", "Q4.", "95", "2022", "89", "32")):
            self.assertIn(marker, page)

    def test_round_metadata_is_preserved_as_recalled_weighting_not_2027_ballots(self):
        pages = [page.extract_text() for page in PdfReader(self.pdf).pages]
        weighting = discovery.normalize_text(pages[4])
        self.assertIn("presidentielle 2022", weighting)
        self.assertIn("legislatives 2024", weighting)
        self.assertEqual(discovery.confirm_document_eligibility(pages[4])[1], ["first_round", "second_round"])
        for i, page in enumerate(pages):
            if i != 4:
                self.assertEqual(discovery.confirm_document_eligibility(page)[1], [])
        self.assertEqual(self.record["confirmed_rounds"], ["first_round", "second_round"])
        self.assertEqual(self.review["metadata_limitations"]["confirmed_rounds"]["measured_2027_rounds"], [])
        self.assertIsNone(self.record["commissioner"])
        self.assertEqual(coverage._canonical_sha256(self.record), RECORD_SHA256)

    def test_fuel_question_and_conflicting_published_label_are_both_retained(self):
        pages = [page.extract_text() for page in PdfReader(self.pdf).pages]
        conflict = self.review["metadata_limitations"]["fuel_price_wording"]
        self.assertIn(discovery.normalize_text(conflict["questionnaire_literal"]), discovery.normalize_text(pages[1]))
        self.assertIn(discovery.normalize_text(conflict["published_table_literal"]), discovery.normalize_text(pages[5]))
        self.assertEqual(conflict["published_percent"], 89)
        self.assertNotEqual(conflict["questionnaire_literal"], conflict["published_table_literal"])

    def test_changed_original_record_fields_are_each_rejected(self):
        changes = {
            "notice_id": "commission:99999", "listed_date": "2026-10-29", "category": "Autre",
            "title": self.record["title"] + " changed", "institute": "Ifop", "commissioner": "BFMTV",
            "listed_url": self.record["listed_url"] + "?changed",
            "resolved_url": self.record["resolved_url"].replace("http:", "https:"),
            "classification": "unsupported", "classification_reason": "unreviewed",
            "first_discovered_at": "2026-10-28T23:00:17.814469Z",
            "content_sha256": "0" * 64, "confirmed_rounds": [],
        }
        self.assertEqual(set(changes), set(self.record))
        for field, value in changes.items():
            registry = copy.deepcopy(self.registry)
            registry["notices"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Commission registry addition"):
                reconciliation._authenticate_registry_baseline(registry)

    def test_unexpected_record_fields_cannot_hide_coverage_or_parser_admission(self):
        for field, value in {
            "unexpected": None, "parser": "elabe",
            "coverage": coverage.unresolved_coverage("unreviewed"),
            "survey_metadata": {"fieldwork_start": "2026-10-27", "fieldwork_end": "2026-10-28"},
        }.items():
            registry = copy.deepcopy(self.registry)
            registry["notices"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "changed: commission:10342"):
                reconciliation._authenticate_registry_baseline(registry)

    def test_every_missing_original_record_field_is_rejected(self):
        for field in self.record:
            registry = copy.deepcopy(self.registry)
            del registry["notices"][0][field]
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                reconciliation._authenticate_registry_baseline(registry)

    def test_missing_historical_and_each_reviewed_addition_are_rejected(self):
        historical = next(n["notice_id"] for n in self.registry["notices"]
                          if n["notice_id"] not in {NOTICE_ID, *reconciliation._REVIEWED_REGISTRY_ADDITIONS})
        for notice_id in (historical, *reconciliation._REVIEWED_REGISTRY_ADDITIONS, NOTICE_ID):
            registry = copy.deepcopy(self.registry)
            registry["notices"] = [n for n in registry["notices"] if n["notice_id"] != notice_id]
            with self.subTest(notice_id=notice_id), self.assertRaises(ValueError):
                reconciliation._authenticate_registry_baseline(registry)

    def test_duplicate_historical_and_each_reviewed_addition_are_rejected(self):
        historical = next(n["notice_id"] for n in self.registry["notices"]
                          if n["notice_id"] not in {NOTICE_ID, *reconciliation._REVIEWED_REGISTRY_ADDITIONS})
        for notice_id in (historical, *reconciliation._REVIEWED_REGISTRY_ADDITIONS, NOTICE_ID):
            registry = copy.deepcopy(self.registry)
            registry["notices"].append(copy.deepcopy(next(n for n in registry["notices"] if n["notice_id"] == notice_id)))
            with self.subTest(notice_id=notice_id), self.assertRaisesRegex(ValueError, "Duplicate Commission"):
                reconciliation._authenticate_registry_baseline(registry)

    def test_unauthorized_excluded_and_relevant_additions_remain_rejected(self):
        for template_id in (NOTICE_ID, "commission:10339"):
            registry = copy.deepcopy(self.registry)
            extra = dict(next(n for n in registry["notices"] if n["notice_id"] == template_id), notice_id="commission:99999")
            registry["notices"].append(extra)
            with self.subTest(template=template_id), self.assertRaisesRegex(ValueError, "unexpectedly extended"):
                reconciliation._authenticate_registry_baseline(registry)

    def test_unreviewed_10343_is_rejected_independently_of_10339_drift(self):
        current = json.loads((ROOT / "commission_notice_registry.json").read_bytes())
        extra = copy.deepcopy(next(n for n in current["notices"] if n["notice_id"] == "commission:10343"))
        self.assertEqual(extra["classification"], "excluded_non_voting")
        self.registry["notices"].insert(0, extra)
        with self.assertRaisesRegex(ValueError, "Historical Commission records.*unexpectedly extended"):
            reconciliation._authenticate_registry_baseline(self.registry)

    def test_changed_current_10339_is_rejected_independently_of_10343(self):
        current = json.loads((ROOT / "commission_notice_registry.json").read_bytes())
        changed = next(n for n in current["notices"] if n["notice_id"] == "commission:10339")
        self.assertNotEqual(coverage._canonical_sha256(changed), reconciliation._REVIEWED_REGISTRY_ADDITIONS[changed["notice_id"]])
        self.registry["notices"] = [copy.deepcopy(changed) if n["notice_id"] == changed["notice_id"] else n
                                    for n in self.registry["notices"]]
        with self.assertRaisesRegex(ValueError, "Reviewed Commission registry addition changed: commission:10339"):
            reconciliation._authenticate_registry_baseline(self.registry)

    def test_current_production_registry_still_fails_its_10339_evidence_gate(self):
        current = json.loads((ROOT / "commission_notice_registry.json").read_bytes())
        before = copy.deepcopy(current)
        with self.assertRaisesRegex(ValueError, "Reviewed Commission registry addition changed: commission:10339"):
            reconciliation._authenticate_registry_baseline(current)
        self.assertEqual(current, before)

    def test_altered_review_sections_or_self_reported_hash_cannot_repin_evidence(self):
        changes = {
            "scope": "accept all excluded notices", "original_record": {**self.record, "confirmed_rounds": []},
            "record_canonical_sha256": "0" * 64,
            "source_document": {**self.review["source_document"], "sha256": "0" * 64},
            "introduction": {**self.review["introduction"], "commit": "0" * 40},
            "classification_review": {**self.review["classification_review"], "classification": "eligible"},
            "metadata_limitations": {}, "archival_registry": {}, "authorization_limits": [], "unexpected": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            for field, value in changes.items():
                changed = copy.deepcopy(self.review)
                changed[field] = value
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "explicit review required"):
                    reconciliation._load_10342_registry_review(path)

    def test_duplicate_review_json_keys_are_rejected_even_with_same_values(self):
        raw = reconciliation._10342_REVIEW.read_text(encoding="utf-8")
        raw = raw.replace('"review_id":', '"review_id": "FR27-COMMISSION-10342-HISTORICAL-REGISTRY-20261029", "review_id":', 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate 10342 evidence JSON key"):
                reconciliation._load_10342_registry_review(path)

    def test_missing_changed_truncated_or_transcribed_original_pdf_is_rejected(self):
        original = self.pdf.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / self.review["source_document"]["fixture"]
            target.parent.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                reconciliation._load_10342_registry_review(fixture_root=root)
            for label, raw in {"changed": original + b"\n", "truncated": original[:100],
                               "transcription": b"Les Francais et les revendications des mobilisations sociales"}.items():
                target.write_bytes(raw)
                with self.subTest(fixture=label), self.assertRaisesRegex(ValueError, "original PDF bytes changed"):
                    reconciliation._load_10342_registry_review(fixture_root=root)

    def test_changed_archival_fixture_is_rejected_before_becoming_a_positive_control(self):
        fixture = self.review["archival_registry"]
        raw = gzip.decompress((ROOT / fixture["fixture"]).read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / fixture["fixture"]
            target.parent.mkdir(parents=True)
            target.write_bytes(gzip.compress(raw + b"\n", mtime=0))
            with patch.object(reconciliation, "ROOT", root), self.assertRaisesRegex(ValueError, "archival registry fixture changed"):
                reconciliation._archival_registry_with_10342()

    def test_offline_discovery_reproduces_the_original_record_and_repeats_exactly(self):
        body = index_html(("/notices/medias/fichiers/add/2362", self.record["title"])).replace("Juillet 2026", "Octobre 2026").encode()
        def fetch(url, method):
            self.assertEqual(method, "GET")
            if url == discovery.INDEX_URL:
                return discovery.FetchResult(body, discovery.INDEX_URL, "text/html")
            self.assertEqual(url, self.record["listed_url"])
            return discovery.FetchResult(self.pdf.read_bytes(), self.record["resolved_url"], "application/pdf")
        empty = dict(self.registry, notices=[])
        with (patch.object(socket.socket, "connect", side_effect=AssertionError("offline only")),
              patch.object(subprocess, "run", side_effect=AssertionError("no Git at test runtime")),
              patch.object(subprocess, "check_output", side_effect=AssertionError("no Git at test runtime"))):
            reconciliation._authenticate_registry_baseline(self.registry)
            once = discovery.discover_registry(empty, fetch=fetch, discovered_at=self.record["first_discovered_at"]).registry
            twice = discovery.discover_registry(once, fetch=fetch, discovered_at="2026-10-29T00:00:00Z").registry
        self.assertEqual(once["notices"], [self.record])
        self.assertEqual(twice, once)
        self.assertEqual(empty["notices"], [])

    def test_no_numerical_admission_or_change_to_observations_and_five_warnings(self):
        self.assertFalse(coverage.is_relevant_notice(self.record))
        self.assertNotIn(NOTICE_ID, [n["notice_id"] for n in discovery.registry_event_notices(self.registry)])
        self.assertTrue({"coverage", "parser", "survey_metadata"}.isdisjoint(self.record))
        current = json.loads((ROOT / "commission_notice_registry.json").read_bytes())
        self.assertEqual(coverage.coverage_warnings(current), coverage.coverage_warnings(self.registry))
        self.assertEqual(coverage.coverage_summary(current), self.summary)
        self.assertEqual(self.summary["unresolved_notice_ids"], ["commission:10333", "commission:10327", "commission:10319", "commission:10264", "commission:10260"])
        lane = json.loads((ROOT / "publication_manifest.json").read_bytes())["lanes"]["polls"]
        self.assertEqual(lane["warnings"], coverage.coverage_warnings(current))
        self.assertEqual(lane["commission_notice_coverage"], self.summary)
        first = json.loads((ROOT / "polls.json").read_bytes())
        second = json.loads((ROOT / "second_round_polls.json").read_bytes())["events"]
        before = copy.deepcopy(first + second)
        _authenticate_historical_polling_corpus(first, second)
        self.assertEqual((len(first), len(second)), (349, 108))
        self.assertEqual(first + second, before)


if __name__ == "__main__":
    unittest.main()
