from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))

BASE_ARGUMENTS = {
    "family": "field",
    "detector_id": "field_distance.v3",
    "primary_entity_ids": ["candidate:b", "candidate:a"],
    "observation_window": {"start": "2026-08-01", "end": "2026-08-31"},
    "evidence": {
        "distance": {"availability": "observed", "value": 4.5, "unit": "points"},
        "sample": {"availability": "observed", "value": 1200},
    },
}


def setUpModule() -> None:
    """Defer TRACE import until repository-isolation tests have run."""

    global ContractError, IdentityError
    global build_draft_trace, canonicalize_evidence, canonicalize_observation_window
    global evidence_snapshot_hash, trace_key
    from tools.fr27_trace import (
        ContractError as contract_error,
        IdentityError as identity_error,
        build_draft_trace as draft_builder,
        canonicalize_evidence as evidence_canonicalizer,
        canonicalize_observation_window as window_canonicalizer,
        evidence_snapshot_hash as snapshot_hasher,
        trace_key as key_builder,
    )

    ContractError = contract_error
    IdentityError = identity_error
    build_draft_trace = draft_builder
    canonicalize_evidence = evidence_canonicalizer
    canonicalize_observation_window = window_canonicalizer
    evidence_snapshot_hash = snapshot_hasher
    trace_key = key_builder


