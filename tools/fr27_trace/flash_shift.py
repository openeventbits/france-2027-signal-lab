"""Read-only Flash/Shift extraction for the Candidate TRACE family.

``flash_shift.v1`` deliberately freezes the Candidate Attention classifier
semantics that were in production when this detector version was introduced.
The production builder is not imported: this module uses the pure production
artifact validator, then independently verifies the stored flag against the
frozen constants and precedence below.
"""

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

from candidate_attention_contract import (
    CandidateAttentionContractError,
    EVIDENCE_OBSERVED,
    EVIDENCE_UNAVAILABLE_NO_PERSONAL_ARTICLE,
    SCHEMA_VERSION as CANDIDATE_ATTENTION_SCHEMA_VERSION,
    SOURCE_ACCESS,
    SOURCE_AGENT,
    SOURCE_GRANULARITY,
    SOURCE_METRIC,
    SOURCE_PROJECT,
    validate_candidate_attention,
)

from .contract import build_draft_trace


DETECTOR_ID = "flash_shift.v1"
FIELD_TYPE = "flash_shift"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ATTENTION_PATH = REPOSITORY_ROOT / "candidate_attention.json"

# Frozen parity with build_candidate_attention.py for flash_shift.v1. A
# material upstream semantic change requires deliberate detector versioning.
LOW_BASE_7D_VIEWS = 3000
SUSTAINED_CHANGE_MIN_PCT = 5.0
EVENT_AMPLIFIED_RAW_MIN_PCT = 10.0
EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT = 15.0
EVENT_AMPLIFIED_RETAINED_RATIO_MAX = 0.40
EVENT_AMPLIFIED_PEAK_SHARE_MIN = 0.35

ALLOWED_FLAGS = frozenset(
    {
        "low_base",
        "stable",
        "event_amplified",
        "sustained_rise",
        "sustained_decline",
    }
)
ELIGIBLE_FLAGS = frozenset(
    {"event_amplified", "sustained_rise", "sustained_decline"}
)
CLASSIFICATION_LABELS = {
    "event_amplified": "FLASH",
    "sustained_rise": "SHIFT · RISE",
    "sustained_decline": "SHIFT · DECLINE",
}

_CANONICAL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SOURCE_VALUE = {
    "project": SOURCE_PROJECT,
    "metric": SOURCE_METRIC,
    "access": SOURCE_ACCESS,
    "agent": SOURCE_AGENT,
    "granularity": SOURCE_GRANULARITY,
}
_METRIC_UNITS = {
    "previous_7_views": "pageviews",
    "latest_7_views": "pageviews",
    "change_7_pct": "percent",
    "latest_7_peak_date": "utc_date",
    "latest_7_peak_views": "pageviews",
    "latest_7_peak_share": "ratio",
    "change_7_peak_removed_pct": "percent",
}


class FlashShiftError(ValueError):
    """Raised when upstream evidence is malformed or selection is unsafe."""


@dataclass(frozen=True)
class FlashShiftSelection:
    """An eligible TRACE selection or a valid, explicit suppression."""

    candidate_id: str
    candidate_name: str
    evidence_state: str
    interpretation_flag: str | None
    status: str
    suppression_reason: str | None
    observation_window: Mapping[str, str] | None
    evidence: Mapping[str, Any] | None

    @property
    def eligible(self) -> bool:
        return self.status == "eligible"

    @property
    def classification_label(self) -> str | None:
        if self.interpretation_flag is None:
            return None
        return CLASSIFICATION_LABELS.get(self.interpretation_flag)

    def build_trace(self) -> dict[str, Any] | None:
        """Build the Candidate TRACE when eligible; suppression returns None."""

        if not self.eligible:
            return None
        if self.evidence is None or self.observation_window is None:
            raise FlashShiftError("eligible Flash/Shift selection lacks evidence")
        validate_flash_shift_evidence(self.evidence)
        return build_draft_trace(
            family="candidate",
            detector_id=DETECTOR_ID,
            primary_entity_ids=[self.candidate_id],
            observation_window=self.observation_window,
            evidence=self.evidence,
        )


def percentage_change(current: int, previous: int) -> float | None:
    """Mirror production Candidate Attention one-decimal arithmetic."""

    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100.0, 1)


