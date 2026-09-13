"""Deterministic canonicalization and identity for TRACE evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
from typing import Any


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class IdentityError(ValueError):
    """Raised when identity inputs cannot be represented canonically."""


def _normalized_text(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IdentityError(f"{label} must be valid UTF-8 text") from exc
    return normalized


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise IdentityError(f"{label} must be a non-empty string")
    normalized = _normalized_text(value, label)
    if normalized != normalized.strip():
        raise IdentityError(f"{label} must not have surrounding whitespace")
    return normalized


def _canonical_json_value(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _normalized_text(value, f"{path} string")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise IdentityError(f"{path} contains a non-finite number")
        if value == 0 or value.is_integer():
            return int(value)
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise IdentityError(f"{path} contains a non-string object key")
            key = _normalized_text(raw_key, f"{path} object key")
            if key in result:
                raise IdentityError(f"{path} contains duplicate normalized key {key!r}")
            result[key] = _canonical_json_value(item, f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise IdentityError(f"{path} contains non-JSON value of type {type(value).__name__}")


def canonicalize_evidence(evidence: Mapping[str, Any]) -> str:
    """Return stable UTF-8-ready JSON for exactly the selected evidence slice."""

    if not isinstance(evidence, Mapping):
        raise IdentityError("evidence must be a JSON object")
    canonical = _canonical_json_value(evidence)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def evidence_snapshot_hash(evidence: Mapping[str, Any]) -> str:
    """Hash a selected evidence slice, independent of its object-key order."""

    payload = canonicalize_evidence(evidence).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonicalize_primary_entity_ids(entity_ids: Sequence[str]) -> tuple[str, ...]:
    """Normalize and sort the set of primary entity IDs used by identity."""

    if isinstance(entity_ids, (str, bytes, bytearray)) or not isinstance(entity_ids, Sequence):
        raise IdentityError("primary_entity_ids must be a non-empty array")
    normalized = tuple(_text(item, "primary entity ID") for item in entity_ids)
    if not normalized:
        raise IdentityError("primary_entity_ids must be a non-empty array")
    if len(set(normalized)) != len(normalized):
        raise IdentityError("primary_entity_ids must not contain duplicates")
    return tuple(sorted(normalized))


def _canonical_boundary(value: Any, label: str) -> str:
    raw = _text(value, label)
    try:
        if "T" not in raw:
            return date.fromisoformat(raw).isoformat()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IdentityError(f"{label} must be an ISO 8601 date or timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IdentityError(f"{label} timestamp must include a UTC offset")
    utc_value = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return utc_value


def canonicalize_observation_window(window: Mapping[str, str]) -> dict[str, str]:
    """Validate and normalize the closed observation window."""

    if not isinstance(window, Mapping):
        raise IdentityError("observation_window must be an object")
    if set(window) != {"start", "end"}:
        raise IdentityError("observation_window must contain exactly start and end")
    start = _canonical_boundary(window["start"], "observation_window.start")
    end = _canonical_boundary(window["end"], "observation_window.end")
    if ("T" in start) != ("T" in end):
        raise IdentityError("observation_window boundaries must use the same precision")
    start_value = datetime.fromisoformat(start.replace("Z", "+00:00")) if "T" in start else date.fromisoformat(start)
    end_value = datetime.fromisoformat(end.replace("Z", "+00:00")) if "T" in end else date.fromisoformat(end)
    if end_value < start_value:
        raise IdentityError("observation_window.end must not precede start")
    return {"start": start, "end": end}


def trace_key(
    *,
    trace_schema_version: str,
    family: str,
    detector_id: str,
    primary_entity_ids: Sequence[str],
    observation_window: Mapping[str, str],
    evidence_snapshot_hash_value: str,
) -> str:
    """Return a deterministic key from the frozen TRACE identity fields."""

    schema_version = _text(trace_schema_version, "trace_schema_version")
    family_value = _text(family, "family")
    detector = _text(detector_id, "detector_id")
    if not isinstance(evidence_snapshot_hash_value, str) or not _SHA256_RE.fullmatch(
        evidence_snapshot_hash_value
    ):
        raise IdentityError("evidence_snapshot_hash must be a lowercase SHA-256 hex digest")
    payload = {
        "detector_id": detector,
        "evidence_snapshot_hash": evidence_snapshot_hash_value,
        "family": family_value,
        "observation_window": canonicalize_observation_window(observation_window),
        "primary_entity_ids": list(canonicalize_primary_entity_ids(primary_entity_ids)),
        "trace_schema_version": schema_version,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "trace_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
