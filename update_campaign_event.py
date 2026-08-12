"""Interactive and callable helpers for updating one manual Campaign Event."""

from __future__ import annotations

import copy
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from add_campaign_event import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_UPDATES_PATH,
    EVENT_TYPE_CHOICES,
    SOURCE_TYPE_CHOICES,
    CampaignEventCurationError,
    LoadedManualDocuments,
    generate_update_key,
    load_manual_documents,
    normalize_human_text,
    parse_participants,
    persist_manual_documents,
    transaction_timestamp,
    validate_manual_documents,
)
from campaign_event_sources import normalize_https_url


KEEP = object()
REMOVE = object()
UPDATE_ACTIONS = (
    ("CONFIRMED", "Confirmed"),
    ("UPDATED", "Updated / rescheduled"),
    ("POSTPONED", "Postponed"),
    ("CANCELLED", "Cancelled"),
)
_EDITABLE_FIELDS = (
    "title",
    "date",
    "time",
    "event_type",
    "participants",
    "organization",
    "location_name",
    "locality",
    "department",
)
_OPTIONAL_FIELDS = frozenset(
    {
        "time",
        "participants",
        "organization",
        "location_name",
        "locality",
        "department",
    }
)


@dataclass(frozen=True)
class UpdateProposal:
    events_payload: dict[str, Any]
    updates_payload: dict[str, Any]
    previous_event: dict[str, Any]
    event: dict[str, Any]
    update: dict[str, Any]
    normalized_event: dict[str, Any]
    normalized_update: dict[str, Any]


def _normalize_source(source: dict[str, Any]) -> dict[str, str]:
    return {
        "source_url": normalize_https_url(source.get("source_url"), "source_url"),
        "source_publisher": normalize_human_text(
            source.get("source_publisher"), "source publisher"
        ),
        "source_type": normalize_human_text(source.get("source_type"), "source type"),
    }


def _apply_changes(event: dict[str, Any], changes: dict[str, Any]) -> bool:
    concrete_replacement_schedule = False
    unexpected = sorted(set(changes) - set(_EDITABLE_FIELDS))
    if unexpected:
        raise CampaignEventCurationError(f"unsupported event fields: {unexpected}")
    for field, value in changes.items():
        if value is KEEP:
            continue
        if value is REMOVE:
            if field not in _OPTIONAL_FIELDS:
                raise CampaignEventCurationError(f"required field {field} cannot be removed")
            if field in event:
                del event[field]
            continue
        if field == "participants":
            normalized = (
                parse_participants(value)
                if isinstance(value, str)
                else [normalize_human_text(item, "participant") for item in value]
            )
            if normalized:
                event[field] = normalized
            else:
                event.pop(field, None)
        else:
            normalized = normalize_human_text(value, field)
            if field in {"date", "time"} and event.get(field) != normalized:
                concrete_replacement_schedule = True
            event[field] = normalized
    return concrete_replacement_schedule


def build_update_proposal(
    events_payload: dict[str, Any],
    updates_payload: dict[str, Any],
    *,
    event_key: str,
    action: str,
    changes: dict[str, Any] | None,
    headline: str,
    source: dict[str, Any],
    timestamp: str | None = None,
    now: datetime | None = None,
    uuid_factory: Callable[[], Any] = uuid.uuid4,
) -> UpdateProposal:
    """Build and validate one event mutation plus one appended watch entry."""

    if action not in {value for value, _ in UPDATE_ACTIONS}:
        raise CampaignEventCurationError(f"unsupported update action: {action!r}")
    captured = timestamp if timestamp is not None else transaction_timestamp(now)
    proposed_events = copy.deepcopy(events_payload)
    proposed_updates = copy.deepcopy(updates_payload)
    try:
        matches = [
            event
            for event in proposed_events["events"]
            if event.get("event_key") == event_key
        ]
    except (KeyError, TypeError) as error:
        raise CampaignEventCurationError(
            "existing manual Campaign Events document has no valid events array"
        ) from error
    if len(matches) != 1:
        raise CampaignEventCurationError(
            "selected event_key must resolve to exactly one manual event"
        )
    event = matches[0]
    previous_event = copy.deepcopy(event)
    current_status = event.get("status", "scheduled")
    supplied_changes = changes or {}

    if current_status == "completed":
        raise CampaignEventCurationError(
            "completed events are terminal and cannot be changed by this v1 helper"
        )

    if action == "CONFIRMED":
        if current_status != "scheduled":
            raise CampaignEventCurationError(
                "CONFIRMED is only supported for a currently scheduled event"
            )
        if supplied_changes:
            raise CampaignEventCurationError("CONFIRMED does not edit event facts")
        event["status"] = "scheduled"
    elif action == "UPDATED":
        if current_status == "cancelled":
            raise CampaignEventCurationError(
                "revival of a cancelled event is not supported by this v1 helper"
            )
        concrete_replacement_schedule = _apply_changes(event, supplied_changes)
        if current_status == "postponed" and concrete_replacement_schedule:
            event["status"] = "scheduled"
        else:
            event["status"] = current_status
    elif action == "POSTPONED":
        if supplied_changes:
            raise CampaignEventCurationError("POSTPONED does not edit event facts")
        event["status"] = "postponed"
    else:
        if supplied_changes:
            raise CampaignEventCurationError("CANCELLED does not edit event facts")
        event["status"] = "cancelled"

    normalized_source = _normalize_source(source)
    event.update(normalized_source)
    event["last_verified_at"] = captured
    normalized_headline = normalize_human_text(headline, "Event Watch headline")
    update = {
        "update_key": generate_update_key(uuid_factory),
        "event_key": event_key,
        "update_type": action,
        "headline": normalized_headline,
        "source_url": normalized_source["source_url"],
        "source_publisher": normalized_source["source_publisher"],
        "source_type": normalized_source["source_type"],
        "observed_at": captured,
    }
    try:
        proposed_updates["updates"].append(update)
    except (KeyError, AttributeError) as error:
        raise CampaignEventCurationError(
            "existing manual Event Watch document has no valid updates array"
        ) from error
    normalized_events, normalized_updates = validate_manual_documents(
        proposed_events, proposed_updates
    )
    normalized_event = next(
        value for value in normalized_events if value["event_key"] == event_key
    )
    normalized_update = next(
        value
        for value in normalized_updates
        if value["update_key"] == update["update_key"]
    )
    return UpdateProposal(
        events_payload=proposed_events,
        updates_payload=proposed_updates,
        previous_event=previous_event,
        event=event,
        update=update,
        normalized_event=normalized_event,
        normalized_update=normalized_update,
    )


