import copy
import hashlib
import json
import unittest
from pathlib import Path

from fetch_polls import integrate_french_migration_source
from poll_contract import FIRST_ROUND, apply_completeness_contract, validate_poll_events
from poll_migration import (
    exact_factual_key, load_migration_registry, parse_french_frozen_fixture,
)
from post_audit_first_round_corrections import (
    load_corrections, reconcile_first_round_corrections, validate_corrections,
)
from rehearse_fr_poll_migration import reconcile_french_production_source


ROOT = Path(__file__).parent
FIXTURES = ROOT / "test_fixtures/fr27_polling"


def read(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class PostAuditFirstRoundCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_corrections()
        cls.registry["corrections"] = [r for r in cls.registry["corrections"]
                                       if r["incoming_factual_key"]["pollster_identity"] != "yougov"]
        cls.retained = [r for r in cls.registry["corrections"] if r["action"] != "accept_reviewed_sample"]
        cls.historical = cls.registry["corrections"][-1]["historical_withheld_source"]
        cls.parsed = read("fr_mediawiki_240128358.json")["parse"]
        cls.rows = parse_french_frozen_fixture(cls.parsed)[FIRST_ROUND]
        cls.previous = read("notice_10284_previous_events.json")
        cls.primary = read("notice_10284_first_round.json")

    def run_lane(self, *, rows=None, previous=None, revision=240128358, registry=None):
        return reconcile_first_round_corrections(
            self.rows if rows is None else rows, revision,
            self.previous if previous is None else previous,
            registry=self.registry if registry is None else registry,
        )

    def mutated_row(self, mutate, locator="FR-T0R1"):
        rows = copy.deepcopy(self.rows)
        row = next(row for row in rows if row["source_locator"] == locator)
        mutate(row)
        return rows

    def test_frozen_revision_and_independent_official_scenarios(self):
        # Keep raw-byte SHA checks portable by pinning the checkout LF contract.
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        for name in (
            "fr_mediawiki_240128358.json", "fr_mediawiki_240131611.json",
            "notice_10284_first_round.json", "notice_10284_previous_events.json",
        ):
            with self.subTest(fixture=name):
                self.assertIn(f"/test_fixtures/fr27_polling/{name} text eol=lf", attributes)
                self.assertNotIn(b"\r", (FIXTURES / name).read_bytes())
        self.assertEqual(self.parsed["revid"], 240128358)
        self.assertEqual(
            hashlib.sha256((FIXTURES / "fr_mediawiki_240128358.json").read_bytes()).hexdigest(),
            self.primary["mediawiki_fixture"]["sha256"],
        )
        self.assertEqual(self.primary["total_adults"], 1527)
        self.assertEqual(self.primary["registered_voters"], 1393)
        expected_expressed = [1027, 1003, 970, 964, 928, 974, 971, 969, 980, 1015]
        for record, official, expressed in zip(
            self.retained, self.primary["scenarios"], expected_expressed,
        ):
            with self.subTest(locator=record["source_locator"]):
                self.assertEqual(record["source_locator"], official["source_locator"])
                self.assertEqual(record["official_page"], official["official_page"])
                self.assertEqual(record["canonical_candidates"], official["candidates"])
                self.assertEqual(official["expressed_intentions"], expressed)
                self.assertEqual(record["canonical_factual_key"]["sample_size"], 1393)
                self.assertEqual(record["canonical_factual_key"]["sample_scope"], "registered_voters")
                self.assertEqual(record["evidence_urls"], [self.primary["source_url"]])

    def test_later_page_revisions_reuse_only_exact_reviewed_targets(self):
        metadata = self.primary["subsequent_mediawiki_fixture"]
        path = FIXTURES / metadata["filename"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), metadata["sha256"])
        parsed = read(metadata["filename"])["parse"]
        self.assertEqual(parsed["revid"], metadata["revision_id"])
        rows = parse_french_frozen_fixture(parsed)[FIRST_ROUND]
        self.assertEqual(rows, self.rows)
        result = self.run_lane(rows=rows, revision=metadata["revision_id"])
        self.assertEqual(result.events, self.run_lane().events)
        self.assertEqual(result.excluded, {"FR-T0R28"})
        for revision in (metadata["revision_id"] + 1, 240133071, 240133072):
            with self.subTest(revision=revision):
                later = self.run_lane(rows=rows, revision=revision)
                self.assertEqual(later.events, result.events)
                self.assertEqual(later.excluded, {"FR-T0R28"})

    def test_original_audit_stays_at_75_and_lane_is_separate(self):
        original = load_migration_registry()
        self.assertEqual(len(original["reviewed_reconciliations"]), 75)
        self.assertEqual(len(self.registry["corrections"]), 11)
        result = self.run_lane()
        self.assertEqual(result.report["correct_retained_sample"], 9)
        self.assertEqual(result.report["supersede_event"], 1)
        self.assertEqual(result.report["excluded_source_rows"], 1)

    def test_nine_metadata_ids_retained_and_one_explicit_successor(self):
        result = self.run_lane()
        self.assertEqual(len(result.events), 10)
        validate_poll_events(result.events)
        by_id = {event["event_id"]: event for event in result.events}
        for record in self.retained:
            event = by_id[record["canonical_event_id"]]
            self.assertEqual(exact_factual_key(event).to_dict(), record["canonical_factual_key"])
            if record["action"] == "correct_retained_sample":
                self.assertIn(record["previous_event_id"], by_id)
            else:
                self.assertNotIn(record["previous_event_id"], by_id)
                self.assertEqual(event["supersedes_event_id"], record["previous_event_id"])
        self.assertEqual(
            set(e["event_id"] for e in self.previous) - set(by_id),
            set(result.report["superseded_event_ids"]),
        )

    def test_ruffin_complete_lineup_is_independently_verified(self):
        record = self.retained[-1]
        self.assertEqual(record["source_locator"], "FR-T0R10")
        event = next(e for e in self.run_lane().events if e["event_id"] == record["canonical_event_id"])
        self.assertEqual(event["reported_total"], 100)
        self.assertEqual(len(event["candidates"]), 14)
        self.assertIn({"name": "François Ruffin", "score": 3}, event["candidates"])
        self.assertEqual(event["candidates"], self.primary["scenarios"][-1]["candidates"])

    def test_canonical_ruffin_omission_does_not_pass(self):
        result = self.run_lane()
        altered = copy.deepcopy(result.events)
        successor = next(e for e in altered if e.get("supersedes_event_id"))
        successor["candidates"] = [c for c in successor["candidates"] if c["name"] != "François Ruffin"]
        apply_completeness_contract(successor)
        with self.assertRaises(ValueError):
            self.run_lane(previous=altered)

    def test_exact_replay_idempotency_and_determinism(self):
        first = self.run_lane()
        second = self.run_lane(previous=first.events)
        self.assertEqual(first.events, second.events)
        self.assertEqual(second.report["already_applied"], 10)
        self.assertEqual(second.report["superseded_event_ids"], [])
        self.assertEqual(second.report["correct_retained_sample"], 0)
        self.assertEqual(first.events, self.run_lane().events)
        self.assertEqual(parse_french_frozen_fixture(self.parsed), parse_french_frozen_fixture(self.parsed))

    def test_exact_historical_representation_replays_canonical_facts(self):
        rows = copy.deepcopy(self.rows)
        rows = [r for r in rows if r["source_url"] != self.historical["source_url"]]
        for row in rows:
            if row["source_locator"] in {r["source_locator"] for r in self.retained}:
                row["sample_size"] = 1597
        original = self.run_lane(rows=rows, revision=240063728)
        applied = self.run_lane(rows=rows, revision=240063728, previous=original.events)
        self.assertEqual(original.events, applied.events)
        self.assertEqual(original.events, self.run_lane().events)

    def test_near_samples_fail_closed(self):
        for sample in (1526, 1528, 1393, 1597):
            with self.subTest(sample=sample), self.assertRaisesRegex(ValueError, "scope/facts"):
                self.run_lane(rows=self.mutated_row(lambda r: r.update(sample_size=sample)))

    def test_mutated_score_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "scope/facts"):
            self.run_lane(rows=self.mutated_row(lambda r: r["candidates"][0].update(score=1)))

    def test_mutated_candidate_membership_fails_closed(self):
        for locator in ("FR-T0R1", "FR-T0R10"):
            with self.subTest(locator=locator), self.assertRaisesRegex(ValueError, "scope/facts"):
                self.run_lane(rows=self.mutated_row(lambda r: r["candidates"].pop(), locator))

    def test_pre_review_revision_locator_and_url_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "scope/facts"):
            self.run_lane(revision=240128357)
        for fields in ({"source_locator": "FR-T0R999"}, {"source_url": "https://example.org/unreviewed"}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, "scope/facts"):
                self.run_lane(rows=self.mutated_row(lambda r: r.update(fields)))

    def test_later_revision_target_mutations_still_fail_closed(self):
        mutations = [
            lambda r: r.update(sample_size=1528),
            lambda r: r.update(sample_scope="registered_voters"),
            lambda r: r["candidates"][0].update(score=1),
            lambda r: r["candidates"].pop(),
            lambda r: r.update(fieldwork_start="2026-09-24"),
            lambda r: r.update(fieldwork_end="2026-09-30"),
            lambda r: r.update(pollster="Ipsos"),
            lambda r: r.update(source_url="https://example.org/unreviewed"),
            lambda r: r.update(source_locator="FR-T0R999"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaisesRegex(ValueError, "scope/facts"):
                self.run_lane(rows=self.mutated_row(mutate), revision=240133071)
        rows = copy.deepcopy(self.rows)
        extra = copy.deepcopy(next(r for r in rows if r["source_locator"] == "FR-T0R1"))
        extra.update(source_locator="FR-T0R999", sample_size=1528)
        with self.assertRaisesRegex(ValueError, "unregistered row"):
            self.run_lane(rows=rows + [extra], revision=240133071)

    def test_unknown_anchor_collision_and_duplicate_row_fail_closed(self):
        rows = copy.deepcopy(self.rows)
        extra = copy.deepcopy(next(r for r in rows if r["source_locator"] == "FR-T0R1"))
        extra.update(source_locator="FR-T0R999", sample_size=1528)
        with self.assertRaisesRegex(ValueError, "unregistered row"):
            self.run_lane(rows=rows + [extra])
        with self.assertRaisesRegex(ValueError, "duplicate incoming"):
            self.run_lane(rows=rows + [rows[0]])

    def test_prior_unreviewed_mutation_and_both_supersession_ids_fail(self):
        previous = copy.deepcopy(self.previous)
        previous[0]["sample_size"] = 1596
        with self.assertRaisesRegex(ValueError, "unexpected facts"):
            self.run_lane(previous=previous)
        canonical = self.run_lane().events
        successor = next(e for e in canonical if e.get("supersedes_event_id"))
        with self.assertRaisesRegex(ValueError, "both event identities"):
            self.run_lane(previous=self.previous + [successor])

    def test_unrelated_row_is_withheld_and_mutations_fail_closed(self):
        exclusion = self.historical
        result = self.run_lane()
        self.assertEqual(result.excluded, {"FR-T0R28"})
        for revision in (240128358, 240133071):
            for fields in ({"sample_size": 1549}, {"sample_scope": "registered_voters"}, {"source_locator": "FR-T0R999"}, {"source_url": "https://example.org/changed"}):
                with self.subTest(revision=revision, fields=fields), self.assertRaisesRegex(ValueError, "withheld"):
                    self.run_lane(rows=self.mutated_row(lambda r: r.update(fields), exclusion["source_locator"]), revision=revision)

    def test_full_migration_and_fetch_integration_preserve_corrected_facts(self):
        first = read("post_audit_first_round_9579b90.json") + self.previous + read("notice_10270_previous_events.json")
        # Use the published, already-applied runoff lifecycle; this lane must
        # leave second-round provenance and identity behavior untouched.
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        parsed = copy.deepcopy(self.parsed)
        parsed["revid"] = 240133071
        migration = reconcile_french_production_source(parsed, first, second)
        events, runoffs, report, _ = integrate_french_migration_source(parsed, first, second, [])
        by_id = {event["event_id"]: event for event in events}
        self.assertEqual(len(by_id), len(events))
        self.assertEqual(runoffs, migration.second_round_events)
        for record in self.retained:
            self.assertEqual(exact_factual_key(by_id[record["canonical_event_id"]]).to_dict(), record["canonical_factual_key"])
        self.assertFalse(any(e["source_url"] == self.historical["source_url"] for e in events))
        repeated, repeated_runoffs, _, _ = integrate_french_migration_source(parsed, events, runoffs, [])
        self.assertEqual(events, repeated)
        self.assertEqual(runoffs, repeated_runoffs)
        self.assertEqual(report["post_audit_first_round_corrections"]["correct_retained_sample"], 9)


class Notice10292AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load_corrections()["corrections"][-1]
        cls.registry = {
            "schema_version": "1.0", "corrections": [cls.record],
            "excluded_source_rows": [],
        }
        cls.parsed = read("fr_mediawiki_240128358.json")["parse"]
        rows = parse_french_frozen_fixture(cls.parsed)[FIRST_ROUND]
        cls.row = copy.deepcopy(next(r for r in rows if r["source_url"] == cls.record["source_url"]))
        cls.row["source_locator"] = "FR-T0R27"
        cls.previous = read("notice_10284_previous_events.json")

    def run_lane(self, *, rows=None, previous=None, revision=240180750):
        return reconcile_first_round_corrections(
            [self.row] if rows is None else rows, revision,
            self.previous if previous is None else previous, registry=self.registry,
        )

    def test_reviewed_representation_becomes_registered_voter_event(self):
        self.assertEqual((self.row["sample_size"], self.row.get("sample_scope", "reported")), (1548, "reported"))
        result = self.run_lane()
        event = next(e for e in result.events if e["source_url"] == self.record["source_url"])
        self.assertEqual((event["sample_size"], event["sample_scope"]), (1443, "registered_voters"))
        self.assertEqual((event["fieldwork_start"], event["fieldwork_end"]), ("2026-09-09", "2026-09-11"))
        self.assertEqual(event["source_url"], self.row["source_url"])
        self.assertEqual(event["migration_source_locator"], "FR-T0R27")
        self.assertEqual(event["candidates"], self.row["candidates"])
        self.assertEqual(dict(exact_factual_key(event).candidates), {
            "nathalie-arthaud": "0.5", "jean-luc-melenchon": "17",
            "fabien-roussel": "2", "marine-tondelier": "3",
            "raphael-glucksmann": "9", "gabriel-attal": "7",
            "edouard-philippe": "14", "bruno-retailleau": "6.5",
            "nicolas-dupont-aignan": "2", "marine-le-pen": "35", "eric-zemmour": "4",
        })
        self.assertEqual(result.report["accept_reviewed_sample"], 1)
        self.assertEqual(result.excluded, set())
        self.assertEqual(set(result.handled), {"FR-T0R27"})
        repeated = self.run_lane(previous=result.events)
        self.assertEqual(repeated.events, result.events)
        self.assertEqual(repeated.report["already_applied"], 1)
        self.assertEqual(self.run_lane(revision=240180751).events, result.events)

    def test_unrelated_locator_occupants_and_moved_row_are_not_accepted(self):
        unrelated = copy.deepcopy(self.row)
        unrelated.update(pollster="OpinionWay", fieldwork_start="2026-09-15", source_url="https://example.org/other")
        for locator in ("FR-T0R27", "FR-T0R28"):
            unrelated["source_locator"] = locator
            with self.subTest(locator=locator), self.assertRaises(ValueError):
                self.run_lane(rows=[unrelated])
        moved = copy.deepcopy(self.row)
        moved["source_locator"] = "FR-T0R28"
        with self.assertRaisesRegex(ValueError, "scope/facts"):
            self.run_lane(rows=[moved, {**unrelated, "source_locator": "FR-T0R27"}])
        # An unrelated R28 alongside exact reviewed R27 is not handled by this lane.
        result = self.run_lane(rows=[self.row, {**unrelated, "source_locator": "FR-T0R28"}])
        self.assertEqual(set(result.handled), {"FR-T0R27"})

    def test_score_and_candidate_lineup_changes_fail_closed(self):
        for mutate in (
            lambda r: r["candidates"][0].update(score=1),
            lambda r: r["candidates"].pop(),
            lambda r: r["candidates"][0].update(name="François Ruffin"),
        ):
            row = copy.deepcopy(self.row)
            mutate(row)
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "scope/facts"):
                self.run_lane(rows=[row])

    def test_url_dates_pollster_and_sample_representation_changes_fail_closed(self):
        for fields in (
            {"source_url": "https://example.org/changed"},
            {"fieldwork_start": "2026-09-08"}, {"fieldwork_end": "2026-09-12"},
            {"pollster": "Ipsos"}, {"sample_size": 1549}, {"sample_size": 1443},
            {"sample_scope": "registered_voters"}, {"source_locator": "FR-T0R28"},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.run_lane(rows=[{**self.row, **fields}], revision=240180751)

    def test_unregistered_same_notice_or_wave_fails_closed(self):
        for fields in ({"fieldwork_start": "2026-09-08"}, {"source_url": "https://example.org/other"}):
            extra = {**copy.deepcopy(self.row), **fields, "source_locator": "FR-T0R999"}
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, "unregistered row"):
                self.run_lane(rows=[self.row, extra])

    def test_prior_event_drift_and_missing_reviewed_wave_fail_closed(self):
        result = self.run_lane()
        for mutate in (
            lambda e: e.update(sample_size=1444),
            lambda e: e["candidates"][0].update(score=1),
        ):
            previous = copy.deepcopy(result.events)
            event = next(e for e in previous if e["source_url"] == self.row["source_url"])
            mutate(event)
            apply_completeness_contract(event)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, "unexpected facts"):
                self.run_lane(previous=previous)
        with self.assertRaisesRegex(ValueError, "wave is missing"):
            self.run_lane(rows=[])

    def test_historical_withholding_is_superseded_only_at_review(self):
        old = {**self.row, "source_locator": "FR-T0R28"}
        for revision in (240128358, 240131611, 240133071):
            result = self.run_lane(rows=[old], revision=revision)
            self.assertEqual(result.events, self.previous)
            self.assertEqual(result.excluded, {"FR-T0R28"})
            self.assertEqual(result.report["accept_reviewed_sample"], 0)
        with self.assertRaisesRegex(ValueError, "withheld"):
            self.run_lane(revision=240180749)
        self.assertEqual(load_corrections()["excluded_source_rows"], [])

    def test_historical_blank_companion_stays_parser_rejected_and_unpublished(self):
        parsed = parse_french_frozen_fixture(self.parsed)
        self.assertTrue(any(r["source_locator"] == "FR-T0R27" and r["reason_code"] == "unnamed_generic_candidate" for r in parsed["rejected"]))
        # Simulate a parseable historical companion; it still has no acceptance.
        blank = copy.deepcopy(self.row)
        scores = [0.5, 16, 2, 2.5, 8, 6, 13, 6, 2, 34, 4]
        for candidate, score in zip(blank["candidates"], scores):
            candidate["score"] = score
        blank["candidates"].append({"name": "vote blanc", "score": 6})
        blank["source_locator"] = "FR-T0R999"
        with self.assertRaisesRegex(ValueError, "unregistered row"):
            self.run_lane(rows=[self.row, blank])

    def test_full_fetch_integration_accepts_only_ordinary_scenario(self):
        from lxml import html
        parsed = copy.deepcopy(self.parsed)
        tree = html.fromstring(parsed["text"])
        link = tree.xpath('//a[contains(@href,"10292-pres-vote-blanc")]')[0]
        companion = link
        while companion.tag != "tr":
            companion = companion.getparent()
        ordinary = companion.getnext()
        # Model only the reviewed removal; existing frozen fixture stays intact.
        for cell in reversed(list(companion)[:3]):
            cell.attrib.pop("rowspan", None)
            ordinary.insert(0, cell)
        companion.getparent().remove(companion)
        parsed["text"] = html.tostring(tree, encoding="unicode")
        parsed["revid"] = 240180750
        first = read("post_audit_first_round_9579b90.json") + self.previous + read("notice_10270_previous_events.json")
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        events, runoffs, report, _ = integrate_french_migration_source(parsed, first, second, [])
        accepted = [e for e in events if e["source_url"] == self.row["source_url"]]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(exact_factual_key(accepted[0]).to_dict(), self.record["canonical_factual_key"])
        self.assertEqual(accepted[0]["candidates"], self.row["candidates"])
        self.assertEqual(report["post_audit_first_round_corrections"]["accept_reviewed_sample"], 1)
        for record in load_corrections()["corrections"]:
            event = next(e for e in events if e["event_id"] == record["canonical_event_id"])
            self.assertEqual(exact_factual_key(event).to_dict(), record["canonical_factual_key"])
        repeated, repeated_runoffs, _, _ = integrate_french_migration_source(parsed, events, runoffs, [])
        self.assertEqual(events, repeated)
        self.assertEqual(runoffs, repeated_runoffs)


