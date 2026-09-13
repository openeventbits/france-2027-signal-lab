from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def setUpModule() -> None:
    """Defer TRACE import until repository-isolation tests have run."""

    global ContractError, build_draft_trace, validate_trace
    from tools.fr27_trace import (
        ContractError as contract_error,
        build_draft_trace as draft_builder,
        validate_trace as trace_validator,
    )

    ContractError = contract_error
    build_draft_trace = draft_builder
    validate_trace = trace_validator


def load_fixture(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class ContractTests(unittest.TestCase):
    def test_frozen_valid_fixture(self) -> None:
        self.assertIsNone(validate_trace(load_fixture("valid_trace_v1.json")))

    def test_every_public_family_is_valid(self) -> None:
        for family in ("candidate", "field", "issue", "story", "event"):
            with self.subTest(family=family):
                trace = build_draft_trace(
                    family=family,
                    detector_id="fixture_detector.v1",
                    primary_entity_ids=["entity:1"],
                    observation_window={"start": "2026-08-01", "end": "2026-08-31"},
                    evidence={"datum": {"availability": "observed", "value": 1}},
                )
                self.assertIsNone(validate_trace(trace))

    def test_invalid_family_fixture_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "family"):
            validate_trace(load_fixture("invalid_family_trace_v1.json"))

    def test_malformed_availability_fixture_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "availability"):
            validate_trace(load_fixture("invalid_availability_trace_v1.json"))

    def test_draft_has_no_public_serial(self) -> None:
        trace = load_fixture("valid_trace_v1.json")
        self.assertNotIn("public_serial", trace)
        with self.assertRaisesRegex(ContractError, "public_serial"):
            validate_trace(load_fixture("invalid_public_serial_trace_v1.json"))

    def test_observed_zero_is_distinct_from_unavailable(self) -> None:
        observed = build_draft_trace(
            family="issue",
            detector_id="zero_check.v1",
            primary_entity_ids=["issue:zero"],
            observation_window={"start": "2026-08-01", "end": "2026-08-31"},
            evidence={"datum": {"availability": "observed", "value": 0}},
        )
        unavailable = build_draft_trace(
            family="issue",
            detector_id="zero_check.v1",
            primary_entity_ids=["issue:zero"],
            observation_window={"start": "2026-08-01", "end": "2026-08-31"},
            evidence={"datum": {"availability": "unavailable"}},
        )
        self.assertEqual(0, observed["evidence"]["datum"]["value"])
        self.assertNotIn("value", unavailable["evidence"]["datum"])
        self.assertNotEqual(observed["evidence_snapshot_hash"], unavailable["evidence_snapshot_hash"])
        self.assertNotEqual(observed["trace_key"], unavailable["trace_key"])

    def test_observed_false_and_zero_are_valid_distinct_values(self) -> None:
        traces = [
            build_draft_trace(
                family="issue",
                detector_id="false_zero.v1",
                primary_entity_ids=["issue:false-zero"],
                observation_window={"start": "2026-08-01", "end": "2026-08-31"},
                evidence={"datum": {"availability": "observed", "value": value}},
            )
            for value in (False, 0)
        ]
        self.assertIs(False, traces[0]["evidence"]["datum"]["value"])
        self.assertEqual(0, traces[1]["evidence"]["datum"]["value"])
        self.assertNotEqual(traces[0]["evidence_snapshot_hash"], traces[1]["evidence_snapshot_hash"])

    def test_all_non_observed_states_remain_distinct(self) -> None:
        hashes = set()
        for state in ("not_observed", "unavailable", "not_applicable"):
            trace = build_draft_trace(
                family="issue",
                detector_id="availability.v1",
                primary_entity_ids=["issue:availability"],
                observation_window={"start": "2026-08-01", "end": "2026-08-31"},
                evidence={"datum": {"availability": state}},
            )
            hashes.add(trace["evidence_snapshot_hash"])
        self.assertEqual(3, len(hashes))

    def test_non_observed_states_must_not_contain_value(self) -> None:
        for state in ("not_observed", "unavailable", "not_applicable"):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ContractError, "must not contain value"):
                    build_draft_trace(
                        family="issue",
                        detector_id="availability.v1",
                        primary_entity_ids=["issue:availability"],
                        observation_window={
                            "start": "2026-08-01",
                            "end": "2026-08-31",
                        },
                        evidence={"datum": {"availability": state, "value": 0}},
                    )

    def test_nested_array_availability_records_are_validated(self) -> None:
        trace = build_draft_trace(
            family="issue",
            detector_id="nested_availability.v1",
            primary_entity_ids=["issue:nested"],
            observation_window={"start": "2026-08-01", "end": "2026-08-31"},
            evidence={
                "groups": [
                    {"datum": {"availability": "observed", "value": 0}},
                    {"datum": {"availability": "unavailable"}},
                ]
            },
        )
        self.assertIsNone(validate_trace(trace))

        with self.assertRaisesRegex(ContractError, "availability"):
            build_draft_trace(
                family="issue",
                detector_id="nested_availability.v1",
                primary_entity_ids=["issue:nested"],
                observation_window={"start": "2026-08-01", "end": "2026-08-31"},
                evidence={
                    "groups": [
                        {"datum": {"availability": "observed", "value": 0}},
                        {"metadata": {"availability": "external"}},
                    ]
                },
            )

    def test_changed_or_forged_digests_are_rejected(self) -> None:
        trace = load_fixture("valid_trace_v1.json")
        changed_evidence = deepcopy(trace)
        changed_evidence["evidence"]["poll_support"]["value"] = 1
        with self.assertRaisesRegex(ContractError, "evidence_snapshot_hash"):
            validate_trace(changed_evidence)
        changed_key = deepcopy(trace)
        changed_key["trace_key"] = "trace_" + "0" * 64
        with self.assertRaisesRegex(ContractError, "trace_key"):
            validate_trace(changed_key)


if __name__ == "__main__":
    unittest.main()
