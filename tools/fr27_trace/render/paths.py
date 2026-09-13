"""Fail-closed repository paths for Task 02 fixtures and generated output."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = (REPOSITORY_ROOT / "_trace_output").resolve()
FIXTURE_ROOT = (Path(__file__).resolve().parents[1] / "fixtures").resolve()


class OutputPathError(ValueError):
    """Raised when a requested renderer path escapes its authorized root."""


def _resolve_beneath(requested: str | Path, root: Path, label: str) -> Path:
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    resolved = candidate.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise OutputPathError(f"{label} must resolve beneath {root}")
    return resolved


def resolve_output_path(requested: str | Path) -> Path:
    """Accept only PNG descendants of repository-root ``_trace_output``."""

    resolved = _resolve_beneath(requested, OUTPUT_ROOT, "output path")
    if resolved.suffix.lower() != ".png":
        raise OutputPathError("output path must end in .png")
    return resolved


def fixture_path(requested: str | Path) -> Path:
    """Task 02 reads frozen TRACE-local fixtures only, never live FR27 data."""

    resolved = _resolve_beneath(requested, FIXTURE_ROOT, "fixture path")
    if resolved.suffix.lower() != ".json":
        raise OutputPathError("fixture path must end in .json")
    return resolved
