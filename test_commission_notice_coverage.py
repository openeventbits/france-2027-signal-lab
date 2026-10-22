import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from commission_notice_coverage import (
    CORROBORATING_WAVE_ATTRIBUTES,
    coverage_summary,
    coverage_warnings,
    reconcile_commission_notices,
    validate_notice_coverage,
)


def event(
    label,
    *,
    pollster="Ifop",
    start="2026-07-01",
    end="2026-07-02",
    source="https://example.test/poll",
    sample_size=1000,
    commissioner=None,
    publication_date=None,
    round_name="first_round",
    official_notice_id=None,
):
    payload = {
        "event_id": hashlib.sha256(label.encode()).hexdigest(),
        "round": round_name,
        "pollster": pollster,
        "fieldwork_start": start,
        "fieldwork_end": end,
        "source_url": source,
        "sample_size": sample_size,
        "commissioner": commissioner,
        "publication_date": publication_date,
    }
    if official_notice_id is not None:
        payload["official_notice_id"] = official_notice_id
    return payload


def notice(
    notice_id="commission:20000",
    *,
    classification="unsupported",
    pollster="Ifop",
    start="2026-07-01",
    end="2026-07-02",
    sample_size=None,
    commissioner=None,
    publication_date=None,
    confirmed_rounds=None,
):
    metadata = {
        "fieldwork_start": start,
        "fieldwork_end": end,
    }
    if sample_size is not None:
        metadata["sample_size"] = sample_size
    if commissioner is not None:
        metadata["commissioner"] = commissioner
    if publication_date is not None:
        metadata["publication_date"] = publication_date
    return {
        "notice_id": notice_id,
        "title": f"{notice_id} presidential voting intentions",
        "classification": classification,
        "institute": pollster,
        "confirmed_rounds": (
            ["first_round"]
            if confirmed_rounds is None
            else list(confirmed_rounds)
        ),
        "survey_metadata": metadata,
    }


def registry(*notices):
    return {"notices": list(notices)}


