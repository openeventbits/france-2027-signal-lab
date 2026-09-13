from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TRACE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = TRACE_ROOT / "fixtures" / "coverage_anatomy_candidate_v1.json"
sys.path.insert(0, str(REPOSITORY_ROOT))


def setUpModule() -> None:
    global CoverageAnatomyError, TraceRenderModel, build_draft_trace
    global coverage_module, extract_live_coverage_anatomy
    global select_coverage_anatomy, validate_trace
    import tools.fr27_trace.coverage_anatomy as module
    from tools.fr27_trace import build_draft_trace as draft_builder
    from tools.fr27_trace import validate_trace as trace_validator
    from tools.fr27_trace.coverage_anatomy import (
        CoverageAnatomyError as extraction_error,
        select_coverage_anatomy as selector,
        extract_live_coverage_anatomy as live_extractor,
    )
    from tools.fr27_trace.render import TraceRenderModel as render_model

    CoverageAnatomyError = extraction_error
    TraceRenderModel = render_model
    build_draft_trace = draft_builder
    coverage_module = module
    extract_live_coverage_anatomy = live_extractor
    select_coverage_anatomy = selector
    validate_trace = trace_validator


def source_payload() -> dict:
    def metric(
        name: str,
        *,
        share: float,
        publishers: int,
        clusters: int,
        leading_story_share: float,
        leading_publisher_share: float,
    ) -> dict:
        return {
            "candidate": name,
            "record_count": 100,
            "share": share,
            "publisher_count": publishers,
            "publisher_names": [f"Publisher {index}" for index in range(publishers)],
            "active_day_count": 7,
            "headline_match_count": 80,
            "summary_only_match_count": 20,
            "scope_counts": {"election": 70, "campaign": 30, "general": 0},
            "scope_shares": {"election": 0.7, "campaign": 0.3, "general": 0},
            "story_cluster_count": clusters,
            "story_clusters": [{"unselected": "fixture-only"}],
            "concentration": {
                "leading_publisher": "Synthetic Publisher",
                "leading_publisher_record_count": round(leading_publisher_share * 100),
                "leading_publisher_share": leading_publisher_share,
                "leading_story_record_count": round(leading_story_share * 100),
                "leading_story_share": leading_story_share,
            },
        }

    return {
        "schema_version": "unselected",
        "candidate_visibility": {
            "method": "share_of_candidate_linked_records",
            "primary_scopes": ["election", "campaign"],
            "secondary_scope": "general",
            "prior_period": {
                "start_date": "2026-08-18",
                "end_date": "2026-08-24",
                "record_count": 833,
                "publisher_count": 60,
                "publisher_names": ["unselected"],
                "candidate_metrics": [
                    metric(
                        "Synthetic Candidate Alpha",
                        share=0.12,
                        publishers=39,
                        clusters=16,
                        leading_story_share=0.18,
                        leading_publisher_share=0.11,
                    )
                ],
            },
            "current_period": {
                "start_date": "2026-08-25",
                "end_date": "2026-08-31",
                "record_count": 769,
                "publisher_count": 50,
                "publisher_names": ["unselected"],
                "candidate_metrics": [
                    metric(
                        "Synthetic Candidate Alpha",
                        share=0.13,
                        publishers=21,
                        clusters=7,
                        leading_story_share=0.46,
                        leading_publisher_share=0.24,
                    )
                ],
            },
            "general_current_period": {"unselected": True},
            "general_prior_period": {"unselected": True},
            "comparison_quality": {
                "status": "comparable",
                "reason": "comparable",
                "current_record_count": 769,
                "prior_record_count": 833,
                "current_publisher_count": 50,
                "prior_publisher_count": 60,
                "common_publisher_count": 45,
                "publisher_union_count": 65,
                "publisher_overlap_ratio": 0.692,
                "record_count_ratio": 1.083,
                "thresholds": {
                    "minimum_period_records": 10,
                    "minimum_period_publishers": 5,
                    "minimum_common_publishers": 5,
                    "minimum_publisher_overlap_ratio": 0.5,
                    "maximum_record_count_ratio": 2.0,
                },
            },
        },
        "unrelated_news": [{"headline": "not selected"}],
    }


def load_fixture() -> dict:
    with FIXTURE.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def document_with_evidence(evidence: dict) -> dict:
    document = load_fixture()
    source_trace = document["trace"]
    document["trace"] = build_draft_trace(
        family=source_trace["family"],
        detector_id=source_trace["detector_id"],
        primary_entity_ids=source_trace["primary_entity_ids"],
        observation_window=source_trace["observation_window"],
        evidence=evidence,
    )
    return document


