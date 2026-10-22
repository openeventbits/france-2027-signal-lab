"""Complete original-table comparisons and bounded live Commission reviews."""

import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commission_notice_coverage import reconcile_commission_notices
from fetch_polls import integrate_french_migration_source
from poll_contract import make_event_id, validate_poll_events
from poll_migration import candidate_identity, parse_french_frozen_fixture, reviewed_candidate_name
from reviewed_commission_coverage import (
    NOTICE_IDS, admit_batch2_configurations, load_batch2_review,
    reconcile_batch2_notice_coverage,
)


ROOT = Path(__file__).parent
FIXTURES = ROOT / "test_fixtures/fr27_polling"
BLOCKED = {"commission:10264", "commission:10260", "commission:10205"}
# Independently captured from unmodified origin/main before adding the identity.
FROZEN_EXTRACTION_DIGESTS = {
    "fr_mediawiki_238906992.json": "8de9a8b4342e29f8d8d671491bb5bb2c992605f89f399295aefb237800d89f91",
    "fr_mediawiki_239248634.json": "c39b5df75ac394c628f1af8fcd19c038bfc90f5fe2afbefe66e1cca1d9a2e5bd",
    "fr_mediawiki_239255702.json": "6aefdef1c506475660dffbc4e7481f65454257ca241b6f6cd9761228f3a6ff31",
    "fr_mediawiki_239587014.json": "89f355217c0bf1019ace496535aaa9e7aab057dc99320f9a726dafb5c2365f8e",
    "fr_mediawiki_240128358.json": "e09d3a37a790083a247121f984626183a114ab485ad222e0398e8cd70d0a79b4",
    "fr_mediawiki_240131611.json": "2c0a4d98fd3227b8a997b422c77253a8977c97be4eb0d2dcc439d6267089cc76",
    "fr_mediawiki_240287946.json": "91dde20324c166b3aefa719a6fdb822303b3aaf3c4b1a6192065c215cae22f68",
    "fr_mediawiki_240408882.json": "1cf44374cd70c3d3f640438f9d3397c3602c19b1c3ff97e2974dc5e9d33ec670",
    "fr_mediawiki_240418689.json": "42852c29c96d35f7a4102661acc73eab179267cd7b20803d7fab51e71998c665",
    "fr_mediawiki_240485606.json": "85a25b461ce1355e3172651b44a1349627a8f12b0ea902b18cf2096e6ce93eb9",
    "fr_mediawiki_240490172.json.gz": "149ef15e6e602f9800fb766d0706e5da80825a61ddb9d624ebfc28bd5cb38368",
    "fr_mediawiki_240498648.json.gz": "55a7fa5bca8aa1c3eb388c0b8ccee98c7dd609c1bee8de63c1a5c7f264f17ddb",
    "fr_mediawiki_240522402.json.gz": "f8eb6bd39e4718332bd63ed5a58a1c42c579c6d5ac8f418747b5dbf6217e60e0",
    "fr_mediawiki_240562307.json.gz": "f61126b093229d94edf730eda22a2dbcf723a289acfca923bdad53b99eadc811",
}


