"""Presentation-only model for the fixed TRACE renderer shell."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..contract import ContractError, validate_trace
from ..coverage_anatomy import (
    CoverageAnatomyError,
    validate_coverage_anatomy_evidence,
)
from ..flash_shift import (
    CLASSIFICATION_LABELS,
    FlashShiftError,
    validate_flash_shift_evidence,
)


FAMILY_LABELS = {
    "candidate": "CANDIDATE",
    "field": "FIELD",
    "issue": "ISSUE",
    "story": "STORY",
    "event": "EVENT",
}
RENDERER_VERSION = "trace-shell.v1"

_REQUIRED_PRESENTATION_FIELDS = frozenset(
    {
        "language",
        "display_label",
        "finding",
        "source_scope",
        "methodological_boundary",
        "observation_window_display",
        "renderer_version",
    }
)
_OPTIONAL_PRESENTATION_FIELDS = frozenset({"qualifier", "field_type"})
_MAX_LENGTHS = {
    "display_label": 48,
    "finding": 120,
    "qualifier": 96,
    "source_scope": 88,
    "methodological_boundary": 88,
    "observation_window_display": 40,
    "renderer_version": 32,
}

_COVERAGE_FIELD_TYPE = "coverage_anatomy"
_FLASH_SHIFT_FIELD_TYPE = "flash_shift"
_COVERAGE_ROW_DEFINITIONS = (
    ("share", "COVERAGE SHARE", "percent", "OF PERIOD CANDIDATE-LINKED COVERAGE"),
    ("publisher_count", "PUBLISHERS", "count", "PUBLISHER COUNT"),
    ("story_cluster_count", "STORY CLUSTERS", "count", "STORY CLUSTER COUNT"),
    ("leading_story_share", "LARGEST STORY", "percent", "OF CANDIDATE-LINKED COVERAGE"),
    ("leading_publisher_share", "TOP PUBLISHER", "percent", "OF CANDIDATE-LINKED COVERAGE"),
)
class RenderModelError(ValueError):
    """Raised when presentation data cannot safely fit the frozen shell."""


def _one_line_text(value: Any, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise RenderModelError(f"presentation.{field} must be a non-empty string")
    if value != value.strip():
        raise RenderModelError(f"presentation.{field} must not have surrounding whitespace")
    if any(character in value for character in ("\r", "\n", "\t")):
        raise RenderModelError(f"presentation.{field} must be one line")
    if len(value) > _MAX_LENGTHS[field]:
        raise RenderModelError(
            f"presentation.{field} exceeds {_MAX_LENGTHS[field]} characters"
        )
    return value


def _coverage_value(
    period: Mapping[str, Any],
    metric: str,
) -> int | float:
    return period["candidate_metrics"][metric]["value"]


def _format_coverage_value(value: int | float, kind: str) -> str:
    if kind == "count":
        if type(value) is not int:
            raise RenderModelError("Coverage Anatomy count values must be integers")
        return str(value)
    if value > 1:
        raise RenderModelError("Coverage Anatomy ratio values must be at most one")
    percentage = f"{value * 100:.1f}".rstrip("0").rstrip(".")
    return f"{percentage}%"


def _coverage_field_payload(trace: Mapping[str, Any]) -> dict[str, Any]:
    if trace["family"] != "candidate" or trace["detector_id"] != "coverage_anatomy.v1":
        raise RenderModelError(
            "coverage_anatomy field requires family='candidate' and detector_id='coverage_anatomy.v1'"
        )
    try:
        validate_coverage_anatomy_evidence(trace["evidence"])
    except CoverageAnatomyError as exc:
        raise RenderModelError(f"invalid Coverage Anatomy evidence: {exc}") from exc

    prior = trace["evidence"]["prior_period"]
    current = trace["evidence"]["current_period"]
    rows = []
    for key, label, kind, unit_label in _COVERAGE_ROW_DEFINITIONS:
        prior_value = _coverage_value(prior, key)
        current_value = _coverage_value(current, key)
        rows.append(
            {
                "key": key,
                "label": label,
                "unitLabel": unit_label,
                "prior": _format_coverage_value(prior_value, kind),
                "current": _format_coverage_value(current_value, kind),
            }
        )
    return {
        "priorLabel": "PRIOR",
        "priorDates": f"{prior['start']} — {prior['end']}",
        "currentLabel": "CURRENT",
        "currentDates": f"{current['start']} — {current['end']}",
        "rows": rows,
    }


def _signed_percent(value: int | float) -> str:
    return f"{value:+.1f}%"


def _flash_shift_field_payload(trace: Mapping[str, Any]) -> dict[str, Any]:
    if trace["family"] != "candidate" or trace["detector_id"] != "flash_shift.v1":
        raise RenderModelError(
            "flash_shift field requires family='candidate' and detector_id='flash_shift.v1'"
        )
    try:
        validate_flash_shift_evidence(trace["evidence"])
    except FlashShiftError as exc:
        raise RenderModelError(f"invalid Flash/Shift evidence: {exc}") from exc

    evidence = trace["evidence"]
    flag = evidence["classification"]["value"]
    if flag not in CLASSIFICATION_LABELS:
        raise RenderModelError("flash_shift field requires an eligible classification")
    previous = evidence["previous_7"]
    latest = evidence["latest_7"]
    observations = [
        (day, "previous") for day in previous["daily_views"]
    ] + [
        (day, "latest") for day in latest["daily_views"]
    ]
    maximum = max(day["views"]["value"] for day, _window in observations)
    peak_date = evidence["metrics"]["latest_7_peak_date"]["value"]
    days = []
    for day, window in observations:
        views = day["views"]["value"]
        days.append(
            {
                "date": day["date"],
                "dateLabel": day["date"][5:].replace("-", "/"),
                "views": views,
                "viewsLabel": f"{views:,}",
                "window": window,
                "heightPercent": 0 if maximum == 0 else round(views / maximum * 100, 4),
                "isPeak": window == "latest" and day["date"] == peak_date,
            }
        )

    metrics = evidence["metrics"]
    previous_total = metrics["previous_7_views"]["value"]
    latest_total = metrics["latest_7_views"]["value"]
    raw_change = metrics["change_7_pct"]["value"]
    peak_removed = metrics["change_7_peak_removed_pct"]["value"]
    peak_share = metrics["latest_7_peak_share"]["value"]
    return {
        "componentLabel": "FLASH / SHIFT · WIKIPEDIA ATTENTION",
        "classificationLabel": CLASSIFICATION_LABELS[flag],
        "previousLabel": "PREVIOUS 7 DAYS",
        "previousDates": f"{previous['start']} — {previous['end']}",
        "latestLabel": "LATEST 7 DAYS",
        "latestDates": f"{latest['start']} — {latest['end']}",
        "days": days,
        "summary": [
            {"key": "previous", "label": "PREVIOUS 7D", "value": f"{previous_total:,}"},
            {"key": "latest", "label": "LATEST 7D", "value": f"{latest_total:,}"},
            {"key": "change", "label": "CHANGE", "value": _signed_percent(raw_change)},
            {
                "key": "peak_removed",
                "label": "PEAK-REMOVED",
                "value": _signed_percent(peak_removed),
            },
            {"key": "peak_share", "label": "PEAK SHARE", "value": f"{peak_share * 100:.1f}%"},
        ],
    }


@dataclass(frozen=True)
class TraceRenderModel:
    """Validated TRACE identity plus non-identity presentation metadata."""

    trace: Mapping[str, Any]
    language: str
    display_label: str
    finding: str
    qualifier: str | None
    source_scope: str
    methodological_boundary: str
    observation_window_display: str
    renderer_version: str
    field_type: str | None

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "TraceRenderModel":
        if not isinstance(document, Mapping) or set(document) != {"trace", "presentation"}:
            raise RenderModelError("render fixture must contain exactly trace and presentation")

        trace = document["trace"]
        presentation = document["presentation"]
        if not isinstance(trace, Mapping):
            raise RenderModelError("trace must be an object")
        try:
            validate_trace(trace)
        except ContractError as exc:
            raise RenderModelError(f"invalid TRACE object: {exc}") from exc
        if not isinstance(presentation, Mapping):
            raise RenderModelError("presentation must be an object")
        fields = set(presentation)
        missing = _REQUIRED_PRESENTATION_FIELDS - fields
        if missing:
            raise RenderModelError(
                "presentation is missing required fields: " + ", ".join(sorted(missing))
            )
        unknown = fields - _REQUIRED_PRESENTATION_FIELDS - _OPTIONAL_PRESENTATION_FIELDS
        if unknown:
            raise RenderModelError(
                "presentation contains unknown fields: " + ", ".join(sorted(unknown))
            )

        language = presentation["language"]
        if language not in {"fr", "en"}:
            raise RenderModelError("presentation.language must be fr or en")
        if "language" in trace and trace["language"] != language:
            raise RenderModelError("presentation.language must match TRACE language when present")
        renderer_version = _one_line_text(
            presentation["renderer_version"], "renderer_version"
        )
        if renderer_version != RENDERER_VERSION:
            raise RenderModelError(f"renderer_version must be {RENDERER_VERSION!r}")
        field_type = presentation.get("field_type")
        if field_type is not None and field_type not in {
            _COVERAGE_FIELD_TYPE,
            _FLASH_SHIFT_FIELD_TYPE,
        }:
            raise RenderModelError("presentation.field_type is not supported")
        if field_type == _COVERAGE_FIELD_TYPE:
            _coverage_field_payload(trace)
        elif field_type == _FLASH_SHIFT_FIELD_TYPE:
            _flash_shift_field_payload(trace)

        return cls(
            trace=deepcopy(dict(trace)),
            language=language,
            display_label=_one_line_text(presentation["display_label"], "display_label"),
            finding=_one_line_text(presentation["finding"], "finding"),
            qualifier=_one_line_text(
                presentation.get("qualifier"), "qualifier", required=False
            ),
            source_scope=_one_line_text(presentation["source_scope"], "source_scope"),
            methodological_boundary=_one_line_text(
                presentation["methodological_boundary"], "methodological_boundary"
            ),
            observation_window_display=_one_line_text(
                presentation["observation_window_display"],
                "observation_window_display",
            ),
            renderer_version=renderer_version,
            field_type=field_type,
        )

    @property
    def family_label(self) -> str:
        return FAMILY_LABELS[self.trace["family"]]

    def to_payload(self) -> dict[str, Any]:
        """Return the minimal DOM payload; evidence stays in the validated TRACE object."""

        payload = {
            "family": self.family_label,
            "status": "TRACE DRAFT",
            "language": self.language,
            "displayLabel": self.display_label,
            "finding": self.finding,
            "qualifier": self.qualifier,
            "sourceScope": self.source_scope,
            "methodologicalBoundary": self.methodological_boundary,
            "observationWindow": self.observation_window_display,
            "rendererVersion": self.renderer_version,
            "fieldType": self.field_type or "shell_preview",
        }
        if self.field_type == _COVERAGE_FIELD_TYPE:
            payload["field"] = _coverage_field_payload(self.trace)
        elif self.field_type == _FLASH_SHIFT_FIELD_TYPE:
            payload["field"] = _flash_shift_field_payload(self.trace)
        return payload
