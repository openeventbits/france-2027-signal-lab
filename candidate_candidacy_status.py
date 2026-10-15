"""Validation and projections for the candidacy-status source registry."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
from zoneinfo import ZoneInfo

from candidate_identity import (
    CandidateIdentityError,
    candidate_id,
    candidate_identity_map,
    canonical_candidate_name,
    normalized_candidate_key,
)

__all__ = [
    "CandidateCandidacyStatusError",
    "active_candidate_ids",
    "active_candidate_names",
    "active_candidate_records",
    "active_candidate_records_as_of",
    "candidate_state_as_of",
    "CuratedCandidacySource",
    "load_curated_candidacy_sources",
    "apply_lifecycle_events",
    "parse_candidacy_instant",
    "candidacy_status_by_id",
    "load_candidate_candidacy_status",
    "project_active_monitoring_field",
    "project_display_tiers",
    "semantic_candidate_registry",
    "semantic_sha256",
    "validate_candidate_candidacy_status",
]


class CandidateCandidacyStatusError(ValueError):
    """Raised when the candidacy-status registry violates its contract."""


_TOP_LEVEL_KEYS_V1 = frozenset(
    {
        "schema_version",
        "status_as_of",
        "candidates",
    }
)
_CANDIDATE_KEYS_V1 = frozenset(
    {
        "candidate_id",
        "candidate_name",
        "status",
        "display_tier",
        "status_as_of",
        "source_date",
        "source_url",
        "source_title",
        "source_publisher",
        "status_note",
    }
)
_TOP_LEVEL_KEYS_V2 = frozenset(
    {
        "schema_version",
        "status_as_of",
        "source",
        "candidates",
    }
)
_SOURCE_KEYS_V2 = frozenset(
    {
        "publisher",
        "page_title",
        "page_url",
        "revision_id",
        "revision_timestamp",
        "revision_url",
    }
)
_CANDIDATE_KEYS_V2 = _CANDIDATE_KEYS_V1 | frozenset(
    {
        "upstream_presence",
        "wikipedia_article",
        "previous_names",
    }
)
_ARTICLE_KEYS = frozenset({"page_id", "title", "url"})
_STATUS_TO_TIER = {
    "declared": "main",
    "party_selected": "main",
    "primary_contender": "main",
    "active_potential": "secondary",
    "conditional": "secondary",
    "ruled_out": "hidden",
    "withdrawn": "hidden",
    "primary_eliminated": "hidden",
    "historical_poll_only": "hidden",
}
def display_tier_for_status(status: str) -> str:
    """Return the canonical display tier for one candidacy status."""
    try:
        return _STATUS_TO_TIER[status]
    except (KeyError, TypeError) as error:
        raise CandidateCandidacyStatusError(
            f"unsupported candidacy status: {status!r}"
        ) from error


_DISPLAY_TIERS = frozenset({"main", "secondary", "hidden"})
_UPSTREAM_PRESENCE = frozenset({"present", "temporarily_missing"})
_CANDIDATE_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z"
)
_WIKIPEDIA_HOST = "fr.wikipedia.org"
_PROHIBITED_NOTE_LANGUAGE = re.compile(
    r"\b(?:"
    r"chance|confidence|forecast(?:s|ed|ing)?|momentum|odds|"
    r"poll(?:s|ed|ing)?|predict(?:s|ed|ing|ion|ions|ive)?|"
    r"probab(?:le|ility|ilities)|rank(?:s|ed|ing)?|"
    r"recommend(?:s|ed|ing|ation|ations)?|"
    r"scor(?:e|es|ed|ing)|viab(?:le|ility)"
    r")\b",
    re.IGNORECASE,
)
_PLACEHOLDER_HOST_LABELS = frozenset(
    {
        "example",
        "invalid",
        "placeholder",
        "test",
    }
)
_PLACEHOLDER_URL_MARKERS = (
    "<",
    ">",
    "{",
    "}",
    "[source",
    "replace-me",
    "replace_me",
    "todo",
    "your-source",
    "your_source",
)
def _fail(message: str) -> None:
    raise CandidateCandidacyStatusError(message)


def _require_exact_keys(
    value: dict[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        _fail(
            f"{context} must have exact keys; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _require_iso_date(value: Any, context: str) -> date:
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.fullmatch(value):
        _fail(f"{context} must be a canonical ISO YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CandidateCandidacyStatusError(
            f"{context} must be a valid canonical ISO YYYY-MM-DD date"
        ) from error
    if parsed.isoformat() != value:
        _fail(f"{context} must be a canonical ISO YYYY-MM-DD date")
    return parsed


def _require_trimmed_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{context} must be non-empty trimmed text")
    return value


def _require_source_url(value: Any, context: str) -> str:
    url = _require_trimmed_text(value, context)
    try:
        parsed = urlsplit(url)
        hostname_value = parsed.hostname
    except ValueError as error:
        raise CandidateCandidacyStatusError(
            f"{context} must be a well-formed absolute HTTPS URL"
        ) from error
    if parsed.scheme.lower() != "https":
        _fail(f"{context} must use absolute HTTPS")
    if not parsed.netloc or not hostname_value:
        _fail(f"{context} must have a non-empty host")

    hostname = hostname_value.rstrip(".").casefold()
    labels = set(hostname.split("."))
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname == "example.com"
        or hostname.endswith(".example.com")
        or labels & _PLACEHOLDER_HOST_LABELS
        or any(marker in url.casefold() for marker in _PLACEHOLDER_URL_MARKERS)
    ):
        _fail(f"{context} must not be localhost, example.com, or a placeholder")
    return url


def _require_utc_timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(value):
        _fail(f"{context} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidateCandidacyStatusError(
            f"{context} must be a valid canonical UTC timestamp"
        ) from error
    if parsed.tzinfo != timezone.utc:
        _fail(f"{context} must be UTC")
    return value


def _canonical_wikipedia_url(title: str) -> str:
    article_path = quote(title.replace(" ", "_"), safe="()_-")
    return f"https://{_WIKIPEDIA_HOST}/wiki/{article_path}"


def _validate_v2_source(value: Any) -> None:
    if type(value) is not dict:
        _fail("source must be a plain dict")
    _require_exact_keys(value, _SOURCE_KEYS_V2, "source")
    if _require_trimmed_text(value["publisher"], "source.publisher") != (
        "French Wikipedia"
    ):
        _fail("source.publisher must equal 'French Wikipedia'")
    page_title = _require_trimmed_text(
        value["page_title"],
        "source.page_title",
    )
    page_url = _require_source_url(value["page_url"], "source.page_url")
    if urlsplit(page_url).hostname.casefold() != _WIKIPEDIA_HOST:
        _fail("source.page_url must use fr.wikipedia.org")
    if page_url != _canonical_wikipedia_url(page_title):
        _fail("source.page_url is not canonical for source.page_title")
    revision_id = value["revision_id"]
    if type(revision_id) is not int or revision_id <= 0:
        _fail("source.revision_id must be a positive integer")
    _require_utc_timestamp(
        value["revision_timestamp"],
        "source.revision_timestamp",
    )
    revision_url = _require_source_url(
        value["revision_url"],
        "source.revision_url",
    )
    parsed_revision_url = urlsplit(revision_url)
    if parsed_revision_url.hostname.casefold() != _WIKIPEDIA_HOST:
        _fail("source.revision_url must use fr.wikipedia.org")
    revision_query = parse_qs(
        parsed_revision_url.query,
        keep_blank_values=True,
    )
    if (
        parsed_revision_url.path != "/w/index.php"
        or parsed_revision_url.fragment
        or revision_query != {
            "title": [page_title],
            "oldid": [str(revision_id)],
        }
    ):
        _fail(
            "source.revision_url must identify the exact configured page "
            "and source.revision_id"
        )


def _validate_wikipedia_article(value: Any, context: str) -> None:
    if value is None:
        return
    if type(value) is not dict:
        _fail(f"{context} must be null or a plain dict")
    _require_exact_keys(value, _ARTICLE_KEYS, context)
    page_id = value["page_id"]
    if type(page_id) is not int or page_id <= 0:
        _fail(f"{context}.page_id must be a positive integer")
    title = _require_trimmed_text(value["title"], f"{context}.title")
    url = _require_source_url(value["url"], f"{context}.url")
    if url != _canonical_wikipedia_url(title):
        _fail(f"{context}.url is not canonical for its title")


def _validate_previous_names(
    value: Any,
    *,
    candidate_name: str,
    context: str,
) -> list[str]:
    if not isinstance(value, list):
        _fail(f"{context} must be a list")
    canonical_names: list[str] = []
    seen: set[str] = set()
    for index, prior_name in enumerate(value):
        field = f"{context}[{index}]"
        try:
            canonical = canonical_candidate_name(prior_name)
        except CandidateIdentityError as error:
            raise CandidateCandidacyStatusError(
                f"{field} is invalid: {error}"
            ) from error
        if canonical != prior_name:
            _fail(f"{field} must be canonical")
        if canonical == candidate_name:
            _fail(f"{context} must exclude the current candidate_name")
        if canonical in seen:
            _fail(f"{context} must contain unique names")
        seen.add(canonical)
        canonical_names.append(canonical)
    expected = sorted(canonical_names, key=lambda name: (name.casefold(), name))
    if canonical_names != expected:
        _fail(f"{context} must be deterministically ordered")
    return canonical_names


def _validate_candidate_universe(
    candidates: list[dict[str, Any]],
    candidate_universe: Any,
) -> None:
    if not isinstance(candidate_universe, list):
        _fail("candidate_universe must be a list")

    universe_by_id: dict[str, str] = {}
    for index, value in enumerate(candidate_universe):
        context = f"candidate_universe[{index}]"
        if type(value) is not dict:
            _fail(f"{context} must be a plain dict")
        identifier = value.get("candidate_id")
        name = value.get("candidate_name")
        if not isinstance(identifier, str):
            _fail(f"{context}.candidate_id must be a string")
        if identifier in universe_by_id:
            _fail(f"candidate_universe has duplicate candidate ID: {identifier}")
        try:
            canonical_name = canonical_candidate_name(name)
        except CandidateIdentityError as error:
            raise CandidateCandidacyStatusError(
                f"{context}.candidate_name is invalid: {error}"
            ) from error
        if canonical_name != name:
            _fail(f"{context}.candidate_name must be canonical")
        universe_by_id[identifier] = name

    registry_by_id = {
        candidate["candidate_id"]: candidate["candidate_name"]
        for candidate in candidates
    }
    registry_ids = set(registry_by_id)
    universe_ids = set(universe_by_id)
    missing_ids = sorted(registry_ids - universe_ids)
    unknown_ids = sorted(universe_ids - registry_ids)
    if unknown_ids:
        _fail(f"candidate_universe has unknown candidate IDs: {unknown_ids}")
    if missing_ids:
        _fail(f"candidate_universe is missing registry IDs: {missing_ids}")
    for identifier, registry_name in registry_by_id.items():
        if universe_by_id[identifier] != registry_name:
            _fail(
                "candidate_universe canonical name mismatch for "
                f"{identifier}: expected {registry_name!r}, "
                f"got {universe_by_id[identifier]!r}"
            )


def validate_candidate_candidacy_status(
    payload: Any,
    candidate_universe: Any = None,
) -> None:
    """Validate the complete candidacy-status source contract.

    ``candidate_universe`` may be a Candidate Signals candidate list. When
    supplied, its candidate IDs and canonical names must have exact parity
    with the registry, regardless of the current candidate count.
    """

    if type(payload) is not dict:
        _fail("payload must be a plain dict")
    if "schema_version" not in payload:
        _require_exact_keys(payload, _TOP_LEVEL_KEYS_V1, "payload")
    schema_version = payload.get("schema_version")
    if schema_version == "1.0":
        _require_exact_keys(payload, _TOP_LEVEL_KEYS_V1, "payload")
        is_v2 = False
    elif schema_version == "2.0":
        _require_exact_keys(payload, _TOP_LEVEL_KEYS_V2, "payload")
        _validate_v2_source(payload["source"])
        is_v2 = True
    else:
        _fail("schema_version must be exactly '1.0' or '2.0'")

    top_status_date = _require_iso_date(
        payload["status_as_of"],
        "status_as_of",
    )
    if is_v2 and payload["status_as_of"] < payload["source"]["revision_timestamp"][:10]:
        _fail("status_as_of cannot precede the accepted source revision date")
    candidates = payload["candidates"]
    if not isinstance(candidates, list) or not candidates:
        _fail("candidates must be a non-empty list")
    identifiers: set[str] = set()
    canonical_names: set[str] = set()
    normalized_names: dict[str, str] = {}
    identity_names: list[str] = []
    identity_alias_owners: dict[str, str] = {}
    article_page_owners: dict[int, str] = {}
    source_metadata_by_url: dict[str, tuple[str, str, str]] = {}
    for index, value in enumerate(candidates):
        context = f"candidates[{index}]"
        if type(value) is not dict:
            _fail(f"{context} must be a plain dict")
        _require_exact_keys(
            value,
            _CANDIDATE_KEYS_V2 if is_v2 else _CANDIDATE_KEYS_V1,
            context,
        )

        identifier = value["candidate_id"]
        if (
            not isinstance(identifier, str)
            or not _CANDIDATE_ID_PATTERN.fullmatch(identifier)
        ):
            _fail(f"{context}.candidate_id must be lowercase ASCII kebab-case")

        name = value["candidate_name"]
        try:
            canonical_name = canonical_candidate_name(name)
        except CandidateIdentityError as error:
            raise CandidateCandidacyStatusError(
                f"{context}.candidate_name is invalid: {error}"
            ) from error
        if canonical_name != name:
            _fail(f"{context}.candidate_name must be canonical")
        if name in canonical_names:
            _fail(f"duplicate canonical candidate name: {name}")
        normalized_name = normalized_candidate_key(name)
        prior_normalized_name = normalized_names.get(normalized_name)
        if prior_normalized_name is not None:
            _fail(
                "normalized candidate identity collision between "
                f"{prior_normalized_name!r} and {name!r}"
            )
        if identifier in identifiers:
            _fail(f"duplicate candidate ID: {identifier}")
        if not is_v2 and identifier != candidate_id(name):
            _fail(f"{context}.candidate_id does not match candidate_name")
        identifiers.add(identifier)
        canonical_names.add(name)
        normalized_names[normalized_name] = name
        identity_names.append(name)

        previous_names: list[str] = []
        if is_v2:
            presence = value["upstream_presence"]
            if presence not in _UPSTREAM_PRESENCE:
                _fail(
                    f"{context}.upstream_presence is not allowed: "
                    f"{presence!r}"
                )
            previous_names = _validate_previous_names(
                value["previous_names"],
                candidate_name=name,
                context=f"{context}.previous_names",
            )
            _validate_wikipedia_article(
                value["wikipedia_article"],
                f"{context}.wikipedia_article",
            )
            article = value["wikipedia_article"]
            if article is not None:
                page_id = article["page_id"]
                prior_owner = article_page_owners.get(page_id)
                if prior_owner is not None:
                    _fail(
                        "duplicate wikipedia_article.page_id between "
                        f"{prior_owner!r} and {identifier!r}"
                    )
                article_page_owners[page_id] = identifier

        for identity_name in [name, *previous_names]:
            alias_key = normalized_candidate_key(identity_name)
            prior_owner = identity_alias_owners.get(alias_key)
            if prior_owner is not None and prior_owner != identifier:
                _fail(
                    "normalized candidate identity alias collision between "
                    f"{prior_owner!r} and {identifier!r}: {identity_name!r}"
                )
            identity_alias_owners[alias_key] = identifier

        status = value["status"]
        if not isinstance(status, str) or status not in _STATUS_TO_TIER:
            _fail(f"{context}.status is not allowed: {status!r}")
        tier = value["display_tier"]
        if not isinstance(tier, str) or tier not in _DISPLAY_TIERS:
            _fail(f"{context}.display_tier is not allowed: {tier!r}")
        expected_tier = _STATUS_TO_TIER[status]
        if tier != expected_tier:
            _fail(
                f"{context} status {status!r} requires "
                f"display_tier {expected_tier!r}"
            )
        entry_status_date = _require_iso_date(
            value["status_as_of"],
            f"{context}.status_as_of",
        )
        source_date = _require_iso_date(
            value["source_date"],
            f"{context}.source_date",
        )
        if entry_status_date < source_date:
            _fail(f"{context}.status_as_of cannot precede source_date")
        if top_status_date < entry_status_date:
            _fail(
                "top-level status_as_of cannot precede "
                f"{context}.status_as_of"
            )

        source_url = _require_source_url(
            value["source_url"],
            f"{context}.source_url",
        )
        source_title = _require_trimmed_text(
            value["source_title"],
            f"{context}.source_title",
        )
        source_publisher = _require_trimmed_text(
            value["source_publisher"],
            f"{context}.source_publisher",
        )
        status_note = _require_trimmed_text(
            value["status_note"],
            f"{context}.status_note",
        )
        if _PROHIBITED_NOTE_LANGUAGE.search(status_note):
            _fail(
                f"{context}.status_note contains prohibited scoring, "
                "prediction, viability, probability, polling, ranking, "
                "or recommendation language"
            )

        source_metadata = (
            value["source_date"],
            source_title,
            source_publisher,
        )
        prior_source_metadata = source_metadata_by_url.get(source_url)
        if (
            prior_source_metadata is not None
            and prior_source_metadata != source_metadata
        ):
            _fail(
                f"{context}.source_url reuses a URL with conflicting "
                "source metadata"
            )
        source_metadata_by_url[source_url] = source_metadata

    if not is_v2:
        try:
            candidate_identity_map(identity_names)
        except CandidateIdentityError as error:
            raise CandidateCandidacyStatusError(
                f"candidate identity collision: {error}"
            ) from error

    expected_order = sorted(
        candidates,
        key=lambda candidate: (
            candidate["candidate_name"].casefold(),
            candidate["candidate_id"],
        ),
    )
    if candidates != expected_order:
        _fail(
            "candidates must be ordered by "
            "candidate_name.casefold(), then candidate_id"
        )

    if candidate_universe is not None:
        _validate_candidate_universe(candidates, candidate_universe)


def load_candidate_candidacy_status(
    path: str | Path,
) -> dict[str, Any]:
    """Load UTF-8 JSON from ``path``, validate it, and return the payload."""

    with Path(path).open("r", encoding="utf-8") as registry_file:
        payload = json.load(registry_file)
    validate_candidate_candidacy_status(payload)
    return payload


def candidacy_status_by_id(
    payload: Any,
) -> dict[str, dict[str, Any]]:
    """Return validated registry entries keyed by candidate ID."""

    validate_candidate_candidacy_status(payload)
    return {
        candidate["candidate_id"]: candidate
        for candidate in payload["candidates"]
    }


def _upstream_presence(candidate: dict[str, Any]) -> str:
    """Return explicit v2 presence or the implicit v1 legacy state."""

    return candidate.get("upstream_presence", "present")


def _is_active_candidate(candidate: dict[str, Any]) -> bool:
    """Apply the one canonical active-monitoring eligibility rule."""

    return (
        candidate["display_tier"] in {"main", "secondary"}
        and _upstream_presence(candidate) == "present"
    )


def active_candidate_records(payload: Any) -> list[dict[str, Any]]:
    """Return main/secondary records that are currently present upstream."""

    validate_candidate_candidacy_status(payload)
    return [
        candidate
        for candidate in payload["candidates"]
        if _is_active_candidate(candidate)
    ]


def active_candidate_ids(payload: Any) -> list[str]:
    """Return active-monitoring candidate IDs in deterministic registry order."""

    return [
        candidate["candidate_id"]
        for candidate in active_candidate_records(payload)
    ]


def active_candidate_names(payload: Any) -> list[str]:
    """Return active-monitoring candidate names in deterministic registry order."""

    return [
        candidate["candidate_name"]
        for candidate in active_candidate_records(payload)
    ]


def active_projection_provenance(payload: Any) -> dict[str, Any]:
    """Return exact Registry-v2 provenance for downstream active projections."""

    validate_candidate_candidacy_status(payload)
    if payload.get("schema_version") != "2.0":
        raise CandidateCandidacyStatusError(
            "active projection provenance requires Candidate Registry schema 2.0"
        )

    source = payload["source"]
    return {
        "source": "candidate_candidacy_status.json",
        "source_revision_id": source["revision_id"],
        "source_revision_timestamp": source["revision_timestamp"],
        "status_as_of": payload["status_as_of"],
        "rule": "active_monitoring_field",
    }


def project_display_tiers(payload: Any) -> dict[str, Any]:
    """Project complete stored political/display-tier membership."""

    validate_candidate_candidacy_status(payload)
    tiers = {
        tier: [
            candidate["candidate_id"]
            for candidate in payload["candidates"]
            if candidate["display_tier"] == tier
        ]
        for tier in ("main", "secondary", "hidden")
    }
    counts = {
        "main": len(tiers["main"]),
        "secondary": len(tiers["secondary"]),
        "hidden": len(tiers["hidden"]),
        "total": len(payload["candidates"]),
    }
    return {
        "status_as_of": payload["status_as_of"],
        **tiers,
        "counts": counts,
    }


def project_active_monitoring_field(payload: Any) -> dict[str, Any]:
    """Project the effective present main/secondary monitoring universe."""

    records = active_candidate_records(payload)
    tiers = {
        tier: [
            candidate["candidate_id"]
            for candidate in records
            if candidate["display_tier"] == tier
        ]
        for tier in ("main", "secondary")
    }
    return {
        "main": tiers["main"],
        "secondary": tiers["secondary"],
        "counts": {
            "main": len(tiers["main"]),
            "secondary": len(tiers["secondary"]),
            "active": len(records),
        },
    }


def semantic_candidate_registry(payload: Any) -> dict[str, Any]:
    """Return provenance-free, order-independent registry semantics."""

    validate_candidate_candidacy_status(payload)
    candidates = []
    for candidate in payload["candidates"]:
        article = candidate.get("wikipedia_article")
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate["candidate_name"],
                "status": candidate["status"],
                "display_tier": candidate["display_tier"],
                "upstream_presence": _upstream_presence(candidate),
                "active_monitoring_eligible": _is_active_candidate(candidate),
                "wikipedia_article": (
                    None
                    if article is None
                    else {
                        "page_id": article["page_id"],
                        "title": article["title"],
                        "url": article["url"],
                    }
                ),
                "previous_names": sorted(
                    candidate.get("previous_names", []),
                    key=lambda name: (name.casefold(), name),
                ),
            }
        )
    candidates.sort(key=lambda candidate: candidate["candidate_id"])
    return {
        "schema_version": payload["schema_version"],
        "candidates": candidates,
    }


def semantic_sha256(payload: Any) -> str:
    """Return SHA-256 over canonical registry semantics only."""

    semantic = semantic_candidate_registry(payload)
    serialized = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True)
class CuratedCandidacySource:
    source_id: str
    candidate_id: str
    candidate_name: str
    source_type: str
    publisher: str
    url: str
    source_date: str
    source_title: str
    status: str
    status_as_of: str
    status_note: str
    effective_at: str | None = None
    event_type: str | None = None
    prior_status: str | None = None


def parse_candidacy_instant(value: str) -> datetime:
    """Parse a canonical UTC evidence boundary without reducing its precision."""
    if not isinstance(value, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(value):
        _fail("lifecycle timestamp must be canonical UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidateCandidacyStatusError("invalid lifecycle timestamp") from error


def load_curated_candidacy_sources(
    path: str | Path = Path(__file__).with_name("candidate_candidacy_sources.json"),
) -> tuple[CuratedCandidacySource, ...]:
    """Load curated evidence, including effective-dated authoritative events."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateCandidacyStatusError(
            f"could not load candidacy source inventory: {error}"
        ) from error

    if type(payload) is not dict or set(payload) != {"schema_version", "sources"}:
        _fail("candidacy source inventory must contain schema_version and sources")
    if payload["schema_version"] != "1.0":
        _fail("candidacy source inventory schema_version must be exactly '1.0'")
    if not isinstance(payload["sources"], list):
        _fail("candidacy source inventory sources must be a list")

    expected_keys = {
        "source_id",
        "candidate_id",
        "candidate_name",
        "source_type",
        "publisher",
        "url",
        "source_date",
        "source_title",
        "status",
        "status_as_of",
        "status_note",
        "enabled",
    }
    allowed_source_types = {"candidate_first_party", "party_first_party"}
    records: list[CuratedCandidacySource] = []
    seen_source_ids: set[str] = set()
    seen_candidate_ids: set[str] = set()
    seen_event_instants: set[tuple[str, str]] = set()

    for index, value in enumerate(payload["sources"]):
        context = f"candidacy source inventory sources[{index}]"
        is_event = isinstance(value, dict) and "effective_at" in value
        keys = expected_keys | {"effective_at", "event_type"} if is_event else expected_keys
        if is_event and "prior_status" in value:
            keys = keys | {"prior_status"}
        if type(value) is not dict or set(value) != keys:
            _fail(f"{context} has invalid keys")
        if type(value["enabled"]) is not bool:
            _fail(f"{context}.enabled must be a boolean")
        if not value["enabled"]:
            continue

        for field in (
            "source_id",
            "candidate_id",
            "candidate_name",
            "publisher",
            "url",
            "source_date",
            "source_title",
            "status",
            "status_as_of",
            "status_note",
        ):
            if not isinstance(value[field], str) or not value[field].strip():
                _fail(f"{context}.{field} must be non-empty text")

        if value["source_type"] not in allowed_source_types and not (
            is_event and value["source_type"] == "primary_result_report"
            and value["event_type"] == "primary_result"
        ):
            _fail(f"{context}.source_type must be first-party or a primary-result report")
        if not value["url"].startswith("https://"):
            _fail(f"{context}.url must use HTTPS")

        try:
            source_date = datetime.strptime(
                value["source_date"], "%Y-%m-%d"
            ).date()
            status_as_of = datetime.strptime(
                value["status_as_of"], "%Y-%m-%d"
            ).date()
        except ValueError as error:
            raise CandidateCandidacyStatusError(
                f"{context} has an invalid ISO date"
            ) from error
        if status_as_of < source_date:
            _fail(f"{context}.status_as_of cannot precede source_date")

        if is_event:
            if not isinstance(value["event_type"], str):
                _fail(f"{context}.event_type must be text")
            if "prior_status" in value:
                display_tier_for_status(value["prior_status"])
            effective = parse_candidacy_instant(value["effective_at"])
            if not source_date <= effective.date() <= status_as_of:
                _fail(f"{context}.effective_at must fall between source_date and status_as_of")
            event_statuses = {
                "primary_result": {"party_selected", "primary_eliminated"},
                "declaration": {"declared"},
                "withdrawal": {"withdrawn"},
                "selection": {"party_selected"},
                "ruled_out": {"ruled_out"},
            }
            if value["status"] not in event_statuses.get(value["event_type"], set()):
                _fail(f"{context} has incompatible event_type and status")
            event_key = (value["candidate_id"], value["effective_at"])
            if event_key in seen_event_instants:
                _fail(f"ambiguous simultaneous lifecycle events: {event_key}")
            seen_event_instants.add(event_key)

        try:
            candidate_id(value["candidate_name"])
            display_tier_for_status(value["status"])
        except (CandidateIdentityError, CandidateCandidacyStatusError) as error:
            raise CandidateCandidacyStatusError(
                f"{context} is invalid: {error}"
            ) from error
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value["candidate_id"]) is None:
            _fail(f"{context}.candidate_id must be lowercase ASCII kebab-case")

        if value["source_id"] in seen_source_ids:
            _fail(f"duplicate candidacy source_id: {value['source_id']}")
        if not is_event and value["candidate_id"] in seen_candidate_ids:
            _fail(
                "multiple enabled curated candidacy sources for candidate: "
                f"{value['candidate_id']}"
            )
        seen_source_ids.add(value["source_id"])
        if not is_event:
            seen_candidate_ids.add(value["candidate_id"])

        records.append(
            CuratedCandidacySource(
                source_id=value["source_id"],
                candidate_id=value["candidate_id"],
                candidate_name=value["candidate_name"],
                source_type=value["source_type"],
                publisher=value["publisher"],
                url=value["url"],
                source_date=value["source_date"],
                source_title=value["source_title"],
                status=value["status"],
                status_as_of=value["status_as_of"],
                status_note=value["status_note"],
                effective_at=value.get("effective_at"),
                event_type=value.get("event_type"),
                prior_status=value.get("prior_status"),
            )
        )

    ordered = tuple(sorted(records, key=lambda item: (item.candidate_id, item.effective_at or "")))
    previous_events: dict[str, CuratedCandidacySource] = {}
    for source in ordered:
        if source.effective_at is None:
            continue
        previous = previous_events.get(source.candidate_id)
        if (previous is not None and source.prior_status is not None
                and source.prior_status != previous.status):
            _fail(f"inconsistent prior_status for lifecycle event: {source.source_id}")
        previous_events[source.candidate_id] = source
    return ordered


