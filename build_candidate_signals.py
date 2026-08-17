"""Build the deterministic Candidate Signals public payload.

This module is network-free and depends only on the Python standard library
and the narrow candidate identity and candidacy-status helpers.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import tempfile
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    candidacy_status_by_id,
    project_active_monitoring_field,
    project_display_tiers,
    validate_candidate_candidacy_status,
)
from candidate_identity import (
    CandidateIdentityError,
    candidate_id,
    candidate_identity_map,
    canonical_candidate_name,
    normalized_candidate_key,
    resolve_candidate_name,
)


SCHEMA_VERSION = "1.3"
LATEST_SCRUTINY_DAYS = 14
FEATURED_POLL_BOARD_DISPLAY_LIMIT = 10
FEATURED_POLL_BOARD_SELECTION_BASIS = (
    "featured_package_selected_hypothesis"
)
CANDIDATE_UNIVERSE_SOURCE = "candidate_candidacy_status.json"
CANDIDATE_UNIVERSE_RULE = (
    "Complete controlled candidacy registry: main, secondary, and hidden"
)
PRIMARY_SCOPES = ("election", "campaign")
GENERAL_SCOPE = "general"
VISIBILITY_SCOPES = (*PRIMARY_SCOPES, GENERAL_SCOPE)
ACTIVE_FIELD_VISIBILITY_METHOD = (
    "share_of_active_candidate_linked_records"
)
ACTIVE_FIELD_DENOMINATOR_SCOPE = (
    "records_linked_to_at_least_one_active_monitoring_candidate"
)
ACTIVE_VISIBILITY_THRESHOLDS = {
    "minimum_period_records": 10,
    "minimum_period_publishers": 5,
    "minimum_common_publishers": 5,
    "minimum_publisher_overlap_ratio": 0.5,
    "maximum_record_count_ratio": 2.0,
}


FORBIDDEN_FIELD_PARTS = {
    "average",
    "causal",
    "combined_score",
    "delta",
    "endorsement",
    "forecast",
    "momentum",
    "probability",
    "sentiment",
    "trend",
    "viability",
}
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
CANDIDACY_OUTPUT_KEYS = {
    "status",
    "display_tier",
    "upstream_presence",
    "active_field_eligible",
    "status_as_of",
    "source_date",
    "source_url",
    "source_title",
    "source_publisher",
    "status_note",
}
PRESIDENTIAL_FIELD_KEYS = {
    "status_as_of",
    "main",
    "secondary",
    "hidden",
    "counts",
}
PRESIDENTIAL_FIELD_COUNT_KEYS = {
    "main",
    "secondary",
    "hidden",
    "total",
}
ACTIVE_MONITORING_FIELD_KEYS = {"main", "secondary", "counts"}
ACTIVE_MONITORING_FIELD_COUNT_KEYS = {"main", "secondary", "active"}


class CandidateSignalsError(ValueError):
    """Raised when source data or a Candidate Signals payload is invalid."""


def _error_from_identity(error: CandidateIdentityError) -> CandidateSignalsError:
    return CandidateSignalsError(str(error))


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CandidateSignalsError(f"{field} must be an object")
    return value


def _require_plain_object(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CandidateSignalsError(f"{field} must be a plain object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise CandidateSignalsError(f"{field} must be an array")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateSignalsError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise CandidateSignalsError(f"{field} must not have outer whitespace")
    return value


def _require_non_negative_integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise CandidateSignalsError(f"{field} must be a non-negative integer")
    return value


def _require_positive_integer(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise CandidateSignalsError(f"{field} must be a positive integer")
    return value


def _numeric(value: Any, field: str, *, non_negative: bool = False) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise CandidateSignalsError(f"{field} must be a finite number")
    if non_negative and value < 0:
        raise CandidateSignalsError(f"{field} must be non-negative")
    return value


def _ratio(value: Any, field: str) -> int | float:
    numeric = _numeric(value, field, non_negative=True)
    if numeric > 1:
        raise CandidateSignalsError(f"{field} must be between zero and one")
    return numeric


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        raise CandidateSignalsError(f"{field} must be an ISO calendar date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CandidateSignalsError(
            f"{field} must be an ISO calendar date"
        ) from error
    if parsed.isoformat() != value:
        raise CandidateSignalsError(f"{field} must be an ISO calendar date")
    return parsed


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CandidateSignalsError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidateSignalsError(
            f"{field} must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise CandidateSignalsError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _timestamp_date(value: Any, field: str) -> date:
    return _parse_timestamp(value, field).date()


def _usable_url(value: Any) -> bool:
    if not isinstance(value, str) or value != value.strip() or not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_json(path: Path | str) -> Any:
    """Load one required JSON source with safe, path-specific errors."""

    source_path = Path(path)
    try:
        content = source_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise CandidateSignalsError(
            f"required source file is missing: {source_path}"
        ) from error
    except OSError as error:
        raise CandidateSignalsError(
            f"could not read required source file {source_path}: {error}"
        ) from error
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise CandidateSignalsError(
            f"malformed JSON in {source_path}: "
            f"line {error.lineno}, column {error.colno}"
        ) from error


def load_inputs(
    polls_path: Path | str,
    news_path: Path | str,
    claims_path: Path | str,
    candidacy_status_path: Path | str,
) -> tuple[list[Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load and minimally type-check the four required source payloads."""

    polls = load_json(polls_path)
    news = load_json(news_path)
    claims = load_json(claims_path)
    candidacy_status = load_json(candidacy_status_path)
    if not isinstance(polls, list):
        raise CandidateSignalsError("polls source must be a top-level array")
    if not isinstance(news, dict):
        raise CandidateSignalsError("news source must be a top-level object")
    if not isinstance(claims, dict):
        raise CandidateSignalsError("claims source must be a top-level object")
    if not isinstance(candidacy_status, dict):
        raise CandidateSignalsError(
            "candidacy-status source must be a top-level object"
        )
    return polls, news, claims, candidacy_status


def _poll_qualifying_date(event: dict[str, Any], context: str) -> date:
    """Return the event date used by existing poll package validation."""

    publication = event.get("publication_date")
    if publication not in (None, ""):
        return _parse_date(publication, f"{context}.publication_date")
    return _parse_date(event.get("fieldwork_end"), f"{context}.fieldwork_end")


