"""Canonical dynamic route/index contract for FR27 candidate pages.

The candidate-page universe is derived exclusively from Candidate Registry v2.
There is no fixed candidate count and no candidate-specific route list here.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from candidate_candidacy_status import (
    active_candidate_records,
    active_projection_provenance,
    project_active_monitoring_field,
)


SCHEMA_VERSION = "1.0"
PUBLIC_ORIGIN = "https://france2027.app"


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