class CommissionNoticeCoverageTests(unittest.TestCase):
    def test_missing_legacy_coverage_is_unresolved_and_warns(self):
        item = notice()
        payload = registry(item)

        self.assertEqual(
            coverage_summary(payload),
            {
                "relevant": 1,
                "parsed": 0,
                "reconciled": 0,
                "unresolved": 1,
                "unresolved_notice_ids": [item["notice_id"]],
            },
        )
        self.assertEqual(len(coverage_warnings(payload)), 1)
        self.assertIn(item["notice_id"], coverage_warnings(payload)[0])
        self.assertNotIn("coverage", item)

    def test_parsed_requires_direct_official_notice_provenance(self):
        item = notice(classification="eligible")
        published = event(
            "parsed",
            official_notice_id=item["notice_id"],
        )

        reconcile_commission_notices(registry(item), [published])

        self.assertEqual(item["coverage"]["state"], "parsed")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [published["event_id"]],
        )

    def test_unsupported_notice_reconciles_to_exact_published_wave(self):
        item = notice()
        published = event("reconciled")
        payload = registry(item)

        reconcile_commission_notices(payload, [published])

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(coverage_warnings(payload), [])

    def test_unmatched_relevant_notice_is_unresolved_and_warns(self):
        item = notice()
        payload = registry(item)

        reconcile_commission_notices(payload, [])

        self.assertEqual(item["coverage"]["state"], "unresolved")
        self.assertEqual(len(coverage_warnings(payload)), 1)
        self.assertIn(item["notice_id"], coverage_warnings(payload)[0])

    def test_ambiguous_same_window_waves_remain_unresolved(self):
        item = notice()
        payload = registry(item)
        published = [
            event("wave-a", source="https://a.example/poll", sample_size=900),
            event("wave-b", source="https://b.example/poll", sample_size=1100),
        ]

        reconcile_commission_notices(payload, published)

        self.assertEqual(item["coverage"]["state"], "unresolved")
        self.assertEqual(
            item["coverage"]["method"],
            "ambiguous_published_waves",
        )

    def test_sample_size_can_disambiguate_same_window_waves(self):
        item = notice(sample_size=1100)
        matching = event(
            "wave-b",
            source="https://b.example/poll",
            sample_size=1100,
        )
        payload = registry(item)

        reconcile_commission_notices(
            payload,
            [
                event(
                    "wave-a",
                    source="https://a.example/poll",
                    sample_size=900,
                ),
                matching,
            ],
        )

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [matching["event_id"]],
        )

    def test_conflicting_corroboration_remains_unresolved(self):
        item = notice(sample_size=1000, commissioner="Y")
        payload = registry(item)
        published = [
            event(
                "wave-a",
                source="https://a.example/poll",
                sample_size=1000,
                commissioner="X",
            ),
            event(
                "wave-b",
                source="https://b.example/poll",
                sample_size=1200,
                commissioner="Y",
            ),
        ]

        reconcile_commission_notices(payload, published)

        self.assertEqual(item["coverage"]["state"], "unresolved")
        self.assertEqual(
            item["coverage"]["method"],
            "ambiguous_published_waves",
        )

    def test_conflicting_corroboration_is_attribute_order_independent(self):
        published = [
            event(
                "wave-a",
                source="https://a.example/poll",
                sample_size=1000,
                commissioner="X",
            ),
            event(
                "wave-b",
                source="https://b.example/poll",
                sample_size=1200,
                commissioner="Y",
            ),
        ]
        results = []
        orders = (
            CORROBORATING_WAVE_ATTRIBUTES,
            tuple(reversed(CORROBORATING_WAVE_ATTRIBUTES)),
        )
        for attribute_order in orders:
            item = notice(sample_size=1000, commissioner="Y")
            with patch(
                "commission_notice_coverage.CORROBORATING_WAVE_ATTRIBUTES",
                attribute_order,
            ):
                reconcile_commission_notices(registry(item), published)
            results.append(item["coverage"])

        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["state"], "unresolved")
        self.assertEqual(
            results[0]["method"],
            "ambiguous_published_waves",
        )

    def test_unique_exact_wave_ignores_optional_metadata_mismatch(self):
        item = notice(sample_size=1200)
        published = event("unique-wave", sample_size=1000)

        reconcile_commission_notices(registry(item), [published])

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [published["event_id"]],
        )

    def test_reconciliation_persists_strict_coverage_for_all_relevant_notices(
        self,
    ):
        matched = notice(notice_id="commission:20000")
        unmatched = notice(
            notice_id="commission:19999",
            start="2026-07-03",
            end="2026-07-04",
        )
        payload = registry(matched, unmatched)

        reconcile_commission_notices(payload, [event("published")])

        for item in payload["notices"]:
            self.assertIn("coverage", item)
            validate_notice_coverage(item)

    def test_multiple_events_with_one_wave_use_deterministic_representative(self):
        first = event(
            "one-wave-a",
            commissioner="Client X",
            publication_date="2026-07-03",
        )
        second = event(
            "one-wave-b",
            commissioner="Client X",
            publication_date="2026-07-03",
        )
        expected_event_id = min(first["event_id"], second["event_id"])

        for published in ((first, second), (second, first)):
            with self.subTest(
                input_event_ids=[item["event_id"] for item in published]
            ):
                item = notice(
                    sample_size=1000,
                    commissioner="Client X",
                    publication_date="2026-07-03",
                )

                reconcile_commission_notices(registry(item), published)

                self.assertEqual(item["coverage"]["state"], "reconciled")
                self.assertEqual(
                    item["coverage"]["method"],
                    "exact_pollster_fieldwork_round",
                )
                self.assertEqual(
                    item["coverage"]["matched_event_ids"],
                    [expected_event_id],
                )

    def test_round_incompatibility_fails_closed(self):
        cases = (
            (
                notice(),
                event("second-round", round_name="second_round"),
                "no_exact_published_wave",
            ),
            (
                notice(confirmed_rounds=["second_round"]),
                event("first-round"),
                "no_compatible_published_round",
            ),
        )

        for item, published, expected_method in cases:
            with self.subTest(expected_method=expected_method):
                reconcile_commission_notices(registry(item), [published])

                self.assertEqual(item["coverage"]["state"], "unresolved")
                self.assertEqual(
                    item["coverage"]["method"],
                    expected_method,
                )

    def test_zero_match_optional_metadata_is_non_dispositive(self):
        item = notice(sample_size=999, commissioner="Client Y")
        expected = event(
            "wave-b",
            source="https://b.example/poll",
            sample_size=1200,
            commissioner="Client Y",
        )
        published = [
            event(
                "wave-a",
                source="https://a.example/poll",
                sample_size=1000,
                commissioner="Client X",
            ),
            expected,
        ]

        reconcile_commission_notices(registry(item), published)

        self.assertEqual(item["coverage"]["state"], "reconciled")
        self.assertEqual(
            item["coverage"]["matched_event_ids"],
            [expected["event_id"]],
        )

    def test_pollster_mismatch_does_not_reconcile(self):
        item = notice(pollster="Ifop")

        reconcile_commission_notices(
            registry(item),
            [event("wrong-pollster", pollster="Ipsos")],
        )

        self.assertEqual(item["coverage"]["state"], "unresolved")

    def test_date_incompatibility_does_not_reconcile(self):
        item = notice(start="2026-07-01", end="2026-07-03")

        reconcile_commission_notices(
            registry(item),
            [event("wrong-date", start="2026-07-01", end="2026-07-02")],
        )

        self.assertEqual(item["coverage"]["state"], "unresolved")

    def test_irrelevant_notice_has_no_state_and_no_warning(self):
        item = notice(classification="excluded_non_voting")
        payload = registry(item)

        reconcile_commission_notices(payload, [])

        self.assertNotIn("coverage", item)
        self.assertEqual(coverage_warnings(payload), [])
        self.assertEqual(
            coverage_summary(payload),
            {
                "relevant": 0,
                "parsed": 0,
                "reconciled": 0,
                "unresolved": 0,
                "unresolved_notice_ids": [],
            },
        )


class ElectionBarometerCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parent
        cls.review = json.loads((root / "fr27_commission_barometer_review.json").read_text(encoding="utf-8"))
        cls.first = json.loads((root / "polls.json").read_text(encoding="utf-8"))
        cls.second = json.loads((root / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        cls.registry = json.loads((root / "commission_notice_registry.json").read_text(encoding="utf-8"))

    def coverage(self, record=None, events=None, mutate=None):
        record = record or next(r for r in self.review["notices"] if r["notice_id"] == "commission:10284")
        identity = copy.deepcopy(record["notice_identity"])
        urls = identity.pop("resolved_urls")
        identity["resolved_url"] = urls[0]
        identity["classification"] = "eligible"
        if mutate: mutate(identity)
        registry = {"notices": [identity]}
        reconcile_commission_notices(registry, self.first + self.second if events is None else events)
        return identity["coverage"]

    def test_original_tables_match_all_numeric_values_and_record_the_literal_conflict(self):
        from poll_migration import candidate_identity
        events = {e["event_id"]: e for e in self.first + self.second}
        self.assertEqual(len(events), 439)
        total = 0
        conflicts = []
        for record in self.review["notices"]:
            for table in record["configurations"]:
                published = {candidate_identity(c["name"]): c["score"] for c in events[table["published_event_id"]]["candidates"]}
                expected = {candidate_identity(c["name"]): float(c["published_score"].replace(",", "."))
                            for c in table["candidates"] if c["published_score"] != "-"}
                if any(c["published_score"] == "-" for c in table["candidates"]):
                    conflicts.append((record["notice_id"], table["pdf_page"], published.pop("nathalie-arthaud")))
                self.assertEqual(published, expected)
                total += 1
        self.assertEqual(total, 23)
        self.assertEqual(conflicts, [("commission:10327", 14, 0)])

    def test_10284_requires_all_ten_exact_reviewed_objects(self):
        record = next(r for r in self.review["notices"] if r["notice_id"] == "commission:10284")
        result = self.coverage()
        self.assertEqual(result["state"], "reconciled")
        self.assertEqual(result["matched_event_ids"], record["published_event_ids"])
        self.assertEqual(len(result["matched_event_ids"]), 10)

    def test_one_matching_configuration_cannot_clear_full_notice(self):
        record = next(r for r in self.review["notices"] if r["notice_id"] == "commission:10284")
        one = [e for e in self.first if e["event_id"] == record["published_event_ids"][0]]
        self.assertEqual(self.coverage(events=one)["state"], "unresolved")

    def test_10327_remains_unresolved_with_all_thirteen_lineups_present(self):
        record = next(r for r in self.review["notices"] if r["notice_id"] == "commission:10327")
        self.assertEqual(len(record["published_event_ids"]), 13)
        self.assertEqual(self.coverage(record), {
            "state": "unresolved", "matched_event_ids": [],
            "method": "reviewed_barometer_unresolved_literal_score"})

    def test_missing_extra_duplicate_or_changed_event_evidence_cannot_reconcile(self):
        record = next(r for r in self.review["notices"] if r["notice_id"] == "commission:10284")
        for operation in ("missing", "score", "sample", "scope", "source", "date", "identity", "lineage", "extra", "duplicate"):
            events = copy.deepcopy(self.first + self.second)
            target = next(e for e in events if e["event_id"] == record["published_event_ids"][0])
            if operation == "missing": events.remove(target)
            elif operation == "score": target["candidates"][0]["score"] += .1
            elif operation == "sample": target["sample_size"] += 1
            elif operation == "scope": target["sample_scope"] = "reported"
            elif operation == "source": target["source_url"] += "?unreviewed"
            elif operation == "date": target["fieldwork_end"] = "2026-09-30"
            elif operation == "identity": target["event_id"] = "f" * 64
            elif operation == "lineage": target["supersedes_event_id"] = "e" * 64
            else: events.append({**target, **({"event_id": "d" * 64} if operation == "extra" else {})})
            with self.subTest(operation=operation):
                self.assertEqual(self.coverage(events=events)["state"], "unresolved")

    def test_missing_contradictory_or_changed_notice_evidence_cannot_reconcile(self):
        changes = {"content_sha256": "0" * 64, "title": "different title", "institute": "Elabe",
                   "resolved_url": "https://example.test/notice", "confirmed_rounds": [],
                   "survey_metadata": None, "listed_date": "2026-09-29"}
        for key, value in changes.items():
            with self.subTest(field=key):
                self.assertEqual(self.coverage(mutate=lambda n: n.update({key: value}))["state"], "unresolved")

    def test_unsupported_document_cannot_acquire_parsed_or_reconciled_coverage(self):
        self.assertEqual(self.coverage(mutate=lambda n: n.update(classification="unsupported",
            coverage={"state": "parsed", "method": "unreviewed", "matched_event_ids": ["a" * 64]}))["state"], "unresolved")

    def test_confirmed_document_without_parser_still_requires_the_full_exact_review(self):
        reason = ("document confirms 2027 presidential voting intentions, but no "
                  "existing notice parser supports this listing")
        self.assertEqual(self.coverage(mutate=lambda n: n.update(
            classification="unsupported", classification_reason=reason))["state"], "reconciled")
        self.assertEqual(self.coverage(mutate=lambda n: n.update(
            classification="unsupported", classification_reason=reason,
            content_sha256="0" * 64))["state"], "unresolved")

    def test_complete_coverage_is_idempotent_and_does_not_mutate_any_of_439_events(self):
        before = copy.deepcopy(self.first + self.second)
        self.assertEqual(self.coverage(), self.coverage())
        self.assertEqual(before, self.first + self.second)

    def test_review_bundle_changes_stop_instead_of_weakening_matching(self):
        from commission_notice_coverage import CommissionCoverageError
        changed = copy.deepcopy(self.review)
        changed["notices"][0]["outcome"] = "reconciled"
        with patch("commission_notice_coverage.json.loads", return_value=changed):
            with self.assertRaisesRegex(CommissionCoverageError, "explicit review"):
                self.coverage()

    def test_historical_cutover_hashes_remain_immutable_with_exact_later_reviews(self):
        from rehearse_fr_poll_migration import (
            PHASE4_PROTECTED_LOGIC_SHA256, POST_CUTOVER_LOGIC_REVIEWS, phase4a_cutover_contract,
        )
        self.assertEqual(PHASE4_PROTECTED_LOGIC_SHA256, {
            "poll_contract.py": "d2dc32ad925acb6f0cb6b55e2019358c65ecc367c3f21e7542c4bee3db55077f",
            "commission_notice_discovery.py": "c9b8f3186f14b3febcc994aea9700426ae71c6c54b763e34171b375ba6afe58f",
            "commission_notice_coverage.py": "0f467cccb64cb9bfc73ce58f4b874cf6d145233c8bad6736c8bd603a9b19c1b4",
        })
        self.assertEqual(set(POST_CUTOVER_LOGIC_REVIEWS), {
            "commission_notice_discovery.py", "commission_notice_coverage.py"})
        self.assertEqual(phase4a_cutover_contract()["make_event_id_probes"], {
            "first_round": "ef29af8391fc51e049324a56e953a4fa2bd0436abf49d0ac38f67fb3897c0aed",
            "second_round": "9908b42ab34235bc0b6456e96b237e9f00b9a58fa47ab1821d2a37ed5f019091"})

    def test_cutover_hash_guard_rejects_unreviewed_changes_to_all_protected_files(self):
        from rehearse_fr_poll_migration import ROOT, RehearsalError, phase4a_cutover_contract
        original = Path.read_bytes
        for name in ("commission_notice_discovery.py", "commission_notice_coverage.py", "poll_contract.py"):
            def changed(path, *, target=ROOT / name):
                content = original(path)
                return content + b"\n# unreviewed change\n" if path == target else content
            with self.subTest(file=name), patch.object(Path, "read_bytes", changed):
                with self.assertRaisesRegex(RehearsalError, "protected cutover logic changed"):
                    phase4a_cutover_contract()


class CurrentCommissionCoverageRegressionTests(unittest.TestCase):
    def test_tracked_registry_supports_legacy_and_reconciled_deployment_states(
        self,
    ):
        root = Path(__file__).resolve().parent
        payload = json.loads(
            (root / "commission_notice_registry.json").read_text(
                encoding="utf-8"
            )
        )
        events = json.loads(
            (root / "polls.json").read_text(encoding="utf-8")
        )
        stored = {
            item["notice_id"]: item.get("coverage")
            for item in payload["notices"]
        }

        relevant = [
            item
            for item in payload["notices"]
            if item["classification"] in {"eligible", "unsupported"}
        ]
        if any("coverage" not in item for item in relevant):
            self.assertTrue(
                all("coverage" not in item for item in relevant)
            )
            expected_ids = [item["notice_id"] for item in relevant]
            self.assertEqual(
                coverage_summary(payload),
                {
                    "relevant": len(relevant),
                    "parsed": 0,
                    "reconciled": 0,
                    "unresolved": len(relevant),
                    "unresolved_notice_ids": expected_ids,
                },
            )
            self.assertEqual(
                len(coverage_warnings(payload)),
                len(relevant),
            )
            self.assertEqual(
                {
                    item["notice_id"]: item.get("coverage")
                    for item in payload["notices"]
                },
                stored,
            )
            return

        from poll_migration import load_migration_registry

        audited_locators = {
            record["source_locator"]
            for record in load_migration_registry()["french_additions"]["first_round"]
        }
        commission_evidence = [
            event
            for event in events
            if event.get("migration_source_locator") not in audited_locators
        ]
        stored_summary = coverage_summary(payload)
        summary = reconcile_commission_notices(payload, commission_evidence)
        # Live publication also applies reviewed, exact configuration evidence.
        # Reproduce the deployed layers rather than treating generic matching
        # alone as authoritative for the six mixed-sample Elabe configurations.
        from reviewed_polling_accuracy import reconcile_batch1_notice_coverage

        summary = reconcile_batch1_notice_coverage(payload, events)
        if any(c and c.get("method") == "reviewed_notice_complete_configurations_batch2"
               for c in stored.values()):
            from reviewed_commission_coverage import reconcile_batch2_notice_coverage

            second = json.loads((root / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
            summary = reconcile_batch2_notice_coverage(payload, events + second)

        self.assertEqual(summary, stored_summary)
        self.assertEqual(
            {
                item["notice_id"]: item.get("coverage")
                for item in payload["notices"]
            },
            stored,
        )


if __name__ == "__main__":
    unittest.main()
