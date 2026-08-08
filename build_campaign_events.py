"""Build the deterministic Campaign Events public artifact."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from campaign_event_institutional_seeds import (
    CampaignEventInstitutionalSeedError,
    load_campaign_event_institutional_seeds,
)
from campaign_event_sources import (
    CampaignEventSourceRegistryError,
    load_campaign_event_source_registry,
)
from campaign_events_contract import (
    CampaignEventsContractError,
    campaign_event_id,
    normalize_campaign_event_observations,
    normalize_campaign_events_artifact,
    serialize_campaign_events,
    validate_campaign_events_artifact,
)
from rn_agenda_adapter import build_rn_agenda_events

__all__ = [
    "BuildCampaignEventsError",
    "atomic_write",
    "build_campaign_events_artifact",
    "build_from_paths",
    "preserve_generated_at_if_unchanged",
]


class BuildCampaignEventsError(ValueError):
    """Raised when Campaign Events generation cannot complete safely."""


class CampaignEventCollectionConfigurationError(BuildCampaignEventsError):
    """Raised for fatal collector configuration or interface defects."""


DEFAULT_SEEDS = Path(__file__).with_name("campaign_event_institutional_seeds.json")
DEFAULT_SOURCES = Path(__file__).with_name("campaign_event_sources.json")
DEFAULT_CANDIDATES = Path(__file__).with_name("candidate_candidacy_status.json")
DEFAULT_OUTPUT = Path(__file__).with_name("campaign_events.json")

SourceEventBuilder = Callable[..., list[dict[str, Any]]]
CollectionCollector = Callable[..., "SourceCollectionResult"]


_COLLECTION_FAILURE_REASONS = frozenset(
    {"collector_failure", "invalid_zero_result"}
)


@dataclass(frozen=True, slots=True)
class SourceCollectionResult:
    """Strict internal result returned by generic collection implementations."""

    observations: list[dict[str, Any]]
    attribution_rejected_records: int = 0

    def __post_init__(self) -> None:
        if type(self.observations) is not list:
            raise CampaignEventCollectionConfigurationError(
                "collector result observations must be a list"
            )
        if any(
            type(observation) is not dict for observation in self.observations
        ):
            raise CampaignEventCollectionConfigurationError(
                "collector result observations must contain plain dicts"
            )
        if (
            type(self.attribution_rejected_records) is not int
            or self.attribution_rejected_records < 0
        ):
            raise CampaignEventCollectionConfigurationError(
                "attribution_rejected_records must be a non-negative integer"
            )


def _require_source_collection_result(
    value: Any,
    *,
    source_id: str,
) -> SourceCollectionResult:
    if type(value) is not SourceCollectionResult:
        raise CampaignEventCollectionConfigurationError(
            f"Campaign Events source {source_id} collector must return "
            "SourceCollectionResult"
        )
    value.__post_init__()
    return value


@dataclass(frozen=True, slots=True)
class SourceCollectionHealth:
    """Deterministic internal health for one attempted source collection."""

    source_id: str
    checked_successfully: bool
    accepted_records: int
    attribution_rejected_records: int
    preserved_records: int
    failure_reason: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id
            or self.source_id != self.source_id.strip()
        ):
            raise ValueError("source_id must be non-empty trimmed text")
        if type(self.checked_successfully) is not bool:
            raise ValueError("checked_successfully must be an actual boolean")
        for field in (
            "accepted_records",
            "attribution_rejected_records",
            "preserved_records",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.checked_successfully and self.failure_reason is not None:
            raise ValueError("successful collection must not have failure_reason")
        if not self.checked_successfully and not self.failure_reason:
            raise ValueError("failed collection requires failure_reason")
        if (
            self.failure_reason is not None
            and self.failure_reason not in _COLLECTION_FAILURE_REASONS
        ):
            raise ValueError("failure_reason is not allowed")
        if self.checked_successfully and self.preserved_records:
            raise ValueError("successful collection cannot preserve records")
        if not self.checked_successfully and (
            self.accepted_records or self.attribution_rejected_records
        ):
            raise ValueError(
                "failed collection cannot accept or reject attribution records"
            )


def _collect_rn_agenda(
    *,
    source: dict[str, Any],
    observed_at: str,
) -> SourceCollectionResult:
    if (
        source.get("source_id") != "rn-agenda"
        or source.get("collection", {}).get("collector_family") != "rn-agenda"
    ):
        raise CampaignEventCollectionConfigurationError(
            "rn-agenda collector received an incompatible source record"
        )
    return SourceCollectionResult(
        observations=build_rn_agenda_events(observed_at=observed_at),
        attribution_rejected_records=0,
    )


_PRODUCTION_COLLECTION_COLLECTORS: Mapping[str, CollectionCollector] = {
    "rn-agenda": _collect_rn_agenda,
}


def _resolve_campaign_event_collector(
    source: dict[str, Any],
    *,
    collection_collectors: Mapping[str, CollectionCollector],
) -> CollectionCollector:
    collection = source["collection"]
    collector_family = collection.get(
        "collector_family",
        collection["parser_family"],
    )
    collector = collection_collectors.get(collector_family)
    if collector is None:
        raise CampaignEventCollectionConfigurationError(
            "no Campaign Events collector registered for family "
            f"{collector_family!r} (source {source['source_id']})"
        )
    return collector


def _dispatch_campaign_event_collection(
    source: dict[str, Any],
    *,
    observed_at: str,
    collection_collectors: Mapping[str, CollectionCollector],
) -> SourceCollectionResult:
    collector = _resolve_campaign_event_collector(
        source,
        collection_collectors=collection_collectors,
    )
    supplied = collector(source=source, observed_at=observed_at)
    return _require_source_collection_result(
        supplied,
        source_id=source["source_id"],
    )


_OBSERVATION_FIELDS = frozenset({"status_as_of", "last_verified_at"})


def _transform_seed(seed: dict[str, Any]) -> dict[str, Any]:
    event_key = seed["event_key"]
    return {
        "event_key": event_key,
        "event_id": campaign_event_id(seed["lane"], event_key),
        "event_type": seed["event_type"],
        "title": seed["title"],
        "candidate_ids": [],
        "candidate_names": [],
        "scheduled_start": seed["scheduled_start"],
        "time_precision": seed["time_precision"],
        "timezone": seed["timezone"],
        "status": seed["status"],
        "status_as_of": seed["status_as_of"],
        "evidence_status": seed["evidence_status"],
        "last_verified_at": seed["last_verified_at"],
        "evidence": [dict(record) for record in seed["evidence"]],
    }


def _event_source_ids(event: dict[str, Any]) -> frozenset[str]:
    return frozenset(record["source_id"] for record in event["evidence"])


def _event_semantics_without_observation(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key not in _OBSERVATION_FIELDS
    }


def _deduplicate_campaign_events(
    events: list[dict[str, Any]],
    *,
    context: str,
) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for index, supplied in enumerate(events):
        if type(supplied) is not dict:
            raise BuildCampaignEventsError(
                f"{context}[{index}] must be a plain dict"
            )
        event = copy.deepcopy(supplied)
        event_key = event.get("event_key")
        event_id = event.get("event_id")
        if not isinstance(event_key, str) or not isinstance(event_id, str):
            raise BuildCampaignEventsError(
                f"{context}[{index}] must contain string event_key and event_id"
            )

        prior_key = by_key.get(event_key)
        if prior_key is not None and prior_key != event:
            raise BuildCampaignEventsError(
                f"conflicting campaign event_key: {event_key}"
            )
        prior_id = by_id.get(event_id)
        if prior_id is not None and prior_id != event:
            raise BuildCampaignEventsError(
                f"conflicting campaign event_id: {event_id}"
            )
        if prior_key is not None or prior_id is not None:
            continue
        by_key[event_key] = event
        by_id[event_id] = event
        unique.append(event)
    return unique


def _ascii_key_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def _reconciliation_time_token(event: dict[str, Any]) -> str:
    scheduled = event["scheduled_start"]
    if event["time_precision"] == "date":
        return scheduled
    date_part, time_part = scheduled.split("T", 1)
    hour_minute = time_part[:5].replace(":", "")
    return f"{date_part}-{hour_minute}"


def _compatible_optional_value(
    observations: list[dict[str, Any]],
    field: str,
) -> str | None:
    values = {
        event[field]
        for event in observations
        if field in event
    }
    if len(values) > 1:
        raise BuildCampaignEventsError(
            f"conflicting reconciled Campaign Events field {field}: "
            f"{sorted(values)!r}"
        )
    return next(iter(values)) if values else None


def _scheduled_calendar_date(event: dict[str, Any]) -> str:
    if event["time_precision"] == "date":
        return event["scheduled_start"]
    return event["scheduled_start"].split("T", 1)[0]


def _resolved_reconciled_schedule(
    observations: list[dict[str, Any]],
) -> tuple[str, str]:
    calendar_dates = {
        _scheduled_calendar_date(event)
        for event in observations
    }
    if len(calendar_dates) != 1:
        raise BuildCampaignEventsError(
            "conflicting reconciled Campaign Events calendar dates: "
            f"{sorted(calendar_dates)!r}"
        )

    datetime_values = {
        event["scheduled_start"]
        for event in observations
        if event["time_precision"] == "datetime"
    }
    if len(datetime_values) > 1:
        raise BuildCampaignEventsError(
            "conflicting reconciled Campaign Events datetime schedules: "
            f"{sorted(datetime_values)!r}"
        )

    if datetime_values:
        return next(iter(datetime_values)), "datetime"

    return next(iter(calendar_dates)), "date"


def _same_real_world_event(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    if (
        left["event_type"] != right["event_type"]
        or left["timezone"] != right["timezone"]
    ):
        return False

    same_precision = left["time_precision"] == right["time_precision"]

    if same_precision:
        if left["scheduled_start"] != right["scheduled_start"]:
            return False
        if set(left["candidate_ids"]).isdisjoint(right["candidate_ids"]):
            return False
    else:
        precisions = {
            left["time_precision"],
            right["time_precision"],
        }
        if precisions != {"date", "datetime"}:
            return False

        if _scheduled_calendar_date(left) != _scheduled_calendar_date(right):
            return False

        if set(left["candidate_ids"]) != set(right["candidate_ids"]):
            return False

        context_fields = (
            "organization",
            "location_name",
            "locality",
            "department",
        )
        shared_context = any(
            field in left
            and field in right
            and left[field] == right[field]
            for field in context_fields
        )
        if not shared_context:
            return False

    for field in (
        "scheduled_end",
        "organization",
        "location_name",
        "locality",
        "department",
    ):
        if (
            field in left
            and field in right
            and left[field] != right[field]
        ):
            return False

    return True


def _canonical_reconciled_event_key(
    observations: list[dict[str, Any]],
    merged: dict[str, Any],
) -> str:
    parts = [
        "campaign",
        merged["event_type"],
        _reconciliation_time_token(merged),
    ]

    anchor = (
        merged.get("organization")
        or merged.get("location_name")
        or merged.get("locality")
    )
    if anchor:
        token = _ascii_key_token(anchor)
        if token:
            parts.append(token)

    return "-".join(parts)


def _merge_campaign_event_observations(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    if not observations:
        raise BuildCampaignEventsError(
            "cannot reconcile an empty Campaign Events observation group"
        )

    ordered = sorted(
        (copy.deepcopy(event) for event in observations),
        key=lambda event: (
            -len(event["candidate_ids"]),
            event["title"].casefold(),
            event["event_key"],
        ),
    )
    base = ordered[0]

    candidate_by_id: dict[str, str] = {}
    for event in ordered:
        for candidate_id, candidate_name in zip(
            event["candidate_ids"],
            event["candidate_names"],
        ):
            prior = candidate_by_id.get(candidate_id)
            if prior is not None and prior != candidate_name:
                raise BuildCampaignEventsError(
                    f"conflicting candidate name for {candidate_id}"
                )
            candidate_by_id[candidate_id] = candidate_name

    candidate_pairs = sorted(
        candidate_by_id.items(),
        key=lambda pair: (pair[1].casefold(), pair[0]),
    )

    evidence_by_url: dict[str, dict[str, Any]] = {}
    for event in ordered:
        for record in event["evidence"]:
            source_url = record["source_url"]
            prior = evidence_by_url.get(source_url)
            if prior is not None and prior != record:
                raise BuildCampaignEventsError(
                    f"conflicting evidence for source URL {source_url}"
                )
            evidence_by_url[source_url] = copy.deepcopy(record)

    scheduled_start, time_precision = _resolved_reconciled_schedule(
        ordered
    )

    merged = {
        "event_type": base["event_type"],
        "title": base["title"],
        "candidate_ids": [pair[0] for pair in candidate_pairs],
        "candidate_names": [pair[1] for pair in candidate_pairs],
        "scheduled_start": scheduled_start,
        "time_precision": time_precision,
        "timezone": base["timezone"],
        "status": base["status"],
        "status_as_of": max(event["status_as_of"] for event in ordered),
        "evidence_status": base["evidence_status"],
        "last_verified_at": max(
            event["last_verified_at"]
            for event in ordered
        ),
        "evidence": list(evidence_by_url.values()),
    }

    statuses = {event["status"] for event in ordered}
    if len(statuses) != 1:
        raise BuildCampaignEventsError(
            f"conflicting reconciled Campaign Events statuses: "
            f"{sorted(statuses)!r}"
        )

    evidence_statuses = {
        event["evidence_status"]
        for event in ordered
    }
    if len(evidence_statuses) != 1:
        raise BuildCampaignEventsError(
            f"conflicting reconciled evidence statuses: "
            f"{sorted(evidence_statuses)!r}"
        )

    for field in (
        "scheduled_end",
        "organization",
        "location_name",
        "locality",
        "department",
    ):
        value = _compatible_optional_value(ordered, field)
        if value is not None:
            merged[field] = value

    event_key = _canonical_reconciled_event_key(ordered, merged)
    merged["event_key"] = event_key
    merged["event_id"] = campaign_event_id("campaign_events", event_key)

    return merged


def _reconcile_campaign_event_observations(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []

    for supplied in events:
        event = copy.deepcopy(supplied)
        matches = [
            group
            for group in groups
            if any(
                _same_real_world_event(event, existing)
                for existing in group
            )
        ]

        if len(matches) > 1:
            raise BuildCampaignEventsError(
                f"ambiguous Campaign Events reconciliation for "
                f"{event['event_key']}"
            )
        if matches:
            matches[0].append(event)
        else:
            groups.append([event])

    reconciled = [
        _merge_campaign_event_observations(group)
        for group in groups
    ]

    return _deduplicate_campaign_events(
        reconciled,
        context="reconciled campaign_events",
    )


def _normalize_source_events(
    source_id: str,
    events: list[dict[str, Any]],
    *,
    observed_at: str,
    source_registry_path: str | Path,
    candidate_registry_path: str | Path,
) -> list[dict[str, Any]]:
    try:
        normalized_events = normalize_campaign_event_observations(
            events,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
    except CampaignEventsContractError as error:
        raise BuildCampaignEventsError(
            f"Campaign Events source {source_id} returned invalid events: {error}"
        ) from error

    for event in normalized_events:
        if _event_source_ids(event) != {source_id}:
            raise BuildCampaignEventsError(
                f"Campaign Events source {source_id} returned an event without "
                "exclusive source ownership"
            )
    return normalized_events


def _partition_source_owned_events(
    events: list[dict[str, Any]],
    source_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    owned: list[dict[str, Any]] = []
    unrelated: list[dict[str, Any]] = []
    for event in events:
        owners = _event_source_ids(event)
        if source_id not in owners:
            unrelated.append(event)
        elif owners == {source_id}:
            owned.append(event)
        else:
            raise BuildCampaignEventsError(
                f"Campaign Events source {source_id} has conflicting prior "
                "evidence ownership"
            )
    return owned, unrelated


def _stabilize_observation_fields(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    previous_by_key = {event["event_key"]: event for event in previous}
    previous_by_id = {event["event_id"]: event for event in previous}
    stabilized: list[dict[str, Any]] = []
    for supplied in current:
        event = copy.deepcopy(supplied)
        prior_by_key = previous_by_key.get(event["event_key"])
        prior_by_id = previous_by_id.get(event["event_id"])
        if (
            prior_by_key is not None
            and prior_by_id is not None
            and prior_by_key is not prior_by_id
        ):
            raise BuildCampaignEventsError(
                f"conflicting previous identity for event_key {event['event_key']}"
            )
        prior = prior_by_key or prior_by_id
        if prior is not None and (
            _event_semantics_without_observation(event)
            == _event_semantics_without_observation(prior)
        ):
            event["status_as_of"] = prior["status_as_of"]
            event["last_verified_at"] = prior["last_verified_at"]
        stabilized.append(event)
    return stabilized


def _source_failure(
    source: dict[str, Any],
    *,
    preserved_count: int,
    disallowed_zero: bool,
    cause: Exception | None = None,
) -> None:
    source_id = source["source_id"]
    detail = (
        "returned zero events while zero_result_valid is false"
        if disallowed_zero
        else "failed"
    )
    if source["required"]:
        error = BuildCampaignEventsError(
            f"required Campaign Events source {source_id} {detail}"
        )
        if cause is not None:
            raise error from cause
        raise error
    suffix = "record" if preserved_count == 1 else "records"
    print(
        f"warning: Campaign Events source {source_id} {detail}; "
        f"preserved {preserved_count} previous {suffix}"
    )


def _previous_campaign_event_observations(
    previous_artifact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Reconstruct conservative per-source fallbacks from the last good artifact.

    A previously reconciled event may contain evidence from several sources.
    Split that event into source-owned observations so each source can refresh,
    fail, or validly disappear independently on the next build. Canonical
    semantics are intentionally copied to every fallback observation because
    the public artifact does not retain finer-grained source contributions.
    """

    if previous_artifact is None:
        return []

    observations: list[dict[str, Any]] = []
    for event in previous_artifact["campaign_events"]:
        evidence_by_source: dict[str, list[dict[str, Any]]] = {}
        for record in event["evidence"]:
            evidence_by_source.setdefault(
                record["source_id"],
                [],
            ).append(copy.deepcopy(record))

        for source_id in sorted(evidence_by_source):
            observation = copy.deepcopy(event)
            observation["evidence"] = evidence_by_source[source_id]
            observations.append(observation)

    return observations