class PostAuditCorrectionSchemaTests(unittest.TestCase):
    def setUp(self):
        self.registry = copy.deepcopy(load_corrections())

    def assert_invalid(self, mutate, pattern=None):
        mutate(self.registry)
        with self.assertRaisesRegex(ValueError, pattern or ".+"):
            validate_corrections(self.registry)

    def test_schema_version_and_unexpected_fields(self):
        for value in ("2.0", 1, None):
            payload = copy.deepcopy(self.registry)
            payload["schema_version"] = value
            with self.assertRaises(ValueError):
                validate_corrections(payload)
        self.assert_invalid(lambda p: p.update(unexpected=True), "schema")

    def test_each_required_record_field_and_unexpected_fields(self):
        for index in (0, -1):
            for field in set(self.registry["corrections"][index]) - {"source_variants", "historical_incoming_factual_key", "additional_previous_events"}:
                payload = copy.deepcopy(self.registry)
                del payload["corrections"][index][field]
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    validate_corrections(payload)
        self.assert_invalid(lambda p: p["corrections"][0].update(unexpected=True), "fields")

    def test_acceptance_history_and_canonical_sample_only_schema_are_strict(self):
        mutations = (
            lambda r: r.update(unexpected=True),
            lambda r: r.update(previous_event_id=r["canonical_event_id"]),
            lambda r: r["historical_withheld_source"].update(source_revisions=[240180750]),
            lambda r: r["historical_withheld_source"].update(source_url="https://example.org/changed"),
            lambda r: r["historical_withheld_source"]["factual_key"].update(sample_size=1549),
            lambda r: r["canonical_factual_key"].update(fieldwork_start="2026-09-08"),
            lambda r: r["canonical_factual_key"]["candidates"][0].update(score="7"),
            lambda r: r.update(canonical_event_id="0" * 64),
            lambda r: r.update(canonical_hypothesis="unreviewed"),
        )
        for index, mutate in enumerate(mutations):
            payload = copy.deepcopy(self.registry)
            mutate(payload["corrections"][-1])
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                validate_corrections(payload)

    def test_duplicate_locator(self):
        self.assert_invalid(lambda p: p["corrections"][1].update(source_locator="FR-T0R1"), "duplicate")

    def test_duplicate_incoming_key(self):
        self.assert_invalid(lambda p: p["corrections"][1].update(incoming_factual_key=p["corrections"][0]["incoming_factual_key"]), "duplicate")

    def test_ambiguous_canonical_target(self):
        self.assert_invalid(lambda p: p["corrections"][1].update(canonical_event_id=p["corrections"][0]["canonical_event_id"]), "ambiguous")

    def test_evidence_urls_and_reason(self):
        for field, value in (("evidence_urls", []), ("evidence_urls", ["file:///bad"]), ("source_url", "not-a-url"), ("review_reason", " ")):
            payload = copy.deepcopy(self.registry)
            payload["corrections"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_corrections(payload)

    def test_actions_and_scope_are_strict(self):
        for field, value in (("action", "guess"), ("incoming_source_revisions", [240128358, 240128246]), ("incoming_source_revisions", [True]), ("historical_source_revision", 240128358), ("official_page", 0)):
            payload = copy.deepcopy(self.registry)
            payload["corrections"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_corrections(payload)

    def test_metadata_correction_cannot_change_candidates(self):
        self.assert_invalid(lambda p: p["corrections"][0]["canonical_candidates"][0].update(score=1), "contradict")

    def test_canonical_candidate_fields_are_strict(self):
        for candidates in (None, [], [{"name": "Nathalie Arthaud", "score": 0.5, "unexpected": True}]):
            self.assert_invalid(
                lambda p: p["corrections"][0].update(canonical_candidates=candidates), "fields",
            )
        self.assert_invalid(
            lambda p: p["corrections"][0]["canonical_candidates"][0].update(unexpected=True), "fields",
        )

    def test_candidate_correction_cannot_silently_retain_identity(self):
        self.assert_invalid(lambda p: p["corrections"][9].update(action="correct_retained_sample"), "non-sample facts|identity")

    def test_exclusion_schema_and_overlapping_locators(self):
        self.registry["excluded_source_rows"] = [copy.deepcopy(self.registry["corrections"][-1]["historical_withheld_source"])]
        self.assert_invalid(lambda p: p["excluded_source_rows"][0].update(source_locator="FR-T0R1"), "duplicate")


if __name__ == "__main__":
    unittest.main()



class ReviewedCandidateExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from reviewed_candidate_expansions import REGISTRY
        cls.payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.records = cls.payload["expansions"]
        cls.rows = [copy.deepcopy(r["incoming_row"]) for r in cls.records]
        cls.previous = json.loads(
            (FIXTURES / "pre_candidate_expansion_first_round_23a2bbd.json").read_text(encoding="utf-8")
        )
        cls.source_review = read("elabe_10324_source_review.json")
        cls.refreshed_parsed = read("fr_mediawiki_240485606.json")["parse"]
        cls.refreshed_rows = parse_french_frozen_fixture(cls.refreshed_parsed)[FIRST_ROUND]

    def run_expansion(self, rows=None, previous=None, revision=240470913,
                      registry_path=None):
        from reviewed_candidate_expansions import (
            REGISTRY, reconcile_reviewed_candidate_expansions,
        )
        return reconcile_reviewed_candidate_expansions(
            self.rows if rows is None else rows,
            revision,
            self.previous if previous is None else previous,
            registry_path=REGISTRY if registry_path is None else registry_path,
        )

    def test_frozen_pre_expansion_corpus_integrity(self):
        # Exact polls.json bytes from 23a2bbd01e2f292d7b7e2fea18b44aa3e8cf4cbf.
        name = "pre_candidate_expansion_first_round_23a2bbd.json"
        raw = (FIXTURES / name).read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "fed336f0b12adb43866d8bc7e9c7a2580e979217198d47d4aa4eda49f0c9e91a",
        )
        self.assertEqual(len(self.previous), 316)
        self.assertNotIn(b"\r", raw)
        self.assertIn(
            f"/test_fixtures/fr27_polling/{name} text eol=lf",
            (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines(),
        )
        validate_poll_events(self.previous)

    def test_production_successors_replay_deterministically_without_changes(self):
        # This publication contract allows future additions without pinning a count.
        published = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
        before = {event["event_id"]: event for event in published}
        old_ids = {record["previous_event"]["event_id"] for record in self.records}
        new_ids = {record["canonical_event_id"] for record in self.records}
        self.assertEqual(len(before), len(published))
        self.assertEqual(len(new_ids), 3)
        self.assertTrue(new_ids <= before.keys())
        self.assertTrue(old_ids.isdisjoint(before))

        replay = self.run_expansion(previous=published)
        self.assertEqual(replay.events, published)
        self.assertEqual((replay.applied, replay.already_applied), (0, 3))
        self.assertEqual(replay.canonical_event_ids, sorted(new_ids))
        self.assertEqual(replay.superseded_event_ids, [])
        self.assertEqual(replay.covered_persistence_ids, sorted(old_ids))
        self.assertEqual(replay, self.run_expansion(previous=published))
        self.assertEqual(
            replay,
            self.run_expansion(rows=list(reversed(self.rows)),
                               previous=replay.events, revision=240470914),
        )
        validate_poll_events(replay.events)

    def test_exact_three_successors_and_313_other_events_preserved(self):
        result = self.run_expansion()
        old_ids = {r["previous_event"]["event_id"] for r in self.records}
        new_ids = {r["canonical_event_id"] for r in self.records}
        before = {e["event_id"]: e for e in self.previous}
        after = {e["event_id"]: e for e in result.events}

        self.assertEqual((result.applied, result.already_applied), (3, 0))
        self.assertEqual(len(before), 316)
        self.assertEqual(len(after), 316)
        self.assertEqual(set(before) - set(after), old_ids)
        self.assertEqual(set(after) - set(before), new_ids)
        self.assertEqual(
            result.superseded_event_ids, sorted(old_ids)
        )
        self.assertEqual(result.canonical_event_ids, sorted(new_ids))
        self.assertEqual(result.covered_persistence_ids, sorted(old_ids))

        for event_id in set(before) & set(after):
            self.assertEqual(before[event_id], after[event_id])

        for record in self.records:
            event = after[record["canonical_event_id"]]
            self.assertEqual(
                event["supersedes_event_id"],
                record["previous_event"]["event_id"],
            )
            self.assertEqual(event["source_url"], record["incoming_row"]["source_url"])
            self.assertEqual(event["reported_total"], 100)
            self.assertEqual(event["completeness_status"], "complete")

        validate_poll_events(result.events)

    def test_idempotent_replay_and_later_revision(self):
        first = self.run_expansion()
        again = self.run_expansion(
            previous=first.events, revision=240470914
        )
        self.assertEqual(first.events, again.events)
        self.assertEqual(again.applied, 0)
        self.assertEqual(again.already_applied, 3)
        self.assertEqual(again.superseded_event_ids, [])
        expected_old = sorted(
            record["previous_event"]["event_id"]
            for record in self.records
        )
        self.assertEqual(again.covered_persistence_ids, expected_old)

    def test_pre_review_revision_does_not_apply_expansions(self):
        result = self.run_expansion(revision=240470912)
        self.assertEqual(result.events, self.previous)
        self.assertEqual(result.canonical_event_ids, [])
        self.assertEqual(result.superseded_event_ids, [])

    def test_each_incoming_source_mutation_fails_closed(self):
        mutations = (
            lambda r: r["candidates"][0].update(score=99),
            lambda r: r["candidates"].pop(),
            lambda r: r["candidates"].append(
                {"name": "Unreviewed Candidate", "score": 1}
            ),
            lambda r: r.update(sample_size=9999),
            lambda r: r.update(
                source_url="https://example.org/unreviewed"
            ),
            lambda r: r.update(source_locator="FR-T9R999"),
            lambda r: r.update(fieldwork_end="2026-10-17"),
        )
        for index in range(3):
            for mutate in mutations:
                rows = copy.deepcopy(self.rows)
                mutate(rows[index])
                with self.subTest(index=index, mutate=mutate):
                    with self.assertRaisesRegex(
                        ValueError, "source facts/provenance changed"
                    ):
                        self.run_expansion(rows=rows)

    def test_unreviewed_historical_change_fails_closed(self):
        old_id = self.records[0]["previous_event"]["event_id"]
        events = copy.deepcopy(self.previous)
        target = next(e for e in events if e["event_id"] == old_id)
        target["candidates"][0]["score"] = 99
        with self.assertRaises(ValueError):
            self.run_expansion(previous=events)

    def test_missing_or_mixed_identity_fails_closed(self):
        from reviewed_candidate_expansions import _canonical_event
        old_id = self.records[0]["previous_event"]["event_id"]
        successor = _canonical_event(self.rows[0], old_id)

        mixed = copy.deepcopy(self.previous) + [successor]
        with self.assertRaisesRegex(ValueError, "both historical"):
            self.run_expansion(previous=mixed)

        missing = [
            e for e in self.previous if e["event_id"] != old_id
        ]
        with self.assertRaisesRegex(ValueError, "neither historical"):
            self.run_expansion(previous=missing)

    def test_elabe_source_refresh_fixture_and_primary_evidence(self):
        metadata = self.source_review
        fixture = metadata["wikipedia_fixture"]
        self.assertEqual(
            hashlib.sha256((FIXTURES / fixture["filename"]).read_bytes()).hexdigest(),
            "b1f8478756a50f29302a19596e3538cfbfd501a4c3a484c8d3f015bd40ebf3de",
        )
        self.assertEqual(fixture["sha256"],
                         "b1f8478756a50f29302a19596e3538cfbfd501a4c3a484c8d3f015bd40ebf3de")
        self.assertEqual(self.refreshed_parsed["revid"], 240485606)
        for name in (fixture["filename"], "elabe_10324_source_review.json"):
            self.assertFalse(b"\r" in (FIXTURES / name).read_bytes(), name)
            self.assertIn(
                f"/test_fixtures/fr27_polling/{name} text eol=lf",
                (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines(),
            )
        historical = self.records[0]["incoming_row"]
        refreshed = next(r for r in self.refreshed_rows if r["source_locator"] == "FR-T0R5")
        self.assertEqual(metadata["changed_fields"], ["source_url"])
        self.assertEqual(refreshed, {
            **historical, "source_url": metadata["commission_notice"]["source_url"],
        })
        self.assertEqual(exact_factual_key(historical), exact_factual_key(refreshed))
        self.assertEqual(metadata["survey"]["candidates"], historical["candidates"])
        self.assertEqual(sum(c["score"] for c in metadata["survey"]["candidates"]), 100)
        self.assertEqual(
            (metadata["survey"]["total_adults"], metadata["survey"]["registered_voters"],
             historical["sample_size"], historical["sample_scope"]),
            (1701, 1553, 1701, "reported"),
        )
        self.assertEqual(metadata["survey"]["configuration"], 5)
        self.assertEqual(metadata["commission_notice"]["sha256"],
                         "a8a95533cad304be016080af5960ec928c8a6d4c49089e6c11b851feb4f235d8")
        self.assertEqual(metadata["elabe_report"]["sha256"],
                         "edbb125fd84f90b26fe6d98e8e42563ca0e876fb46804e23937e99d2e1dd8f99")

    def test_elabe_historical_and_reviewed_sources_keep_the_published_id(self):
        historical = self.run_expansion()
        refreshed = self.run_expansion(rows=self.refreshed_rows, revision=240485606)
        self.assertEqual(refreshed, historical)
        self.assertEqual((refreshed.applied, refreshed.already_applied), (3, 0))
        canonical_id = "63aecb7f3bd59f50845e47dc628ed7d480330d1a028228561ad2cc6a3bb1afb0"
        canonical = next(e for e in refreshed.events if e["event_id"] == canonical_id)
        self.assertEqual(canonical["source_url"], self.records[0]["incoming_row"]["source_url"])
        # The reviewed notice is evidence, never a new source input to event IDs.
        from reviewed_candidate_expansions import _canonical_event
        row = next(r for r in self.refreshed_rows if r["source_locator"] == "FR-T0R5")
        would_be_duplicate = _canonical_event(row, self.records[0]["previous_event"]["event_id"])
        self.assertNotEqual(would_be_duplicate["event_id"], canonical_id)
        self.assertNotIn(would_be_duplicate["event_id"], {e["event_id"] for e in refreshed.events})

    def test_elabe_reviewed_source_replay_is_deterministic_and_idempotent(self):
        first = self.run_expansion(rows=self.refreshed_rows, revision=240485606)
        for revision in (240485523, 240485606, 240490172, 240490173):
            with self.subTest(revision=revision):
                replay = self.run_expansion(rows=list(reversed(self.refreshed_rows)),
                                            previous=first.events, revision=revision)
                self.assertEqual(replay.events, first.events)
                self.assertEqual((replay.applied, replay.already_applied), (0, 3))
                self.assertEqual(replay.superseded_event_ids, [])
                self.assertEqual(replay.canonical_event_ids, first.canonical_event_ids)
                self.assertEqual(replay.covered_persistence_ids, first.covered_persistence_ids)

    def test_elabe_source_refresh_requires_the_reviewed_revision_boundary(self):
        for revision in (240470913, 240470914, 240485522):
            with self.subTest(revision=revision), self.assertRaisesRegex(
                ValueError, "source facts/provenance changed: FR-T0R5",
            ):
                self.run_expansion(rows=self.refreshed_rows, revision=revision)
        # Earlier audited fixtures remain independent of all later expansions.
        early = self.run_expansion(rows=self.refreshed_rows, revision=238906992)
        self.assertEqual(early.events, self.previous)
        self.assertEqual((early.applied, early.already_applied), (0, 0))

    def test_elabe_refreshed_source_still_rejects_every_unreviewed_field(self):
        mutations = (
            lambda r: r.update(sample_size=1700),
            lambda r: r.update(sample_size=1553),
            lambda r: r.update(sample_scope="registered_voters"),
            lambda r: r.update(pollster="ELABE"),
            lambda r: r.update(fieldwork_start="2026-10-13"),
            lambda r: r.update(fieldwork_end="2026-10-17"),
            lambda r: r.update(round="second_round"),
            lambda r: r.update(source_locator="FR-T0R999"),
            lambda r: r["candidates"][5].update(score=4.4),
            lambda r: r["candidates"].pop(5),
            lambda r: r["candidates"][5].update(name="Unreviewed Candidate"),
            lambda r: r["candidates"].append({"name": "New Candidate", "score": 0}),
            lambda r: r["candidates"].reverse(),
            lambda r: r.update(unreviewed_metadata=True),
            lambda r: r.update(source_url="https://example.org/unreviewed"),
            lambda r: r.update(source_url=self.source_review["commission_notice"]["source_url"].replace("10324", "10325")),
            lambda r: r.update(source_url=self.source_review["commission_notice"]["source_url"].replace("https:", "http:")),
            lambda r: r.update(source_url=self.source_review["commission_notice"]["source_url"] + "?unreviewed=1"),
        )
        for revision in (240485606, 240490172):
            for index, mutate in enumerate(mutations):
                rows = copy.deepcopy(self.refreshed_rows)
                row = next(r for r in rows if r["source_locator"] == "FR-T0R5")
                mutate(row)
                with self.subTest(revision=revision, mutation=index), self.assertRaisesRegex(
                    ValueError, "source facts/provenance changed: FR-T0R5",
                ):
                    self.run_expansion(rows=rows, revision=revision)
        for index in (1, 2):
            rows = copy.deepcopy(self.refreshed_rows)
            row = next(r for r in rows if r["source_locator"] == self.records[index]["source_locator"])
            row["source_url"] = self.source_review["commission_notice"]["source_url"]
            with self.subTest(other_expansion=index), self.assertRaisesRegex(
                ValueError, "source facts/provenance changed",
            ):
                self.run_expansion(rows=rows, revision=240485606)

    def test_elabe_refreshed_source_keeps_historical_identity_guards(self):
        first = self.run_expansion()
        canonical_id = self.records[0]["canonical_event_id"]
        successor = next(e for e in first.events if e["event_id"] == canonical_id)
        old_id = self.records[0]["previous_event"]["event_id"]
        with self.assertRaisesRegex(ValueError, "both historical"):
            self.run_expansion(rows=self.refreshed_rows, revision=240485606,
                               previous=self.previous + [successor])
        with self.assertRaisesRegex(ValueError, "neither historical"):
            self.run_expansion(rows=self.refreshed_rows, revision=240485606,
                               previous=[e for e in self.previous if e["event_id"] != old_id])
        altered = copy.deepcopy(first.events)
        next(e for e in altered if e["event_id"] == canonical_id)["source_url"] = self.source_review["commission_notice"]["source_url"]
        with self.assertRaisesRegex(ValueError, "successor facts/provenance changed"):
            self.run_expansion(rows=self.refreshed_rows, revision=240485606, previous=altered)
        with self.assertRaisesRegex(ValueError, "Duplicate incoming"):
            self.run_expansion(rows=self.refreshed_rows + [self.refreshed_rows[0]], revision=240485606)

    def test_elabe_full_fetch_integration_preserves_history_and_runoffs(self):
        first = self.run_expansion().events
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        events, runoffs, report, _ = integrate_french_migration_source(
            self.refreshed_parsed, first, second, [],
        )
        for before, after in ((first, events), (second, runoffs)):
            by_id = {event["event_id"]: event for event in after}
            self.assertEqual(len(by_id), len(after))
            self.assertTrue({e["event_id"] for e in before} <= by_id.keys())
            for event in before:
                self.assertEqual(event, by_id[event["event_id"]])
        target = next(e for e in events if e["event_id"] == self.records[0]["canonical_event_id"])
        target_wave = (target["pollster"], target["fieldwork_start"], target["fieldwork_end"])
        self.assertEqual(sum(
            exact_factual_key(e, sample_scope=e.get("sample_scope", "reported"))
            == exact_factual_key(target) for e in events
            if (e["pollster"], e["fieldwork_start"], e["fieldwork_end"]) == target_wave
        ), 1)
        self.assertTrue({r["previous_event"]["event_id"] for r in self.records}.isdisjoint(e["event_id"] for e in events))
        self.assertEqual(report["post_audit_first_round_corrections"]["reviewed_candidate_expansions"],
                         {"applied": 0, "already_applied": 3})
        self.assertEqual(report["superseded_second_round_event_ids"], [])
        repeated, repeated_runoffs, _, _ = integrate_french_migration_source(
            self.refreshed_parsed, events, runoffs, [],
        )
        self.assertEqual(events, repeated)
        self.assertEqual(runoffs, repeated_runoffs)

    def test_elabe_full_fetch_integration_rejects_unreviewed_provenance(self):
        parsed = copy.deepcopy(self.refreshed_parsed)
        notice_url = self.source_review["commission_notice"]["source_url"]
        self.assertIn(notice_url, parsed["text"])
        parsed["text"] = parsed["text"].replace(notice_url, "https://example.org/unreviewed")
        second = json.loads((ROOT / "second_round_polls.json").read_text(encoding="utf-8"))["events"]
        with self.assertRaisesRegex(ValueError, "source facts/provenance changed: FR-T0R5"):
            integrate_french_migration_source(parsed, self.previous, second, [])

    def test_unregistered_registry_mutation_fails_closed(self):
        import tempfile

        modifications = (
            lambda p: p["expansions"].pop(),
            lambda p: p["expansions"].append(
                copy.deepcopy(p["expansions"][0])
            ),
            lambda p: p["expansions"][0].update(
                evidence_page=999
            ),
            lambda p: p["expansions"][0].update(
                canonical_event_id="0" * 64
            ),
            lambda p: p.update(reviewed_revision=240470914),
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            for modify in modifications:
                payload = copy.deepcopy(self.payload)
                modify(payload)
                path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                with self.subTest(modify=modify):
                    with self.assertRaises(ValueError):
                        self.run_expansion(registry_path=path)



class StructuredSourceCorrectionTests(unittest.TestCase):
    OLD = "4708b7c647cfa31ad8c8db6a257450ebe22c8f1cbcc455e7a03d3e7d5d23523e"
    EARLIER = "07a06aee6b9812cfbd6e897ae5004c4ad268ef5cf29ce95c8c0ff2afed183a3a"
    NEW = "44a6411d5cbb73e264613fcd90f0857576049bd039fd189db6c10e5028eda108"

    @classmethod
    def setUpClass(cls):
        cls.parsed = read("fr_mediawiki_240287946.json")["parse"]
        cls.rows = parse_french_frozen_fixture(cls.parsed)[FIRST_ROUND]
        cls.previous = read("structured_source_correction_previous_events.json")
        cls.second = read("structured_source_correction_previous_second_round.json")["events"]
        cls.registry = load_corrections()
        cls.record = next(r for r in cls.registry["corrections"] if r["action"] == "consolidate_events")
        cls.expected = reconcile_first_round_corrections(cls.rows,240287946,cls.previous)

    def run_lane(self, rows=None, previous=None, registry=None):
        return reconcile_first_round_corrections(self.rows if rows is None else rows,240287946,
                                                self.previous if previous is None else previous,
                                                registry=self.registry if registry is None else registry)

    def test_primary_complete_hypothesis_and_frozen_provenance(self):
        primary = read("notice_10270_first_round.json")
        self.assertEqual(primary["pdf_sha256"], "4b95c5d1ca180dac1117629532518aaa14e47c71619ad70e002e357386dd24ce")
        self.assertEqual((primary["official_page"],primary["hypothesis"],primary["total_adults"],primary["registered_voters"]),(26,5,1103,1008))
        self.assertEqual({c["name"]:c["score"] for c in primary["weighted_candidates"]},
                         {c["name"]:c["score"] for c in self.record["canonical_candidates"]})
        self.assertEqual(self.record["evidence_urls"],[primary["source_url"]])
        self.assertEqual(self.record["canonical_event_id"],self.NEW)
        self.assertEqual(len(self.record["canonical_candidates"]),16)
        self.assertEqual(sum(c["score"] for c in self.record["canonical_candidates"]),100)

    def test_exact_explicit_successor_removes_reviewed_partial_identity(self):
        events = {e["event_id"]:e for e in self.expected.events}
        self.assertNotIn(self.OLD,events)
        self.assertNotIn(self.EARLIER,events)
        self.assertEqual(events[self.NEW]["supersedes_event_ids"],sorted([self.OLD,self.EARLIER]))
        self.assertNotIn("supersedes_event_id",events[self.NEW])
        self.assertEqual(exact_factual_key(events[self.NEW]).to_dict(),self.record["canonical_factual_key"])
        self.assertEqual(set(self.expected.report["superseded_event_ids"]),{self.OLD,self.EARLIER})
        self.assertEqual(self.expected.report["consolidate_events"],1)
        self.assertEqual((len(self.previous),len(events)),(299,298))

    def test_ifop_and_cluster17_reviewed_ids_and_maps_are_unchanged(self):
        by_id={e["event_id"]:e for e in self.expected.events}
        for identity in ("7ae37b33f52f31df34aa2b1fd0e5a326fff1c7e6b8683255b30472d9fb44309a",
                         "4810851ea958b928b63298fa94fb082afc6cc7d449b2aad41f023953bb1aac36"):
            self.assertEqual(by_id[identity],next(e for e in self.previous if e["event_id"]==identity))

    def test_reordered_explicit_entries_retain_canonical_successor(self):
        rows=copy.deepcopy(self.rows)
        row=next(r for r in rows if r["source_locator"]=="FR-T1R21")
        row["candidates"]=list(reversed(row["candidates"]))
        self.assertEqual(self.run_lane(rows).events,self.expected.events)

    def test_incoming_candidate_score_and_metadata_drift_fail_closed(self):
        for mutate in (lambda r:r["candidates"].pop(), lambda r:r["candidates"][0].update(score=2),
                       lambda r:r.update(sample_size=1104),lambda r:r.update(source_locator="FR-T1R999"),
                       lambda r:r.update(source_url="https://example.org/unreviewed")):
            rows=copy.deepcopy(self.rows)
            mutate(next(r for r in rows if r["source_locator"]=="FR-T1R21"))
            with self.subTest(mutate=mutate),self.assertRaisesRegex(ValueError,"scope/facts"):
                self.run_lane(rows)

    def test_replay_is_deterministic_and_idempotent(self):
        self.assertEqual(self.run_lane().events,self.expected.events)
        repeated=self.run_lane(previous=self.expected.events)
        self.assertEqual(repeated.events,self.expected.events)
        self.assertEqual(repeated.report["superseded_event_ids"],[])

    def test_no_implicit_correction_without_review_record(self):
        from unittest.mock import patch
        registry=copy.deepcopy(self.registry)
        registry["corrections"]=[r for r in registry["corrections"] if r["incoming_factual_key"]["pollster_identity"]!="yougov"]
        with patch("post_audit_first_round_corrections.load_corrections",return_value=registry):
            with self.assertRaisesRegex(ValueError,"explicit correction required"):
                reconcile_french_production_source(self.parsed,self.previous,self.second)

    def test_duplicate_old_and_successor_fail(self):
        successor=next(e for e in self.expected.events if e["event_id"]==self.NEW)
        with self.assertRaisesRegex(ValueError,"both event identities"):
            self.run_lane(previous=self.previous+[successor])

    def test_full_reconciliation_preserves_all_other_ids_and_runoffs(self):
        result=reconcile_french_production_source(self.parsed,self.previous,self.second)
        self.assertEqual(result.second_round_events,self.second)
        old={e["event_id"] for e in self.previous}; new={e["event_id"] for e in result.first_round_events}
        self.assertEqual(old-new,{self.OLD,self.EARLIER})
        self.assertEqual(new-old,{self.NEW})
        prior={e["event_id"]:e for e in self.previous}
        for event in result.first_round_events:
            if event["event_id"] != self.NEW:
                self.assertEqual(event,prior[event["event_id"]])
                self.assertEqual(json.dumps(event,ensure_ascii=False,separators=(",",":")),
                                 json.dumps(prior[event["event_id"]],ensure_ascii=False,separators=(",",":")))
        self.assertEqual((len(result.first_round_events),len(result.second_round_events)),(298,81))
        repeated=reconcile_french_production_source(self.parsed,result.first_round_events,result.second_round_events)
        self.assertEqual(repeated.first_round_events,result.first_round_events)
        self.assertEqual(repeated.second_round_events,result.second_round_events)

    def test_reviewed_source_variant_schema_rejects_unregistered_provenance(self):
        for update in ({"first_revision":240287947},{"source_locator":None},
                       {"source_locator":"FR-T1Rinvalid"},{"factual_key":{}}):
            registry=copy.deepcopy(self.registry)
            record=next(r for r in registry["corrections"] if r["action"]=="consolidate_events")
            record["source_variants"][0].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError): validate_corrections(registry)

    def altered_registry(self):
        registry=copy.deepcopy(self.registry)
        return registry,next(r for r in registry["corrections"] if r["action"]=="consolidate_events")

    def test_predecessor_evidence_and_historical_provenance_are_explicit(self):
        previous={e["event_id"]:e for e in self.previous}
        self.assertEqual({p["event_id"] for p in self.record["predecessors"]},{self.OLD,self.EARLIER})
        for predecessor in self.record["predecessors"]:
            event=previous[predecessor["event_id"]]
            self.assertEqual(predecessor["factual_key"],exact_factual_key(event).to_dict())
            self.assertEqual(predecessor["source_url"],event["source_url"])
            self.assertEqual(predecessor["source_locator"],event["migration_source_locator"])
            self.assertEqual(predecessor["source_revision"],239927833 if predecessor["event_id"]==self.EARLIER else 240063728)
            self.assertEqual((predecessor["evidence_urls"],predecessor["official_page"]),
                             (self.record["evidence_urls"],26))
            self.assertTrue(predecessor["review_reason"])

    def test_missing_either_or_both_predecessors_fails(self):
        for removed in ({self.OLD},{self.EARLIER},{self.OLD,self.EARLIER}):
            with self.subTest(removed=removed),self.assertRaisesRegex(ValueError,"missing a predecessor or successor"):
                self.run_lane(previous=[e for e in self.previous if e["event_id"] not in removed])

    def test_each_mutated_predecessor_factual_key_fails(self):
        for identity in (self.OLD,self.EARLIER):
            previous=copy.deepcopy(self.previous)
            event=next(e for e in previous if e["event_id"]==identity)
            event["candidates"][0]["score"]+=1
            apply_completeness_contract(event)
            with self.subTest(identity=identity),self.assertRaisesRegex(ValueError,"predecessor facts/provenance"):
                self.run_lane(previous=previous)

    def test_each_mutated_predecessor_provenance_fails(self):
        for identity in (self.OLD,self.EARLIER):
            for field,value in (("source_url","https://example.org/unreviewed"),
                                ("migration_source_locator","FR-T0R999")):
                previous=copy.deepcopy(self.previous)
                next(e for e in previous if e["event_id"]==identity)[field]=value
                with self.subTest(identity=identity,field=field),self.assertRaises(ValueError):
                    self.run_lane(previous=previous)

    def test_canonical_facts_and_provenance_drift_fail_on_replay(self):
        for mutate in (lambda e:e["candidates"][0].update(score=2),
                       lambda e:e.update(sample_size=1104),
                       lambda e:e.update(source_url="https://example.org/unreviewed"),
                       lambda e:e.update(supersedes_event_ids=[self.OLD]),
                       lambda e:e.update(supersedes_event_id=self.OLD)):
            previous=copy.deepcopy(self.expected.events)
            event=next(e for e in previous if e["event_id"]==self.NEW)
            mutate(event);apply_completeness_contract(event)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.run_lane(previous=previous)

    def test_successor_cannot_coexist_with_either_predecessor(self):
        for identity in (self.OLD,self.EARLIER):
            event=next(e for e in self.previous if e["event_id"]==identity)
            with self.subTest(identity=identity),self.assertRaisesRegex(ValueError,"both event identities"):
                self.run_lane(previous=self.expected.events+[event])

    def test_missing_canonical_after_correction_fails(self):
        with self.assertRaisesRegex(ValueError,"missing a predecessor or successor"):
            self.run_lane(previous=[e for e in self.expected.events if e["event_id"]!=self.NEW])

    def test_duplicate_and_unbounded_predecessor_declarations_fail(self):
        for count in (0,1,9):
            registry,record=self.altered_registry()
            record["predecessors"]=(record["predecessors"]*5)[:count]
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,"bounded"):
                validate_corrections(registry)
        registry,record=self.altered_registry()
        record["predecessors"][1]=copy.deepcopy(record["predecessors"][0])
        with self.assertRaisesRegex(ValueError,"duplicate.*predecessor"):
            validate_corrections(registry)

    def test_unknown_predecessor_id_cannot_authorize_removal(self):
        from poll_contract import make_event_id
        registry,record=self.altered_registry()
        predecessor=record["predecessors"][1]
        predecessor["hypothesis"]+=" reviewed unknown"
        key=predecessor["factual_key"]
        predecessor["event_id"]=make_event_id("YouGov",key["fieldwork_start"],key["fieldwork_end"],
                                            predecessor["hypothesis"],predecessor["source_url"])
        validate_corrections(registry)
        with self.assertRaisesRegex(ValueError,"missing a predecessor"):
            self.run_lane(registry=registry)

    def test_duplicate_canonical_and_shared_predecessor_corrections_fail(self):
        registry,record=self.altered_registry()
        registry["corrections"].append(copy.deepcopy(record))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            validate_corrections(registry)
        registry,record=self.altered_registry()
        other=copy.deepcopy(record)
        other["source_locator"]="FR-T0R999"
        other["incoming_factual_key"]["sample_size"]=1104
        registry["corrections"].append(other)
        with self.assertRaisesRegex(ValueError,"ambiguous correction"):
            validate_corrections(registry)

    def test_unrelated_or_incompatible_predecessors_fail(self):
        for field,value in (("pollster_identity","ifop"),("sample_size",1104),
                            ("sample_scope","registered_voters"),("fieldwork_end","2026-09-22")):
            registry,record=self.altered_registry()
            record["predecessors"][1]["factual_key"][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"contradicts"):
                validate_corrections(registry)
        registry,record=self.altered_registry()
        record["predecessors"][1]["factual_key"]["candidates"][0]["score"]="99"
        with self.assertRaisesRegex(ValueError,"contradicts"):validate_corrections(registry)

    def test_predecessor_schema_provenance_and_primary_evidence_are_strict(self):
        for field,value in (("source_url","https://example.org/unreviewed"),
                            ("evidence_urls",[]),("official_page",25),("source_revision",None),
                            ("source_locator","unknown"),("review_reason","")):
            registry,record=self.altered_registry()
            record["predecessors"][1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_corrections(registry)
        for field in self.record["predecessors"][1]:
            registry,record=self.altered_registry();del record["predecessors"][1][field]
            with self.subTest(missing=field),self.assertRaisesRegex(ValueError,"fields"):
                validate_corrections(registry)

    def test_successor_canonical_declaration_cannot_drift(self):
        registry,record=self.altered_registry()
        record["canonical_candidates"][0]["score"]=2
        with self.assertRaisesRegex(ValueError,"contradict"):
            validate_corrections(registry)

    def test_unchanged_workflow_shrink_guard_still_rejects_reviewed_consolidation(self):
        import textwrap
        from fetch_polls import filter_rejected_poll_waves,load_poll_wave_overrides
        workflow=(ROOT/".github/workflows/update-polls.yml").read_text(encoding="utf-8")
        start=workflow.index("          if len(fetched) < len(reviewed_current):")
        end=workflow.index("          required =",start)
        guard=compile(textwrap.dedent(workflow[start:end]),"unchanged workflow shrink guard","exec")
        reviewed,_,_=filter_rejected_poll_waves(self.previous,load_poll_wave_overrides())
        with self.assertRaisesRegex(SystemExit,"299 expected publishable -> 298 events"):
            exec(guard,{"reviewed_current":reviewed,"fetched":self.expected.events})
