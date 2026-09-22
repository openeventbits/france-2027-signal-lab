"""Build the deterministic FR27 Polling Lab explorer payload.

The builder is intentionally network-free. It derives the standalone polling
explorer contract entirely from polls.json while reusing the exact first-round
wave grouping semantics already used by Race at a Glance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from build_candidate_signals import (
    build_poll_packages,
    french_compatible_sort_key,
    validated_first_round_events,
)
from candidate_identity import CandidateIdentityError, candidate_id, canonical_candidate_name


SCHEMA_VERSION = "1.0"
WAVE_ID_PREFIX = "wave-"
WAVE_ID_HEX_LENGTH = 16

EXPLICIT_CANDIDATE_ALIASES = {
    "Arthaud": "Nathalie Arthaud",
    "Attal": "Gabriel Attal",
    "Bardella": "Jordan Bardella",
    "Bayrou": "François Bayrou",
    "Bertrand": "Xavier Bertrand",
    "Darmanin": "Gérald Darmanin",
    "de Villepin": "Dominique de Villepin",
    "de Villiers": "Philippe de Villiers",
    "Dupont-Aignan": "Nicolas Dupont-Aignan",
    "Faure": "Olivier Faure",
    "Hanouna": "Cyril Hanouna",
    "Hollande": "François Hollande",
    "Knafo": "Sarah Knafo",
    "Leclerc": "Michel-Édouard Leclerc",
    "Lecornu": "Sébastien Lecornu",
    "Mélenchon": "Jean-Luc Mélenchon",
    "Philippe": "Édouard Philippe",
    "Poutou": "Philippe Poutou",
    "Retailleau": "Bruno Retailleau",
    "Riner": "Teddy Riner",
    "Roussel": "Fabien Roussel",
    "Ruffin": "François Ruffin",
    "Sébastien": "Patrick Sébastien",
    "Tondelier": "Marine Tondelier",
    "Wauquiez": "Laurent Wauquiez",
    "Zemmour": "Éric Zemmour",
}

BALLOT_LABEL_IDENTITIES = frozenset(
    {
        "Generic DIV",
        "Generic DLF",
        "Generic ENS",
        "Generic EXG",
        "Generic LFI",
        "Generic LR",
        "Generic NFP",
        "Generic PS/PP",
        "Generic REC!",
        "Generic RN",
        "Generic UDR",
    }
)


class PollExplorerError(ValueError):
    """Raised when the polling explorer cannot be derived safely."""


def load_polls(path: Path | str) -> list[Any]:
    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PollExplorerError(f"poll source is missing: {source_path}") from error
    except OSError as error:
        raise PollExplorerError(f"could not read poll source {source_path}: {error}") from error
    except json.JSONDecodeError as error:
        raise PollExplorerError(
            f"malformed JSON in {source_path}: line {error.lineno}, column {error.colno}"
        ) from error
    if not isinstance(payload, list):
        raise PollExplorerError("poll source must be a top-level array")
    return payload


def make_wave_id(package_key: str) -> str:
    if not isinstance(package_key, str) or not package_key:
        raise PollExplorerError("poll package key must be a non-empty string")
    digest = hashlib.sha256(package_key.encode("utf-8")).hexdigest()
    return f"{WAVE_ID_PREFIX}{digest[:WAVE_ID_HEX_LENGTH]}"


def _candidate_identity_directory(
    indexed_events: list[tuple[int, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Map published labels to explicit canonical polling identities.

    Alias resolution is intentionally finite and audited through
    EXPLICIT_CANDIDATE_ALIASES. No fuzzy matching, surname inference, or
    automatic alias discovery is performed. Generic party/list labels remain
    preserved as non-person ballot labels and are excluded from the candidate
    directory used by the picker.
    """

    source_names: set[str] = set()
    for _index, event in indexed_events:
        for candidate in event["candidates"]:
            raw_name = candidate["name"]
            try:
                published_name = canonical_candidate_name(raw_name)
            except CandidateIdentityError as error:
                raise PollExplorerError(str(error)) from error
            if published_name != raw_name:
                raise PollExplorerError(
                    f"published candidate label is not canonical: {raw_name!r}"
                )
            source_names.add(published_name)

    identities_by_published_name: dict[str, dict[str, Any]] = {}
    identities_by_id: dict[str, dict[str, Any]] = {}

    for published_name in sorted(
        source_names, key=lambda value: (french_compatible_sort_key(value), value)
    ):
        canonical_name = EXPLICIT_CANDIDATE_ALIASES.get(published_name, published_name)
        try:
            canonical_name = canonical_candidate_name(canonical_name)
            identifier = candidate_id(canonical_name)
        except CandidateIdentityError as error:
            raise PollExplorerError(str(error)) from error

        identity_type = (
            "ballot_label" if published_name in BALLOT_LABEL_IDENTITIES else "person"
        )
        existing = identities_by_id.get(identifier)
        if existing is None:
            existing = {
                "candidate_id": identifier,
                "candidate_name": canonical_name,
                "identity_type": identity_type,
                "source_labels": [],
            }
            identities_by_id[identifier] = existing
        else:
            if existing["candidate_name"] != canonical_name:
                raise PollExplorerError(
                    "explicit candidate identity collision: "
                    f"{existing['candidate_name']!r} and {canonical_name!r} -> {identifier}"
                )
            if existing["identity_type"] != identity_type:
                raise PollExplorerError(
                    f"candidate identity type collision for {canonical_name!r}"
                )

        existing["source_labels"].append(published_name)
        identities_by_published_name[published_name] = existing

    for identity in identities_by_id.values():
        identity["source_labels"].sort(
            key=lambda value: (french_compatible_sort_key(value), value)
        )

    return identities_by_published_name