class IdentityTests(unittest.TestCase):
    def test_same_evidence_produces_same_trace_key(self) -> None:
        self.assertEqual(
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
        )

    def test_reordered_json_keys_produce_same_identity(self) -> None:
        reordered = OrderedDict(
            [
                ("sample", OrderedDict([("value", 1200), ("availability", "observed")])),
                (
                    "distance",
                    OrderedDict(
                        [("unit", "points"), ("value", 4.5), ("availability", "observed")]
                    ),
                ),
            ]
        )
        first = build_draft_trace(**BASE_ARGUMENTS)
        second = build_draft_trace(**{**BASE_ARGUMENTS, "evidence": reordered})
        self.assertEqual(first["evidence_snapshot_hash"], second["evidence_snapshot_hash"])
        self.assertEqual(first["trace_key"], second["trace_key"])

    def test_nfc_equivalent_evidence_keys_and_values_preserve_identity(self) -> None:
        composed = {"résumé": {"availability": "observed", "value": "café"}}
        decomposed = {
            "re\u0301sume\u0301": {"availability": "observed", "value": "cafe\u0301"}
        }
        self.assertEqual(
            evidence_snapshot_hash(composed),
            evidence_snapshot_hash(decomposed),
        )

    def test_duplicate_keys_after_nfc_normalization_are_rejected(self) -> None:
        with self.assertRaisesRegex(IdentityError, "duplicate normalized key"):
            canonicalize_evidence({"é": 1, "e\u0301": 2})

    def test_unpaired_surrogates_are_rejected_by_identity_and_contract_apis(self) -> None:
        surrogate = "\ud800"
        invalid_arguments = {
            "evidence key": {
                **BASE_ARGUMENTS,
                "evidence": {surrogate: {"availability": "observed", "value": 1}},
            },
            "evidence value": {
                **BASE_ARGUMENTS,
                "evidence": {
                    "datum": {"availability": "observed", "value": surrogate}
                },
            },
            "detector_id": {**BASE_ARGUMENTS, "detector_id": surrogate},
            "primary entity ID": {
                **BASE_ARGUMENTS,
                "primary_entity_ids": [surrogate],
            },
            "observation window": {
                **BASE_ARGUMENTS,
                "observation_window": {"start": surrogate, "end": "2026-08-31"},
            },
        }
        with self.assertRaisesRegex(IdentityError, "UTF-8"):
            evidence_snapshot_hash(
                {"datum": {"availability": "observed", "value": surrogate}}
            )
        for label, arguments in invalid_arguments.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ContractError, "UTF-8"):
                    build_draft_trace(**arguments)

    def test_integral_float_and_integer_canonicalize_equivalently(self) -> None:
        self.assertEqual(
            evidence_snapshot_hash(
                {"datum": {"availability": "observed", "value": 1}}
            ),
            evidence_snapshot_hash(
                {"datum": {"availability": "observed", "value": 1.0}}
            ),
        )

    def test_non_finite_numbers_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(IdentityError, "non-finite"):
                    evidence_snapshot_hash(
                        {"datum": {"availability": "observed", "value": value}}
                    )

    def test_evidence_array_order_is_identity_significant(self) -> None:
        first = {"values": [1, 2], "datum": {"availability": "observed", "value": 1}}
        second = {"values": [2, 1], "datum": {"availability": "observed", "value": 1}}
        self.assertNotEqual(evidence_snapshot_hash(first), evidence_snapshot_hash(second))

    def test_language_timestamp_and_renderer_do_not_affect_identity(self) -> None:
        french = build_draft_trace(
            **BASE_ARGUMENTS,
            language="fr",
            generated_at="2026-09-01T12:00:00Z",
            renderer_version="renderer.v1",
        )
        english = build_draft_trace(
            **BASE_ARGUMENTS,
            language="en",
            generated_at="2026-09-10T08:30:00+02:00",
            renderer_version="renderer.v9",
        )
        self.assertEqual(french["trace_key"], english["trace_key"])

    def test_unrelated_upstream_provenance_does_not_affect_identity(self) -> None:
        first = build_draft_trace(
            **BASE_ARGUMENTS,
            upstream_provenance={"dataset_revision": "a", "unselected_row_count": 10},
        )
        second = build_draft_trace(
            **BASE_ARGUMENTS,
            upstream_provenance={"dataset_revision": "b", "unselected_row_count": 999},
        )
        self.assertEqual(first["trace_key"], second["trace_key"])

    def test_selected_evidence_change_produces_new_identity(self) -> None:
        changed = {
            **BASE_ARGUMENTS,
            "evidence": {
                **BASE_ARGUMENTS["evidence"],
                "distance": {"availability": "observed", "value": 4.6, "unit": "points"},
            },
        }
        self.assertNotEqual(
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
            build_draft_trace(**changed)["trace_key"],
        )

    def test_observation_window_change_produces_new_identity(self) -> None:
        changed = {
            **BASE_ARGUMENTS,
            "observation_window": {"start": "2026-08-02", "end": "2026-08-31"},
        }
        self.assertNotEqual(
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
            build_draft_trace(**changed)["trace_key"],
        )

    def test_equivalent_timezone_offsets_produce_same_window_and_key(self) -> None:
        offset_window = {
            "start": "2026-08-01T02:00:00+02:00",
            "end": "2026-08-01T04:00:00+02:00",
        }
        utc_window = {
            "start": "2026-08-01T00:00:00Z",
            "end": "2026-08-01T02:00:00Z",
        }
        self.assertEqual(
            canonicalize_observation_window(offset_window),
            canonicalize_observation_window(utc_window),
        )
        first = build_draft_trace(**{**BASE_ARGUMENTS, "observation_window": offset_window})
        second = build_draft_trace(**{**BASE_ARGUMENTS, "observation_window": utc_window})
        self.assertEqual(first["trace_key"], second["trace_key"])

    def test_invalid_observation_window_precision_and_ranges_are_rejected(self) -> None:
        invalid_windows = {
            "mixed date and timestamp": {
                "start": "2026-08-01",
                "end": "2026-08-01T00:00:00Z",
            },
            "naive timestamp": {
                "start": "2026-08-01T00:00:00",
                "end": "2026-08-02T00:00:00",
            },
            "reversed dates": {"start": "2026-08-02", "end": "2026-08-01"},
        }
        for label, window in invalid_windows.items():
            with self.subTest(label=label):
                with self.assertRaises(IdentityError):
                    canonicalize_observation_window(window)

    def test_equal_observation_window_boundaries_are_valid(self) -> None:
        window = {
            "start": "2026-08-01T02:00:00+02:00",
            "end": "2026-08-01T00:00:00Z",
        }
        self.assertEqual(
            {"start": "2026-08-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"},
            canonicalize_observation_window(window),
        )

    def test_detector_change_produces_new_identity(self) -> None:
        changed = {**BASE_ARGUMENTS, "detector_id": "field_distance.v4"}
        self.assertNotEqual(
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
            build_draft_trace(**changed)["trace_key"],
        )

    def test_primary_entity_change_produces_new_identity(self) -> None:
        changed = {**BASE_ARGUMENTS, "primary_entity_ids": ["candidate:a", "candidate:c"]}
        self.assertNotEqual(
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
            build_draft_trace(**changed)["trace_key"],
        )

    def test_entity_order_is_canonical(self) -> None:
        reversed_ids = {**BASE_ARGUMENTS, "primary_entity_ids": ["candidate:a", "candidate:b"]}
        self.assertEqual(
            build_draft_trace(**BASE_ARGUMENTS)["trace_key"],
            build_draft_trace(**reversed_ids)["trace_key"],
        )

    def test_schema_version_change_produces_new_identity(self) -> None:
        trace = build_draft_trace(**BASE_ARGUMENTS)
        changed = trace_key(
            trace_schema_version="2",
            family=trace["family"],
            detector_id=trace["detector_id"],
            primary_entity_ids=trace["primary_entity_ids"],
            observation_window=trace["observation_window"],
            evidence_snapshot_hash_value=trace["evidence_snapshot_hash"],
        )
        self.assertNotEqual(trace["trace_key"], changed)

    def test_numeric_zero_is_canonical_but_not_missing(self) -> None:
        self.assertEqual(
            evidence_snapshot_hash({"datum": {"availability": "observed", "value": 0}}),
            evidence_snapshot_hash({"datum": {"value": -0.0, "availability": "observed"}}),
        )
        self.assertNotEqual(
            evidence_snapshot_hash({"datum": {"availability": "observed", "value": 0}}),
            evidence_snapshot_hash({"datum": {"availability": "unavailable"}}),
        )


if __name__ == "__main__":
    unittest.main()
