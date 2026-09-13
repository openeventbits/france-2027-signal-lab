"""Validation and construction of the frozen TRACE v1 draft object."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from typing import Any

from .identity import (
    IdentityError,
    canonicalize_evidence,
    canonicalize_observation_window,
    canonicalize_primary_entity_ids,
    evidence_snapshot_hash,
    trace_key,
)


TRACE_SCHEMA_VERSION = "1"
VALID_FAMILIES = frozenset({"candidate", "field", "issue", "story", "event"})
AVAILABILITY_STATES = frozenset(
    {"observed", "not_observed", "unavailable", "not_applicable"}
)

_REQUIRED_FIELDS = frozenset(
    {
        "trace_schema_version",
        "status",
        "family",
        "detector_id",
        "primary_entity_ids",
        "observation_window",
        "evidence",
        "evidence_snapshot_hash",
        "trace_key",
    }
)
_OPTIONAL_FIELDS = frozenset(
    {"language", "generated_at", "renderer_version", "upstream_provenance"}
)


class ContractError(ValueError):
    """Raised when an object does not satisfy the TRACE v1 contract."""


def _contract_guard(operation: Any) -> Any:
    try:
        return operation()
    except IdentityError as exc:
        raise ContractError(str(exc)) from exc


def _validate_availability(value: Any, path: str = "evidence") -> int:
    """Validate the reserved availability key in every nested evidence mapping.

    Within evidence, any mapping containing ``availability`` is a TRACE
    availability record. The key is reserved and cannot carry other semantics.
    """

    count = 0
    if isinstance(value, Mapping):
        if "availability" in value:
            count += 1
            state = value["availability"]
            if not isinstance(state, str) or state not in AVAILABILITY_STATES:
                raise ContractError(f"{path}.availability is not a valid availability state")
            if state == "observed":
                if "value" not in value or value["value"] is None:
                    raise ContractError(f"{path} observed evidence requires a non-null value")
            elif "value" in value:
                raise ContractError(f"{path} non-observed evidence must not contain value")
        for key, item in value.items():
            count += _validate_availability(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            count += _validate_availability(item, f"{path}[{index}]")
    return count


def _validate_optional_metadata(trace: Mapping[str, Any]) -> None:
    if "language" in trace and trace["language"] not in {"fr", "en"}:
        raise ContractError("language must be fr or en")
    for field in ("renderer_version",):
        if field in trace and (not isinstance(trace[field], str) or not trace[field]):
            raise ContractError(f"{field} must be a non-empty string")
    if "generated_at" in trace:
        generated_at = trace["generated_at"]
        if not isinstance(generated_at, str):
            raise ContractError("generated_at must be an ISO 8601 timestamp")
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError("generated_at must be an ISO 8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ContractError("generated_at must include a UTC offset")
    if "upstream_provenance" in trace:
        provenance = trace["upstream_provenance"]
        if not isinstance(provenance, Mapping):
            raise ContractError("upstream_provenance must be an object")
        _contract_guard(lambda: canonicalize_evidence(provenance))


def validate_trace(trace: Mapping[str, Any]) -> None:
    """Validate a complete TRACE v1 draft and verify both identity digests."""

    if not isinstance(trace, Mapping):
        raise ContractError("TRACE must be an object")
    if any(not isinstance(field, str) for field in trace):
        raise ContractError("TRACE field names must be strings")
    fields = set(trace)
    missing = _REQUIRED_FIELDS - fields
    if missing:
        raise ContractError(f"TRACE is missing required fields: {', '.join(sorted(missing))}")
    if "public_serial" in trace:
        raise ContractError("draft TRACE objects must not contain public_serial")
    unknown = fields - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unknown:
        raise ContractError(f"TRACE contains unknown fields: {', '.join(sorted(unknown))}")
    if trace["trace_schema_version"] != TRACE_SCHEMA_VERSION:
        raise ContractError(f"trace_schema_version must be {TRACE_SCHEMA_VERSION!r}")
    if trace["status"] != "draft":
        raise ContractError("status must be draft")
    if not isinstance(trace["family"], str) or trace["family"] not in VALID_FAMILIES:
        raise ContractError("family is not a valid public TRACE family")
    if not isinstance(trace["detector_id"], str) or not trace["detector_id"]:
        raise ContractError("detector_id must be a non-empty, versioned identifier")

    canonical_ids = _contract_guard(
        lambda: canonicalize_primary_entity_ids(trace["primary_entity_ids"])
    )
    if list(canonical_ids) != trace["primary_entity_ids"]:
        raise ContractError("primary_entity_ids must be stored in canonical sorted order")
    canonical_window = _contract_guard(
        lambda: canonicalize_observation_window(trace["observation_window"])
    )
    if canonical_window != trace["observation_window"]:
        raise ContractError("observation_window must be stored in canonical form")
    if not isinstance(trace["evidence"], Mapping):
        raise ContractError("evidence must be an object")
    _contract_guard(lambda: canonicalize_evidence(trace["evidence"]))
    if _validate_availability(trace["evidence"]) == 0:
        raise ContractError("evidence must contain at least one availability state")

    expected_evidence_hash = _contract_guard(
        lambda: evidence_snapshot_hash(trace["evidence"])
    )
    if trace["evidence_snapshot_hash"] != expected_evidence_hash:
        raise ContractError("evidence_snapshot_hash does not match selected evidence")
    expected_trace_key = _contract_guard(
        lambda: trace_key(
            trace_schema_version=trace["trace_schema_version"],
            family=trace["family"],
            detector_id=trace["detector_id"],
            primary_entity_ids=trace["primary_entity_ids"],
            observation_window=trace["observation_window"],
            evidence_snapshot_hash_value=expected_evidence_hash,
        )
    )
    if trace["trace_key"] != expected_trace_key:
        raise ContractError("trace_key does not match the TRACE identity fields")
    _validate_optional_metadata(trace)


def build_draft_trace(
    *,
    family: str,
    detector_id: str,
    primary_entity_ids: list[str] | tuple[str, ...],
    observation_window: Mapping[str, str],
    evidence: Mapping[str, Any],
    language: str | None = None,
    generated_at: str | None = None,
    renderer_version: str | None = None,
    upstream_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a validated draft without allocating a public serial."""

    ids = list(_contract_guard(lambda: canonicalize_primary_entity_ids(primary_entity_ids)))
    window = _contract_guard(lambda: canonicalize_observation_window(observation_window))
    # Round-trip canonical JSON data so the returned object cannot retain mutable aliases.
    selected_evidence = json.loads(_contract_guard(lambda: canonicalize_evidence(evidence)))
    snapshot_hash = _contract_guard(lambda: evidence_snapshot_hash(selected_evidence))
    result: dict[str, Any] = {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "status": "draft",
        "family": family,
        "detector_id": detector_id,
        "primary_entity_ids": ids,
        "observation_window": window,
        "evidence": selected_evidence,
        "evidence_snapshot_hash": snapshot_hash,
        "trace_key": _contract_guard(
            lambda: trace_key(
                trace_schema_version=TRACE_SCHEMA_VERSION,
                family=family,
                detector_id=detector_id,
                primary_entity_ids=ids,
                observation_window=window,
                evidence_snapshot_hash_value=snapshot_hash,
            )
        ),
    }
    for key, value in (
        ("language", language),
        ("generated_at", generated_at),
        ("renderer_version", renderer_version),
        ("upstream_provenance", upstream_provenance),
    ):
        if value is not None:
            result[key] = value
    validate_trace(result)
    return result
