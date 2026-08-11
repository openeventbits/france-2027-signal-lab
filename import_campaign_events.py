"""Safe batch importer for model-assisted manual Campaign Events curation."""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from add_campaign_event import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_UPDATES_PATH,
    EVENT_TYPE_CHOICES,
    SOURCE_TYPE_CHOICES,
    AddProposal,
    CampaignEventCurationError,
    DuplicateMatch,
    LoadedManualDocuments,
    build_add_proposal,
    find_likely_duplicates,
    load_manual_documents,
    normalize_human_text,
    persist_manual_documents,
    transaction_timestamp,
    validate_manual_documents,
)
from update_campaign_event import REMOVE, UpdateProposal, build_update_proposal


SCHEMA_VERSION = "1.0"
_TOP_LEVEL_KEYS = frozenset({"schema_version", "new_events", "updates"})
_NEW_REQUIRED_KEYS = frozenset(
    {"title", "date", "event_type", "source_url", "source_publisher", "source_type"}
)
_NEW_OPTIONAL_KEYS = frozenset(
    {
        "time",
        "participants",
        "organization",
        "location_name",
        "locality",
        "department",
    }
)
_UPDATE_REQUIRED_KEYS = frozenset(
    {
        "event_key",
        "action",
        "headline",
        "source_url",
        "source_publisher",
        "source_type",
    }
)
_UPDATE_OPTIONAL_KEYS = frozenset({"changes"})
_CHANGE_KEYS = frozenset(
    {
        "title",
        "date",
        "time",
        "event_type",
        "participants",
        "organization",
        "location_name",
        "locality",
        "department",
    }
)
_REQUIRED_CHANGE_FIELDS = frozenset({"title", "date", "event_type"})
_ACTIONS = frozenset({"CONFIRMED", "UPDATED", "POSTPONED", "CANCELLED"})
_EVENT_TYPES = frozenset(value for value, _label in EVENT_TYPE_CHOICES)
_SOURCE_TYPES = frozenset(value for value, _label in SOURCE_TYPE_CHOICES)
_EVENT_KEY = re.compile(r"manual-[0-9a-f]{32}\Z", re.ASCII)


class BatchImportError(ValueError):
    """Raised when a proposed batch cannot be applied safely."""


@dataclass(frozen=True)
class BatchProposal:
    """One fully validated, in-memory two-document transaction."""

    events_payload: dict[str, Any]
    updates_payload: dict[str, Any]
    additions: tuple[AddProposal, ...]
    updates: tuple[UpdateProposal, ...]
    timestamp: str


