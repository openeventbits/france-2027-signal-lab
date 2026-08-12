"""Strict, deterministic normalization for manually curated Campaign Events."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from campaign_event_attribution import (
    CandidateAttributionConfigurationError,
    match_active_candidate_participants,
)
from campaign_event_sources import (
    CAMPAIGN_EVENT_TYPES,
    CampaignEventSourceRegistryError,
    manual_evidence_source_id,
    normalize_https_url,
)
from campaign_events_contract import (
    CampaignEventsContractError,
    campaign_event_id,
    normalize_campaign_event_observations,
)

__all__ = [
    "CampaignEventsManualError",
    "load_campaign_events_manual",
    "normalize_campaign_events_manual",
    "validate_campaign_events_manual",
]


class CampaignEventsManualError(ValueError):
    """Raised when the manual Campaign Events input violates its contract."""


SCHEMA_VERSION = "1.0"
TIMEZONE = "Europe/Paris"
_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name("campaign_event_sources.json")
_PARIS = ZoneInfo(TIMEZONE)
_UTC = timezone.utc
_TOP_LEVEL_KEYS = frozenset({"schema_version", "events"})
_REQUIRED_EVENT_KEYS = frozenset(
    {
        "event_key",
        "title",
        "date",
        "event_type",
        "source_url",
        "source_publisher",
        "source_type",
        "last_verified_at",
    }
)
_OPTIONAL_EVENT_KEYS = frozenset(
    {
        "time",
        "participants",
        "organization",
        "location_name",
        "locality",
        "department",
        "status",
    }
)
_EVENT_KEY = re.compile(r"manual-[0-9a-f]{32}\Z", re.ASCII)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_TIME = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z", re.ASCII)
_UTC_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
    re.ASCII,
)
_STATUSES = frozenset({"scheduled", "postponed", "cancelled", "completed"})


def _fail(message: str) -> None:
    raise CampaignEventsManualError(message)


def _require_exact_keys(
    value: dict[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing or unexpected:
        _fail(
            f"{context} must have exact allowed keys; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _normalize_text(value: Any, context: str) -> str:
    if not isinstance(value, str):
        _fail(f"{context} must be text")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not normalized:
        _fail(f"{context} must be non-empty text")
    return normalized


def _require_date(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        _fail(f"{context} must be a canonical YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CampaignEventsManualError(f"{context} must be a valid date") from error
    if parsed.isoformat() != value:
        _fail(f"{context} must be a canonical date")
    return value


def _require_time(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        _fail(f"{context} must be a canonical local HH:MM time")
    return value


def _require_utc_timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{context} must be a canonical UTC timestamp ending in Z")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_UTC)
    except ValueError as error:
        raise CampaignEventsManualError(
            f"{context} must be a valid UTC timestamp"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(f"{context} must be a canonical UTC timestamp")
    return value


def _scheduled_start(
    date_value: str,
    time_value: str | None,
    *,
    context: str,
) -> tuple[str, str]:
    if time_value is None:
        return date_value, "date"

    naive = datetime.fromisoformat(f"{date_value}T{time_value}:00")
    valid: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=_PARIS, fold=fold)
        round_trip = candidate.astimezone(_UTC).astimezone(_PARIS)
        if round_trip.replace(tzinfo=None) == naive:
            valid.append(candidate)
    if not valid:
        _fail(f"{context} is a nonexistent Europe/Paris local time")
    if len({candidate.utcoffset() for candidate in valid}) > 1:
        _fail(f"{context} is an ambiguous Europe/Paris local time")
    return valid[0].isoformat(timespec="seconds"), "datetime"


def _normalize_participants(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        _fail(f"{context} must be a list")
    participants = [
        _normalize_text(participant, f"{context}[{index}]")
        for index, participant in enumerate(value)
    ]
    if len(set(participants)) != len(participants):
        _fail(f"{context} must not contain duplicates")
    return participants


def _is_past_scheduled(
    scheduled_start: str,
    time_precision: str,
    last_verified_at: str,
) -> bool:
    verified = datetime.strptime(
        last_verified_at,
        "%Y-%m-%dT%H:%M:%SZ",
    ).replace(tzinfo=_UTC)
    if time_precision == "date":
        return date.fromisoformat(scheduled_start) < verified.astimezone(_PARIS).date()
    return datetime.fromisoformat(scheduled_start) < verified.astimezone(_PARIS)


def _normalize_event(
    value: Any,
    *,
    index: int,
    candidate_registry_path: str | Path,
) -> dict[str, Any]:
    context = f"events[{index}]"
    if type(value) is not dict:
        _fail(f"{context} must be a plain dict")
    _require_exact_keys(
        value,
        _REQUIRED_EVENT_KEYS,
        _OPTIONAL_EVENT_KEYS,
        context,
    )

    event_key = value["event_key"]
    if not isinstance(event_key, str) or not _EVENT_KEY.fullmatch(event_key):
        _fail(f"{context}.event_key must be manual- plus 32 lowercase hex characters")
    title = _normalize_text(value["title"], f"{context}.title")
    date_value = _require_date(value["date"], f"{context}.date")
    time_value = None
    if "time" in value:
        time_value = _require_time(value["time"], f"{context}.time")
    scheduled_start, time_precision = _scheduled_start(
        date_value,
        time_value,
        context=f"{context}.time",
    )

    event_type = value["event_type"]
    if not isinstance(event_type, str) or event_type not in CAMPAIGN_EVENT_TYPES:
        _fail(f"{context}.event_type is not in the Campaign Events vocabulary")
    status = value.get("status", "scheduled")
    if not isinstance(status, str) or status not in _STATUSES:
        _fail(f"{context}.status is not allowed")
    last_verified_at = _require_utc_timestamp(
        value["last_verified_at"],
        f"{context}.last_verified_at",
    )

    participants = _normalize_participants(
        value.get("participants", []),
        f"{context}.participants",
    )
    try:
        candidate_pairs = match_active_candidate_participants(
            participants,
            candidate_registry_path=candidate_registry_path,
        )
    except CandidateAttributionConfigurationError as error:
        raise CampaignEventsManualError(
            f"{context} candidate linkage failed: {error}"
        ) from error

    source_publisher = _normalize_text(
        value["source_publisher"],
        f"{context}.source_publisher",
    )
    try:
        source_url = normalize_https_url(
            value["source_url"],
            f"{context}.source_url",
        )
        source_id = manual_evidence_source_id(
            value["source_type"],
            source_publisher,
            source_url,
        )
    except CampaignEventSourceRegistryError as error:
        raise CampaignEventsManualError(str(error)) from error

    evidence_type = (
        "explicit_schedule" if status == "scheduled" else "explicit_status_update"
    )
    evidence_status = (
        "past_unconfirmed"
        if status == "scheduled"
        and _is_past_scheduled(scheduled_start, time_precision, last_verified_at)
        else "verified"
    )
    event: dict[str, Any] = {
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "event_type": event_type,
        "title": title,
        "candidate_ids": [candidate_id for candidate_id, _ in candidate_pairs],
        "candidate_names": [candidate_name for _, candidate_name in candidate_pairs],
        "scheduled_start": scheduled_start,
        "time_precision": time_precision,
        "timezone": TIMEZONE,
        "status": status,
        "status_as_of": last_verified_at[:10],
        "evidence_status": evidence_status,
        "last_verified_at": last_verified_at,
        "evidence": [
            {
                "source_id": source_id,
                "source_url": source_url,
                "source_publisher": source_publisher,
                "source_type": value["source_type"],
                "evidence_type": evidence_type,
            }
        ],
    }
    if participants:
        event["participants"] = participants
    for field in ("organization", "location_name", "locality"):
        if field in value:
            event[field] = _normalize_text(value[field], f"{context}.{field}")
    if "department" in value:
        event["department"] = value["department"]
    return event


def normalize_campaign_events_manual(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> list[dict[str, Any]]:
    """Return deterministic publication-compatible manual Campaign Events."""

    if type(payload) is not dict:
        _fail("payload must be a plain dict")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, frozenset(), "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version must be exactly '1.0'")
    events = payload["events"]
    if not isinstance(events, list):
        _fail("events must be a list")

    raw_events = [
        _normalize_event(
            event,
            index=index,
            candidate_registry_path=candidate_registry_path,
        )
        for index, event in enumerate(events)
    ]
    try:
        return normalize_campaign_event_observations(
            raw_events,
            candidate_registry_path=candidate_registry_path,
            source_registry_path=source_registry_path,
        )
    except CampaignEventsContractError as error:
        raise CampaignEventsManualError(
            f"manual Campaign Event is invalid: {error}"
        ) from error


def validate_campaign_events_manual(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> None:
    """Validate manual input without requiring its human facts to be pre-sorted."""

    normalize_campaign_events_manual(
        payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )


def load_campaign_events_manual(
    path: str | Path,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> list[dict[str, Any]]:
    """Load one UTF-8 manual source file and return normalized event records."""

    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise CampaignEventsManualError(
            f"could not read manual Campaign Events input {target}: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CampaignEventsManualError(
            f"manual Campaign Events input {target} is malformed JSON: {error}"
        ) from error
    return normalize_campaign_events_manual(
        payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