def apply_lifecycle_events(
    records: list[dict[str, Any]],
    sources: tuple[CuratedCandidacySource, ...],
    *,
    as_of: str,
) -> None:
    """Apply the latest effective authoritative event, independently of page presence.

    Wikipedia revision dates describe page edits, not new candidacy decisions.
    Only a newer dated authoritative event supersedes an accepted lifecycle event.
    Historical rebuilds must use a last-good registry from that historical period.
    """
    instant = parse_candidacy_instant(as_of)
    by_id = {record["candidate_id"]: record for record in records}
    latest = latest_lifecycle_events(sources, as_of=instant)
    for identifier, source in latest.items():
        record = by_id.get(identifier)
        if record is None or normalized_candidate_key(source.candidate_name) not in {
            normalized_candidate_key(name)
            for name in [record["candidate_name"], *record.get("previous_names", [])]
        }:
            _fail(f"lifecycle event does not match a registered identity: {identifier}")
        record.update({
            "status": source.status,
            "display_tier": display_tier_for_status(source.status),
            "status_as_of": source.effective_at[:10],
            "source_date": source.source_date,
            "source_url": source.url,
            "source_title": source.source_title,
            "source_publisher": source.publisher,
            "status_note": source.status_note,
        })


def latest_lifecycle_events(
    sources: tuple[CuratedCandidacySource, ...], *, as_of: datetime,
) -> dict[str, CuratedCandidacySource]:
    """Select authoritative decisions with the same cutoff for every consumer."""
    latest: dict[str, CuratedCandidacySource] = {}
    seen_instants: set[tuple[str, str]] = set()
    for source in sources:
        if source.effective_at is None:
            continue
        event_key = (source.candidate_id, source.effective_at)
        if event_key in seen_instants:
            _fail(f"ambiguous simultaneous lifecycle events: {event_key}")
        seen_instants.add(event_key)
        if parse_candidacy_instant(source.effective_at) > as_of:
            continue
        previous = latest.get(source.candidate_id)
        if previous is None or source.effective_at > previous.effective_at:
            latest[source.candidate_id] = source
    return latest


