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
        first = read("post_audit_first_round_9579b90.json") + self.previous
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
        first = read("post_audit_first_round_9579b90.json") + self.previous
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
            for field in self.registry["corrections"][index]:
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
        self.assert_invalid(lambda p: p["corrections"][9].update(action="correct_retained_sample"), "identity")

    def test_exclusion_schema_and_overlapping_locators(self):
        self.registry["excluded_source_rows"] = [copy.deepcopy(self.registry["corrections"][-1]["historical_withheld_source"])]
        self.assert_invalid(lambda p: p["excluded_source_rows"][0].update(source_locator="FR-T0R1"), "duplicate")


if __name__ == "__main__":
    unittest.main()
