"""Bounded OpinionWay 10318 source variants; no published object mutations."""

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fetch_polls import integrate_french_migration_source, load_poll_wave_overrides
from poll_migration import exact_factual_key, parse_french_frozen_fixture
from reviewed_polling_accuracy import (
    load_source_retention_review, reviewed_source_retention,
)


ROOT = Path(__file__).parent


class ReviewedSourceRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = load_source_retention_review()
        cls.first = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
        cls.second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        cls.parsed = json.loads(gzip.decompress(
            (ROOT / "test_fixtures/fr27_polling/fr_mediawiki_240570516.json.gz").read_bytes()
        ))
        cls.archived = parse_french_frozen_fixture(cls.parsed, allow_reviewed_polony=True)
        cls.rows = copy.deepcopy(cls.archived)
        cls.ids = {d["retained_event_id"] for d in cls.review["decisions"]}
        retained = [e for e in cls.first if e["event_id"] in cls.ids]
        keys = {exact_factual_key(e) for e in retained}
        cls.variants = []
        for row in cls.rows["first_round"]:
            if exact_factual_key(row) in keys:
                row["sample_size"] = 1001
                cls.variants.append(row)
        if len(cls.variants) != 2:
            raise AssertionError("10318 archived evidence must contain both configurations")
        cls.overrides = load_poll_wave_overrides(ROOT / "poll_wave_overrides.json")

    def integrate(self, rows=None, parsed=None):
        source = self.parsed if parsed is None else parsed
        if rows is None:
            return integrate_french_migration_source(
                source, self.first, self.second, [], self.overrides,
                retain_published_history=True,
            )
        with patch("rehearse_fr_poll_migration._assert_production_source_structure", return_value=rows):
            return self.integrate(parsed=source)

    def changed_rows(self, change):
        rows = copy.deepcopy(self.rows)
        locator = self.variants[0]["source_locator"]
        row = next(r for r in rows["first_round"] if r["source_locator"] == locator)
        change(row)
        return rows

    def test_only_two_exact_variants_map_to_unchanged_objects(self):
        before = copy.deepcopy((self.first, self.second, self.rows))
        handled, report = reviewed_source_retention(self.rows, self.first)
        self.assertEqual(len(handled), 2)
        self.assertEqual({r["retained_event_id"] for r in report}, self.ids)
        self.assertEqual({r["source_sample_size"] for r in report}, {1001})
        retained = {e["event_id"]: exact_factual_key(e) for e in self.first if e["event_id"] in self.ids}
        self.assertEqual(set(handled.values()), set(retained.values()))
        self.assertEqual(before, (self.first, self.second, self.rows))

    def test_integration_preserves_every_production_object_and_adds_none(self):
        first, second, report, _ = self.integrate(self.rows)
        self.assertEqual(first, self.first)
        self.assertEqual(second, self.second)
        self.assertEqual(len(report["reviewed_source_retention"]), 2)
        self.assertEqual(report["normal_post_audit_additions"], {"first_round": 0, "second_round": 0})

    def test_archived_1043_source_still_replays(self):
        first, second, report, _ = self.integrate()
        self.assertEqual((first, second), (self.first, self.second))
        self.assertEqual({r["source_sample_size"] for r in report["reviewed_source_retention"]}, {1043})

    def test_future_revision_and_relocated_exact_facts_are_accepted(self):
        parsed = {**self.parsed, "revid": 240999999}
        rows = copy.deepcopy(self.rows)
        for row in rows["first_round"]:
            if row["source_locator"] in {r["source_locator"] for r in self.variants}:
                row["source_locator"] += "-relocated"
        self.assertEqual(self.integrate(rows, parsed)[:2], (self.first, self.second))

    def test_changed_scores_are_rejected(self):
        rows = self.changed_rows(lambda r: r["candidates"][0].update(score=1.25))
        with self.assertRaisesRegex(ValueError, "unreviewed source facts"):
            self.integrate(rows)

    def test_changed_candidate_membership_is_rejected(self):
        rows = self.changed_rows(lambda r: r["candidates"].pop())
        with self.assertRaisesRegex(ValueError, "unreviewed source facts"):
            reviewed_source_retention(rows, self.first)

    def test_dates_sample_scope_size_round_and_pollster_are_not_aliased(self):
        for fields in (
            {"fieldwork_start": "2026-10-12"}, {"fieldwork_end": "2026-10-15"},
            {"sample_size": 1002}, {"sample_scope": "registered_voters"},
            {"pollster": "Ifop"},
        ):
            with self.subTest(fields=fields):
                rows = self.changed_rows(lambda r: r.update(fields))
                with self.assertRaisesRegex(ValueError, "unreviewed source facts"):
                    reviewed_source_retention(rows, self.first)

    def test_wrong_round_is_rejected_by_the_existing_factual_contract(self):
        rows = self.changed_rows(lambda r: r.update(round="second_round"))
        with self.assertRaisesRegex(ValueError, "invalid candidate count"):
            reviewed_source_retention(rows, self.first)

    def test_missing_altered_or_reidentified_retained_targets_fail(self):
        for target_id in self.ids:
            for action in ("missing", "score", "source", "sample", "id"):
                with self.subTest(target=target_id, action=action):
                    first = copy.deepcopy(self.first)
                    target = next(e for e in first if e["event_id"] == target_id)
                    if action == "missing":
                        first.remove(target)
                    elif action == "score":
                        target["candidates"][0]["score"] += .25
                    else:
                        target[{"source": "source_url", "sample": "sample_size", "id": "event_id"}[action]] = {
                            "source": "https://example.org/other", "sample": 1001, "id": "0" * 64,
                        }[action]
                    with self.assertRaisesRegex(ValueError, "retained event changed or missing"):
                        reviewed_source_retention(self.rows, first)

    def test_duplicate_source_identities_and_both_representations_fail(self):
        for sample in (1001, 1043):
            with self.subTest(sample=sample):
                rows = copy.deepcopy(self.rows)
                duplicate = copy.deepcopy(self.variants[0])
                duplicate.update(source_locator="duplicate-reviewed", sample_size=sample)
                rows["first_round"].append(duplicate)
                with self.assertRaisesRegex(ValueError, "duplicate source representations"):
                    reviewed_source_retention(rows, self.first)

    def test_duplicate_prior_ids_fail(self):
        with self.assertRaisesRegex(ValueError, "duplicate prior event ID"):
            reviewed_source_retention(self.rows, self.first + [self.first[0]])

    def test_similar_anchor_with_another_document_has_no_exemption(self):
        rows = self.changed_rows(lambda r: r.update(source_url="https://example.org/unreviewed-survey.pdf"))
        handled, _ = reviewed_source_retention(rows, self.first)
        self.assertEqual(len(handled), 1)
        with self.assertRaisesRegex(ValueError, "unregistered French row shares a review anchor"):
            self.integrate(rows)

    def test_other_wave_and_pollster_do_not_receive_a_sample_alias(self):
        rows = self.changed_rows(lambda r: r.update(
            pollster="Ifop", fieldwork_start="2026-10-11", fieldwork_end="2026-10-12",
            source_url="https://example.org/another-wave.pdf",
        ))
        handled, _ = reviewed_source_retention(rows, self.first)
        self.assertNotIn(("first_round", self.variants[0]["source_locator"]), handled)

    def test_review_changes_cannot_replace_target_ids_or_documentary_evidence(self):
        for field in ("retained_event_id", "documentary_evidence"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                review = copy.deepcopy(self.review)
                if field == "retained_event_id":
                    review["decisions"][0][field] = "0" * 64
                else:
                    review[field][0]["content_sha256"] = "0" * 64
                path = Path(temporary) / "review.json"
                path.write_text(json.dumps(review), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "review changed; explicit review required"):
                    load_source_retention_review(path)

    def test_hypothesis_one_remains_censored_and_excluded(self):
        notice = self.review["decisions"][0]["incoming_source_url"]
        rejected = [r for r in self.rows["rejected"] if r.get("source_url") == notice]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reason_code"], "censored_score")
        self.assertEqual(len([r for r in self.rows["first_round"] if r["source_url"] == notice]), 2)

    def test_older_corpora_without_the_survey_remain_independent(self):
        self.assertEqual(reviewed_source_retention({"first_round": [], "second_round": []}, []), ({}, []))


if __name__ == "__main__":
    unittest.main()