def frozen_interpretation_flag(metrics: Mapping[str, Any]) -> str:
    """Recompute the exact classifier frozen for ``flash_shift.v1``."""

    latest_7_views = metrics["latest_7_views"]
    raw_change = metrics["change_7_pct"]
    peak_removed_change = metrics["change_7_peak_removed_pct"]
    peak_share = metrics["latest_7_peak_share"]

    if latest_7_views < LOW_BASE_7D_VIEWS:
        return "low_base"

    if raw_change is None or peak_removed_change is None:
        return "stable"

    raw_abs = abs(raw_change)
    adjusted_abs = abs(peak_removed_change)
    opposite_or_removed = (
        raw_change != 0
        and (
            peak_removed_change == 0
            or (raw_change > 0 and peak_removed_change < 0)
            or (raw_change < 0 and peak_removed_change > 0)
        )
    )
    difference = abs(raw_change - peak_removed_change)
    retained_ratio = adjusted_abs / raw_abs if raw_abs > 0 else 1.0
    event_amplified = (
        raw_abs >= EVENT_AMPLIFIED_RAW_MIN_PCT
        and (
            opposite_or_removed
            or (
                difference >= EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT
                and retained_ratio <= EVENT_AMPLIFIED_RETAINED_RATIO_MAX
            )
            or (
                peak_share is not None
                and peak_share >= EVENT_AMPLIFIED_PEAK_SHARE_MIN
                and adjusted_abs < SUSTAINED_CHANGE_MIN_PCT
            )
        )
    )
    if event_amplified:
        return "event_amplified"
    if (
        raw_change >= SUSTAINED_CHANGE_MIN_PCT
        and peak_removed_change >= SUSTAINED_CHANGE_MIN_PCT
    ):
        return "sustained_rise"
    if (
        raw_change <= -SUSTAINED_CHANGE_MIN_PCT
        and peak_removed_change <= -SUSTAINED_CHANGE_MIN_PCT
    ):
        return "sustained_decline"
    return "stable"


