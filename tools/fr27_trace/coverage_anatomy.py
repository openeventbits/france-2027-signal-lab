"""Read-only Coverage Anatomy extraction for the Candidate TRACE family."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
import json
import math
from pathlib import Path
import re
from typing import Any

from candidate_identity import (
    CandidateIdentityError,
    candidate_id,
    candidate_identity_map,
    canonical_candidate_name,
)

from .contract import build_draft_trace


DETECTOR_ID = "coverage_anatomy.v1"
FIELD_TYPE = "coverage_anatomy"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
NEWS_WIRE_PATH = REPOSITORY_ROOT / "news_wire.json"

_CANONICAL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PRIMARY_SCOPES = frozenset({"campaign", "election"})
_UPSTREAM_METHOD = "share_of_candidate_linked_records"
_PERIOD_NAMES = ("prior_period", "current_period")
_COUNT_FIELDS = (
    "record_count",
    "publisher_count",
    "story_cluster_count",
)
_CONCENTRATION_COUNT_FIELDS = (
    "leading_story_record_count",
    "leading_publisher_record_count",
)
_CONCENTRATION_SHARE_FIELDS = (
    "leading_story_share",
    "leading_publisher_share",
)
COVERAGE_METRIC_UNITS = {
    "record_count": "candidate_linked_records",
    "share": "ratio",
    "publisher_count": "publishers",
    "story_cluster_count": "story_clusters",
    "leading_story_record_count": "candidate_linked_records",
    "leading_story_share": "ratio",
    "leading_publisher_record_count": "candidate_linked_records",
    "leading_publisher_share": "ratio",
}
_COVERAGE_COUNT_METRICS = frozenset(
    {
        "record_count",
        "publisher_count",
        "story_cluster_count",
        "leading_story_record_count",
        "leading_publisher_record_count",
    }
)
_COVERAGE_SHARE_METRICS = frozenset(
    {"share", "leading_story_share", "leading_publisher_share"}
)
_QUALITY_COUNT_FIELDS = (
    "current_record_count",
    "prior_record_count",
    "current_publisher_count",
    "prior_publisher_count",
    "common_publisher_count",
    "publisher_union_count",
)
_QUALITY_RATIO_FIELDS = (
    "publisher_overlap_ratio",
    "record_count_ratio",
)
_THRESHOLD_FIELDS = {
    "minimum_period_records": "count",
    "minimum_period_publishers": "count",
    "minimum_common_publishers": "count",
    "minimum_publisher_overlap_ratio": "ratio",
    "maximum_record_count_ratio": "positive_number",
}


class CoverageAnatomyError(ValueError):
    """Raised when the narrow live evidence slice cannot be selected safely."""


@dataclass(frozen=True)
class CoverageAnatomySelection:
    """Selected identity-bearing evidence and separate candidate display name."""

    candidate_id: str
    candidate_name: str
    observation_window: Mapping[str, str]
    evidence: Mapping[str, Any]

    def build_trace(self) -> dict[str, Any]:
        validate_coverage_anatomy_evidence(self.evidence)
        return build_draft_trace(
            family="candidate",
            detector_id=DETECTOR_ID,
            primary_entity_ids=[self.candidate_id],
            observation_window=self.observation_window,
            evidence=self.evidence,
        )


def _object(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoverageAnatomyError(f"{context} must be an object")
    return value


def _require_fields(value: Mapping[str, Any], fields: set[str], context: str) -> None:
    missing = fields - set(value)
    if missing:
        raise CoverageAnatomyError(
            f"{context} is missing required fields: {', '.join(sorted(missing))}"
        )


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CoverageAnatomyError(f"{context} must be a non-empty trimmed string")
    return value


def _count(value: Any, context: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise CoverageAnatomyError(f"{context} must be a {qualifier} integer")
    return value


def _number(value: Any, context: str, *, minimum: float | None = None) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (minimum is not None and value < minimum)
    ):
        raise CoverageAnatomyError(f"{context} must be a finite number")
    return value


def _ratio(value: Any, context: str) -> int | float:
    number = _number(value, context)
    if not 0 <= number <= 1:
        raise CoverageAnatomyError(f"{context} must be between zero and one")
    return number


def _date(value: Any, context: str) -> str:
    text = _text(value, context)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise CoverageAnatomyError(f"{context} must be an ISO 8601 date") from exc
    if parsed.isoformat() != text:
        raise CoverageAnatomyError(f"{context} must be a canonical ISO 8601 date")
    return text


def _observed(value: Any, unit: str) -> dict[str, Any]:
    return {"availability": "observed", "unit": unit, "value": value}


def _round_candidate_visibility_ratio(value: float) -> float:
    """Mirror the production candidate-visibility three-decimal half-up rule."""

    return math.floor(value * 1000 + 0.5) / 1000


def _candidate_metrics_by_id(period: Mapping[str, Any], context: str) -> dict[str, Mapping[str, Any]]:
    metrics = period.get("candidate_metrics")
    if not isinstance(metrics, list):
        raise CoverageAnatomyError(f"{context}.candidate_metrics must be an array")

    names: list[str] = []
    rows_by_name: dict[str, Mapping[str, Any]] = {}
    for index, raw_metric in enumerate(metrics):
        metric_context = f"{context}.candidate_metrics[{index}]"
        metric = _object(raw_metric, metric_context)
        name = _text(metric.get("candidate"), f"{metric_context}.candidate")
        try:
            canonical_name = canonical_candidate_name(name)
        except CandidateIdentityError as exc:
            raise CoverageAnatomyError(str(exc)) from exc
        if canonical_name != name:
            raise CoverageAnatomyError(f"{metric_context}.candidate is not canonical")
        names.append(name)
        rows_by_name[name] = metric

    try:
        identities = candidate_identity_map(names)
    except CandidateIdentityError as exc:
        raise CoverageAnatomyError(str(exc)) from exc
    if len(rows_by_name) != len(metrics):
        raise CoverageAnatomyError(f"{context}.candidate_metrics contains duplicates")
    return {identities[name]: rows_by_name[name] for name in names}


def _select_period(
    raw_period: Any,
    period_name: str,
    candidate_identifier: str,
) -> tuple[dict[str, Any], str, int, int, int, int]:
    context = f"candidate_visibility.{period_name}"
    period = _object(raw_period, context)
    _require_fields(
        period,
        {"start_date", "end_date", "record_count", "publisher_count", "candidate_metrics"},
        context,
    )
    start = _date(period["start_date"], f"{context}.start_date")
    end = _date(period["end_date"], f"{context}.end_date")
    if (date.fromisoformat(end) - date.fromisoformat(start)).days != 6:
        raise CoverageAnatomyError(f"{context} must span exactly seven days")
    period_record_count = _count(period["record_count"], f"{context}.record_count")
    period_publisher_count = _count(period["publisher_count"], f"{context}.publisher_count")

    rows_by_id = _candidate_metrics_by_id(period, context)
    metric = rows_by_id.get(candidate_identifier)
    if metric is None:
        raise CoverageAnatomyError(
            f"candidate {candidate_identifier!r} is absent from {period_name}"
        )
    metric_context = f"{context}.candidate_metrics[{candidate_identifier}]"
    _require_fields(
        metric,
        {"candidate", "record_count", "share", "publisher_count", "story_cluster_count", "concentration"},
        metric_context,
    )
    record_count = _count(metric["record_count"], f"{metric_context}.record_count", positive=True)
    publisher_count = _count(metric["publisher_count"], f"{metric_context}.publisher_count")
    story_cluster_count = _count(
        metric["story_cluster_count"], f"{metric_context}.story_cluster_count"
    )
    share = _ratio(metric["share"], f"{metric_context}.share")
    if publisher_count > record_count or story_cluster_count > record_count:
        raise CoverageAnatomyError(f"{metric_context} structural counts exceed record_count")

    concentration = _object(metric["concentration"], f"{metric_context}.concentration")
    concentration_fields = set(_CONCENTRATION_COUNT_FIELDS + _CONCENTRATION_SHARE_FIELDS)
    _require_fields(concentration, concentration_fields, f"{metric_context}.concentration")
    selected_metrics = {
        "record_count": _observed(record_count, "candidate_linked_records"),
        "share": _observed(share, "ratio"),
        "publisher_count": _observed(publisher_count, "publishers"),
        "story_cluster_count": _observed(story_cluster_count, "story_clusters"),
    }
    for field in _CONCENTRATION_COUNT_FIELDS:
        value = _count(concentration[field], f"{metric_context}.concentration.{field}")
        if value > record_count:
            raise CoverageAnatomyError(
                f"{metric_context}.concentration.{field} exceeds record_count"
            )
        selected_metrics[field] = _observed(value, "candidate_linked_records")
    for field in _CONCENTRATION_SHARE_FIELDS:
        selected_metrics[field] = _observed(
            _ratio(concentration[field], f"{metric_context}.concentration.{field}"),
            "ratio",
        )

    selected_period = {
        "start": start,
        "end": end,
        "candidate_metrics": selected_metrics,
    }
    if record_count > period_record_count or publisher_count > period_publisher_count:
        raise CoverageAnatomyError(f"{metric_context} exceeds its period totals")
    return (
        selected_period,
        metric["candidate"],
        record_count,
        publisher_count,
        period_record_count,
        period_publisher_count,
    )


def _select_quality(raw_quality: Any) -> dict[str, Any]:
    context = "candidate_visibility.comparison_quality"
    quality = _object(raw_quality, context)
    required = {
        "status",
        "reason",
        *_QUALITY_COUNT_FIELDS,
        *_QUALITY_RATIO_FIELDS,
        "thresholds",
    }
    _require_fields(quality, required, context)
    status = _text(quality["status"], f"{context}.status")
    if status != "comparable":
        raise CoverageAnatomyError(
            f"Coverage Anatomy suppressed: upstream comparison_quality.status is {status!r}, not 'comparable'"
        )

    selected: dict[str, Any] = {
        "status": status,
        "reason": _text(quality["reason"], f"{context}.reason"),
    }
    for field in _QUALITY_COUNT_FIELDS:
        selected[field] = _count(quality[field], f"{context}.{field}")
    selected["publisher_overlap_ratio"] = _ratio(
        quality["publisher_overlap_ratio"], f"{context}.publisher_overlap_ratio"
    )
    selected["record_count_ratio"] = _number(
        quality["record_count_ratio"], f"{context}.record_count_ratio", minimum=1
    )

    thresholds = _object(quality["thresholds"], f"{context}.thresholds")
    _require_fields(thresholds, set(_THRESHOLD_FIELDS), f"{context}.thresholds")
    selected_thresholds: dict[str, Any] = {}
    for field, kind in _THRESHOLD_FIELDS.items():
        value = thresholds[field]
        if kind == "count":
            selected_thresholds[field] = _count(value, f"{context}.thresholds.{field}")
        elif kind == "ratio":
            selected_thresholds[field] = _ratio(value, f"{context}.thresholds.{field}")
        else:
            selected_thresholds[field] = _number(
                value, f"{context}.thresholds.{field}", minimum=0
            )
    selected["thresholds"] = selected_thresholds
    return selected


def _selected_metric_value(
    metrics: Mapping[str, Any],
    period_name: str,
    metric_name: str,
) -> int | float:
    context = f"evidence.{period_name}.candidate_metrics.{metric_name}"
    record = _object(metrics.get(metric_name), context)
    if set(record) != {"availability", "unit", "value"}:
        raise CoverageAnatomyError(f"{context} has invalid fields")
    if record["availability"] != "observed":
        raise CoverageAnatomyError(f"{context}.availability must be 'observed'")
    expected_unit = COVERAGE_METRIC_UNITS[metric_name]
    if record["unit"] != expected_unit:
        raise CoverageAnatomyError(
            f"{context}.unit must be {expected_unit!r}"
        )
    if metric_name in _COVERAGE_COUNT_METRICS:
        return _count(record["value"], f"{context}.value")
    if metric_name in _COVERAGE_SHARE_METRICS:
        return _ratio(record["value"], f"{context}.value")
    raise CoverageAnatomyError(f"unsupported Coverage Anatomy metric {metric_name!r}")


def validate_coverage_anatomy_evidence(evidence: Mapping[str, Any]) -> None:
    """Validate the complete Task 03 evidence slice and derived relationships."""

    selected = _object(evidence, "evidence")
    if set(selected) != {
        "scope",
        "prior_period",
        "current_period",
        "comparison_quality",
    }:
        raise CoverageAnatomyError("Coverage Anatomy evidence has unexpected fields")

    scope = _object(selected["scope"], "evidence.scope")
    if (
        set(scope) != {"availability", "unit", "value"}
        or scope.get("availability") != "observed"
        or scope.get("unit") != "candidate_visibility_scopes"
        or scope.get("value") != sorted(_PRIMARY_SCOPES)
    ):
        raise CoverageAnatomyError(
            "Coverage Anatomy evidence scope must be observed campaign and election scopes"
        )

    quality_record = _object(
        selected["comparison_quality"], "evidence.comparison_quality"
    )
    if set(quality_record) != {"availability", "unit", "value"}:
        raise CoverageAnatomyError(
            "evidence.comparison_quality has invalid fields"
        )
    if quality_record["availability"] != "observed":
        raise CoverageAnatomyError(
            "evidence.comparison_quality.availability must be 'observed'"
        )
    if quality_record["unit"] != "upstream_comparison_quality":
        raise CoverageAnatomyError(
            "evidence.comparison_quality.unit must be 'upstream_comparison_quality'"
        )
    quality_value = _object(
        quality_record["value"], "evidence.comparison_quality.value"
    )
    validated_quality = _select_quality(quality_value)
    if dict(quality_value) != validated_quality:
        raise CoverageAnatomyError(
            "evidence.comparison_quality.value has unexpected fields"
        )

    for period_name, quality_prefix in (
        ("prior_period", "prior"),
        ("current_period", "current"),
    ):
        period_context = f"evidence.{period_name}"
        period = _object(selected[period_name], period_context)
        if set(period) != {"start", "end", "candidate_metrics"}:
            raise CoverageAnatomyError(f"{period_context} has invalid fields")
        start = _date(period["start"], f"{period_context}.start")
        end = _date(period["end"], f"{period_context}.end")
        if (date.fromisoformat(end) - date.fromisoformat(start)).days != 6:
            raise CoverageAnatomyError(f"{period_context} must span exactly seven days")

        metrics = _object(
            period["candidate_metrics"], f"{period_context}.candidate_metrics"
        )
        if set(metrics) != set(COVERAGE_METRIC_UNITS):
            raise CoverageAnatomyError(
                f"{period_context}.candidate_metrics has unexpected fields"
            )
        values = {
            metric_name: _selected_metric_value(metrics, period_name, metric_name)
            for metric_name in COVERAGE_METRIC_UNITS
        }

        record_count = values["record_count"]
        period_record_count = validated_quality[f"{quality_prefix}_record_count"]
        if record_count > period_record_count:
            raise CoverageAnatomyError(
                f"{period_context}.candidate_metrics.record_count exceeds its period denominator"
            )
        if (
            values["publisher_count"]
            > validated_quality[f"{quality_prefix}_publisher_count"]
        ):
            raise CoverageAnatomyError(
                f"{period_context}.candidate_metrics.publisher_count exceeds its period denominator"
            )
        expected_share = _round_candidate_visibility_ratio(
            record_count / period_record_count if period_record_count else 0.0
        )
        if values["share"] != expected_share:
            raise CoverageAnatomyError(
                f"{period_context}.candidate_metrics.share is inconsistent with record counts"
            )

        for count_name, share_name in (
            ("leading_story_record_count", "leading_story_share"),
            ("leading_publisher_record_count", "leading_publisher_share"),
        ):
            leading_count = values[count_name]
            if leading_count > record_count:
                raise CoverageAnatomyError(
                    f"{period_context}.candidate_metrics.{count_name} exceeds record_count"
                )
            expected_leading_share = _round_candidate_visibility_ratio(
                leading_count / record_count if record_count else 0.0
            )
            if values[share_name] != expected_leading_share:
                raise CoverageAnatomyError(
                    f"{period_context}.candidate_metrics.{share_name} is inconsistent with record_count"
                )

        for count_name in ("publisher_count", "story_cluster_count"):
            if values[count_name] > record_count:
                raise CoverageAnatomyError(
                    f"{period_context}.candidate_metrics.{count_name} exceeds record_count"
                )


def select_coverage_anatomy(
    news_wire: Mapping[str, Any],
    candidate_identifier: str,
) -> CoverageAnatomySelection:
    """Select one explicit candidate's comparable structural evidence."""

    if not isinstance(candidate_identifier, str) or not _CANONICAL_ID.fullmatch(
        candidate_identifier
    ):
        raise CoverageAnatomyError("candidate ID must be a canonical lowercase FR27 ID")
    payload = _object(news_wire, "news_wire")
    visibility = _object(payload.get("candidate_visibility"), "candidate_visibility")
    _require_fields(
        visibility,
        {"method", "primary_scopes", "prior_period", "current_period", "comparison_quality"},
        "candidate_visibility",
    )
    method = _text(visibility["method"], "candidate_visibility.method")
    if method != _UPSTREAM_METHOD:
        raise CoverageAnatomyError(
            f"candidate_visibility.method must be {_UPSTREAM_METHOD!r}"
        )
    scopes = visibility["primary_scopes"]
    if (
        not isinstance(scopes, list)
        or len(scopes) != len(_PRIMARY_SCOPES)
        or set(scopes) != _PRIMARY_SCOPES
    ):
        raise CoverageAnatomyError(
            "candidate_visibility.primary_scopes must contain campaign and election"
        )

    quality = _select_quality(visibility["comparison_quality"])
    periods: dict[str, dict[str, Any]] = {}
    candidate_names: list[str] = []
    selected_counts: dict[str, tuple[int, int, int, int]] = {}
    for period_name in _PERIOD_NAMES:
        (
            period,
            name,
            record_count,
            publisher_count,
            period_record_count,
            period_publisher_count,
        ) = _select_period(
            visibility[period_name], period_name, candidate_identifier
        )
        periods[period_name] = period
        candidate_names.append(name)
        selected_counts[period_name] = (
            record_count,
            publisher_count,
            period_record_count,
            period_publisher_count,
        )

    if candidate_names[0] != candidate_names[1]:
        raise CoverageAnatomyError(
            "selected candidate display name differs between comparative periods"
        )
    if candidate_id(candidate_names[0]) != candidate_identifier:
        raise CoverageAnatomyError("selected candidate does not match the requested candidate ID")
    prior_end = date.fromisoformat(periods["prior_period"]["end"])
    current_start = date.fromisoformat(periods["current_period"]["start"])
    if current_start != prior_end + timedelta(days=1):
        raise CoverageAnatomyError("candidate_visibility comparative periods must be adjacent")

    for period_name, quality_prefix in (
        ("prior_period", "prior"),
        ("current_period", "current"),
    ):
        (
            record_count,
            publisher_count,
            period_record_count,
            period_publisher_count,
        ) = selected_counts[period_name]
        if quality[f"{quality_prefix}_record_count"] != period_record_count:
            raise CoverageAnatomyError(
                f"comparison_quality {quality_prefix}_record_count differs from {period_name}"
            )
        if quality[f"{quality_prefix}_publisher_count"] != period_publisher_count:
            raise CoverageAnatomyError(
                f"comparison_quality {quality_prefix}_publisher_count differs from {period_name}"
            )
        if record_count > period_record_count:
            raise CoverageAnatomyError(
                f"selected candidate record_count exceeds {period_name} record_count"
            )
        if publisher_count > period_publisher_count:
            raise CoverageAnatomyError(
                f"selected candidate publisher_count exceeds {period_name} publisher_count"
            )

    evidence = {
        "scope": _observed(sorted(_PRIMARY_SCOPES), "candidate_visibility_scopes"),
        "prior_period": periods["prior_period"],
        "current_period": periods["current_period"],
        "comparison_quality": _observed(quality, "upstream_comparison_quality"),
    }
    validate_coverage_anatomy_evidence(evidence)
    return CoverageAnatomySelection(
        candidate_id=candidate_identifier,
        candidate_name=candidate_names[0],
        observation_window={
            "start": periods["prior_period"]["start"],
            "end": periods["current_period"]["end"],
        },
        evidence=deepcopy(evidence),
    )


def extract_live_coverage_anatomy(candidate_identifier: str) -> CoverageAnatomySelection:
    """Read only repository-root news_wire.json and select one explicit candidate."""

    with NEWS_WIRE_PATH.open(encoding="utf-8") as source_file:
        payload = json.load(source_file)
    return select_coverage_anatomy(payload, candidate_identifier)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract one candidate's read-only Coverage Anatomy TRACE evidence"
    )
    parser.add_argument("--candidate-id", required=True, help="canonical FR27 candidate ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        selection = extract_live_coverage_anatomy(arguments.candidate_id)
    except CoverageAnatomyError as exc:
        raise SystemExit(f"Coverage Anatomy extraction failed: {exc}") from exc
    print(
        json.dumps(
            {"candidate_name": selection.candidate_name, "trace": selection.build_trace()},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
