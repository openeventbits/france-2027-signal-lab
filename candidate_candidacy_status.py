"""Validation and projections for the candidacy-status source registry."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

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
    "historical_poll_only": "hidden",
}
def display_tier_for_status(status: str) -> str:
    """Return the canonical display tier for one candidacy status."""
    try:
        return _STATUS_TO_TIER[status]
    except KeyError as error:
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