def sorted_events_for_selection(
    events: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return curator selection order without changing source insertion history."""

    current_date = today if today is not None else datetime.now().astimezone().date()

    def sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
        event_date = date.fromisoformat(event["date"])
        schedule = event["date"] + "T" + event.get("time", "99:99")
        status = event.get("status", "scheduled")
        if event_date >= current_date and status == "scheduled":
            return (0, schedule, event["event_key"])
        if event_date >= current_date and status in {"postponed", "cancelled"}:
            return (1, schedule, event["event_key"])
        return (2, -event_date.toordinal(), schedule, event["event_key"])

    return sorted(events, key=sort_key)


def _prompt_source_type(
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    *,
    default: str | None,
) -> str:
    for index, (value, label) in enumerate(SOURCE_TYPE_CHOICES, start=1):
        output_fn(f"{index} {value} — {label}")
    suffix = f" [default: {default}]" if default is not None else ""
    supplied = input_fn(f"Source type{suffix}: ").strip()
    if not supplied and default is not None:
        return default
    try:
        return SOURCE_TYPE_CHOICES[int(supplied) - 1][0]
    except (ValueError, IndexError):
        raise CampaignEventCurationError(f"invalid source type choice: {supplied!r}") from None


def _prompt_with_default(
    input_fn: Callable[[str], str],
    label: str,
    default: str,
) -> str:
    supplied = input_fn(f"{label} [default: {default}]: ")
    return default if not supplied.strip() else supplied


def _prompt_edit(
    input_fn: Callable[[str], str],
    label: str,
    current: str,
    *,
    optional: bool,
) -> Any:
    supplied = input_fn(f"{label} [{current}]: ")
    if not supplied.strip():
        return KEEP
    if supplied.strip() == "-":
        if not optional:
            raise CampaignEventCurationError(f"{label} is required and cannot be removed")
        return REMOVE
    return supplied


def _collect_updated_changes(
    event: dict[str, Any],
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    changes["title"] = _prompt_edit(
        input_fn, "Title", event["title"], optional=False
    )
    changes["date"] = _prompt_edit(input_fn, "Date", event["date"], optional=False)
    changes["time"] = _prompt_edit(
        input_fn, "Time", event.get("time", "none"), optional=True
    )
    for index, (value, label) in enumerate(EVENT_TYPE_CHOICES, start=1):
        output_fn(f"{index} {value} — {label}")
    raw_type = input_fn(f"Event type [{event['event_type']}]: ").strip()
    if not raw_type:
        changes["event_type"] = KEEP
    elif raw_type == "-":
        raise CampaignEventCurationError("Event type is required and cannot be removed")
    else:
        try:
            changes["event_type"] = EVENT_TYPE_CHOICES[int(raw_type) - 1][0]
        except (ValueError, IndexError):
            raise CampaignEventCurationError(
                f"invalid event type choice: {raw_type!r}"
            ) from None
    participants = ", ".join(event.get("participants", [])) or "none"
    changes["participants"] = _prompt_edit(
        input_fn, "Participants", participants, optional=True
    )
    for field, label in (
        ("organization", "Organization"),
        ("location_name", "Location"),
        ("locality", "City/locality"),
        ("department", "Department code"),
    ):
        changes[field] = _prompt_edit(
            input_fn, label, event.get(field, "none"), optional=True
        )
    return changes


def _print_event_list(events: list[dict[str, Any]], output_fn: Callable[[str], None]) -> None:
    for index, event in enumerate(events, start=1):
        time_value = event.get("time", "")
        schedule = f"{event['date']} {time_value:<5}"
        output_fn(
            f"[{index}] {schedule} · {event['event_type'].upper():<16} · {event['title']}"
        )


def _print_update_preview(
    proposal: UpdateProposal,
    output_fn: Callable[[str], None],
) -> None:
    output_fn("-" * 50)
    output_fn("PREVIOUS EVENT")
    for field in _EDITABLE_FIELDS + ("status",):
        output_fn(f"{field}: {proposal.previous_event.get(field, '—')}")
    output_fn("")
    output_fn("PROPOSED EVENT")
    for field in _EDITABLE_FIELDS + ("status",):
        output_fn(f"{field}: {proposal.event.get(field, '—')}")
    output_fn("")
    output_fn(
        f"Event Watch: {proposal.update['update_type']} · {proposal.update['headline']}"
    )
    output_fn(proposal.update["source_publisher"])
    output_fn(proposal.update["source_url"])
    output_fn("-" * 50)


def _selected_event(
    loaded: LoadedManualDocuments,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    *,
    today: date | None,
) -> dict[str, Any] | None:
    events = sorted_events_for_selection(loaded.events_payload["events"], today=today)
    if not events:
        output_fn("No manual Campaign Events are available.")
        return None
    _print_event_list(events, output_fn)
    supplied = input_fn("Select event [number]: ").strip()
    try:
        return events[int(supplied) - 1]
    except (ValueError, IndexError):
        raise CampaignEventCurationError(f"invalid event selection: {supplied!r}") from None


def run_update_interactive(
    *,
    events_path: str | Path = DEFAULT_EVENTS_PATH,
    updates_path: str | Path = DEFAULT_UPDATES_PATH,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    uuid_factory: Callable[[], Any] = uuid.uuid4,
    replace_func: Callable[[str | bytes | os.PathLike[str], str | bytes | os.PathLike[str]], None] = os.replace,
    today: date | None = None,
) -> int:
    """Run the update flow; dependencies are injectable for deterministic tests."""

    try:
        loaded = load_manual_documents(events_path, updates_path)
        validate_manual_documents(loaded.events_payload, loaded.updates_payload)
        output_fn("=== UPDATE KEY CAMPAIGN EVENT ===")
        selected = _selected_event(
            loaded, input_fn, output_fn, today=today
        )
        if selected is None:
            return 0
        output_fn("What changed?")
        for index, (_, label) in enumerate(UPDATE_ACTIONS, start=1):
            output_fn(f"{index} {label}")
        output_fn("5 Exit")
        action_choice = input_fn("Select action [1-5]: ").strip()
        if action_choice == "5":
            output_fn("No changes made.")
            return 0
        try:
            action = UPDATE_ACTIONS[int(action_choice) - 1][0]
        except (ValueError, IndexError):
            raise CampaignEventCurationError(
                f"invalid update action: {action_choice!r}"
            ) from None
        if action == "UPDATED" and selected.get("status", "scheduled") == "cancelled":
            raise CampaignEventCurationError(
                "revival of a cancelled event is not supported by this v1 helper"
            )

        changes = (
            _collect_updated_changes(selected, input_fn, output_fn)
            if action == "UPDATED"
            else {}
        )
        proposed_title = selected["title"]
        if action == "UPDATED" and changes.get("title") not in {KEEP, REMOVE}:
            proposed_title = normalize_human_text(changes["title"], "title")
        headline = _prompt_with_default(
            input_fn, "Event Watch headline", proposed_title
        )

        if action == "CONFIRMED":
            source_url = _prompt_with_default(
                input_fn, "Exact source URL", selected["source_url"]
            )
            publisher = _prompt_with_default(
                input_fn, "Publisher", selected["source_publisher"]
            )
            source_type = _prompt_source_type(
                input_fn,
                output_fn,
                default=selected["source_type"],
            )
        else:
            label = action.casefold()
            source_url = input_fn(f"Exact {label} source URL: ")
            publisher = input_fn("Publisher: ")
            source_type = _prompt_source_type(input_fn, output_fn, default=None)

        proposal = build_update_proposal(
            loaded.events_payload,
            loaded.updates_payload,
            event_key=selected["event_key"],
            action=action,
            changes=changes,
            headline=headline,
            source={
                "source_url": source_url,
                "source_publisher": publisher,
                "source_type": source_type,
            },
            now=now_factory(),
            uuid_factory=uuid_factory,
        )
        _print_update_preview(proposal, output_fn)
        if input_fn("Apply this update? [y/N]: ").strip().casefold() not in {"y", "yes"}:
            output_fn("No changes made.")
            return 0
        persist_manual_documents(
            proposal.events_payload,
            proposal.updates_payload,
            events_path=events_path,
            updates_path=updates_path,
            expected_events_bytes=loaded.events_bytes,
            expected_updates_bytes=loaded.updates_bytes,
            replace_func=replace_func,
        )
        output_fn("Event and Event Watch entry updated.")
        return 0
    except (CampaignEventCurationError, ValueError, OSError) as error:
        output_fn(f"Error: {error}")
        return 1


def main() -> int:
    return run_update_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