def digest(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def fixture(name):
    path = FIXTURES / name
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def official_scores(candidates):
    return {c["name"]: float(c["published_score"].rstrip("%").replace(",", ".")) for c in candidates}


def event_scores(event):
    return {reviewed_candidate_name(c["name"]): c["score"] for c in event["candidates"]}


class CommissionCoverageBatch2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = gzip.decompress((FIXTURES / "batch2_pre_review_335_102.json.gz").read_bytes())
        if hashlib.sha256(raw).hexdigest() != "edd1c15a32fc5350ed6b035546c495fd1fa3b37aebd78dda1e5ead3fdd1d1a3b":
            raise AssertionError("Batch 2 historical baseline changed")
        cls.before = json.loads(raw)
        cls.tables = fixture("batch2_original_tables.json")
        if digest(cls.tables) != "d3284beeb5b3cea6c0d0aa28d22113f68c5a2d194838a0ca05c048e425fd0010":
            raise AssertionError("Batch 2 original-table transcription changed")
        cls.review = load_batch2_review()
        cls.first, cls.admission_report = admit_batch2_configurations(
            cls.before["first_round"], cls.before["commission_registry"],
        )
        cls.second = cls.before["second_round"]

    def coverage(self, events=None, registry=None):
        notices = copy.deepcopy(self.before["commission_registry"] if registry is None else registry)
        reconcile_batch2_notice_coverage(notices, self.first + self.second if events is None else events)
        return {n["notice_id"]: n for n in notices["notices"]}

    def test_complete_audit_has_all_79_current_configurations_and_twelve_original_hashes(self):
        self.assertEqual(len(self.tables["notices"]), 12)
        self.assertEqual(sum(len(n["configurations"]) for n in self.tables["notices"]), 79)
        before = {n["notice_id"]: n for n in self.before["commission_registry"]["notices"]}
        for notice in self.tables["notices"]:
            self.assertEqual(notice["content_sha256"], before[notice["notice_id"]]["content_sha256"])
            self.assertTrue(all(c["pdf_page"] > 0 for c in notice["configurations"]))

    def test_all_reconciled_tables_match_exact_original_publication_values(self):
        records = {r["notice_identity"]["notice_id"]: r for r in self.review["notice_reviews"]}
        count = 0
        for notice in self.tables["notices"]:
            if notice["notice_id"] in BLOCKED:
                continue
            events = records[notice["notice_id"]]["published_events"]
            for table in notice["configurations"]:
                candidates = table.get("original_public_report", table)["candidates"]
                matches = [e for e in events if e["round"] == table["round"]
                           and event_scores(e) == official_scores(candidates)]
                self.assertEqual(len(matches), 1, (notice["notice_id"], table["configuration"]))
                self.assertEqual(table["published_event_ids_before"], [matches[0]["event_id"]])
                count += 1
        self.assertEqual(count, 70)

    def test_only_two_numeric_opinionway_tables_are_admitted_with_exact_ids(self):
        self.assertEqual((len(self.first), len(self.second)), (337, 102))
        self.assertEqual(self.admission_report["admitted"], 2)
        self.assertCountEqual([d["canonical_event"]["event_id"] for d in self.review["admissions"]], [
            "34b67c973777cf14f9c19068b4642d119367e3312053f442ba16e9612c051cac",
            "547d14cf13fb2f407e743b91f6347dad9c0a3db48e750b380bdfc27b8fede2cd",
        ])
        notice = next(n for n in self.tables["notices"] if n["notice_id"] == "commission:10260")
        for decision, table in zip(self.review["admissions"], notice["configurations"][:2]):
            event = decision["canonical_event"]
            self.assertIsNone(decision["previous_event"])
            self.assertEqual(event_scores(event), official_scores(table["candidates"]))
            self.assertEqual(event["reported_total"], 100)
            self.assertNotIn("supersedes_event_id", event)
            self.assertNotIn("official_notice_id", event)  # No parser claim.
            self.assertEqual((event["sample_size"], event["sample_scope"]), (935, "registered_voters"))
            self.assertIsNone(event["publication_date"])  # Listing date is not an asserted publication date.

    def test_all_437_historical_objects_and_all_batch1_lineage_are_unchanged(self):
        after = {e["event_id"]: e for e in self.first + self.second}
        old = self.before["first_round"] + self.before["second_round"]
        self.assertEqual(len(old), 437)
        for event in old:
            self.assertEqual(after[event["event_id"]], event)
        self.assertEqual(len(after), 439)
        from reviewed_polling_accuracy import load_batch1_review
        for decision in load_batch1_review()["decisions"]:
            self.assertEqual(after[decision["canonical_event"]["event_id"]], decision["canonical_event"])

    def test_harris_surveys_are_complete_aliases_and_cannot_be_admitted_again(self):
        expected = {"commission:10305": (5, 2), "commission:10277": (5, 2), "commission:10263": (5, 3)}
        for record in self.review["notice_reviews"]:
            notice_id = record["notice_identity"]["notice_id"]
            if notice_id in expected:
                events = record["published_events"]
                self.assertEqual(tuple(sum(e["round"] == r for e in events) for r in ("first_round", "second_round")), expected[notice_id])
                self.assertTrue(all(e["pollster"] == "Harris" for e in events))
        self.assertTrue(all(d["notice_id"] == "commission:10260" for d in self.review["admissions"]))

    def test_cluster_paired_precision_evidence_preserves_every_legacy_object(self):
        for notice in self.tables["notices"]:
            if notice["notice_id"] not in {"commission:10273", "commission:10251"}:
                continue
            self.assertEqual(len(notice["additional_primary_evidence"]["sha256"]), 64)
            for table in notice["configurations"]:
                self.assertNotEqual(official_scores(table["candidates"]), official_scores(table["original_public_report"]["candidates"]))
            record = next(r for r in self.review["notice_reviews"] if r["notice_identity"]["notice_id"] == notice["notice_id"])
            original = {e["event_id"]: e for e in self.before["first_round"]}
            self.assertTrue(all(e == original[e["event_id"]] for e in record["published_events"]))

    def test_all_nine_reconciliations_require_complete_first_and_second_round_collections(self):
        result = self.coverage()
        for record in self.review["notice_reviews"]:
            notice_id = record["notice_identity"]["notice_id"]
            coverage = result[notice_id]["coverage"]
            self.assertEqual(coverage["state"], record["outcome"])
            if notice_id not in BLOCKED:
                self.assertEqual(coverage["matched_event_ids"], [e["event_id"] for e in record["published_events"]])
        self.assertEqual(sum(result[n]["coverage"]["state"] == "reconciled" for n in NOTICE_IDS), 9)

    def test_all_other_notice_objects_including_10324_remain_exactly_unchanged(self):
        result = self.coverage()
        for notice in self.before["commission_registry"]["notices"]:
            if notice["notice_id"] not in NOTICE_IDS:
                self.assertEqual(result[notice["notice_id"]], notice)

    def test_bounded_scores_are_literal_and_never_numeric_admissions(self):
        bounded = [(n["notice_id"], c) for n in self.tables["notices"] for c in n["configurations"]
                   if any(v["published_score"].startswith("<") for v in c["candidates"])]
        self.assertEqual(len(bounded), 2)
        self.assertEqual(sum(v["published_score"].startswith("<") for _, c in bounded for v in c["candidates"]), 3)
        for notice_id, table in bounded:
            self.assertEqual(table["published_event_ids_before"], [])
            self.assertEqual(self.coverage()[notice_id]["coverage"]["state"], "unresolved")
        for decision in self.review["admissions"]:
            event = copy.deepcopy(decision["canonical_event"])
            event["candidates"][0]["score"] = "<1%"
            with self.assertRaisesRegex(ValueError, "numeric"):
                validate_poll_events([event])

    def test_composite_rn_option_is_not_relabelled_as_bardella(self):
        table = next(n for n in self.tables["notices"] if n["notice_id"] == "commission:10205")
        self.assertTrue(all(any(c["name"] == "Le candidat du RN, Marine Le Pen ou Jordan Bardella" for c in t["candidates"]) for t in table["configurations"]))
        self.assertTrue(all(not t["published_event_ids_before"] for t in table["configurations"]))
        coverage = self.coverage()["commission:10205"]["coverage"]
        self.assertEqual(coverage["method"], "reviewed_composite_candidate_identity_conflict")
        self.assertEqual(coverage["matched_event_ids"], [])

    def test_partial_10260_stays_unresolved_even_when_ordinary_coverage_accepts_two_tables(self):
        registry = copy.deepcopy(self.before["commission_registry"])
        reconcile_commission_notices(registry, self.first)
        notice = next(n for n in registry["notices"] if n["notice_id"] == "commission:10260")
        self.assertEqual(notice["coverage"]["state"], "reconciled")
        reconcile_batch2_notice_coverage(registry, self.first + self.second)
        self.assertEqual(notice["coverage"]["state"], "unresolved")
        self.assertEqual(notice["coverage"]["method"], "reviewed_incomplete_bounded_score_configuration")

    def test_repeat_admission_and_coverage_are_identical_without_mutating_inputs(self):
        first, registry = copy.deepcopy(self.first), copy.deepcopy(self.before["commission_registry"])
        repeated, report = admit_batch2_configurations(first, registry)
        self.assertEqual(repeated, self.first)
        self.assertEqual(report["already_applied"], 2)
        self.assertEqual(report["admitted"], 0)
        self.assertEqual(first, self.first)
        self.assertEqual(registry, self.before["commission_registry"])
        reconcile_batch2_notice_coverage(registry, first + self.second)
        before = copy.deepcopy(registry)
        reconcile_batch2_notice_coverage(registry, first + self.second)
        self.assertEqual(registry, before)

    def test_changed_canonical_objects_and_alternative_id_duplicates_fail_closed(self):
        for operation in ("score", "sample", "scope", "provenance", "lineage", "duplicate"):
            events = copy.deepcopy(self.first)
            event = next(e for e in events if e.get("reviewed_correction_id") == "FR27-B2-10260-H1")
            if operation == "score": event["candidates"][0]["score"] += .1; event["reported_total"] += .1
            if operation == "sample": event["sample_size"] = 1001
            if operation == "scope": event["sample_scope"] = "reported"
            if operation == "provenance": event["commissioner"] = "another buyer"
            if operation == "lineage": event["reviewed_notice_page"] = 14
            if operation == "duplicate":
                extra = copy.deepcopy(event)
                extra["source_url"] = "https://example.test/duplicate"
                extra["event_id"] = make_event_id(extra["pollster"], extra["fieldwork_start"], extra["fieldwork_end"], extra["hypothesis"], extra["source_url"])
                events.append(extra)
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                admit_batch2_configurations(events, self.before["commission_registry"])

    def test_future_discovery_identity_cannot_create_a_second_configuration(self):
        events = copy.deepcopy(self.before["first_round"])
        incoming = copy.deepcopy(self.review["admissions"][0]["canonical_event"])
        incoming["hypothesis"] = "French source — discovered elsewhere"
        incoming["event_id"] = make_event_id(incoming["pollster"], incoming["fieldwork_start"], incoming["fieldwork_end"], incoming["hypothesis"], incoming["source_url"])
        events.append(incoming)
        with self.assertRaisesRegex(ValueError, "identity collision"):
            admit_batch2_configurations(events, self.before["commission_registry"])

    def test_admission_requires_exact_notice_evidence(self):
        for operation in ("missing", "duplicate", "hash", "url", "dates"):
            registry = copy.deepcopy(self.before["commission_registry"])
            notice = next(n for n in registry["notices"] if n["notice_id"] == "commission:10260")
            if operation == "missing": registry["notices"].remove(notice)
            if operation == "duplicate": registry["notices"].append(copy.deepcopy(notice))
            if operation == "hash": notice["content_sha256"] = "0" * 64
            if operation == "url": notice["resolved_url"] += "?different"
            if operation == "dates": notice["survey_metadata"]["fieldwork_end"] = "2026-09-11"
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "notice"):
                admit_batch2_configurations(self.before["first_round"], registry)

    def test_every_notice_identity_change_fails_closed_without_affecting_other_records(self):
        changes = {"content_sha256": "0" * 64, "resolved_url": "https://example.test/unreviewed.pdf",
                   "institute": "Another institute", "listed_date": "2026-10-21", "title": "different",
                   "commissioner": "unreviewed", "listed_url": "https://example.test/notice",
                   "confirmed_rounds": [], "survey_metadata": {"fieldwork_start": "2026-01-01", "fieldwork_end": "2026-01-02"}}
        for notice_id in NOTICE_IDS - BLOCKED:
            for field, value in changes.items():
                registry = copy.deepcopy(self.before["commission_registry"])
                notice = next(n for n in registry["notices"] if n["notice_id"] == notice_id)
                notice[field] = value
                with self.subTest(notice_id=notice_id, field=field):
                    result = self.coverage(registry=registry)
                    self.assertEqual(result[notice_id]["coverage"]["state"], "unresolved")
                    self.assertEqual(result[notice_id]["coverage"]["matched_event_ids"], [])

    def test_missing_changed_duplicate_extra_and_wrong_round_objects_cannot_resolve(self):
        for notice_id in NOTICE_IDS - BLOCKED:
            record = next(r for r in self.review["notice_reviews"] if r["notice_identity"]["notice_id"] == notice_id)
            event_id = record["published_events"][0]["event_id"]
            for operation in ("missing", "score", "sample", "source", "duplicate", "extra", "round", "dates"):
                events = copy.deepcopy(self.first + self.second)
                event = next(e for e in events if e["event_id"] == event_id)
                if operation == "missing": events.remove(event)
                if operation == "score": event["candidates"][0]["score"] += .1
                if operation == "sample": event["sample_size"] += 1
                if operation == "source": event["source_url"] = "https://example.test/another"
                if operation == "duplicate": events.append(copy.deepcopy(event))
                if operation == "extra": events.append({**copy.deepcopy(event), "event_id": "f" * 64})
                if operation == "round": event["round"] = "unreviewed_round"
                if operation == "dates": event["fieldwork_end"] = "2026-10-21"
                with self.subTest(notice_id=notice_id, operation=operation):
                    self.assertEqual(self.coverage(events=events)[notice_id]["coverage"]["state"], "unresolved")

    def test_round_one_alone_is_insufficient_for_surveys_with_runoffs(self):
        result = self.coverage(events=self.first)
        for notice_id in ("commission:10305", "commission:10277", "commission:10263", "commission:10323", "commission:10270", "commission:10242"):
            self.assertEqual(result[notice_id]["coverage"]["state"], "unresolved")

    def test_duplicate_or_reclassified_reviewed_notices_stop(self):
        for operation in ("duplicate", "irrelevant"):
            registry = copy.deepcopy(self.before["commission_registry"])
            notice = next(n for n in registry["notices"] if n["notice_id"] == "commission:10305")
            if operation == "duplicate": registry["notices"].append(copy.deepcopy(notice))
            else: notice["classification"] = "irrelevant"
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                reconcile_batch2_notice_coverage(registry, self.first + self.second)

    def test_unreviewed_notice_identity_is_never_authorized(self):
        notice = copy.deepcopy(next(n for n in self.before["commission_registry"]["notices"] if n["notice_id"] == "commission:10305"))
        notice["notice_id"] = "commission:99999"
        registry = {"notices": [notice]}
        before = copy.deepcopy(registry)
        reconcile_batch2_notice_coverage(registry, self.first + self.second)
        self.assertEqual(registry, before)

    def test_reviewed_bundle_changes_require_a_new_explicit_decision(self):
        for field in ("admissions", "notice_reviews"):
            value = copy.deepcopy(self.review)
            value[field].pop()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "changed.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "explicit review"):
                    load_batch2_review(path)

    def test_candidate_identity_does_not_change_any_of_fourteen_frozen_extractions(self):
        self.assertEqual(candidate_identity("Karim Bouamrane"), "karim-bouamrane")
        for name, expected in FROZEN_EXTRACTION_DIGESTS.items():
            parsed = fixture(name)
            parsed = parsed.get("parse", parsed)
            result = parse_french_frozen_fixture(parsed, allow_reviewed_polony=parsed["revid"] >= 240562307)
            with self.subTest(name=name):
                self.assertEqual(digest(result), expected)

    def test_current_and_older_wikipedia_ingestion_preserve_all_events_and_admissions(self):
        from reviewed_composite_rn import load_composite_review

        # The separate 10205 review supersedes three historical objects after
        # Batch 2. Every other object and both Batch 2 admissions stay exact.
        decisions = load_composite_review()["decisions"]
        superseded = {d["previous_event"]["event_id"] for d in decisions}
        expected = {e["event_id"]: e for e in self.first if e["event_id"] not in superseded}
        expected.update({d["canonical_event"]["event_id"]: d["canonical_event"] for d in decisions})
        first, second = self.first, self.second
        for name in ("fr_mediawiki_240570516.json.gz", "fr_mediawiki_240569682.json.gz", "fr_mediawiki_240562307.json.gz", "fr_mediawiki_240522402.json.gz"):
            parsed = fixture(name)
            migrated, runoff, report, _ = integrate_french_migration_source(
                parsed, first, second,
                [e for e in self.before["first_round"] if e.get("official_notice_id")],
                retain_published_history=True,
            )
            after, admissions = admit_batch2_configurations(migrated, self.before["commission_registry"])
            self.assertEqual({e["event_id"]: e for e in after}, expected)
            self.assertEqual(runoff, second)
            self.assertEqual(admissions["already_applied"], 2)
            self.assertEqual(report["unexplained_historical_losses"], 0)
            self.assertEqual(report["polling_accuracy_batch1"]["already_applied"], 9)
            first = after

    def test_10327_review_changes_only_eight_exact_source_variants(self):
        from reviewed_polling_accuracy import load_batch1_review

        review = copy.deepcopy(load_batch1_review())
        refresh, = review.pop("source_refresh_reviews")
        self.assertEqual(refresh["review_id"], "FR27-B2-IFOP-SOURCE-10327")
        self.assertEqual(refresh["content_sha256"], "39b82377458a44db5c7de3ad95ca4f7938f87dd791163083206538c32795fac5")
        self.assertEqual(refresh["methodology_pdf_page"], 2)
        self.assertEqual({r["pdf_page"] for r in refresh["representations"]}, {13, 16, 17, 18, 19, 20, 21})
        self.assertEqual(len(refresh["representations"]), 8)
        for representation in reversed(refresh["representations"]):
            decision = next(d for d in review["decisions"] if d["decision_id"] == representation["decision_id"])
            self.assertEqual(decision["source_variants"].pop(), representation["incoming_variant"])
            self.assertEqual(decision["canonical_event"]["event_id"], representation["canonical_event_id"])
        # Exact original registry, including every canonical/predecessor object,
        # previous source variant, evidence and 10324 coverage review.
        self.assertEqual(digest(review), "ecce41bfd0ff61dc30fd8003c8fea2ae5fc43e21743922f735b2b3eda4db207b")

    def test_10327_exact_variants_do_not_allow_other_source_or_factual_drift(self):
        from rehearse_fr_poll_migration import _assert_production_source_structure
        from reviewed_polling_accuracy import reconcile_batch1_accuracy

        from reviewed_polling_accuracy import load_batch1_review
        refresh, = load_batch1_review()["source_refresh_reviews"]
        for representation in refresh["representations"]:
            revision = representation.get("discovery_revision", refresh["discovery_revision"])
            parsed = fixture(f"fr_mediawiki_{revision}.json.gz")
            rows = _assert_production_source_structure(parsed)
            for field in ("source_url", "score", "sample_size", "sample_scope"):
                changed = copy.deepcopy(rows)
                row = next(r for values in (changed["first_round"], changed["second_round"])
                           for r in values if r["source_locator"] == representation["source_locator"])
                if field == "source_url": row[field] += "?unreviewed=1"
                elif field == "score": row["candidates"][0]["score"] += .125
                elif field == "sample_size": row[field] += 1
                else: row[field] = "registered_voters"
                with self.subTest(locator=row["source_locator"], field=field):
                    with self.assertRaisesRegex(ValueError, "reviewed source facts/provenance changed"):
                        reconcile_batch1_accuracy(changed, parsed["revid"], self.first, self.second,
                                                  retain_published_history=True)

    def test_extraction_loss_guard_still_runs_before_official_admissions(self):
        from rehearse_fr_poll_migration import SourceDriftError
        parsed = fixture("fr_mediawiki_240562307.json.gz")
        rows = parse_french_frozen_fixture(parsed, allow_reviewed_polony=True)
        rows["first_round"] = rows["first_round"][:50]
        with patch("rehearse_fr_poll_migration._assert_production_source_structure", return_value=rows):
            with self.assertRaises(SourceDriftError):
                integrate_french_migration_source(parsed, self.first, self.second, [], retain_published_history=True)

    def test_only_live_french_cli_applies_later_review(self):
        source = (ROOT / "fetch_polls.py").read_text(encoding="utf-8")
        self.assertIn('if not args.french_fixture:\n                from reviewed_commission_coverage import admit_batch2_configurations', source)
        self.assertIn('if args.wikipedia_source == "french" and not args.french_fixture:', source)
        for decision in self.review["admissions"]:
            self.assertFalse({"candidacy_status", "declared", "status"} & set(decision["canonical_event"]))


if __name__ == "__main__":
    unittest.main()
