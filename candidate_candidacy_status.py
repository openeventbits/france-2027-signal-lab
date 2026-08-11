"""Validation and projections for the candidacy-status source registry."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from candidate_identity import (
    CandidateIdentityError,
    candidate_id,
    candidate_identity_map,
    canonical_candidate_name,
    normalized_candidate_key,
)

__all__ = [
    "CandidateCandidacyStatusError",
    "candidacy_status_by_id",
    "load_candidate_candidacy_status",
    "project_display_tiers",
    "validate_candidate_candidacy_status",
]


class CandidateCandidacyStatusError(ValueError):
    """Raised when the candidacy-status registry violates its contract."""


_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "status_as_of",
        "candidates",
    }
)
_CANDIDATE_KEYS = frozenset(
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
_DISPLAY_TIERS = frozenset({"main", "secondary", "hidden"})
_CANDIDATE_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
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
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "payload")
    if payload["schema_version"] != "1.0":
        _fail("schema_version must be exactly '1.0'")

    top_status_date = _require_iso_date(
        payload["status_as_of"],
        "status_as_of",
    )
    candidates = payload["candidates"]
    if not isinstance(candidates, list) or not candidates:
        _fail("candidates must be a non-empty list")
    identifiers: set[str] = set()
    canonical_names: set[str] = set()
    normalized_names: dict[str, str] = {}
    identity_names: list[str] = []
    source_metadata_by_url: dict[str, tuple[str, str, str]] = {}
    for index, value in enumerate(candidates):
        context = f"candidates[{index}]"
        if type(value) is not dict:
            _fail(f"{context} must be a plain dict")
        _require_exact_keys(value, _CANDIDATE_KEYS, context)

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
        if identifier != candidate_id(name):
            _fail(f"{context}.candidate_id does not match candidate_name")
        identifiers.add(identifier)
        canonical_names.add(name)
        normalized_names[normalized_name] = name
        identity_names.append(name)

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


def project_display_tiers(payload: Any) -> dict[str, Any]:
    """Project ordered candidate IDs and counts without writing a file."""

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
    }
    counts["active"] = counts["main"] + counts["secondary"]
    counts["total"] = counts["active"] + counts["hidden"]
    return {
        "status_as_of": payload["status_as_of"],
        **tiers,
        "counts": counts,
    }
