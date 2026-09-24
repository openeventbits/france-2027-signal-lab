"""Resolve candidate portraits from the root dashboard's canonical registry."""

from __future__ import annotations

import json
import re
from pathlib import Path


class CandidatePortraitRegistryError(ValueError):
    """Raised when the dashboard portrait registry cannot be read safely."""


_REGISTRY_PATTERN = re.compile(
    r"const\s+candidatePortraits\s*=\s*Object\.freeze\(\s*(\{.*?\})\s*\);",
    re.DOTALL,
)


def load_candidate_portraits(index_path: Path) -> dict[str, str]:
    """Parse the authoritative ``candidatePortraits`` mapping in index.html."""

    document = index_path.read_text(encoding="utf-8")
    matches = _REGISTRY_PATTERN.findall(document)

    if len(matches) != 1:
        raise CandidatePortraitRegistryError(
            "expected exactly one candidatePortraits registry in index.html"
        )

    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise CandidatePortraitRegistryError(
            "candidatePortraits is not a JSON-compatible object"
        ) from exc

    if not isinstance(payload, dict):
        raise CandidatePortraitRegistryError(
            "candidatePortraits must be an object"
        )

    portraits: dict[str, str] = {}
    for candidate_name, path in payload.items():
        if not isinstance(candidate_name, str) or not candidate_name.strip():
            raise CandidatePortraitRegistryError(
                "candidatePortraits contains an invalid candidate name"
            )
        if not isinstance(path, str) or not path.startswith("assets/candidates/"):
            raise CandidatePortraitRegistryError(
                f"candidatePortraits path is invalid for {candidate_name!r}"
            )
        portraits[candidate_name] = "/" + path

    return portraits


def resolve_candidate_portrait(
    candidate_name: str,
    *,
    index_path: Path,
) -> str | None:
    """Return a verified root-relative portrait path, or ``None``."""

    return load_candidate_portraits(index_path).get(candidate_name)
