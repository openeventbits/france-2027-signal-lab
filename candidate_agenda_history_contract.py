"""Contract for persistent Candidate Agenda History publications."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from fetch_news_wire import CAMPAIGN_AGENDA_TOPICS, POLICY_AGENDA_TOPICS


SCHEMA_VERSION = "1.0"
TRACKING_START = "2026-08-20"
DAY_BOUNDARY = "UTC"
POLICY_MIN_NONZERO_TOPICS = 3

POLICY_TAXONOMY = tuple(
    (topic["id"], topic["label"]) for topic in POLICY_AGENDA_TOPICS
)
CAMPAIGN_TAXONOMY = tuple(
    (topic["id"], topic["label"]) for topic in CAMPAIGN_AGENDA_TOPICS
)

METHODOLOGY = {
    "source": "news_wire.json:relevant_news",
    "candidate_linkage": "validated published candidate associations",
    "policy_classification": (
        "existing multi-label classify_policy_agenda semantics"
    ),
    "campaign_classification": (
        "existing single-topic normalize and classify_campaign_agenda semantics"
    ),
    "cumulative_profile": (
        "policy when at least 3 policy topics have non-zero counts; otherwise campaign"
    ),
    "measurement": (
        "descriptive unweighted candidate-topic association counts since tracking"
    ),
}


class CandidateAgendaHistoryContractError(ValueError):
    """Raised when Candidate Agenda History violates its public contract."""


def _keys(value: Any, expected: set[str], *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise CandidateAgendaHistoryContractError(
            f"{field} must contain exactly {sorted(expected)}"
        )
    return value


def _date(value: Any, *, field: str) -> date:
    if not isinstance(value, str):
        raise CandidateAgendaHistoryContractError(
            f"{field} must be an ISO calendar date"
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CandidateAgendaHistoryContractError(
            f"{field} must be an ISO calendar date"
        ) from error
    if parsed.isoformat() != value:
        raise CandidateAgendaHistoryContractError(
            f"{field} must be a canonical ISO calendar date"
        )
    return parsed


def _count(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise CandidateAgendaHistoryContractError(
            f"{field} must be a non-negative integer"
        )
    return value


def _taxonomy(
    value: Any,
    expected: tuple[tuple[str, str], ...],
    *,
    field: str,
) -> None:
    if not isinstance(value, list) or len(value) != len(expected):
        raise CandidateAgendaHistoryContractError(
            f"{field} must contain the canonical taxonomy"
        )
    actual: list[tuple[str, str]] = []
    for index, row in enumerate(value):
        row = _keys(row, {"id", "label"}, field=f"{field}[{index}]")
        if not all(isinstance(row[key], str) and row[key] for key in row):
            raise CandidateAgendaHistoryContractError(
                f"{field}[{index}] id and label must be non-empty strings"
            )
        actual.append((row["id"], row["label"]))
    if tuple(actual) != expected:
        raise CandidateAgendaHistoryContractError(
            f"{field} must exactly match the canonical definitions and order"
        )


def _counts(
    value: Any,
    taxonomy: tuple[tuple[str, str], ...],
    *,
    field: str,
) -> dict[str, int]:
    expected_ids = [topic_id for topic_id, _label in taxonomy]
    if not isinstance(value, dict) or list(value) != expected_ids:
        raise CandidateAgendaHistoryContractError(
            f"{field} must contain every canonical topic in canonical order"
        )
    return {
        topic_id: _count(value[topic_id], field=f"{field}.{topic_id}")
        for topic_id in expected_ids
    }


def _expected_candidate_pairs(expected_candidates: Any) -> list[tuple[str, str]]:
    if not isinstance(expected_candidates, list):
        raise CandidateAgendaHistoryContractError(
            "expected_candidates must be an array"
        )
    result: list[tuple[str, str]] = []
    for index, candidate in enumerate(expected_candidates):
        if not isinstance(candidate, dict):
            raise CandidateAgendaHistoryContractError(
                f"expected_candidates[{index}] must be an object"
            )
        candidate_id = candidate.get("candidate_id")
        candidate_name = candidate.get("candidate_name")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise CandidateAgendaHistoryContractError(
                f"expected_candidates[{index}].candidate_id is invalid"
            )
        if not isinstance(candidate_name, str) or not candidate_name:
            raise CandidateAgendaHistoryContractError(
                f"expected_candidates[{index}].candidate_name is invalid"
            )
        result.append((candidate_id, candidate_name))
    return result


def validate_candidate_agenda_history(
    payload: Any,
    *,
    expected_candidates: list[dict[str, Any]] | None = None,
) -> None:
    """Validate intrinsic history and optional current-registry parity."""

    payload = _keys(
        payload,
        {"schema_version", "tracking", "methodology", "taxonomies", "candidates"},
        field="candidate_agenda_history",
    )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise CandidateAgendaHistoryContractError(
            f"schema_version must equal {SCHEMA_VERSION}"
        )

    tracking = _keys(
        payload["tracking"],
        {"start_date", "data_as_of", "day_boundary", "current_utc_day_excluded"},
        field="tracking",
    )
    if tracking["start_date"] != TRACKING_START:
        raise CandidateAgendaHistoryContractError(
            f"tracking.start_date must equal {TRACKING_START}"
        )
    tracking_start = _date(tracking["start_date"], field="tracking.start_date")
    data_as_of = _date(tracking["data_as_of"], field="tracking.data_as_of")
    if data_as_of < tracking_start:
        raise CandidateAgendaHistoryContractError(
            "tracking.data_as_of must not predate tracking.start_date"
        )
    if tracking["day_boundary"] != DAY_BOUNDARY:
        raise CandidateAgendaHistoryContractError(
            f"tracking.day_boundary must equal {DAY_BOUNDARY}"
        )
    if tracking["current_utc_day_excluded"] is not True:
        raise CandidateAgendaHistoryContractError(
            "tracking.current_utc_day_excluded must be true"
        )
    if payload["methodology"] != METHODOLOGY:
        raise CandidateAgendaHistoryContractError(
            "methodology must match the locked descriptive contract"
        )

    taxonomies = _keys(
        payload["taxonomies"], {"policy", "campaign"}, field="taxonomies"
    )
    _taxonomy(taxonomies["policy"], POLICY_TAXONOMY, field="taxonomies.policy")
    _taxonomy(
        taxonomies["campaign"], CAMPAIGN_TAXONOMY, field="taxonomies.campaign"
    )

    candidates = payload["candidates"]
    if not isinstance(candidates, list):
        raise CandidateAgendaHistoryContractError("candidates must be an array")
    identities: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        prefix = f"candidates[{index}]"
        candidate = _keys(
            candidate,
            {
                "candidate_id",
                "candidate_name",
                "tracking_start",
                "daily_series",
                "cumulative_profile",
            },
            field=prefix,
        )
        candidate_id = candidate["candidate_id"]
        candidate_name = candidate["candidate_name"]
        if not isinstance(candidate_id, str) or not candidate_id:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.candidate_id must be a non-empty string"
            )
        if not isinstance(candidate_name, str) or not candidate_name:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.candidate_name must be a non-empty string"
            )
        if candidate_id in seen_ids:
            raise CandidateAgendaHistoryContractError(
                f"duplicate candidate_id: {candidate_id}"
            )
        seen_ids.add(candidate_id)
        identities.append((candidate_id, candidate_name))

        candidate_start = _date(
            candidate["tracking_start"], field=f"{prefix}.tracking_start"
        )
        if candidate_start < tracking_start or candidate_start > data_as_of:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.tracking_start is outside the published period"
            )
        series = candidate["daily_series"]
        if not isinstance(series, list):
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.daily_series must be an array"
            )
        expected_days = (data_as_of - candidate_start).days + 1
        if len(series) != expected_days:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.daily_series must be contiguous through data_as_of"
            )
        policy_totals = {topic_id: 0 for topic_id, _label in POLICY_TAXONOMY}
        campaign_totals = {topic_id: 0 for topic_id, _label in CAMPAIGN_TAXONOMY}
        for day_index, day_row in enumerate(series):
            day_prefix = f"{prefix}.daily_series[{day_index}]"
            day_row = _keys(
                day_row,
                {"date", "policy_counts", "campaign_counts"},
                field=day_prefix,
            )
            expected_date = candidate_start + timedelta(days=day_index)
            actual_date = _date(day_row["date"], field=f"{day_prefix}.date")
            if actual_date != expected_date:
                raise CandidateAgendaHistoryContractError(
                    f"{prefix}.daily_series dates must be unique, ascending, and contiguous"
                )
            policy_counts = _counts(
                day_row["policy_counts"],
                POLICY_TAXONOMY,
                field=f"{day_prefix}.policy_counts",
            )
            campaign_counts = _counts(
                day_row["campaign_counts"],
                CAMPAIGN_TAXONOMY,
                field=f"{day_prefix}.campaign_counts",
            )
            for topic_id, count in policy_counts.items():
                policy_totals[topic_id] += count
            for topic_id, count in campaign_counts.items():
                campaign_totals[topic_id] += count

        profile = _keys(
            candidate["cumulative_profile"],
            {
                "profile_mode",
                "period_start",
                "period_end",
                "day_count",
                "association_count",
                "topics",
            },
            field=f"{prefix}.cumulative_profile",
        )
        expected_mode = (
            "policy"
            if sum(count > 0 for count in policy_totals.values())
            >= POLICY_MIN_NONZERO_TOPICS
            else "campaign"
        )
        if profile["profile_mode"] != expected_mode:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.cumulative_profile.profile_mode violates the selection rule"
            )
        if profile["period_start"] != candidate["tracking_start"]:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.cumulative_profile.period_start must equal tracking_start"
            )
        if profile["period_end"] != tracking["data_as_of"]:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.cumulative_profile.period_end must equal data_as_of"
            )
        if _count(profile["day_count"], field=f"{prefix}.cumulative_profile.day_count") != expected_days:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.cumulative_profile.day_count does not reconcile"
            )
        taxonomy = POLICY_TAXONOMY if expected_mode == "policy" else CAMPAIGN_TAXONOMY
        totals = policy_totals if expected_mode == "policy" else campaign_totals
        association_count = sum(totals.values())
        if _count(
            profile["association_count"],
            field=f"{prefix}.cumulative_profile.association_count",
        ) != association_count:
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.cumulative_profile.association_count does not reconcile"
            )
        topics = profile["topics"]
        if not isinstance(topics, list) or len(topics) != len(taxonomy):
            raise CandidateAgendaHistoryContractError(
                f"{prefix}.cumulative_profile.topics must contain the selected taxonomy"
            )
        for topic_index, ((topic_id, label), topic) in enumerate(zip(taxonomy, topics)):
            topic_prefix = f"{prefix}.cumulative_profile.topics[{topic_index}]"
            topic = _keys(topic, {"id", "label", "count", "share"}, field=topic_prefix)
            expected_share = (
                round(totals[topic_id] / association_count, 6)
                if association_count
                else 0.0
            )
            if (
                topic["id"] != topic_id
                or topic["label"] != label
                or _count(topic["count"], field=f"{topic_prefix}.count")
                != totals[topic_id]
                or type(topic["share"]) is not float
                or topic["share"] != expected_share
            ):
                raise CandidateAgendaHistoryContractError(
                    f"{topic_prefix} does not reconcile with the selected taxonomy"
                )

    if expected_candidates is not None:
        expected_pairs = _expected_candidate_pairs(expected_candidates)
        if identities != expected_pairs:
            raise CandidateAgendaHistoryContractError(
                "candidates must exactly match the current registry identities and order"
            )


def serialize_candidate_agenda_history(payload: dict[str, Any]) -> bytes:
    """Return deterministic public JSON bytes after intrinsic validation."""

    validate_candidate_agenda_history(payload)
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