def _object(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FlashShiftError(f"{context} must be an object")
    return value


def _date_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FlashShiftError(f"{context} must be a canonical ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise FlashShiftError(f"{context} must be a canonical ISO date") from exc
    if parsed.isoformat() != value:
        raise FlashShiftError(f"{context} must be a canonical ISO date")
    return value


def _non_negative_integer(value: Any, context: str) -> int:
    if type(value) is not int or value < 0:
        raise FlashShiftError(f"{context} must be a non-negative integer")
    return value


def _number(value: Any, context: str) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FlashShiftError(f"{context} must be a finite number")
    return value


def _observed(value: Any, unit: str) -> dict[str, Any]:
    return {"availability": "observed", "unit": unit, "value": value}


def _derived(value: Any, unit: str) -> dict[str, Any]:
    if value is None:
        return {"availability": "unavailable", "unit": unit}
    return _observed(value, unit)


def _record_value(
    record: Any,
    context: str,
    unit: str,
    *,
    allow_unavailable: bool = False,
) -> Any:
    value = _object(record, context)
    expected_observed = {"availability", "unit", "value"}
    expected_unavailable = {"availability", "unit"}
    if value.get("unit") != unit:
        raise FlashShiftError(f"{context}.unit must be {unit!r}")
    if value.get("availability") == "observed" and set(value) == expected_observed:
        return value["value"]
    if (
        allow_unavailable
        and value.get("availability") == "unavailable"
        and set(value) == expected_unavailable
    ):
        return None
    raise FlashShiftError(f"{context} has an invalid availability record")


def _window_peak(observations: list[dict[str, Any]]) -> dict[str, Any]:
    # Ascending observations plus max() preserves production's earliest tie.
    return max(observations, key=lambda observation: observation["views"])


def _validate_window(value: Any, name: str) -> list[dict[str, Any]]:
    context = f"evidence.{name}"
    window = _object(value, context)
    if set(window) != {"start", "end", "daily_views"}:
        raise FlashShiftError(f"{context} has unexpected fields")
    start = _date_text(window["start"], f"{context}.start")
    end = _date_text(window["end"], f"{context}.end")
    days = window["daily_views"]
    if not isinstance(days, list) or len(days) != 7:
        raise FlashShiftError(f"{context}.daily_views must contain exactly seven days")
    expected_dates = [
        (date.fromisoformat(start) + timedelta(days=offset)).isoformat()
        for offset in range(7)
    ]
    if expected_dates[-1] != end:
        raise FlashShiftError(f"{context} must span exactly seven days")
    observations: list[dict[str, Any]] = []
    for index, raw_day in enumerate(days):
        day_context = f"{context}.daily_views[{index}]"
        day = _object(raw_day, day_context)
        if set(day) != {"date", "views"}:
            raise FlashShiftError(f"{day_context} has unexpected fields")
        observed_date = _date_text(day["date"], f"{day_context}.date")
        if observed_date != expected_dates[index]:
            raise FlashShiftError("Flash/Shift daily dates must be exact and continuous")
        views = _record_value(day["views"], f"{day_context}.views", "pageviews")
        observations.append(
            {"date": observed_date, "views": _non_negative_integer(views, f"{day_context}.views.value")}
        )
    return observations


def validate_flash_shift_evidence(evidence: Mapping[str, Any]) -> None:
    """Validate the narrow 14-day evidence and all derived relationships."""

    selected = _object(evidence, "evidence")
    if set(selected) != {
        "source",
        "classification",
        "previous_7",
        "latest_7",
        "metrics",
    }:
        raise FlashShiftError("Flash/Shift evidence has unexpected fields")

    source_value = _record_value(
        selected["source"], "evidence.source", "wikimedia_pageview_scope"
    )
    if source_value != _SOURCE_VALUE:
        raise FlashShiftError("evidence.source does not match the locked source scope")

    flag = _record_value(
        selected["classification"],
        "evidence.classification",
        "candidate_attention_interpretation_flag",
    )
    if flag not in ALLOWED_FLAGS:
        raise FlashShiftError("evidence.classification contains an invalid flag")

    previous = _validate_window(selected["previous_7"], "previous_7")
    latest = _validate_window(selected["latest_7"], "latest_7")
    if date.fromisoformat(latest[0]["date"]) != date.fromisoformat(previous[-1]["date"]) + timedelta(days=1):
        raise FlashShiftError("Flash/Shift seven-day windows must be adjacent")

    metrics = _object(selected["metrics"], "evidence.metrics")
    if set(metrics) != set(_METRIC_UNITS):
        raise FlashShiftError("evidence.metrics has unexpected fields")
    values: dict[str, Any] = {}
    for name, unit in _METRIC_UNITS.items():
        values[name] = _record_value(
            metrics[name],
            f"evidence.metrics.{name}",
            unit,
            allow_unavailable=name in {
                "change_7_pct",
                "latest_7_peak_share",
                "change_7_peak_removed_pct",
            },
        )
    for name in ("previous_7_views", "latest_7_views", "latest_7_peak_views"):
        values[name] = _non_negative_integer(
            values[name], f"evidence.metrics.{name}.value"
        )
    values["latest_7_peak_date"] = _date_text(
        values["latest_7_peak_date"],
        "evidence.metrics.latest_7_peak_date.value",
    )
    for name in (
        "change_7_pct",
        "latest_7_peak_share",
        "change_7_peak_removed_pct",
    ):
        if values[name] is not None:
            values[name] = _number(values[name], f"evidence.metrics.{name}.value")
    if values["latest_7_peak_share"] is not None and not 0 <= values["latest_7_peak_share"] <= 1:
        raise FlashShiftError("evidence.metrics.latest_7_peak_share.value must be a ratio")

    previous_total = sum(day["views"] for day in previous)
    latest_total = sum(day["views"] for day in latest)
    previous_peak = _window_peak(previous)
    latest_peak = _window_peak(latest)
    expected = {
        "previous_7_views": previous_total,
        "latest_7_views": latest_total,
        "change_7_pct": percentage_change(latest_total, previous_total),
        "latest_7_peak_date": latest_peak["date"],
        "latest_7_peak_views": latest_peak["views"],
        "latest_7_peak_share": (
            None if latest_total == 0 else round(latest_peak["views"] / latest_total, 4)
        ),
        "change_7_peak_removed_pct": percentage_change(
            latest_total - latest_peak["views"],
            previous_total - previous_peak["views"],
        ),
    }
    for name, expected_value in expected.items():
        actual = values[name]
        if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            if actual is None or abs(float(actual) - float(expected_value)) > 1e-9:
                raise FlashShiftError(f"evidence.metrics.{name} is inconsistent with daily views")
        elif actual != expected_value:
            raise FlashShiftError(f"evidence.metrics.{name} is inconsistent with daily views")

    classifier_metrics = {
        "latest_7_views": values["latest_7_views"],
        "change_7_pct": values["change_7_pct"],
        "latest_7_peak_share": values["latest_7_peak_share"],
        "change_7_peak_removed_pct": values["change_7_peak_removed_pct"],
    }
    expected_flag = frozen_interpretation_flag(classifier_metrics)
    if flag != expected_flag:
        raise FlashShiftError(
            "evidence.classification does not match the frozen flash_shift.v1 classifier"
        )


def _selected_evidence(candidate: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    series = candidate["daily_series"]
    previous = series[-14:-7]
    latest = series[-7:]
    evidence = {
        "source": _observed(
            {
                "project": source["project"],
                "metric": source["metric"],
                "access": source["access"],
                "agent": source["agent"],
                "granularity": source["granularity"],
            },
            "wikimedia_pageview_scope",
        ),
        "classification": _observed(
            candidate["interpretation_flag"],
            "candidate_attention_interpretation_flag",
        ),
        "previous_7": {
            "start": previous[0]["date"],
            "end": previous[-1]["date"],
            "daily_views": [
                {"date": day["date"], "views": _observed(day["views"], "pageviews")}
                for day in previous
            ],
        },
        "latest_7": {
            "start": latest[0]["date"],
            "end": latest[-1]["date"],
            "daily_views": [
                {"date": day["date"], "views": _observed(day["views"], "pageviews")}
                for day in latest
            ],
        },
        "metrics": {
            name: _derived(candidate[name], unit)
            for name, unit in _METRIC_UNITS.items()
        },
    }
    validate_flash_shift_evidence(evidence)
    return evidence


def select_flash_shift(
    candidate_attention: Mapping[str, Any],
    candidate_identifier: str,
) -> FlashShiftSelection:
    """Validate production evidence and select one exact canonical candidate."""

    if not isinstance(candidate_identifier, str) or not _CANONICAL_ID.fullmatch(candidate_identifier):
        raise FlashShiftError("candidate ID must be a canonical lowercase FR27 ID")
    payload = _object(candidate_attention, "candidate_attention")
    if payload.get("schema_version") != CANDIDATE_ATTENTION_SCHEMA_VERSION:
        raise FlashShiftError(
            f"candidate_attention schema_version must equal {CANDIDATE_ATTENTION_SCHEMA_VERSION}"
        )
    try:
        validate_candidate_attention(dict(payload))
    except CandidateAttentionContractError as exc:
        raise FlashShiftError(f"invalid candidate_attention.json: {exc}") from exc

    candidate = next(
        (
            row
            for row in payload["candidates"]
            if row["candidate_id"] == candidate_identifier
        ),
        None,
    )
    if candidate is None:
        raise FlashShiftError(f"candidate {candidate_identifier!r} is absent")

    candidate_name = candidate["candidate_name"]
    evidence_state = candidate["evidence_state"]
    if evidence_state == EVIDENCE_UNAVAILABLE_NO_PERSONAL_ARTICLE:
        return FlashShiftSelection(
            candidate_id=candidate_identifier,
            candidate_name=candidate_name,
            evidence_state=evidence_state,
            interpretation_flag=None,
            status="suppressed",
            suppression_reason="unavailable",
            observation_window=None,
            evidence=None,
        )
    if evidence_state != EVIDENCE_OBSERVED:
        raise FlashShiftError(f"candidate evidence_state {evidence_state!r} is invalid")

    evidence = _selected_evidence(candidate, payload["source"])
    flag = candidate["interpretation_flag"]
    observation_window = {
        "start": evidence["previous_7"]["start"],
        "end": evidence["latest_7"]["end"],
    }
    eligible = flag in ELIGIBLE_FLAGS
    return FlashShiftSelection(
        candidate_id=candidate_identifier,
        candidate_name=candidate_name,
        evidence_state=evidence_state,
        interpretation_flag=flag,
        status="eligible" if eligible else "suppressed",
        suppression_reason=None if eligible else flag,
        observation_window=observation_window,
        evidence=deepcopy(evidence),
    )


def extract_live_flash_shift(candidate_identifier: str) -> FlashShiftSelection:
    """Read only repository-root candidate_attention.json for one exact ID."""

    with CANDIDATE_ATTENTION_PATH.open(encoding="utf-8") as source_file:
        payload = json.load(source_file)
    return select_flash_shift(payload, candidate_identifier)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract one candidate's read-only Flash/Shift TRACE evidence"
    )
    parser.add_argument("--candidate-id", required=True, help="canonical FR27 candidate ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        selection = extract_live_flash_shift(arguments.candidate_id)
    except FlashShiftError as exc:
        raise SystemExit(f"Flash/Shift extraction failed: {exc}") from exc
    output = {
        "candidate_id": selection.candidate_id,
        "candidate_name": selection.candidate_name,
        "evidence_state": selection.evidence_state,
        "interpretation_flag": selection.interpretation_flag,
        "status": selection.status,
        "suppression_reason": selection.suppression_reason,
        "observation_window": selection.observation_window,
        "trace": selection.build_trace(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
