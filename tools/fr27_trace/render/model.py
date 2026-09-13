"""Presentation-only model for the fixed TRACE renderer shell."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..contract import ContractError, validate_trace


FAMILY_LABELS = {
    "candidate": "CANDIDATE",
    "field": "FIELD",
    "issue": "ISSUE",
    "story": "STORY",
    "event": "EVENT",
}
RENDERER_VERSION = "trace-shell.v1"

_REQUIRED_PRESENTATION_FIELDS = frozenset(
    {
        "language",
        "display_label",
        "finding",
        "source_scope",
        "methodological_boundary",
        "observation_window_display",
        "renderer_version",
    }
)
_OPTIONAL_PRESENTATION_FIELDS = frozenset({"qualifier"})
_MAX_LENGTHS = {
    "display_label": 48,
    "finding": 120,
    "qualifier": 96,
    "source_scope": 88,
    "methodological_boundary": 88,
    "observation_window_display": 40,
    "renderer_version": 32,
}


class RenderModelError(ValueError):
    """Raised when presentation data cannot safely fit the frozen shell."""


def _one_line_text(value: Any, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise RenderModelError(f"presentation.{field} must be a non-empty string")
    if value != value.strip():
        raise RenderModelError(f"presentation.{field} must not have surrounding whitespace")
    if any(character in value for character in ("\r", "\n", "\t")):
        raise RenderModelError(f"presentation.{field} must be one line")
    if len(value) > _MAX_LENGTHS[field]:
        raise RenderModelError(
            f"presentation.{field} exceeds {_MAX_LENGTHS[field]} characters"
        )
    return value


@dataclass(frozen=True)
class TraceRenderModel:
    """Validated TRACE identity plus non-identity presentation metadata."""

    trace: Mapping[str, Any]
    language: str
    display_label: str
    finding: str
    qualifier: str | None
    source_scope: str
    methodological_boundary: str
    observation_window_display: str
    renderer_version: str

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "TraceRenderModel":
        if not isinstance(document, Mapping) or set(document) != {"trace", "presentation"}:
            raise RenderModelError("render fixture must contain exactly trace and presentation")

        trace = document["trace"]
        presentation = document["presentation"]
        if not isinstance(trace, Mapping):
            raise RenderModelError("trace must be an object")
        try:
            validate_trace(trace)
        except ContractError as exc:
            raise RenderModelError(f"invalid TRACE object: {exc}") from exc
        if not isinstance(presentation, Mapping):
            raise RenderModelError("presentation must be an object")
        fields = set(presentation)
        missing = _REQUIRED_PRESENTATION_FIELDS - fields
        if missing:
            raise RenderModelError(
                "presentation is missing required fields: " + ", ".join(sorted(missing))
            )
        unknown = fields - _REQUIRED_PRESENTATION_FIELDS - _OPTIONAL_PRESENTATION_FIELDS
        if unknown:
            raise RenderModelError(
                "presentation contains unknown fields: " + ", ".join(sorted(unknown))
            )

        language = presentation["language"]
        if language not in {"fr", "en"}:
            raise RenderModelError("presentation.language must be fr or en")
        if "language" in trace and trace["language"] != language:
            raise RenderModelError("presentation.language must match TRACE language when present")
        renderer_version = _one_line_text(
            presentation["renderer_version"], "renderer_version"
        )
        if renderer_version != RENDERER_VERSION:
            raise RenderModelError(f"renderer_version must be {RENDERER_VERSION!r}")

        return cls(
            trace=deepcopy(dict(trace)),
            language=language,
            display_label=_one_line_text(presentation["display_label"], "display_label"),
            finding=_one_line_text(presentation["finding"], "finding"),
            qualifier=_one_line_text(
                presentation.get("qualifier"), "qualifier", required=False
            ),
            source_scope=_one_line_text(presentation["source_scope"], "source_scope"),
            methodological_boundary=_one_line_text(
                presentation["methodological_boundary"], "methodological_boundary"
            ),
            observation_window_display=_one_line_text(
                presentation["observation_window_display"],
                "observation_window_display",
            ),
            renderer_version=renderer_version,
        )

    @property
    def family_label(self) -> str:
        return FAMILY_LABELS[self.trace["family"]]

    def to_payload(self) -> dict[str, Any]:
        """Return the minimal DOM payload; evidence stays in the validated TRACE object."""

        return {
            "family": self.family_label,
            "status": "TRACE DRAFT",
            "language": self.language,
            "displayLabel": self.display_label,
            "finding": self.finding,
            "qualifier": self.qualifier,
            "sourceScope": self.source_scope,
            "methodologicalBoundary": self.methodological_boundary,
            "observationWindow": self.observation_window_display,
            "rendererVersion": self.renderer_version,
        }