class CoverageAnatomyExtractionTests(unittest.TestCase):
    def test_frozen_fixture_is_a_valid_candidate_trace(self) -> None:
        document = load_fixture()
        self.assertIsNone(validate_trace(document["trace"]))
        self.assertEqual("candidate", document["trace"]["family"])
        self.assertEqual("coverage_anatomy.v1", document["trace"]["detector_id"])

    def test_extractor_uses_canonical_deterministic_primary_identity(self) -> None:
        first = select_coverage_anatomy(source_payload(), "synthetic-candidate-alpha")
        second = select_coverage_anatomy(source_payload(), "synthetic-candidate-alpha")
        self.assertEqual("Synthetic Candidate Alpha", first.candidate_name)
        self.assertEqual(["synthetic-candidate-alpha"], first.build_trace()["primary_entity_ids"])
        self.assertEqual(first.build_trace()["trace_key"], second.build_trace()["trace_key"])

    def test_selected_evidence_has_only_the_narrow_comparative_slice(self) -> None:
        trace = select_coverage_anatomy(
            source_payload(), "synthetic-candidate-alpha"
        ).build_trace()
        self.assertEqual(
            {"scope", "prior_period", "current_period", "comparison_quality"},
            set(trace["evidence"]),
        )
        self.assertEqual(
            "upstream_comparison_quality",
            trace["evidence"]["comparison_quality"]["unit"],
        )
        expected_metrics = {
            "record_count",
            "share",
            "publisher_count",
            "story_cluster_count",
            "leading_story_record_count",
            "leading_story_share",
            "leading_publisher_record_count",
            "leading_publisher_share",
        }
        for period_name in ("prior_period", "current_period"):
            period = trace["evidence"][period_name]
            self.assertEqual({"start", "end", "candidate_metrics"}, set(period))
            self.assertEqual(expected_metrics, set(period["candidate_metrics"]))
        serialized = json.dumps(trace["evidence"])
        for excluded in (
            '"story_clusters":',
            '"publisher_names":',
            '"leading_publisher":',
            '"active_day_count":',
            '"headline_match_count":',
            '"general_current_period":',
        ):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, serialized)

    def test_unrelated_news_wire_changes_do_not_change_identity(self) -> None:
        first_source = source_payload()
        second_source = deepcopy(first_source)
        second_source["unrelated_news"] = [{"headline": "changed elsewhere"}] * 25
        second_source["candidate_visibility"]["current_period"]["candidate_metrics"][0][
            "story_clusters"
        ] = [{"different": "ignored"}]
        second_source["candidate_visibility"]["current_period"]["candidate_metrics"][0][
            "concentration"
        ]["leading_publisher"] = "Another ignored publisher identity"
        first = select_coverage_anatomy(first_source, "synthetic-candidate-alpha").build_trace()
        second = select_coverage_anatomy(second_source, "synthetic-candidate-alpha").build_trace()
        self.assertEqual(first["evidence_snapshot_hash"], second["evidence_snapshot_hash"])
        self.assertEqual(first["trace_key"], second["trace_key"])

    def test_one_displayed_metric_change_changes_identity(self) -> None:
        changed = source_payload()
        changed["candidate_visibility"]["current_period"]["candidate_metrics"][0][
            "concentration"
        ].update(
            {
                "leading_story_record_count": 47,
                "leading_story_share": 0.47,
            }
        )
        first = select_coverage_anatomy(
            source_payload(), "synthetic-candidate-alpha"
        ).build_trace()
        second = select_coverage_anatomy(
            changed, "synthetic-candidate-alpha"
        ).build_trace()
        self.assertNotEqual(first["evidence_snapshot_hash"], second["evidence_snapshot_hash"])
        self.assertNotEqual(first["trace_key"], second["trace_key"])

    def test_inconsistent_selected_shares_fail_closed_in_both_periods(self) -> None:
        cases = (
            ("share", False),
            ("leading_story_share", True),
            ("leading_publisher_share", True),
        )
        for period_name in ("prior_period", "current_period"):
            for metric_name, in_concentration in cases:
                with self.subTest(period=period_name, metric=metric_name):
                    source = source_payload()
                    metric = source["candidate_visibility"][period_name][
                        "candidate_metrics"
                    ][0]
                    target = metric["concentration"] if in_concentration else metric
                    target[metric_name] = 0.99
                    with self.assertRaisesRegex(
                        CoverageAnatomyError, rf"{metric_name}.*inconsistent"
                    ):
                        select_coverage_anatomy(
                            source, "synthetic-candidate-alpha"
                        )

    def test_share_validation_uses_upstream_three_decimal_half_up_rounding(self) -> None:
        self.assertEqual(
            0.063,
            coverage_module._round_candidate_visibility_ratio(1 / 16),
        )

    def test_period_and_full_comparative_window_change_identity(self) -> None:
        changed = source_payload()
        changed["candidate_visibility"]["prior_period"]["start_date"] = "2026-08-17"
        changed["candidate_visibility"]["prior_period"]["end_date"] = "2026-08-23"
        changed["candidate_visibility"]["current_period"]["start_date"] = "2026-08-24"
        changed["candidate_visibility"]["current_period"]["end_date"] = "2026-08-30"
        first = select_coverage_anatomy(
            source_payload(), "synthetic-candidate-alpha"
        ).build_trace()
        second = select_coverage_anatomy(
            changed, "synthetic-candidate-alpha"
        ).build_trace()
        self.assertEqual(
            {"start": "2026-08-17", "end": "2026-08-30"},
            second["observation_window"],
        )
        self.assertNotEqual(first["trace_key"], second["trace_key"])

    def test_not_comparable_upstream_state_fails_closed(self) -> None:
        source = source_payload()
        source["candidate_visibility"]["comparison_quality"].update(
            {"status": "not_comparable", "reason": "insufficient_data"}
        )
        with self.assertRaisesRegex(CoverageAnatomyError, "suppressed.*not_comparable"):
            select_coverage_anatomy(source, "synthetic-candidate-alpha")

    def test_candidate_missing_from_prior_period_fails_closed(self) -> None:
        source = source_payload()
        source["candidate_visibility"]["prior_period"]["candidate_metrics"] = []
        with self.assertRaisesRegex(CoverageAnatomyError, "absent from prior_period"):
            select_coverage_anatomy(source, "synthetic-candidate-alpha")

    def test_candidate_missing_from_current_period_fails_closed(self) -> None:
        source = source_payload()
        source["candidate_visibility"]["current_period"]["candidate_metrics"] = []
        with self.assertRaisesRegex(CoverageAnatomyError, "absent from current_period"):
            select_coverage_anatomy(source, "synthetic-candidate-alpha")

    def test_zero_is_observed_and_distinct_from_missing_or_unavailable(self) -> None:
        source = source_payload()
        source["candidate_visibility"]["prior_period"]["candidate_metrics"][0][
            "publisher_count"
        ] = 0
        observed = select_coverage_anatomy(
            source, "synthetic-candidate-alpha"
        ).build_trace()
        record = observed["evidence"]["prior_period"]["candidate_metrics"][
            "publisher_count"
        ]
        self.assertEqual({"availability": "observed", "unit": "publishers", "value": 0}, record)

        missing = source_payload()
        del missing["candidate_visibility"]["prior_period"]["candidate_metrics"][0][
            "publisher_count"
        ]
        with self.assertRaisesRegex(CoverageAnatomyError, "publisher_count"):
            select_coverage_anatomy(missing, "synthetic-candidate-alpha")

        unavailable_evidence = deepcopy(observed["evidence"])
        unavailable_evidence["prior_period"]["candidate_metrics"]["publisher_count"] = {
            "availability": "unavailable"
        }
        unavailable = build_draft_trace(
            family="candidate",
            detector_id="coverage_anatomy.v1",
            primary_entity_ids=["synthetic-candidate-alpha"],
            observation_window=observed["observation_window"],
            evidence=unavailable_evidence,
        )
        self.assertNotEqual(observed["evidence_snapshot_hash"], unavailable["evidence_snapshot_hash"])

    def test_noncanonical_candidate_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(CoverageAnatomyError, "canonical lowercase"):
            select_coverage_anatomy(source_payload(), "Synthetic Candidate Alpha")

    def test_extractor_source_contains_no_ranking_or_writer_entry_point(self) -> None:
        source = (TRACE_ROOT / "coverage_anatomy.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "fetch_news_wire",
            "build_candidate_signals",
            "requests",
            "urlopen",
            "subprocess",
            ".write_text(",
            ".write_bytes(",
            "ranking",
            "top_n",
            "publication_threshold",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_live_adapter_opens_only_its_source_for_reading(self) -> None:
        source_file = io.StringIO(json.dumps(source_payload()))
        fake_path = mock.Mock()
        fake_path.open.return_value = source_file
        with mock.patch.object(coverage_module, "NEWS_WIRE_PATH", fake_path):
            selection = extract_live_coverage_anatomy("synthetic-candidate-alpha")
        self.assertEqual("synthetic-candidate-alpha", selection.candidate_id)
        fake_path.open.assert_called_once_with(encoding="utf-8")

    def test_synthetic_extraction_does_not_modify_protected_production_files(self) -> None:
        protected = [
            REPOSITORY_ROOT / "fetch_news_wire.py",
            REPOSITORY_ROOT / "build_candidate_signals.py",
            REPOSITORY_ROOT / "news_wire.json",
            REPOSITORY_ROOT / "candidate_signals.json",
            REPOSITORY_ROOT / "candidate_visibility_history.json",
        ]
        before = {path: path.read_bytes() for path in protected}
        select_coverage_anatomy(source_payload(), "synthetic-candidate-alpha").build_trace()
        after = {path: path.read_bytes() for path in protected}
        self.assertEqual(before, after)


class CoverageAnatomyRenderTests(unittest.TestCase):
    def test_every_selected_metric_requires_explicit_observed_availability(self) -> None:
        metric_names = (
            "record_count",
            "share",
            "publisher_count",
            "story_cluster_count",
            "leading_publisher_record_count",
            "leading_publisher_share",
            "leading_story_record_count",
            "leading_story_share",
        )
        for period_name in ("prior_period", "current_period"):
            for metric_name in metric_names:
                with self.subTest(period=period_name, metric=metric_name):
                    evidence = deepcopy(load_fixture()["trace"]["evidence"])
                    del evidence[period_name]["candidate_metrics"][metric_name][
                        "availability"
                    ]
                    with self.assertRaisesRegex(
                        Exception, "invalid Coverage Anatomy evidence"
                    ):
                        TraceRenderModel.from_document(
                            document_with_evidence(evidence)
                        )

    def test_non_observed_selected_metrics_fail_closed(self) -> None:
        metric_names = tuple(
            load_fixture()["trace"]["evidence"]["prior_period"][
                "candidate_metrics"
            ]
        )
        for period_name in ("prior_period", "current_period"):
            for metric_name in metric_names:
                with self.subTest(period=period_name, metric=metric_name):
                    evidence = deepcopy(load_fixture()["trace"]["evidence"])
                    evidence[period_name]["candidate_metrics"][metric_name] = {
                        "availability": "unavailable"
                    }
                    with self.assertRaisesRegex(
                        Exception, "invalid Coverage Anatomy evidence"
                    ):
                        TraceRenderModel.from_document(
                            document_with_evidence(evidence)
                        )

    def test_every_selected_metric_requires_its_established_unit(self) -> None:
        metric_names = tuple(
            load_fixture()["trace"]["evidence"]["prior_period"][
                "candidate_metrics"
            ]
        )
        for period_name in ("prior_period", "current_period"):
            for metric_name in metric_names:
                with self.subTest(period=period_name, metric=metric_name):
                    evidence = deepcopy(load_fixture()["trace"]["evidence"])
                    evidence[period_name]["candidate_metrics"][metric_name][
                        "unit"
                    ] = "wrong_unit"
                    with self.assertRaisesRegex(
                        Exception, "invalid Coverage Anatomy evidence"
                    ):
                        TraceRenderModel.from_document(
                            document_with_evidence(evidence)
                        )

    def test_every_selected_metric_rejects_wrong_value_type(self) -> None:
        share_metrics = {
            "share",
            "leading_publisher_share",
            "leading_story_share",
        }
        metric_names = tuple(
            load_fixture()["trace"]["evidence"]["prior_period"][
                "candidate_metrics"
            ]
        )
        for period_name in ("prior_period", "current_period"):
            for metric_name in metric_names:
                with self.subTest(period=period_name, metric=metric_name):
                    evidence = deepcopy(load_fixture()["trace"]["evidence"])
                    evidence[period_name]["candidate_metrics"][metric_name][
                        "value"
                    ] = "0.5" if metric_name in share_metrics else True
                    with self.assertRaisesRegex(
                        Exception, "invalid Coverage Anatomy evidence"
                    ):
                        TraceRenderModel.from_document(
                            document_with_evidence(evidence)
                        )

    def test_observed_zero_is_valid_for_every_selected_metric(self) -> None:
        evidence = deepcopy(load_fixture()["trace"]["evidence"])
        for period_name in ("prior_period", "current_period"):
            for record in evidence[period_name]["candidate_metrics"].values():
                record["value"] = 0
        model = TraceRenderModel.from_document(document_with_evidence(evidence))
        self.assertEqual(
            ["0%", "0", "0", "0%", "0%"],
            [row["prior"] for row in model.to_payload()["field"]["rows"]],
        )

    def test_renderer_uses_five_rows_in_frozen_semantic_order(self) -> None:
        payload = TraceRenderModel.from_document(load_fixture()).to_payload()
        rows = payload["field"]["rows"]
        self.assertEqual(
            [
                "COVERAGE SHARE",
                "PUBLISHERS",
                "STORY CLUSTERS",
                "LARGEST STORY",
                "TOP PUBLISHER",
            ],
            [row["label"] for row in rows],
        )
        self.assertEqual(["12%", "39", "16", "18%", "11%"], [row["prior"] for row in rows])
        self.assertEqual(["13%", "21", "7", "46%", "24%"], [row["current"] for row in rows])

    def test_temporal_labels_and_exact_period_dates_are_explicit(self) -> None:
        field = TraceRenderModel.from_document(load_fixture()).to_payload()["field"]
        self.assertEqual("PRIOR", field["priorLabel"])
        self.assertEqual("CURRENT", field["currentLabel"])
        self.assertEqual("2026-08-18 — 2026-08-24", field["priorDates"])
        self.assertEqual("2026-08-25 — 2026-08-31", field["currentDates"])

    def test_no_shared_scale_or_composite_score_is_in_render_payload(self) -> None:
        payload = TraceRenderModel.from_document(load_fixture()).to_payload()
        serialized = json.dumps(payload).lower()
        self.assertNotIn("composite", serialized)
        self.assertNotIn("score", serialized)
        self.assertNotIn("scale", serialized)
        self.assertEqual(
            {"key", "label", "unitLabel", "prior", "current"},
            set(payload["field"]["rows"][0]),
        )

    def test_presentation_and_finding_changes_do_not_change_identity(self) -> None:
        first_document = load_fixture()
        second_document = deepcopy(first_document)
        second_document["presentation"].update(
            {
                "finding": "SYNTHETIC PRESENTATION-ONLY FINDING.",
                "qualifier": "Synthetic presentation-only replacement.",
            }
        )
        first = TraceRenderModel.from_document(first_document)
        second = TraceRenderModel.from_document(second_document)
        self.assertEqual(first.trace["evidence_snapshot_hash"], second.trace["evidence_snapshot_hash"])
        self.assertEqual(first.trace["trace_key"], second.trace["trace_key"])

    def test_rows_have_no_connectors_and_header_direction_remains(self) -> None:
        html = (TRACE_ROOT / "render" / "shell.html").read_text(encoding="utf-8")
        css = (TRACE_ROOT / "render" / "shell.css").read_text(encoding="utf-8")
        javascript = (TRACE_ROOT / "render" / "shell.js").read_text(encoding="utf-8")
        self.assertIn('class="coverage-direction"', html)
        self.assertIn(".coverage-direction", css)
        self.assertNotIn("coverage-bridge", html + css + javascript)

    def test_candidate_header_footer_and_methodological_boundary_are_preserved(self) -> None:
        payload = TraceRenderModel.from_document(load_fixture()).to_payload()
        self.assertEqual("CANDIDATE", payload["family"])
        self.assertEqual("SYNTHETIC CANDIDATE ALPHA", payload["displayLabel"])
        self.assertEqual("FR27 CANDIDATE-LINKED COVERAGE", payload["sourceScope"])
        self.assertEqual(
            "COVERAGE STRUCTURE ≠ SUPPORT OR SENTIMENT",
            payload["methodologicalBoundary"],
        )

    def test_coverage_field_requires_matching_candidate_detector(self) -> None:
        document = load_fixture()
        document["trace"]["detector_id"] = "another_detector.v1"
        with self.assertRaisesRegex(Exception, "invalid TRACE|coverage_anatomy"):
            TraceRenderModel.from_document(document)


if __name__ == "__main__":
    unittest.main()
