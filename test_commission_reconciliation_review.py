"""The 26 October review changes coverage, never the numerical corpus."""

import copy
import gzip
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import commission_notice_coverage as coverage
from reviewed_commission_coverage import load_batch2_review, reconcile_batch2_notice_coverage
from test_commission_notice_coverage import _authenticate_historical_polling_corpus


ROOT = Path(__file__).parent


# Authenticate the full original 173-record post-review registry at
# 920e515ad73714a1b9a2d959e18fc1dc237ee7a6, not today's unrelated-notice digest.
# 714278bac added 10339/10340; 18413e424 added the backdated 10306.
_HISTORICAL_REGISTRY_SHA256 = "a2963a840d0d60adfd232c5af6d63dab970d5ffa2b90c35bf2f61175995243d9"
_REVIEWED_REGISTRY_ADDITIONS = {
    "commission:10306": "ff4b757c3b67165a92a1d9068c754af5e84f9d080bb22017b997c645320670cc",
    "commission:10339": "e93b81651a458882500cf932191deabf96cd13ac9ee4eb09f1a228f6eced2d57",
    "commission:10340": "e6e1e78e047d569b15de8d834e499d77e38df5160f90086be5decd0bbad5954d",
}
_10342_RECORD_SHA256 = "6e636e49c9ecf15cfcd010d055b6adb876581aeb2580d37e71c40d5a407ac1a8"
_10342_REVIEW = ROOT / "fr27_commission_10342_registry_review.json"
_10342_REVIEW_SHA256 = "8ba42efc5005f51107f7f23e641ca60e9bff8be82dafd205ff1a2913bfe7e977"
_HISTORICAL_COVERAGE_SUMMARY = {
    "relevant": 42, "parsed": 3, "reconciled": 34, "unresolved": 5,
    "unresolved_notice_ids": ["commission:10333", "commission:10327", "commission:10319",
                              "commission:10264", "commission:10260"],
}


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate 10342 evidence JSON key: " + key)
        result[key] = value
    return result