def _exact_keys(
    value: dict[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing or unexpected:
        raise BatchImportError(
            f"{context} must have exact allowed keys; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _text(value: Any, context: str) -> str:
    try:
        return normalize_human_text(value, context)
    except CampaignEventCurationError as error:
        raise BatchImportError(str(error)) from error


def _choice(value: Any, allowed: frozenset[str], context: str) -> str:
    normalized = _text(value, context)
    if normalized not in allowed:
        raise BatchImportError(f"{context} is not an allowed value")
    return normalized


def _participants(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise BatchImportError(f"{context} must be a JSON array of full names")
    participants = [
        _text(participant, f"{context}[{index}]")
        for index, participant in enumerate(value)
    ]
    if len(set(participants)) != len(participants):
        raise BatchImportError(f"{context} must not contain duplicate names")
    return participants


def load_batch_payload(path: str | Path) -> Any:
    """Read one UTF-8 JSON payload without altering it."""

    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as error:
        raise BatchImportError(f"could not read batch file {target}: {error}") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BatchImportError(f"batch file {target} is not UTF-8: {error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise BatchImportError(f"batch file {target} is malformed JSON: {error}") from error


def _normalize_new_event(value: Any, index: int) -> dict[str, Any]:
    context = f"new_events[{index}]"
    if type(value) is not dict:
        raise BatchImportError(f"{context} must be a JSON object")
    _exact_keys(value, _NEW_REQUIRED_KEYS, _NEW_OPTIONAL_KEYS, context)
    normalized: dict[str, Any] = {
        "title": _text(value["title"], f"{context}.title"),
        "date": _text(value["date"], f"{context}.date"),
        "event_type": _choice(
            value["event_type"], _EVENT_TYPES, f"{context}.event_type"
        ),
        "source_url": _text(value["source_url"], f"{context}.source_url"),
        "source_publisher": _text(
            value["source_publisher"], f"{context}.source_publisher"
        ),
        "source_type": _choice(
            value["source_type"], _SOURCE_TYPES, f"{context}.source_type"
        ),
    }
    for field in ("time", "organization", "location_name", "locality", "department"):
        if field in value:
            normalized[field] = _text(value[field], f"{context}.{field}")
    if "participants" in value:
        normalized["participants"] = _participants(
            value["participants"], f"{context}.participants"
        )
    return normalized


def _normalize_changes(value: Any, context: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise BatchImportError(f"{context} must be a JSON object")
    unexpected = sorted(set(value) - _CHANGE_KEYS)
    if unexpected:
        raise BatchImportError(f"{context} has unexpected fields: {unexpected}")
    normalized: dict[str, Any] = {}
    for field, supplied in value.items():
        field_context = f"{context}.{field}"
        if supplied is None:
            if field in _REQUIRED_CHANGE_FIELDS:
                raise BatchImportError(f"{field_context} may not be null")
            normalized[field] = REMOVE
        elif field == "participants":
            normalized[field] = _participants(supplied, field_context)
        elif field == "event_type":
            normalized[field] = _choice(supplied, _EVENT_TYPES, field_context)
        else:
            normalized[field] = _text(supplied, field_context)
    return normalized


def _normalize_update(value: Any, index: int) -> dict[str, Any]:
    context = f"updates[{index}]"
    if type(value) is not dict:
        raise BatchImportError(f"{context} must be a JSON object")
    _exact_keys(value, _UPDATE_REQUIRED_KEYS, _UPDATE_OPTIONAL_KEYS, context)
    event_key = value["event_key"]
    if not isinstance(event_key, str) or not _EVENT_KEY.fullmatch(event_key):
        raise BatchImportError(
            f"{context}.event_key must be manual- plus 32 lowercase hex characters"
        )
    action = _choice(value["action"], _ACTIONS, f"{context}.action")
    has_changes = "changes" in value
    if action != "UPDATED" and has_changes:
        raise BatchImportError(f"{context}.changes is forbidden for action {action}")
    changes = (
        _normalize_changes(value["changes"], f"{context}.changes")
        if has_changes
        else {}
    )
    return {
        "event_key": event_key,
        "action": action,
        "changes": changes,
        "headline": _text(value["headline"], f"{context}.headline"),
        "source_url": _text(value["source_url"], f"{context}.source_url"),
        "source_publisher": _text(
            value["source_publisher"], f"{context}.source_publisher"
        ),
        "source_type": _choice(
            value["source_type"], _SOURCE_TYPES, f"{context}.source_type"
        ),
    }


def normalize_batch_payload(payload: Any) -> dict[str, Any]:
    """Enforce the exact model-facing v1 batch contract."""

    if type(payload) is not dict:
        raise BatchImportError("batch payload must be a JSON object")
    _exact_keys(payload, _TOP_LEVEL_KEYS, frozenset(), "batch payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise BatchImportError("schema_version must be exactly '1.0'")
    if not isinstance(payload["new_events"], list):
        raise BatchImportError("new_events must be a JSON array")
    if not isinstance(payload["updates"], list):
        raise BatchImportError("updates must be a JSON array")
    return {
        "schema_version": SCHEMA_VERSION,
        "new_events": [
            _normalize_new_event(value, index)
            for index, value in enumerate(payload["new_events"])
        ],
        "updates": [
            _normalize_update(value, index)
            for index, value in enumerate(payload["updates"])
        ],
    }


def _duplicate_error(index: int, matches: list[DuplicateMatch]) -> BatchImportError:
    lines = [f"new_events[{index}] is a likely duplicate:"]
    for match in matches:
        lines.append(
            f"- {match.date} · {match.title} [{match.event_key}]: "
            f"{', '.join(match.reasons)}"
        )
    return BatchImportError("\n".join(lines))


def build_batch_proposal(
    events_payload: dict[str, Any],
    updates_payload: dict[str, Any],
    batch: dict[str, Any],
    *,
    timestamp: str,
    uuid_factory: Callable[[], Any] = uuid.uuid4,
) -> BatchProposal:
    """Build and validate the complete transaction without performing I/O."""

    try:
        validate_manual_documents(events_payload, updates_payload)
        starting_event_keys = {
            event["event_key"] for event in events_payload["events"]
        }
    except (CampaignEventCurationError, KeyError, TypeError, ValueError) as error:
        raise BatchImportError(f"existing manual documents are invalid: {error}") from error

    proposed_events = events_payload
    proposed_updates = updates_payload
    additions: list[AddProposal] = []
    update_proposals: list[UpdateProposal] = []

    for index, facts in enumerate(batch["new_events"]):
        try:
            proposal = build_add_proposal(
                proposed_events,
                proposed_updates,
                facts,
                timestamp=timestamp,
                uuid_factory=uuid_factory,
            )
            matches = find_likely_duplicates(
                proposed_events["events"], proposal.event
            )
        except (CampaignEventCurationError, KeyError, TypeError, ValueError) as error:
            raise BatchImportError(f"new_events[{index}]: {error}") from error
        if matches:
            raise _duplicate_error(index, matches)
        proposed_events = proposal.events_payload
        proposed_updates = proposal.updates_payload
        additions.append(proposal)

    targeted: set[str] = set()
    current_event_keys = {
        event["event_key"] for event in proposed_events["events"]
    }
    for index, update in enumerate(batch["updates"]):
        event_key = update["event_key"]
        if event_key not in starting_event_keys:
            if event_key in current_event_keys:
                raise BatchImportError(
                    f"updates[{index}].event_key may not target an event created "
                    "in the same batch"
                )
            raise BatchImportError(
                f"updates[{index}].event_key does not reference an event that "
                "existed before the batch"
            )
        if event_key in targeted:
            raise BatchImportError(
                f"updates[{index}].event_key targets {event_key} more than once"
            )
        targeted.add(event_key)
        try:
            proposal = build_update_proposal(
                proposed_events,
                proposed_updates,
                event_key=event_key,
                action=update["action"],
                changes=update["changes"],
                headline=update["headline"],
                source={
                    "source_url": update["source_url"],
                    "source_publisher": update["source_publisher"],
                    "source_type": update["source_type"],
                },
                timestamp=timestamp,
                uuid_factory=uuid_factory,
            )
        except (CampaignEventCurationError, KeyError, TypeError, ValueError) as error:
            raise BatchImportError(f"updates[{index}]: {error}") from error
        proposed_events = proposal.events_payload
        proposed_updates = proposal.updates_payload
        update_proposals.append(proposal)

    try:
        validate_manual_documents(proposed_events, proposed_updates)
    except (CampaignEventCurationError, ValueError) as error:
        raise BatchImportError(f"resulting manual documents are invalid: {error}") from error
    return BatchProposal(
        events_payload=proposed_events,
        updates_payload=proposed_updates,
        additions=tuple(additions),
        updates=tuple(update_proposals),
        timestamp=timestamp,
    )


def print_batch_preview(
    proposal: BatchProposal,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Print one compact human review of the complete transaction."""

    output_fn("=" * 60)
    output_fn("FR27 CAMPAIGN EVENTS IMPORT")
    output_fn("=" * 60)
    output_fn("")
    output_fn(f"NEW EVENTS: {len(proposal.additions)}")
    output_fn(f"UPDATES:    {len(proposal.updates)}")
    if proposal.additions:
        output_fn("")
        output_fn("NEW")
    for addition in proposal.additions:
        event = addition.event
        schedule = event["date"] + (f" {event['time']}" if "time" in event else "")
        output_fn(f"+ {schedule} · {event['event_type'].upper()}")
        output_fn(f"  {event['title']}")
        if event.get("participants"):
            output_fn(f"  {' · '.join(event['participants'])}")
        output_fn(f"  {event['source_publisher']}")
    for update in proposal.updates:
        event = update.event
        action = update.update["update_type"]
        symbol = {
            "CONFIRMED": "✓",
            "UPDATED": "~",
            "POSTPONED": "!",
            "CANCELLED": "×",
        }[action]
        output_fn("")
        output_fn(action)
        output_fn(f"{symbol} {event['date']} · {event['title']}")
        output_fn(f"  {update.update['source_publisher']}")
    source_count = len(proposal.additions) + len(proposal.updates)
    output_fn("")
    output_fn("SOURCES")
    output_fn(f"{source_count} exact HTTPS supporting URLs")
    output_fn("")
    output_fn("DUPLICATE WARNINGS")
    output_fn("0")
    output_fn("")
    output_fn("=" * 60)


def run_batch_import(
    file_path: str | Path,
    *,
    events_path: str | Path = DEFAULT_EVENTS_PATH,
    updates_path: str | Path = DEFAULT_UPDATES_PATH,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    uuid_factory: Callable[[], Any] = uuid.uuid4,
    replace_func: Callable[[str | bytes | os.PathLike[str], str | bytes | os.PathLike[str]], None] = os.replace,
    persistence_fn: Callable[..., None] = persist_manual_documents,
) -> int:
    """Validate, preview, confirm once, and atomically apply one batch."""

    try:
        loaded: LoadedManualDocuments = load_manual_documents(events_path, updates_path)
        validate_manual_documents(loaded.events_payload, loaded.updates_payload)
        batch = normalize_batch_payload(load_batch_payload(file_path))
        if not batch["new_events"] and not batch["updates"]:
            output_fn("No Campaign Events changes proposed.")
            return 0
        timestamp = transaction_timestamp(now_factory())
        proposal = build_batch_proposal(
            loaded.events_payload,
            loaded.updates_payload,
            batch,
            timestamp=timestamp,
            uuid_factory=uuid_factory,
        )
        print_batch_preview(proposal, output_fn)
        if input_fn("Apply this batch? [y/N]: ").strip().casefold() not in {"y", "yes"}:
            output_fn("No changes made.")
            return 0
        persistence_fn(
            proposal.events_payload,
            proposal.updates_payload,
            events_path=events_path,
            updates_path=updates_path,
            expected_events_bytes=loaded.events_bytes,
            expected_updates_bytes=loaded.updates_bytes,
            replace_func=replace_func,
        )
        output_fn("Campaign Events batch applied.")
        return 0
    except (BatchImportError, CampaignEventCurationError, ValueError, OSError) as error:
        output_fn(f"Error: {error}")
        return 1


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely import one model-assisted Campaign Events JSON batch."
    )
    parser.add_argument("--file", required=True, type=Path, help="UTF-8 JSON batch file")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    return run_batch_import(arguments.file)


if __name__ == "__main__":
    raise SystemExit(main())
