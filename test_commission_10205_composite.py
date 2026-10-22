"""Original-table accuracy, exact supersessions and non-person attribution."""

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from build_candidate_signals import (
    build_poll_packages, project_candidate_poll_history, project_candidate_polling,
)
from build_poll_explorer import build_poll_explorer
from build_poll_pages import candidate_variation_rows, render_scenario
from candidate_identity import candidate_id
from fetch_polls import integrate_french_migration_source
from poll_ballot_labels import RN_CONDITIONAL_OPTION, RN_CONDITIONAL_DISPLAY_NAMES
from poll_contract import make_event_id, make_scenario_key, validate_poll_events
from poll_migration import candidate_identity, parse_french_frozen_fixture
from reviewed_composite_rn import (
    load_composite_review, reconcile_composite_notice_coverage, reconcile_composite_rn,
)

ROOT = Path(__file__).parent
FIXTURES = ROOT / "test_fixtures/fr27_polling"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fixture(revision):
    path = FIXTURES / f"fr_mediawiki_{revision}.json.gz"
    return json.loads(gzip.decompress(path.read_bytes()))


class CompositeRnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = load_composite_review()
        cls.first = read(ROOT / "polls.json")
        # Exercise the immutable before-state even after these successors are
        # published. A changed successor cannot be converted into a fixture.
        replacements = {d["canonical_event"]["event_id"]: d for d in cls.review["decisions"]}
        for index, event in enumerate(cls.first):
            decision = replacements.get(event["event_id"])
            if decision is not None:
                if json.dumps(event, sort_keys=True) != json.dumps(decision["canonical_event"], sort_keys=True):
                    raise AssertionError("published 10205 successor changed")
                cls.first[index] = copy.deepcopy(decision["previous_event"])
        cls.second = read(ROOT / "second_round_polls.json")["events"]
        cls.parsed = fixture(240570516)
        cls.rows = parse_french_frozen_fixture(cls.parsed)["first_round"]
        cls.result = reconcile_composite_rn(cls.rows, 240570516, cls.first,
                                          retain_published_history=True)
        cls.old = [d["previous_event"] for d in cls.review["decisions"]]
        cls.new = [d["canonical_event"] for d in cls.review["decisions"]]
        cls.old_ids = {e["event_id"] for e in cls.old}
        cls.new_ids = {e["event_id"] for e in cls.new}
        cls.roster = [{"candidate_name": n, "candidate_id": candidate_id(n)} for n in (
            "Jordan Bardella", "Marine Le Pen", "Gabriel Attal", "Édouard Philippe",
        )]

    def apply(self, events, rows=None):
        return reconcile_composite_rn(self.rows if rows is None else rows, 240570516,
                                     events, retain_published_history=True)

    def notice(self, newer=True):
        n = copy.deepcopy(next(n for n in read(ROOT / "commission_notice_registry.json")["notices"]
                               if n["notice_id"] == "commission:10205"))
        identity = self.review["notice_identity_review"]["accepted_identities"][int(newer)]
        n.update({k: copy.deepcopy(v) for k, v in identity.items() if k != "resolved_urls"})
        n["resolved_url"] = identity["resolved_urls"][-1]
        n["classification"] = "eligible"
        return n

    def coverage(self, notice, events=None):
        registry = {"notices": [notice]}
        reconcile_composite_notice_coverage(registry, self.result.events if events is None else events)
        return notice["coverage"]

    def test_source_fixture_and_distinct_bases(self):
        doc = json.loads(gzip.decompress((FIXTURES / "commission_10205_document.json.gz").read_bytes()))
        self.assertEqual(doc["content_sha256"], self.review["evidence"]["content_sha256"])
        self.assertEqual(set(doc["pages"]), {"2", "3", "4", "12", "13", "14"})
        self.assertEqual(self.review["evidence"]["sample_bases"], {
            "adults": 1001, "registered_voters": 901, "certain_to_vote": 683,
            "expressed_respondents": None,
        })

    def test_all_three_complete_published_columns(self):
        for decision, rn_score in zip(self.review["decisions"], (35, 33, 34)):
            event = decision["canonical_event"]
            expected = {candidate_identity(c["name"]): float(c["published_score"].rstrip("%"))
                        for c in decision["source_table"]["candidates"]}
            actual = {candidate_identity(c["name"]): c["score"] for c in event["candidates"]}
            self.assertEqual(actual, expected)
            option = next(c for c in event["candidates"] if c["name"] == RN_CONDITIONAL_OPTION)
            self.assertEqual(option["score"], rn_score)
            self.assertEqual(option["identity_type"], "ballot_label")
            self.assertEqual(option["display_names"], RN_CONDITIONAL_DISPLAY_NAMES)
            self.assertEqual(event["reported_total"], 100)

    def test_only_three_ids_change_and_other_436_objects_identical(self):
        original = {e["event_id"]: e for e in self.first + self.second}
        current = {e["event_id"]: e for e in self.result.events + self.second}
        self.assertEqual(len(original), 439)
        self.assertEqual(len(current), 439)
        self.assertEqual(set(original) - set(current), self.old_ids)
        self.assertEqual(set(current) - set(original), self.new_ids)
        for event_id in set(original) - self.old_ids:
            self.assertEqual(json.dumps(original[event_id], sort_keys=True),
                             json.dumps(current[event_id], sort_keys=True))

    def test_dates_samples_other_scores_labels_and_earlier_lineage_preserved(self):
        for old, new in zip(self.old, self.new):
            for key in old.keys() - {"event_id", "hypothesis", "scenario_key", "candidates", "supersedes_event_id"}:
                self.assertEqual(new[key], old[key])
            self.assertEqual(new["sample_size"], 1001)
            self.assertEqual(new.get("sample_scope"), old.get("sample_scope"))
            self.assertEqual(new["supersedes_event_id"], old["event_id"])
            self.assertEqual(new["reviewed_source_pdf_page"], 12 + self.old.index(old))
            for a, b in zip(old["candidates"], new["candidates"]):
                if candidate_identity(a["name"]) != "jordan-bardella":
                    self.assertEqual(a, b)
                else:
                    self.assertEqual(a["score"], b["score"])
            if old.get("migration_source_locator"):
                self.assertIn("supersedes_event_id", old)

    def test_successor_ids_and_scenarios_are_deterministic(self):
        validate_poll_events(self.result.events)
        for event in self.new:
            self.assertEqual(event["scenario_key"], make_scenario_key(c["name"] for c in event["candidates"]))
            self.assertEqual(event["event_id"], make_event_id(event["pollster"], event["fieldwork_start"],
                             event["fieldwork_end"], event["hypothesis"], event["source_url"]))

    def test_repeated_correction_is_identical_without_mutating_inputs(self):
        prior = copy.deepcopy(self.first)
        twice = self.apply(self.result.events)
        self.assertEqual(twice.events, self.result.events)
        self.assertEqual(twice.report, {"applied": 0, "already_applied": 3})
        self.assertEqual(prior, self.first)

    def test_missing_predecessors_or_successors_fail_closed(self):
        for corpus, ids in ((self.first, self.old_ids), (self.result.events, self.new_ids)):
            for event_id in ids:
                with self.assertRaises(ValueError):
                    self.apply([e for e in corpus if e["event_id"] != event_id])

    def test_altered_predecessor_and_successor_fail_closed(self):
        for corpus, ids in ((self.first, self.old_ids), (self.result.events, self.new_ids)):
            for field, value in (("sample_size", 901), ("source_url", "https://example.test/changed"),
                                 ("fieldwork_end", "2026-06-12"), ("commissioner", "changed")):
                mutated = copy.deepcopy(corpus)
                next(e for e in mutated if e["event_id"] in ids)[field] = value
                with self.assertRaises(ValueError):
                    self.apply(mutated)

    def test_duplicate_and_simultaneous_identities_fail_closed(self):
        for corpus in (self.first + [self.old[0]], self.result.events + [self.old[0]]):
            with self.assertRaises(ValueError):
                self.apply(corpus)

    def test_json_numeric_type_changes_cannot_impersonate_exact_snapshots(self):
        for corpus, event_id in ((self.first, self.old[0]["event_id"]),
                                 (self.result.events, self.new[0]["event_id"])):
            for value in (True, 1.0):
                changed = copy.deepcopy(corpus)
                next(e for e in changed if e["event_id"] == event_id)["candidates"][0]["score"] = value
                with self.assertRaises(ValueError):
                    self.apply(changed)
        changed = copy.deepcopy(self.result.events)
        next(e for e in changed if e["event_id"] == self.new[0]["event_id"])["candidates"][0]["score"] = 1.0
        self.assertEqual(self.coverage(self.notice(), changed)["state"], "unresolved")

    def test_lookalike_predecessor_with_new_id_is_rejected(self):
        extra = copy.deepcopy(self.old[0]); extra["event_id"] = "a" * 64
        with self.assertRaises(ValueError):
            self.apply(self.first + [extra])

    def test_changed_and_duplicate_incoming_source_facts_fail_closed(self):
        for field, value in (("sample_size", 901), ("source_url", "https://example.test/changed")):
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r["source_locator"] in self.result.handled)
            row[field] = value
            with self.assertRaises(ValueError):
                self.apply(self.first, rows)
        row = next(r for r in self.rows if r["source_locator"] in self.result.handled)
        with self.assertRaises(ValueError):
            self.apply(self.first, self.rows + [copy.deepcopy(row)])

    def test_changed_source_scores_and_truncated_lineups_fail_closed(self):
        for truncate in (True, False):
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r["source_locator"] in self.result.handled)
            if truncate:
                row["candidates"].pop()
            else:
                row["candidates"][0]["score"] += 0.5
            with self.assertRaises(ValueError):
                self.apply(self.first, rows)

    def test_changed_registry_requires_new_explicit_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "review.json"
            changed = copy.deepcopy(self.review)
            changed["decisions"][0]["canonical_event"]["sample_size"] = 901
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_composite_review(path)

    def test_original_frozen_replay_stays_independent(self):
        result = reconcile_composite_rn(self.rows, 240562307, self.first, retain_published_history=True)
        self.assertEqual(result.events, self.first)
        strict = reconcile_composite_rn(self.rows, 240570516, self.first)
        self.assertEqual(strict.events, self.first)

    def test_live_boundary_repeats_and_never_reactivates_predecessors(self):
        first, second, report, _ = integrate_french_migration_source(
            self.parsed, self.first, self.second, [], retain_published_history=True)
        again, runoff, repeat, _ = integrate_french_migration_source(
            self.parsed, first, second, [], retain_published_history=True)
        self.assertEqual(first, again)
        self.assertEqual(second, runoff)
        self.assertEqual(second, self.second)
        self.assertFalse(self.old_ids & {e["event_id"] for e in again})
        self.assertEqual(report["commission_10205_composite"]["applied"], 3)
        self.assertEqual(repeat["commission_10205_composite"]["already_applied"], 3)

    def test_three_older_wikipedia_snapshots_cannot_reverse_published_successors(self):
        for revision in (240522402, 240562307, 240569682):
            events, runoff, _report, _ = integrate_french_migration_source(
                fixture(revision), self.result.events, self.second, [], retain_published_history=True)
            self.assertEqual({e["event_id"]: e for e in events}, {e["event_id"]: e for e in self.result.events})
            self.assertEqual(runoff, self.second)

    def test_candidate_ranges_and_histories_exclude_both_individuals(self):
        package = build_poll_packages(self.new)[0]
        polling = project_candidate_polling(self.roster, package)
        histories = project_candidate_poll_history(self.roster, self.new)
        for person in ("jordan-bardella", "marine-le-pen"):
            self.assertEqual(polling[person]["evidence_state"], "not_observed")
            self.assertIsNone(polling[person]["range_max"])
            self.assertEqual(histories[person]["observation_count"], 0)
        before = project_candidate_polling(self.roster, build_poll_packages(self.old)[0])
        self.assertEqual(before["jordan-bardella"]["range_min"], 33)
        self.assertEqual(before["jordan-bardella"]["range_max"], 35)

    def test_even_an_arbitrary_matching_roster_cannot_project_a_ballot_as_a_person(self):
        roster = self.roster + [{"candidate_name": RN_CONDITIONAL_OPTION,
                                "candidate_id": candidate_id(RN_CONDITIONAL_OPTION)}]
        result = project_candidate_polling(roster, build_poll_packages(self.new)[0])
        self.assertEqual(result[candidate_id(RN_CONDITIONAL_OPTION)]["evidence_state"], "not_observed")

    def test_polling_lab_excludes_ballot_from_person_directory_and_candidate_statistics(self):
        old, new = build_poll_explorer(self.first), build_poll_explorer(self.result.events)
        wave = next(w for w in new["waves"] if w["fieldwork_end"] == "2026-06-11" and w["pollster"] == "OpinionWay")
        self.assertNotIn("jordan-bardella", wave["candidate_ids"])
        self.assertNotIn("marine-le-pen", wave["candidate_ids"])
        self.assertNotIn(candidate_id(RN_CONDITIONAL_OPTION), wave["candidate_ids"])
        self.assertNotIn(candidate_id(RN_CONDITIONAL_OPTION), {c["candidate_id"] for c in new["candidates"]})
        counts = lambda p: next(c for c in p["candidates"] if c["candidate_id"] == "jordan-bardella")["scenario_count"]
        self.assertEqual(counts(old) - counts(new), 3)
        prior = next(w for w in old["waves"] if w["wave_id"] == wave["wave_id"])
        self.assertEqual(prior["page_path_fr"], wave["page_path_fr"])
        self.assertEqual(prior["page_path_en"], wave["page_path_en"])

    def test_bilingual_results_keep_conditional_label_and_exclude_candidate_variation(self):
        wave = build_poll_explorer(self.new)["waves"][0]
        for language in ("fr", "en"):
            for scenario in wave["scenarios"]:
                html = render_scenario(scenario, 1, language)
                self.assertIn(RN_CONDITIONAL_DISPLAY_NAMES[language], html)
            self.assertNotIn(RN_CONDITIONAL_DISPLAY_NAMES[language], "".join(candidate_variation_rows(wave, language)))
        javascript = (ROOT / "assets/polling-lab.js").read_text(encoding="utf-8")
        self.assertIn("item.display_names?.[PAGE_LANG]", javascript)
        for name in ("index.html", "en/index.html"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('if (candidate.identity_type === "ballot_label") return;', source)
            self.assertIn('.filter(candidate => candidate.identity_type !== "ballot_label")', source)

    def test_coverage_accepts_only_the_two_reviewed_exact_notice_snapshots(self):
        for newer in (True, False):
            coverage = self.coverage(self.notice(newer))
            self.assertEqual(coverage["state"], "reconciled")
            self.assertEqual(set(coverage["matched_event_ids"]), self.new_ids)

    def test_unrelated_generic_ballot_variation_summaries_are_preserved(self):
        wave = next(w for w in build_poll_explorer(self.first)["waves"]
                    if w["fieldwork_end"] == "2025-04-25" and w["pollster"] == "Harris Interactive")
        for language in ("fr", "en"):
            summaries = "".join(candidate_variation_rows(wave, language))
            self.assertIn('>RN</span>', summaries)
            self.assertIn('>EXG</span>', summaries)

    def test_old_objects_cannot_authorize_reconciliation(self):
        self.assertEqual(self.coverage(self.notice(), self.first)["state"], "unresolved")

    def test_missing_changed_duplicate_and_extra_objects_cannot_clear_notice(self):
        extra = copy.deepcopy(self.new[0]); extra["event_id"] = "e" * 64
        for variation in (self.result.events + [extra], self.result.events + [self.new[0]],
                          [e for e in self.result.events if e["event_id"] != self.new[0]["event_id"]]):
            self.assertEqual(self.coverage(self.notice(), variation)["state"], "unresolved")
        changed = copy.deepcopy(self.result.events)
        next(e for e in changed if e["event_id"] in self.new_ids)["sample_size"] = 901
        self.assertEqual(self.coverage(self.notice(), changed)["state"], "unresolved")

    def test_source_identity_dates_and_confirmation_drift_cannot_clear_notice(self):
        for key, value in (("content_sha256", "f" * 64), ("resolved_url", "https://example.test/x"),
                           ("confirmed_rounds", ["second_round"]),
                           ("survey_metadata", {"fieldwork_start": "2026-06-09", "fieldwork_end": "2026-06-11"})):
            notice = self.notice(); notice[key] = value
            self.assertEqual(self.coverage(notice)["state"], "unresolved")
        notice = self.notice(); notice["classification"] = "unsupported"; notice["classification_reason"] = "document fetch failed"
        self.assertEqual(self.coverage(notice)["state"], "unresolved")

    def test_other_notices_and_batch1_batch2_decisions_are_not_mutated(self):
        registry = read(ROOT / "commission_notice_registry.json")
        before = copy.deepcopy(registry)
        reconcile_composite_notice_coverage(registry, self.result.events + self.second)
        for original, current in zip(before["notices"], registry["notices"]):
            if original["notice_id"] != "commission:10205":
                self.assertEqual(original, current)
        for notice_id in ("commission:10327", "commission:10264", "commission:10260"):
            self.assertEqual(next(n for n in registry["notices"] if n["notice_id"] == notice_id)["coverage"]["state"], "unresolved")

    def test_coverage_is_idempotent(self):
        registry = {"notices": [self.notice()]}
        reconcile_composite_notice_coverage(registry, self.result.events)
        original = copy.deepcopy(registry)
        reconcile_composite_notice_coverage(registry, self.result.events)
        self.assertEqual(original, registry)


if __name__ == "__main__":
    unittest.main()
