"""Strict, network-free validation for immutable institutional event seeds."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from campaign_event_sources import (
    CampaignEventSourceRegistryError,
    load_campaign_event_source_registry,
    normalize_https_url,
)

__all__ = [
    "CampaignEventInstitutionalSeedError",
    "load_campaign_event_institutional_seeds",
    "normalize_campaign_event_institutional_seeds",
    "serialize_campaign_event_institutional_seeds",
    "validate_campaign_event_institutional_seeds",
]


class CampaignEventInstitutionalSeedError(ValueError):
    """Raised when immutable institutional seed configuration is invalid."""


SCHEMA_VERSION = "1.0"
LANE = "institutional_milestones"
TIMEZONE = "Europe/Paris"
REQUIRED_EVENT_TYPES = frozenset({"first_round", "second_round"})
OFFICIAL_SOURCE_TYPES = frozenset({"official_structured", "official_unstructured"})
STATUSES = frozenset({"scheduled", "postponed", "cancelled", "completed"})
EVIDENCE_STATUSES = frozenset({"verified", "stale", "past_unconfirmed"})
EVIDENCE_TYPES = frozenset(
    {"explicit_schedule", "explicit_status_update", "official_rule_derivation"}
)

_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name("campaign_event_sources.json")
_TOP_LEVEL_KEYS = frozenset({"schema_version", "seeds"})
_SEED_KEYS = frozenset(
    {
        "event_key",
        "lane",
        "event_type",
        "title",
        "scheduled_start",
        "time_precision",
        "timezone",
        "status",
        "status_as_of",
        "evidence_status",
        "last_verified_at",
        "evidence",
    }
)
_EVIDENCE_KEYS = frozenset(
    {
        "source_id",
        "source_url",
        "source_publisher",
        "source_type",
        "evidence_type",
    }
)
_KEBAB_CASE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_UTC_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
    re.ASCII,
)
_UTC = timezone.utc
_EVENT_ORDER = {"first_round": 0, "second_round": 1}


def _fail(message: str) -> None:
    raise CampaignEventInstitutionalSeedError(message)


def _require_exact_keys(
    value: dict[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        _fail(
            f"{context} must have exact keys; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _require_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{context} must be non-empty trimmed text")
    if unicodedata.normalize("NFC", value) != value:
        _fail(f"{context} must use canonical NFC text")
    return value


def _require_kebab_case(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _KEBAB_CASE.fullmatch(value):
        _fail(f"{context} must be lowercase ASCII kebab-case")
    return value


def _require_date(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        _fail(f"{context} must be a canonical date-only YYYY-MM-DD value")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CampaignEventInstitutionalSeedError(
            f"{context} must be a valid date-only value"
        ) from error
    if parsed.isoformat() != value:
        _fail(f"{context} must be a canonical date-only YYYY-MM-DD value")
    return value


def _require_utc_timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{context} must be a canonical UTC RFC 3339 timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_UTC
        )
    except ValueError as error:
        raise CampaignEventInstitutionalSeedError(
            f"{context} must be a valid UTC RFC 3339 timestamp"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(f"{context} must be a canonical UTC RFC 3339 timestamp")
    return value


def _source_registry_by_id(path: str | Path) -> dict[str, dict[str, Any]]:
    try:
        registry = load_campaign_event_source_registry(path)
    except (OSError, json.JSONDecodeError, CampaignEventSourceRegistryError) as error:
        raise CampaignEventInstitutionalSeedError(
            f"source registry is unavailable or invalid: {error}"
        ) from error
    return {source["source_id"]: source for source in registry["sources"]}


def _eligible_source_ids(
    source_by_id: dict[str, dict[str, Any]],
    event_type: str,
) -> set[str]:
    return {
        source_id
        for source_id, source in source_by_id.items()
        if source["enabled"]
        and source["source_type"] in OFFICIAL_SOURCE_TYPES
        and LANE in source["allowed_lanes"]
        and event_type in source["allowed_event_types"]
    }


def _normalize_evidence(
    value: Any,
    *,
    event_type: str,
    source_by_id: dict[str, dict[str, Any]],
    context: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        _fail(f"{context} must be a non-empty list")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for index, evidence in enumerate(value):
        evidence_context = f"{context}[{index}]"
        if type(evidence) is not dict:
            _fail(f"{evidence_context} must be a plain dict")
        _require_exact_keys(evidence, _EVIDENCE_KEYS, evidence_context)
        source_id = _require_kebab_case(
            evidence["source_id"], f"{evidence_context}.source_id"
        )
        registered = source_by_id.get(source_id)
        if registered is None:
            _fail(f"{evidence_context}.source_id is not authorized")
        if not registered["enabled"]:
            _fail(f"{evidence_context}.source_id is disabled")
        if registered["source_type"] not in OFFICIAL_SOURCE_TYPES:
            _fail(f"{evidence_context}.source_id must be an official source")
        if evidence["source_type"] != registered["source_type"]:
            _fail(f"{evidence_context}.source_type does not match the registry")
        if evidence["source_publisher"] != registered["publisher"]:
            _fail(f"{evidence_context}.source_publisher does not match the registry")
        _require_text(
            evidence["source_publisher"], f"{evidence_context}.source_publisher"
        )
        if LANE not in registered["allowed_lanes"]:
            _fail(f"{evidence_context}.source_id is not authorized for {LANE}")
        if event_type not in registered["allowed_event_types"]:
            _fail(
                f"{evidence_context}.source_id is not authorized for {event_type}"
            )
        evidence_type = evidence["evidence_type"]
        if evidence_type not in EVIDENCE_TYPES:
            _fail(f"{evidence_context}.evidence_type is not allowed")
        supplied_source_url = evidence["source_url"]
        try:
            source_url = normalize_https_url(
                supplied_source_url, f"{evidence_context}.source_url"
            )
        except CampaignEventSourceRegistryError as error:
            raise CampaignEventInstitutionalSeedError(str(error)) from error
        if (
            supplied_source_url != registered["url"]
            or source_url != registered["url"]
        ):
            _fail(
                f"{evidence_context}.source_url must exactly match the registered "
                "source URL"
            )
        if source_id in seen_ids:
            _fail(f"{context} contains a duplicate source_id")
        if source_url in seen_urls:
            _fail(f"{context} contains a duplicate source URL")
        seen_ids.add(source_id)
        seen_urls.add(source_url)
        records.append(
            {
                "source_id": source_id,
                "source_url": registered["url"],
                "source_publisher": registered["publisher"],
                "source_type": registered["source_type"],
                "evidence_type": evidence_type,
            }
        )
    expected_ids = _eligible_source_ids(source_by_id, event_type)
    if seen_ids != expected_ids:
        _fail(
            f"{context} must include exactly the authorized official sources; "
            f"expected={sorted(expected_ids)}, actual={sorted(seen_ids)}"
        )
    records.sort(key=lambda record: record["source_id"])
    return records


def normalize_campaign_event_institutional_seeds(
    payload: Any,
    *,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> dict[str, Any]:
    """Return newly allocated, canonical immutable milestone seed configuration."""

    if type(payload) is not dict:
        _fail("payload must be a plain dict")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version must be exactly '1.0'")
    seeds = payload["seeds"]
    if not isinstance(seeds, list):
        _fail("seeds must be a list")
    source_by_id = _source_registry_by_id(source_registry_path)
    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_types: set[str] = set()
    for index, seed in enumerate(seeds):
        context = f"seeds[{index}]"
        if type(seed) is not dict:
            _fail(f"{context} must be a plain dict")
        _require_exact_keys(seed, _SEED_KEYS, context)
        event_key = _require_kebab_case(seed["event_key"], f"{context}.event_key")
        if event_key in seen_keys:
            _fail(f"duplicate seed event_key: {event_key}")
        seen_keys.add(event_key)
        if seed["lane"] != LANE:
            _fail(f"{context}.lane must be exactly {LANE}")
        event_type = seed["event_type"]
        if event_type not in REQUIRED_EVENT_TYPES:
            _fail(f"{context}.event_type must be an institutional round type")
        if event_type in seen_types:
            _fail(f"duplicate event_type for presidential-2027: {event_type}")
        seen_types.add(event_type)
        title = _require_text(seed["title"], f"{context}.title")
        scheduled_start = _require_date(
            seed["scheduled_start"], f"{context}.scheduled_start"
        )
        if seed["time_precision"] != "date":
            _fail(f"{context}.time_precision must be exactly 'date'")
        if seed["timezone"] != TIMEZONE:
            _fail(f"{context}.timezone must be exactly {TIMEZONE}")
        if seed["status"] not in STATUSES:
            _fail(f"{context}.status is not allowed")
        status_as_of = _require_date(seed["status_as_of"], f"{context}.status_as_of")
        if seed["evidence_status"] not in EVIDENCE_STATUSES:
            _fail(f"{context}.evidence_status is not allowed")
        last_verified_at = _require_utc_timestamp(
            seed["last_verified_at"], f"{context}.last_verified_at"
        )
        evidence = _normalize_evidence(
            seed["evidence"],
            event_type=event_type,
            source_by_id=source_by_id,
            context=f"{context}.evidence",
        )
        normalized.append(
            {
                "event_key": event_key,
                "lane": LANE,
                "event_type": event_type,
                "title": title,
                "scheduled_start": scheduled_start,
                "time_precision": "date",
                "timezone": TIMEZONE,
                "status": seed["status"],
                "status_as_of": status_as_of,
                "evidence_status": seed["evidence_status"],
                "last_verified_at": last_verified_at,
                "evidence": evidence,
            }
        )
    if seen_types != REQUIRED_EVENT_TYPES:
        _fail(
            "seeds must contain exactly first_round and second_round; "
            f"actual={sorted(seen_types)}"
        )
    normalized.sort(
        key=lambda seed: (_EVENT_ORDER[seed["event_type"]], seed["event_key"])
    )
    return {"schema_version": SCHEMA_VERSION, "seeds": normalized}


def validate_campaign_event_institutional_seeds(
    payload: Any,
    *,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> None:
    """Validate seed values and require canonical deterministic ordering."""

    normalized = normalize_campaign_event_institutional_seeds(
        payload,
        source_registry_path=source_registry_path,
    )
    if payload != normalized:
        _fail("seed configuration must use canonical values and deterministic ordering")


def serialize_campaign_event_institutional_seeds(
    payload: Any,
    *,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> bytes:
    """Return canonical UTF-8 JSON with two-space indentation and a newline."""

    normalized = normalize_campaign_event_institutional_seeds(
        payload,
        source_registry_path=source_registry_path,
    )
    validate_campaign_event_institutional_seeds(
        normalized,
        source_registry_path=source_registry_path,
    )
    return (json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )


def load_campaign_event_institutional_seeds(
    path: str | Path,
    *,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> dict[str, Any]:
    """Load and validate one canonical UTF-8 institutional seed file."""

    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise CampaignEventInstitutionalSeedError(
            f"could not read institutional seeds {target}: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CampaignEventInstitutionalSeedError(
            f"institutional seeds {target} are malformed JSON: {error}"
        ) from error
    validate_campaign_event_institutional_seeds(
        payload,
        source_registry_path=source_registry_path,
    )
    return normalize_campaign_event_institutional_seeds(
        payload,
        source_registry_path=source_registry_path,
    )