def _collect_dynamic_campaign_events(
    source_registry: dict[str, Any],
    *,
    observed_at: str,
    previous_artifact: dict[str, Any] | None,
    source_registry_path: str | Path,
    candidate_registry_path: str | Path,
    source_event_builders: Mapping[str, SourceEventBuilder] | None,
    collection_collectors: Mapping[str, CollectionCollector],
    collection_health: list[SourceCollectionHealth] | None = None,
) -> list[dict[str, Any]]:
    events = _previous_campaign_event_observations(previous_artifact)
    for source in source_registry["sources"]:
        source_id = source["source_id"]
        if (
            not source["enabled"]
            or "campaign_events" not in source["allowed_lanes"]
        ):
            continue

        legacy_builder = None
        collector = None
        if source_event_builders is not None:
            legacy_builder = source_event_builders.get(source_id)
            if legacy_builder is None:
                continue
        else:
            collector = _resolve_campaign_event_collector(
                source,
                collection_collectors=collection_collectors,
            )

        previous_owned, unrelated = _partition_source_owned_events(
            events,
            source_id,
        )
        try:
            if legacy_builder is not None:
                supplied = legacy_builder(observed_at=observed_at)
            else:
                supplied = collector(source=source, observed_at=observed_at)
        except CampaignEventCollectionConfigurationError:
            raise
        except Exception as error:
            if collection_health is not None:
                collection_health.append(
                    SourceCollectionHealth(
                        source_id=source_id,
                        checked_successfully=False,
                        accepted_records=0,
                        attribution_rejected_records=0,
                        preserved_records=len(previous_owned),
                        failure_reason="collector_failure",
                    )
                )
            _source_failure(
                source,
                preserved_count=len(previous_owned),
                disallowed_zero=False,
                cause=error,
            )
            continue

        attribution_rejected_records = 0
        if legacy_builder is None:
            collection_result = _require_source_collection_result(
                supplied,
                source_id=source_id,
            )
            observations = collection_result.observations
            attribution_rejected_records = (
                collection_result.attribution_rejected_records
            )
        else:
            if type(supplied) is not list:
                raise BuildCampaignEventsError(
                    f"Campaign Events source {source_id} must return a list"
                )
            observations = supplied

        if not observations:
            if not source["zero_result_valid"]:
                if collection_health is not None:
                    collection_health.append(
                        SourceCollectionHealth(
                            source_id=source_id,
                            checked_successfully=False,
                            accepted_records=0,
                            attribution_rejected_records=0,
                            preserved_records=len(previous_owned),
                            failure_reason="invalid_zero_result",
                        )
                    )
                _source_failure(
                    source,
                    preserved_count=len(previous_owned),
                    disallowed_zero=True,
                )
                continue
            events = unrelated
            if collection_health is not None:
                collection_health.append(
                    SourceCollectionHealth(
                        source_id=source_id,
                        checked_successfully=True,
                        accepted_records=0,
                        attribution_rejected_records=(
                            attribution_rejected_records
                        ),
                        preserved_records=0,
                        failure_reason=None,
                    )
                )
            continue

        deduplicated = _deduplicate_campaign_events(
            observations,
            context=f"Campaign Events source {source_id}",
        )
        normalized = _normalize_source_events(
            source_id,
            deduplicated,
            observed_at=observed_at,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        events = unrelated + _stabilize_observation_fields(
            normalized,
            previous_owned,
        )
        if collection_health is not None:
            collection_health.append(
                SourceCollectionHealth(
                    source_id=source_id,
                    checked_successfully=True,
                    accepted_records=len(normalized),
                    attribution_rejected_records=(
                        attribution_rejected_records
                    ),
                    preserved_records=0,
                    failure_reason=None,
                )
            )

    reconciled = _reconcile_campaign_event_observations(events)
    if previous_artifact is None:
        return reconciled
    return _stabilize_observation_fields(
        reconciled,
        previous_artifact["campaign_events"],
    )


def _validated_previous_artifact(
    payload: Any,
    *,
    source_registry_path: str | Path,
    candidate_registry_path: str | Path,
) -> dict[str, Any] | None:
    try:
        validate_campaign_events_artifact(
            payload,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        normalized = normalize_campaign_events_artifact(
            payload,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
    except CampaignEventsContractError:
        return None
    return normalized


def build_campaign_events_artifact(
    seed_payload: dict[str, Any] | None,
    *,
    generated_at: str,
    campaign_events: list[dict[str, Any]] | None = None,
    source_registry_path: str | Path = DEFAULT_SOURCES,
    candidate_registry_path: str | Path = DEFAULT_CANDIDATES,
    bootstrap_empty: bool = False,
) -> dict[str, Any]:
    """Transform validated seed data into the canonical public artifact."""

    if bootstrap_empty:
        milestones: list[dict[str, Any]] = []
    else:
        if seed_payload is None:
            raise BuildCampaignEventsError("institutional seeds are required")
        seeds = seed_payload.get("seeds")
        if not isinstance(seeds, list) or len(seeds) != 2:
            raise BuildCampaignEventsError(
                "production build requires exactly two institutional seeds"
            )
        milestones = [_transform_seed(seed) for seed in seeds]

    dynamic_events = [] if campaign_events is None else campaign_events
    records = dynamic_events + milestones
    data_as_of = (
        max(record["last_verified_at"] for record in records)
        if records
        else generated_at
    )
    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "campaign_events": dynamic_events,
        "institutional_milestones": milestones,
    }
    try:
        normalized = normalize_campaign_events_artifact(
            payload,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        validate_campaign_events_artifact(
            normalized,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
    except CampaignEventsContractError as error:
        raise BuildCampaignEventsError(
            f"generated Campaign Events artifact is invalid: {error}"
        ) from error
    return normalized


def preserve_generated_at_if_unchanged(
    candidate: dict[str, Any],
    existing: Any,
    *,
    source_registry_path: str | Path = DEFAULT_SOURCES,
    candidate_registry_path: str | Path = DEFAULT_CANDIDATES,
) -> dict[str, Any]:
    """Preserve a valid existing timestamp only for identical event semantics."""

    try:
        validate_campaign_events_artifact(
            existing,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
    except CampaignEventsContractError:
        return candidate

    candidate_semantics = {
        key: value for key, value in candidate.items() if key != "generated_at"
    }
    existing_semantics = {
        key: value for key, value in existing.items() if key != "generated_at"
    }
    if candidate_semantics != existing_semantics:
        return candidate

    preserved = dict(candidate)
    preserved["generated_at"] = existing["generated_at"]
    try:
        normalized = normalize_campaign_events_artifact(
            preserved,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        validate_campaign_events_artifact(
            normalized,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
    except CampaignEventsContractError as error:
        raise BuildCampaignEventsError(
            f"preserved Campaign Events artifact is invalid: {error}"
        ) from error
    return normalized


def _load_optional_existing_artifact(path: str | Path) -> Any | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def atomic_write(path: str | Path, content: bytes) -> None:
    """Replace one artifact only after a complete durable temporary write."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def build_from_paths(
    *,
    generated_at: str,
    seed_path: str | Path = DEFAULT_SEEDS,
    source_registry_path: str | Path = DEFAULT_SOURCES,
    candidate_registry_path: str | Path = DEFAULT_CANDIDATES,
    output_path: str | Path = DEFAULT_OUTPUT,
    bootstrap_empty: bool = False,
    preserve_generated_at_from: str | Path | None = None,
    source_event_builders: Mapping[str, SourceEventBuilder] | None = None,
    collection_collectors: Mapping[str, CollectionCollector] | None = None,
    collection_health: list[SourceCollectionHealth] | None = None,
) -> dict[str, Any]:
    """Load, build, serialize, and atomically publish one validated artifact."""

    try:
        source_registry = load_campaign_event_source_registry(
            source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        existing = (
            _load_optional_existing_artifact(preserve_generated_at_from)
            if preserve_generated_at_from is not None
            else None
        )
        previous = _validated_previous_artifact(
            existing,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        seeds = None
        if not bootstrap_empty:
            seeds = load_campaign_event_institutional_seeds(
                seed_path,
                source_registry_path=source_registry_path,
            )

        campaign_events: list[dict[str, Any]] = []
        if not bootstrap_empty:
            collectors = (
                _PRODUCTION_COLLECTION_COLLECTORS
                if collection_collectors is None
                else collection_collectors
            )
            campaign_events = _collect_dynamic_campaign_events(
                source_registry,
                observed_at=generated_at,
                previous_artifact=previous,
                source_registry_path=source_registry_path,
                candidate_registry_path=candidate_registry_path,
                source_event_builders=source_event_builders,
                collection_collectors=collectors,
                collection_health=collection_health,
            )
        artifact = build_campaign_events_artifact(
            seeds,
            generated_at=generated_at,
            campaign_events=campaign_events,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
            bootstrap_empty=bootstrap_empty,
        )
        if preserve_generated_at_from is not None:
            artifact = preserve_generated_at_if_unchanged(
                artifact,
                existing,
                source_registry_path=source_registry_path,
                candidate_registry_path=candidate_registry_path,
            )
        content = serialize_campaign_events(
            artifact,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        atomic_write(output_path, content)
    except BuildCampaignEventsError:
        raise
    except Exception as error:
        raise BuildCampaignEventsError(str(error)) from error
    return artifact


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the validated Campaign Events artifact"
    )
    parser.add_argument(
        "--generated-at",
        required=True,
        help="explicit UTC RFC 3339 generation timestamp",
    )
    parser.add_argument("--seeds", default=str(DEFAULT_SEEDS))
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--preserve-generated-at-from",
        help=(
            "preserve generated_at from a valid existing artifact when all "
            "other canonical content is unchanged"
        ),
    )
    parser.add_argument(
        "--bootstrap-empty",
        action="store_true",
        help="explicitly build a valid empty bootstrap artifact",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        artifact = build_from_paths(
            generated_at=arguments.generated_at,
            seed_path=arguments.seeds,
            source_registry_path=arguments.sources,
            candidate_registry_path=arguments.candidates,
            output_path=arguments.output,
            bootstrap_empty=arguments.bootstrap_empty,
            preserve_generated_at_from=arguments.preserve_generated_at_from,
        )
    except BuildCampaignEventsError as error:
        print(f"campaign events build error: {error}")
        return 1
    print(
        f"wrote {Path(arguments.output).name} "
        f"({len(artifact['campaign_events'])} campaign events, "
        f"{len(artifact['institutional_milestones'])} institutional milestones)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
