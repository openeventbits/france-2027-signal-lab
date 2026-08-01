"""Deterministic, network-free Campaign Events artifact contract."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    candidacy_status_by_id,
    load_candidate_candidacy_status,
)
from campaign_event_sources import (
    CAMPAIGN_EVENT_TYPES,
    INSTITUTIONAL_EVENT_TYPES,
    SOURCE_TYPES,
    CampaignEventSourceRegistryError,
    load_campaign_event_source_registry,
    normalize_https_url,
)

__all__ = [
    "CampaignEventsContractError",
    "campaign_event_id",
    "normalize_campaign_events_artifact",
    "serialize_campaign_events",
    "validate_campaign_events_artifact",
]


class CampaignEventsContractError(ValueError):
    """Raised when a Campaign Events artifact violates its contract."""


SCHEMA_VERSION = "1.0"
CAMPAIGN_EVENTS_LANE = "campaign_events"
INSTITUTIONAL_MILESTONES_LANE = "institutional_milestones"
TIMEZONE = "Europe/Paris"
TIME_PRECISIONS = frozenset({"date", "datetime"})
STATUSES = frozenset({"scheduled", "postponed", "cancelled", "completed"})
EVIDENCE_STATUSES = frozenset({"verified", "stale", "past_unconfirmed"})
EVIDENCE_TYPES = frozenset(
    {
        "explicit_schedule",
        "explicit_status_update",
        "official_rule_derivation",
    }
)

_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name(
    "campaign_event_sources.json"
)
_PARIS = ZoneInfo(TIMEZONE)
_UTC = timezone.utc
_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "data_as_of",
        CAMPAIGN_EVENTS_LANE,
        INSTITUTIONAL_MILESTONES_LANE,
    }
)
_REQUIRED_EVENT_KEYS = frozenset(
    {
        "event_key",
        "event_id",
        "event_type",
        "title",
        "candidate_ids",
        "candidate_names",
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
_OPTIONAL_EVENT_KEYS = frozenset(
    {
        "scheduled_end",
        "organization",
        "location_name",
        "locality",
        "department",
    }
)
_REQUIRED_EVIDENCE_KEYS = frozenset(
    {
        "source_id",
        "source_url",
        "source_publisher",
        "source_type",
        "evidence_type",
    }
)
_OPTIONAL_EVIDENCE_KEYS = frozenset({"source_published_at"})
_KEBAB_CASE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_EVENT_ID = re.compile(r"ce-[0-9a-f]{24}\Z", re.ASCII)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_UTC_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
    re.ASCII,
)
_OFFSET_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\Z",
    re.ASCII,
)
_DEPARTMENT_CODES = frozenset(
    {
        *(f"{number:02d}" for number in range(1, 20)),
        "2A",
        "2B",
        *(f"{number:02d}" for number in range(21, 96)),
        "971",
        "972",
        "973",
        "974",
        "976",
    }
)
_EVENT_TYPE_ORDER = {
    event_type: index
    for index, event_type in enumerate(
        (
            "rally",
            "public_meeting",
            "candidate_visit",
            "campaign_launch",
            "sponsorship_deadline",
            "official_candidate_list",
            "campaign_period_boundary",
            "first_round",
            "second_round",
        )
    )
}
_SOURCE_TYPE_ORDER = {
    source_type: index
    for index, source_type in enumerate(
        (
            "official_structured",
            "official_unstructured",
            "candidate_first_party",
            "party_first_party",
            "organizer_first_party",
            "reliable_media",
        )
    )
}
_EVIDENCE_TYPE_ORDER = {
    evidence_type: index
    for index, evidence_type in enumerate(
        (
            "explicit_status_update",
            "explicit_schedule",
            "official_rule_derivation",
        )
    )
}


def _fail(message: str) -> None:
    raise CampaignEventsContractError(message)


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


def _require_trimmed_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{context} must be non-empty trimmed text")
    if unicodedata.normalize("NFC", value) != value:
        _fail(f"{context} must use canonical NFC text")
    return value


def _require_kebab_case(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _KEBAB_CASE.fullmatch(value):
        _fail(f"{context} must be lowercase ASCII kebab-case")
    return value


def _require_date(value: Any, context: str) -> date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        _fail(f"{context} must be a canonical YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CampaignEventsContractError(
            f"{context} must be a valid canonical YYYY-MM-DD date"
        ) from error
    if parsed.isoformat() != value:
        _fail(f"{context} must be a canonical YYYY-MM-DD date")
    return parsed


def _require_utc_timestamp(value: Any, context: str) -> datetime:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        _fail(f"{context} must be a canonical UTC RFC 3339 timestamp ending in Z")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_UTC
        )
    except ValueError as error:
        raise CampaignEventsContractError(
            f"{context} must be a valid UTC RFC 3339 timestamp"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(f"{context} must be a canonical UTC RFC 3339 timestamp")
    return parsed


def _require_paris_datetime(value: Any, context: str) -> datetime:
    if not isinstance(value, str) or not _OFFSET_TIMESTAMP.fullmatch(value):
        _fail(
            f"{context} must be RFC 3339 with seconds and an explicit UTC offset"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CampaignEventsContractError(
            f"{context} must be a valid RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None:
        _fail(f"{context} must include a UTC offset")

    naive = parsed.replace(tzinfo=None)
    supplied_offset = parsed.utcoffset()
    valid = False
    for fold in (0, 1):
        paris_value = naive.replace(tzinfo=_PARIS, fold=fold)
        round_trip = paris_value.astimezone(_UTC).astimezone(_PARIS)
        if (
            paris_value.utcoffset() == supplied_offset
            and round_trip.replace(tzinfo=None) == naive
        ):
            valid = True
            break
    if not valid:
        _fail(f"{context} UTC offset is not valid for Europe/Paris at that time")
    return parsed


def _candidate_registry_by_id(
    candidate_registry_path: str | Path,
) -> dict[str, dict[str, Any]]:
    try:
        registry = load_candidate_candidacy_status(candidate_registry_path)
        return candidacy_status_by_id(registry)
    except (OSError, json.JSONDecodeError, CandidateCandidacyStatusError) as error:
        raise CampaignEventsContractError(
            f"candidate registry is unavailable or invalid: {error}"
        ) from error


def _source_registry_by_id(
    source_registry_path: str | Path,
    *,
    candidate_registry_path: str | Path,
) -> dict[str, dict[str, Any]]:
    try:
        registry = load_campaign_event_source_registry(
            source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
    except CampaignEventSourceRegistryError as error:
        raise CampaignEventsContractError(
            f"Campaign Events source registry is unavailable or invalid: {error}"
        ) from error
    return {
        source["source_id"]: source
        for source in registry["sources"]
    }


def campaign_event_id(lane: str, event_key: str) -> str:
    """Return the version-1 deterministic ID for one immutable event key."""

    if lane not in {CAMPAIGN_EVENTS_LANE, INSTITUTIONAL_MILESTONES_LANE}:
        _fail(f"unsupported Campaign Events lane: {lane!r}")
    _require_kebab_case(event_key, "event_key")
    identity = f"campaign-events:v1\0{lane}\0{event_key}".encode("utf-8")
    return "ce-" + hashlib.sha256(identity).hexdigest()[:24]


def _normalize_candidates(
    event: dict[str, Any],
    *,
    lane: str,
    candidate_by_id: dict[str, dict[str, Any]],
    context: str,
) -> tuple[list[str], list[str]]:
    candidate_ids = event["candidate_ids"]
    candidate_names = event["candidate_names"]
    if not isinstance(candidate_ids, list) or not isinstance(candidate_names, list):
        _fail(f"{context}.candidate_ids and candidate_names must be lists")
    if len(candidate_ids) != len(candidate_names):
        _fail(f"{context}.candidate_ids and candidate_names must be parallel")
    if lane == CAMPAIGN_EVENTS_LANE and not candidate_ids:
        _fail(f"{context} Campaign Events require at least one candidate")
    if lane == INSTITUTIONAL_MILESTONES_LANE and (
        candidate_ids or candidate_names
    ):
        _fail(f"{context} Institutional Milestones must be candidate-free")

    seen_ids: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for index, (identifier, supplied_name) in enumerate(
        zip(candidate_ids, candidate_names)
    ):
        _require_kebab_case(identifier, f"{context}.candidate_ids[{index}]")
        if identifier in seen_ids:
            _fail(f"{context} contains duplicate candidate IDs")
        registry_entry = candidate_by_id.get(identifier)
        if registry_entry is None:
            _fail(f"{context}.candidate_ids[{index}] is not canonical")
        canonical_name = registry_entry["candidate_name"]
        if supplied_name != canonical_name:
            _fail(
                f"{context}.candidate_names[{index}] does not match "
                f"canonical identity {identifier!r}"
            )
        seen_ids.add(identifier)
        pairs.append((identifier, canonical_name))

    pairs.sort(key=lambda pair: (pair[1].casefold(), pair[0]))
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def _normalize_evidence(
    value: Any,
    *,
    lane: str,
    event_type: str,
    event_candidate_ids: list[str],
    source_by_id: dict[str, dict[str, Any]],
    event_context: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        _fail(f"{event_context}.evidence must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    full_records: set[tuple[Any, ...]] = set()
    source_urls: set[str] = set()

    for index, evidence in enumerate(value):
        context = f"{event_context}.evidence[{index}]"
        if type(evidence) is not dict:
            _fail(f"{context} must be a plain dict")
        _require_exact_keys(
            evidence,
            _REQUIRED_EVIDENCE_KEYS,
            _OPTIONAL_EVIDENCE_KEYS,
            context,
        )
        source_id = _require_kebab_case(evidence["source_id"], f"{context}.source_id")
        try:
            source_url = normalize_https_url(
                evidence["source_url"],
                f"{context}.source_url",
            )
        except CampaignEventSourceRegistryError as error:
            raise CampaignEventsContractError(str(error)) from error
        source_publisher = _require_trimmed_text(
            evidence["source_publisher"],
            f"{context}.source_publisher",
        )
        source_type = evidence["source_type"]
        if not isinstance(source_type, str) or source_type not in SOURCE_TYPES:
            _fail(f"{context}.source_type is not allowed: {source_type!r}")
        evidence_type = evidence["evidence_type"]
        if not isinstance(evidence_type, str) or evidence_type not in EVIDENCE_TYPES:
            _fail(f"{context}.evidence_type is not allowed: {evidence_type!r}")
        if evidence_type == "official_rule_derivation" and (
            lane != INSTITUTIONAL_MILESTONES_LANE
            or source_type not in {"official_structured", "official_unstructured"}
        ):
            _fail(
                f"{context}.official_rule_derivation requires official "
                "Institutional Milestone evidence"
            )

        source_published_at = None
        if "source_published_at" in evidence:
            _require_utc_timestamp(
                evidence["source_published_at"],
                f"{context}.source_published_at",
            )
            source_published_at = evidence["source_published_at"]

        record_identity = (
            source_id,
            source_url,
            source_publisher,
            source_type,
            evidence_type,
            source_published_at,
        )
        if record_identity in full_records:
            _fail(f"{event_context}.evidence contains a duplicate record")
        if source_url in source_urls:
            _fail(f"{event_context}.evidence contains a duplicate source URL")
        full_records.add(record_identity)
        source_urls.add(source_url)

        normalized_record: dict[str, Any] = {
            "source_id": source_id,
            "source_url": source_url,
            "source_publisher": source_publisher,
            "source_type": source_type,
            "evidence_type": evidence_type,
        }
        if source_published_at is not None:
            normalized_record["source_published_at"] = source_published_at
        registered_source = _validate_evidence_registry_parity(
            normalized_record,
            lane=lane,
            event_type=event_type,
            event_candidate_ids=event_candidate_ids,
            source_by_id=source_by_id,
            context=context,
        )
        normalized_record["source_id"] = registered_source["source_id"]
        normalized_record["source_publisher"] = registered_source["publisher"]
        normalized_record["source_type"] = registered_source["source_type"]
        normalized.append(normalized_record)

    normalized.sort(key=_evidence_sort_key)
    _validate_evidence_sufficiency(normalized, lane=lane, context=event_context)
    return normalized


def _validate_evidence_registry_parity(
    evidence: dict[str, Any],
    *,
    lane: str,
    event_type: str,
    event_candidate_ids: list[str],
    source_by_id: dict[str, dict[str, Any]],
    context: str,
) -> dict[str, Any]:
    source_id = evidence["source_id"]
    registered = source_by_id.get(source_id)
    if registered is None:
        _fail(f"{context}.source_id is not in the approved source registry")
    if not registered["enabled"]:
        _fail(f"{context}.source_id is disabled in the approved source registry")
    if evidence["source_type"] != registered["source_type"]:
        _fail(f"{context}.source_type does not match the approved source registry")
    if evidence["source_publisher"] != registered["publisher"]:
        _fail(
            f"{context}.source_publisher does not match the approved source registry"
        )
    if lane not in registered["allowed_lanes"]:
        _fail(f"{context}.source_id is not approved for lane {lane!r}")
    if event_type not in registered["allowed_event_types"]:
        _fail(
            f"{context}.source_id is not approved for event_type {event_type!r}"
        )

    evidence_hostname = urlsplit(evidence["source_url"]).hostname
    registered_hostname = urlsplit(registered["url"]).hostname
    if evidence_hostname != registered_hostname:
        _fail(
            f"{context}.source_url hostname does not exactly match the "
            "approved source hostname"
        )

    if registered["source_type"] == "candidate_first_party":
        owned_candidate_ids = registered.get("candidate_ids")
        if not owned_candidate_ids:
            _fail(
                f"{context}.source_id has no registered candidate ownership"
            )
        if set(event_candidate_ids).isdisjoint(owned_candidate_ids):
            _fail(
                f"{context}.source_id is unrelated to every event candidate"
            )
    return registered


def _evidence_sort_key(evidence: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _SOURCE_TYPE_ORDER[evidence["source_type"]],
        _EVIDENCE_TYPE_ORDER[evidence["evidence_type"]],
        evidence["source_publisher"].casefold(),
        evidence["source_id"],
        evidence["source_url"],
        evidence.get("source_published_at", ""),
    )


def _validate_evidence_sufficiency(
    evidence: list[dict[str, Any]],
    *,
    lane: str,
    context: str,
) -> None:
    explicit_types = {"explicit_schedule", "explicit_status_update"}
    if lane == INSTITUTIONAL_MILESTONES_LANE:
        qualifying = any(
            record["source_type"]
            in {"official_structured", "official_unstructured"}
            and record["evidence_type"]
            in explicit_types | {"official_rule_derivation"}
            for record in evidence
        )
        if not qualifying:
            _fail(f"{context} requires qualifying official evidence")
        return

    has_first_party = any(
        record["source_type"]
        in {
            "candidate_first_party",
            "party_first_party",
            "organizer_first_party",
        }
        and record["evidence_type"] in explicit_types
        for record in evidence
    )
    media_records = [
        record
        for record in evidence
        if record["source_type"] == "reliable_media"
        and record["evidence_type"] in explicit_types
    ]
    independent_source_ids = {record["source_id"] for record in media_records}
    independent_publishers = {
        record["source_publisher"].casefold() for record in media_records
    }
    if not has_first_party and not (
        len(independent_source_ids) >= 2 and len(independent_publishers) >= 2
    ):
        _fail(
            f"{context} requires first-party/organizer evidence or two "
            "independent reliable-media sources and publishers"
        )


def _normalize_scheduled_values(
    event: dict[str, Any],
    *,
    context: str,
) -> tuple[str, str | None]:
    precision = event["time_precision"]
    if not isinstance(precision, str) or precision not in TIME_PRECISIONS:
        _fail(f"{context}.time_precision is not allowed: {precision!r}")
    if event["timezone"] != TIMEZONE:
        _fail(f"{context}.timezone must be exactly {TIMEZONE}")

    start_value = event["scheduled_start"]
    if precision == "date":
        start = _require_date(start_value, f"{context}.scheduled_start")
    else:
        start = _require_paris_datetime(start_value, f"{context}.scheduled_start")

    scheduled_end = None
    if "scheduled_end" in event:
        scheduled_end = event["scheduled_end"]
        if precision == "date":
            end = _require_date(scheduled_end, f"{context}.scheduled_end")
        else:
            end = _require_paris_datetime(
                scheduled_end,
                f"{context}.scheduled_end",
            )
        if end < start:
            _fail(f"{context}.scheduled_end must not precede scheduled_start")
    return start_value, scheduled_end


def _normalize_event(
    value: Any,
    *,
    lane: str,
    index: int,
    candidate_by_id: dict[str, dict[str, Any]],
    source_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    context = f"{lane}[{index}]"
    if type(value) is not dict:
        _fail(f"{context} must be a plain dict")
    _require_exact_keys(
        value,
        _REQUIRED_EVENT_KEYS,
        _OPTIONAL_EVENT_KEYS,
        context,
    )

    event_key = _require_kebab_case(value["event_key"], f"{context}.event_key")
    supplied_event_id = value["event_id"]
    if not isinstance(supplied_event_id, str) or not _EVENT_ID.fullmatch(
        supplied_event_id
    ):
        _fail(f"{context}.event_id must be ce- plus 24 lowercase hex characters")
    expected_event_id = campaign_event_id(lane, event_key)
    if supplied_event_id != expected_event_id:
        _fail(f"{context}.event_id does not match lane and event_key")

    event_type = value["event_type"]
    allowed_types = (
        CAMPAIGN_EVENT_TYPES
        if lane == CAMPAIGN_EVENTS_LANE
        else INSTITUTIONAL_EVENT_TYPES
    )
    if not isinstance(event_type, str) or event_type not in allowed_types:
        _fail(f"{context}.event_type is not allowed in {lane}: {event_type!r}")
    title = _require_trimmed_text(value["title"], f"{context}.title")
    candidate_ids, candidate_names = _normalize_candidates(
        value,
        lane=lane,
        candidate_by_id=candidate_by_id,
        context=context,
    )
    scheduled_start, scheduled_end = _normalize_scheduled_values(
        value,
        context=context,
    )

    status = value["status"]
    if not isinstance(status, str) or status not in STATUSES:
        _fail(f"{context}.status is not allowed: {status!r}")
    _require_date(value["status_as_of"], f"{context}.status_as_of")
    evidence_status = value["evidence_status"]
    if not isinstance(evidence_status, str) or evidence_status not in EVIDENCE_STATUSES:
        _fail(f"{context}.evidence_status is not allowed: {evidence_status!r}")
    _require_utc_timestamp(value["last_verified_at"], f"{context}.last_verified_at")
    evidence = _normalize_evidence(
        value["evidence"],
        lane=lane,
        event_type=event_type,
        event_candidate_ids=candidate_ids,
        source_by_id=source_by_id,
        event_context=context,
    )

    optional_text: dict[str, str] = {}
    for field in ("organization", "location_name", "locality"):
        if field in value:
            optional_text[field] = _require_trimmed_text(
                value[field],
                f"{context}.{field}",
            )
    department = None
    if "department" in value:
        department = value["department"]
        if not isinstance(department, str) or department not in _DEPARTMENT_CODES:
            _fail(f"{context}.department must be a canonical INSEE department code")

    normalized: dict[str, Any] = {
        "event_key": event_key,
        "event_id": supplied_event_id,
        "event_type": event_type,
        "title": title,
        "candidate_ids": candidate_ids,
        "candidate_names": candidate_names,
        "scheduled_start": scheduled_start,
    }
    if scheduled_end is not None:
        normalized["scheduled_end"] = scheduled_end
    normalized.update(
        {
            "time_precision": value["time_precision"],
            "timezone": TIMEZONE,
        }
    )
    for field in ("organization", "location_name", "locality"):
        if field in optional_text:
            normalized[field] = optional_text[field]
    if department is not None:
        normalized["department"] = department
    normalized.update(
        {
            "status": status,
            "status_as_of": value["status_as_of"],
            "evidence_status": evidence_status,
            "last_verified_at": value["last_verified_at"],
            "evidence": evidence,
        }
    )
    return normalized


def _event_sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
    scheduled = event["scheduled_start"]
    if event["time_precision"] == "date":
        date_part = scheduled
        precision_order = 1
        time_part = ""
    else:
        date_part = scheduled[:10]
        precision_order = 0
        time_part = scheduled[11:19]
    return (
        date_part,
        precision_order,
        time_part,
        _EVENT_TYPE_ORDER[event["event_type"]],
        tuple(event["candidate_ids"]),
        event["event_key"],
        event["event_id"],
    )


def normalize_campaign_events_artifact(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> dict[str, Any]:
    """Return a new canonical artifact without mutating caller-supplied input."""

    if type(payload) is not dict:
        _fail("payload must be a plain dict")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, frozenset(), "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version must be exactly '1.0'")
    _require_utc_timestamp(payload["generated_at"], "generated_at")
    _require_utc_timestamp(payload["data_as_of"], "data_as_of")
    candidate_by_id = _candidate_registry_by_id(candidate_registry_path)
    source_by_id = _source_registry_by_id(
        source_registry_path,
        candidate_registry_path=candidate_registry_path,
    )

    normalized_lanes: dict[str, list[dict[str, Any]]] = {}
    seen_event_keys: set[str] = set()
    seen_event_ids: set[str] = set()
    for lane in (CAMPAIGN_EVENTS_LANE, INSTITUTIONAL_MILESTONES_LANE):
        records = payload[lane]
        if not isinstance(records, list):
            _fail(f"{lane} must be a list")
        normalized_records = [
            _normalize_event(
                record,
                lane=lane,
                index=index,
                candidate_by_id=candidate_by_id,
                source_by_id=source_by_id,
            )
            for index, record in enumerate(records)
        ]
        for record in normalized_records:
            event_key = record["event_key"]
            event_id = record["event_id"]
            if event_id in seen_event_ids:
                _fail(f"duplicate event_id across artifact: {event_id}")
            if event_key in seen_event_keys:
                _fail(f"duplicate event_key across artifact: {event_key}")
            seen_event_keys.add(event_key)
            seen_event_ids.add(event_id)
        normalized_records.sort(key=_event_sort_key)
        normalized_lanes[lane] = normalized_records

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "data_as_of": payload["data_as_of"],
        CAMPAIGN_EVENTS_LANE: normalized_lanes[CAMPAIGN_EVENTS_LANE],
        INSTITUTIONAL_MILESTONES_LANE: normalized_lanes[
            INSTITUTIONAL_MILESTONES_LANE
        ],
    }


def validate_campaign_events_artifact(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> None:
    """Validate values and require canonical deterministic list ordering."""

    normalized = normalize_campaign_events_artifact(
        payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    if payload != normalized:
        _fail("artifact must use canonical values and deterministic ordering")


def serialize_campaign_events(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> bytes:
    """Return the canonical UTF-8 serialization with a trailing newline."""

    normalized = normalize_campaign_events_artifact(
        payload,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    validate_campaign_events_artifact(
        normalized,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    return (
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