def _scenario_projection(
    event: dict[str, Any],
    identities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hypothesis = event.get("hypothesis")
    if not isinstance(hypothesis, str) or not hypothesis.strip():
        raise PollExplorerError(f"event {event.get('event_id')} has no hypothesis")

    candidates: list[dict[str, Any]] = []
    for candidate in event["candidates"]:
        published_name = candidate["name"]
        identity = identities.get(published_name)
        if identity is None:
            raise PollExplorerError(f"candidate identity missing for {published_name!r}")
        candidates.append(
            {
                "candidate_id": identity["candidate_id"],
                "candidate_name": identity["candidate_name"],
                "published_candidate_name": published_name,
                "identity_type": identity["identity_type"],
                "score": candidate["score"],
            }
        )

    return {
        "event_id": event["event_id"],
        "scenario_key": event["scenario_key"],
        "hypothesis": hypothesis,
        "source_url": event["source_url"],
        "completeness_status": event["completeness_status"],
        "partial_scenario": event["partial_scenario"],
        "reported_total": event["reported_total"],
        "candidates": candidates,
    }

def build_poll_explorer(polls: Any) -> dict[str, Any]:
    indexed_events = validated_first_round_events(polls)
    packages = build_poll_packages(polls)
    identities = _candidate_identity_directory(indexed_events)

    canonical_identities = {
        identity["candidate_id"]: identity for identity in identities.values()
    }
    candidate_stats: dict[str, dict[str, Any]] = {
        identity["candidate_id"]: {
            "candidate_id": identity["candidate_id"],
            "candidate_name": identity["candidate_name"],
            "source_labels": list(identity["source_labels"]),
            "wave_ids": set(),
            "scenario_count": 0,
            "first_observed": None,
            "last_observed": None,
        }
        for identity in canonical_identities.values()
        if identity["identity_type"] == "person"
    }
    institute_stats: dict[str, dict[str, Any]] = {}
    waves: list[dict[str, Any]] = []

    for package in packages:
        wave_id = make_wave_id(package["package_key"])
        scenarios = [
            _scenario_projection(event, identities)
            for event in package["events"]
        ]
        source_urls = sorted({scenario["source_url"] for scenario in scenarios})

        people_in_wave = {
            candidate["candidate_id"]: candidate["candidate_name"]
            for scenario in scenarios
            for candidate in scenario["candidates"]
            if candidate["identity_type"] == "person"
        }
        candidate_ids = [
            identifier
            for identifier, _name in sorted(
                people_in_wave.items(),
                key=lambda item: (
                    french_compatible_sort_key(item[1]),
                    item[0],
                ),
            )
        ]

        wave = {
            "wave_id": wave_id,
            "pollster": package["pollster"],
            "fieldwork_start": package["fieldwork_start"],
            "fieldwork_end": package["fieldwork_end"],
            "sample_size": package["sample_size"],
            "scenario_count": len(scenarios),
            "selected_event_id": package["selected_event"]["event_id"],
            "selected_comparable_candidate_count": package[
                "selected_comparable_candidate_count"
            ],
            "source_urls": source_urls,
            "candidate_ids": candidate_ids,
            "scenarios": scenarios,
        }
        waves.append(wave)

        for scenario in scenarios:
            for candidate in scenario["candidates"]:
                if candidate["identity_type"] != "person":
                    continue
                stats = candidate_stats[candidate["candidate_id"]]
                stats["wave_ids"].add(wave_id)
                stats["scenario_count"] += 1
                start = package["fieldwork_start"]
                end = package["fieldwork_end"]
                if stats["first_observed"] is None or start < stats["first_observed"]:
                    stats["first_observed"] = start
                if stats["last_observed"] is None or end > stats["last_observed"]:
                    stats["last_observed"] = end

        institute = institute_stats.setdefault(
            package["pollster"],
            {
                "name": package["pollster"],
                "wave_ids": set(),
                "scenario_count": 0,
                "first_observed": None,
                "last_observed": None,
            },
        )
        institute["wave_ids"].add(wave_id)
        institute["scenario_count"] += len(scenarios)
        start = package["fieldwork_start"]
        end = package["fieldwork_end"]
        if institute["first_observed"] is None or start < institute["first_observed"]:
            institute["first_observed"] = start
        if institute["last_observed"] is None or end > institute["last_observed"]:
            institute["last_observed"] = end

    waves.sort(
        key=lambda wave: (
            -int(wave["fieldwork_end"].replace("-", "")),
            french_compatible_sort_key(wave["pollster"]),
            wave["wave_id"],
        )
    )

    candidates = [
        {
            "candidate_id": stats["candidate_id"],
            "candidate_name": stats["candidate_name"],
            "source_labels": stats["source_labels"],
            "wave_count": len(stats["wave_ids"]),
            "scenario_count": stats["scenario_count"],
            "first_observed": stats["first_observed"],
            "last_observed": stats["last_observed"],
        }
        for stats in candidate_stats.values()
    ]
    candidates.sort(
        key=lambda candidate: (
            french_compatible_sort_key(candidate["candidate_name"]),
            candidate["candidate_id"],
        )
    )

    institutes = [
        {
            "name": stats["name"],
            "wave_count": len(stats["wave_ids"]),
            "scenario_count": stats["scenario_count"],
            "first_observed": stats["first_observed"],
            "last_observed": stats["last_observed"],
        }
        for stats in institute_stats.values()
    ]
    institutes.sort(
        key=lambda institute: (
            french_compatible_sort_key(institute["name"]),
            institute["name"],
        )
    )

    starts = [event["fieldwork_start"] for _index, event in indexed_events]
    ends = [event["fieldwork_end"] for _index, event in indexed_events]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "data_as_of": max(ends),
        "metrics": {
            "wave_count": len(waves),
            "scenario_count": len(indexed_events),
            "candidate_count": len(candidates),
            "institute_count": len(institutes),
            "period_start": min(starts),
            "period_end": max(ends),
        },
        "candidates": candidates,
        "institutes": institutes,
        "waves": waves,
    }
    return payload


def serialize_poll_explorer(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def write_poll_explorer(payload: dict[str, Any], output_path: Path | str) -> None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = serialize_poll_explorer(payload)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, destination)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def build_from_paths(
    polls_path: Path | str = "polls.json",
    output_path: Path | str = "poll_explorer.json",
) -> dict[str, Any]:
    polls = load_polls(polls_path)
    payload = build_poll_explorer(polls)
    write_poll_explorer(payload, output_path)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the deterministic FR27 Polling Lab explorer payload"
    )
    parser.add_argument("--polls", default="polls.json")
    parser.add_argument("--output", default="poll_explorer.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        payload = build_from_paths(arguments.polls, arguments.output)
    except (PollExplorerError, ValueError) as error:
        print(f"poll explorer error: {error}")
        return 1
    metrics = payload["metrics"]
    print(
        "built poll explorer: "
        f"{metrics['wave_count']} waves, "
        f"{metrics['scenario_count']} scenarios, "
        f"{metrics['candidate_count']} tested people, "
        f"{metrics['institute_count']} institutes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