def _load_10342_registry_review(path=_10342_REVIEW, *, fixture_root=ROOT):
    """Test-only review: authenticate the review and original PDF bytes offline."""
    review = json.loads(Path(path).read_bytes(), object_pairs_hook=_unique_json_object)
    if coverage._canonical_sha256(review) != _10342_REVIEW_SHA256:
        raise ValueError("10342 registry review changed; explicit review required")
    if coverage._canonical_sha256(review["original_record"]) != _10342_RECORD_SHA256:
        raise ValueError("10342 reviewed original record changed")
    source = review["source_document"]
    if hashlib.sha256((fixture_root / source["fixture"]).read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("10342 original PDF bytes changed")
    return review


def _archival_registry_with_10342():
    """A passing archival control; never substitute old 10339 into production."""
    review = _load_10342_registry_review()
    fixture = review["archival_registry"]
    raw = gzip.decompress((ROOT / fixture["fixture"]).read_bytes())
    if hashlib.sha256(raw).hexdigest() != fixture["uncompressed_sha256"]:
        raise ValueError("10342 archival registry fixture changed")
    archive = json.loads(raw, object_pairs_hook=_unique_json_object)
    if (len(archive["notices"]) != 176
            or coverage._canonical_sha256(archive) != fixture["canonical_sha256"]):
        raise ValueError("10342 archival registry scope changed")
    registry = dict(archive, notices=[review["original_record"], *archive["notices"]])
    _authenticate_registry_baseline(registry)
    return registry


def _authenticate_registry_baseline(registry):
    """Test-only finite review of historical records and four exact additions.

    Full-object pins include classifications, source identities and coverage
    decisions, including the three excluded additions. Unknown records are never
    accepted merely because they leave the headline coverage counts unchanged.
    """
    records = registry["notices"]
    ids = [n["notice_id"] for n in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Commission registry record")
    added = {n["notice_id"]: n for n in records if n["notice_id"] in _REVIEWED_REGISTRY_ADDITIONS}
    if set(added) != set(_REVIEWED_REGISTRY_ADDITIONS):
        raise ValueError("Missing reviewed Commission registry addition")
    for notice_id, expected in _REVIEWED_REGISTRY_ADDITIONS.items():
        if coverage._canonical_sha256(added[notice_id]) != expected:
            raise ValueError("Reviewed Commission registry addition changed: " + notice_id)
    # This separately authenticated extension leaves all three earlier pins intact.
    _load_10342_registry_review()
    extra = [n for n in records if n["notice_id"] == "commission:10342"]
    if not extra:
        raise ValueError("Missing reviewed Commission registry addition: commission:10342")
    if coverage._canonical_sha256(extra[0]) != _10342_RECORD_SHA256:
        raise ValueError("Reviewed Commission registry addition changed: commission:10342")
    added["commission:10342"] = extra[0]
    historical = dict(registry, notices=[n for n in records if n["notice_id"] not in added])
    if len(historical["notices"]) != 173 or coverage._canonical_sha256(historical) != _HISTORICAL_REGISTRY_SHA256:
        raise ValueError("Historical Commission records missing, changed or unexpectedly extended")
    if coverage.coverage_summary(historical) != _HISTORICAL_COVERAGE_SUMMARY:
        raise ValueError("Historical reconciliation decisions changed")
    addition_summary = coverage.coverage_summary({"notices": list(added.values())})
    if addition_summary != {"relevant": 1, "parsed": 0, "reconciled": 1, "unresolved": 0, "unresolved_notice_ids": []}:
        raise ValueError("Reviewed Commission addition coverage changed")
    expected_summary = copy.deepcopy(_HISTORICAL_COVERAGE_SUMMARY)
    for key in ("relevant", "parsed", "reconciled", "unresolved"):
        expected_summary[key] += addition_summary[key]
    return historical, expected_summary


def notice_from(identity):
    notice = copy.deepcopy(identity)
    notice["resolved_url"] = notice.pop("resolved_urls")[0]
    notice.update(classification="unsupported", classification_reason=(
        "document confirms 2027 presidential voting intentions, but no "
        "existing notice parser supports this listing"))
    return notice


class CommissionReconciliationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = coverage.load_notice_reconciliation_review()
        cls.records = {r["notice_id"]: r for r in cls.review["notices"]}
        cls.harris = cls.records["commission:10332"]["published_events"]
        cls.yougov_review = next(r for r in load_batch2_review()["notice_reviews"]
                                if r["notice_identity"]["notice_id"] == "commission:10323")
        cls.yougov = cls.yougov_review["published_events"]

    def reconcile(self, notice_id, *, events=None, mutate_notice=None, generic_events=None):
        record = self.records[notice_id]
        notice = notice_from(record["notice_identity"])
        if mutate_notice:
            mutate_notice(notice)
        payload = {"notices": [notice]}
        if events is None:
            events = self.yougov if notice_id == "commission:10323" else self.harris
        coverage.reconcile_commission_notices(
            payload, events if generic_events is None else generic_events,
            reviewed_events=events,
        )
        if notice_id == "commission:10323":
            reconcile_batch2_notice_coverage(payload, events)
        return notice["coverage"]

    def test_harris_requires_all_five_first_round_and_three_runoff_objects(self):
        self.assertEqual([sum(e["round"] == r for e in self.harris)
                          for r in ("first_round", "second_round")], [5, 3])
        result = self.reconcile("commission:10332")
        self.assertEqual(result, {
            "state": "reconciled", "method": "reviewed_10332_complete_configurations",
            "matched_event_ids": [e["event_id"] for e in self.harris],
        })
        for events in (self.harris[:1], [e for e in self.harris if e["round"] == "first_round"]):
            self.assertEqual(self.reconcile("commission:10332", events=events)["state"], "unresolved")

    def test_harris_complete_corpus_is_separate_from_filtered_generic_evidence(self):
        first = [e for e in self.harris if e["round"] == "first_round"]
        self.assertEqual(self.reconcile("commission:10332", generic_events=first)["state"], "reconciled")
        payload = {"notices": [notice_from(self.records["commission:10332"]["notice_identity"])]}
        coverage.reconcile_commission_notices(payload, first)
        self.assertEqual(payload["notices"][0]["coverage"]["state"], "unresolved")

    def test_every_harris_source_configuration_matches_the_entire_candidate_vector(self):
        from poll_migration import candidate_identity

        events = {e["event_id"]: e for e in self.harris}
        count = 0
        for table in self.records["commission:10332"]["source_configurations"]:
            binding = table["reviewed_event_binding"]
            event = events[binding["event_id"]]
            self.assertEqual(coverage._canonical_sha256(event), binding["event_object_sha256"])
            self.assertEqual({candidate_identity(c["name"]): c["score"] for c in event["candidates"]},
                             {r["identity_id"]: r["result"]["percent"] for r in table["rows"]})
            count += len(table["rows"])
        self.assertEqual(count, 61)

    def test_changed_missing_extra_duplicate_or_reidentified_harris_events_fail_closed(self):
        operations = ("missing", "duplicate", "extra", "identity", "pollster", "start", "end",
                      "score", "candidate", "sample", "scope", "commissioner", "publication",
                      "source", "locator", "round", "official_claim")
        for operation in operations:
            events = copy.deepcopy(self.harris)
            event = events[0]
            if operation == "missing": events.pop()
            elif operation == "duplicate": events.append(copy.deepcopy(event))
            elif operation == "extra": events.append({**copy.deepcopy(event), "event_id": "f" * 64})
            elif operation == "identity": event["event_id"] = "f" * 64
            elif operation == "pollster": event["pollster"] = "Harris Interactive"
            elif operation == "start": event["fieldwork_start"] = "2026-10-18"
            elif operation == "end": event["fieldwork_end"] = "2026-10-22"
            elif operation == "score": event["candidates"][0]["score"] += .5
            elif operation == "candidate": event["candidates"].pop()
            elif operation == "sample": event["sample_size"] += 1
            elif operation == "scope": event["sample_scope"] = "adults"
            elif operation == "commissioner": event["commissioner"] = "M6 & RTL"
            elif operation == "publication": event["publication_date"] = "2026-10-23"
            elif operation == "source": event["source_url"] += "?unreviewed"
            elif operation == "locator": event["migration_source_locator"] += "changed"
            elif operation == "round": event["round"] = "unreviewed"
            else: event["official_notice_id"] = "commission:10332"
            with self.subTest(operation=operation):
                self.assertEqual(self.reconcile("commission:10332", events=events)["state"], "unresolved")

    def test_scoped_review_cannot_authorize_a_different_notice_or_global_alias(self):
        notice = notice_from(self.records["commission:10332"]["notice_identity"])
        notice["notice_id"] = "commission:99999"
        coverage.reconcile_commission_notices({"notices": [notice]}, self.harris)
        self.assertEqual(notice["coverage"]["method"], "no_exact_published_wave")

    def test_both_exact_yougov_identities_require_the_same_eleven_objects(self):
        record = self.records["commission:10323"]
        self.assertEqual(self.yougov_review["notice_identity"], record["historical_notice_identity"])
        self.assertEqual(coverage._canonical_sha256(self.yougov), record["published_collection_sha256"])
        self.assertEqual([sum(e["round"] == r for e in self.yougov)
                          for r in ("first_round", "second_round")], [5, 6])
        for identity in (record["notice_identity"], record["historical_notice_identity"]):
            payload = {"notices": [notice_from(identity)]}
            reconcile_batch2_notice_coverage(payload, self.yougov)
            self.assertEqual(payload["notices"][0]["coverage"], {
                "state": "reconciled", "method": "reviewed_notice_complete_configurations_batch2",
                "matched_event_ids": record["published_event_ids"],
            })
        first = [e for e in self.yougov if e["round"] == "first_round"]
        self.assertEqual(self.reconcile("commission:10323", events=first)["state"], "unresolved")

    def test_current_yougov_identity_drift_or_mixed_variants_still_fail_closed(self):
        historical = self.records["commission:10323"]["historical_notice_identity"]
        changes = {"title": historical["title"], "listed_url": historical["listed_url"],
                   "content_sha256": historical["content_sha256"], "commissioner": "HuffPost",
                   "survey_metadata": {"fieldwork_start": "2026-10-12", "fieldwork_end": "2026-10-15"},
                   "institute": "YOUGOV", "listed_date": "2026-10-19",
                   "resolved_url": "https://example.test/10323.pdf", "confirmed_rounds": ["first_round"]}
        for key, value in changes.items():
            with self.subTest(field=key):
                result = self.reconcile("commission:10323", mutate_notice=lambda n: n.update({key: value}))
                self.assertEqual(result, coverage.unresolved_coverage("reviewed_notice_identity_mismatch"))
        changed = copy.deepcopy(historical)
        changed["title"] += "unreviewed"
        current = notice_from(self.records["commission:10323"]["notice_identity"])
        self.assertFalse(coverage.matches_reviewed_yougov_identity_variant(current, changed))

    def test_yougov_changed_complete_objects_cannot_use_the_identity_variant(self):
        for operation in ("missing", "extra", "duplicate", "score", "sample", "source", "identity", "round"):
            events = copy.deepcopy(self.yougov)
            event = events[0]
            if operation == "missing": events.pop()
            elif operation == "extra": events.append({**copy.deepcopy(event), "event_id": "f" * 64})
            elif operation == "duplicate": events.append(copy.deepcopy(event))
            elif operation == "score": event["candidates"][0]["score"] += .5
            elif operation == "sample": event["sample_size"] += 1
            elif operation == "source": event["source_url"] += "?unreviewed"
            elif operation == "identity": event["event_id"] = "f" * 64
            else: event["round"] = "unreviewed"
            with self.subTest(operation=operation):
                self.assertEqual(self.reconcile("commission:10323", events=events)["method"],
                                 "reviewed_notice_incomplete_or_changed_configurations")

    def test_cnews_veto_precedes_single_wave_optional_metadata_and_direct_claims(self):
        record = self.records["commission:10319"]
        # A single plausible event with the historically misattributed identity.
        event = {"event_id": record["rejected_numerical_event_ids"][0], "pollster": "OpinionWay",
                 "round": "first_round", "fieldwork_start": "2026-10-13",
                 "fieldwork_end": "2026-10-14", "sample_size": 1043,
                 "commissioner": None, "publication_date": None,
                 "source_url": record["incompatible_source"]["url"]}
        for events in ([], [event], [event, {**event, "event_id": "e" * 64}],
                       [{**event, "official_notice_id": "commission:10319"}],
                       [{**event, "round": "second_round"}]):
            with self.subTest(events=events):
                self.assertEqual(self.reconcile("commission:10319", events=events),
                                 coverage.unresolved_coverage("reviewed_cnews_incomplete_bounded_first_round"))
        result = self.reconcile("commission:10319", events=[event], mutate_notice=lambda n:
                                n["survey_metadata"].update(commissioner="CNEWS", sample_size=1043))
        self.assertEqual(result["state"], "unresolved")

    def test_exact_notice_evidence_required_for_scoped_harris_and_cnews(self):
        for notice_id in ("commission:10332", "commission:10319"):
            for key, value in {"title": "changed", "content_sha256": "0" * 64,
                               "institute": "changed", "commissioner": "changed",
                               "resolved_url": "https://example.test/source.pdf",
                               "survey_metadata": None, "confirmed_rounds": []}.items():
                with self.subTest(notice_id=notice_id, field=key):
                    self.assertEqual(self.reconcile(notice_id, mutate_notice=lambda n: n.update({key: value})),
                                     coverage.unresolved_coverage("reviewed_reconciliation_notice_identity_mismatch"))

    def test_no_mutation_idempotence_and_input_order_independence(self):
        for notice_id, events in (("commission:10332", self.harris), ("commission:10323", self.yougov)):
            before = copy.deepcopy(events)
            once = self.reconcile(notice_id, events=events)
            self.assertEqual(once, self.reconcile(notice_id, events=list(reversed(events))))
            self.assertEqual(events, before)

    def test_tampered_review_evidence_cannot_be_repinned_at_runtime(self):
        for field in ("notice_identity", "published_events", "source_configurations"):
            changed = copy.deepcopy(self.review)
            changed["notices"][0][field] = None
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "review.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(coverage.CommissionCoverageError, "explicit review"):
                    coverage.load_notice_reconciliation_review(path)


class CurrentReconciliationIntegrationTests(unittest.TestCase):
    def test_production_layers_reproduce_only_the_three_audited_decisions(self):
        from poll_migration import load_migration_registry
        from reviewed_polling_accuracy import reconcile_batch1_notice_coverage
        from reviewed_composite_rn import reconcile_composite_notice_coverage

        first = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        published = json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))
        _authenticate_historical_polling_corpus(first, second)
        historical, expected_summary = _authenticate_registry_baseline(published)
        historical_notice_ids = {n["notice_id"] for n in historical["notices"]}
        registry = copy.deepcopy(published)
        # Start from the three audited pre-correction states, including the false
        # stored match. Every unrelated notice stays exactly as published.
        old_coverage = {
            "commission:10332": coverage.unresolved_coverage("no_exact_published_wave"),
            "commission:10323": coverage.unresolved_coverage("reviewed_notice_identity_mismatch"),
            "commission:10319": {"state": "reconciled", "method": "exact_pollster_fieldwork_round",
                                 "matched_event_ids": ["7c7bb3a59970c61e70ba91e474b2ed4a6386645d2b258b8d6c3aa9e4f7aecf03"]},
        }
        for notice in registry["notices"]:
            if notice["notice_id"] in old_coverage:
                notice["coverage"] = old_coverage[notice["notice_id"]]
        before_events = copy.deepcopy(first + second)
        locators = {e["source_locator"] for e in load_migration_registry()["french_additions"]["first_round"]}
        generic = [e for e in first if e.get("migration_source_locator") not in locators]
        coverage.reconcile_commission_notices(registry, generic, reviewed_events=first + second)
        reconcile_batch1_notice_coverage(registry, first)
        reconcile_batch2_notice_coverage(registry, first + second)
        summary = reconcile_composite_notice_coverage(registry, first + second)
        self.assertEqual(registry, published)
        self.assertEqual(first + second, before_events)
        unrelated = [{k: n.get(k) for k in ("notice_id", "classification", "coverage")}
                     for n in registry["notices"]
                     if n["notice_id"] in historical_notice_ids
                     and n["notice_id"] not in coverage.RECONCILIATION_NOTICE_IDS]
        # Preserve the original digest over its authenticated historical scope.
        # The four individually pinned additions remain covered by whole-registry
        # equality above, rather than silently entering or weakening this scope.
        self.assertEqual(coverage._canonical_sha256(unrelated),
                         "faf3553ae7b381255f725957595cb5f30d32d24f31367c0447b9a84ee31d1b3b")
        self.assertEqual(summary, expected_summary)

    def test_live_cli_replays_cached_sources_twice_with_all_454_objects_unchanged(self):
        import fetch_polls
        from commission_notice_discovery import DiscoveryResult

        first = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        registry = json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))
        _authenticate_historical_polling_corpus(first, second)
        _, expected_summary = _authenticate_registry_baseline(registry)
        expected_coverage_log = (
            f"{expected_summary['relevant']} relevant ({expected_summary['parsed']} parsed, "
            f"{expected_summary['reconciled']} reconciled, {expected_summary['unresolved']} unresolved)"
        )
        parsed = json.loads(gzip.decompress(
            (ROOT / "test_fixtures/fr27_polling/fr_mediawiki_240570516.json.gz").read_bytes()))
        official = [e for e in first if e.get("official_notice_id")]
        notices = fetch_polls.registry_event_notices(registry)
        counts = {n["notice_id"]: sum(e.get("official_notice_id") == n["notice_id"] for e in official)
                  for n in notices}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            previous_first, previous_second = ROOT / "polls.json", ROOT / "second_round_polls.json"
            for run in (1, 2):
                args = ["fetch_polls.py", "--wikipedia-source", "french",
                        "--previous-first-round", str(previous_first),
                        "--previous-second-round", str(previous_second),
                        "--poll-wave-overrides", str(ROOT / "poll_wave_overrides.json"),
                        "--commission-registry", str(ROOT / "commission_notice_registry.json"),
                        "--commission-registry-output", str(output / "registry.json"),
                        "--output", str(output / "first.json"),
                        "--second-round-output", str(output / "second.json"),
                        "--closest-runoff-output", str(output / "closest.json")]
                stdout = io.StringIO()
                with (patch.object(sys, "argv", args),
                      patch("socket.socket.connect", side_effect=AssertionError("No network in replay")),
                      patch("fetch_polls.discover_registry", return_value=DiscoveryResult(copy.deepcopy(registry), [])),
                      patch("fetch_polls.fetch_official_events", return_value=(copy.deepcopy(official), counts, notices)),
                      patch("rehearse_fr_poll_migration.fetch_live_french_parse", return_value=copy.deepcopy(parsed)),
                      redirect_stdout(stdout)):
                    fetch_polls.main()
                with self.subTest(run=run):
                    self.assertEqual(json.loads((output / "first.json").read_text(encoding="utf-8")), first)
                    self.assertEqual(json.loads((output / "second.json").read_text(encoding="utf-8"))["events"], second)
                    self.assertEqual(json.loads((output / "registry.json").read_text(encoding="utf-8")), registry)
                    self.assertIn(expected_coverage_log, stdout.getvalue())
                previous_first, previous_second = output / "first.json", output / "second.json"

    def test_registry_baseline_rejects_missing_changed_duplicate_and_unexpected_records(self):
        original = _archival_registry_with_10342()
        operations = ("missing_historical", "missing_addition", "duplicate", "unexpected_excluded",
                      "unexpected_relevant", "historical_identity", "addition_identity", "addition_coverage",
                      "excluded_addition", "harris_decision", "yougov_decision", "cnews_decision")
        for operation in operations:
            registry = copy.deepcopy(original)
            records = registry["notices"]
            historical = next(n for n in records if n["notice_id"] not in _REVIEWED_REGISTRY_ADDITIONS
                              and n["notice_id"] != "commission:10342")
            by_id = {n["notice_id"]: n for n in records}
            if operation == "missing_historical": records.remove(historical)
            elif operation == "missing_addition": records.remove(by_id["commission:10306"])
            elif operation == "duplicate": records.append(copy.deepcopy(historical))
            elif operation in ("unexpected_excluded", "unexpected_relevant"):
                template = by_id["commission:10306" if operation == "unexpected_excluded" else "commission:10339"]
                records.append(dict(template, notice_id="commission:99999"))
            elif operation == "historical_identity": historical["listed_url"] += "?unreviewed"
            elif operation == "addition_identity": by_id["commission:10339"]["content_sha256"] = "0" * 64
            elif operation == "addition_coverage": by_id["commission:10339"]["coverage"]["matched_event_ids"] = []
            elif operation == "excluded_addition": by_id["commission:10340"]["classification"] = "unsupported"
            else:
                notice_id = {"harris_decision": "commission:10332", "yougov_decision": "commission:10323",
                             "cnews_decision": "commission:10319"}[operation]
                by_id[notice_id]["coverage"]["method"] = "unreviewed_decision"
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                _authenticate_registry_baseline(registry)

    def test_registry_baseline_authenticates_original_scope_and_exact_reviewed_delta_without_mutation(self):
        registry = json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))
        before = copy.deepcopy(registry)
        historical, summary = _authenticate_registry_baseline(registry)
        self.assertEqual(len(historical["notices"]), 173)
        self.assertEqual(coverage.coverage_summary(historical), _HISTORICAL_COVERAGE_SUMMARY)
        self.assertEqual((summary["relevant"], summary["reconciled"]), (43, 35))
        self.assertEqual(summary["unresolved_notice_ids"], _HISTORICAL_COVERAGE_SUMMARY["unresolved_notice_ids"])
        self.assertEqual(coverage.coverage_summary(registry), summary)
        self.assertEqual(registry, before)


if __name__ == "__main__":
    unittest.main()
