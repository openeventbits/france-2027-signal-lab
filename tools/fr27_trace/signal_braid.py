"""Task 05 Candidate Trace / Signal Braid v1.

This module is deliberately a narrow, read-only adapter over established
production artifacts.  It does not write production data, fetch network data,
or create a cross-lane score.  Media and agenda are separate observables drawn
from shared candidate-linked news evidence; they are not independent sources.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from candidate_attention_contract import (
    CandidateAttentionContractError,
    validate_candidate_attention,
)
from candidate_visibility_history_contract import (
    CandidateVisibilityHistoryContractError,
    validate_candidate_visibility_history,
)

from .contract import ContractError, build_draft_trace, validate_trace
from .coverage_anatomy import (
    DETECTOR_ID as COVERAGE_ANATOMY_DETECTOR_ID,
    CoverageAnatomyError,
    extract_live_coverage_anatomy,
    validate_coverage_anatomy_evidence,
)
from .flash_shift import (
    DETECTOR_ID as FLASH_SHIFT_DETECTOR_ID,
    FlashShiftError,
    select_flash_shift,
)


DETECTOR_ID = "signal_braid.v1"
FAMILY = "candidate"
FIELD_TYPE = "signal_braid"
WINDOW_DAYS = 28

SUPPRESSION_INSUFFICIENT_COVERAGE = "insufficient_longitudinal_coverage"
SUPPRESSION_NO_QUALIFYING_SIGNAL = "no_qualifying_signal"
SUPPRESSION_NO_COMMON_WINDOW = "no_common_28_day_window"
SUPPRESSION_CODES = frozenset(
    {
        SUPPRESSION_INSUFFICIENT_COVERAGE,
        SUPPRESSION_NO_QUALIFYING_SIGNAL,
        SUPPRESSION_NO_COMMON_WINDOW,
    }
)

FLASH_FINDINGS = {
    "event_amplified": "WIKIPEDIA ATTENTION SHOWED A FLASH PATTERN.",
    "sustained_rise": "WIKIPEDIA ATTENTION SHOWED A SHIFT · RISE PATTERN.",
    "sustained_decline": "WIKIPEDIA ATTENTION SHOWED A SHIFT · DECLINE PATTERN.",
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRACE_KEY_RE = re.compile(r"^trace_[0-9a-f]{64}$")
_CANONICAL_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MONTH_LABELS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)
POLICY_TOPICS = (
    "economy_public_finances",
    "work_purchasing_power_pensions",
    "immigration_identity_secularism",
    "security_justice",
    "health_education_public_services",
    "climate_energy_agriculture",
    "europe_defence_foreign_affairs",
    "institutions_democracy_territories",
)
CAMPAIGN_TOPICS = (
    "legal_eligibility",
    "selection_strategy",
    "candidacies_endorsements",
    "rules_calendar",
    "positioning_integrity",
    "polls_race",
)

_ROOT = Path(__file__).resolve().parents[2]
_MEDIA_PATH = _ROOT / "candidate_visibility_history.json"
_WIKIPEDIA_PATH = _ROOT / "candidate_attention.json"
_AGENDA_PATH = _ROOT / "candidate_agenda_history.json"
_POLL_HISTORY_PATH = _ROOT / "candidate_signals.json"
_CANDIDACY_PATH = _ROOT / "candidate_candidacy_status.json"


class SignalBraidError(ValueError):
    """Raised when source evidence or component relationships fail closed."""


@dataclass(frozen=True)
class SignalBraidSelection:
    """Deterministic selection result for one explicit canonical candidate."""

    candidate_id: str
    candidate_name: str
    status: str
    suppression_reason: str | None
    observation_window: dict[str, str] | None
    evidence: dict[str, Any] | None
    flash_status: str
    flash_classification: str | None
    coverage_status: str

    @property
    def eligible(self) -> bool:
        return self.status == "eligible"

    @property
    def finding(self) -> str | None:
        if not self.eligible or self.evidence is None:
            return None
        return signal_braid_finding(self.evidence)

    @property
    def qualifier(self) -> str:
        if not self.eligible or self.evidence is None:
            return ""
        return signal_braid_qualifier(self.evidence) or ""

    def build_trace(self) -> dict[str, Any] | None:
        if not self.eligible:
            return None
        if self.observation_window is None or self.evidence is None:
            raise SignalBraidError("eligible selection is missing identity evidence")
        validate_signal_braid_evidence(
            self.evidence,
            observation_window=self.observation_window,
            candidate_id=self.candidate_id,
        )
        return build_draft_trace(
            family=FAMILY,
            detector_id=DETECTOR_ID,
            primary_entity_ids=[self.candidate_id],
            observation_window=self.observation_window,
            evidence=self.evidence,
        )


def _parse_date(value: Any, *, field: str) -> date:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        raise SignalBraidError(f"{field} must be an ISO calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SignalBraidError(f"{field} must be a valid calendar date") from exc


def _require_canonical_candidate_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _CANONICAL_ID_RE.fullmatch(value):
        raise SignalBraidError(f"{field} must be a canonical lowercase FR27 ID")
    return value


def signal_braid_window_display(window: Mapping[str, Any]) -> str:
    """Return the deterministic, presentation-only Task 05 date label."""

    start = _parse_date(window.get("start"), field="display window start")
    end = _parse_date(window.get("end"), field="display window end")
    if end < start:
        raise SignalBraidError("display window end must not precede start")
    start_label = f"{start.day:02d} {_MONTH_LABELS[start.month - 1]}"
    end_label = f"{end.day:02d} {_MONTH_LABELS[end.month - 1]} {end.year}"
    if start.year != end.year:
        start_label += f" {start.year}"
    return f"{start_label} — {end_label} · UTC"


def signal_braid_finding(evidence: Mapping[str, Any]) -> str:
    """Return the only permitted public finding for validated Task 05 evidence."""

    annotations = _require_mapping(evidence.get("annotations"), field="annotations")
    flash = annotations.get("flash_shift")
    if flash is not None:
        classification = _require_mapping(
            _require_mapping(flash, field="annotations.flash_shift").get("value"),
            field="annotations.flash_shift.value",
        ).get("classification")
        if classification not in FLASH_FINDINGS:
            raise SignalBraidError("Flash/Shift classification has no Task 05 finding")
        return FLASH_FINDINGS[classification]
    poll_tests = _require_mapping(evidence.get("poll_tests"), field="poll_tests")
    count = len(poll_tests.get("value", []))
    if poll_tests.get("availability") != "observed" or count < 1:
        raise SignalBraidError("eligible Task 05 evidence has no finding trigger")
    noun = "PACKAGE" if count == 1 else "PACKAGES"
    return f"TESTED IN {count} FIRST-ROUND POLL {noun} THIS WINDOW."


def signal_braid_qualifier(evidence: Mapping[str, Any]) -> str | None:
    """Return the optional deterministic poll qualifier for a Flash/Shift finding."""

    annotations = _require_mapping(evidence.get("annotations"), field="annotations")
    poll_tests = _require_mapping(evidence.get("poll_tests"), field="poll_tests")
    count = len(poll_tests.get("value", []))
    if "flash_shift" not in annotations or poll_tests.get("availability") != "observed":
        return None
    noun = "package" if count == 1 else "packages"
    return f"Also tested in {count} accepted first-round poll {noun} this window."


def _date_strings(start: date, end: date) -> list[str]:
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SignalBraidError(f"{field} must be an object")
    return value


def _require_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise SignalBraidError(f"{field} must be an array")
    return value


def _require_nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SignalBraidError(f"{field} must be a non-negative integer")
    return value


def _validate_availability_record(
    record: Any,
    *,
    field: str,
    allowed: Iterable[str],
) -> Mapping[str, Any]:
    obj = _require_mapping(record, field=field)
    availability = obj.get("availability")
    allowed_set = set(allowed)
    if availability not in allowed_set:
        raise SignalBraidError(
            f"{field}.availability must be one of {sorted(allowed_set)}"
        )
    if availability == "observed":
        if "value" not in obj or obj.get("value") is None:
            raise SignalBraidError(f"{field} observed records require a value")
    elif "value" in obj:
        raise SignalBraidError(f"{field} non-observed records must omit value")
    return obj


def _canonical_candidates(
    controlled_candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    normalized: list[dict[str, str]] = []
    by_id: dict[str, str] = {}
    for index, candidate in enumerate(controlled_candidates):
        obj = _require_mapping(candidate, field=f"controlled_candidates[{index}]")
        candidate_id = obj.get("id", obj.get("candidate_id"))
        name = obj.get("name", obj.get("candidate_name"))
        _require_canonical_candidate_id(
            candidate_id, field=f"controlled_candidates[{index}].id"
        )
        if not isinstance(name, str) or not name:
            raise SignalBraidError(
                f"controlled_candidates[{index}].name must be a non-empty string"
            )
        if candidate_id in by_id:
            raise SignalBraidError(f"duplicate controlled candidate id: {candidate_id}")
        by_id[candidate_id] = name
        normalized.append(
            {"candidate_id": candidate_id, "candidate_name": name}
        )
    return normalized, by_id


def _find_candidate(
    payload: Mapping[str, Any],
    candidate_id: str,
    *,
    source: str,
    candidate_name: str,
    missing_ok: bool = False,
) -> Mapping[str, Any] | None:
    candidates = _require_list(payload.get("candidates"), field=f"{source}.candidates")
    matches = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("candidate_id") == candidate_id
    ]
    if len(matches) > 1:
        raise SignalBraidError(f"{source} contains duplicate candidate id {candidate_id}")
    if not matches:
        if missing_ok:
            return None
        raise SignalBraidError(f"{source} is missing controlled candidate {candidate_id}")
    candidate = matches[0]
    if candidate.get("candidate_name") != candidate_name:
        raise SignalBraidError(f"{source} candidate name disagrees with controlled identity")
    return candidate


def _validate_source_contracts(
    media_payload: Mapping[str, Any],
    wikipedia_payload: Mapping[str, Any],
    agenda_payload: Mapping[str, Any],
    controlled_candidates: Sequence[Mapping[str, Any]],
) -> None:
    # This contract imports the production taxonomy definitions through the
    # news builder module. Keep it outside module import time; selection still
    # validates it before reading any lane evidence.
    from candidate_agenda_history_contract import (
        CAMPAIGN_TAXONOMY,
        POLICY_TAXONOMY,
        CandidateAgendaHistoryContractError,
        validate_candidate_agenda_history,
    )

    expected_candidates, _ = _canonical_candidates(controlled_candidates)
    try:
        validate_candidate_visibility_history(
            media_payload,
            expected_candidates=expected_candidates,
        )
        validate_candidate_attention(wikipedia_payload)
        validate_candidate_agenda_history(
            agenda_payload,
            expected_candidates=expected_candidates,
        )
        if tuple(topic_id for topic_id, _label in POLICY_TAXONOMY) != POLICY_TOPICS:
            raise SignalBraidError("production policy taxonomy changed")
        if tuple(topic_id for topic_id, _label in CAMPAIGN_TAXONOMY) != CAMPAIGN_TOPICS:
            raise SignalBraidError("production campaign taxonomy changed")
    except (
        CandidateVisibilityHistoryContractError,
        CandidateAttentionContractError,
        CandidateAgendaHistoryContractError,
    ) as exc:
        raise SignalBraidError(f"malformed production source: {exc}") from exc


def _common_window(
    media_payload: Mapping[str, Any],
    wikipedia_payload: Mapping[str, Any],
    agenda_payload: Mapping[str, Any],
    *,
    current_utc_date: date,
) -> tuple[dict[str, str], list[str]] | None:
    media_period = _require_mapping(media_payload.get("period"), field="media.period")
    wikipedia_period = _require_mapping(
        wikipedia_payload.get("period"), field="wikipedia.period"
    )
    agenda_period = _require_mapping(agenda_payload.get("tracking"), field="agenda.tracking")

    if media_period.get("current_utc_day_excluded") is not True:
        raise SignalBraidError("media period must exclude the current UTC day")
    if media_period.get("day_boundary") != "UTC":
        raise SignalBraidError("media period must use UTC day boundaries")
    media_end = _parse_date(media_period.get("data_as_of"), field="media.data_as_of")
    wikipedia_end = _parse_date(
        wikipedia_period.get("data_as_of"), field="wikipedia.data_as_of"
    )
    agenda_end = _parse_date(
        agenda_period.get("data_as_of"), field="agenda.tracking.data_as_of"
    )
    common_end = min(media_end, wikipedia_end)
    if common_end >= current_utc_date:
        raise SignalBraidError(
            "common window end must precede the current UTC calendar date"
        )
    common_start = common_end - timedelta(days=WINDOW_DAYS - 1)

    media_start = _parse_date(
        media_period.get("start_date"), field="media.period.start_date"
    )
    wikipedia_start = _parse_date(
        wikipedia_period.get("start_date"), field="wikipedia.period.start_date"
    )
    agenda_start = _parse_date(
        agenda_period.get("start_date"), field="agenda.tracking.start_date"
    )
    if media_start > common_start or wikipedia_start > common_start:
        return None
    if agenda_start > common_end or agenda_end < common_end:
        return None
    days = _date_strings(common_start, common_end)
    if len(days) != WINDOW_DAYS:
        raise SignalBraidError("common window arithmetic must produce exactly 28 days")
    return (
        {"start": common_start.isoformat(), "end": common_end.isoformat()},
        days,
    )


def _media_evidence(candidate: Mapping[str, Any], days: Sequence[str]) -> dict[str, Any]:
    lane = _require_mapping(
        candidate.get("campaign_attention"), field="media.campaign_attention"
    )
    series = _require_list(lane.get("daily_series"), field="media.daily_series")
    by_date = {
        row.get("date"): row
        for row in series
        if isinstance(row, Mapping) and isinstance(row.get("date"), str)
    }
    selected: list[dict[str, Any]] = []
    for day in days:
        row = by_date.get(day)
        if row is None:
            raise SignalBraidError(f"media continuity is broken at {day}")
        count = _require_nonnegative_int(
            row.get("record_count"), field=f"media[{day}].record_count"
        )
        selected.append(
            {
                "date": day,
                "record_count": {
                    "availability": "observed",
                    "unit": "candidate_linked_records",
                    "value": count,
                },
            }
        )
    return {
        "semantics": {
            "availability": "observed",
            "unit": "media_scope",
            "value": {
                "source": "news_wire.json:candidate_watch",
                "primary_scopes": ["election", "campaign"],
                "candidate_linkage": "published_candidate_matches",
                "metric": "daily_retained_candidate_linked_record_count",
            },
        },
        "series": {
            "availability": "observed",
            "unit": "candidate_linked_records_daily",
            "value": selected,
        },
    }


def _wikipedia_evidence(
    candidate: Mapping[str, Any] | None,
    days: Sequence[str],
) -> dict[str, Any]:
    semantics = {
        "availability": "observed",
        "unit": "pageview_scope",
        "value": {
            "project": "fr.wikipedia.org",
            "platform": "all-access",
            "agent": "user",
            "granularity": "daily",
            "metric": "raw_pageviews",
        },
    }
    if candidate is None:
        return {
            "semantics": semantics,
            "series": {
                "availability": "unavailable",
                "unit": "pageviews_daily",
                "reason": "candidate_absent_from_attention_source",
            },
        }
    evidence_state = candidate.get("evidence_state")
    if evidence_state == "unavailable_no_personal_article":
        return {
            "semantics": semantics,
            "series": {
                "availability": "unavailable",
                "unit": "pageviews_daily",
                "reason": evidence_state,
            },
        }
    if evidence_state != "observed":
        raise SignalBraidError("Wikipedia availability has an unsupported state")
    series = _require_list(candidate.get("daily_series"), field="wikipedia.daily_series")
    by_date = {
        row.get("date"): row
        for row in series
        if isinstance(row, Mapping) and isinstance(row.get("date"), str)
    }
    selected: list[dict[str, Any]] = []
    for day in days:
        row = by_date.get(day)
        if row is None:
            raise SignalBraidError(f"Wikipedia continuity is broken at {day}")
        views = _require_nonnegative_int(row.get("views"), field=f"wikipedia[{day}].views")
        selected.append(
            {
                "date": day,
                "views": {
                    "availability": "observed",
                    "unit": "pageviews",
                    "value": views,
                },
            }
        )
    return {
        "semantics": semantics,
        "series": {
            "availability": "observed",
            "unit": "pageviews_daily",
            "value": selected,
        },
    }


def _agenda_evidence(candidate: Mapping[str, Any], days: Sequence[str]) -> dict[str, Any]:
    tracking_start = _parse_date(
        candidate.get("tracking_start"), field="agenda.tracking_start"
    )
    series = _require_list(candidate.get("daily_series"), field="agenda.daily_series")
    by_date = {
        row.get("date"): row
        for row in series
        if isinstance(row, Mapping) and isinstance(row.get("date"), str)
    }
    selected: list[dict[str, Any]] = []
    for day_string in days:
        day = _parse_date(day_string, field="agenda selected date")
        if day < tracking_start:
            selected.append(
                {
                    "date": day_string,
                    "availability": "not_observed",
                    "reason": "date_precedes_tracking_start",
                }
            )
            continue
        row = by_date.get(day_string)
        if row is None:
            raise SignalBraidError(f"agenda continuity is broken at {day_string}")
        policy_counts = _require_mapping(
            row.get("policy_counts"), field=f"agenda[{day_string}].policy_counts"
        )
        campaign_counts = _require_mapping(
            row.get("campaign_counts"), field=f"agenda[{day_string}].campaign_counts"
        )
        selected.append(
            {
                "date": day_string,
                "availability": "observed",
                "value": {
                    "policy_counts": [
                        _require_nonnegative_int(
                            policy_counts.get(topic),
                            field=f"agenda[{day_string}].policy_counts.{topic}",
                        )
                        for topic in POLICY_TOPICS
                    ],
                    "campaign_counts": [
                        _require_nonnegative_int(
                            campaign_counts.get(topic),
                            field=f"agenda[{day_string}].campaign_counts.{topic}",
                        )
                        for topic in CAMPAIGN_TOPICS
                    ],
                },
            }
        )
    return {
        "semantics": {
            "availability": "observed",
            "unit": "agenda_taxonomy_contract",
            "value": {
                "schema_version": "1.0",
                "source": "news_wire.json:relevant_news",
                "candidate_linkage": "validated published candidate associations",
                "policy_classification": "existing multi-label classify_policy_agenda semantics",
                "campaign_classification": (
                    "existing single-topic normalize and classify_campaign_agenda semantics"
                ),
                "policy_topic_ids": list(POLICY_TOPICS),
                "campaign_topic_ids": list(CAMPAIGN_TOPICS),
            },
        },
        "tracking_start": tracking_start.isoformat(),
        "days": selected,
    }


def _parse_package_key(value: Any) -> tuple[str, str, str, int | None]:
    if not isinstance(value, str) or not value:
        raise SignalBraidError("poll package_key must be a non-empty JSON string")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SignalBraidError("poll package_key must be valid JSON") from exc
    if not isinstance(decoded, list) or len(decoded) != 4:
        raise SignalBraidError("poll package_key must encode four package fields")
    pollster, fieldwork_start, fieldwork_end, sample_size = decoded
    if not isinstance(pollster, str) or not pollster:
        raise SignalBraidError("poll package_key pollster must be non-empty")
    _parse_date(fieldwork_start, field="poll package_key fieldwork_start")
    _parse_date(fieldwork_end, field="poll package_key fieldwork_end")
    if sample_size is not None:
        _require_nonnegative_int(sample_size, field="poll package_key sample_size")
    return pollster, fieldwork_start, fieldwork_end, sample_size


def _canonical_package_key(
    key: tuple[str, str, str, int | None],
) -> str:
    return json.dumps(list(key), ensure_ascii=False, separators=(",", ":"))


def _pollster_sort_key(value: str) -> tuple[str, str]:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())
    return normalized, unicodedata.normalize("NFC", value).casefold()


def _poll_evidence(
    candidate_signals_payload: Mapping[str, Any],
    *,
    candidate_id: str,
    candidate_name: str,
    window: Mapping[str, str],
) -> dict[str, Any]:
    if candidate_signals_payload.get("schema_version") != "1.5":
        raise SignalBraidError("candidate_signals.json must use schema_version 1.5")
    candidate = _find_candidate(
        candidate_signals_payload,
        candidate_id,
        source="candidate_signals",
        candidate_name=candidate_name,
    )
    assert candidate is not None
    history = _require_mapping(candidate.get("poll_history"), field="poll_history")
    expected_history_fields = {
        "evidence_state",
        "observation_count",
        "period_start",
        "period_end",
        "observations",
    }
    if set(history) != expected_history_fields:
        raise SignalBraidError("poll_history fields do not match production schema 1.5")
    evidence_state = history.get("evidence_state")
    if evidence_state not in {"reported", "not_observed"}:
        raise SignalBraidError("poll_history.evidence_state is invalid")
    observations = _require_list(history.get("observations"), field="poll_history.observations")
    observation_count = _require_nonnegative_int(
        history.get("observation_count"), field="poll_history.observation_count"
    )
    if observation_count != len(observations):
        raise SignalBraidError("poll_history observation_count is inconsistent")
    if (evidence_state == "not_observed") != (observation_count == 0):
        raise SignalBraidError("poll_history evidence_state is inconsistent")
    if observation_count == 0:
        if history.get("period_start") is not None or history.get("period_end") is not None:
            raise SignalBraidError("unobserved poll_history must not declare a period")
    else:
        history_start = _parse_date(
            history.get("period_start"), field="poll_history.period_start"
        )
        history_end = _parse_date(
            history.get("period_end"), field="poll_history.period_end"
        )
        if history_start > history_end:
            raise SignalBraidError("poll_history period dates are reversed")

    start = _parse_date(window.get("start"), field="parent window start")
    end = _parse_date(window.get("end"), field="parent window end")
    packages_by_tuple: dict[
        tuple[str, str, str, int | None], dict[str, Any]
    ] = {}
    observed_starts: list[date] = []
    observed_ends: list[date] = []
    for index, raw_observation in enumerate(observations):
        observation = _require_mapping(
            raw_observation, field=f"poll_history.observations[{index}]"
        )
        semantic_key = _parse_package_key(observation.get("package_key"))
        pollster, fieldwork_start, fieldwork_end, sample_size = semantic_key
        if observation.get("pollster") != pollster:
            raise SignalBraidError("poll package pollster disagrees with package_key")
        if observation.get("fieldwork_start") != fieldwork_start:
            raise SignalBraidError("poll fieldwork_start disagrees with package_key")
        if observation.get("fieldwork_end") != fieldwork_end:
            raise SignalBraidError("poll fieldwork_end disagrees with package_key")
        if observation.get("sample_size") != sample_size:
            raise SignalBraidError("poll sample_size disagrees with package_key")
        start_date = _parse_date(fieldwork_start, field="poll fieldwork_start")
        end_date = _parse_date(fieldwork_end, field="poll fieldwork_end")
        if start_date > end_date:
            raise SignalBraidError("poll fieldwork_start must not follow fieldwork_end")
        observed_starts.append(start_date)
        observed_ends.append(end_date)
        hypothesis_count = _require_nonnegative_int(
            observation.get("hypothesis_count"), field="poll hypothesis_count"
        )
        if hypothesis_count < 1:
            raise SignalBraidError("poll hypothesis_count must be positive")
        package = {
            "package_key": _canonical_package_key(semantic_key),
            "pollster": pollster,
            "fieldwork_start": fieldwork_start,
            "fieldwork_end": fieldwork_end,
            "sample_size": sample_size,
            "hypothesis_count": hypothesis_count,
        }
        previous = packages_by_tuple.get(semantic_key)
        if previous is not None:
            if previous != package:
                raise SignalBraidError(
                    "duplicate semantic poll package has conflicting facts"
                )
            continue
        packages_by_tuple[semantic_key] = package

    if observations:
        assert observed_starts and observed_ends
        if (
            min(observed_starts) != history_start
            or max(observed_ends) != history_end
        ):
            raise SignalBraidError("poll_history period does not match observations")

    selected = [
        package
        for package in packages_by_tuple.values()
        if start <= _parse_date(package["fieldwork_end"], field="poll fieldwork_end") <= end
    ]
    selected.sort(
        key=lambda row: (
            row["fieldwork_end"],
            row["fieldwork_start"],
            _pollster_sort_key(row["pollster"]),
            row["package_key"],
        )
    )
    if not selected:
        return {
            "availability": "not_observed",
            "unit": "first_round_poll_packages",
            "reason": "no_accepted_package_ended_in_window",
        }
    return {
        "availability": "observed",
        "unit": "first_round_poll_packages",
        "value": selected,
    }


def _contained(
    child_window: Mapping[str, Any], parent_window: Mapping[str, str]
) -> bool:
    child_start = _parse_date(child_window.get("start"), field="child window start")
    child_end = _parse_date(child_window.get("end"), field="child window end")
    parent_start = _parse_date(parent_window.get("start"), field="parent window start")
    parent_end = _parse_date(parent_window.get("end"), field="parent window end")
    return parent_start <= child_start <= child_end <= parent_end


def _child_trace(document_or_trace: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = document_or_trace.get("trace")
    if candidate is None:
        candidate = document_or_trace
    return _require_mapping(candidate, field="child trace")


def _validated_coverage_child_reference(
    document_or_trace: Mapping[str, Any],
    *,
    candidate_id: str,
) -> dict[str, Any]:
    trace = _child_trace(document_or_trace)
    try:
        validate_trace(trace)
        validate_coverage_anatomy_evidence(trace.get("evidence"))
    except (ContractError, CoverageAnatomyError) as exc:
        raise SignalBraidError(f"invalid Coverage Anatomy child: {exc}") from exc
    if trace.get("family") != FAMILY or trace.get("detector_id") != COVERAGE_ANATOMY_DETECTOR_ID:
        raise SignalBraidError("Coverage Anatomy child has the wrong family or detector")
    entities = trace.get("primary_entity_ids")
    if not isinstance(entities, list) or len(entities) != 1:
        raise SignalBraidError("Coverage Anatomy child must have exactly one primary entity")
    if entities[0] != candidate_id:
        raise SignalBraidError("Coverage Anatomy child candidate does not match parent")
    window = _require_mapping(trace.get("observation_window"), field="coverage child window")
    evidence = _require_mapping(trace.get("evidence"), field="coverage child evidence")
    expected_window = {
        "start": evidence["prior_period"]["start"],
        "end": evidence["current_period"]["end"],
    }
    if dict(window) != expected_window:
        raise SignalBraidError(
            "Coverage Anatomy child TRACE window disagrees with its complete evidence"
        )
    return {
        "availability": "observed",
        "unit": "child_trace_reference",
        "value": {
            "detector_id": COVERAGE_ANATOMY_DETECTOR_ID,
            "trace_key": trace["trace_key"],
            "observation_window": {
                "start": window["start"],
                "end": window["end"],
            },
        },
    }


def _flash_annotation(
    trace: Mapping[str, Any], classification: str
) -> dict[str, Any]:
    window = _require_mapping(trace.get("observation_window"), field="flash child window")
    return {
        "availability": "observed",
        "unit": "child_trace_reference",
        "value": {
            "detector_id": FLASH_SHIFT_DETECTOR_ID,
            "trace_key": trace["trace_key"],
            "observation_window": {"start": window["start"], "end": window["end"]},
            "classification": classification,
        },
    }


def select_signal_braid(
    media_payload: Mapping[str, Any],
    wikipedia_payload: Mapping[str, Any],
    agenda_payload: Mapping[str, Any],
    candidate_signals_payload: Mapping[str, Any],
    candidate_id: str,
    *,
    controlled_candidates: Sequence[Mapping[str, Any]],
    coverage_child: Mapping[str, Any] | None = None,
    current_utc_date: date | None = None,
) -> SignalBraidSelection:
    """Select one braid without fuzzy matching or alternate-candidate fallback."""

    _require_canonical_candidate_id(candidate_id, field="candidate_id")
    if current_utc_date is None:
        current_utc_date = datetime.now(timezone.utc).date()
    if type(current_utc_date) is not date:
        raise SignalBraidError("current_utc_date must be a UTC calendar date")
    expected_candidates, candidate_names = _canonical_candidates(controlled_candidates)
    if candidate_id not in candidate_names:
        raise SignalBraidError(f"unknown canonical candidate id: {candidate_id}")
    candidate_name = candidate_names[candidate_id]
    _validate_source_contracts(
        media_payload,
        wikipedia_payload,
        agenda_payload,
        expected_candidates,
    )

    media_candidate = _find_candidate(
        media_payload,
        candidate_id,
        source="candidate_visibility_history",
        candidate_name=candidate_name,
    )
    agenda_candidate = _find_candidate(
        agenda_payload,
        candidate_id,
        source="candidate_agenda_history",
        candidate_name=candidate_name,
    )
    wikipedia_candidate = _find_candidate(
        wikipedia_payload,
        candidate_id,
        source="candidate_attention",
        candidate_name=candidate_name,
        missing_ok=True,
    )
    assert media_candidate is not None and agenda_candidate is not None

    common = _common_window(
        media_payload,
        wikipedia_payload,
        agenda_payload,
        current_utc_date=current_utc_date,
    )
    if common is None:
        return SignalBraidSelection(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            status="suppressed",
            suppression_reason=SUPPRESSION_NO_COMMON_WINDOW,
            observation_window=None,
            evidence=None,
            flash_status="unselected",
            flash_classification=None,
            coverage_status="unselected",
        )
    observation_window, days = common

    media = _media_evidence(media_candidate, days)
    wikipedia = _wikipedia_evidence(wikipedia_candidate, days)
    agenda = _agenda_evidence(agenda_candidate, days)
    poll_tests = _poll_evidence(
        candidate_signals_payload,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        window=observation_window,
    )

    annotations: dict[str, Any] = {}
    flash_status = "unavailable" if wikipedia_candidate is None else "suppressed"
    flash_classification: str | None = None
    if wikipedia_candidate is not None:
        try:
            flash = select_flash_shift(wikipedia_payload, candidate_id)
        except FlashShiftError as exc:
            raise SignalBraidError(f"invalid Flash/Shift component evidence: {exc}") from exc
        if flash.eligible:
            flash_trace = flash.build_trace()
            if flash_trace is None:
                raise SignalBraidError("eligible Flash/Shift component produced no trace")
            if _contained(flash_trace["observation_window"], observation_window):
                classification = flash.interpretation_flag
                if classification not in FLASH_FINDINGS:
                    raise SignalBraidError("Flash/Shift classification is not renderable")
                annotations["flash_shift"] = _flash_annotation(
                    flash_trace, classification
                )
                flash_status = "eligible"
                flash_classification = classification
            else:
                flash_status = "incompatible"
        else:
            flash_status = "suppressed"

    coverage_status = "unselected"
    if coverage_child is not None:
        coverage_reference = _validated_coverage_child_reference(
            coverage_child,
            candidate_id=candidate_id,
        )
        coverage_window = coverage_reference["value"]["observation_window"]
        if _contained(coverage_window, observation_window):
            annotations["coverage_anatomy"] = coverage_reference
            coverage_status = "compatible"
        else:
            coverage_status = "incompatible"

    evidence: dict[str, Any] = {
        "calendar": {
            "availability": "observed",
            "unit": "utc_calendar",
            "value": {
                "timezone": "UTC",
                "start": observation_window["start"],
                "end": observation_window["end"],
                "days": WINDOW_DAYS,
                "inclusive": True,
                "current_utc_day_excluded": True,
            },
        },
        "media": media,
        "wikipedia": wikipedia,
        "agenda": agenda,
        "poll_tests": poll_tests,
        "annotations": annotations,
    }
    validate_signal_braid_evidence(
        evidence,
        observation_window=observation_window,
        candidate_id=candidate_id,
    )

    longitudinal_count = 1
    if wikipedia["series"]["availability"] == "observed":
        longitudinal_count += 1
    if all(row["availability"] == "observed" for row in agenda["days"]):
        longitudinal_count += 1
    if longitudinal_count < 2:
        return SignalBraidSelection(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            status="suppressed",
            suppression_reason=SUPPRESSION_INSUFFICIENT_COVERAGE,
            observation_window=observation_window,
            evidence=evidence,
            flash_status=flash_status,
            flash_classification=flash_classification,
            coverage_status=coverage_status,
        )

    has_poll_trigger = poll_tests["availability"] == "observed"
    has_flash_trigger = "flash_shift" in annotations
    if not has_poll_trigger and not has_flash_trigger:
        return SignalBraidSelection(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            status="suppressed",
            suppression_reason=SUPPRESSION_NO_QUALIFYING_SIGNAL,
            observation_window=observation_window,
            evidence=evidence,
            flash_status=flash_status,
            flash_classification=flash_classification,
            coverage_status=coverage_status,
        )

    return SignalBraidSelection(
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        status="eligible",
        suppression_reason=None,
        observation_window=observation_window,
        evidence=evidence,
        flash_status=flash_status,
        flash_classification=flash_classification,
        coverage_status=coverage_status,
    )


def _validate_child_reference(
    record: Any,
    *,
    field: str,
    detector_id: str,
    parent_window: Mapping[str, str],
    classification_required: bool,
) -> None:
    obj = _validate_availability_record(record, field=field, allowed={"observed"})
    if obj.get("unit") != "child_trace_reference":
        raise SignalBraidError(f"{field}.unit is invalid")
    value = _require_mapping(obj.get("value"), field=f"{field}.value")
    expected = {"detector_id", "trace_key", "observation_window"}
    if classification_required:
        expected.add("classification")
    if set(value) != expected:
        raise SignalBraidError(f"{field}.value fields are not minimal and exact")
    if value.get("detector_id") != detector_id:
        raise SignalBraidError(f"{field} detector_id is invalid")
    if not isinstance(value.get("trace_key"), str) or not _TRACE_KEY_RE.fullmatch(
        value["trace_key"]
    ):
        raise SignalBraidError(f"{field} trace_key is invalid")
    window = _require_mapping(value.get("observation_window"), field=f"{field}.window")
    if set(window) != {"start", "end"} or not _contained(window, parent_window):
        raise SignalBraidError(f"{field} window is not contained by parent")
    if classification_required and value.get("classification") not in FLASH_FINDINGS:
        raise SignalBraidError(f"{field} classification is invalid")


def validate_signal_braid_evidence(
    evidence: Any,
    *,
    observation_window: Mapping[str, str] | None = None,
    candidate_id: str | None = None,
) -> None:
    """Validate the narrow identity-bound Task 05 evidence slice."""

    del candidate_id  # Candidate identity is bound by the enclosing Task 01 TRACE.
    obj = _require_mapping(evidence, field="evidence")
    if set(obj) != {"calendar", "media", "wikipedia", "agenda", "poll_tests", "annotations"}:
        raise SignalBraidError("signal_braid evidence fields are not exact")
    calendar = _validate_availability_record(
        obj["calendar"], field="calendar", allowed={"observed"}
    )
    if calendar.get("unit") != "utc_calendar":
        raise SignalBraidError("calendar.unit must be utc_calendar")
    calendar_value = _require_mapping(calendar.get("value"), field="calendar.value")
    expected_calendar = {
        "timezone",
        "start",
        "end",
        "days",
        "inclusive",
        "current_utc_day_excluded",
    }
    if set(calendar_value) != expected_calendar:
        raise SignalBraidError("calendar fields are not exact")
    if (
        calendar_value.get("timezone") != "UTC"
        or calendar_value.get("days") != WINDOW_DAYS
        or calendar_value.get("inclusive") is not True
        or calendar_value.get("current_utc_day_excluded") is not True
    ):
        raise SignalBraidError("calendar semantics are invalid")
    start = _parse_date(calendar_value.get("start"), field="calendar.start")
    end = _parse_date(calendar_value.get("end"), field="calendar.end")
    if (end - start).days != WINDOW_DAYS - 1:
        raise SignalBraidError("calendar must be exactly 28 closed days")
    parent_window = {"start": start.isoformat(), "end": end.isoformat()}
    if observation_window is not None and dict(observation_window) != parent_window:
        raise SignalBraidError("calendar disagrees with TRACE observation_window")
    days = _date_strings(start, end)

    media = _require_mapping(obj["media"], field="media")
    if set(media) != {"semantics", "series"}:
        raise SignalBraidError("media fields are not exact")
    media_semantics = _validate_availability_record(
        media["semantics"], field="media.semantics", allowed={"observed"}
    )
    if media_semantics.get("unit") != "media_scope":
        raise SignalBraidError("media semantics unit is invalid")
    media_scope = _require_mapping(media_semantics.get("value"), field="media.scope")
    if media_scope != {
        "source": "news_wire.json:candidate_watch",
        "primary_scopes": ["election", "campaign"],
        "candidate_linkage": "published_candidate_matches",
        "metric": "daily_retained_candidate_linked_record_count",
    }:
        raise SignalBraidError("media scope semantics are invalid")
    media_series = _validate_availability_record(
        media["series"], field="media.series", allowed={"observed"}
    )
    if media_series.get("unit") != "candidate_linked_records_daily":
        raise SignalBraidError("media series unit is invalid")
    media_rows = _require_list(media_series.get("value"), field="media.series.value")
    if [row.get("date") if isinstance(row, Mapping) else None for row in media_rows] != days:
        raise SignalBraidError("media series must contain the exact 28 dates")
    for index, row in enumerate(media_rows):
        row_obj = _require_mapping(row, field=f"media[{index}]")
        if set(row_obj) != {"date", "record_count"}:
            raise SignalBraidError("media day fields are not exact")
        count = _validate_availability_record(
            row_obj["record_count"],
            field=f"media[{row_obj['date']}].record_count",
            allowed={"observed"},
        )
        if count.get("unit") != "candidate_linked_records":
            raise SignalBraidError("media record count unit is invalid")
        _require_nonnegative_int(count.get("value"), field="media record_count")

    wikipedia = _require_mapping(obj["wikipedia"], field="wikipedia")
    if set(wikipedia) != {"semantics", "series"}:
        raise SignalBraidError("Wikipedia fields are not exact")
    wiki_semantics = _validate_availability_record(
        wikipedia["semantics"], field="wikipedia.semantics", allowed={"observed"}
    )
    if wiki_semantics.get("unit") != "pageview_scope":
        raise SignalBraidError("Wikipedia semantics unit is invalid")
    if wiki_semantics.get("value") != {
        "project": "fr.wikipedia.org",
        "platform": "all-access",
        "agent": "user",
        "granularity": "daily",
        "metric": "raw_pageviews",
    }:
        raise SignalBraidError("Wikipedia source scope is invalid")
    wiki_series = _validate_availability_record(
        wikipedia["series"],
        field="wikipedia.series",
        allowed={"observed", "unavailable"},
    )
    if wiki_series.get("unit") != "pageviews_daily":
        raise SignalBraidError("Wikipedia series unit is invalid")
    if wiki_series["availability"] == "observed":
        wiki_rows = _require_list(wiki_series.get("value"), field="wikipedia.series.value")
        if [row.get("date") if isinstance(row, Mapping) else None for row in wiki_rows] != days:
            raise SignalBraidError("Wikipedia series must contain the exact 28 dates")
        for row in wiki_rows:
            row_obj = _require_mapping(row, field="Wikipedia day")
            if set(row_obj) != {"date", "views"}:
                raise SignalBraidError("Wikipedia day fields are not exact")
            views = _validate_availability_record(
                row_obj["views"], field="Wikipedia views", allowed={"observed"}
            )
            if views.get("unit") != "pageviews":
                raise SignalBraidError("Wikipedia views unit is invalid")
            _require_nonnegative_int(views.get("value"), field="Wikipedia views")
    elif not isinstance(wiki_series.get("reason"), str) or not wiki_series["reason"]:
        raise SignalBraidError("unavailable Wikipedia requires a reason")

    agenda = _require_mapping(obj["agenda"], field="agenda")
    if set(agenda) != {"semantics", "tracking_start", "days"}:
        raise SignalBraidError("agenda fields are not exact")
    agenda_semantics = _validate_availability_record(
        agenda["semantics"], field="agenda.semantics", allowed={"observed"}
    )
    if agenda_semantics.get("unit") != "agenda_taxonomy_contract":
        raise SignalBraidError("agenda semantics unit is invalid")
    semantic_value = _require_mapping(
        agenda_semantics.get("value"), field="agenda.semantics.value"
    )
    expected_agenda_semantics = {
        "schema_version": "1.0",
        "source": "news_wire.json:relevant_news",
        "candidate_linkage": "validated published candidate associations",
        "policy_classification": "existing multi-label classify_policy_agenda semantics",
        "campaign_classification": (
            "existing single-topic normalize and classify_campaign_agenda semantics"
        ),
        "policy_topic_ids": list(POLICY_TOPICS),
        "campaign_topic_ids": list(CAMPAIGN_TOPICS),
    }
    if semantic_value != expected_agenda_semantics:
        raise SignalBraidError("agenda taxonomy semantics are not exact")
    tracking_start = _parse_date(agenda.get("tracking_start"), field="agenda.tracking_start")
    agenda_rows = _require_list(agenda.get("days"), field="agenda.days")
    if [row.get("date") if isinstance(row, Mapping) else None for row in agenda_rows] != days:
        raise SignalBraidError("agenda must contain the exact 28 dates")
    for row in agenda_rows:
        row_obj = _require_mapping(row, field="agenda day")
        day = _parse_date(row_obj.get("date"), field="agenda day date")
        if day < tracking_start:
            if row_obj != {
                "date": day.isoformat(),
                "availability": "not_observed",
                "reason": "date_precedes_tracking_start",
            }:
                raise SignalBraidError("pre-tracking agenda dates must be not_observed")
            continue
        day_record = _validate_availability_record(
            row_obj, field=f"agenda[{day.isoformat()}]", allowed={"observed"}
        )
        if set(day_record) != {"date", "availability", "value"}:
            raise SignalBraidError("observed agenda day fields are not exact")
        value = _require_mapping(day_record.get("value"), field="agenda day value")
        if set(value) != {"policy_counts", "campaign_counts"}:
            raise SignalBraidError("agenda count groups are not exact")
        policy_counts = _require_list(value["policy_counts"], field="agenda policy_counts")
        campaign_counts = _require_list(
            value["campaign_counts"], field="agenda campaign_counts"
        )
        if len(policy_counts) != len(POLICY_TOPICS) or len(campaign_counts) != len(CAMPAIGN_TOPICS):
            raise SignalBraidError("agenda count arrays must match canonical taxonomies")
        for count in [*policy_counts, *campaign_counts]:
            _require_nonnegative_int(count, field="agenda topic count")

    poll_tests = _validate_availability_record(
        obj["poll_tests"],
        field="poll_tests",
        allowed={"observed", "not_observed"},
    )
    if poll_tests.get("unit") != "first_round_poll_packages":
        raise SignalBraidError("poll_tests unit is invalid")
    if poll_tests["availability"] == "observed":
        packages = _require_list(poll_tests.get("value"), field="poll_tests.value")
        if not packages:
            raise SignalBraidError("observed poll_tests must contain a package")
        seen: set[str] = set()
        expected_package_fields = {
            "package_key",
            "pollster",
            "fieldwork_start",
            "fieldwork_end",
            "sample_size",
            "hypothesis_count",
        }
        previous_package_order: tuple[Any, ...] | None = None
        for package in packages:
            item = _require_mapping(package, field="poll package")
            if set(item) != expected_package_fields:
                raise SignalBraidError("poll package facts are not narrow and exact")
            key = item.get("package_key")
            parsed = _parse_package_key(key)
            if key != _canonical_package_key(parsed):
                raise SignalBraidError("selected poll package_key is not canonical")
            if key in seen:
                raise SignalBraidError("selected poll packages contain a duplicate")
            seen.add(key)
            if tuple(item.get(field) for field in ("pollster", "fieldwork_start", "fieldwork_end", "sample_size")) != parsed:
                raise SignalBraidError("selected poll package disagrees with package_key")
            fieldwork_start = _parse_date(item["fieldwork_start"], field="poll start")
            fieldwork_end = _parse_date(item["fieldwork_end"], field="poll end")
            if fieldwork_start > fieldwork_end or not start <= fieldwork_end <= end:
                raise SignalBraidError("selected poll package interval is invalid")
            if _require_nonnegative_int(item.get("hypothesis_count"), field="hypothesis_count") < 1:
                raise SignalBraidError("hypothesis_count must be positive")
            package_order = (
                item["fieldwork_end"],
                item["fieldwork_start"],
                _pollster_sort_key(item["pollster"]),
                key,
            )
            if previous_package_order is not None and package_order < previous_package_order:
                raise SignalBraidError("selected poll packages are not in canonical order")
            previous_package_order = package_order
    elif not isinstance(poll_tests.get("reason"), str) or not poll_tests["reason"]:
        raise SignalBraidError("not_observed poll_tests requires a reason")

    annotations = _require_mapping(obj["annotations"], field="annotations")
    if not set(annotations).issubset({"flash_shift", "coverage_anatomy"}):
        raise SignalBraidError("annotations contains an unsupported child")
    if "flash_shift" in annotations:
        _validate_child_reference(
            annotations["flash_shift"],
            field="annotations.flash_shift",
            detector_id=FLASH_SHIFT_DETECTOR_ID,
            parent_window=parent_window,
            classification_required=True,
        )
    if "coverage_anatomy" in annotations:
        _validate_child_reference(
            annotations["coverage_anatomy"],
            field="annotations.coverage_anatomy",
            detector_id=COVERAGE_ANATOMY_DETECTOR_ID,
            parent_window=parent_window,
            classification_required=False,
        )


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SignalBraidError(f"unable to read validated source {path.name}: {exc}") from exc
    return _require_mapping(payload, field=path.name)


def _live_controlled_candidates() -> list[dict[str, str]]:
    # Imported only for an explicit live read.  Keeping this production module
    # out of import time also keeps its optional HTTP-library imports outside
    # normal TRACE construction and renderer imports.
    from candidate_candidacy_status import (
        CandidateCandidacyStatusError,
        validate_candidate_candidacy_status,
    )

    payload = _load_json(_CANDIDACY_PATH)
    try:
        validate_candidate_candidacy_status(payload)
    except CandidateCandidacyStatusError as exc:
        raise SignalBraidError(f"malformed controlled candidate source: {exc}") from exc
    candidates = _require_list(payload.get("candidates"), field="candidacy candidates")
    return [
        {
            "id": candidate["candidate_id"],
            "name": candidate["candidate_name"],
        }
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]


def _coverage_compatibility(
    child: Mapping[str, Any] | None,
    *,
    candidate_id: str,
    parent_window: Mapping[str, str] | None,
) -> str:
    if child is None or parent_window is None:
        return "unavailable"
    reference = _validated_coverage_child_reference(
        child,
        candidate_id=candidate_id,
    )
    return (
        "compatible"
        if _contained(reference["value"]["observation_window"], parent_window)
        else "incompatible"
    )


def _is_optional_coverage_absence(
    error: CoverageAnatomyError,
    *,
    candidate_id: str,
) -> bool:
    return str(error) in {
        f"candidate {candidate_id!r} is absent from prior_period",
        f"candidate {candidate_id!r} is absent from current_period",
    }


def extract_live_signal_braid(candidate_id: str) -> SignalBraidSelection:
    """Read fixed repository artifacts and select exactly ``candidate_id``."""

    controlled_candidates = _live_controlled_candidates()
    media_payload = _load_json(_MEDIA_PATH)
    wikipedia_payload = _load_json(_WIKIPEDIA_PATH)
    agenda_payload = _load_json(_AGENDA_PATH)
    candidate_signals_payload = _load_json(_POLL_HISTORY_PATH)
    current_utc_date = datetime.now(timezone.utc).date()
    selection = select_signal_braid(
        media_payload,
        wikipedia_payload,
        agenda_payload,
        candidate_signals_payload,
        candidate_id,
        controlled_candidates=controlled_candidates,
        current_utc_date=current_utc_date,
    )
    coverage_child: Mapping[str, Any] | None = None
    try:
        coverage_selection = extract_live_coverage_anatomy(candidate_id)
        coverage_child = coverage_selection.build_trace()
    except CoverageAnatomyError as exc:
        if not _is_optional_coverage_absence(exc, candidate_id=candidate_id):
            raise SignalBraidError(
                f"invalid optional Coverage Anatomy source: {exc}"
            ) from exc
    coverage_status = _coverage_compatibility(
        coverage_child,
        candidate_id=candidate_id,
        parent_window=selection.observation_window,
    )
    if coverage_status == "compatible" and coverage_child is not None:
        selection = select_signal_braid(
            media_payload,
            wikipedia_payload,
            agenda_payload,
            candidate_signals_payload,
            candidate_id,
            controlled_candidates=controlled_candidates,
            coverage_child=coverage_child,
            current_utc_date=current_utc_date,
        )
    else:
        selection = replace(selection, coverage_status=coverage_status)
    return selection


def build_signal_braid_document(selection: SignalBraidSelection) -> dict[str, Any]:
    """Build the deterministic presentation wrapper for one eligible selection."""

    trace = selection.build_trace()
    if trace is None or selection.observation_window is None or selection.finding is None:
        raise SignalBraidError("suppressed Signal Braid selections cannot be rendered")
    return {
        "trace": trace,
        "presentation": {
            "language": "en",
            "display_label": selection.candidate_name,
            "finding": selection.finding,
            "qualifier": selection.qualifier or None,
            "source_scope": (
                "FR27 CANDIDATE-LINKED NEWS · WIKIPEDIA · FIRST-ROUND POLL PACKAGES"
            ),
            "methodological_boundary": (
                "SEPARATE LANES · NO COMBINED SCALE, SUPPORT MEASURE OR CAUSAL CLAIM"
            ),
            "observation_window_display": signal_braid_window_display(
                selection.observation_window
            ),
            "renderer_version": "trace-shell.v1",
            "field_type": FIELD_TYPE,
        },
    }


def live_smoke_summary(candidate_id: str = "edouard-philippe") -> dict[str, Any]:
    selection = extract_live_signal_braid(candidate_id)
    evidence = selection.evidence
    summary: dict[str, Any] = {
        "candidate_id": selection.candidate_id,
        "common_window": selection.observation_window,
        "status": selection.status,
        "suppression_reason": selection.suppression_reason,
        "flash_shift": {
            "status": selection.flash_status,
            "classification": selection.flash_classification,
        },
        "coverage_anatomy": selection.coverage_status,
        "finding": selection.finding,
    }
    if evidence is None:
        return summary
    media_rows = evidence["media"]["series"]["value"]
    wiki_series = evidence["wikipedia"]["series"]
    agenda_days = evidence["agenda"]["days"]
    poll_tests = evidence["poll_tests"]
    summary.update(
        {
            "lane_availability": {
                "media": evidence["media"]["series"]["availability"],
                "wikipedia": wiki_series["availability"],
                "agenda": (
                    "observed"
                    if all(day["availability"] == "observed" for day in agenda_days)
                    else "partially_not_observed"
                ),
                "poll_tests": poll_tests["availability"],
            },
            "media_28_day_total": sum(
                row["record_count"]["value"] for row in media_rows
            ),
            "wikipedia_28_day_total": (
                sum(row["views"]["value"] for row in wiki_series["value"])
                if wiki_series["availability"] == "observed"
                else None
            ),
            "agenda_observed_day_count": sum(
                1 for day in agenda_days if day["availability"] == "observed"
            ),
            "poll_package_count": len(poll_tests.get("value", [])),
        }
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Task 05 live smoke")
    parser.add_argument("--candidate-id", default="edouard-philippe")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            live_smoke_summary(args.candidate_id),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
