"""Interactive and callable helpers for adding one manual Campaign Event."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from campaign_event_sources import normalize_https_url
from campaign_event_updates_manual import normalize_campaign_event_updates_manual
from campaign_events_manual import normalize_campaign_events_manual


ROOT = Path(__file__).resolve().parent
DEFAULT_EVENTS_PATH = ROOT / "campaign_events_manual.json"
DEFAULT_UPDATES_PATH = ROOT / "campaign_event_updates_manual.json"
EVENT_TYPE_CHOICES = (
    ("rally", "Rally"),
    ("public_meeting", "Public meeting"),
    ("debate", "Debate"),
    ("candidate_visit", "Candidate visit"),
    ("campaign_launch", "Campaign launch"),
    ("other", "Other"),
)
SOURCE_TYPE_CHOICES = (
    ("candidate_first_party", "Candidate first-party"),
    ("party_first_party", "Party first-party"),
    ("organizer_first_party", "Organizer first-party"),
    ("official_structured", "Official structured source"),
    ("official_unstructured", "Official webpage/document"),
    ("reliable_media", "Reliable media"),
)
_KEY = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)


class CampaignEventCurationError(ValueError):
    """Raised when a curation operation cannot be completed safely."""


@dataclass(frozen=True)
class LoadedManualDocuments:
    events_payload: dict[str, Any]
    updates_payload: dict[str, Any]
    events_bytes: bytes
    updates_bytes: bytes


@dataclass(frozen=True)
class AddProposal:
    events_payload: dict[str, Any]
    updates_payload: dict[str, Any]
    event: dict[str, Any]
    update: dict[str, Any]
    normalized_event: dict[str, Any]
    normalized_update: dict[str, Any]


@dataclass(frozen=True)
class DuplicateMatch:
    event_key: str
    title: str
    date: str
    reasons: tuple[str, ...]


def normalize_human_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise CampaignEventCurationError(f"{field} must be text")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not normalized:
        raise CampaignEventCurationError(f"{field} must not be blank")
    return normalized


def parse_participants(value: str) -> list[str]:
    """Parse comma-separated names while preserving each supplied full name."""

    if not isinstance(value, str):
        raise CampaignEventCurationError("participants must be text")
    participants = []
    for raw_name in value.split(","):
        if raw_name.strip():
            participants.append(normalize_human_text(raw_name, "participant"))
    return participants


def transaction_timestamp(now: datetime | None = None) -> str:
    """Capture one canonical second-precision UTC timestamp."""

    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise CampaignEventCurationError("transaction time must be timezone-aware")
    return instant.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _generated_key(prefix: str, uuid_factory: Callable[[], Any]) -> str:
    generated = uuid_factory()
    hex_value = getattr(generated, "hex", None)
    if not isinstance(hex_value, str) or not _KEY.fullmatch(hex_value):
        raise CampaignEventCurationError("UUID generator returned an invalid value")
    return prefix + hex_value


def generate_event_key(uuid_factory: Callable[[], Any] = uuid.uuid4) -> str:
    return _generated_key("manual-", uuid_factory)


def generate_update_key(uuid_factory: Callable[[], Any] = uuid.uuid4) -> str:
    return _generated_key("update-", uuid_factory)


def _read_json_document(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CampaignEventCurationError(f"could not read {label}: {error}") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignEventCurationError(f"{label} is malformed: {error}") from error
    if type(payload) is not dict:
        raise CampaignEventCurationError(f"{label} must contain a JSON object")
    return payload, raw


def load_manual_documents(
    events_path: str | Path = DEFAULT_EVENTS_PATH,
    updates_path: str | Path = DEFAULT_UPDATES_PATH,
) -> LoadedManualDocuments:
    event_target = Path(events_path)
    update_target = Path(updates_path)
    events_payload, events_bytes = _read_json_document(
        event_target, "manual Campaign Events file"
    )
    updates_payload, updates_bytes = _read_json_document(
        update_target, "manual Event Watch file"
    )
    return LoadedManualDocuments(
        events_payload=events_payload,
        updates_payload=updates_payload,
        events_bytes=events_bytes,
        updates_bytes=updates_bytes,
    )


def validate_manual_documents(
    events_payload: Any,
    updates_payload: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate both proposed source documents without writing either one."""

    normalized_events = normalize_campaign_events_manual(events_payload)
    normalized_updates = normalize_campaign_event_updates_manual(
        updates_payload,
        manual_events_payload=events_payload,
    )
    return normalized_events, normalized_updates


