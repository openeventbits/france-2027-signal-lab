"""Build the deterministic FR27 Polling Lab explorer payload.

The builder is intentionally network-free. It derives the standalone polling
numerical explorer contract from polls.json while reusing the exact first-round
wave grouping semantics already used by Race at a Glance. Authenticated documentary
source scenarios are projected separately for browsing, never numerical analysis.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
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
from poll_ballot_labels import RN_CONDITIONAL_OPTION, RN_CONDITIONAL_DISPLAY_NAMES
from poll_source_tables import load_source_tables, digest as source_digest
from poll_studies import reviewed_member, load_binding
from poll_scope import RETROSPECTIVE, scope_record, load_scope_registry, validate_scope_registry


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
        RN_CONDITIONAL_OPTION,
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
                **({"display_names": dict(RN_CONDITIONAL_DISPLAY_NAMES)}
                   if published_name == RN_CONDITIONAL_OPTION else {}),
            }
        )

    projection = {
        "election_scope": scope_record(event)["scope"],
        "scope_review": scope_record(event),
        "event_id": event["event_id"],
        "scenario_key": event["scenario_key"],
        "hypothesis": hypothesis,
        "source_url": event["source_url"],
        "completeness_status": event["completeness_status"],
        "partial_scenario": event["partial_scenario"],
        "reported_total": event["reported_total"],
        "candidates": candidates,
    }
    member = reviewed_member(event)
    if member:
        projection.update(source_pollster=event["pollster"],
                          document_hypothesis=member["document_hypothesis"],
                          document_page=member["pdf_page"])
    return projection


def _route_slug_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    if not slug:
        raise PollExplorerError("Poll wave route component is empty.")
    return slug


def poll_wave_page_slug(
    *,
    fieldwork_end: str,
    pollster: str,
    wave_id: str,
) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fieldwork_end):
        raise PollExplorerError(
            f"Invalid poll wave fieldwork end date for route: {fieldwork_end!r}"
        )

    match = re.fullmatch(r"wave-([0-9a-f]{16})", wave_id)
    if match is None:
        raise PollExplorerError(
            f"Invalid canonical poll wave identifier for route: {wave_id!r}"
        )

    pollster_slug = _route_slug_component(pollster)
    wave_token = match.group(1)

    return f"{fieldwork_end}-{pollster_slug}-{wave_token}"


def poll_wave_page_paths(
    *,
    fieldwork_end: str,
    pollster: str,
    wave_id: str,
) -> tuple[str, str, str]:
    slug = poll_wave_page_slug(
        fieldwork_end=fieldwork_end,
        pollster=pollster,
        wave_id=wave_id,
    )
    return (
        slug,
        f"/sondages/{slug}/",
        f"/en/sondages/{slug}/",
    )


def reviewed_source_scenarios() -> list[dict[str, Any]]:
    """Finite browsing projection of the explicitly published documentary tables.

    These objects deliberately have neither wave/event IDs nor scalar scores.
    Exact published values remain typed results too; none are analytics inputs.
    """
    record = load_source_tables()
    projected = []
    for notice in record["standalone_pages"]:
        entry = record["tables"][notice]
        table = entry["table"]
        page = record["standalone_pages"][notice]
        candidates = []
        for row in table["rows"]:
            name = canonical_candidate_name(row["published_name"])
            identifier = candidate_id(name)
            if identifier != row["identity_id"]:
                raise PollExplorerError("Reviewed source candidate identity changed")
            candidates.append({
                "candidate_id": identifier, "candidate_name": name,
                "published_candidate_name": row["published_name"],
                "identity_type": "person", "result": dict(row["result"]),
            })
        bases = {b["scope"]: b["count"] for b in table["respondent_bases"]}
        projected.append({
            "kind": "reviewed_source_scenario",
            "round": table["round"],
            "source_scenario_id": table["source_table_id"],
            "survey_id": table["notice"]["notice_id"], "notice_id": notice,
            "evidence_status": "SOURCE_DOCUMENT_VERIFIED", "analysis_eligible": False,
            "record_sha256": entry["record_sha256"], "source": dict(table["source"]),
            "pollster": table["institute"], "commissioner": table["commissioner"],
            "publication_date": table.get("publication_date"),
            "fieldwork_start": table["fieldwork_start"], "fieldwork_end": table["fieldwork_end"],
            "respondent_bases": bases,
            "page_path_fr": page["page_path_fr"], "page_path_en": page["page_path_en"],
            "candidate_ids": [c["candidate_id"] for c in candidates], "candidates": candidates,
        })
    return projected


def directory_entries(waves, source_scenarios=None):
    """Merge for browsing only; never use this list for numerical analysis."""
    approved = reviewed_source_scenarios()
    sources = approved if source_scenarios is None else source_scenarios
    identities = [s["source_scenario_id"] for s in sources]
    surveys = [s["survey_id"] for s in sources]
    if len(set(identities)) != len(identities) or len(set(surveys)) != len(surveys):
        raise PollExplorerError("Duplicate reviewed source scenario/survey")
    if source_digest(sources) != source_digest(approved):
        raise PollExplorerError("Unreviewed source scenario projection")
    return sorted([*waves, *sources], key=lambda entry: (
        -int(entry["fieldwork_end"].replace("-", "")),
        french_compatible_sort_key(entry["pollster"]),
        entry.get("wave_id", entry.get("source_scenario_id")),
    ))


def build_poll_explorer(polls: Any) -> dict[str, Any]:
    indexed_events = validated_first_round_events(polls)
    # Reusable projection also serves finite synthetic/source-review subsets.
    # The file/publication boundary below requires the complete registry.
    validate_scope_registry(load_scope_registry(), polls, require_all=False)
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

        page_slug, page_path_fr, page_path_en = poll_wave_page_paths(
            fieldwork_end=package["fieldwork_end"],
            pollster=package["pollster"],
            wave_id=wave_id,
        )

        wave = {
            "wave_id": wave_id,
            "page_slug": page_slug,
            "page_path_fr": page_path_fr,
            "page_path_en": page_path_en,
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
        if any(reviewed_member(event) for event in package["events"]):
            binding = load_binding()
            if wave_id != binding["canonical_wave_id"]:
                raise PollExplorerError("Reviewed study canonical wave identity changed")
            wave.update(study_id=binding["study_id"],
                        source_pollster_labels=sorted({event["pollster"] for event in package["events"]}),
                        source_document=dict(binding["source_document"]))
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
        "source_scenarios": reviewed_source_scenarios(),
    }
    payload["default_2027"] = default_2027_projection(waves)
    payload["historical_archive"] = {
        "scope": RETROSPECTIVE,
        "scenario_count": sum(s["election_scope"] == RETROSPECTIVE for w in waves for s in w["scenarios"]),
        "wave_count": sum(any(s["election_scope"] == RETROSPECTIVE for s in w["scenarios"]) for w in waves),
    }
    return payload


def default_2027_projection(waves):
    """Default counts do not assert individual verification of election scope."""
    selected = [(wave, [s for s in wave["scenarios"] if s["election_scope"] != RETROSPECTIVE])
                for wave in waves]
    selected = [(wave, scenarios) for wave, scenarios in selected if scenarios]
    candidates, institutes = {}, {}
    for wave, scenarios in selected:
        for directory, identities in (
            (institutes, {wave["pollster"]: wave["pollster"]}),
            (candidates, {c["candidate_id"]: c["candidate_name"] for s in scenarios
                          for c in s["candidates"] if c["identity_type"] == "person"}),
        ):
            for identifier, name in identities.items():
                stats = directory.setdefault(identifier, {"name": name, "wave_count": 0,
                    "scenario_count": 0, "first_observed": wave["fieldwork_start"], "last_observed": wave["fieldwork_end"]})
                stats["wave_count"] += 1
                stats["scenario_count"] += (len(scenarios) if directory is institutes else
                    sum(any(c["candidate_id"] == identifier for c in s["candidates"]) for s in scenarios))
                stats["first_observed"] = min(stats["first_observed"], wave["fieldwork_start"])
                stats["last_observed"] = max(stats["last_observed"], wave["fieldwork_end"])
    return {"metrics": {"wave_count": len(selected),
        "scenario_count": sum(len(scenarios) for _, scenarios in selected),
        "candidate_count": len(candidates), "institute_count": len(institutes),
        "period_start": min((w["fieldwork_start"] for w, _ in selected), default=None),
        "period_end": max((w["fieldwork_end"] for w, _ in selected), default=None)},
        "candidates": [dict(candidate_id=k, candidate_name=v["name"], **{a:b for a,b in v.items() if a != "name"})
                       for k,v in sorted(candidates.items())],
        "institutes": [dict(v) for _,v in sorted(institutes.items())]}


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
    validate_scope_registry(load_scope_registry(), polls)
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
