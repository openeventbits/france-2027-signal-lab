"""First-round polling event contract and deterministic identity helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Iterable


FIRST_ROUND = "first_round"
COMPLETE = "complete"
PARTIAL = "partial"
COMPLETENESS_STATES = {COMPLETE, PARTIAL}
MIN_COMPLETE_TOTAL = 99.0
MAX_COMPLETE_TOTAL = 101.0
MAX_POSSIBLE_TOTAL = 101.0


class PollContractError(ValueError):
    """Raised when a first-round event violates the publication contract."""


def normalize_identity(value: str) -> str:
    """Normalize identity text for stable hashes and duplicate checks."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )
    value = value.casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def make_scenario_key(
    names: Iterable[str], *, round_name: str = FIRST_ROUND
) -> str:
    normalized_names = sorted(normalize_identity(name) for name in names)
    material = round_name + "|" + "|".join(normalized_names)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def make_event_id(
    pollster: str,
    fieldwork_start: str,
    fieldwork_end: str,
    hypothesis: str,
    source_url: str,
    *,
    round_name: str = FIRST_ROUND,
) -> str:
    material = (
        normalize_identity(pollster)
        + fieldwork_start
        + fieldwork_end
        + round_name
        + normalize_identity(hypothesis)
        + source_url
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _numeric(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PollContractError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise PollContractError(f"{field} must be finite")
    return number


def reported_candidate_total(candidates: Any) -> float:
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise PollContractError("candidates must contain at least two results")

    scores = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise PollContractError(f"candidate {index} must be an object")
        score = _numeric(
            candidate.get("score"),
            field=f"candidate {index} score",
        )
        if score < 0:
            raise PollContractError(
                f"candidate {index} score must not be negative"
            )
        scores.append(score)

    return round(math.fsum(scores), 10)


def derive_completeness(candidates: Any) -> dict[str, Any]:
    """Derive additive completeness metadata without inventing support."""
    total = reported_candidate_total(candidates)
    if total <= 0 or total > MAX_POSSIBLE_TOTAL:
        raise PollContractError(f"reported total is impossible: {total:g}")

    complete = MIN_COMPLETE_TOTAL <= total <= MAX_COMPLETE_TOTAL
    return {
        "reported_total": total,
        "completeness_status": COMPLETE if complete else PARTIAL,
        "partial_scenario": not complete,
        "unreported_share": (
            None if complete else round(100.0 - total, 10)
        ),
    }


def apply_completeness_contract(event: dict[str, Any]) -> dict[str, Any]:
    """Add derived completeness fields to an event in place."""
    event.update(derive_completeness(event.get("candidates")))
    return event


def _required_text(event: dict[str, Any], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PollContractError(f"{field} must be a non-empty string")
    return value


def _iso_date(event: dict[str, Any], field: str) -> date:
    value = _required_text(event, field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise PollContractError(f"{field} must be a valid ISO date") from error
    if parsed.isoformat() != value:
        raise PollContractError(f"{field} must use YYYY-MM-DD")
    return parsed


def validate_poll_event(event: Any) -> None:
    """Validate one explicit first-round event contract."""
    if not isinstance(event, dict):
        raise PollContractError("event must be an object")

    event_id = _required_text(event, "event_id")
    if not re.fullmatch(r"[0-9a-f]{64}", event_id):
        raise PollContractError("event_id must be a lowercase SHA-256")

    pollster = _required_text(event, "pollster")
    hypothesis = _required_text(event, "hypothesis")
    source_url = _required_text(event, "source_url")
    if not source_url.startswith(("http://", "https://")):
        raise PollContractError("source_url must be HTTP(S)")

    fieldwork_start = _iso_date(event, "fieldwork_start")
    fieldwork_end = _iso_date(event, "fieldwork_end")
    if fieldwork_start > fieldwork_end:
        raise PollContractError(
            "fieldwork_start must not be after fieldwork_end"
        )

    if event.get("round") != FIRST_ROUND:
        raise PollContractError("round must equal first_round")

    candidates = event.get("candidates")
    total = reported_candidate_total(candidates)
    normalized_names: list[str] = []
    for index, candidate in enumerate(candidates):
        name = candidate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PollContractError(
                f"candidate {index} name must be a non-empty string"
            )
        normalized_names.append(normalize_identity(name))
    if len(normalized_names) != len(set(normalized_names)):
        raise PollContractError("event contains a duplicate candidate")

    expected_scenario_key = make_scenario_key(normalized_names)
    if event.get("scenario_key") != expected_scenario_key:
        raise PollContractError("scenario_key is not deterministic")

    expected_event_id = make_event_id(
        pollster,
        fieldwork_start.isoformat(),
        fieldwork_end.isoformat(),
        hypothesis,
        source_url,
    )
    if event_id != expected_event_id:
        raise PollContractError("event_id is not deterministic")

    expected = derive_completeness(candidates)
    actual_total = _numeric(
        event.get("reported_total"),
        field="reported_total",
    )
    if not math.isclose(
        actual_total,
        total,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise PollContractError(
            "reported_total does not equal the candidate-score total"
        )

    status = event.get("completeness_status")
    if status not in COMPLETENESS_STATES:
        raise PollContractError("completeness_status is invalid")
    if status != expected["completeness_status"]:
        raise PollContractError(
            "completeness_status contradicts reported_total"
        )

    partial_marker = event.get("partial_scenario")
    if not isinstance(partial_marker, bool):
        raise PollContractError("partial_scenario must be boolean")
    if partial_marker != expected["partial_scenario"]:
        raise PollContractError(
            "partial_scenario contradicts completeness_status"
        )

    unreported_share = event.get("unreported_share")
    expected_unreported = expected["unreported_share"]
    if expected_unreported is None:
        if unreported_share is not None:
            raise PollContractError(
                "complete scenarios must not claim unreported share"
            )
    else:
        actual_unreported = _numeric(
            unreported_share,
            field="unreported_share",
        )
        if actual_unreported < 0 or not math.isclose(
            actual_unreported,
            expected_unreported,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise PollContractError(
                "unreported_share contradicts reported_total"
            )


def validate_poll_events(events: Any) -> dict[str, int]:
    """Validate a publication payload and return completeness counts."""
    if not isinstance(events, list) or not events:
        raise PollContractError("poll payload must be a non-empty list")

    event_ids: set[str] = set()
    counts = {COMPLETE: 0, PARTIAL: 0, "invalid": 0}
    for index, event in enumerate(events):
        try:
            validate_poll_event(event)
        except PollContractError as error:
            counts["invalid"] += 1
            raise PollContractError(f"event {index}: {error}") from error
        if event["event_id"] in event_ids:
            raise PollContractError(
                f"event {index}: duplicate event_id {event['event_id']}"
            )
        event_ids.add(event["event_id"])
        counts[event["completeness_status"]] += 1
    return counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the explicit first-round poll-event contract"
    )
    parser.add_argument("path", nargs="?", default="polls.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    path = Path(arguments.path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = validate_poll_events(payload)
    except (OSError, json.JSONDecodeError, PollContractError) as error:
        print(f"poll contract error: {error}")
        return 1
    print(
        f"validated {len(payload)} events "
        f"({counts[COMPLETE]} complete, {counts[PARTIAL]} partial)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
