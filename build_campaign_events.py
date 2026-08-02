"""Build the deterministic, network-free Campaign Events public artifact."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

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


def build_campaign_events_artifact(
    seed_payload: dict[str, Any] | None,
    *,
    generated_at: str,
    source_registry_path: str | Path = DEFAULT_SOURCES,
    candidate_registry_path: str | Path = DEFAULT_CANDIDATES,
    bootstrap_empty: bool = False,
) -> dict[str, Any]:
    """Transform validated seed data into the canonical public artifact."""

    if bootstrap_empty:
        milestones: list[dict[str, Any]] = []
        data_as_of = generated_at
    else:
        if seed_payload is None:
            raise BuildCampaignEventsError("institutional seeds are required")
        seeds = seed_payload.get("seeds")
        if not isinstance(seeds, list) or len(seeds) != 2:
            raise BuildCampaignEventsError(
                "production build requires exactly two institutional seeds"
            )
        milestones = [_transform_seed(seed) for seed in seeds]
        data_as_of = max(seed["last_verified_at"] for seed in seeds)

    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "campaign_events": [],
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
) -> dict[str, Any]:
    """Load, build, serialize, and atomically publish one validated artifact."""

    try:
        load_campaign_event_source_registry(
            source_registry_path,
            candidate_registry_path=candidate_registry_path,
        )
        seeds = None
        if not bootstrap_empty:
            seeds = load_campaign_event_institutional_seeds(
                seed_path,
                source_registry_path=source_registry_path,
            )
        artifact = build_campaign_events_artifact(
            seeds,
            generated_at=generated_at,
            source_registry_path=source_registry_path,
            candidate_registry_path=candidate_registry_path,
            bootstrap_empty=bootstrap_empty,
        )
        if preserve_generated_at_from is not None:
            artifact = preserve_generated_at_if_unchanged(
                artifact,
                _load_optional_existing_artifact(preserve_generated_at_from),
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
        description="Build the static institutional Campaign Events artifact"
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