def serialize_manual_document(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _write_sibling_temp(target: Path, data: bytes, tag: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{target.name}.{tag}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def persist_manual_documents(
    events_payload: dict[str, Any],
    updates_payload: dict[str, Any],
    *,
    events_path: str | Path = DEFAULT_EVENTS_PATH,
    updates_path: str | Path = DEFAULT_UPDATES_PATH,
    expected_events_bytes: bytes | None = None,
    expected_updates_bytes: bytes | None = None,
    replace_func: Callable[[str | bytes | os.PathLike[str], str | bytes | os.PathLike[str]], None] = os.replace,
) -> None:
    """Validate and replace two files with bounded rollback of the first replace."""

    validate_manual_documents(events_payload, updates_payload)
    event_target = Path(events_path)
    update_target = Path(updates_path)
    try:
        original_events = event_target.read_bytes()
        original_updates = update_target.read_bytes()
    except OSError as error:
        raise CampaignEventCurationError(
            f"could not retain original manual source bytes: {error}"
        ) from error
    if expected_events_bytes is not None and original_events != expected_events_bytes:
        raise CampaignEventCurationError(
            "manual Campaign Events file changed during this transaction"
        )
    if expected_updates_bytes is not None and original_updates != expected_updates_bytes:
        raise CampaignEventCurationError(
            "manual Event Watch file changed during this transaction"
        )

    event_temp: Path | None = None
    update_temp: Path | None = None
    event_rollback: Path | None = None
    first_replaced = False
    try:
        event_temp = _write_sibling_temp(
            event_target, serialize_manual_document(events_payload), "proposed"
        )
        update_temp = _write_sibling_temp(
            update_target, serialize_manual_document(updates_payload), "proposed"
        )
        event_rollback = _write_sibling_temp(
            event_target, original_events, "rollback"
        )
        replace_func(event_temp, event_target)
        first_replaced = True
        event_temp = None
        replace_func(update_temp, update_target)
        update_temp = None
    except BaseException as error:
        if first_replaced and event_rollback is not None:
            try:
                replace_func(event_rollback, event_target)
                event_rollback = None
            except BaseException as rollback_error:
                raise CampaignEventCurationError(
                    "second file replacement failed and rollback also failed: "
                    f"{error}; rollback: {rollback_error}"
                ) from rollback_error
        raise CampaignEventCurationError(
            f"manual source transaction failed: {error}"
        ) from error
    finally:
        for temporary in (event_temp, update_temp, event_rollback):
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignEventCurationError(f"{field} must be text")
    if not value.strip():
        return None
    return normalize_human_text(value, field)


def build_add_proposal(
    events_payload: dict[str, Any],
    updates_payload: dict[str, Any],
    facts: dict[str, Any],
    *,
    timestamp: str | None = None,
    now: datetime | None = None,
    uuid_factory: Callable[[], Any] = uuid.uuid4,
) -> AddProposal:
    """Build and validate one appended event plus its automatic NEW update."""

    captured = timestamp if timestamp is not None else transaction_timestamp(now)
    event_key = generate_event_key(uuid_factory)
    update_key = generate_update_key(uuid_factory)
    title = normalize_human_text(facts.get("title"), "title")
    source_publisher = normalize_human_text(
        facts.get("source_publisher"), "source publisher"
    )
    source_url = normalize_https_url(facts.get("source_url"), "source_url")

    event: dict[str, Any] = {
        "event_key": event_key,
        "title": title,
        "date": normalize_human_text(facts.get("date"), "date"),
        "event_type": normalize_human_text(facts.get("event_type"), "event type"),
        "source_url": source_url,
        "source_publisher": source_publisher,
        "source_type": normalize_human_text(facts.get("source_type"), "source type"),
        "last_verified_at": captured,
        "status": "scheduled",
    }
    time_value = _optional_text(facts.get("time"), "time")
    if time_value is not None:
        event["time"] = time_value
    participants_value = facts.get("participants", "")
    participants = (
        parse_participants(participants_value)
        if isinstance(participants_value, str)
        else [normalize_human_text(value, "participant") for value in participants_value]
    )
    if participants:
        event["participants"] = participants
    for source_field, event_field, label in (
        ("organization", "organization", "organization"),
        ("location_name", "location_name", "location"),
        ("locality", "locality", "locality"),
        ("department", "department", "department"),
    ):
        optional_value = _optional_text(facts.get(source_field), label)
        if optional_value is not None:
            event[event_field] = optional_value

    update = {
        "update_key": update_key,
        "event_key": event_key,
        "update_type": "NEW",
        "headline": title,
        "source_url": source_url,
        "source_publisher": source_publisher,
        "source_type": event["source_type"],
        "observed_at": captured,
    }
    proposed_events = copy.deepcopy(events_payload)
    proposed_updates = copy.deepcopy(updates_payload)
    try:
        proposed_events["events"].append(event)
        proposed_updates["updates"].append(update)
    except (KeyError, AttributeError) as error:
        raise CampaignEventCurationError(
            "existing manual source documents do not have the expected arrays"
        ) from error
    normalized_events, normalized_updates = validate_manual_documents(
        proposed_events, proposed_updates
    )
    normalized_event = next(
        value for value in normalized_events if value["event_key"] == event_key
    )
    normalized_update = next(
        value for value in normalized_updates if value["update_key"] == update_key
    )
    return AddProposal(
        events_payload=proposed_events,
        updates_payload=proposed_updates,
        event=event,
        update=update,
        normalized_event=normalized_event,
        normalized_update=normalized_update,
    )


def _participant_identity(event: dict[str, Any]) -> frozenset[str]:
    values = event.get("participants", [])
    if not isinstance(values, list):
        return frozenset()
    return frozenset(
        normalize_human_text(value, "participant").casefold() for value in values
    )


def find_likely_duplicates(
    existing_events: list[dict[str, Any]],
    proposed_event: dict[str, Any],
) -> list[DuplicateMatch]:
    """Return conservative exact-normalized duplicate candidates."""

    proposed_date = proposed_event["date"]
    proposed_title = normalize_human_text(proposed_event["title"], "title").casefold()
    proposed_url = normalize_https_url(proposed_event["source_url"], "source_url")
    proposed_participants = _participant_identity(proposed_event)
    matches = []
    for event in existing_events:
        if event.get("date") != proposed_date:
            continue
        reasons = []
        if normalize_human_text(event.get("title"), "title").casefold() == proposed_title:
            reasons.append("same date and title")
        if normalize_https_url(event.get("source_url"), "source_url") == proposed_url:
            reasons.append("same date and source URL")
        if (
            proposed_participants
            and event.get("event_type") == proposed_event.get("event_type")
            and _participant_identity(event) == proposed_participants
        ):
            reasons.append("same date, type, and participants")
        if reasons:
            matches.append(
                DuplicateMatch(
                    event_key=event["event_key"],
                    title=event["title"],
                    date=event["date"],
                    reasons=tuple(reasons),
                )
            )
    return matches


def _prompt_choice(
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    prompt: str,
    choices: tuple[tuple[str, str], ...],
) -> str:
    for index, (value, label) in enumerate(choices, start=1):
        output_fn(f"{index} {value} — {label}")
    supplied = input_fn(prompt).strip()
    try:
        return choices[int(supplied) - 1][0]
    except (ValueError, IndexError):
        raise CampaignEventCurationError(f"invalid choice: {supplied!r}") from None


def _confirmed(value: str) -> bool:
    return value.strip().casefold() in {"y", "yes"}


def _print_add_preview(proposal: AddProposal, output_fn: Callable[[str], None]) -> None:
    event = proposal.event
    output_fn("-" * 50)
    output_fn("NEW EVENT")
    output_fn("")
    output_fn(event["title"])
    schedule = event["date"] + (f" {event['time']}" if "time" in event else "")
    output_fn(schedule)
    output_fn(event["event_type"].upper())
    location = " · ".join(
        value for value in (event.get("locality"), event.get("location_name")) if value
    )
    if location:
        output_fn(location)
    if event.get("participants"):
        output_fn("Participants:")
        for participant in event["participants"]:
            output_fn(f"  {participant}")
    output_fn("")
    output_fn("Source:")
    output_fn(event["source_publisher"])
    output_fn(event["source_url"])
    output_fn("")
    output_fn(f"Event Watch: NEW · {proposal.update['headline']}")
    output_fn("-" * 50)


def run_add_interactive(
    *,
    events_path: str | Path = DEFAULT_EVENTS_PATH,
    updates_path: str | Path = DEFAULT_UPDATES_PATH,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    uuid_factory: Callable[[], Any] = uuid.uuid4,
    replace_func: Callable[[str | bytes | os.PathLike[str], str | bytes | os.PathLike[str]], None] = os.replace,
) -> int:
    """Run the add flow; dependencies are injectable for deterministic tests."""

    try:
        loaded = load_manual_documents(events_path, updates_path)
        validate_manual_documents(loaded.events_payload, loaded.updates_payload)
        output_fn("=== ADD KEY CAMPAIGN EVENT ===")
        title = input_fn("Title: ")
        date_value = input_fn("Date [YYYY-MM-DD]: ")
        time_value = input_fn("Time [HH:MM, optional]: ")
        event_type = _prompt_choice(input_fn, output_fn, "Type [1-6]: ", EVENT_TYPE_CHOICES)
        participants = input_fn("Participants [comma-separated, optional]: ")
        organization = input_fn("Organization [optional]: ")
        location_name = input_fn("Location [optional]: ")
        locality = input_fn("City/locality [optional]: ")
        department = input_fn("Department code [optional]: ")
        source_url = input_fn("Exact source URL: ")
        source_publisher = input_fn("Publisher: ")
        source_type = _prompt_choice(
            input_fn, output_fn, "Source type [1-6]: ", SOURCE_TYPE_CHOICES
        )
        proposal = build_add_proposal(
            loaded.events_payload,
            loaded.updates_payload,
            {
                "title": title,
                "date": date_value,
                "time": time_value,
                "event_type": event_type,
                "participants": participants,
                "organization": organization,
                "location_name": location_name,
                "locality": locality,
                "department": department,
                "source_url": source_url,
                "source_publisher": source_publisher,
                "source_type": source_type,
            },
            now=now_factory(),
            uuid_factory=uuid_factory,
        )
        duplicates = find_likely_duplicates(
            loaded.events_payload["events"], proposal.event
        )
        if duplicates:
            output_fn("Possible duplicate found.")
            for match in duplicates:
                output_fn(
                    f"{match.date} · {match.title} ({', '.join(match.reasons)})"
                )
            if not _confirmed(input_fn("Add anyway? [y/N]: ")):
                output_fn("No changes made.")
                return 0
        _print_add_preview(proposal, output_fn)
        if not _confirmed(input_fn("Save this event? [y/N]: ")):
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
        output_fn("Event and Event Watch entry saved.")
        return 0
    except (CampaignEventCurationError, ValueError, OSError) as error:
        output_fn(f"Error: {error}")
        return 1


def main() -> int:
    return run_add_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