def _validate_first_round_event(
    event: Any,
    index: int,
) -> dict[str, Any]:
    context = f"polls[{index}]"
    value = _require_object(event, context)
    if value.get("round") != "first_round":
        raise CandidateSignalsError(f"{context}.round must equal first_round")

    _require_text(value.get("event_id"), f"{context}.event_id")
    _require_text(value.get("scenario_key"), f"{context}.scenario_key")
    _require_text(value.get("pollster"), f"{context}.pollster")
    fieldwork_start = _parse_date(
        value.get("fieldwork_start"),
        f"{context}.fieldwork_start",
    )
    fieldwork_end = _parse_date(
        value.get("fieldwork_end"),
        f"{context}.fieldwork_end",
    )
    if fieldwork_start > fieldwork_end:
        raise CandidateSignalsError(
            f"{context} has fieldwork_start after fieldwork_end"
        )
    _poll_qualifying_date(value, context)

    sample_size = value.get("sample_size")
    if sample_size is not None:
        _require_non_negative_integer(sample_size, f"{context}.sample_size")

    source_url = value.get("source_url")
    if not _usable_url(source_url):
        raise CandidateSignalsError(f"{context}.source_url is invalid")
    official_source_url = value.get("official_source_url")
    if official_source_url not in (None, "") and not _usable_url(
        official_source_url
    ):
        raise CandidateSignalsError(
            f"{context}.official_source_url is invalid"
        )

    candidates = _require_list(value.get("candidates"), f"{context}.candidates")
    if len(candidates) < 2:
        raise CandidateSignalsError(
            f"{context}.candidates must contain at least two candidates"
        )

    seen_names: set[str] = set()
    reported_total = 0.0
    for candidate_index, candidate_value in enumerate(candidates):
        candidate_context = f"{context}.candidates[{candidate_index}]"
        candidate = _require_object(candidate_value, candidate_context)
        try:
            name = canonical_candidate_name(candidate.get("name"))
            key = normalized_candidate_key(name)
        except CandidateIdentityError as error:
            raise _error_from_identity(error) from error
        if candidate.get("name") != name:
            raise CandidateSignalsError(
                f"{candidate_context}.name is not canonical whitespace"
            )
        if key in seen_names:
            raise CandidateSignalsError(
                f"{context} contains a duplicate candidate identity"
            )
        seen_names.add(key)
        score = _numeric(
            candidate.get("score"),
            f"{candidate_context}.score",
            non_negative=True,
        )
        reported_total += float(score)

    declared_total = _numeric(
        value.get("reported_total"),
        f"{context}.reported_total",
        non_negative=True,
    )
    if not math.isclose(
        float(declared_total),
        reported_total,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise CandidateSignalsError(
            f"{context}.reported_total does not match candidate scores"
        )

    completeness_status = value.get("completeness_status")
    partial_scenario = value.get("partial_scenario")
    unreported_share = value.get("unreported_share")
    if completeness_status == "complete":
        if (
            partial_scenario is not False
            or not 99 <= reported_total <= 101
            or unreported_share is not None
        ):
            raise CandidateSignalsError(
                f"{context} has inconsistent complete-scenario metadata"
            )
    elif completeness_status == "partial":
        expected_unreported = 100 - reported_total
        if (
            partial_scenario is not True
            or not 0 < reported_total < 99
            or isinstance(unreported_share, bool)
            or not isinstance(unreported_share, (int, float))
            or not math.isfinite(float(unreported_share))
            or not math.isclose(
                float(unreported_share),
                expected_unreported,
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            raise CandidateSignalsError(
                f"{context} has inconsistent partial-scenario metadata"
            )
    else:
        raise CandidateSignalsError(
            f"{context}.completeness_status is invalid"
        )

    return value


def validated_first_round_events(
    polls: Any,
) -> list[tuple[int, dict[str, Any]]]:
    """Return valid first-round events with their original input indexes."""

    values = _require_list(polls, "polls")
    events: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(values):
        if not isinstance(event, dict):
            raise CandidateSignalsError(f"polls[{index}] must be an object")
        round_name = event.get("round")
        if round_name == "second_round":
            continue
        if round_name != "first_round":
            raise CandidateSignalsError(f"polls[{index}].round is invalid")
        events.append((index, _validate_first_round_event(event, index)))
    if not events:
        raise CandidateSignalsError("polls contains no valid first-round events")
    return events


def candidate_universe_from_candidacy_status(
    candidacy_status: Any,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Project the complete canonical universe from the candidacy registry."""

    try:
        validate_candidate_candidacy_status(candidacy_status)
    except CandidateCandidacyStatusError as error:
        raise CandidateSignalsError(
            f"candidacy-status registry is invalid: {error}"
        ) from error
    candidates = [
        {
            "candidate_id": candidate["candidate_id"],
            "candidate_name": candidate["candidate_name"],
        }
        for candidate in candidacy_status["candidates"]
    ]
    metadata = {
        "source": CANDIDATE_UNIVERSE_SOURCE,
        "rule": CANDIDATE_UNIVERSE_RULE,
        "status_as_of": candidacy_status["status_as_of"],
        "count": len(candidates),
    }
    return metadata, candidates


def _package_key(event: dict[str, Any]) -> tuple[str, str, str, int | None]:
    return (
        event["pollster"],
        event["fieldwork_start"],
        event["fieldwork_end"],
        event.get("sample_size"),
    )


def _serialized_package_key(
    key: tuple[str, str, str, int | None],
) -> str:
    return json.dumps(
        list(key),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _event_candidate_score(
    event: dict[str, Any],
    candidate_name: str,
) -> int | float | None:
    for candidate in event["candidates"]:
        if candidate["name"] == candidate_name:
            return candidate["score"]
    return None


def _normalize_comparable_text(value: Any) -> str:
    """Match the frontend's NFKC, whitespace, and French lowercase handling."""

    return " ".join(unicodedata.normalize("NFKC", str(value)).split()).lower()


def _comparable_candidate_count(
    event: dict[str, Any],
    events: list[dict[str, Any]],
) -> int:
    pollster_key = _normalize_comparable_text(event["pollster"])
    count = 0
    for candidate in event["candidates"]:
        candidate_name = candidate["name"]
        has_prior = any(
            previous["round"] == event["round"]
            and previous["scenario_key"] == event["scenario_key"]
            and previous["fieldwork_end"] < event["fieldwork_end"]
            and _normalize_comparable_text(previous["pollster"]) == pollster_key
            and _event_candidate_score(previous, candidate_name) is not None
            for previous in events
        )
        if has_prior:
            count += 1
    return count


def french_compatible_sort_key(value: str) -> tuple[str, str]:
    """Return deterministic accent-insensitive ordering compatible with French."""

    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).casefold()
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())
    return normalized, unicodedata.normalize("NFC", value).casefold()


def build_poll_packages(polls: Any) -> list[dict[str, Any]]:
    """Group first-round hypotheses by the exact Race at a Glance key."""

    indexed_events = validated_first_round_events(polls)
    events = [event for _index, event in indexed_events]
    ordered_events = sorted(
        indexed_events,
        key=lambda item: (
            -_parse_date(
                item[1]["fieldwork_end"],
                f"polls[{item[0]}].fieldwork_end",
            ).toordinal(),
            french_compatible_sort_key(item[1]["pollster"]),
            item[0],
        ),
    )
    packages_by_key: dict[
        tuple[str, str, str, int | None],
        dict[str, Any],
    ] = {}
    packages: list[dict[str, Any]] = []
    for original_index, event in ordered_events:
        key = _package_key(event)
        package = packages_by_key.get(key)
        if package is None:
            package = {
                "package_key_values": list(key),
                "package_key": _serialized_package_key(key),
                "pollster": event["pollster"],
                "fieldwork_start": event["fieldwork_start"],
                "fieldwork_end": event["fieldwork_end"],
                "sample_size": event.get("sample_size"),
                "events": [],
                "original_package_index": len(packages),
                "first_input_index": original_index,
            }
            packages_by_key[key] = package
            packages.append(package)
        package["events"].append(event)

    for package in packages:
        selected_event = package["events"][0]
        selected_count = -1
        selected_index = 0
        for index, event in enumerate(package["events"]):
            comparable_count = _comparable_candidate_count(event, events)
            if comparable_count > selected_count:
                selected_event = event
                selected_count = comparable_count
                selected_index = index
        package["selected_event"] = selected_event
        package["selected_event_index"] = selected_index
        package["selected_comparable_candidate_count"] = max(
            0,
            selected_count,
        )

    return packages


def select_featured_polling_package(polls: Any) -> dict[str, Any]:
    """Return the first package under exact Race at a Glance ranking rules."""

    packages = build_poll_packages(polls)
    ranked = sorted(
        packages,
        key=lambda package: (
            -_parse_date(
                package["fieldwork_end"],
                "poll package fieldwork_end",
            ).toordinal(),
            -package["selected_comparable_candidate_count"],
            french_compatible_sort_key(package["pollster"]),
            package["original_package_index"],
        ),
    )
    if not ranked:
        raise CandidateSignalsError("no valid featured poll package exists")
    return ranked[0]


def project_candidate_polling(
    candidates: list[dict[str, str]],
    featured_package: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Project featured-package ranges without crossing pollster boundaries."""

    expected_key = (
        featured_package["pollster"],
        featured_package["fieldwork_start"],
        featured_package["fieldwork_end"],
        featured_package["sample_size"],
    )
    if any(_package_key(event) != expected_key for event in featured_package["events"]):
        raise CandidateSignalsError(
            "featured polling range would cross package or pollster boundaries"
        )

    canonical_names = [
        candidate["candidate_name"]
        for candidate in candidates
    ]
    by_name = {
        candidate["candidate_name"]: candidate
        for candidate in candidates
    }
    appearances: dict[str, list[int | float]] = {
        candidate["candidate_id"]: []
        for candidate in candidates
    }
    for event in featured_package["events"]:
        seen: set[str] = set()
        for candidate in event["candidates"]:
            try:
                resolved_name = resolve_candidate_name(
                    candidate["name"],
                    canonical_names,
                )
            except CandidateIdentityError:
                continue
            universe_candidate = by_name[resolved_name]
            identifier = universe_candidate["candidate_id"]
            if identifier in seen:
                raise CandidateSignalsError(
                    "featured hypothesis repeats a candidate"
                )
            seen.add(identifier)
            appearances[identifier].append(candidate["score"])

    selected_event = featured_package["selected_event"]
    selected_scores: dict[str, int | float] = {}
    for selected_candidate in selected_event["candidates"]:
        try:
            resolved_name = resolve_candidate_name(
                selected_candidate["name"],
                canonical_names,
            )
        except CandidateIdentityError:
            continue
        selected_scores[resolved_name] = selected_candidate["score"]
    projections: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        identifier = candidate["candidate_id"]
        scores = appearances[identifier]
        selected_score = selected_scores.get(candidate["candidate_name"])
        selected_rank = (
            1
            + sum(
                float(score) > float(selected_score)
                for score in selected_scores.values()
            )
            if selected_score is not None
            else None
        )
        if scores:
            projections[identifier] = {
                "evidence_state": "reported",
                "hypothesis_count": len(scores),
                "range_min": min(scores),
                "range_max": max(scores),
                "selected_hypothesis_score": selected_score,
                "selected_hypothesis_rank": selected_rank,
            }
        else:
            projections[identifier] = {
                "evidence_state": "not_observed",
                "hypothesis_count": None,
                "range_min": None,
                "range_max": None,
                "selected_hypothesis_score": None,
                "selected_hypothesis_rank": None,
            }
    return projections


PERIOD_KEYS = {
    "start_date",
    "end_date",
    "record_count",
    "publisher_count",
    "publisher_names",
    "candidate_metrics",
}
METRIC_KEYS = {
    "candidate",
    "record_count",
    "share",
    "publisher_count",
    "publisher_names",
    "active_day_count",
    "headline_match_count",
    "summary_only_match_count",
    "scope_counts",
    "scope_shares",
    "story_cluster_count",
    "story_clusters",
    "concentration",
}
CONCENTRATION_KEYS = {
    "leading_publisher",
    "leading_publisher_record_count",
    "leading_publisher_share",
    "leading_story_record_count",
    "leading_story_share",
}
QUALITY_KEYS = {
    "status",
    "reason",
    "current_record_count",
    "prior_record_count",
    "current_publisher_count",
    "prior_publisher_count",
    "common_publisher_count",
    "publisher_union_count",
    "publisher_overlap_ratio",
    "record_count_ratio",
    "thresholds",
}
ACTIVE_VISIBILITY_KEYS = {
    "method",
    "denominator_scope",
    "status_as_of",
    "primary",
    "general",
}
ACTIVE_SCOPE_KEYS = {
    "current_period",
    "prior_period",
    "comparison_quality",
    "main",
    "secondary",
}
ACTIVE_PERIOD_KEYS = {
    "start_date",
    "end_date",
    "record_count",
    "publisher_count",
}
ACTIVE_ROW_KEYS = {
    "candidate_id",
    "candidate_name",
    "status",
    "display_tier",
    "current_record_count",
    "current_share",
    "prior_record_count",
    "prior_share",
    "share_change",
}




def _validate_concentration(
    value: Any,
    context: str,
    record_count: int,
) -> dict[str, Any]:
    concentration = _require_object(value, context)
    if set(concentration) != CONCENTRATION_KEYS:
        raise CandidateSignalsError(f"{context} has unexpected fields")
    leading_publisher = concentration["leading_publisher"]
    if leading_publisher is not None:
        _require_text(leading_publisher, f"{context}.leading_publisher")
    for field in (
        "leading_publisher_record_count",
        "leading_story_record_count",
    ):
        count = _require_non_negative_integer(
            concentration[field],
            f"{context}.{field}",
        )
        if count > record_count:
            raise CandidateSignalsError(f"{context}.{field} is too large")
    for field in ("leading_publisher_share", "leading_story_share"):
        _ratio(concentration[field], f"{context}.{field}")
    return concentration


def _validate_visibility_period(
    value: Any,
    context: str,
    *,
    expected_lane: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    period = _require_object(value, context)
    if set(period) != PERIOD_KEYS:
        raise CandidateSignalsError(f"{context} has unexpected fields")
    start = _parse_date(period["start_date"], f"{context}.start_date")
    end = _parse_date(period["end_date"], f"{context}.end_date")
    if start > end or (end - start).days != 6:
        raise CandidateSignalsError(f"{context} must span exactly seven days")
    _require_non_negative_integer(
        period["record_count"],
        f"{context}.record_count",
    )
    publisher_count = _require_non_negative_integer(
        period["publisher_count"],
        f"{context}.publisher_count",
    )
    publisher_names = _require_list(
        period["publisher_names"],
        f"{context}.publisher_names",
    )
    if (
        any(
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            for name in publisher_names
        )
        or len(publisher_names) != len(set(publisher_names))
        or publisher_count != len(publisher_names)
    ):
        raise CandidateSignalsError(f"{context}.publisher_names is invalid")

    metrics = _require_list(
        period["candidate_metrics"],
        f"{context}.candidate_metrics",
    )
    metrics_by_key: dict[str, dict[str, Any]] = {}
    for index, metric_value in enumerate(metrics):
        metric_context = f"{context}.candidate_metrics[{index}]"
        metric = _require_object(metric_value, metric_context)
        if set(metric) != METRIC_KEYS:
            raise CandidateSignalsError(
                f"{metric_context} has unexpected fields"
            )
        try:
            candidate_name = canonical_candidate_name(metric["candidate"])
            candidate_key = normalized_candidate_key(candidate_name)
        except CandidateIdentityError as error:
            raise _error_from_identity(error) from error
        if candidate_name != metric["candidate"]:
            raise CandidateSignalsError(
                f"{metric_context}.candidate has non-canonical whitespace"
            )
        if candidate_key in metrics_by_key:
            raise CandidateSignalsError(
                f"{context} contains duplicate candidate metrics"
            )

        record_count = _require_non_negative_integer(
            metric["record_count"],
            f"{metric_context}.record_count",
        )
        if record_count == 0:
            raise CandidateSignalsError(
                f"{metric_context}.record_count must be positive"
            )
        _ratio(metric["share"], f"{metric_context}.share")
        metric_publisher_count = _require_non_negative_integer(
            metric["publisher_count"],
            f"{metric_context}.publisher_count",
        )
        metric_publishers = _require_list(
            metric["publisher_names"],
            f"{metric_context}.publisher_names",
        )
        if (
            len(metric_publishers) != len(set(metric_publishers))
            or any(
                not isinstance(name, str)
                or not name.strip()
                or name != name.strip()
                for name in metric_publishers
            )
            or metric_publisher_count != len(metric_publishers)
        ):
            raise CandidateSignalsError(
                f"{metric_context}.publisher_names is invalid"
            )
        for field in (
            "active_day_count",
            "headline_match_count",
            "summary_only_match_count",
            "story_cluster_count",
        ):
            _require_non_negative_integer(
                metric[field],
                f"{metric_context}.{field}",
            )
        if (
            metric["headline_match_count"]
            + metric["summary_only_match_count"]
            != record_count
        ):
            raise CandidateSignalsError(
                f"{metric_context} match counts do not equal record_count"
            )

        scope_counts = _require_object(
            metric["scope_counts"],
            f"{metric_context}.scope_counts",
        )
        scope_shares = _require_object(
            metric["scope_shares"],
            f"{metric_context}.scope_shares",
        )
        if set(scope_counts) != set(VISIBILITY_SCOPES) or set(
            scope_shares
        ) != set(VISIBILITY_SCOPES):
            raise CandidateSignalsError(
                f"{metric_context} scope composition is invalid"
            )
        for scope in VISIBILITY_SCOPES:
            _require_non_negative_integer(
                scope_counts[scope],
                f"{metric_context}.scope_counts.{scope}",
            )
            _ratio(
                scope_shares[scope],
                f"{metric_context}.scope_shares.{scope}",
            )
        if sum(scope_counts.values()) != record_count:
            raise CandidateSignalsError(
                f"{metric_context} scope counts do not equal record_count"
            )
        if expected_lane == "primary":
            if scope_counts[GENERAL_SCOPE] != 0:
                raise CandidateSignalsError(
                    "general records appear inside the primary attention lane"
                )
        elif (
            scope_counts["election"] != 0
            or scope_counts["campaign"] != 0
            or scope_counts[GENERAL_SCOPE] != record_count
        ):
            raise CandidateSignalsError(
                "election/campaign records appear inside the general lane"
            )

        story_clusters = _require_list(
            metric["story_clusters"],
            f"{metric_context}.story_clusters",
        )
        if metric["story_cluster_count"] != len(story_clusters):
            raise CandidateSignalsError(
                f"{metric_context}.story_cluster_count is inconsistent"
            )
        _validate_concentration(
            metric["concentration"],
            f"{metric_context}.concentration",
            record_count,
        )
        metrics_by_key[candidate_key] = metric
    return period, metrics_by_key


def _project_concentration(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "leading_publisher": value["leading_publisher"],
        "leading_publisher_record_count": value[
            "leading_publisher_record_count"
        ],
        "leading_publisher_share": value["leading_publisher_share"],
        "leading_story_record_count": value["leading_story_record_count"],
        "leading_story_share": value["leading_story_share"],
    }


def _campaign_metric_projection(
    metric: dict[str, Any] | None,
) -> dict[str, Any]:
    if metric is None:
        return {
            "evidence_state": "not_observed",
            "record_count": None,
            "share": None,
            "publisher_count": None,
            "active_day_count": None,
            "headline_match_count": None,
            "summary_only_match_count": None,
            "scope_counts": None,
            "scope_shares": None,
            "story_cluster_count": None,
            "concentration": None,
        }
    return {
        "evidence_state": "reported",
        "record_count": metric["record_count"],
        "share": metric["share"],
        "publisher_count": metric["publisher_count"],
        "active_day_count": metric["active_day_count"],
        "headline_match_count": metric["headline_match_count"],
        "summary_only_match_count": metric["summary_only_match_count"],
        "scope_counts": copy.deepcopy(metric["scope_counts"]),
        "scope_shares": copy.deepcopy(metric["scope_shares"]),
        "story_cluster_count": metric["story_cluster_count"],
        "concentration": _project_concentration(metric["concentration"]),
    }


def _general_metric_projection(
    metric: dict[str, Any] | None,
) -> dict[str, Any]:
    if metric is None:
        return {
            "evidence_state": "not_observed",
            "record_count": None,
            "share": None,
            "publisher_count": None,
            "active_day_count": None,
            "headline_match_count": None,
            "summary_only_match_count": None,
            "story_cluster_count": None,
            "concentration": None,
        }
    return {
        "evidence_state": "reported",
        "record_count": metric["record_count"],
        "share": metric["share"],
        "publisher_count": metric["publisher_count"],
        "active_day_count": metric["active_day_count"],
        "headline_match_count": metric["headline_match_count"],
        "summary_only_match_count": metric["summary_only_match_count"],
        "story_cluster_count": metric["story_cluster_count"],
        "concentration": _project_concentration(metric["concentration"]),
    }


def project_visibility(
    candidates: list[dict[str, str]],
    news: Any,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Validate and separately project primary and general visibility."""

    news_object = _require_object(news, "news")
    visibility = _require_object(
        news_object.get("candidate_visibility"),
        "news.candidate_visibility",
    )
    expected_top_keys = {
        "method",
        "primary_scopes",
        "secondary_scope",
        "current_period",
        "prior_period",
        "general_current_period",
        "general_prior_period",
        "comparison_quality",
    }
    if set(visibility) != expected_top_keys:
        raise CandidateSignalsError(
            "news.candidate_visibility has unexpected fields"
        )
    method = _require_text(
        visibility["method"],
        "news.candidate_visibility.method",
    )
    if visibility["primary_scopes"] != list(PRIMARY_SCOPES):
        raise CandidateSignalsError(
            "news.candidate_visibility.primary_scopes is invalid"
        )
    if visibility["secondary_scope"] != GENERAL_SCOPE:
        raise CandidateSignalsError(
            "news.candidate_visibility.secondary_scope is invalid"
        )

    current, current_metrics = _validate_visibility_period(
        visibility["current_period"],
        "news.candidate_visibility.current_period",
        expected_lane="primary",
    )
    prior, _prior_metrics = _validate_visibility_period(
        visibility["prior_period"],
        "news.candidate_visibility.prior_period",
        expected_lane="primary",
    )
    general_current, general_metrics = _validate_visibility_period(
        visibility["general_current_period"],
        "news.candidate_visibility.general_current_period",
        expected_lane="general",
    )
    _general_prior, _general_prior_metrics = _validate_visibility_period(
        visibility["general_prior_period"],
        "news.candidate_visibility.general_prior_period",
        expected_lane="general",
    )

    quality = _require_object(
        visibility["comparison_quality"],
        "news.candidate_visibility.comparison_quality",
    )
    if set(quality) != QUALITY_KEYS:
        raise CandidateSignalsError(
            "news.candidate_visibility.comparison_quality has unexpected fields"
        )
    if quality["status"] not in {"comparable", "not_comparable"}:
        raise CandidateSignalsError(
            "news.candidate_visibility.comparison_quality.status is invalid"
        )
    _require_text(
        quality["reason"],
        "news.candidate_visibility.comparison_quality.reason",
    )
    for field in (
        "current_record_count",
        "prior_record_count",
        "current_publisher_count",
        "prior_publisher_count",
        "common_publisher_count",
        "publisher_union_count",
    ):
        _require_non_negative_integer(
            quality[field],
            f"news.candidate_visibility.comparison_quality.{field}",
        )
    _ratio(
        quality["publisher_overlap_ratio"],
        "news.candidate_visibility.comparison_quality.publisher_overlap_ratio",
    )
    record_count_ratio = quality["record_count_ratio"]
    if record_count_ratio is not None:
        ratio = _numeric(
            record_count_ratio,
            "news.candidate_visibility.comparison_quality.record_count_ratio",
            non_negative=True,
        )
        if ratio < 1:
            raise CandidateSignalsError(
                "comparison_quality.record_count_ratio must be at least one"
            )
    _require_object(
        quality["thresholds"],
        "news.candidate_visibility.comparison_quality.thresholds",
    )
    expected_quality_counts = {
        "current_record_count": current["record_count"],
        "prior_record_count": prior["record_count"],
        "current_publisher_count": current["publisher_count"],
        "prior_publisher_count": prior["publisher_count"],
    }
    if any(
        quality[field] != expected
        for field, expected in expected_quality_counts.items()
    ):
        raise CandidateSignalsError(
            "comparison_quality counts do not match visibility periods"
        )

    visibility_projection = {
        "method": method,
        "primary_scopes": list(PRIMARY_SCOPES),
        "secondary_scope": GENERAL_SCOPE,
        "current_period": {
            "start_date": current["start_date"],
            "end_date": current["end_date"],
            "record_count": current["record_count"],
            "publisher_count": current["publisher_count"],
        },
        "general_current_period": {
            "start_date": general_current["start_date"],
            "end_date": general_current["end_date"],
            "record_count": general_current["record_count"],
            "publisher_count": general_current["publisher_count"],
        },
        "comparison_quality": copy.deepcopy(quality),
    }
    campaign: dict[str, dict[str, Any]] = {}
    general: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        identifier = candidate["candidate_id"]
        key = normalized_candidate_key(candidate["candidate_name"])
        campaign[identifier] = _campaign_metric_projection(
            current_metrics.get(key)
        )
        general[identifier] = _general_metric_projection(
            general_metrics.get(key)
        )
    return visibility_projection, campaign, general


def _empty_scrutiny_counts() -> dict[str, Any]:
    return {
        "review_count": 0,
        "by_count": 0,
        "about_count": 0,
        "newest_review_date": None,
        "newest_review_url": None,
    }


def _update_newest_review(
    bucket: dict[str, Any],
    review_date: str,
    review_url: str,
) -> None:
    current_date = bucket["newest_review_date"]
    current_url = bucket["newest_review_url"]
    if (
        current_date is None
        or review_date > current_date
        or (
            review_date == current_date
            and (current_url is None or review_url < current_url)
        )
    ):
        bucket["newest_review_date"] = review_date
        bucket["newest_review_url"] = review_url


def project_scrutiny(
    candidates: list[dict[str, str]],
    claims: Any,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str | None]:
    """Project inclusive 14-day and archive scrutiny counts per candidate."""

    claims_object = _require_object(claims, "claims")
    latest_end = _timestamp_date(
        claims_object.get("generated_at"),
        "claims.generated_at",
    )
    latest_start = latest_end - timedelta(days=LATEST_SCRUTINY_DAYS - 1)
    archive_window_days = _require_non_negative_integer(
        claims_object.get("archive_window_days"),
        "claims.archive_window_days",
    )
    reviews = _require_list(claims_object.get("reviews"), "claims.reviews")

    by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    by_key = {
        normalized_candidate_key(candidate["candidate_name"]): candidate
        for candidate in candidates
    }
    projections = {
        candidate["candidate_id"]: {
            "latest_14_days": _empty_scrutiny_counts(),
            "archive": _empty_scrutiny_counts(),
        }
        for candidate in candidates
    }
    newest_evidence: date | None = None

    for review_index, review_value in enumerate(reviews):
        context = f"claims.reviews[{review_index}]"
        review = _require_object(review_value, context)
        review_date = _parse_date(
            review.get("review_date"),
            f"{context}.review_date",
        )
        if review_date > latest_end:
            raise CandidateSignalsError(
                f"{context}.review_date is in the future relative to "
                "claims.generated_at"
            )
        newest_evidence = (
            review_date
            if newest_evidence is None
            else max(newest_evidence, review_date)
        )
        review_url = review.get("review_url")
        if not _usable_url(review_url):
            raise CandidateSignalsError(f"{context}.review_url is invalid")
        associations = _require_list(
            review.get("candidate_associations"),
            f"{context}.candidate_associations",
        )
        seen_associations: set[str] = set()
        for association_index, association_value in enumerate(associations):
            association_context = (
                f"{context}.candidate_associations[{association_index}]"
            )
            association = _require_object(
                association_value,
                association_context,
            )
            association_id = _require_text(
                association.get("candidate_id"),
                f"{association_context}.candidate_id",
            )
            try:
                association_name = canonical_candidate_name(
                    association.get("candidate_name")
                )
                association_key = normalized_candidate_key(association_name)
            except CandidateIdentityError as error:
                raise _error_from_identity(error) from error
            if association_id in seen_associations:
                raise CandidateSignalsError(
                    f"{context} associates the same candidate more than once"
                )
            seen_associations.add(association_id)
            relationship = association.get("relationship")
            if relationship not in {"by", "about"}:
                raise CandidateSignalsError(
                    f"{association_context}.relationship must be by or about"
                )

            universe_candidate = by_id.get(association_id)
            if universe_candidate is None:
                if by_key.get(association_key) is not None:
                    raise CandidateSignalsError(
                        f"{association_context} conflicts with candidate universe"
                    )
                continue
            if normalized_candidate_key(
                universe_candidate["candidate_name"]
            ) != association_key:
                raise CandidateSignalsError(
                    f"{association_context} conflicts with candidate universe"
                )

            candidate_projection = projections[association_id]
            archive = candidate_projection["archive"]
            archive["review_count"] += 1
            archive[f"{relationship}_count"] += 1
            _update_newest_review(
                archive,
                review_date.isoformat(),
                review_url,
            )
            if latest_start <= review_date <= latest_end:
                latest = candidate_projection["latest_14_days"]
                latest["review_count"] += 1
                latest[f"{relationship}_count"] += 1
                _update_newest_review(
                    latest,
                    review_date.isoformat(),
                    review_url,
                )

    window = {
        "latest_days": LATEST_SCRUTINY_DAYS,
        "latest_start_date": latest_start.isoformat(),
        "latest_end_date": latest_end.isoformat(),
        "archive_window_days": archive_window_days,
    }
    return (
        window,
        projections,
        newest_evidence.isoformat() if newest_evidence is not None else None,
    )


def _validated_candidate_watch(
    candidate_watch: Any,
) -> list[dict[str, Any]]:
    items = _require_list(candidate_watch, "news.candidate_watch")
    validated: list[dict[str, Any]] = []
    for index, item_value in enumerate(items):
        context = f"news.candidate_watch[{index}]"
        item = _require_object(item_value, context)
        identifier = _require_text(item.get("id"), f"{context}.id")
        published = _parse_timestamp(
            item.get("published_at"),
            f"{context}.published_at",
        )
        publisher = _require_text(
            item.get("publisher"),
            f"{context}.publisher",
        )
        headline = _require_text(
            item.get("headline"),
            f"{context}.headline",
        )
        coverage_scope = item.get("coverage_scope")
        if coverage_scope not in VISIBILITY_SCOPES:
            raise CandidateSignalsError(
                f"{context}.coverage_scope is invalid"
            )
        candidates = _require_list(
            item.get("candidates"),
            f"{context}.candidates",
        )
        candidate_keys: list[str] = []
        for candidate_index, candidate_name in enumerate(candidates):
            try:
                canonical = canonical_candidate_name(candidate_name)
                candidate_keys.append(normalized_candidate_key(canonical))
            except CandidateIdentityError as error:
                raise CandidateSignalsError(
                    f"{context}.candidates[{candidate_index}]: {error}"
                ) from error
        if len(candidate_keys) != len(set(candidate_keys)):
            raise CandidateSignalsError(
                f"{context}.candidates contains duplicates"
            )

        candidate_matches = _require_list(
            item.get("candidate_matches"),
            f"{context}.candidate_matches",
        )
        matched_candidates: list[str] = []
        headline_candidate_keys: list[str] = []
        approved_match_keys = {
            "candidate",
            "matched_aliases",
            "locations",
        }
        approved_locations = {"headline", "summary"}

        for match_index, match_value in enumerate(candidate_matches):
            match_context = (
                f"{context}.candidate_matches[{match_index}]"
            )
            match = _require_object(match_value, match_context)
            if set(match) != approved_match_keys:
                raise CandidateSignalsError(
                    f"{match_context} has unexpected fields"
                )

            match_candidate = match["candidate"]
            if (
                not isinstance(match_candidate, str)
                or not match_candidate.strip()
            ):
                raise CandidateSignalsError(
                    f"{match_context}.candidate must be non-empty"
                )

            try:
                match_key = normalized_candidate_key(
                    canonical_candidate_name(match_candidate)
                )
            except CandidateIdentityError as error:
                raise CandidateSignalsError(
                    f"{match_context}.candidate: {error}"
                ) from error

            matched_aliases = match["matched_aliases"]
            if (
                not isinstance(matched_aliases, list)
                or not matched_aliases
                or any(
                    not isinstance(alias, str) or not alias.strip()
                    for alias in matched_aliases
                )
                or len(matched_aliases) != len(set(matched_aliases))
            ):
                raise CandidateSignalsError(
                    f"{match_context}.matched_aliases is invalid"
                )

            locations = match["locations"]
            if (
                not isinstance(locations, list)
                or not locations
                or any(
                    location not in approved_locations
                    for location in locations
                )
                or len(locations) != len(set(locations))
            ):
                raise CandidateSignalsError(
                    f"{match_context}.locations is invalid"
                )

            matched_candidates.append(match_candidate)

            if "headline" in locations:
                headline_candidate_keys.append(match_key)

        if len(matched_candidates) != len(set(matched_candidates)):
            raise CandidateSignalsError(
                f"{context}.candidate_matches contains duplicates"
            )

        if sorted(matched_candidates) != sorted(candidates):
            raise CandidateSignalsError(
                f"{context}.candidates and candidate_matches disagree"
            )

        url = item.get("url")
        validated.append(
            {
                "id": identifier,
                "published_at": item["published_at"],
                "_published_datetime": published,
                "publisher": publisher,
                "headline": headline,
                "url": url,
                "_usable_url": _usable_url(url),
                "coverage_scope": coverage_scope,
                "_candidate_keys": candidate_keys,
                "_headline_candidate_keys": headline_candidate_keys,
            }
        )
    return validated
def _round_visibility_ratio(value: float) -> float:
    return math.floor(value * 1000 + 0.5) / 1000


def build_active_comparison_quality(
    *,
    current_record_count: int,
    prior_record_count: int,
    current_publishers: set[str],
    prior_publishers: set[str],
) -> dict[str, Any]:
    """Build the collector-compatible gate from one pair of record unions."""

    common_publisher_count = len(
        current_publishers & prior_publishers
    )
    publisher_union_count = len(
        current_publishers | prior_publishers
    )
    publisher_overlap_ratio = _round_visibility_ratio(
        common_publisher_count / publisher_union_count
        if publisher_union_count
        else 0.0
    )
    record_count_ratio = (
        _round_visibility_ratio(
            max(current_record_count, prior_record_count)
            / min(current_record_count, prior_record_count)
        )
        if current_record_count and prior_record_count
        else None
    )
    thresholds = ACTIVE_VISIBILITY_THRESHOLDS
    if (
        current_record_count < thresholds["minimum_period_records"]
        or prior_record_count < thresholds["minimum_period_records"]
        or len(current_publishers)
        < thresholds["minimum_period_publishers"]
        or len(prior_publishers)
        < thresholds["minimum_period_publishers"]
        or common_publisher_count
        < thresholds["minimum_common_publishers"]
    ):
        status = "not_comparable"
        reason = "insufficient_data"
    elif (
        publisher_overlap_ratio
        < thresholds["minimum_publisher_overlap_ratio"]
        or record_count_ratio is None
        or record_count_ratio
        > thresholds["maximum_record_count_ratio"]
    ):
        status = "not_comparable"
        reason = "publisher_panel_changed"
    else:
        status = "comparable"
        reason = "comparable"

    return {
        "status": status,
        "reason": reason,
        "current_record_count": current_record_count,
        "prior_record_count": prior_record_count,
        "current_publisher_count": len(current_publishers),
        "prior_publisher_count": len(prior_publishers),
        "common_publisher_count": common_publisher_count,
        "publisher_union_count": publisher_union_count,
        "publisher_overlap_ratio": publisher_overlap_ratio,
        "record_count_ratio": record_count_ratio,
        "thresholds": dict(ACTIVE_VISIBILITY_THRESHOLDS),
    }


def _active_row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    current_share = row["current_share"]
    prior_share = row["prior_share"]
    return (
        current_share is None,
        -(current_share if current_share is not None else 0),
        -row["current_record_count"],
        prior_share is None,
        -(prior_share if prior_share is not None else 0),
        -row["prior_record_count"],
        row["candidate_name"].casefold(),
        row["candidate_id"],
    )


def derive_active_field_visibility(
    news: Any,
    active_monitoring_field: Any,
    candidacy_status: Any,
) -> dict[str, Any]:
    """Derive active-field visibility from published record associations."""

    news_object = _require_object(news, "news")
    field = _require_plain_object(
        active_monitoring_field,
        "active_monitoring_field",
    )
    if set(field) != ACTIVE_MONITORING_FIELD_KEYS:
        raise CandidateSignalsError(
            "active_monitoring_field has unexpected fields"
        )
    try:
        validate_candidate_candidacy_status(candidacy_status)
        registry_by_id = candidacy_status_by_id(candidacy_status)
        expected_field = project_active_monitoring_field(candidacy_status)
    except CandidateCandidacyStatusError as error:
        raise CandidateSignalsError(
            f"candidacy-status registry is invalid: {error}"
        ) from error
    if field != expected_field:
        raise CandidateSignalsError(
            "active_monitoring_field does not match candidacy registry"
        )

    source_visibility = _require_object(
        news_object.get("candidate_visibility"),
        "news.candidate_visibility",
    )
    source_quality = _require_object(
        source_visibility.get("comparison_quality"),
        "news.candidate_visibility.comparison_quality",
    )
    if source_quality.get("thresholds") != ACTIVE_VISIBILITY_THRESHOLDS:
        raise CandidateSignalsError(
            "candidate visibility thresholds do not match active-field gate"
        )

    source_periods: dict[str, dict[str, Any]] = {}
    for period_name, lane in (
        ("current_period", "primary"),
        ("prior_period", "primary"),
        ("general_current_period", "general"),
        ("general_prior_period", "general"),
    ):
        period, _metrics = _validate_visibility_period(
            source_visibility.get(period_name),
            f"news.candidate_visibility.{period_name}",
            expected_lane=lane,
        )
        source_periods[period_name] = period

    active_ids = [
        identifier
        for tier in ("main", "secondary")
        for identifier in field[tier]
    ]
    active_by_key: dict[str, str] = {}
    for identifier in active_ids:
        source = registry_by_id[identifier]
        key = normalized_candidate_key(source["candidate_name"])
        if key in active_by_key:
            raise CandidateSignalsError(
                "active candidacy registry contains duplicate identities"
            )
        active_by_key[key] = identifier

    records = _validated_candidate_watch(
        news_object.get("candidate_watch")
    )
    record_ids: set[str] = set()
    for record in records:
        if record["id"] in record_ids:
            raise CandidateSignalsError(
                "news.candidate_watch record IDs must be unique"
            )
        record_ids.add(record["id"])

    def collect_period(
        source_period: dict[str, Any],
        scopes: set[str],
    ) -> dict[str, Any]:
        start = _parse_date(
            source_period["start_date"],
            "active visibility period start_date",
        )
        end = _parse_date(
            source_period["end_date"],
            "active visibility period end_date",
        )
        denominator_ids: set[str] = set()
        publishers: set[str] = set()
        candidate_record_ids = {
            identifier: set()
            for identifier in active_ids
        }
        for record in records:
            published_date = record["_published_datetime"].date()
            if (
                record["coverage_scope"] not in scopes
                or not start <= published_date <= end
            ):
                continue
            matched_active_ids = {
                active_by_key[key]
                for key in record["_candidate_keys"]
                if key in active_by_key
            }
            if not matched_active_ids:
                continue
            identifier = record["id"]
            denominator_ids.add(identifier)
            publishers.add(record["publisher"])
            for candidate_identifier in matched_active_ids:
                candidate_record_ids[candidate_identifier].add(identifier)
        return {
            "start_date": source_period["start_date"],
            "end_date": source_period["end_date"],
            "record_count": len(denominator_ids),
            "publisher_count": len(publishers),
            "_publishers": publishers,
            "_candidate_record_ids": candidate_record_ids,
        }

    def build_scope(
        current_source: dict[str, Any],
        prior_source: dict[str, Any],
        scopes: set[str],
    ) -> dict[str, Any]:
        current = collect_period(current_source, scopes)
        prior = collect_period(prior_source, scopes)
        quality = build_active_comparison_quality(
            current_record_count=current["record_count"],
            prior_record_count=prior["record_count"],
            current_publishers=current["_publishers"],
            prior_publishers=prior["_publishers"],
        )

        rows_by_tier: dict[str, list[dict[str, Any]]] = {
            "main": [],
            "secondary": [],
        }
        for tier in ("main", "secondary"):
            for identifier in field[tier]:
                source = registry_by_id[identifier]
                current_count = len(
                    current["_candidate_record_ids"][identifier]
                )
                prior_count = len(
                    prior["_candidate_record_ids"][identifier]
                )
                current_share = (
                    _round_visibility_ratio(
                        current_count / current["record_count"]
                    )
                    if current["record_count"]
                    else None
                )
                prior_share = (
                    _round_visibility_ratio(
                        prior_count / prior["record_count"]
                    )
                    if prior["record_count"]
                    else None
                )
                share_change = (
                    _round_visibility_ratio(
                        current_share - prior_share
                    )
                    if (
                        quality["status"] == "comparable"
                        and current_share is not None
                        and prior_share is not None
                    )
                    else None
                )
                rows_by_tier[tier].append(
                    {
                        "candidate_id": identifier,
                        "candidate_name": source["candidate_name"],
                        "status": source["status"],
                        "display_tier": source["display_tier"],
                        "current_record_count": current_count,
                        "current_share": current_share,
                        "prior_record_count": prior_count,
                        "prior_share": prior_share,
                        "share_change": share_change,
                    }
                )
            rows_by_tier[tier].sort(key=_active_row_sort_key)

        def public_period(period: dict[str, Any]) -> dict[str, Any]:
            return {
                field_name: period[field_name]
                for field_name in (
                    "start_date",
                    "end_date",
                    "record_count",
                    "publisher_count",
                )
            }

        return {
            "current_period": public_period(current),
            "prior_period": public_period(prior),
            "comparison_quality": quality,
            "main": rows_by_tier["main"],
            "secondary": rows_by_tier["secondary"],
        }

    return {
        "method": ACTIVE_FIELD_VISIBILITY_METHOD,
        "denominator_scope": ACTIVE_FIELD_DENOMINATOR_SCOPE,
        "status_as_of": candidacy_status["status_as_of"],
        "primary": build_scope(
            source_periods["current_period"],
            source_periods["prior_period"],
            set(PRIMARY_SCOPES),
        ),
        "general": build_scope(
            source_periods["general_current_period"],
            source_periods["general_prior_period"],
            {GENERAL_SCOPE},
        ),
    }

def validate_active_field_visibility(
    value: Any,
    active_monitoring_field: dict[str, Any],
    candidates: list[dict[str, Any]],
    status_as_of: str,
) -> None:
    """Validate the published active roster, arithmetic, gate, and order."""

    active = _require_plain_object(value, "active_field_visibility")
    if set(active) != ACTIVE_VISIBILITY_KEYS:
        raise CandidateSignalsError(
            "active_field_visibility has unexpected fields"
        )
    if active["method"] != ACTIVE_FIELD_VISIBILITY_METHOD:
        raise CandidateSignalsError(
            "active_field_visibility.method is invalid"
        )
    if active["denominator_scope"] != ACTIVE_FIELD_DENOMINATOR_SCOPE:
        raise CandidateSignalsError(
            "active_field_visibility.denominator_scope is invalid"
        )
    if active["status_as_of"] != status_as_of:
        raise CandidateSignalsError(
            "active_field_visibility.status_as_of is inconsistent"
        )

    candidates_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in candidates
    }
    parsed_periods: dict[str, tuple[date, date]] = {}

    for scope_name in ("primary", "general"):
        scope = _require_plain_object(
            active[scope_name],
            f"active_field_visibility.{scope_name}",
        )
        if set(scope) != ACTIVE_SCOPE_KEYS:
            raise CandidateSignalsError(
                f"active_field_visibility.{scope_name} has unexpected fields"
            )

        periods: dict[str, dict[str, Any]] = {}
        for period_name in ("current_period", "prior_period"):
            context = (
                f"active_field_visibility.{scope_name}.{period_name}"
            )
            period = _require_plain_object(scope[period_name], context)
            if set(period) != ACTIVE_PERIOD_KEYS:
                raise CandidateSignalsError(
                    f"{context} has unexpected fields"
                )
            start = _parse_date(
                period["start_date"],
                f"{context}.start_date",
            )
            end = _parse_date(
                period["end_date"],
                f"{context}.end_date",
            )
            if start > end or (end - start).days != 6:
                raise CandidateSignalsError(
                    f"{context} must span exactly seven days"
                )
            _require_non_negative_integer(
                period["record_count"],
                f"{context}.record_count",
            )
            _require_non_negative_integer(
                period["publisher_count"],
                f"{context}.publisher_count",
            )
            periods[period_name] = period
            parsed_periods[f"{scope_name}.{period_name}"] = (start, end)
            if period["publisher_count"] > period["record_count"]:
                raise CandidateSignalsError(
                    f"{context}.publisher_count exceeds record_count"
                )


        current_start, _current_end = parsed_periods[
            f"{scope_name}.current_period"
        ]
        _prior_start, prior_end = parsed_periods[
            f"{scope_name}.prior_period"
        ]
        if prior_end != current_start - timedelta(days=1):
            raise CandidateSignalsError(
                f"active_field_visibility.{scope_name} periods are not contiguous"
            )

        quality_context = (
            f"active_field_visibility.{scope_name}.comparison_quality"
        )
        quality = _require_plain_object(
            scope["comparison_quality"],
            quality_context,
        )
        if set(quality) != QUALITY_KEYS:
            raise CandidateSignalsError(
                f"{quality_context} has unexpected fields"
            )
        for field_name in (
            "current_record_count",
            "prior_record_count",
            "current_publisher_count",
            "prior_publisher_count",
            "common_publisher_count",
            "publisher_union_count",
        ):
            _require_non_negative_integer(
                quality[field_name],
                f"{quality_context}.{field_name}",
            )
        current_publisher_count = quality["current_publisher_count"]
        prior_publisher_count = quality["prior_publisher_count"]
        common_publisher_count = quality["common_publisher_count"]
        if common_publisher_count > min(
            current_publisher_count,
            prior_publisher_count,
        ):
            raise CandidateSignalsError(
                f"{quality_context} common publisher count is invalid"
            )
        expected_union = (
            current_publisher_count
            + prior_publisher_count
            - common_publisher_count
        )
        if quality["publisher_union_count"] != expected_union:
            raise CandidateSignalsError(
                f"{quality_context} publisher union is inconsistent"
            )
        common_publishers = {
            f"common-{index}"
            for index in range(common_publisher_count)
        }
        synthetic_current = common_publishers | {
            f"current-{index}"
            for index in range(
                current_publisher_count - common_publisher_count
            )
        }
        synthetic_prior = common_publishers | {
            f"prior-{index}"
            for index in range(
                prior_publisher_count - common_publisher_count
            )
        }
        expected_quality = build_active_comparison_quality(
            current_record_count=periods["current_period"]["record_count"],
            prior_record_count=periods["prior_period"]["record_count"],
            current_publishers=synthetic_current,
            prior_publishers=synthetic_prior,
        )
        if quality != expected_quality:
            raise CandidateSignalsError(
                f"{quality_context} is inconsistent"
            )

        published_ids: set[str] = set()
        for tier in ("main", "secondary"):
            rows = _require_list(
                scope[tier],
                f"active_field_visibility.{scope_name}.{tier}",
            )
            if len(rows) != len(active_monitoring_field[tier]):
                raise CandidateSignalsError(
                    f"active_field_visibility.{scope_name}.{tier} count is invalid"
                )
            normalized_rows: list[dict[str, Any]] = []
            for index, row_value in enumerate(rows):
                context = (
                    f"active_field_visibility.{scope_name}.{tier}[{index}]"
                )
                row = _require_plain_object(row_value, context)
                if set(row) != ACTIVE_ROW_KEYS:
                    raise CandidateSignalsError(
                        f"{context} has unexpected fields"
                    )
                identifier = _require_text(
                    row["candidate_id"],
                    f"{context}.candidate_id",
                )
                if identifier in published_ids:
                    raise CandidateSignalsError(
                        f"active_field_visibility.{scope_name} has duplicate rows"
                    )
                published_ids.add(identifier)
                candidate = candidates_by_id.get(identifier)
                if candidate is None:
                    raise CandidateSignalsError(
                        f"{context} has an unknown candidate"
                    )
                candidacy = candidate["candidacy"]
                if (
                    identifier not in active_monitoring_field[tier]
                    or row["candidate_name"] != candidate["candidate_name"]
                    or row["status"] != candidacy["status"]
                    or row["display_tier"] != tier
                    or candidacy["display_tier"] != tier
                    or not candidacy["active_field_eligible"]
                ):
                    raise CandidateSignalsError(
                        f"{context} identity or candidacy is inconsistent"
                    )
                current_count = _require_non_negative_integer(
                    row["current_record_count"],
                    f"{context}.current_record_count",
                )
                prior_count = _require_non_negative_integer(
                    row["prior_record_count"],
                    f"{context}.prior_record_count",
                )
                if (
                    current_count > periods["current_period"]["record_count"]
                    or prior_count > periods["prior_period"]["record_count"]
                ):
                    raise CandidateSignalsError(
                        f"{context} count exceeds its denominator"
                    )
                expected_current_share = (
                    _round_visibility_ratio(
                        current_count
                        / periods["current_period"]["record_count"]
                    )
                    if periods["current_period"]["record_count"]
                    else None
                )
                expected_prior_share = (
                    _round_visibility_ratio(
                        prior_count
                        / periods["prior_period"]["record_count"]
                    )
                    if periods["prior_period"]["record_count"]
                    else None
                )
                if (
                    row["current_share"] != expected_current_share
                    or row["prior_share"] != expected_prior_share
                ):
                    raise CandidateSignalsError(
                        f"{context} share arithmetic is inconsistent"
                    )
                expected_change = (
                    _round_visibility_ratio(
                        expected_current_share - expected_prior_share
                    )
                    if (
                        quality["status"] == "comparable"
                        and expected_current_share is not None
                        and expected_prior_share is not None
                    )
                    else None
                )
                if row["share_change"] != expected_change:
                    raise CandidateSignalsError(
                        f"{context}.share_change is inconsistent"
                    )
                normalized_rows.append(row)
            if normalized_rows != sorted(
                normalized_rows,
                key=_active_row_sort_key,
            ):
                raise CandidateSignalsError(
                    f"active_field_visibility.{scope_name}.{tier} order is invalid"
                )
            if {row["candidate_id"] for row in normalized_rows} != set(
                active_monitoring_field[tier]
            ):
                raise CandidateSignalsError(
                    f"active_field_visibility.{scope_name}.{tier} membership is invalid"
                )

        expected_active_ids = set(
            active_monitoring_field["main"]
            + active_monitoring_field["secondary"]
        )
        if published_ids != expected_active_ids:
            raise CandidateSignalsError(
                f"active_field_visibility.{scope_name} active roster is incomplete"
            )

    if (
        parsed_periods["primary.current_period"]
        != parsed_periods["general.current_period"]
        or parsed_periods["primary.prior_period"]
        != parsed_periods["general.prior_period"]
    ):
        raise CandidateSignalsError(
            "active_field_visibility scope periods do not align"
        )





def _empty_latest_development() -> dict[str, Any]:
    return {
        "evidence_state": "none",
        "id": None,
        "published_at": None,
        "publisher": None,
        "headline": None,
        "url": None,
        "coverage_scope": None,
    }


def select_latest_development(
    candidate_name: str,
    candidate_watch: Any,
) -> dict[str, Any]:
    """Select one newest source-linked election/campaign candidate record."""

    try:
        key = normalized_candidate_key(candidate_name)
    except CandidateIdentityError as error:
        raise _error_from_identity(error) from error
    items = _validated_candidate_watch(candidate_watch)
    matches = [
        item
        for item in items
        if key in item["_headline_candidate_keys"]
        and item["coverage_scope"] in PRIMARY_SCOPES
        and item["_usable_url"]
    ]
    if not matches:
        return _empty_latest_development()
    matches.sort(
        key=lambda item: (
            -item["_published_datetime"].timestamp(),
            item["id"],
        )
    )
    selected = matches[0]
    return {
        "evidence_state": "reported",
        "id": selected["id"],
        "published_at": selected["published_at"],
        "publisher": selected["publisher"],
        "headline": selected["headline"],
        "url": selected["url"],
        "coverage_scope": selected["coverage_scope"],
    }


def project_latest_developments(
    candidates: list[dict[str, str]],
    candidate_watch: Any,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Project latest developments and the newest candidate-watch evidence date."""

    items = _validated_candidate_watch(candidate_watch)
    developments: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = normalized_candidate_key(candidate["candidate_name"])
        matches = [
            item
            for item in items
            if key in item["_headline_candidate_keys"]
            and item["coverage_scope"] in PRIMARY_SCOPES
            and item["_usable_url"]
        ]
        matches.sort(
            key=lambda item: (
                -item["_published_datetime"].timestamp(),
                item["id"],
            )
        )
        if matches:
            selected = matches[0]
            developments[candidate["candidate_id"]] = {
                "evidence_state": "reported",
                "id": selected["id"],
                "published_at": selected["published_at"],
                "publisher": selected["publisher"],
                "headline": selected["headline"],
                "url": selected["url"],
                "coverage_scope": selected["coverage_scope"],
            }
        else:
            developments[candidate["candidate_id"]] = (
                _empty_latest_development()
            )

    usable_dates = [
        item["_published_datetime"].date()
        for item in items
        if item["_usable_url"]
    ]
    newest = max(usable_dates).isoformat() if usable_dates else None
    return developments, newest


def _featured_package_public(
    package: dict[str, Any],
) -> dict[str, Any]:
    source_urls: list[str] = []
    for event in package["events"]:
        for field in ("official_source_url", "source_url"):
            url = event.get(field)
            if _usable_url(url) and url not in source_urls:
                source_urls.append(url)
    if not source_urls:
        raise CandidateSignalsError(
            "featured polling package has no usable source URL"
        )
    return {
        "package_key": package["package_key"],
        "pollster": package["pollster"],
        "fieldwork_start": package["fieldwork_start"],
        "fieldwork_end": package["fieldwork_end"],
        "sample_size": package["sample_size"],
        "hypothesis_count": len(package["events"]),
        "selected_hypothesis_event_id": package["selected_event"]["event_id"],
        "source_urls": source_urls,
    }


def _featured_poll_candidate_sort_key(
    candidate: dict[str, Any],
) -> tuple[float, int, str]:
    return (
        -float(candidate["reported_score"]),
        candidate["source_position"],
        candidate["candidate_id"],
    )


def _featured_poll_board_public(
    package: dict[str, Any],
    candidates: list[dict[str, str]],
    source_urls: list[str],
) -> dict[str, Any]:
    selected_event = package["selected_event"]
    canonical_names = [
        candidate["candidate_name"]
        for candidate in candidates
    ]
    by_name = {
        candidate["candidate_name"]: candidate
        for candidate in candidates
    }
    lineup: list[dict[str, Any]] = []
    for source_position, selected_candidate in enumerate(
        selected_event["candidates"],
        start=1,
    ):
        try:
            resolved_name = resolve_candidate_name(
                selected_candidate["name"],
                canonical_names,
            )
            candidate_name = by_name[resolved_name]["candidate_name"]
        except CandidateIdentityError:
            try:
                candidate_name = canonical_candidate_name(
                    selected_candidate["name"]
                )
            except CandidateIdentityError as error:
                raise _error_from_identity(error) from error
        lineup.append(
            {
                "candidate_id": candidate_id(candidate_name),
                "candidate_name": candidate_name,
                "reported_score": selected_candidate["score"],
                "source_position": source_position,
            }
        )

    ordered = sorted(lineup, key=_featured_poll_candidate_sort_key)
    displayed = ordered[:FEATURED_POLL_BOARD_DISPLAY_LIMIT]
    board_candidates = [
        {**candidate, "display_position": display_position}
        for display_position, candidate in enumerate(displayed, start=1)
    ]
    hypothesis = selected_event.get("hypothesis")
    hypothesis_label = (
        hypothesis.strip()
        if isinstance(hypothesis, str) and hypothesis.strip()
        else None
    )
    return {
        "selection_basis": FEATURED_POLL_BOARD_SELECTION_BASIS,
        "pollster": package["pollster"],
        "fieldwork_start": package["fieldwork_start"],
        "fieldwork_end": package["fieldwork_end"],
        "sample_size": package["sample_size"],
        "round": selected_event["round"],
        "scenario_key": selected_event["scenario_key"],
        "selected_event_id": selected_event["event_id"],
        "hypothesis_label": hypothesis_label,
        "package_hypothesis_count": len(package["events"]),
        "source_urls": list(source_urls),
        "full_candidate_count": len(lineup),
        "display_limit": FEATURED_POLL_BOARD_DISPLAY_LIMIT,
        "displayed_candidate_count": len(board_candidates),
        "omitted_candidate_count": len(lineup) - len(board_candidates),
        "candidates": board_candidates,
    }


def _polling_evidence_date(package: dict[str, Any]) -> str:
    publication_dates = [
        _parse_date(
            event["publication_date"],
            "featured package publication_date",
        )
        for event in package["events"]
        if event.get("publication_date") not in (None, "")
    ]
    if publication_dates:
        return max(publication_dates).isoformat()
    return _parse_date(
        package["fieldwork_end"],
        "featured package fieldwork_end",
    ).isoformat()


def _construct_candidate_signals(
    polls: Any,
    news: Any,
    claims: Any,
    candidacy_status: Any,
) -> dict[str, Any]:
    universe, candidates = candidate_universe_from_candidacy_status(
        candidacy_status
    )
    try:
        candidacy_by_id = candidacy_status_by_id(candidacy_status)
        presidential_field = project_display_tiers(candidacy_status)
        active_monitoring_field = project_active_monitoring_field(
            candidacy_status
        )
    except CandidateCandidacyStatusError as error:
        raise CandidateSignalsError(
            f"candidacy-status registry is invalid: {error}"
        ) from error
    featured_package = select_featured_polling_package(polls)
    polling = project_candidate_polling(candidates, featured_package)
    visibility, campaign_attention, general_visibility = project_visibility(
        candidates,
        news,
    )
    active_field_visibility = derive_active_field_visibility(
        news,
        active_monitoring_field,
        candidacy_status,
    )
    scrutiny_window, scrutiny, scrutiny_evidence = project_scrutiny(
        candidates,
        claims,
    )
    news_object = _require_object(news, "news")
    developments, news_evidence = project_latest_developments(
        candidates,
        news_object.get("candidate_watch"),
    )
    if news_evidence is None:
        news_evidence = visibility["current_period"]["end_date"]
    featured_polling_package = _featured_package_public(featured_package)
    featured_poll_board = _featured_poll_board_public(
        featured_package,
        candidates,
        featured_polling_package["source_urls"],
    )

    candidate_payloads = []
    active_candidate_identifiers = set(
        active_monitoring_field["main"]
        + active_monitoring_field["secondary"]
    )
    for candidate in candidates:
        identifier = candidate["candidate_id"]
        source_candidacy = candidacy_by_id[identifier]
        candidate_payloads.append(
            {
                "candidate_id": identifier,
                "candidate_name": candidate["candidate_name"],
                "candidacy": {
                    "status": source_candidacy["status"],
                    "display_tier": source_candidacy["display_tier"],
                    "upstream_presence": source_candidacy.get(
                        "upstream_presence",
                        "present",
                    ),
                    "active_field_eligible": (
                        identifier in active_candidate_identifiers
                    ),
                    "status_as_of": source_candidacy["status_as_of"],
                    "source_date": source_candidacy["source_date"],
                    "source_url": source_candidacy["source_url"],
                    "source_title": source_candidacy["source_title"],
                    "source_publisher": source_candidacy["source_publisher"],
                    "status_note": source_candidacy["status_note"],
                },
                "polling": polling[identifier],
                "campaign_attention": campaign_attention[identifier],
                "general_visibility": general_visibility[identifier],
                "scrutiny": scrutiny[identifier],
                "latest_development": developments[identifier],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_universe": universe,
        "presidential_field": presidential_field,
        "active_monitoring_field": active_monitoring_field,
        "active_field_visibility": active_field_visibility,
        "featured_polling_package": featured_polling_package,
        "featured_poll_board": featured_poll_board,
        "visibility": visibility,
        "scrutiny_window": scrutiny_window,
        "evidence_dates": {
            "polling": _polling_evidence_date(featured_package),
            "news": news_evidence,
            "scrutiny": scrutiny_evidence,
        },
        "candidates": candidate_payloads,
    }


POLLING_OUTPUT_KEYS = {
    "evidence_state",
    "hypothesis_count",
    "range_min",
    "range_max",
    "selected_hypothesis_score",
    "selected_hypothesis_rank",
}
CAMPAIGN_OUTPUT_KEYS = {
    "evidence_state",
    "record_count",
    "share",
    "publisher_count",
    "active_day_count",
    "headline_match_count",
    "summary_only_match_count",
    "scope_counts",
    "scope_shares",
    "story_cluster_count",
    "concentration",
}
GENERAL_OUTPUT_KEYS = CAMPAIGN_OUTPUT_KEYS - {
    "scope_counts",
    "scope_shares",
}
SCRUTINY_COUNT_KEYS = {
    "review_count",
    "by_count",
    "about_count",
    "newest_review_date",
    "newest_review_url",
}
LATEST_DEVELOPMENT_KEYS = {
    "evidence_state",
    "id",
    "published_at",
    "publisher",
    "headline",
    "url",
    "coverage_scope",
}
FEATURED_POLL_BOARD_KEYS = {
    "selection_basis",
    "pollster",
    "fieldwork_start",
    "fieldwork_end",
    "sample_size",
    "round",
    "scenario_key",
    "selected_event_id",
    "hypothesis_label",
    "package_hypothesis_count",
    "source_urls",
    "full_candidate_count",
    "display_limit",
    "displayed_candidate_count",
    "omitted_candidate_count",
    "candidates",
}
FEATURED_POLL_BOARD_CANDIDATE_KEYS = {
    "candidate_id",
    "candidate_name",
    "reported_score",
    "source_position",
    "display_position",
}



def _audit_forbidden_fields(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.casefold().replace("-", "_")
            if any(part in normalized_key for part in FORBIDDEN_FIELD_PARTS):
                raise CandidateSignalsError(
                    f"forbidden interpretive field at {path}.{key}"
                )
            _audit_forbidden_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _audit_forbidden_fields(item, f"{path}[{index}]")


def _validate_projected_metric(
    metric: Any,
    context: str,
    expected_keys: set[str],
) -> None:
    value = _require_object(metric, context)
    if set(value) != expected_keys:
        raise CandidateSignalsError(f"{context} has unexpected fields")
    state = value["evidence_state"]
    metric_fields = expected_keys - {"evidence_state"}
    if state == "not_observed":
        if any(value[field] is not None for field in metric_fields):
            raise CandidateSignalsError(
                f"{context} fabricates values for unobserved evidence"
            )
        return
    if state != "reported":
        raise CandidateSignalsError(f"{context}.evidence_state is invalid")
    for field in (
        "record_count",
        "publisher_count",
        "active_day_count",
        "headline_match_count",
        "summary_only_match_count",
        "story_cluster_count",
    ):
        _require_non_negative_integer(value[field], f"{context}.{field}")
    _ratio(value["share"], f"{context}.share")
    _validate_concentration(
        value["concentration"],
        f"{context}.concentration",
        value["record_count"],
    )
    if "scope_counts" in value:
        counts = _require_object(value["scope_counts"], f"{context}.scope_counts")
        shares = _require_object(value["scope_shares"], f"{context}.scope_shares")
        if set(counts) != set(VISIBILITY_SCOPES) or set(shares) != set(
            VISIBILITY_SCOPES
        ):
            raise CandidateSignalsError(f"{context} scope fields are invalid")
        if counts[GENERAL_SCOPE] != 0:
            raise CandidateSignalsError(
                f"{context} contains general records in primary attention"
            )


def _validate_featured_poll_board(
    value: Any,
    candidates: list[dict[str, Any]],
    featured_package: dict[str, Any],
) -> None:
    board = _require_plain_object(value, "featured_poll_board")
    if set(board) != FEATURED_POLL_BOARD_KEYS:
        raise CandidateSignalsError(
            "featured_poll_board has unexpected fields"
        )
    if board["selection_basis"] != FEATURED_POLL_BOARD_SELECTION_BASIS:
        raise CandidateSignalsError(
            "featured_poll_board.selection_basis is invalid"
        )
    _require_text(board["pollster"], "featured_poll_board.pollster")
    start = _parse_date(
        board["fieldwork_start"],
        "featured_poll_board.fieldwork_start",
    )
    end = _parse_date(
        board["fieldwork_end"],
        "featured_poll_board.fieldwork_end",
    )
    if start > end:
        raise CandidateSignalsError(
            "featured_poll_board fieldwork dates are reversed"
        )
    if board["sample_size"] is not None:
        _require_positive_integer(
            board["sample_size"],
            "featured_poll_board.sample_size",
        )
    if board["round"] != "first_round":
        raise CandidateSignalsError(
            "featured_poll_board.round must equal first_round"
        )
    _require_text(
        board["scenario_key"],
        "featured_poll_board.scenario_key",
    )
    _require_text(
        board["selected_event_id"],
        "featured_poll_board.selected_event_id",
    )
    if board["hypothesis_label"] is not None:
        _require_text(
            board["hypothesis_label"],
            "featured_poll_board.hypothesis_label",
        )
    package_hypothesis_count = _require_positive_integer(
        board["package_hypothesis_count"],
        "featured_poll_board.package_hypothesis_count",
    )
    source_urls = _require_list(
        board["source_urls"],
        "featured_poll_board.source_urls",
    )
    if (
        not source_urls
        or any(not _usable_url(url) for url in source_urls)
        or len(source_urls) != len(set(source_urls))
    ):
        raise CandidateSignalsError(
            "featured_poll_board.source_urls is invalid"
        )

    full_candidate_count = _require_positive_integer(
        board["full_candidate_count"],
        "featured_poll_board.full_candidate_count",
    )
    display_limit = _require_positive_integer(
        board["display_limit"],
        "featured_poll_board.display_limit",
    )
    displayed_candidate_count = _require_non_negative_integer(
        board["displayed_candidate_count"],
        "featured_poll_board.displayed_candidate_count",
    )
    omitted_candidate_count = _require_non_negative_integer(
        board["omitted_candidate_count"],
        "featured_poll_board.omitted_candidate_count",
    )
    board_candidates = _require_list(
        board["candidates"],
        "featured_poll_board.candidates",
    )
    if displayed_candidate_count != len(board_candidates):
        raise CandidateSignalsError(
            "featured_poll_board displayed count does not match candidates"
        )
    if displayed_candidate_count > display_limit:
        raise CandidateSignalsError(
            "featured_poll_board displayed count exceeds display limit"
        )
    if displayed_candidate_count != min(full_candidate_count, display_limit):
        raise CandidateSignalsError(
            "featured_poll_board displayed count does not apply display limit"
        )
    if omitted_candidate_count != (
        full_candidate_count - displayed_candidate_count
    ):
        raise CandidateSignalsError(
            "featured_poll_board omitted count is inconsistent"
        )
    if full_candidate_count != (
        displayed_candidate_count + omitted_candidate_count
    ):
        raise CandidateSignalsError(
            "featured_poll_board full candidate count is inconsistent"
        )

    if (
        board["pollster"] != featured_package["pollster"]
        or board["fieldwork_start"] != featured_package["fieldwork_start"]
        or board["fieldwork_end"] != featured_package["fieldwork_end"]
        or board["sample_size"] != featured_package["sample_size"]
        or package_hypothesis_count != featured_package["hypothesis_count"]
        or board["selected_event_id"]
        != featured_package["selected_hypothesis_event_id"]
        or source_urls != featured_package["source_urls"]
    ):
        raise CandidateSignalsError(
            "featured_poll_board does not match featured polling package"
        )

    dossier_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in candidates
    }

    seen_ids: set[str] = set()
    seen_source_positions: set[int] = set()
    seen_display_positions: set[int] = set()
    validated_rows: list[dict[str, Any]] = []
    for index, candidate_value in enumerate(board_candidates):
        context = f"featured_poll_board.candidates[{index}]"
        candidate = _require_plain_object(candidate_value, context)
        if set(candidate) != FEATURED_POLL_BOARD_CANDIDATE_KEYS:
            raise CandidateSignalsError(f"{context} has unexpected fields")
        identifier = _require_text(
            candidate["candidate_id"],
            f"{context}.candidate_id",
        )
        if identifier in seen_ids:
            raise CandidateSignalsError(
                "featured_poll_board candidate IDs must be unique"
            )
        seen_ids.add(identifier)
        try:
            canonical_name = canonical_candidate_name(
                candidate["candidate_name"]
            )
            expected_identifier = candidate_id(canonical_name)
        except CandidateIdentityError as error:
            raise _error_from_identity(error) from error
        if candidate["candidate_name"] != canonical_name:
            raise CandidateSignalsError(
                f"{context}.candidate_name is not canonical"
            )
        dossier_candidate = dossier_by_id.get(identifier)
        if (
            dossier_candidate is not None
            and dossier_candidate["candidate_name"] != canonical_name
        ):
            raise CandidateSignalsError(
                f"{context}.candidate_name is not canonical"
            )
        if identifier != expected_identifier:
            raise CandidateSignalsError(
                f"{context}.candidate_id is not in main candidates or "
                "does not match a canonical poll-only identity"
            )
        reported_score = _numeric(
            candidate["reported_score"],
            f"{context}.reported_score",
            non_negative=True,
        )
        if dossier_candidate is not None:
            selected_score = dossier_candidate["polling"][
                "selected_hypothesis_score"
            ]
            if selected_score is None or reported_score != selected_score:
                raise CandidateSignalsError(
                    f"{context}.reported_score does not match selected event"
                )
        source_position = _require_positive_integer(
            candidate["source_position"],
            f"{context}.source_position",
        )
        if source_position > full_candidate_count:
            raise CandidateSignalsError(
                f"{context}.source_position exceeds selected event"
            )
        if source_position in seen_source_positions:
            raise CandidateSignalsError(
                "featured_poll_board source positions must be unique"
            )
        seen_source_positions.add(source_position)
        display_position = _require_positive_integer(
            candidate["display_position"],
            f"{context}.display_position",
        )
        if display_position in seen_display_positions:
            raise CandidateSignalsError(
                "featured_poll_board display positions must be unique"
            )
        seen_display_positions.add(display_position)
        validated_rows.append(candidate)

    if [
        candidate["display_position"]
        for candidate in validated_rows
    ] != list(range(1, len(validated_rows) + 1)):
        raise CandidateSignalsError(
            "featured_poll_board display positions are not contiguous"
        )
    if validated_rows != sorted(
        validated_rows,
        key=_featured_poll_candidate_sort_key,
    ):
        raise CandidateSignalsError(
            "featured_poll_board candidates are not correctly ordered"
        )
    omitted_scores = [
        candidate["polling"]["selected_hypothesis_score"]
        for identifier, candidate in dossier_by_id.items()
        if (
            identifier not in seen_ids
            and candidate["polling"]["selected_hypothesis_score"] is not None
        )
    ]
    if (
        validated_rows
        and omitted_scores
        and max(omitted_scores) > validated_rows[-1]["reported_score"]
    ):
        raise CandidateSignalsError(
            "featured_poll_board does not contain the highest scores"
        )


def validate_candidate_signals(
    payload: Any,
    *,
    polls: Any | None = None,
    news: Any | None = None,
    claims: Any | None = None,
    candidacy_status: Any | None = None,
) -> None:
    """Strictly validate structure and, when supplied, source equivalence."""

    value = _require_object(payload, "payload")
    _audit_forbidden_fields(value)
    expected_top_keys = {
        "schema_version",
        "candidate_universe",
        "presidential_field",
        "active_monitoring_field",
        "active_field_visibility",
        "featured_polling_package",
        "featured_poll_board",
        "visibility",
        "scrutiny_window",
        "evidence_dates",
        "candidates",
    }
    if set(value) != expected_top_keys:
        raise CandidateSignalsError("payload has unexpected fields")
    if value["schema_version"] != SCHEMA_VERSION:
        raise CandidateSignalsError("schema_version must equal 1.3")

    universe = _require_object(
        value["candidate_universe"],
        "candidate_universe",
    )
    universe_keys = set(universe)
    current_universe_keys = {"source", "rule", "status_as_of", "count"}
    legacy_universe_keys = {"rule", "as_of_date", "cutoff_date", "count"}
    if universe_keys == current_universe_keys:
        if universe["source"] != CANDIDATE_UNIVERSE_SOURCE:
            raise CandidateSignalsError("candidate_universe.source is invalid")
        _parse_date(
            universe["status_as_of"],
            "candidate_universe.status_as_of",
        )
    elif universe_keys == legacy_universe_keys:
        as_of = _parse_date(
            universe["as_of_date"],
            "candidate_universe.as_of_date",
        )
        cutoff = _parse_date(
            universe["cutoff_date"],
            "candidate_universe.cutoff_date",
        )
        if cutoff != as_of - timedelta(days=183):
            raise CandidateSignalsError(
                "legacy candidate_universe cutoff is invalid"
            )
    else:
        raise CandidateSignalsError(
            "candidate_universe has unexpected fields"
        )
    _require_text(universe["rule"], "candidate_universe.rule")
    count = _require_non_negative_integer(
        universe["count"],
        "candidate_universe.count",
    )

    presidential_field = _require_plain_object(
        value["presidential_field"],
        "presidential_field",
    )
    if set(presidential_field) != PRESIDENTIAL_FIELD_KEYS:
        raise CandidateSignalsError(
            "presidential_field has unexpected fields"
        )
    _parse_date(
        presidential_field["status_as_of"],
        "presidential_field.status_as_of",
    )
    tier_ids: dict[str, list[str]] = {}
    for tier in ("main", "secondary", "hidden"):
        identifiers = _require_list(
            presidential_field[tier],
            f"presidential_field.{tier}",
        )
        if any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        ):
            raise CandidateSignalsError(
                f"presidential_field.{tier} must contain candidate IDs"
            )
        if len(identifiers) != len(set(identifiers)):
            raise CandidateSignalsError(
                f"presidential_field.{tier} candidate IDs must be unique"
            )
        tier_ids[tier] = identifiers
    counts_value = _require_plain_object(
        presidential_field["counts"],
        "presidential_field.counts",
    )
    if set(counts_value) != PRESIDENTIAL_FIELD_COUNT_KEYS:
        raise CandidateSignalsError(
            "presidential_field.counts has unexpected fields"
        )
    field_counts = {
        key: _require_non_negative_integer(
            counts_value[key],
            f"presidential_field.counts.{key}",
        )
        for key in PRESIDENTIAL_FIELD_COUNT_KEYS
    }
    expected_counts = {
        "main": len(tier_ids["main"]),
        "secondary": len(tier_ids["secondary"]),
        "hidden": len(tier_ids["hidden"]),
        "total": sum(len(tier_ids[tier]) for tier in tier_ids),
    }
    if field_counts != expected_counts:
        raise CandidateSignalsError(
            "presidential_field counts do not match tier membership"
        )

    active_monitoring_field = _require_plain_object(
        value["active_monitoring_field"],
        "active_monitoring_field",
    )
    if set(active_monitoring_field) != ACTIVE_MONITORING_FIELD_KEYS:
        raise CandidateSignalsError(
            "active_monitoring_field has unexpected fields"
        )
    active_tier_ids: dict[str, list[str]] = {}
    for tier in ("main", "secondary"):
        identifiers = _require_list(
            active_monitoring_field[tier],
            f"active_monitoring_field.{tier}",
        )
        if any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        ):
            raise CandidateSignalsError(
                f"active_monitoring_field.{tier} must contain candidate IDs"
            )
        if len(identifiers) != len(set(identifiers)):
            raise CandidateSignalsError(
                f"active_monitoring_field.{tier} candidate IDs must be unique"
            )
        active_tier_ids[tier] = identifiers
    if set(active_tier_ids["main"]) & set(active_tier_ids["secondary"]):
        raise CandidateSignalsError(
            "active_monitoring_field candidate IDs appear in multiple tiers"
        )
    active_counts_value = _require_plain_object(
        active_monitoring_field["counts"],
        "active_monitoring_field.counts",
    )
    if set(active_counts_value) != ACTIVE_MONITORING_FIELD_COUNT_KEYS:
        raise CandidateSignalsError(
            "active_monitoring_field.counts has unexpected fields"
        )
    active_counts = {
        key: _require_non_negative_integer(
            active_counts_value[key],
            f"active_monitoring_field.counts.{key}",
        )
        for key in ACTIVE_MONITORING_FIELD_COUNT_KEYS
    }
    expected_active_counts = {
        "main": len(active_tier_ids["main"]),
        "secondary": len(active_tier_ids["secondary"]),
        "active": (
            len(active_tier_ids["main"])
            + len(active_tier_ids["secondary"])
        ),
    }
    if active_counts != expected_active_counts:
        raise CandidateSignalsError(
            "active_monitoring_field counts do not match membership"
        )

    featured = _require_object(
        value["featured_polling_package"],
        "featured_polling_package",
    )
    featured_keys = {
        "package_key",
        "pollster",
        "fieldwork_start",
        "fieldwork_end",
        "sample_size",
        "hypothesis_count",
        "selected_hypothesis_event_id",
        "source_urls",
    }
    if set(featured) != featured_keys:
        raise CandidateSignalsError(
            "featured_polling_package has unexpected fields"
        )
    package_key = _require_text(
        featured["package_key"],
        "featured_polling_package.package_key",
    )
    try:
        parsed_package_key = json.loads(package_key)
    except json.JSONDecodeError as error:
        raise CandidateSignalsError(
            "featured_polling_package.package_key is invalid"
        ) from error
    expected_package_key = [
        featured["pollster"],
        featured["fieldwork_start"],
        featured["fieldwork_end"],
        featured["sample_size"],
    ]
    if parsed_package_key != expected_package_key:
        raise CandidateSignalsError(
            "featured_polling_package.package_key does not match its fields"
        )
    _require_text(featured["pollster"], "featured_polling_package.pollster")
    start = _parse_date(
        featured["fieldwork_start"],
        "featured_polling_package.fieldwork_start",
    )
    end = _parse_date(
        featured["fieldwork_end"],
        "featured_polling_package.fieldwork_end",
    )
    if start > end:
        raise CandidateSignalsError(
            "featured polling fieldwork dates are reversed"
        )
    if featured["sample_size"] is not None:
        _require_non_negative_integer(
            featured["sample_size"],
            "featured_polling_package.sample_size",
        )
    if (
        _require_non_negative_integer(
            featured["hypothesis_count"],
            "featured_polling_package.hypothesis_count",
        )
        == 0
    ):
        raise CandidateSignalsError(
            "featured_polling_package must contain hypotheses"
        )
    _require_text(
        featured["selected_hypothesis_event_id"],
        "featured_polling_package.selected_hypothesis_event_id",
    )
    source_urls = _require_list(
        featured["source_urls"],
        "featured_polling_package.source_urls",
    )
    if (
        not source_urls
        or any(not _usable_url(url) for url in source_urls)
        or len(source_urls) != len(set(source_urls))
    ):
        raise CandidateSignalsError(
            "featured_polling_package.source_urls is invalid"
        )

    visibility = _require_object(value["visibility"], "visibility")
    if set(visibility) != {
        "method",
        "primary_scopes",
        "secondary_scope",
        "current_period",
        "general_current_period",
        "comparison_quality",
    }:
        raise CandidateSignalsError("visibility has unexpected fields")
    _require_text(visibility["method"], "visibility.method")
    if visibility["primary_scopes"] != list(PRIMARY_SCOPES):
        raise CandidateSignalsError("visibility.primary_scopes is invalid")
    if visibility["secondary_scope"] != GENERAL_SCOPE:
        raise CandidateSignalsError("visibility.secondary_scope is invalid")
    for period_name in ("current_period", "general_current_period"):
        period = _require_object(
            visibility[period_name],
            f"visibility.{period_name}",
        )
        if set(period) != {
            "start_date",
            "end_date",
            "record_count",
            "publisher_count",
        }:
            raise CandidateSignalsError(
                f"visibility.{period_name} has unexpected fields"
            )
        period_start = _parse_date(
            period["start_date"],
            f"visibility.{period_name}.start_date",
        )
        period_end = _parse_date(
            period["end_date"],
            f"visibility.{period_name}.end_date",
        )
        if period_start > period_end or (period_end - period_start).days != 6:
            raise CandidateSignalsError(
                f"visibility.{period_name} must span seven days"
            )
        _require_non_negative_integer(
            period["record_count"],
            f"visibility.{period_name}.record_count",
        )
        _require_non_negative_integer(
            period["publisher_count"],
            f"visibility.{period_name}.publisher_count",
        )
    quality = _require_object(
        visibility["comparison_quality"],
        "visibility.comparison_quality",
    )
    if set(quality) != QUALITY_KEYS:
        raise CandidateSignalsError(
            "visibility.comparison_quality has unexpected fields"
        )

    scrutiny_window = _require_object(
        value["scrutiny_window"],
        "scrutiny_window",
    )
    if set(scrutiny_window) != {
        "latest_days",
        "latest_start_date",
        "latest_end_date",
        "archive_window_days",
    }:
        raise CandidateSignalsError("scrutiny_window has unexpected fields")
    if scrutiny_window["latest_days"] != LATEST_SCRUTINY_DAYS:
        raise CandidateSignalsError("scrutiny_window.latest_days is invalid")
    scrutiny_start = _parse_date(
        scrutiny_window["latest_start_date"],
        "scrutiny_window.latest_start_date",
    )
    scrutiny_end = _parse_date(
        scrutiny_window["latest_end_date"],
        "scrutiny_window.latest_end_date",
    )
    if scrutiny_start != scrutiny_end - timedelta(
        days=LATEST_SCRUTINY_DAYS - 1
    ):
        raise CandidateSignalsError("scrutiny_window boundaries are invalid")
    _require_non_negative_integer(
        scrutiny_window["archive_window_days"],
        "scrutiny_window.archive_window_days",
    )

    evidence_dates = _require_object(
        value["evidence_dates"],
        "evidence_dates",
    )
    if set(evidence_dates) != {"polling", "news", "scrutiny"}:
        raise CandidateSignalsError("evidence_dates has unexpected fields")
    _parse_date(evidence_dates["polling"], "evidence_dates.polling")
    _parse_date(evidence_dates["news"], "evidence_dates.news")
    if evidence_dates["scrutiny"] is not None:
        _parse_date(
            evidence_dates["scrutiny"],
            "evidence_dates.scrutiny",
        )

    candidates = _require_list(value["candidates"], "candidates")
    if len(candidates) != count:
        raise CandidateSignalsError(
            "candidate_universe.count does not match candidates"
        )
    identity_names: list[str] = []
    expected_order: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for index, candidate_value in enumerate(candidates):
        context = f"candidates[{index}]"
        candidate = _require_object(candidate_value, context)
        if set(candidate) != {
            "candidate_id",
            "candidate_name",
            "candidacy",
            "polling",
            "campaign_attention",
            "general_visibility",
            "scrutiny",
            "latest_development",
        }:
            raise CandidateSignalsError(f"{context} has unexpected fields")
        try:
            name = canonical_candidate_name(candidate["candidate_name"])
            identifier = candidate_id(name)
        except CandidateIdentityError as error:
            raise _error_from_identity(error) from error
        if candidate["candidate_id"] != identifier:
            raise CandidateSignalsError(
                f"{context}.candidate_id does not match candidate_name"
            )
        if identifier in seen_ids:
            raise CandidateSignalsError("candidate IDs must be unique")
        seen_ids.add(identifier)
        identity_names.append(name)
        expected_order.append((name.casefold(), identifier))

        candidacy = _require_plain_object(
            candidate["candidacy"],
            f"{context}.candidacy",
        )
        if set(candidacy) != CANDIDACY_OUTPUT_KEYS:
            raise CandidateSignalsError(
                f"{context}.candidacy has unexpected fields"
            )
        for field in (
            "status",
            "display_tier",
            "source_title",
            "source_publisher",
            "status_note",
        ):
            _require_text(candidacy[field], f"{context}.candidacy.{field}")
        if candidacy["display_tier"] not in {"main", "secondary", "hidden"}:
            raise CandidateSignalsError(
                f"{context}.candidacy.display_tier is invalid"
            )
        if candidacy["upstream_presence"] not in {
            "present",
            "temporarily_missing",
        }:
            raise CandidateSignalsError(
                f"{context}.candidacy.upstream_presence is invalid"
            )
        if type(candidacy["active_field_eligible"]) is not bool:
            raise CandidateSignalsError(
                f"{context}.candidacy.active_field_eligible must be boolean"
            )
        _parse_date(
            candidacy["status_as_of"],
            f"{context}.candidacy.status_as_of",
        )
        _parse_date(
            candidacy["source_date"],
            f"{context}.candidacy.source_date",
        )
        if not _usable_url(candidacy["source_url"]):
            raise CandidateSignalsError(
                f"{context}.candidacy.source_url is invalid"
            )

        polling = _require_object(candidate["polling"], f"{context}.polling")
        if set(polling) != POLLING_OUTPUT_KEYS:
            raise CandidateSignalsError(
                f"{context}.polling has unexpected fields"
            )
        polling_state = polling["evidence_state"]
        polling_fields = POLLING_OUTPUT_KEYS - {"evidence_state"}
        if polling_state in {"not_observed", "not_tested"}:
            if any(polling[field] is not None for field in polling_fields):
                raise CandidateSignalsError(
                    f"{context}.polling fabricates an unobserved value"
                )
        elif polling_state == "reported":
            if (
                type(polling["hypothesis_count"]) is not int
                or polling["hypothesis_count"] <= 0
            ):
                raise CandidateSignalsError(
                    f"{context}.polling.hypothesis_count is invalid"
                )
            low = _numeric(
                polling["range_min"],
                f"{context}.polling.range_min",
                non_negative=True,
            )
            high = _numeric(
                polling["range_max"],
                f"{context}.polling.range_max",
                non_negative=True,
            )
            if low > high:
                raise CandidateSignalsError(
                    f"{context}.polling range is reversed"
                )
            selected_score = polling["selected_hypothesis_score"]
            selected_rank = polling["selected_hypothesis_rank"]
            if (selected_score is None) != (selected_rank is None):
                raise CandidateSignalsError(
                    f"{context}.polling selected score/rank must align"
                )
            if selected_score is not None:
                _numeric(
                    selected_score,
                    f"{context}.polling.selected_hypothesis_score",
                    non_negative=True,
                )
                if type(selected_rank) is not int or selected_rank <= 0:
                    raise CandidateSignalsError(
                        f"{context}.polling selected rank is invalid"
                    )
        else:
            raise CandidateSignalsError(
                f"{context}.polling.evidence_state is invalid"
            )

        _validate_projected_metric(
            candidate["campaign_attention"],
            f"{context}.campaign_attention",
            CAMPAIGN_OUTPUT_KEYS,
        )
        _validate_projected_metric(
            candidate["general_visibility"],
            f"{context}.general_visibility",
            GENERAL_OUTPUT_KEYS,
        )

        scrutiny = _require_object(candidate["scrutiny"], f"{context}.scrutiny")
        if set(scrutiny) != {"latest_14_days", "archive"}:
            raise CandidateSignalsError(
                f"{context}.scrutiny has unexpected fields"
            )
        for window_name in ("latest_14_days", "archive"):
            window = _require_object(
                scrutiny[window_name],
                f"{context}.scrutiny.{window_name}",
            )
            if set(window) != SCRUTINY_COUNT_KEYS:
                raise CandidateSignalsError(
                    f"{context}.scrutiny.{window_name} has unexpected fields"
                )
            for field in ("review_count", "by_count", "about_count"):
                _require_non_negative_integer(
                    window[field],
                    f"{context}.scrutiny.{window_name}.{field}",
                )
            if window["review_count"] != window["by_count"] + window["about_count"]:
                raise CandidateSignalsError(
                    f"{context}.scrutiny.{window_name} counts are inconsistent"
                )
            newest_date = window["newest_review_date"]
            newest_url = window["newest_review_url"]
            if window["review_count"] == 0:
                if newest_date is not None or newest_url is not None:
                    raise CandidateSignalsError(
                        f"{context}.scrutiny.{window_name} has unsupported "
                        "newest-review evidence"
                    )
            else:
                _parse_date(
                    newest_date,
                    f"{context}.scrutiny.{window_name}.newest_review_date",
                )
                if not _usable_url(newest_url):
                    raise CandidateSignalsError(
                        f"{context}.scrutiny.{window_name}.newest_review_url "
                        "is invalid"
                    )

        development = _require_object(
            candidate["latest_development"],
            f"{context}.latest_development",
        )
        if set(development) != LATEST_DEVELOPMENT_KEYS:
            raise CandidateSignalsError(
                f"{context}.latest_development has unexpected fields"
            )
        development_fields = LATEST_DEVELOPMENT_KEYS - {"evidence_state"}
        if development["evidence_state"] == "none":
            if any(development[field] is not None for field in development_fields):
                raise CandidateSignalsError(
                    f"{context}.latest_development fabricates evidence"
                )
        elif development["evidence_state"] == "reported":
            for field in ("id", "published_at", "publisher", "headline"):
                _require_text(
                    development[field],
                    f"{context}.latest_development.{field}",
                )
            _parse_timestamp(
                development["published_at"],
                f"{context}.latest_development.published_at",
            )
            if not _usable_url(development["url"]):
                raise CandidateSignalsError(
                    f"{context}.latest_development.url is invalid"
                )
            if development["coverage_scope"] not in PRIMARY_SCOPES:
                raise CandidateSignalsError(
                    f"{context}.latest_development scope is not campaign-relevant"
                )
        else:
            raise CandidateSignalsError(
                f"{context}.latest_development.evidence_state is invalid"
            )

    try:
        candidate_identity_map(identity_names)
    except CandidateIdentityError as error:
        raise _error_from_identity(error) from error
    if expected_order != sorted(expected_order):
        raise CandidateSignalsError(
            "candidates are not deterministically ordered"
        )
    all_tier_ids = [
        identifier
        for tier in ("main", "secondary", "hidden")
        for identifier in tier_ids[tier]
    ]
    if len(all_tier_ids) != len(set(all_tier_ids)):
        raise CandidateSignalsError(
            "presidential_field candidate IDs appear in multiple tiers"
        )
    unknown_tier_ids = sorted(set(all_tier_ids) - seen_ids)
    missing_tier_ids = sorted(seen_ids - set(all_tier_ids))
    if unknown_tier_ids:
        raise CandidateSignalsError(
            f"presidential_field has unknown candidate IDs: {unknown_tier_ids}"
        )
    if missing_tier_ids:
        raise CandidateSignalsError(
            f"presidential_field is missing candidate IDs: {missing_tier_ids}"
        )
    if field_counts["total"] != count:
        raise CandidateSignalsError(
            "presidential_field total does not match candidate universe"
        )
    tier_by_id = {
        identifier: tier
        for tier in ("main", "secondary", "hidden")
        for identifier in tier_ids[tier]
    }
    for index, candidate in enumerate(candidates):
        if candidate["candidacy"]["display_tier"] != tier_by_id[
            candidate["candidate_id"]
        ]:
            raise CandidateSignalsError(
                f"candidates[{index}].candidacy tier conflicts with "
                "presidential_field"
            )
    active_ids_in_order = (
        active_tier_ids["main"] + active_tier_ids["secondary"]
    )
    active_id_set = set(active_ids_in_order)
    unknown_active_ids = sorted(active_id_set - seen_ids)
    if unknown_active_ids:
        raise CandidateSignalsError(
            "active_monitoring_field has unknown candidate IDs: "
            f"{unknown_active_ids}"
        )
    for tier in ("main", "secondary"):
        expected_tier_order = [
            candidate["candidate_id"]
            for candidate in candidates
            if (
                candidate["candidacy"]["display_tier"] == tier
                and candidate["candidacy"]["active_field_eligible"]
            )
        ]
        if active_tier_ids[tier] != expected_tier_order:
            raise CandidateSignalsError(
                f"active_monitoring_field.{tier} membership or order is invalid"
            )
    for index, candidate in enumerate(candidates):
        identifier = candidate["candidate_id"]
        candidacy = candidate["candidacy"]
        expected_eligible = identifier in active_id_set
        if candidacy["active_field_eligible"] != expected_eligible:
            raise CandidateSignalsError(
                f"candidates[{index}].candidacy active eligibility conflicts "
                "with active_monitoring_field"
            )
        if expected_eligible and (
            candidacy["display_tier"] not in {"main", "secondary"}
            or candidacy["upstream_presence"] != "present"
        ):
            raise CandidateSignalsError(
                f"candidates[{index}] is not eligible for active monitoring"
            )
    validate_active_field_visibility(
        value["active_field_visibility"],
        active_monitoring_field,
        candidates,
        presidential_field["status_as_of"],
    )
    _validate_featured_poll_board(
        value["featured_poll_board"],
        candidates,
        featured,
    )

    supplied = (
        polls is not None,
        news is not None,
        claims is not None,
        candidacy_status is not None,
    )
    if any(supplied) and not all(supplied):
        raise CandidateSignalsError(
            "polls, news, claims, and candidacy_status must all be supplied "
            "for source validation"
        )
    if all(supplied):
        expected = _construct_candidate_signals(
            polls,
            news,
            claims,
            candidacy_status,
        )
        if value != expected:
            raise CandidateSignalsError(
                "candidate signals payload does not match source evidence"
            )


def build_candidate_signals(
    polls: Any,
    news: Any,
    claims: Any,
    candidacy_status: Any,
) -> dict[str, Any]:
    """Construct and strictly validate one Candidate Signals payload."""

    payload = _construct_candidate_signals(
        polls,
        news,
        claims,
        candidacy_status,
    )
    validate_candidate_signals(payload)
    return payload


def serialize_candidate_signals(payload: Any) -> bytes:
    """Return the canonical UTF-8 public serialization."""

    validate_candidate_signals(payload)
    return (
        json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n"
    ).encode("utf-8")


def atomic_write(path: Path | str, content: bytes) -> None:
    """Atomically replace a target only after complete content is available."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def build_from_paths(
    polls_path: Path | str = "polls.json",
    news_path: Path | str = "news_wire.json",
    claims_path: Path | str = "claims_under_scrutiny.json",
    candidacy_status_path: Path | str = "candidate_candidacy_status.json",
    output_path: Path | str = "candidate_signals.json",
) -> dict[str, Any]:
    """Load, construct, source-validate, serialize, and atomically write."""

    polls, news, claims, candidacy_status = load_inputs(
        polls_path,
        news_path,
        claims_path,
        candidacy_status_path,
    )
    payload = build_candidate_signals(
        polls,
        news,
        claims,
        candidacy_status,
    )
    validate_candidate_signals(
        payload,
        polls=polls,
        news=news,
        claims=claims,
        candidacy_status=candidacy_status,
    )
    content = serialize_candidate_signals(payload)
    atomic_write(output_path, content)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic Candidate Signals data",
    )
    parser.add_argument("--polls", default="polls.json")
    parser.add_argument("--news", default="news_wire.json")
    parser.add_argument(
        "--claims",
        default="claims_under_scrutiny.json",
    )
    parser.add_argument(
        "--candidacy-status",
        default="candidate_candidacy_status.json",
    )
    parser.add_argument("--output", default="candidate_signals.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        payload = build_from_paths(
            arguments.polls,
            arguments.news,
            arguments.claims,
            arguments.candidacy_status,
            arguments.output,
        )
    except CandidateSignalsError as error:
        raise SystemExit(f"Candidate Signals build failed: {error}") from None
    print(
        "Candidate Signals: "
        f"{payload['candidate_universe']['count']} candidates; "
        f"featured {payload['featured_polling_package']['pollster']} "
        f"with {payload['featured_polling_package']['hypothesis_count']} "
        f"hypotheses; wrote {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
