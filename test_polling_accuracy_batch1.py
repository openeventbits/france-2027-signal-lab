"""Original-report evidence, bounded changes, and recurring ingestion for Batch 1."""

import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fetch_polls import integrate_french_migration_source, validate_second_round_event
from poll_contract import make_event_id, validate_poll_events
from poll_migration import candidate_identity, parse_french_frozen_fixture
from reviewed_polling_accuracy import (
    REVIEWED_SOURCE_REVISION, load_batch1_review, reconcile_batch1_accuracy, reconcile_batch1_notice_coverage,
)

ROOT = Path(__file__).parent
FIXTURES = ROOT / "test_fixtures/fr27_polling"


def scores(event):
    return {candidate["name"]: candidate["score"] for candidate in event["candidates"]}


class PollingAccuracyBatch1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def frozen(name, digest):
            raw = gzip.decompress((FIXTURES / name).read_bytes())
            if hashlib.sha256(raw).hexdigest() != digest:
                raise AssertionError("Batch 1 frozen evidence changed")
            return json.loads(raw)
        cls.before = frozen("batch1_pre_review_333_102.json.gz",
                            "6efe0b77fa65088fdbb58760f261218a91475769f3f37c8b67ea3583371b1c80")
        cls.parsed = frozen("fr_mediawiki_240562307.json.gz",
                            "fa24cbe57e09b9f8ee2fe48971b7fb3c784838d88c851953c5d3e8751d629832")
        cls.rows = parse_french_frozen_fixture(cls.parsed, allow_reviewed_polony=True)
        cls.review = load_batch1_review()
        cls.evidence = json.loads((FIXTURES / "batch1_original_tables.json").read_text(encoding="utf-8"))
        cls.first, cls.second, cls.report, _ = cls.integrate()

    @classmethod
    def integrate(cls, first=None, second=None):
        f = cls.before["first_round"] if first is None else first
        s = cls.before["second_round"] if second is None else second
        return integrate_french_migration_source(
            cls.parsed, f, s,
            [e for e in cls.before["first_round"] if e.get("official_notice_id")],
            retain_published_history=True,
        )

    def apply(self, rows=None, first=None, second=None, revision=REVIEWED_SOURCE_REVISION):
        return reconcile_batch1_accuracy(
            self.rows if rows is None else rows, revision,
            self.before["first_round"] if first is None else first,
            self.before["second_round"] if second is None else second,
            retain_published_history=True,
        )

    def test_only_reviewed_decisions_change_objects(self):
        self.assertEqual((len(self.first), len(self.second)), (335, 102))
        permitted = {r["previous_event"]["event_id"] for r in self.review["decisions"] if r["previous_event"]}
        after = {e["event_id"]: e for e in self.first + self.second}
        before = self.before["first_round"] + self.before["second_round"]
        for event in before:
            if event["event_id"] not in permitted:
                self.assertEqual(event, after[event["event_id"]])
        self.assertEqual(sum(e["event_id"] not in permitted for e in before), 428)
        self.assertEqual(self.report["unexplained_historical_losses"], 0)

    def test_all_six_elabe_lineups_and_scores_match_original_notice(self):
        wave = [e for e in self.first if e["pollster"] == "Elabe" and e["fieldwork_start"] == "2026-10-14"]
        self.assertEqual(len(wave), 6)
        self.assertCountEqual([scores(e) for e in wave], [scores(e) for e in self.evidence["elabe"]])
        self.assertTrue(all(e["reported_total"] == 100 for e in wave))
        record = self.review["decisions"][0]
        self.assertEqual(record["previous_event"]["event_id"], record["canonical_event"]["event_id"])
        self.assertEqual(record["canonical_event"]["reviewed_correction_id"], "FR27-B1-A")

    def test_all_eight_ifop_lineups_and_scores_match_original_tables(self):
        wave = [e for e in self.first if e["pollster"] == "Ifop" and e["fieldwork_start"] == "2026-10-17"]
        self.assertEqual(len(wave), 8)
        self.assertCountEqual([set(scores(e)) for e in wave], [set(scores(e)) for e in self.evidence["ifop"]])
        conflicts = []
        for original in self.evidence["ifop"]:
            current = next(e for e in wave if scores(e).keys() == scores(original).keys())
            for name, score in scores(original).items():
                if scores(current)[name] != score:
                    conflicts.append((original["configuration"], name, score, scores(current)[name]))
        self.assertEqual(conflicts, [])
        new = next(e for e in wave if "Natacha Polony" in scores(e))
        self.assertEqual(scores(new), scores(self.evidence["ifop"][7]))
        self.assertEqual((new["sample_size"], new["sample_scope"]), (1928, "registered_voters"))

    def test_new_elabe_sample_is_registered_not_adult_or_expressed_base(self):
        event = next(e for e in self.first if e.get("reviewed_correction_id") == "FR27-B1-B")
        self.assertEqual((event["sample_size"], event["sample_scope"]), (1553, "registered_voters"))
        self.assertEqual(scores(event)["Natacha Polony"], 1.5)

    def test_five_runoff_supersessions_preserve_matchups_and_exact_identity(self):
        after = {e["event_id"]: e for e in self.second}
        records = [r for r in self.review["decisions"] if r["action"] == "supersede_runoff_metadata"]
        self.assertEqual(len(records), 5)
        for record in records:
            old, event = record["previous_event"], record["canonical_event"]
            self.assertNotIn(old["event_id"], after)
            self.assertEqual(after[event["event_id"]], event)
            self.assertEqual(event["supersedes_event_id"], old["event_id"])
            self.assertEqual(event["matchup_key"], old["matchup_key"])
            self.assertEqual(scores(event), scores(old))
            self.assertEqual((event["fieldwork_start"], event["fieldwork_end"], event["sample_size"], event["sample_scope"]),
                             ("2026-10-17", "2026-10-19", 1928, "registered_voters"))
            validate_second_round_event(event)
        self.assertCountEqual(self.report["superseded_second_round_event_ids"],
                              [r["previous_event"]["event_id"] for r in records])

    def test_repeat_integration_is_object_identical_and_inputs_unchanged(self):
        f, s = copy.deepcopy(self.first), copy.deepcopy(self.second)
        repeated = self.integrate(f, s)
        self.assertEqual(repeated[:2], (self.first, self.second))
        self.assertEqual((f, s), (self.first, self.second))
        self.assertEqual(repeated[2]["polling_accuracy_batch1"]["already_applied"], 9)
        self.assertEqual(repeated[2]["superseded_second_round_event_ids"], [])

    def test_reviewed_source_facts_cannot_be_reversed_or_duplicated(self):
        for round_name, decision in (("first_round", "FR27-B1-A"), ("second_round", "FR27-B1-D-Gabriel Attal")):
            with self.subTest(round=round_name):
                rows = copy.deepcopy(self.rows)
                event = next(r["previous_event"] for r in self.review["decisions"] if r["decision_id"] == decision)
                row = next(r for r in rows[round_name] if scores(r) == scores(event) and r["fieldwork_start"] == event["fieldwork_start"])
                row["candidates"][0]["score"] += .25
                with self.assertRaisesRegex(ValueError, "source facts/provenance changed"):
                    self.apply(rows, self.first, self.second)
                rows = copy.deepcopy(self.rows)
                row = next(r for r in rows[round_name] if scores(r) == scores(event) and r["fieldwork_start"] == event["fieldwork_start"])
                rows[round_name].append({**row, "source_locator": "duplicate-reviewed"})
                with self.assertRaisesRegex(ValueError, "duplicate source representations"):
                    self.apply(rows)

    def test_missing_discovery_rows_and_older_snapshot_cannot_undo_review(self):
        rows = copy.deepcopy(self.rows)
        rows["first_round"] = []
        rows["second_round"] = []
        # This narrow unit helper does not replace the global extraction guard.
        result = self.apply(rows, self.first, self.second, revision=240522402)
        self.assertEqual(result.first_round, self.first)
        self.assertEqual(result.second_round, self.second)

    def test_frozen_historical_replay_does_not_activate_batch(self):
        result = self.apply(revision=240522402)
        self.assertEqual(result.first_round, self.before["first_round"])
        self.assertEqual(result.second_round, self.before["second_round"])
        self.assertEqual(result.handled, {})

    def test_corrected_discovery_adopts_no_second_identity(self):
        rows = copy.deepcopy(self.rows)
        for record in self.review["decisions"]:
            event = record["canonical_event"]
            round_name = event["round"]
            names = set(scores(event))
            row = next((r for r in rows[round_name] if r["pollster"] == event["pollster"]
                        and r["fieldwork_start"] == event["fieldwork_start"]
                        and set(scores(r)) == names), None)
            replacement = {k: copy.deepcopy(event[k]) for k in (
                "round", "pollster", "fieldwork_start", "fieldwork_end", "sample_size",
                "sample_scope", "candidates", "source_url",
            )}
            replacement["source_locator"] = row["source_locator"] if row else "official-ifop-polony"
            replacement["candidates"].reverse()
            if row:
                rows[round_name].remove(row)
            rows[round_name].append(replacement)
        with patch("rehearse_fr_poll_migration._assert_production_source_structure", return_value=rows):
            result = self.integrate(self.first, self.second)
        self.assertEqual(result[:2], (self.first, self.second))

    def test_full_integration_of_older_discovery_preserves_published_review(self):
        parsed = json.loads(gzip.decompress((FIXTURES / "fr_mediawiki_240522402.json.gz").read_bytes()))
        result = integrate_french_migration_source(
            parsed, self.first, self.second,
            [e for e in self.before["first_round"] if e.get("official_notice_id")],
            retain_published_history=True,
        )
        self.assertEqual(result[:2], (self.first, self.second))

    def test_missing_tampered_and_double_persisted_predecessors_fail_closed(self):
        old = next(r["previous_event"] for r in self.review["decisions"] if r["action"] == "supersede_runoff_metadata")
        for operation in ("remove", "mutate", "both"):
            second = copy.deepcopy(self.before["second_round"])
            current = next(e for e in second if e["event_id"] == old["event_id"])
            if operation == "remove": second.remove(current)
            if operation == "mutate": current["commissioner"] = "unexpected"
            if operation == "both":
                second.append(copy.deepcopy(next(r["canonical_event"] for r in self.review["decisions"] if r["previous_event"] == old)))
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.apply(second=second)

    def test_admission_identity_collision_is_rejected(self):
        first = copy.deepcopy(self.before["first_round"])
        event = copy.deepcopy(self.review["decisions"][1]["canonical_event"])
        event["source_url"] = "https://example.test/duplicate"
        event["event_id"] = make_event_id(event["pollster"],event["fieldwork_start"],event["fieldwork_end"],event["hypothesis"],event["source_url"])
        first.append(event)
        with self.assertRaisesRegex(ValueError, "identity collision"):
            self.apply(first=first)

    def test_registry_changes_require_explicit_review(self):
        payload = copy.deepcopy(self.review)
        payload["decisions"][1]["canonical_event"]["candidates"][0]["score"] = 9
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "review.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicit review required"):
                load_batch1_review(path)

    def test_candidate_mapping_does_not_declare_candidacy(self):
        self.assertEqual(candidate_identity("Polony"), "natacha-polony")
        self.assertEqual(candidate_identity("Natacha Polony"), "natacha-polony")
        # The candidacy source already contains Polony independently. This
        # review cannot infer or overwrite a declaration from a poll option.
        for record in self.review["decisions"]:
            self.assertFalse({"candidacy_status", "declared", "status"} & set(record["canonical_event"]))
        validate_poll_events(self.first)

    def test_hollande_score_review_changes_only_the_authorized_fields(self):
        record = next(r for r in self.review["decisions"] if r["decision_id"] == "FR27-B1-E")
        old, corrected = record["previous_event"], record["canonical_event"]
        event_id = "9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f"
        self.assertEqual(old, next(e for e in self.before["first_round"] if e["event_id"] == event_id))
        self.assertEqual(corrected["event_id"], event_id)
        self.assertEqual(scores(corrected), scores(self.evidence["ifop"][4]))
        self.assertEqual(corrected["reported_total"], 100)
        changed = {k for k in set(old) | set(corrected) if old.get(k) != corrected.get(k)}
        self.assertEqual(changed, {"candidates", "reported_total", "reviewed_correction_id"})
        self.assertEqual({k: v for k, v in scores(old).items() if k != "Nicolas Dupont-Aignan"},
                         {k: v for k, v in scores(corrected).items() if k != "Nicolas Dupont-Aignan"})
        self.assertEqual((scores(old)["Nicolas Dupont-Aignan"], scores(corrected)["Nicolas Dupont-Aignan"]), (2.5, 2))
        prior_batch = [copy.deepcopy(old if e["event_id"] == event_id else e) for e in self.first]
        result = self.apply(first=prior_batch, second=self.second)
        self.assertEqual({e["event_id"]: e for e in result.first_round}, {e["event_id"]: e for e in self.first})
        self.assertEqual(result.second_round, self.second)
        self.assertEqual(result.report["applied"], 1)
        self.assertEqual(result.report["already_applied"], 8)

    def test_hollande_old_and_corrected_discovery_cannot_reverse_the_review(self):
        record = next(r for r in self.review["decisions"] if r["decision_id"] == "FR27-B1-E")
        for corrected in (False, True):
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows["first_round"] if scores(r) == scores(record["previous_event"])
                       and r["fieldwork_start"] == "2026-10-17")
            if corrected:
                row["candidates"] = copy.deepcopy(record["canonical_event"]["candidates"])
            result = self.apply(rows, self.first, self.second)
            self.assertEqual(result.first_round, self.first)
            self.assertEqual(result.report["already_applied"], 9)

    @classmethod
    def coverage(cls, *, events=None, notice=None):
        from commission_notice_coverage import reconcile_commission_notices
        registry = json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))
        if notice is not None:
            registry["notices"] = [notice if n["notice_id"] == "commission:10324" else n for n in registry["notices"]]
        published = cls.first if events is None else events
        reconcile_commission_notices(registry, published)
        ordinary = copy.deepcopy(registry)
        summary = reconcile_batch1_notice_coverage(registry, published)
        target = next(n for n in registry["notices"] if n["notice_id"] == "commission:10324")
        return target, registry, ordinary, summary

    def test_10324_requires_all_six_exact_reviewed_objects_and_no_sample_edits(self):
        before = copy.deepcopy(self.first)
        target, registry, ordinary, summary = self.coverage()
        expected = self.review["notice_coverage_reviews"][0]["configurations"]
        self.assertEqual(target["coverage"], {
            "state": "reconciled", "method": "reviewed_notice_complete_configurations",
            "matched_event_ids": [e["event_id"] for e in expected],
        })
        from commission_notice_coverage import coverage_summary
        self.assertEqual(summary["unresolved"], coverage_summary(ordinary)["unresolved"] - 1)
        self.assertEqual(self.first, before)
        for old, new in zip(ordinary["notices"], registry["notices"]):
            if old["notice_id"] != "commission:10324":
                self.assertEqual(old, new)
        repeated = copy.deepcopy(registry)
        self.assertEqual(reconcile_batch1_notice_coverage(repeated, self.first), summary)
        self.assertEqual(repeated, registry)

    def test_10324_incomplete_mutated_duplicate_and_extra_configurations_fail_closed(self):
        elabe = self.review["notice_coverage_reviews"][0]["configurations"]
        for operation in ("missing", "duplicate", "score", "sample", "scope", "source", "lineage", "extra"):
            events = copy.deepcopy(self.first)
            event = next(e for e in events if e["event_id"] == elabe[0]["event_id"])
            if operation == "missing": events.remove(event)
            if operation == "duplicate": events.append(copy.deepcopy(event))
            if operation == "score": event["candidates"][0]["score"] += .5
            if operation == "sample": event["sample_size"] = 1553
            if operation == "scope": event["sample_scope"] = "registered_voters"
            if operation == "source": event["source_url"] = "https://example.test/other-survey"
            if operation == "lineage": event["reviewed_correction_id"] = "unexpected"
            if operation == "extra":
                extra = copy.deepcopy(event)
                extra["event_id"] = "f" * 64
                extra["pollster"] = "ELABE"
                events.append(extra)
            with self.subTest(operation=operation):
                target, *_ = self.coverage(events=events)
                self.assertEqual(target["coverage"]["state"], "unresolved")
                self.assertEqual(target["coverage"]["matched_event_ids"], [])

    def test_10324_identity_changes_and_other_notice_ids_cannot_authorize_coverage(self):
        original = next(n for n in json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))["notices"]
                        if n["notice_id"] == "commission:10324")
        for field, value in (("content_sha256", "0" * 64), ("resolved_url", "https://example.test/10324.pdf"),
                             ("institute", "Ifop"), ("listed_date", "2026-10-18"), ("confirmed_rounds", ["second_round"])):
            notice = copy.deepcopy(original)
            notice[field] = value
            with self.subTest(field=field):
                target, *_ = self.coverage(notice=notice)
                self.assertEqual(target["coverage"]["state"], "unresolved")
        notice = copy.deepcopy(original)
        notice["survey_metadata"]["fieldwork_end"] = "2026-10-17"
        self.assertEqual(self.coverage(notice=notice)[0]["coverage"]["state"], "unresolved")
        notice = copy.deepcopy(original)
        notice["notice_id"] = "commission:99999"
        registry = {"notices": [notice]}
        before = copy.deepcopy(registry)
        reconcile_batch1_notice_coverage(registry, self.first)
        self.assertEqual(registry, before)

    def test_10324_pre_review_snapshot_keeps_generic_coverage_unchanged(self):
        from commission_notice_coverage import reconcile_commission_notices
        registry = json.loads((ROOT / "commission_notice_registry.json").read_text(encoding="utf-8"))
        reconcile_commission_notices(registry, self.before["first_round"])
        before = copy.deepcopy(registry)
        reconcile_batch1_notice_coverage(registry, self.before["first_round"])
        self.assertEqual(registry, before)


if __name__ == "__main__":
    unittest.main()
