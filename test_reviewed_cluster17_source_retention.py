"""Finite 10339 source variants preserve the authenticated October study."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fetch_polls import integrate_french_migration_source, load_poll_wave_overrides
from poll_migration import exact_factual_key, parse_french_frozen_fixture
import poll_studies as studies
import reviewed_polling_accuracy as retention

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "test_fixtures/fr27_polling"
SOURCE_PINS = {
    240766888: "15ad17a8e7a9fa67b90aef8008a8358da219e568d79fc0208d217087471bef2b",
    240741132: "4647dd31da34d5d6eec400aee09e3d13feacfbc3470bda83d38208b92e6376e5",
}


def typed_json(value):
    """Preserve array order and distinguish integer, float, bool and null."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def source(revision):
    path = FIXTURES / f"fr_mediawiki_{revision}.json"
    raw = path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(".json.gz").read_bytes())
    if revision in SOURCE_PINS and hashlib.sha256(raw).hexdigest() != SOURCE_PINS[revision]:
        raise AssertionError("10339 frozen source bytes changed")
    payload = json.loads(raw)
    parsed = payload.get("parse", payload)
    if parsed["revid"] != revision:
        raise AssertionError("10339 frozen revision changed")
    return parsed


class Cluster17SourceRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = json.loads((ROOT / "polls.json").read_bytes())
        cls.second = json.loads((ROOT / "second_round_polls.json").read_bytes())["events"]
        cls.binding = studies.load_binding()
        cls.review = retention.load_cluster17_source_retention_review()
        cls.ids = {m["event_id"] for m in cls.binding["members"]}
        cls.parsed = source(240766888)
        cls.rows = parse_french_frozen_fixture(cls.parsed, allow_reviewed_polony=True)
        cls.variants = [row for row in cls.rows["first_round"]
                        if row["source_url"] == cls.review["documentary_evidence"][1]["url"]]
        if len(cls.variants) != 3:
            raise AssertionError("10339 must contain all three documentary hypotheses")
        cls.overrides = load_poll_wave_overrides(ROOT / "poll_wave_overrides.json")

    def integrate(self, parsed=None):
        return integrate_french_migration_source(
            self.parsed if parsed is None else parsed, self.first, self.second,
            [], self.overrides, retain_published_history=True,
        )

    def changed_rows(self, change):
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows["first_round"]
                   if r["source_locator"] == self.variants[0]["source_locator"])
        change(row)
        return rows

    def test_original_guard_still_rejects_the_unregistered_representation(self):
        with patch.object(retention, "_cluster17_source_retention", return_value=({}, [])):
            with self.assertRaisesRegex(ValueError, "unregistered French row shares a review anchor"):
                self.integrate()

    def test_current_and_parent_real_integration_preserve_all_typed_objects_and_order(self):
        before = typed_json((self.first, self.second, self.parsed))
        for revision, sample in ((240766888, 2817), (240741132, 3000)):
            with self.subTest(revision=revision):
                first, second, report, _ = self.integrate(source(revision))
                self.assertEqual(typed_json(first), typed_json(self.first))
                self.assertEqual(typed_json(second), typed_json(self.second))
                handled = [r for r in report["reviewed_source_retention"]
                           if r["review_id"] == self.review["review_id"]]
                self.assertEqual(len(handled), 3)
                self.assertEqual({r["retained_event_id"] for r in handled}, self.ids)
                self.assertEqual({r["source_sample_size"] for r in handled}, {sample})
                self.assertEqual(report["normal_post_audit_additions"], {"first_round": 0, "second_round": 0})
                self.assertEqual(report["post_audit_first_round_corrections"]["superseded_event_ids"], [])
                studies.validate_study_membership(first)
                repeated = integrate_french_migration_source(source(revision), first, second, [],
                    self.overrides, retain_published_history=True)
                self.assertEqual(typed_json(repeated[:2]), typed_json((first, second)))
        self.assertEqual(typed_json((self.first, self.second, self.parsed)), before)

    def test_previously_supported_snapshots_preserve_their_authenticated_corpora(self):
        historical = json.loads(gzip.decompress(
            (FIXTURES / "phase1_published_326_97.json.gz").read_bytes()))
        # These early sources contain only 95 runoff rows. Today's 106-row
        # baseline must still trigger the unchanged widespread-loss guard.
        with self.assertRaisesRegex(ValueError, "widespread second_round extraction loss"):
            self.integrate(source(240490172))
        for revision in (240490172, 240498648, 240522402):
            with self.subTest(revision=revision):
                first, second = historical["first_round"], historical["second_round"]
                result = integrate_french_migration_source(source(revision), first, second,
                    [e for e in first if e.get("official_notice_id")],
                    retain_published_history=True)
                self.assertEqual(typed_json(result[:2]), typed_json((first, second)))
        self.assertEqual(typed_json(self.integrate(source(240570516))[:2]),
                         typed_json((self.first, self.second)))

    def test_every_enumerated_variant_maps_only_to_its_unchanged_target(self):
        retained = {e["event_id"]: e for e in self.first if e["event_id"] in self.ids}
        for decision in self.review["decisions"]:
            canonical = exact_factual_key(retained[decision["retained_event_id"]])
            for variant in decision["source_variants"]:
                rows = {"first_round": [], "second_round": []}
                event = copy.deepcopy(retained[decision["retained_event_id"]])
                event.update(source_locator="relocated-exact-row", source_url=variant["source_url"],
                             sample_size=variant["factual_key"]["sample_size"])
                rows["first_round"].append(event)
                handled, report = retention._cluster17_source_retention(rows, self.first)
                self.assertEqual(handled, {("first_round", "relocated-exact-row"): canonical})
                self.assertEqual(report[0]["retained_event_id"], decision["retained_event_id"])

    def test_revision_and_locator_alone_never_authorize_different_facts(self):
        moved = copy.deepcopy(self.parsed)
        moved["revid"] = 240999999
        self.assertEqual(typed_json(self.integrate(moved)[:2]), typed_json((self.first, self.second)))
        rows = self.changed_rows(lambda r: r.update(source_locator="another-location", sample_size=2818))
        with self.assertRaises(ValueError):
            retention._cluster17_source_retention(rows, self.first)

    def test_candidate_membership_identity_and_scores_fail_closed(self):
        changes = [lambda r: r["candidates"].pop(),
                   lambda r: r["candidates"][0].update(name="David Lisnard"),
                   lambda r: r["candidates"][0].update(score=0.75)]
        for change in changes:
            with self.subTest(change=changes.index(change)), self.assertRaises(ValueError):
                retention._cluster17_source_retention(self.changed_rows(change), self.first)

    def test_sample_dates_round_institute_and_scope_are_not_aliased(self):
        for fields in ({"sample_size": 2816}, {"sample_size": 2818},
                       {"fieldwork_start": "2026-10-18"}, {"fieldwork_end": "2026-10-23"},
                       {"round": "second_round"}, {"pollster": "Ifop"},
                       {"sample_scope": "registered_voters"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                retention._cluster17_source_retention(self.changed_rows(lambda r: r.update(fields)), self.first)

    def test_unapproved_urls_cannot_authorize_either_sample_representation(self):
        for sample in (2817, 3000):
            rows = self.changed_rows(lambda r: r.update(sample_size=sample, source_url="https://example.org/other.pdf"))
            with self.subTest(sample=sample), self.assertRaisesRegex(ValueError, "unreviewed source facts/provenance"):
                retention._cluster17_source_retention(rows, self.first)

    def test_duplicate_sources_old_and_new_representations_and_locators_fail(self):
        for sample in (2817, 3000):
            rows = copy.deepcopy(self.rows)
            duplicate = copy.deepcopy(self.variants[0])
            duplicate.update(source_locator="duplicate", sample_size=sample)
            if sample == 3000:
                duplicate["source_url"] = self.review["documentary_evidence"][0]["url"]
            rows["first_round"].append(duplicate)
            with self.subTest(sample=sample), self.assertRaisesRegex(ValueError, "duplicate source representations"):
                retention._cluster17_source_retention(rows, self.first)
        rows = self.changed_rows(lambda r: r.update(source_locator=self.variants[1]["source_locator"]))
        with self.assertRaisesRegex(ValueError, "duplicate source representations"):
            retention._cluster17_source_retention(rows, self.first)

    def test_missing_changed_reidentified_and_duplicated_retained_objects_fail(self):
        for event_id in self.ids:
            for action in ("missing", "sample", "source", "score", "id", "type", "extra"):
                first = copy.deepcopy(self.first)
                event = next(e for e in first if e["event_id"] == event_id)
                if action == "missing": first.remove(event)
                elif action == "sample": event["sample_size"] = 2817
                elif action == "source": event["source_url"] = self.review["documentary_evidence"][1]["url"]
                elif action == "score": event["candidates"][0]["score"] += .25
                elif action == "id": event["event_id"] = "0" * 64
                elif action == "type": event["sample_size"] = 3000.0
                else: event["unapproved_field"] = None
                with self.subTest(event=event_id, action=action), self.assertRaises(ValueError):
                    retention._cluster17_source_retention(self.rows, first)
        target = next(e for e in self.first if e["event_id"] in self.ids)
        with self.assertRaisesRegex(ValueError, "duplicate prior event ID"):
            retention._cluster17_source_retention(self.rows, self.first + [target])

    def test_review_target_and_document_hash_changes_are_rejected(self):
        for field in ("documentary_evidence", "retained_event_id", "retained_object_sha256", "study_binding_sha256"):
            changed = copy.deepcopy(self.review)
            if field == "documentary_evidence": changed[field][1]["content_sha256"] = "0" * 64
            elif field == "study_binding_sha256": changed[field] = "0" * 64
            else: changed["decisions"][0][field] = "0" * 64
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "review.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "review changed; explicit review required"):
                    retention.load_cluster17_source_retention_review(path)

    def test_duplicate_target_decisions_fail_even_before_matching(self):
        changed = copy.deepcopy(self.review)
        changed["decisions"][1]["retained_event_id"] = changed["decisions"][0]["retained_event_id"]
        with patch.object(retention, "load_cluster17_source_retention_review", return_value=changed):
            with self.assertRaisesRegex(ValueError, "retained target identities changed"):
                retention._cluster17_source_retention(self.rows, self.first)

    def test_binding_or_original_document_pin_changes_cannot_hide_behind_cache(self):
        original_loader = studies.load_binding
        studies._binding()  # Prepopulate the projection cache with the valid file.
        for field in ("sample_size", "source_document", "members"):
            changed = copy.deepcopy(self.binding)
            if field == "sample_size": changed[field] = 2817
            elif field == "source_document": changed[field]["sha256"] = "0" * 64
            else: changed[field][0]["object_sha256"] = "0" * 64
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "binding.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with patch.object(studies, "load_binding", side_effect=lambda: original_loader(path)):
                    with self.assertRaisesRegex(ValueError, "binding changed"):
                        retention._cluster17_source_retention(self.rows, self.first)

    def test_other_studies_sharing_institute_or_dates_receive_no_exemption(self):
        rows = self.changed_rows(lambda r: r.update(fieldwork_start="2026-10-18"))
        with self.assertRaises(ValueError):
            retention._cluster17_source_retention(rows, self.first)
        rows = self.changed_rows(lambda r: (r.update(source_url="https://example.org/unrelated.pdf"),
                                           r["candidates"][0].update(score=0.75)))
        handled, _ = retention._cluster17_source_retention(rows, self.first)
        self.assertNotIn(("first_round", self.variants[0]["source_locator"]), handled)
        with patch("rehearse_fr_poll_migration._assert_production_source_structure", return_value=rows):
            with self.assertRaisesRegex(ValueError, "unregistered French row shares a review anchor"):
                self.integrate()

    def test_independent_retention_decisions_cannot_overlap(self):
        handled, report = retention._cluster17_source_retention(self.rows, self.first)
        with patch.object(retention, "_opinionway_source_retention", return_value=(handled, report)):
            with self.assertRaisesRegex(ValueError, "Overlapping reviewed source-retention"):
                retention.reviewed_source_retention(self.rows, self.first)

    def test_pre_study_corpora_remain_independent(self):
        self.assertEqual(retention._cluster17_source_retention(
            {"first_round": [], "second_round": []}, []), ({}, []))

    def test_actions_contract_invokes_both_reviews_and_pins_both_new_fixtures(self):
        workflow = (ROOT / ".github/workflows/update-polls.yml").read_text(encoding="utf-8")
        command = workflow.split("python -B run_update_polls_contract_tests.py -v", 1)[1].split("\n\n", 1)[0]
        self.assertIn("test_reviewed_cluster17_source_retention.py", command)
        self.assertIn("test_reviewed_source_retention.py", command)
        for revision in SOURCE_PINS:
            self.assertEqual(source(revision)["revid"], revision)


if __name__ == "__main__":
    unittest.main()
