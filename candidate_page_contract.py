"""Canonical dynamic route/index contract for FR27 candidate pages.

The candidate-page universe is derived exclusively from Candidate Registry v2.
There is no fixed candidate count and no candidate-specific route list here.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

from candidate_candidacy_status import (
    active_candidate_records,
    active_projection_provenance,
    project_active_monitoring_field,
)


SCHEMA_VERSION = "1.0"
PUBLIC_ORIGIN = "https://france2027.app"
ARCHIVED_CANDIDACY_STATUSES = frozenset(
    {
        "ruled_out",
        "withdrawn",
        "historical_poll_only",
    }
)


class CandidatePageContractError(ValueError):
    """Raised when the candidate-page projection becomes inconsistent."""


def _sort_key(candidate: dict[str, Any]) -> tuple[str, str]:
    normalized = unicodedata.normalize(
        "NFKD",
        candidate["candidate_name"],
    )
    folded = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).casefold()

    return folded, candidate["candidate_id"]


def _candidate_routes(candidate_id: str) -> dict[str, str]:
    return {
        "fr": f"/candidates/{candidate_id}/",
        "en": f"/en/candidates/{candidate_id}/",
    }


def is_archived_candidacy_status(status: str) -> bool:
    """Return whether a factual status belongs to the archive lifecycle."""

    return status in ARCHIVED_CANDIDACY_STATUSES


def candidate_detail_artifacts(candidate_id: str) -> tuple[Path, ...]:
    """Return the complete published artifact set for one bilingual dossier."""

    return (
        Path("candidates") / candidate_id / "data.json",
        Path("candidates") / candidate_id / "index.html",
        Path("en") / "candidates" / candidate_id / "index.html",
    )


def _candidate_directory_ids(root: Path) -> set[str]:
    identifiers: set[str] = set()

    for parent in (
        root / "candidates",
        root / "en" / "candidates",
    ):
        if not parent.exists():
            continue

        identifiers.update(
            child.name
            for child in parent.iterdir()
            if child.is_dir()
        )

    return identifiers


def project_candidate_page_lifecycle(
    payload: Any,
    root: Path,
) -> dict[str, Any]:
    """Classify current, retained archive and prunable dossier directories.

    Active pages are derived from the canonical active-monitoring rule. A page
    may remain published after leaving that field only when its factual status
    is explicitly archival. ``temporarily_missing`` is deliberately not an
    archive status, so any old directory for such a record is prunable rather
    than silently retained as a stale current page.
    """

    active = active_candidate_records(payload)
    active_ids = {
        candidate["candidate_id"]
        for candidate in active
    }
    records_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in payload["candidates"]
    }
    directory_ids = _candidate_directory_ids(root)
    archive_status_ids = {
        candidate_id
        for candidate_id, candidate in records_by_id.items()
        if is_archived_candidacy_status(candidate["status"])
    }
    retained_archived_ids = directory_ids & archive_status_ids
    temporarily_missing_ids = {
        candidate_id
        for candidate_id, candidate in records_by_id.items()
        if candidate.get("upstream_presence", "present")
        == "temporarily_missing"
    }
    published_ids = active_ids | retained_archived_ids
    prunable_ids = directory_ids - published_ids

    missing_artifacts: dict[str, list[str]] = {}

    for candidate_id in sorted(published_ids):
        missing = [
            path.as_posix()
            for path in candidate_detail_artifacts(candidate_id)
            if not (root / path).exists()
        ]

        if missing:
            missing_artifacts[candidate_id] = missing

    return {
        "active_ids": sorted(active_ids),
        "retained_archived_ids": sorted(retained_archived_ids),
        "temporarily_missing_ids": sorted(temporarily_missing_ids),
        "published_ids": sorted(published_ids),
        "prunable_ids": sorted(prunable_ids),
        "missing_artifacts": missing_artifacts,
    }


def project_candidate_route_index(
    payload: Any,
    root: Path,
) -> dict[str, Any]:
    """Project every published candidate detail route and its lifecycle kind."""

    lifecycle = project_candidate_page_lifecycle(payload, root)

    if lifecycle["prunable_ids"]:
        raise CandidatePageContractError(
            "prunable candidate dossier directories remain: "
            + ", ".join(lifecycle["prunable_ids"])
        )

    if lifecycle["missing_artifacts"]:
        raise CandidatePageContractError(
            "published candidate dossiers are incomplete: "
            + ", ".join(sorted(lifecycle["missing_artifacts"]))
        )

    records_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in payload["candidates"]
    }
    active_ids = set(lifecycle["active_ids"])
    candidates = []

    for candidate_id in lifecycle["published_ids"]:
        candidate = records_by_id[candidate_id]
        routes = _candidate_routes(candidate_id)
        candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": candidate["candidate_name"],
                "status": candidate["status"],
                "display_tier": candidate["display_tier"],
                "lifecycle": (
                    "active"
                    if candidate_id in active_ids
                    else "archived"
                ),
                "routes": routes,
                "canonical": {
                    locale: f"{PUBLIC_ORIGIN}{route}"
                    for locale, route in routes.items()
                },
            }
        )

    candidates.sort(key=_sort_key)

    return {
        "schema_version": SCHEMA_VERSION,
        "hubs": {
            "fr": "/candidates/",
            "en": "/en/candidates/",
        },
        "counts": {
            "active": len(lifecycle["active_ids"]),
            "retained_archived": len(
                lifecycle["retained_archived_ids"]
            ),
            "published": len(candidates),
        },
        "candidates": candidates,
    }


def project_candidate_page_index(payload: Any) -> dict[str, Any]:
    """Project every currently active candidate into deterministic FR/EN routes.

    Eligibility belongs to candidate_candidacy_status.py. This module only
    projects that canonical active-monitoring universe into public page routes.
    """

    records = active_candidate_records(payload)
    monitoring_field = project_active_monitoring_field(payload)

    if monitoring_field["counts"]["active"] != len(records):
        raise CandidatePageContractError(
            "active monitoring count disagrees with active candidate records"
        )

    candidates: list[dict[str, Any]] = []

    for candidate in records:
        candidate_id = candidate["candidate_id"]
        routes = _candidate_routes(candidate_id)

        candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": candidate["candidate_name"],
                "status": candidate["status"],
                "display_tier": candidate["display_tier"],
                "routes": routes,
                "canonical": {
                    locale: f"{PUBLIC_ORIGIN}{route}"
                    for locale, route in routes.items()
                },
            }
        )

    candidates.sort(key=_sort_key)

    ids = [candidate["candidate_id"] for candidate in candidates]

    if len(ids) != len(set(ids)):
        raise CandidatePageContractError(
            "candidate-page projection contains duplicate candidate IDs"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "status_as_of": payload["status_as_of"],
        "provenance": active_projection_provenance(payload),
        "hubs": {
            "fr": "/candidates/",
            "en": "/en/candidates/",
        },
        "counts": {
            "main": monitoring_field["counts"]["main"],
            "secondary": monitoring_field["counts"]["secondary"],
            "active": len(records),
        },
        "candidates": candidates,
    }
