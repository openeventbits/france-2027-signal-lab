"""Recurring ingestion must preserve history without relaxing frozen replay."""

import copy
import gzip
import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fetch_polls import (
    integrate_french_migration_source, print_french_reconciliation_diagnostics,
)
from poll_contract import apply_completeness_contract, make_event_id
from poll_migration import exact_factual_key, parse_french_frozen_fixture
from rehearse_fr_poll_migration import reconcile_french_production_source


ROOT = Path(__file__).parent
FIXTURES = ROOT / "test_fixtures/fr27_polling"
REVISIONS = (240490172, 240498648, 240522402)
SOURCE_DIGESTS = (
    "8a54b5cd57cb80f99095e5b9dc71074ef31de560b2a7df3511cf545ab999f78c",
    "4ca4844c43c42ff6189bcac56fa24d2a338b84d835c81b6bbf14f722a4439574",
    "f57800b676667bb2b812f749b530ec3675c0db78ea071fd95078460e0f3a6a56",
)


class PollIngestionStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        published = json.loads(gzip.decompress(
            (FIXTURES / "phase1_published_326_97.json.gz").read_bytes()
        ))
        cls.first = published["first_round"]
        cls.second = published["second_round"]
        cls.official = [event for event in cls.first if event.get("official_notice_id")]
        cls.sources = {}
        cls.rows = {}
        for revision, digest in zip(REVISIONS, SOURCE_DIGESTS):
            raw = gzip.decompress((FIXTURES / f"fr_mediawiki_{revision}.json.gz").read_bytes())
            if hashlib.sha256(raw).hexdigest() != digest:
                raise AssertionError("archived source bytes changed")
            parsed = json.loads(raw)
            if parsed["revid"] != revision:
                raise AssertionError("archived source revision changed")
            cls.sources[revision] = parsed
            cls.rows[revision] = parse_french_frozen_fixture(parsed)

    def integrate(self, revision=240522402, *, rows=None, first=None, second=None, official=None):
        arguments = (
            self.sources[revision],
            copy.deepcopy(self.first if first is None else first),
            copy.deepcopy(self.second if second is None else second),
            copy.deepcopy(self.official if official is None else official),
        )
        if rows is None:
            return integrate_french_migration_source(*arguments, retain_published_history=True)
        with patch("rehearse_fr_poll_migration._assert_production_source_structure", return_value=rows):
            return integrate_french_migration_source(*arguments, retain_published_history=True)

    def assert_history(self, first, second):
        self.assertEqual({e["event_id"]: e for e in first},
                         {e["event_id"]: e for e in self.first})
        self.assertEqual({e["event_id"]: e for e in second},
                         {e["event_id"]: e for e in self.second})

    def test_all_three_archived_revisions_preserve_complete_objects_and_repeat(self):
        self.assertEqual((len(self.first), len(self.second)), (326, 97))
        for revision in REVISIONS:
            with self.subTest(revision=revision):
                first, second, report, _ = self.integrate(revision)
                self.assert_history(first, second)
                self.assertEqual((first, second), (self.first, self.second))
                repeated = self.integrate(revision, first=first, second=second)
                self.assertEqual((first, second), repeated[:2])
                self.assertEqual(report["superseded_second_round_event_ids"], [])

    def test_archives_prove_all_28_movements_and_five_link_changes(self):
        def index(revision):
            return {exact_factual_key(row, sample_scope="reported"): row
                    for row in self.rows[revision]["first_round"]}
        before, after = index(240490172), index(240498648)
        self.assertEqual(before.keys(), after.keys())
        self.assertEqual(sum(before[k]["source_locator"] != after[k]["source_locator"] for k in before), 28)
        self.assertEqual(sum(before[k]["source_url"] != after[k]["source_url"] for k in before), 5)
        reviewed = next(row for row in before.values() if row["source_locator"] == "FR-T0R5")
        self.assertEqual(after[exact_factual_key(reviewed, sample_scope="reported")]["source_locator"], "FR-T0R6")

    def test_frozen_replay_remains_revision_specific(self):
        with self.assertRaisesRegex(ValueError, "source facts/provenance changed: FR-T0R5"):
            reconcile_french_production_source(self.sources[240498648], self.first, self.second)

    def test_candidate_order_and_positions_do_not_rewrite_history(self):
        rows = copy.deepcopy(self.rows[240522402])
        for round_name in ("first_round", "second_round"):
            rows[round_name].reverse()
            for i, row in enumerate(rows[round_name]):
                row["source_locator"] = f"discovery-{round_name}-{i}"
                row["candidates"].reverse()
        self.assert_history(*self.integrate(rows=rows)[:2])

    def test_missing_accepted_and_rejected_rows_retain_validated_history(self):
        rows = copy.deepcopy(self.rows[240522402])
        # Includes the reviewed Elabe successor and all siblings, a sample
        # correction wave, and a reviewed runoff successor.
        rows["first_round"] = [r for r in rows["first_round"]
                               if r["fieldwork_end"] not in {"2026-10-16", "2026-09-29"}]
        rows["second_round"] = rows["second_round"][1:]
        rows["rejected"] = []
        self.assert_history(*self.integrate(rows=rows)[:2])

    @staticmethod
    def diagnostics(report):
        output = io.StringIO()
        with redirect_stdout(output):
            print_french_reconciliation_diagnostics(report)
        return output.getvalue()

    def test_normal_extraction_reports_both_rounds_without_warning(self):
        first, second, report, _ = self.integrate()
        self.assert_history(first, second)
        self.assertEqual(report["extraction_coverage"], {
            "first_round": {"extracted": 284, "expected_baseline": 284,
                            "guard_baseline": 282, "shortfall": 0},
            "second_round": {"extracted": 95, "expected_baseline": 95,
                             "guard_baseline": 95, "shortfall": 0},
        })
        output = self.diagnostics(report)
        self.assertIn("French first-round extraction coverage: 284 extracted", output)
        self.assertIn("French runoff extraction coverage: 95 extracted", output)
        self.assertNotIn("WARNING:", output)

    def test_missing_elabe_wave_warns_without_changing_published_objects(self):
        rows = copy.deepcopy(self.rows[240522402])
        rows["first_round"] = [r for r in rows["first_round"] if not (
            r["pollster"] == "Elabe" and r["fieldwork_start"] == "2026-10-14"
            and r["fieldwork_end"] == "2026-10-16"
        )]
        self.assertEqual(len(rows["first_round"]), 279)
        first, second, report, _ = self.integrate(rows=rows)
        self.assertEqual((json.dumps(first), json.dumps(second)),
                         (json.dumps(self.first), json.dumps(self.second)))
        self.assertEqual(report["extraction_coverage"]["first_round"], {
            "extracted": 279, "expected_baseline": 284,
            "guard_baseline": 282, "shortfall": 5,
        })
        output = self.diagnostics(report)
        self.assertIn("WARNING: French first-round extraction coverage: 279 extracted "
                      "against expected baseline 284; shortfall 5", output)
        self.assertNotIn("WARNING: French runoff", output)

    def test_runoff_shortfall_is_reported_independently(self):
        rows = copy.deepcopy(self.rows[240522402])
        rows["second_round"] = rows["second_round"][1:]
        first, second, report, _ = self.integrate(rows=rows)
        self.assert_history(first, second)
        output = self.diagnostics(report)
        self.assertIn("WARNING: French runoff extraction coverage: 94 extracted "
                      "against expected baseline 95; shortfall 1", output)
        self.assertNotIn("WARNING: French first-round", output)

    def test_widespread_loss_still_stops_each_round(self):
        for round_name in ("first_round", "second_round"):
            rows = copy.deepcopy(self.rows[240522402])
            rows[round_name] = rows[round_name][:len(rows[round_name]) // 2]
            with self.subTest(round=round_name), self.assertRaisesRegex(ValueError, "extraction loss"):
                self.integrate(rows=rows)

    def test_original_90_percent_guard_boundaries_are_unchanged(self):
        for round_name, minimum in (("first_round", 254), ("second_round", 86)):
            rows = copy.deepcopy(self.rows[240522402])
            rows[round_name] = rows[round_name][:minimum]
            with self.subTest(round=round_name):
                self.assert_history(*self.integrate(rows=rows)[:2])
                rows[round_name].pop()
                with self.assertRaisesRegex(ValueError, "extraction loss"):
                    self.integrate(rows=rows)

    def test_malformed_structure_still_stops(self):
        parsed = {**self.sources[240522402], "text": "<html><h2>Changed</h2></html>"}
        with self.assertRaisesRegex(ValueError, "structural validation failed"):
            integrate_french_migration_source(parsed, self.first, self.second, [], retain_published_history=True)

    def test_duplicate_incoming_facts_are_ambiguous(self):
        rows = copy.deepcopy(self.rows[240522402])
        duplicate = copy.deepcopy(rows["first_round"][0])
        duplicate["source_locator"] = "another-position"
        rows["first_round"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate factual row|[Aa]mbiguous"):
            self.integrate(rows=rows)

    def test_ambiguous_prior_identity_still_stops(self):
        duplicate = copy.deepcopy(self.first[0])
        duplicate["source_url"] = "https://example.test/another-source"
        duplicate["event_id"] = make_event_id(
            duplicate["pollster"], duplicate["fieldwork_start"], duplicate["fieldwork_end"],
            duplicate["hypothesis"], duplicate["source_url"],
        )
        with self.assertRaisesRegex(ValueError, "multiple prior events"):
            self.integrate(first=self.first + [duplicate])

    def test_official_same_id_cannot_change_any_published_content(self):
        def scores(event):
            event["candidates"][0]["score"] += 0.5
            event["candidates"][1]["score"] -= 0.5
            apply_completeness_contract(event)
        mutations = (
            scores,
            lambda e: e.update(sample_size=e["sample_size"] + 1),
            lambda e: e.update(sample_scope="survey_respondents"),
            lambda e: e.update(population="different population"),
            lambda e: e.update(commissioner="Different commissioner"),
            lambda e: e.update(source_url="https://example.test/changed-provenance"),
            lambda e: e["candidates"].reverse(),
        )
        # Isolate the merge boundary; the real reconciliation result is also
        # covered by the archived replays above.
        from rehearse_fr_poll_migration import RehearsalResult
        report = {"post_audit_first_round_corrections": {
            "canonical_event_ids": [], "superseded_event_ids": [],
        }}
        for mutate in mutations:
            official = copy.deepcopy(self.official)
            mutate(official[0])
            with self.subTest(mutation=mutate), patch(
                "rehearse_fr_poll_migration.reconcile_french_production_source",
                return_value=RehearsalResult(copy.deepcopy(self.first), copy.deepcopy(self.second), report),
            ), self.assertRaisesRegex(ValueError, "changed a published event"):
                self.integrate(official=official)

    def test_equal_official_observation_retains_original_serialized_object(self):
        official = copy.deepcopy(self.official)
        event = official[0]
        event["candidates"][0]["score"] = int(event["candidates"][0]["score"])
        official[0] = dict(reversed(list(event.items())))
        first, _, _, _ = self.integrate(official=official)
        retained = next(e for e in first if e["event_id"] == event["event_id"])
        original = next(e for e in self.first if e["event_id"] == event["event_id"])
        self.assertEqual(json.dumps(retained), json.dumps(original))

    def test_changed_source_scores_samples_and_candidate_truncation_stop(self):
        for mutation in ("score", "sample", "scope", "candidate"):
            rows = copy.deepcopy(self.rows[240522402])
            row = rows["first_round"][0]
            if mutation == "score":
                row["candidates"][0]["score"] += 0.5
            elif mutation == "sample":
                row["sample_size"] += 1
            elif mutation == "scope":
                row["sample_scope"] = "survey_respondents"
            else:
                row["candidates"].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.integrate(rows=rows)

    def test_truncation_of_reviewed_source_with_different_sample_base_stops(self):
        rows = copy.deepcopy(self.rows[240522402])
        row = next(r for r in rows["first_round"]
                   if r["pollster"] == "Elabe" and r["fieldwork_end"] == "2025-10-31"
                   and r["sample_size"] == 1396)
        # This source representation maps to published sample 1501. Comparing
        # only the published base previously let the truncated row add event 327.
        row["candidates"].pop()
        with self.assertRaisesRegex(ValueError, "retained candidate facts"):
            self.integrate(rows=rows)

    def test_missing_registered_successor_still_stops(self):
        canonical_id = "63aecb7f3bd59f50845e47dc628ed7d480330d1a028228561ad2cc6a3bb1afb0"
        with self.assertRaisesRegex(ValueError, "neither historical nor successor"):
            self.integrate(first=[e for e in self.first if e["event_id"] != canonical_id])

    def test_registered_expansions_still_apply_and_supersede_only_reviewed_ids(self):
        previous = json.loads((FIXTURES / "pre_candidate_expansion_first_round_23a2bbd.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "fr27_reviewed_candidate_expansions.json").read_text(encoding="utf-8"))
        old_ids = {r["previous_event"]["event_id"] for r in registry["expansions"]}
        new_ids = {r["canonical_event_id"] for r in registry["expansions"]}
        first, second, report, _ = self.integrate(first=previous)
        by_id = {e["event_id"]: e for e in first}
        self.assertFalse(old_ids & by_id.keys())
        self.assertTrue(new_ids <= by_id.keys())
        self.assertTrue(all(by_id[e["event_id"]] == e for e in previous if e["event_id"] not in old_ids))
        self.assertEqual(set(report["post_audit_first_round_corrections"]["superseded_event_ids"]), old_ids)
        self.assertEqual(self.integrate(first=first, second=second)[:2], (first, second))

    def test_genuine_new_wave_is_admitted_once_without_touching_history(self):
        rows = copy.deepcopy(self.rows[240522402])
        new = copy.deepcopy(rows["first_round"][0])
        new.update(source_locator="new-discovery", fieldwork_start="2026-10-18", fieldwork_end="2026-10-19")
        rows["first_round"].append(new)
        first, second, _, _ = self.integrate(rows=rows)
        by_id = {e["event_id"]: e for e in first}
        self.assertEqual(len(first), 327)
        self.assertTrue(all(by_id[e["event_id"]] == e for e in self.first))
        self.assertEqual(second, self.second)
        self.assertEqual(self.integrate(rows=rows, first=first, second=second)[:2], (first, second))

    def test_scheduled_entry_point_enables_retention_but_fixture_replay_does_not(self):
        source = (ROOT / "fetch_polls.py").read_text(encoding="utf-8")
        self.assertIn("retain_published_history=not bool(args.french_fixture)", source)
        workflow = (ROOT / ".github/workflows/update-polls.yml").read_text(encoding="utf-8")
        self.assertIn("test_poll_ingestion_stability.py", workflow)


if __name__ == "__main__":
    unittest.main()