def candidacy_evaluation_instant(effective_at: str) -> datetime:
    """Evaluate dates at Paris day start; evaluate aware datetimes exactly."""
    try:
        if _ISO_DATE_PATTERN.fullmatch(effective_at):
            return datetime.combine(date.fromisoformat(effective_at), datetime.min.time(),
                                    tzinfo=ZoneInfo("Europe/Paris"))
        instant = datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            _fail("candidacy evaluation requires a date or timezone-aware datetime")
        return instant
    except (TypeError, ValueError) as error:
        raise CandidateCandidacyStatusError("invalid candidacy evaluation date/time") from error


def candidate_state_as_of(
    candidate: dict[str, Any], effective_at: str, *,
    sources: tuple[CuratedCandidacySource, ...],
) -> str | None:
    """Project recorded candidacy decisions, never reverse today's display tier.

    The first event's explicit prior_status supplies the preceding baseline.
    Missing prior evidence returns None before that event. Identities without
    a dated ledger retain legacy registry semantics; this is not a full archive
    of upstream presence, name changes, or undated candidacy decisions.
    """
    instant = candidacy_evaluation_instant(effective_at)
    history = tuple(
        source for source in sources
        if source.candidate_id == candidate["candidate_id"] and source.effective_at
    )
    if not history:
        return candidate["status"]
    for source in history:
        if normalized_candidate_key(source.candidate_name) not in {
            normalized_candidate_key(name)
            for name in [candidate["candidate_name"], *candidate.get("previous_names", [])]
        }:
            _fail(f"lifecycle event does not match a registered identity: {source.candidate_id}")
    latest = latest_lifecycle_events(history, as_of=instant)
    decision = latest.get(candidate["candidate_id"])
    if decision:
        return decision.status
    return min(history, key=lambda source: source.effective_at).prior_status


def active_candidate_records_as_of(
    payload: Any, effective_at: str, *,
    sources: tuple[CuratedCandidacySource, ...] | None = None,
) -> list[dict[str, Any]]:
    """Select registry records eligible at event time, retaining their metadata.

    Use candidate_state_as_of for the projected status; returned records are
    identity/evidence snapshots and may have a different current status.
    """
    validate_candidate_candidacy_status(payload)
    candidacy_evaluation_instant(effective_at)
    if sources is None:
        sources = load_curated_candidacy_sources()
    dated_ids = {source.candidate_id for source in sources if source.effective_at}
    records = []
    for candidate in payload["candidates"]:
        if candidate["candidate_id"] not in dated_ids:
            eligible = _is_active_candidate(candidate)
        else:
            status = candidate_state_as_of(candidate, effective_at, sources=sources)
            eligible = status is not None and display_tier_for_status(status) in {"main", "secondary"}
        if eligible:
            records.append(candidate)
    return records
