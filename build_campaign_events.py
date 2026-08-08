"""Build the deterministic Campaign Events public artifact."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
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


DEFAULT_SEEDS = Path(__file__).with_name("campaign_event_institutional_seeds.json")
DEFAULT_SOURCES = Path(__file__).with_name("campaign_event_sources.json")
DEFAULT_CANDIDATES = Path(__file__).with_name("candidate_candidacy_status.json")
DEFAULT_OUTPUT = Path(__file__).with_name("campaign_events.json")

SourceEventBuilder = Callable[..., list[dict[str, Any]]]
_PRODUCTION_SOURCE_EVENT_BUILDERS: Mapping[str, SourceEventBuilder] = {
    "rn-agenda": build_rn_agenda_events,
}
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


def _normalize_source_events(
    source_id: str,
    events: list[dict[str, Any]],
    *,
    observed_at: str,
    source_registry_path: str | Path,
    candidate_registry_path: str | Path,
) -> list[dict[str, Any]]:
    payload = {
        "schema_version": "1.0",
        "generated_at": observed_at,
        "data_as_of": observed_at,
        "campaign_events": events,
        "institutional_milestones": [],
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
            f"Campaign Events source {source_id} returned invalid events: {error}"
        ) from error

    normalized_events = normalized["campaign_events"]
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


def _collect_dynamic_campaign_events(
    source_registry: dict[str, Any],
    *,
    observed_at: str,
    previous_artifact: dict[str, Any] | None,
    source_registry_path: str | Path,
    candidate_registry_path: str | Path,
    source_event_builders: Mapping[str, SourceEventBuilder],
) -> list[dict[str, Any]]:
    events = (
        copy.deepcopy(previous_artifact["campaign_events"])
        if previous_artifact is not None
        else []
    )
    for source in source_registry["sources"]:
        source_id = source["source_id"]
        builder = source_event_builders.get(source_id)
        if builder is None or not source["enabled"]:
            continue

        previous_owned, unrelated = _partition_source_owned_events(
            events,
            source_id,
        )
        try:
            supplied = builder(observed_at=observed_at)
        except Exception as error:
            _source_failure(
                source,
                preserved_count=len(previous_owned),
                disallowed_zero=False,
                cause=error,
            )
            continue

        if type(supplied) is not list:
            raise BuildCampaignEventsError(
                f"Campaign Events source {source_id} must return a list"
            )
        if not supplied:
            if not source["zero_result_valid"]:
                _source_failure(
                    source,
                    preserved_count=len(previous_owned),
                    disallowed_zero=True,
                )
                continue
            events = unrelated
            continue

        deduplicated = _deduplicate_campaign_events(
            supplied,
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

    return _deduplicate_campaign_events(
        events,
        context="merged campaign_events",
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
            builders = (
                _PRODUCTION_SOURCE_EVENT_BUILDERS
                if source_event_builders is None
                else source_event_builders
            )
            campaign_events = _collect_dynamic_campaign_events(
                source_registry,
                observed_at=generated_at,
                previous_artifact=previous,
                source_registry_path=source_registry_path,
                candidate_registry_path=candidate_registry_path,
                source_event_builders=builders,
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
