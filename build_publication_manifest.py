"""Build the static dashboard publication manifest.

The manifest records publication time separately from lane-local generation,
check, and evidence timestamps.  It is intentionally dependency-free so the
data workflows can run it after their existing validation steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from build_candidate_signals import (
    CandidateSignalsError,
    derive_active_field_visibility,
    validate_candidate_signals,
)
from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    active_candidate_ids,
    active_candidate_names,
    active_candidate_records,
    candidacy_status_by_id,
    project_active_monitoring_field,
    project_display_tiers,
    semantic_sha256 as candidacy_semantic_sha256,
    validate_candidate_candidacy_status,
)
from candidate_attention_contract import (
    CandidateAttentionContractError,
    validate_candidate_attention,
)
from campaign_events_contract import (
    CampaignEventsContractError,
    validate_campaign_events_artifact,
)
from fetch_claims_under_scrutiny import (
    CollectorError as ClaimsCollectorError,
    validate_public_bundle as validate_claims_bundle,
)
from source_health import (
    SourceHealthError,
    source_health_aggregate,
    validate_source_health,
)


SCHEMA_VERSION = "1.3"
OUTPUT_NAME = "publication_manifest.json"
TIMESTAMP_STATUSES = {"known", "unknown", "missing", "invalid"}
LANE_FILES = {
    "candidacy_status": ("candidate_candidacy_status.json",),
    "campaign_events": ("campaign_events.json",),
    "candidate_attention": ("candidate_attention.json",),
    "candidate_signals": ("candidate_signals.json",),
    "claims": ("claims_under_scrutiny.json",),
    "news": ("news_wire.json",),
    "polls": ("polls.json",),
    "recent_changes": ("recent_changes.json",),
    "runoff": (
        "second_round_polls.json",
        "closest_tested_runoff.json",
    ),
    "source_health": ("source_health.json",),
}
SOURCE_NETWORK_FIELDS = (
    "approved_publisher_domains",
    "configured_media_publishers",
    "configured_routes_or_feeds",
    "routes_due_in_run",
    "successful_due_routes",
    "contributing_publishers_in_retained_period",
    "publishers_represented_in_accepted_election_news",
)
SOURCE_HEALTH_FIELDS = (
    "configured_routes",
    "attempted_routes",
    "successful_routes",
    "failed_routes",
    "repeated_failure_routes",
    "healthy_zero_yield_routes",
    "recovered_routes",
)


class ManifestError(ValueError):
    """Raised when the manifest itself cannot satisfy its contract."""


def _utc_timestamp(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a UTC ISO-8601 timestamp")

    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError(
            f"{field} must be a UTC ISO-8601 timestamp"
        ) from error

    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ManifestError(f"{field} must include a UTC offset")

    normalized = parsed.astimezone(timezone.utc).isoformat()
    return normalized.replace("+00:00", "Z")


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_source_bytes(content: bytes) -> bytes:
    """Return repository publication bytes with platform newlines normalized."""

    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _read_source(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "byte_size": None,
        "sha256": None,
        "payload": None,
        "error": None,
    }
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        result["error"] = f"{path.name} is missing"
        return result
    except OSError as error:
        result["error"] = f"{path.name} could not be read: {error}"
        return result

    # Byte metadata stays canonical even when UTF-8 or JSON validation fails.
    canonical_content = _canonical_source_bytes(content)
    result["available"] = True
    result["byte_size"] = len(canonical_content)
    result["sha256"] = _sha256(canonical_content)
    try:
        result["payload"] = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        result["error"] = f"{path.name} is malformed JSON: {error}"
    return result


def _schema_version(payload: Any) -> Any:
    if isinstance(payload, dict):
        return payload.get("schema_version")
    return None


def _calendar_date(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a valid calendar date")
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError as error:
        raise ManifestError(
            f"{field} must be a valid calendar date"
        ) from error
    return parsed.date().isoformat()


def _required_object(
    value: Any,
    *,
    field: str,
    keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ManifestError(f"{field} has an invalid structure")
    return value


def _required_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be non-empty text")
    return value.strip()


def _required_count(value: Any, *, field: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise ManifestError(f"{field} must be a non-negative integer")
    return value


def _absolute_http_url(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _validate_featured_poll_board_public(
    value: Any,
    *,
    candidates_by_id: dict[str, str],
    featured_package: dict[str, Any],
) -> None:
    board = _required_object(
        value,
        field="candidate_signals.featured_poll_board",
        keys={
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
        },
    )
    if board["selection_basis"] != (
        "featured_package_selected_hypothesis"
    ):
        raise ManifestError(
            "candidate_signals.featured_poll_board selection_basis is invalid"
        )
    _required_text(
        board["pollster"],
        field="candidate_signals.featured_poll_board.pollster",
    )
    start = _calendar_date(
        board["fieldwork_start"],
        field="candidate_signals.featured_poll_board.fieldwork_start",
    )
    end = _calendar_date(
        board["fieldwork_end"],
        field="candidate_signals.featured_poll_board.fieldwork_end",
    )
    if start > end:
        raise ManifestError(
            "candidate_signals.featured_poll_board dates are reversed"
        )
    if board["sample_size"] is not None and _required_count(
        board["sample_size"],
        field="candidate_signals.featured_poll_board.sample_size",
    ) == 0:
        raise ManifestError(
            "candidate_signals.featured_poll_board sample_size must be positive"
        )
    if board["round"] != "first_round":
        raise ManifestError(
            "candidate_signals.featured_poll_board round is invalid"
        )
    for field in ("scenario_key", "selected_event_id"):
        _required_text(
            board[field],
            field=f"candidate_signals.featured_poll_board.{field}",
        )
    if board["hypothesis_label"] is not None:
        _required_text(
            board["hypothesis_label"],
            field="candidate_signals.featured_poll_board.hypothesis_label",
        )
    package_count = _required_count(
        board["package_hypothesis_count"],
        field="candidate_signals.featured_poll_board.package_hypothesis_count",
    )
    if package_count == 0:
        raise ManifestError(
            "candidate_signals.featured_poll_board package count must be positive"
        )
    source_urls = board["source_urls"]
    if (
        not isinstance(source_urls, list)
        or not source_urls
        or any(not _absolute_http_url(url) for url in source_urls)
        or len(source_urls) != len(set(source_urls))
    ):
        raise ManifestError(
            "candidate_signals.featured_poll_board source_urls are invalid"
        )

    full_count = _required_count(
        board["full_candidate_count"],
        field="candidate_signals.featured_poll_board.full_candidate_count",
    )
    display_limit = _required_count(
        board["display_limit"],
        field="candidate_signals.featured_poll_board.display_limit",
    )
    displayed_count = _required_count(
        board["displayed_candidate_count"],
        field="candidate_signals.featured_poll_board.displayed_candidate_count",
    )
    omitted_count = _required_count(
        board["omitted_candidate_count"],
        field="candidate_signals.featured_poll_board.omitted_candidate_count",
    )
    board_candidates = board["candidates"]
    if full_count == 0 or display_limit == 0:
        raise ManifestError(
            "candidate_signals.featured_poll_board counts must be positive"
        )
    if not isinstance(board_candidates, list):
        raise ManifestError(
            "candidate_signals.featured_poll_board.candidates must be an array"
        )
    if displayed_count != len(board_candidates):
        raise ManifestError(
            "candidate_signals.featured_poll_board displayed count is invalid"
        )
    if displayed_count > display_limit:
        raise ManifestError(
            "candidate_signals.featured_poll_board exceeds display limit"
        )
    if displayed_count != min(full_count, display_limit):
        raise ManifestError(
            "candidate_signals.featured_poll_board did not apply display limit"
        )
    if omitted_count != full_count - displayed_count:
        raise ManifestError(
            "candidate_signals.featured_poll_board omitted count is invalid"
        )

    if (
        board["pollster"] != featured_package["pollster"]
        or board["fieldwork_start"] != featured_package["fieldwork_start"]
        or board["fieldwork_end"] != featured_package["fieldwork_end"]
        or board["sample_size"] != featured_package["sample_size"]
        or package_count != featured_package["hypothesis_count"]
        or board["selected_event_id"]
        != featured_package["selected_hypothesis_event_id"]
        or source_urls != featured_package["source_urls"]
    ):
        raise ManifestError(
            "candidate_signals.featured_poll_board does not match package"
        )

    seen_ids: set[str] = set()
    source_positions: set[int] = set()
    rows: list[tuple[float, int, str, int]] = []
    for index, candidate in enumerate(board_candidates):
        row = _required_object(
            candidate,
            field=f"candidate_signals.featured_poll_board.candidates[{index}]",
            keys={
                "candidate_id",
                "candidate_name",
                "reported_score",
                "source_position",
                "display_position",
            },
        )
        identifier = _required_text(
            row["candidate_id"],
            field=f"candidate_signals.featured_poll_board.candidates[{index}].candidate_id",
        )
        if identifier in seen_ids:
            raise ManifestError(
                "candidate_signals featured board candidate IDs must be unique"
            )
        seen_ids.add(identifier)
        if identifier not in candidates_by_id:
            raise ManifestError(
                "candidate_signals featured board candidate ID is unknown"
            )
        if row["candidate_name"] != candidates_by_id[identifier]:
            raise ManifestError(
                "candidate_signals featured board candidate name is not canonical"
            )
        score = row["reported_score"]
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
        ):
            raise ManifestError(
                "candidate_signals featured board score must be finite numeric"
            )
        source_position = _required_count(
            row["source_position"],
            field=f"candidate_signals.featured_poll_board.candidates[{index}].source_position",
        )
        display_position = _required_count(
            row["display_position"],
            field=f"candidate_signals.featured_poll_board.candidates[{index}].display_position",
        )
        if source_position == 0 or source_position in source_positions:
            raise ManifestError(
                "candidate_signals featured board source positions are invalid"
            )
        source_positions.add(source_position)
        rows.append((float(score), source_position, identifier, display_position))

    if [row[3] for row in rows] != list(range(1, len(rows) + 1)):
        raise ManifestError(
            "candidate_signals featured board display positions are not contiguous"
        )
    if rows != sorted(rows, key=lambda row: (-row[0], row[1], row[2])):
        raise ManifestError(
            "candidate_signals featured board scores are not correctly ordered"
        )


def _validate_candidate_signals_public(payload: Any) -> int:
    schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
    if schema_version == "1.3":
        try:
            validate_candidate_signals(payload)
        except CandidateSignalsError as error:
            raise ManifestError(
                f"candidate_signals invalid structure: {error}"
            ) from error
        return payload["candidate_universe"]["count"]
    if schema_version != "1.2":
        raise ManifestError(
            "candidate_signals.schema_version must equal 1.2 or 1.3"
        )

    # Temporary migration compatibility for the tracked schema-1.2 artifact.
    value = _required_object(
        payload,
        field="candidate_signals",
        keys={
            "schema_version",
            "candidate_universe",
            "presidential_field",
            "active_field_visibility",
            "featured_polling_package",
            "featured_poll_board",
            "visibility",
            "scrutiny_window",
            "evidence_dates",
            "candidates",
        },
    )
    universe = _required_object(
        value["candidate_universe"],
        field="candidate_signals.candidate_universe",
        keys={"rule", "as_of_date", "cutoff_date", "count"},
    )
    _required_text(
        universe["rule"],
        field="candidate_signals.candidate_universe.rule",
    )
    as_of_date = _calendar_date(
        universe["as_of_date"],
        field="candidate_signals.candidate_universe.as_of_date",
    )
    cutoff_date = _calendar_date(
        universe["cutoff_date"],
        field="candidate_signals.candidate_universe.cutoff_date",
    )
    if cutoff_date > as_of_date:
        raise ManifestError(
            "candidate_signals.candidate_universe cutoff follows as-of date"
        )
    candidate_count = _required_count(
        universe["count"],
        field="candidate_signals.candidate_universe.count",
    )

    featured = _required_object(
        value["featured_polling_package"],
        field="candidate_signals.featured_polling_package",
        keys={
            "package_key",
            "pollster",
            "fieldwork_start",
            "fieldwork_end",
            "sample_size",
            "hypothesis_count",
            "selected_hypothesis_event_id",
            "source_urls",
        },
    )
    for field in (
        "package_key",
        "pollster",
        "selected_hypothesis_event_id",
    ):
        _required_text(
            featured[field],
            field=f"candidate_signals.featured_polling_package.{field}",
        )
    featured_start = _calendar_date(
        featured["fieldwork_start"],
        field="candidate_signals.featured_polling_package.fieldwork_start",
    )
    featured_end = _calendar_date(
        featured["fieldwork_end"],
        field="candidate_signals.featured_polling_package.fieldwork_end",
    )
    if featured_start > featured_end:
        raise ManifestError(
            "candidate_signals.featured_polling_package dates are reversed"
        )
    if featured["sample_size"] is not None:
        _required_count(
            featured["sample_size"],
            field="candidate_signals.featured_polling_package.sample_size",
        )
    if _required_count(
        featured["hypothesis_count"],
        field=(
            "candidate_signals.featured_polling_package.hypothesis_count"
        ),
    ) == 0:
        raise ManifestError(
            "candidate_signals.featured_polling_package must have hypotheses"
        )
    source_urls = featured["source_urls"]
    if (
        not isinstance(source_urls, list)
        or not source_urls
        or any(
            not isinstance(url, str) or not url.strip()
            for url in source_urls
        )
        or len(source_urls) != len(set(source_urls))
    ):
        raise ManifestError(
            "candidate_signals featured source_urls are invalid"
        )

    visibility = _required_object(
        value["visibility"],
        field="candidate_signals.visibility",
        keys={
            "method",
            "primary_scopes",
            "secondary_scope",
            "current_period",
            "general_current_period",
            "comparison_quality",
        },
    )
    _required_text(
        visibility["method"],
        field="candidate_signals.visibility.method",
    )
    primary_scopes = visibility["primary_scopes"]
    if (
        not isinstance(primary_scopes, list)
        or not primary_scopes
        or any(
            not isinstance(scope, str) or not scope.strip()
            for scope in primary_scopes
        )
        or len(primary_scopes) != len(set(primary_scopes))
    ):
        raise ManifestError(
            "candidate_signals.visibility.primary_scopes is invalid"
        )
    _required_text(
        visibility["secondary_scope"],
        field="candidate_signals.visibility.secondary_scope",
    )
    for period_name in ("current_period", "general_current_period"):
        period = _required_object(
            visibility[period_name],
            field=f"candidate_signals.visibility.{period_name}",
            keys={
                "start_date",
                "end_date",
                "record_count",
                "publisher_count",
            },
        )
        period_start = _calendar_date(
            period["start_date"],
            field=(
                f"candidate_signals.visibility.{period_name}.start_date"
            ),
        )
        period_end = _calendar_date(
            period["end_date"],
            field=f"candidate_signals.visibility.{period_name}.end_date",
        )
        if period_start > period_end:
            raise ManifestError(
                f"candidate_signals.visibility.{period_name} dates "
                "are reversed"
            )
        for count_name in ("record_count", "publisher_count"):
            _required_count(
                period[count_name],
                field=(
                    f"candidate_signals.visibility.{period_name}."
                    f"{count_name}"
                ),
            )
    comparison_quality = visibility["comparison_quality"]
    if not isinstance(comparison_quality, dict):
        raise ManifestError(
            "candidate_signals.visibility.comparison_quality "
            "must be an object"
        )
    _required_text(
        comparison_quality.get("status"),
        field="candidate_signals.visibility.comparison_quality.status",
    )

    scrutiny = _required_object(
        value["scrutiny_window"],
        field="candidate_signals.scrutiny_window",
        keys={
            "latest_days",
            "latest_start_date",
            "latest_end_date",
            "archive_window_days",
        },
    )
    if _required_count(
        scrutiny["latest_days"],
        field="candidate_signals.scrutiny_window.latest_days",
    ) == 0:
        raise ManifestError(
            "candidate_signals.scrutiny_window.latest_days must be positive"
        )
    scrutiny_start = _calendar_date(
        scrutiny["latest_start_date"],
        field="candidate_signals.scrutiny_window.latest_start_date",
    )
    scrutiny_end = _calendar_date(
        scrutiny["latest_end_date"],
        field="candidate_signals.scrutiny_window.latest_end_date",
    )
    if scrutiny_start > scrutiny_end:
        raise ManifestError(
            "candidate_signals.scrutiny_window dates are reversed"
        )
    _required_count(
        scrutiny["archive_window_days"],
        field="candidate_signals.scrutiny_window.archive_window_days",
    )

    evidence_dates = _required_object(
        value["evidence_dates"],
        field="candidate_signals.evidence_dates",
        keys={"polling", "news", "scrutiny"},
    )
    for field in ("polling", "news"):
        _calendar_date(
            evidence_dates[field],
            field=f"candidate_signals.evidence_dates.{field}",
        )
    if evidence_dates["scrutiny"] is not None:
        _calendar_date(
            evidence_dates["scrutiny"],
            field="candidate_signals.evidence_dates.scrutiny",
        )

    candidates = value["candidates"]
    if not isinstance(candidates, list):
        raise ManifestError("candidate_signals.candidates must be an array")
    if candidate_count != len(candidates):
        raise ManifestError(
            "candidate_signals candidate count does not match candidates"
        )
    candidate_ids: set[str] = set()
    candidates_by_id: dict[str, str] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ManifestError(
                f"candidate_signals.candidates[{index}] must be an object"
            )
        candidate_id = _required_text(
            candidate.get("candidate_id"),
            field=f"candidate_signals.candidates[{index}].candidate_id",
        )
        candidate_name = _required_text(
            candidate.get("candidate_name"),
            field=f"candidate_signals.candidates[{index}].candidate_name",
        )
        if candidate_id in candidate_ids:
            raise ManifestError(
                "candidate_signals candidate IDs must be unique"
            )
        candidate_ids.add(candidate_id)
        candidates_by_id[candidate_id] = candidate_name
    _validate_featured_poll_board_public(
        value["featured_poll_board"],
        candidates_by_id=candidates_by_id,
        featured_package=featured,
    )
    return candidate_count


def _validate_candidacy_status_public(payload: Any) -> int:
    try:
        validate_candidate_candidacy_status(payload)
    except CandidateCandidacyStatusError as error:
        raise ManifestError(
            f"candidacy_status invalid structure: {error}"
        ) from error
    return len(payload["candidates"])



def _validate_candidate_attention_public(payload: Any) -> int:
    """Validate the intrinsic Candidate Attention artifact contract."""

    try:
        validate_candidate_attention(payload)
    except CandidateAttentionContractError as error:
        raise ManifestError(
            f"candidate_attention invalid structure: {error}"
        ) from error

    return len(payload["candidates"])


def _validate_candidate_attention_parity(
    registry: Any,
    candidate_attention: Any,
) -> None:
    """Require schema-1.1 Attention parity with the canonical active field."""

    try:
        attention_schema = candidate_attention.get("schema_version")
        if attention_schema == "1.0":
            if not isinstance(registry, dict) or not isinstance(
                registry.get("candidates"), list
            ):
                raise CandidateAttentionContractError(
                    "controlled candidacy candidate list is unavailable"
                )
            expected_candidates = registry["candidates"]
        else:
            validate_candidate_candidacy_status(registry)
            expected_candidates = active_candidate_records(registry)
        validate_candidate_attention(
            candidate_attention,
            expected_candidates=expected_candidates,
        )
    except (CandidateCandidacyStatusError, CandidateAttentionContractError) as error:
        raise ManifestError(
            f"candidate_attention candidacy parity failed: {error}"
        ) from error


def _validate_candidacy_status_parity(
    registry: Any,
    candidate_signals: Any,
) -> None:
    candidates = candidate_signals["candidates"]
    universe = [
        {
            "candidate_id": candidate["candidate_id"],
            "candidate_name": candidate["candidate_name"],
        }
        for candidate in candidates
    ]
    try:
        validate_candidate_candidacy_status(
            registry,
            candidate_universe=universe,
        )
        registry_by_id = candidacy_status_by_id(registry)
        expected_field = project_display_tiers(registry)
        expected_active = project_active_monitoring_field(registry)
        active_ids = set(active_candidate_ids(registry))
    except CandidateCandidacyStatusError as error:
        raise ManifestError(
            f"candidacy_status registry parity failed: {error}"
        ) from error

    schema_version = candidate_signals.get("schema_version")
    if schema_version == "1.2":
        expected_field = {
            **expected_field,
            "counts": {
                **expected_field["counts"],
                "active": len(active_ids),
            },
        }
    if candidate_signals["presidential_field"] != expected_field:
        raise ManifestError(
            "candidate_signals presidential_field does not match registry"
        )
    if schema_version == "1.3" and (
        candidate_signals.get("active_monitoring_field") != expected_active
    ):
        raise ManifestError(
            "candidate_signals active_monitoring_field does not match registry"
        )

    for candidate in candidates:
        source = registry_by_id[candidate["candidate_id"]]
        expected_candidacy = {
            "status": source["status"],
            "display_tier": source["display_tier"],
            "active_field_eligible": candidate["candidate_id"] in active_ids,
            "status_as_of": source["status_as_of"],
            "source_date": source["source_date"],
            "source_url": source["source_url"],
            "source_title": source["source_title"],
            "source_publisher": source["source_publisher"],
            "status_note": source["status_note"],
        }
        if schema_version == "1.3":
            expected_candidacy["upstream_presence"] = source.get(
                "upstream_presence", "present"
            )
        if candidate["candidacy"] != expected_candidacy:
            raise ManifestError(
                "candidate_signals candidacy does not match registry for "
                f"{candidate['candidate_id']}"
            )


def _validate_claims_public(payload: Any, registry: Any | None = None) -> int:
    if not isinstance(payload, dict) or payload.get("schema_version") not in {1, 2}:
        raise ManifestError("claims.schema_version must equal integer 1 or 2")
    if payload.get("schema_version") == 1:
        reviews = payload.get("reviews")
        if not isinstance(reviews, list):
            raise ManifestError("claims.reviews must be an array")
        return len(reviews)
    try:
        validate_claims_bundle(
            payload,
            candidacy_payload=registry,
        )
    except ClaimsCollectorError as error:
        raise ManifestError(f"claims invalid structure: {error}") from error
    return len(payload["reviews"])


def _validate_news_active_parity(registry: Any, news: Any) -> None:
    roster = news.get("candidate_roster") if isinstance(news, dict) else None
    if not isinstance(roster, dict):
        return
    if roster.get("source") != "candidate_candidacy_status.json":
        # Legacy tracked News metadata remains valid during migration.
        return
    expected_names = active_candidate_names(registry)
    if (
        roster.get("rule") != "active_monitoring_field"
        or roster.get("status_as_of") != registry["status_as_of"]
        or roster.get("count") != len(expected_names)
        or roster.get("names") != expected_names
    ):
        raise ManifestError("news candidate roster does not match active registry")


def _validate_campaign_event_identity_parity(registry: Any, events: Any) -> None:
    registry_ids = set(candidacy_status_by_id(registry))
    if not isinstance(events, dict):
        return
    for field in ("campaign_events", "institutional_milestones"):
        for index, record in enumerate(events.get(field, [])):
            candidate_ids = record.get("candidate_ids", [])
            if any(identifier not in registry_ids for identifier in candidate_ids):
                raise ManifestError(
                    f"{field}[{index}] references a candidate outside the registry"
                )


def _validate_active_field_visibility_parity(
    registry: Any,
    candidate_signals: Any,
    news: Any,
) -> None:
    try:
        expected = derive_active_field_visibility(
            news,
            project_active_monitoring_field(registry),
            registry,
        )
        if candidate_signals.get("schema_version") == "1.2":
            expected["denominator_scope"] = (
                "records_linked_to_at_least_one_main_or_secondary_candidate"
            )
    except CandidateSignalsError as error:
        raise ManifestError(
            f"candidate_signals active visibility source validation failed: {error}"
        ) from error
    if candidate_signals["active_field_visibility"] != expected:
        raise ManifestError(
            "candidate_signals active_field_visibility does not match news evidence"
        )


def _parse_evidence_value(value: Any) -> tuple[datetime, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        if "T" not in candidate:
            parsed = datetime.strptime(candidate, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            return parsed, parsed.date().isoformat()

        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        parsed = parsed.astimezone(timezone.utc)
        return parsed, parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _maximum_evidence(
    values: Iterable[Any],
) -> tuple[str | None, int]:
    valid: list[tuple[datetime, str]] = []
    invalid_count = 0
    for value in values:
        parsed = _parse_evidence_value(value)
        if parsed is None:
            invalid_count += 1
        else:
            valid.append(parsed)
    if not valid:
        return None, invalid_count
    return max(valid, key=lambda item: item[0])[1], invalid_count


def _timestamp_fields(
    lane_name: str,
    payload: Any,
    warnings: list[str],
) -> tuple[dict[str, str], str]:
    if lane_name == "polls":
        return {}, "unknown"
    if lane_name == "candidacy_status":
        return {}, "known"
    if not isinstance(payload, dict):
        return {}, "invalid"

    field_map = (
        (("generated_at", "generated_at"),)
        if lane_name != "recent_changes"
        else (
            ("generated_at", "generated_at"),
            ("last_successful_check_at", "last_success_at"),
        )
    )
    timestamps: dict[str, str] = {}
    invalid = False
    supplied = False
    for source_field, manifest_field in field_map:
        value = payload.get(source_field)
        if value is None:
            continue
        supplied = True
        try:
            timestamps[manifest_field] = _utc_timestamp(
                value,
                field=f"{lane_name}.{manifest_field}",
            )
        except ManifestError:
            invalid = True
            warnings.append(
                f"{lane_name}: {source_field} is not a valid UTC timestamp"
            )

    if invalid:
        return timestamps, "invalid"
    if timestamps:
        return timestamps, "known"
    return timestamps, "unknown" if not supplied else "invalid"


def _structurally_valid(lane_name: str, sources: list[dict[str, Any]]) -> bool:
    if any(source["payload"] is None for source in sources):
        return False

    payload = sources[0]["payload"]
    if lane_name == "candidacy_status":
        _validate_candidacy_status_public(payload)
        return True
    if lane_name == "candidate_attention":
        try:
            validate_candidate_attention(payload)
        except CandidateAttentionContractError:
            return False
        return True
    if lane_name == "candidate_signals":
        _validate_candidate_signals_public(payload)
        return True
    if lane_name == "claims":
        try:
            _validate_claims_public(payload)
        except ManifestError:
            return False
        return True
    if lane_name == "campaign_events":
        try:
            validate_campaign_events_artifact(payload)
        except CampaignEventsContractError:
            return False
        return True
    if lane_name == "polls":
        return isinstance(payload, list) and all(
            isinstance(item, dict) for item in payload
        )
    if not isinstance(payload, dict):
        return False
    if lane_name == "source_health":
        try:
            validate_source_health(payload)
        except SourceHealthError:
            return False
        return True
    if lane_name == "runoff":
        related = sources[1]["payload"]
        return (
            isinstance(payload.get("events"), list)
            and all(isinstance(item, dict) for item in payload["events"])
            and isinstance(related, dict)
        )
    required_list = {
        "news": "election_news",
        "claims": "reviews",
        "recent_changes": "items",
    }[lane_name]
    return isinstance(payload.get(required_list), list) and all(
        isinstance(item, dict) for item in payload[required_list]
    )


def _evidence_values(lane_name: str, payload: Any) -> list[Any]:
    if lane_name == "candidacy_status":
        return [payload["status_as_of"]]
    if lane_name == "candidate_attention":
        return [payload["period"]["data_as_of"]]
    if lane_name == "candidate_signals":
        evidence_dates = payload["evidence_dates"]
        return [
            evidence_dates["polling"],
            evidence_dates["news"],
        ] + (
            [evidence_dates["scrutiny"]]
            if evidence_dates["scrutiny"] is not None
            else []
        )
    if lane_name == "campaign_events":
        return [payload["data_as_of"]]
    if lane_name == "polls":
        return [item.get("fieldwork_end") for item in payload]
    if lane_name == "runoff":
        return [
            item.get("fieldwork_end")
            for item in payload.get("events", [])
        ]
    if lane_name == "claims":
        return [
            item.get("review_date")
            for item in payload.get("reviews", [])
        ]
    if lane_name == "recent_changes":
        return [
            item.get("trusted_change_at")
            for item in payload.get("items", [])
        ]
    if lane_name == "news":
        values: list[Any] = []
        for list_name in (
            "election_news",
            "notable_developments",
            "relevant_news",
            "candidate_watch",
        ):
            items = payload.get(list_name, [])
            if isinstance(items, list):
                values.extend(
                    item.get("published_at")
                    for item in items
                    if isinstance(item, dict)
                )
        return values
    if lane_name == "source_health":
        current_run = payload.get("current_run", {})
        return [current_run.get("run_at")]
    raise AssertionError(f"unsupported lane: {lane_name}")


def _build_lane(
    root: Path,
    lane_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    file_names = LANE_FILES[lane_name]
    sources = [_read_source(root / file_name) for file_name in file_names]
    if lane_name in {
        "candidacy_status",
        "candidate_attention",
        "candidate_signals",
    }:
        source_error = sources[0]["error"]
        if source_error is not None:
            raise ManifestError(source_error)
    lane_warnings = [
        source["error"] for source in sources if source["error"] is not None
    ]
    available = all(source["available"] for source in sources)
    valid = available and _structurally_valid(lane_name, sources)
    if available and not valid and not lane_warnings:
        lane_warnings.append(
            f"{lane_name}: payload does not match the expected lane structure"
        )

    primary = sources[0]
    lane: dict[str, Any] = {
        "file": file_names[0],
        "available": available,
        "valid": valid,
        "sha256": primary["sha256"],
        "schema_version": _schema_version(primary["payload"]),
        "data_as_of": None,
        "timestamp_status": (
            "missing"
            if not available
            else "invalid"
            if not valid
            else "unknown"
        ),
        "warnings": lane_warnings,
    }
    if lane_name == "campaign_events":
        lane["byte_size"] = primary["byte_size"]
    if len(file_names) > 1:
        lane["related_files"] = [
            {
                "file": file_name,
                "available": source["available"],
                "sha256": source["sha256"],
            }
            for file_name, source in zip(file_names[1:], sources[1:])
        ]

    if valid:
        timestamp_fields, timestamp_status = _timestamp_fields(
            lane_name,
            primary["payload"],
            lane_warnings,
        )
        lane.update(timestamp_fields)
        lane["timestamp_status"] = timestamp_status
        lane["data_as_of"], invalid_count = _maximum_evidence(
            _evidence_values(lane_name, primary["payload"])
        )
        if invalid_count:
            lane_warnings.append(
                f"{lane_name}: ignored {invalid_count} invalid or missing "
                "evidence timestamp"
                + ("" if invalid_count == 1 else "s")
            )
        if lane["data_as_of"] is None:
            lane_warnings.append(
                f"{lane_name}: no valid lane-local evidence date is available"
            )
        if lane_name == "candidacy_status":
            registry = primary["payload"]
            candidates = registry["candidates"]
            tiers = project_display_tiers(registry)
            active = active_candidate_records(registry)
            source = registry.get("source", {})
            lane.update(
                {
                    "record_count": len(candidates),
                    "semantic_sha256": candidacy_semantic_sha256(registry),
                    "status_as_of": registry["status_as_of"],
                    "candidate_total": len(candidates),
                    "main_total": tiers["counts"]["main"],
                    "secondary_total": tiers["counts"]["secondary"],
                    "hidden_total": tiers["counts"]["hidden"],
                    "active_total": len(active),
                    "temporarily_missing_total": sum(
                        candidate.get("upstream_presence") == "temporarily_missing"
                        for candidate in candidates
                    ),
                    "wikipedia_revision_id": source.get("revision_id"),
                    "wikipedia_revision_timestamp": source.get("revision_timestamp"),
                    "canonical_source_url": source.get("page_url"),
                }
            )
        if lane_name == "candidate_attention":
            attention = primary["payload"]
            lane["record_count"] = len(attention["candidates"])
            if attention.get("schema_version") == "1.1":
                lane.update(
                    {
                        "candidate_count": attention["validation"]["candidate_count"],
                        "observed_candidate_count": attention["validation"]["observed_candidate_count"],
                        "unavailable_candidate_count": attention["validation"]["unavailable_candidate_count"],
                    }
                )
        if lane_name == "candidate_signals":
            lane["record_count"] = primary["payload"][
                "candidate_universe"
            ]["count"]
        if lane_name == "campaign_events":
            lane["record_count"] = sum(
                len(primary["payload"][field])
                for field in ("campaign_events", "institutional_milestones")
            )
        if lane_name == "claims":
            claims = primary["payload"]
            lane["record_count"] = len(claims["reviews"])
            if claims.get("schema_version") == 2:
                query = claims["candidate_query"]
                lane.update(
                    {
                        "candidate_query_source": query["source"],
                        "candidate_query_rule": query["rule"],
                        "candidate_query_status_as_of": query["status_as_of"],
                        "candidate_query_count": query["count"],
                    }
                )

    return lane, sources


def _non_negative_integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _source_network(news_payload: Any) -> dict[str, int | None]:
    metrics = {field: None for field in SOURCE_NETWORK_FIELDS}
    if not isinstance(news_payload, dict):
        return metrics

    discovery = news_payload.get("discovery")
    coverage = news_payload.get("feed_coverage")
    if not isinstance(discovery, dict):
        discovery = {}
    if not isinstance(coverage, dict):
        coverage = {}

    metrics.update(
        {
            "approved_publisher_domains": _non_negative_integer(
                discovery.get("approved_publisher_domains")
            ),
            "configured_media_publishers": _non_negative_integer(
                coverage.get("configured_media_publishers")
            ),
            "configured_routes_or_feeds": _non_negative_integer(
                coverage.get("configured_feeds")
            ),
            "routes_due_in_run": _non_negative_integer(
                coverage.get("feeds_due_this_run")
            ),
            "successful_due_routes": _non_negative_integer(
                coverage.get("feeds_successful_this_run")
            ),
            "contributing_publishers_in_retained_period": (
                _non_negative_integer(
                    coverage.get("contributing_publishers_30d")
                )
            ),
        }
    )

    election_news = news_payload.get("election_news")
    if isinstance(election_news, list):
        publishers = {
            item["publisher"].strip()
            for item in election_news
            if isinstance(item, dict)
            and isinstance(item.get("publisher"), str)
            and item["publisher"].strip()
        }
        metrics[
            "publishers_represented_in_accepted_election_news"
        ] = len(publishers)
    return metrics


def _source_health_metrics(
    source_health_payload: Any,
) -> dict[str, int | None]:
    if not isinstance(source_health_payload, dict):
        return {field: None for field in SOURCE_HEALTH_FIELDS}
    try:
        return source_health_aggregate(source_health_payload)
    except SourceHealthError:
        return {field: None for field in SOURCE_HEALTH_FIELDS}


def _snapshot_id(
    lane_sources: dict[str, list[dict[str, Any]]],
) -> str:
    content_hashes = {
        lane_name: [
            {
                "file": file_name,
                "sha256": source["sha256"],
            }
            for file_name, source in zip(
                LANE_FILES[lane_name],
                lane_sources[lane_name],
            )
        ]
        for lane_name in sorted(lane_sources)
    }
    serialized = json.dumps(
        content_hashes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_manifest(
    root: Path | str = ".",
    *,
    published_at: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    normalized_published_at = _utc_timestamp(
        published_at or _now_utc(),
        field="published_at",
    )
    lanes: dict[str, dict[str, Any]] = {}
    lane_sources: dict[str, list[dict[str, Any]]] = {}
    for lane_name in sorted(LANE_FILES):
        lane, sources = _build_lane(root_path, lane_name)
        lanes[lane_name] = lane
        lane_sources[lane_name] = sources

    _validate_candidacy_status_parity(
        lane_sources["candidacy_status"][0]["payload"],
        lane_sources["candidate_signals"][0]["payload"],
    )

    candidate_attention_payload = (
        lane_sources["candidate_attention"][0]["payload"]
    )

    # Intrinsic Stage 2 validation and contemporaneous cross-lane
    # identity parity are deliberately separate publication checks.
    _validate_candidate_attention_public(
        candidate_attention_payload
    )
    _validate_candidate_attention_parity(
        lane_sources["candidacy_status"][0]["payload"],
        candidate_attention_payload,
    )

    registry_payload = lane_sources["candidacy_status"][0]["payload"]
    if lanes["claims"]["valid"]:
        _validate_claims_public(
            lane_sources["claims"][0]["payload"],
            registry_payload,
        )
    if lanes["news"]["valid"]:
        _validate_news_active_parity(
            registry_payload,
            lane_sources["news"][0]["payload"],
        )
    if lanes["campaign_events"]["valid"]:
        _validate_campaign_event_identity_parity(
            registry_payload,
            lane_sources["campaign_events"][0]["payload"],
        )

    warnings = [
        warning
        for lane_name in sorted(lanes)
        for warning in lanes[lane_name]["warnings"]
    ]
    news_payload = (
        lane_sources["news"][0]["payload"]
        if lanes["news"]["valid"]
        else None
    )
    if news_payload is not None:
        _validate_active_field_visibility_parity(
            lane_sources["candidacy_status"][0]["payload"],
            lane_sources["candidate_signals"][0]["payload"],
            news_payload,
        )
    source_health_payload = (
        lane_sources["source_health"][0]["payload"]
        if lanes["source_health"]["valid"]
        else None
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": _snapshot_id(lane_sources),
        "published_at": normalized_published_at,
        "lanes": lanes,
        "source_network": _source_network(news_payload),
        "source_health": _source_health_metrics(source_health_payload),
        "warnings": warnings,
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("schema_version must equal 1.3")
    snapshot_id = manifest.get("snapshot_id")
    if (
        not isinstance(snapshot_id, str)
        or len(snapshot_id) != 64
        or any(character not in "0123456789abcdef" for character in snapshot_id)
    ):
        raise ManifestError("snapshot_id must be a full lowercase SHA-256")
    _utc_timestamp(manifest.get("published_at"), field="published_at")

    lanes = manifest.get("lanes")
    if not isinstance(lanes, dict) or set(lanes) != set(LANE_FILES):
        raise ManifestError("manifest lanes do not match the version 1.3 contract")
    for lane_name, lane in lanes.items():
        if not isinstance(lane, dict):
            raise ManifestError(f"{lane_name} lane must be an object")
        for field in (
            "file",
            "available",
            "valid",
            "sha256",
            "schema_version",
            "data_as_of",
            "timestamp_status",
            "warnings",
        ):
            if field not in lane:
                raise ManifestError(f"{lane_name} lane is missing {field}")
        if lane["timestamp_status"] not in TIMESTAMP_STATUSES:
            raise ManifestError(
                f"{lane_name} has an invalid timestamp_status"
            )
        if not isinstance(lane["warnings"], list):
            raise ManifestError(f"{lane_name} warnings must be an array")
        if lane_name == "candidacy_status" and lane["valid"]:
            for field in (
                "semantic_sha256",
                "status_as_of",
                "candidate_total",
                "main_total",
                "secondary_total",
                "hidden_total",
                "active_total",
                "temporarily_missing_total",
                "wikipedia_revision_id",
                "wikipedia_revision_timestamp",
                "canonical_source_url",
            ):
                if field not in lane:
                    raise ManifestError(f"candidacy_status lane is missing {field}")
            for field in (
                "candidate_total",
                "main_total",
                "secondary_total",
                "hidden_total",
                "active_total",
                "temporarily_missing_total",
            ):
                _required_count(lane[field], field=f"candidacy_status lane {field}")
            if lane["candidate_total"] != (
                lane["main_total"] + lane["secondary_total"] + lane["hidden_total"]
            ):
                raise ManifestError("candidacy_status tier totals do not reconcile")
            semantic = lane["semantic_sha256"]
            if not isinstance(semantic, str) or not re.fullmatch(r"[0-9a-f]{64}", semantic):
                raise ManifestError("candidacy_status semantic_sha256 is invalid")
        if lane_name == "candidate_attention" and lane["valid"] and lane["schema_version"] == "1.1":
            for field in (
                "candidate_count",
                "observed_candidate_count",
                "unavailable_candidate_count",
            ):
                _required_count(lane.get(field), field=f"candidate_attention lane {field}")
            if lane["candidate_count"] != (
                lane["observed_candidate_count"] + lane["unavailable_candidate_count"]
            ):
                raise ManifestError("candidate_attention validation counts do not reconcile")
        if lane_name in {
            "candidacy_status",
            "candidate_attention",
            "candidate_signals",
        }:
            _required_count(
                lane.get("record_count"),
                field=f"{lane_name} lane record_count",
            )
        if lane_name == "claims" and lane["valid"] and lane["schema_version"] == 2:
            for field in (
                "candidate_query_source",
                "candidate_query_rule",
                "candidate_query_status_as_of",
                "candidate_query_count",
            ):
                if field not in lane:
                    raise ManifestError(f"claims lane is missing {field}")
            _required_count(
                lane["candidate_query_count"],
                field="claims lane candidate_query_count",
            )
            if lane["candidate_query_source"] != "candidate_candidacy_status.json":
                raise ManifestError("claims lane candidate query source is invalid")
            if lane["candidate_query_rule"] != "active_monitoring_field":
                raise ManifestError("claims lane candidate query rule is invalid")
        if lane_name == "campaign_events":
            if lane["available"]:
                _required_count(
                    lane.get("byte_size"),
                    field="campaign_events lane byte_size",
                )
            elif lane.get("byte_size") is not None:
                raise ManifestError(
                    "campaign_events lane byte_size must be null when missing"
                )
            if lane["valid"]:
                _required_count(
                    lane.get("record_count"),
                    field="campaign_events lane record_count",
                )

    network = manifest.get("source_network")
    if not isinstance(network, dict) or set(network) != set(
        SOURCE_NETWORK_FIELDS
    ):
        raise ManifestError("source_network does not match the version 1 contract")
    if any(
        value is not None
        and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        )
        for value in network.values()
    ):
        raise ManifestError(
            "source_network metrics must be non-negative integers or null"
        )
    health = manifest.get("source_health")
    if not isinstance(health, dict) or set(health) != set(
        SOURCE_HEALTH_FIELDS
    ):
        raise ManifestError(
            "source_health does not match the version 1 contract"
        )
    if any(
        value is not None
        and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        )
        for value in health.values()
    ):
        raise ManifestError(
            "source_health metrics must be non-negative integers or null"
        )
    if not isinstance(manifest.get("warnings"), list):
        raise ManifestError("warnings must be an array")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build publication_manifest.json version 1.3"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="build and validate in memory without writing the manifest",
    )
    parser.add_argument(
        "--published-at",
        help="coherent snapshot publication time as a UTC ISO-8601 timestamp",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        manifest = build_manifest(
            Path.cwd(),
            published_at=arguments.published_at,
        )
        if not arguments.check:
            atomic_write_json(Path.cwd() / OUTPUT_NAME, manifest)
    except ManifestError as error:
        print(f"publication manifest error: {error}")
        return 1

    action = "validated" if arguments.check else "wrote"
    print(
        f"{action} {OUTPUT_NAME} "
        f"(snapshot {manifest['snapshot_id']})"
    )
    for warning in manifest["warnings"]:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
