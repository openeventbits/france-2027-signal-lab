"""Strict, network-free validation for Campaign Events source registries."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    candidacy_status_by_id,
    load_candidate_candidacy_status,
)

__all__ = [
    "ATTRIBUTION_POLICIES",
    "ALLOWED_EVENT_TYPES",
    "ALLOWED_LANES",
    "CAMPAIGN_EVENT_TYPES",
    "CampaignEventSourceRegistryError",
    "DISCOVERY_METHODS",
    "INSTITUTIONAL_EVENT_TYPES",
    "PARSER_FAMILIES",
    "REFRESH_CLASSES",
    "SOURCE_TYPES",
    "load_campaign_event_source_registry",
    "normalize_campaign_event_source_registry",
    "normalize_https_url",
    "validate_campaign_event_source_registry",
]


class CampaignEventSourceRegistryError(ValueError):
    """Raised when a Campaign Events source registry violates its contract."""


SCHEMA_VERSION = "2.0"
SOURCE_TYPES = frozenset(
    {
        "official_structured",
        "official_unstructured",
        "candidate_first_party",
        "party_first_party",
        "organizer_first_party",
        "reliable_media",
    }
)
ALLOWED_LANES = frozenset(
    {
        "campaign_events",
        "institutional_milestones",
    }
)
CAMPAIGN_EVENT_TYPES = frozenset(
    {
        "rally",
        "public_meeting",
        "debate",
        "candidate_visit",
        "campaign_launch",
    }
)
INSTITUTIONAL_EVENT_TYPES = frozenset(
    {
        "sponsorship_deadline",
        "official_candidate_list",
        "campaign_period_boundary",
        "first_round",
        "second_round",
    }
)
ALLOWED_EVENT_TYPES = CAMPAIGN_EVENT_TYPES | INSTITUTIONAL_EVENT_TYPES
REFRESH_CLASSES = frozenset(
    {
        "hourly",
        "every_3_hours",
        "every_12_hours",
        "daily",
        "manual",
    }
)

DISCOVERY_METHODS = frozenset(
    {
        "direct",
        "linked_event_pages",
        "ics",
        "json_ld",
        "rest",
        "structured_html",
        "custom",
    }
)
PARSER_FAMILIES = frozenset(
    {
        "ics",
        "json_ld",
        "rest",
        "structured_html",
        "custom",
    }
)
ATTRIBUTION_POLICIES = frozenset(
    {
        "explicit_participant",
        "candidate_owned_campaign",
        "multi_candidate_explicit",
        "custom",
    }
)

_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_TOP_LEVEL_KEYS = frozenset({"schema_version", "sources"})
_REQUIRED_SOURCE_KEYS = frozenset(
    {
        "source_id",
        "publisher",
        "source_type",
        "url",
        "allowed_lanes",
        "allowed_event_types",
        "enabled",
        "required",
        "refresh_class",
        "zero_result_valid",
    }
)
_OPTIONAL_SOURCE_KEYS = frozenset(
    {"candidate_ids", "organization", "collection"}
)
_REQUIRED_COLLECTION_KEYS = frozenset(
    {"discovery_method", "parser_family", "attribution_policy"}
)
_OPTIONAL_COLLECTION_KEYS = frozenset({"collector_family"})
_SOURCE_KEYS = _REQUIRED_SOURCE_KEYS | _OPTIONAL_SOURCE_KEYS
_KEBAB_CASE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_HOST_LABEL = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)
_LANE_ORDER = {
    "campaign_events": 0,
    "institutional_milestones": 1,
}
_EVENT_TYPE_ORDER = {
    event_type: index
    for index, event_type in enumerate(
        (
            "rally",
            "public_meeting",
            "debate",
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


def _fail(message: str) -> None:
    raise CampaignEventSourceRegistryError(message)


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
    normalized = unicodedata.normalize("NFC", value)
    if normalized != value:
        _fail(f"{context} must use canonical NFC text")
    return value


def _require_kebab_case(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _KEBAB_CASE.fullmatch(value):
        _fail(f"{context} must be lowercase ASCII kebab-case")
    return value


def normalize_https_url(value: Any, context: str = "url") -> str:
    """Return a canonical absolute HTTPS URL without accessing the network."""

    url = _require_trimmed_text(value, context)
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise CampaignEventSourceRegistryError(
            f"{context} must be a well-formed absolute HTTPS URL"
        ) from error
    if parsed.scheme.casefold() != "https" or not parsed.netloc or not hostname:
        _fail(f"{context} must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        _fail(f"{context} must not contain user information")
    if port is not None:
        _fail(f"{context} must not contain an explicit port")
    if parsed.fragment:
        _fail(f"{context} must not contain a fragment")

    canonical_host = hostname.casefold()
    if canonical_host.endswith("."):
        _fail(f"{context} hostname must not have a trailing dot")
    if len(canonical_host) > 253:
        _fail(f"{context} hostname is too long")
    labels = canonical_host.split(".")
    if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
        _fail(f"{context} hostname is invalid")

    return urlunsplit(("https", canonical_host, parsed.path, parsed.query, ""))


def _candidate_registry_by_id(
    candidate_registry_path: str | Path,
) -> dict[str, dict[str, Any]]:
    try:
        registry = load_candidate_candidacy_status(candidate_registry_path)
        return candidacy_status_by_id(registry)
    except (OSError, json.JSONDecodeError, CandidateCandidacyStatusError) as error:
        raise CampaignEventSourceRegistryError(
            f"candidate registry is unavailable or invalid: {error}"
        ) from error


def _normalize_unique_controlled_list(
    value: Any,
    *,
    allowed: frozenset[str],
    order: dict[str, int],
    context: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(f"{context} must be a non-empty list")
    if any(not isinstance(item, str) or item not in allowed for item in value):
        _fail(f"{context} contains an unsupported value")
    if len(set(value)) != len(value):
        _fail(f"{context} must not contain duplicates")
    return sorted(value, key=lambda item: (order[item], item))


def _normalize_candidate_ids(
    value: Any,
    *,
    candidate_by_id: dict[str, dict[str, Any]],
    context: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(f"{context} must be a non-empty list")
    identifiers: list[str] = []
    for index, identifier in enumerate(value):
        _require_kebab_case(identifier, f"{context}[{index}]")
        if identifier not in candidate_by_id:
            _fail(f"{context}[{index}] is not a canonical candidate ID")
        identifiers.append(identifier)
    if len(set(identifiers)) != len(identifiers):
        _fail(f"{context} must not contain duplicate candidate IDs")
    return sorted(
        identifiers,
        key=lambda identifier: (
            candidate_by_id[identifier]["candidate_name"].casefold(),
            identifier,
        ),
    )


def _normalize_collection(
    value: Any,
    *,
    context: str,
) -> dict[str, str]:
    if type(value) is not dict:
        _fail(f"{context} must be a plain dict")
    _require_exact_keys(
        value,
        _REQUIRED_COLLECTION_KEYS,
        _OPTIONAL_COLLECTION_KEYS,
        context,
    )

    discovery_method = value["discovery_method"]
    if (
        not isinstance(discovery_method, str)
        or discovery_method not in DISCOVERY_METHODS
    ):
        _fail(
            f"{context}.discovery_method is not allowed: "
            f"{discovery_method!r}"
        )

    parser_family = value["parser_family"]
    if (
        not isinstance(parser_family, str)
        or parser_family not in PARSER_FAMILIES
    ):
        _fail(f"{context}.parser_family is not allowed: {parser_family!r}")

    attribution_policy = value["attribution_policy"]
    if (
        not isinstance(attribution_policy, str)
        or attribution_policy not in ATTRIBUTION_POLICIES
    ):
        _fail(
            f"{context}.attribution_policy is not allowed: "
            f"{attribution_policy!r}"
        )

    uses_custom_step = "custom" in {
        discovery_method,
        parser_family,
        attribution_policy,
    }
    collector_family = None
    if "collector_family" in value:
        collector_family = _require_kebab_case(
            value["collector_family"],
            f"{context}.collector_family",
        )
    if uses_custom_step and collector_family is None:
        _fail(f"{context} custom collection requires collector_family")
    if not uses_custom_step and collector_family is not None:
        _fail(
            f"{context}.collector_family is only allowed for custom collection"
        )

    normalized = {
        "discovery_method": discovery_method,
        "parser_family": parser_family,
        "attribution_policy": attribution_policy,
    }
    if collector_family is not None:
        normalized["collector_family"] = collector_family
    return normalized


def _normalize_source(
    value: Any,
    *,
    index: int,
    candidate_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    context = f"sources[{index}]"
    if type(value) is not dict:
        _fail(f"{context} must be a plain dict")
    _require_exact_keys(value, _REQUIRED_SOURCE_KEYS, _OPTIONAL_SOURCE_KEYS, context)

    source_id = _require_kebab_case(value["source_id"], f"{context}.source_id")
    publisher = _require_trimmed_text(value["publisher"], f"{context}.publisher")
    source_type = value["source_type"]
    if not isinstance(source_type, str) or source_type not in SOURCE_TYPES:
        _fail(f"{context}.source_type is not allowed: {source_type!r}")
    url = normalize_https_url(value["url"], f"{context}.url")

    lanes = _normalize_unique_controlled_list(
        value["allowed_lanes"],
        allowed=ALLOWED_LANES,
        order=_LANE_ORDER,
        context=f"{context}.allowed_lanes",
    )
    event_types = _normalize_unique_controlled_list(
        value["allowed_event_types"],
        allowed=ALLOWED_EVENT_TYPES,
        order=_EVENT_TYPE_ORDER,
        context=f"{context}.allowed_event_types",
    )
    event_type_lanes = {
        "campaign_events" if event_type in CAMPAIGN_EVENT_TYPES
        else "institutional_milestones"
        for event_type in event_types
    }
    if event_type_lanes != set(lanes):
        _fail(
            f"{context}.allowed_event_types must cover exactly the allowed lanes"
        )

    for field in ("enabled", "required", "zero_result_valid"):
        if type(value[field]) is not bool:
            _fail(f"{context}.{field} must be an actual boolean")
    refresh_class = value["refresh_class"]
    if not isinstance(refresh_class, str) or refresh_class not in REFRESH_CLASSES:
        _fail(f"{context}.refresh_class is not allowed: {refresh_class!r}")

    candidate_ids = None
    if "candidate_ids" in value:
        candidate_ids = _normalize_candidate_ids(
            value["candidate_ids"],
            candidate_by_id=candidate_by_id,
            context=f"{context}.candidate_ids",
        )
    organization = None
    if "organization" in value:
        organization = _require_trimmed_text(
            value["organization"],
            f"{context}.organization",
        )

    collection = None
    if "collection" in value:
        collection = _normalize_collection(
            value["collection"],
            context=f"{context}.collection",
        )
    if "campaign_events" in lanes and collection is None:
        _fail(f"{context} campaign-event source requires collection")
    if "campaign_events" not in lanes and collection is not None:
        _fail(
            f"{context}.collection is only relevant to campaign-event sources"
        )
    if (
        collection is not None
        and collection["attribution_policy"] == "candidate_owned_campaign"
        and source_type != "candidate_first_party"
    ):
        _fail(
            f"{context}.collection candidate_owned_campaign attribution "
            "requires candidate_first_party"
        )

    if source_type == "candidate_first_party":
        if candidate_ids is None:
            _fail(f"{context} candidate_first_party requires candidate_ids")
        if organization is not None:
            _fail(f"{context} candidate_first_party must not set organization")
    elif source_type in {"party_first_party", "organizer_first_party"}:
        if organization is None:
            _fail(f"{context} {source_type} requires organization")
    elif candidate_ids is not None or organization is not None:
        _fail(f"{context} ownership fields are not relevant to {source_type}")

    normalized: dict[str, Any] = {
        "source_id": source_id,
        "publisher": publisher,
        "source_type": source_type,
        "url": url,
        "allowed_lanes": lanes,
        "allowed_event_types": event_types,
        "enabled": value["enabled"],
        "required": value["required"],
        "refresh_class": refresh_class,
        "zero_result_valid": value["zero_result_valid"],
    }
    if candidate_ids is not None:
        normalized["candidate_ids"] = candidate_ids
    if organization is not None:
        normalized["organization"] = organization
    if collection is not None:
        normalized["collection"] = collection
    return normalized


def normalize_campaign_event_source_registry(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
) -> dict[str, Any]:
    """Validate values and return a newly allocated, deterministically sorted registry."""

    if type(payload) is not dict:
        _fail("payload must be a plain dict")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, frozenset(), "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version must be exactly '2.0'")
    sources = payload["sources"]
    if not isinstance(sources, list):
        _fail("sources must be a list")

    candidate_by_id = _candidate_registry_by_id(candidate_registry_path)
    normalized_sources = [
        _normalize_source(
            source,
            index=index,
            candidate_by_id=candidate_by_id,
        )
        for index, source in enumerate(sources)
    ]

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for source in normalized_sources:
        if source["source_id"] in seen_ids:
            _fail(f"duplicate source_id: {source['source_id']}")
        if source["url"] in seen_urls:
            _fail(f"duplicate source URL: {source['url']}")
        seen_ids.add(source["source_id"])
        seen_urls.add(source["url"])

    normalized_sources.sort(key=lambda source: source["source_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": normalized_sources,
    }


def validate_campaign_event_source_registry(
    payload: Any,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
) -> None:
    """Validate a registry, including its canonical deterministic ordering."""

    normalized = normalize_campaign_event_source_registry(
        payload,
        candidate_registry_path=candidate_registry_path,
    )
    if payload != normalized:
        _fail("registry must use canonical values and deterministic source ordering")


def load_campaign_event_source_registry(
    path: str | Path,
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
) -> dict[str, Any]:
    """Load and validate one UTF-8 JSON registry from a supplied path."""

    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise CampaignEventSourceRegistryError(
            f"could not read Campaign Events source registry {target}: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CampaignEventSourceRegistryError(
            f"Campaign Events source registry {target} is malformed JSON: {error}"
        ) from error
    validate_campaign_event_source_registry(
        payload,
        candidate_registry_path=candidate_registry_path,
    )
    return normalize_campaign_event_source_registry(
        payload,
        candidate_registry_path=candidate_registry_path,
    )
