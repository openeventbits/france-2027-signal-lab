"""Strict, deterministic normalization for manually curated Event Watch updates."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from campaign_event_sources import (
    CampaignEventSourceRegistryError,
    manual_evidence_source_id,
    normalize_https_url,
)
from campaign_events_contract import campaign_event_id
from campaign_events_manual import (
    CampaignEventsManualError,
    load_campaign_events_manual,
    normalize_campaign_events_manual,
)

__all__ = [
    "CampaignEventUpdatesManualError",
    "campaign_event_update_id",
    "load_campaign_event_updates_manual",
    "normalize_campaign_event_updates_manual",
    "validate_campaign_event_updates_manual",
]


class CampaignEventUpdatesManualError(ValueError):
    """Raised when the manual Event Watch input violates its contract."""


SCHEMA_VERSION = "1.0"
_DEFAULT_MANUAL_EVENTS = Path(__file__).with_name("campaign_events_manual.json")
_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name("campaign_event_sources.json")
_TOP_LEVEL_KEYS = frozenset({"schema_version", "updates"})
_UPDATE_KEYS = frozenset(
    {
        "update_key",
        "event_key",
        "update_type",
        "headline",
        "source_url",
        "source_publisher",
        "source_type",
        "observed_at",
    }
)
_UPDATE_KEY = re.compile(r"update-[0-9a-f]{32}\Z", re.ASCII)
_UTC_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
    re.ASCII,
)
_UPDATE_TYPES = frozenset(
    {"NEW", "CONFIRMED", "UPDATED", "POSTPONED", "CANCELLED"}
)
_ALLOWED_EVENT_STATUSES = {
    "NEW": frozenset({"scheduled"}),
    "CONFIRMED": frozenset({"scheduled"}),
    "UPDATED": frozenset({"scheduled", "postponed", "cancelled"}),
    "POSTPONED": frozenset({"scheduled", "postponed"}),
    "CANCELLED": frozenset({"scheduled", "cancelled"}),
}
_UTC = timezone.utc


def _fail(message: str) -> None:
    raise CampaignEventUpdatesManualError(message)


def _require_exact_keys(
    value: dict[str, Any],
    required: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    if missing or unexpected:
        _fail(
            f"{context} must have exact required keys; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _normalize_text(value: Any, context: str) -> str:
    if not isinstance(value, str):
        _fail(f"{context} must be text")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not normalized:
        _fail(f"{context} must be non-empty text")
    return normalized


def _require_utc_timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{context} must be a canonical UTC timestamp ending in Z")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_UTC
        )
    except ValueError as error:
        raise CampaignEventUpdatesManualError(
            f"{context} must be a valid UTC timestamp"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(f"{context} must be a canonical UTC timestamp")
    return value


def campaign_event_update_id(update_key: str) -> str:
    """Return the version-1 public ID for one immutable Event Watch key."""

    if not isinstance(update_key, str) or not _UPDATE_KEY.fullmatch(update_key):
        _fail("update_key must be update- plus 32 lowercase hex characters")
    identity = f"campaign-event-watch:v1\0{update_key}".encode("utf-8")
    return "cew-" + hashlib.sha256(identity).hexdigest()[:24]


def _load_manual_event_index(
    manual_events_path: str | Path,
    *,
    manual_events_payload: Any | None,
    candidate_registry_path: str | Path,
    source_registry_path: str | Path,
) -> dict[str, dict[str, Any]]:
    try:
        if manual_events_payload is None:
            events = load_campaign_events_manual(
                manual_events_path,
                candidate_registry_path=candidate_registry_path,
                source_registry_path=source_registry_path,
            )
        else:
            events = normalize_campaign_events_manual(
                manual_events_payload,
                candidate_registry_path=candidate_registry_path,
                source_registry_path=source_registry_path,
            )
    except CampaignEventsManualError as error:
        raise CampaignEventUpdatesManualError(
            f"manual Campaign Events input is invalid: {error}"
        ) from error

    event_by_key: dict[str, dict[str, Any]] = {}
    for event in events:
        event_key = event["event_key"]
        if event_key in event_by_key:  # Defensive; Step 1 already rejects this.
            _fail(f"manual Campaign Events input has duplicate event_key: {event_key}")
        event_by_key[event_key] = event
    return event_by_key


def _normalize_update(
    value: Any,
    *,
    index: int,
    event_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    context = f"updates[{index}]"
    if type(value) is not dict:
        _fail(f"{context} must be a plain dict")
    _require_exact_keys(value, _UPDATE_KEYS, context)

    update_key = value["update_key"]
    if not isinstance(update_key, str) or not _UPDATE_KEY.fullmatch(update_key):
        _fail(
            f"{context}.update_key must be update- plus 32 lowercase hex characters"
        )

    event_key = value["event_key"]
    if not isinstance(event_key, str) or event_key not in event_by_key:
        _fail(f"{context}.event_key does not reference a manual Campaign Event")

    update_type = value["update_type"]
    if not isinstance(update_type, str) or update_type not in _UPDATE_TYPES:
        _fail(f"{context}.update_type is not allowed")

    headline = _normalize_text(value["headline"], f"{context}.headline")
    observed_at = _require_utc_timestamp(
        value["observed_at"],
        f"{context}.observed_at",
    )
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
        raise CampaignEventUpdatesManualError(str(error)) from error

    return {
        "update_key": update_key,
        "update_id": campaign_event_update_id(update_key),
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "update_type": update_type,
        "headline": headline,
        "observed_at": observed_at,
        "evidence": [
            {
                "source_id": source_id,
                "source_url": source_url,
                "source_publisher": source_publisher,
                "source_type": value["source_type"],
            }
        ],
    }


def _validate_latest_update_statuses(
    updates: list[dict[str, Any]],
    event_by_key: dict[str, dict[str, Any]],
) -> None:
    """Validate current status against only the latest history entry per event."""

    latest_by_event: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for update in updates:
        candidate = (update["observed_at"], update["update_id"], update)
        current = latest_by_event.get(update["event_key"])
        if current is None or candidate[:2] > current[:2]:
            latest_by_event[update["event_key"]] = candidate

    for event_key, (_, _, update) in latest_by_event.items():
        event_status = event_by_key[event_key]["status"]
        update_type = update["update_type"]
        if event_status not in _ALLOWED_EVENT_STATUSES[update_type]:
            _fail(
                f"latest update for {event_key} has type {update_type}, which is "
                f"inconsistent with event status {event_status}"
            )


def normalize_campaign_event_updates_manual(
    payload: Any,
    *,
    manual_events_path: str | Path = _DEFAULT_MANUAL_EVENTS,
    manual_events_payload: Any | None = None,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> list[dict[str, Any]]:
    """Return deterministic normalized Event Watch records."""

    if type(payload) is not dict:
        _fail("payload must be a plain dict")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version must be exactly '1.0'")
    updates = payload["updates"]
    if not isinstance(updates, list):
        _fail("updates must be a list")

    event_by_key = _load_manual_event_index(
        manual_events_path,
        manual_events_payload=manual_events_payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    normalized = [
        _normalize_update(update, index=index, event_by_key=event_by_key)
        for index, update in enumerate(updates)
    ]

    seen_keys: set[str] = set()
    seen_ids: set[str] = set()
    for update in normalized:
        update_key = update["update_key"]
        update_id = update["update_id"]
        if update_key in seen_keys:
            _fail(f"duplicate update_key: {update_key}")
        if update_id in seen_ids:
            _fail(f"duplicate update_id: {update_id}")
        seen_keys.add(update_key)
        seen_ids.add(update_id)

    _validate_latest_update_statuses(normalized, event_by_key)

    # The first stable sort supplies the ascending tie-breaker for the second.
    normalized.sort(key=lambda update: update["update_id"])
    normalized.sort(key=lambda update: update["observed_at"], reverse=True)
    return normalized


def validate_campaign_event_updates_manual(
    payload: Any,
    *,
    manual_events_path: str | Path = _DEFAULT_MANUAL_EVENTS,
    manual_events_payload: Any | None = None,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> None:
    """Validate manual Event Watch input without requiring input ordering."""

    normalize_campaign_event_updates_manual(
        payload,
        manual_events_path=manual_events_path,
        manual_events_payload=manual_events_payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )


def load_campaign_event_updates_manual(
    path: str | Path,
    *,
    manual_events_path: str | Path = _DEFAULT_MANUAL_EVENTS,
    manual_events_payload: Any | None = None,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> list[dict[str, Any]]:
    """Load one UTF-8 manual Event Watch file and return normalized records."""

    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise CampaignEventUpdatesManualError(
            f"could not read manual Event Watch input {target}: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CampaignEventUpdatesManualError(
            f"manual Event Watch input {target} is malformed JSON: {error}"
        ) from error
    return normalize_campaign_event_updates_manual(
        payload,
        manual_events_path=manual_events_path,
        manual_events_payload=manual_events_payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
