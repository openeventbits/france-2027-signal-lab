"""Shared, network-free model and normalization for structured event data."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "StructuredEventParseError",
    "StructuredEventRecord",
]


class StructuredEventParseError(ValueError):
    """Raised when an upstream structured event cannot be parsed safely."""


TARGET_TIMEZONE = "Europe/Paris"
_PARIS = ZoneInfo(TARGET_TIMEZONE)
_UTC = timezone.utc
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_ISO_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?"
    r"(?:Z|[+-]\d{2}:\d{2})?\Z",
    re.ASCII,
)
_PARIS_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\Z",
    re.ASCII,
)


def _normalize_text(
    value: Any,
    *,
    context: str,
    multiline: bool = False,
) -> str:
    if not isinstance(value, str):
        raise StructuredEventParseError(f"{context} must be text")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise StructuredEventParseError(f"{context} contains a null byte")
    if multiline:
        text = "\n".join(line.strip() for line in text.strip().split("\n"))
    else:
        text = " ".join(text.split())
    text = unicodedata.normalize("NFC", text)
    if not text:
        raise StructuredEventParseError(f"{context} must be non-empty text")
    return text


def _optional_text(
    value: Any,
    *,
    context: str,
    multiline: bool = False,
) -> str | None:
    if value is None:
        return None
    return _normalize_text(value, context=context, multiline=multiline)


def _load_timezone(value: Any, *, context: str) -> ZoneInfo:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StructuredEventParseError(
            f"{context} timezone must be non-empty trimmed text"
        )
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise StructuredEventParseError(
            f"{context} timezone is invalid: {value!r}"
        ) from error


def _resolve_wall_time(
    naive: datetime,
    zone: ZoneInfo,
    *,
    context: str,
) -> datetime:
    valid: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(_UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive:
            valid.append(candidate)
    if not valid:
        raise StructuredEventParseError(
            f"{context} is a nonexistent local time in {zone.key}"
        )
    offsets = {candidate.utcoffset() for candidate in valid}
    if len(offsets) > 1:
        raise StructuredEventParseError(
            f"{context} is an ambiguous local time in {zone.key}"
        )
    return valid[0]


def _normalize_iso_temporal(
    value: Any,
    *,
    context: str,
    default_timezone: str | None,
) -> tuple[str, Literal["date", "datetime"]]:
    if not isinstance(value, str) or value != value.strip():
        raise StructuredEventParseError(
            f"{context} must be a trimmed ISO date or datetime"
        )
    if _DATE.fullmatch(value):
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError as error:
            raise StructuredEventParseError(
                f"{context} is not a valid date"
            ) from error
        return parsed_date.isoformat(), "date"
    if not _ISO_DATETIME.fullmatch(value):
        raise StructuredEventParseError(
            f"{context} must be an ISO date or datetime"
        )
    supplied = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(supplied)
    except ValueError as error:
        raise StructuredEventParseError(
            f"{context} is not a valid datetime"
        ) from error
    if parsed.tzinfo is None:
        if default_timezone is None:
            raise StructuredEventParseError(
                f"{context} datetime requires an explicit or default timezone"
            )
        zone = _load_timezone(default_timezone, context=context)
        parsed = _resolve_wall_time(parsed, zone, context=context)
    normalized = parsed.astimezone(_PARIS).isoformat(timespec="seconds")
    return normalized, "datetime"


def _validate_time_range(
    start: str,
    start_precision: str,
    end: str | None,
    end_precision: str | None,
    *,
    context: str,
) -> None:
    if end is None:
        return
    if end_precision != start_precision:
        raise StructuredEventParseError(
            f"{context} start and end must use the same time precision"
        )
    if start_precision == "date":
        start_value: date | datetime = date.fromisoformat(start)
        end_value: date | datetime = date.fromisoformat(end)
    else:
        start_value = datetime.fromisoformat(start)
        end_value = datetime.fromisoformat(end)
    if end_value < start_value:
        raise StructuredEventParseError(
            f"{context} end must not precede start"
        )


def _validate_normalized_temporal(
    value: str,
    precision: str,
    *,
    context: str,
) -> None:
    if not isinstance(value, str):
        raise StructuredEventParseError(f"{context} must be text")
    if precision == "date":
        if not _DATE.fullmatch(value):
            raise StructuredEventParseError(
                f"{context} must be a canonical date"
            )
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError as error:
            raise StructuredEventParseError(
                f"{context} must be a valid canonical date"
            ) from error
        return
    if precision != "datetime" or not _PARIS_DATETIME.fullmatch(value):
        raise StructuredEventParseError(
            f"{context} must be a canonical Europe/Paris datetime"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise StructuredEventParseError(
            f"{context} must be a valid datetime"
        ) from error
    if parsed.astimezone(_PARIS).isoformat(timespec="seconds") != value:
        raise StructuredEventParseError(
            f"{context} must be normalized to Europe/Paris"
        )


@dataclass(frozen=True, slots=True)
class StructuredEventRecord:
    """Immutable pre-attribution facts parsed from one structured event."""

    title: str
    scheduled_start: str
    time_precision: Literal["date", "datetime"]
    timezone: str
    source_format: Literal["json_ld", "ics", "structured_html"]
    scheduled_end: str | None = None
    description: str | None = None
    location_name: str | None = None
    locality: str | None = None
    address: str | None = None
    organization: str | None = None
    event_url: str | None = None
    external_id: str | None = None
    source_status: str | None = None
    participants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_title = _normalize_text(self.title, context="title")
        if normalized_title != self.title:
            raise StructuredEventParseError("title must already be normalized")
        if self.timezone != TARGET_TIMEZONE:
            raise StructuredEventParseError(
                f"timezone must be exactly {TARGET_TIMEZONE}"
            )
        if (
            not isinstance(self.source_format, str)
            or self.source_format
            not in {
                "json_ld",
                "ics",
                "structured_html",
            }
        ):
            raise StructuredEventParseError("source_format is not allowed")
        _validate_normalized_temporal(
            self.scheduled_start,
            self.time_precision,
            context="scheduled_start",
        )
        if self.scheduled_end is not None:
            _validate_normalized_temporal(
                self.scheduled_end,
                self.time_precision,
                context="scheduled_end",
            )
        for field_name in (
            "description",
            "location_name",
            "locality",
            "address",
            "organization",
            "event_url",
            "external_id",
            "source_status",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            normalized = _normalize_text(
                value,
                context=field_name,
                multiline=field_name == "description",
            )
            if normalized != value:
                raise StructuredEventParseError(
                    f"{field_name} must already be normalized"
                )
        if type(self.participants) is not tuple:
            raise StructuredEventParseError("participants must be a tuple")
        for index, participant in enumerate(self.participants):
            normalized = _normalize_text(
                participant,
                context=f"participants[{index}]",
            )
            if normalized != participant:
                raise StructuredEventParseError(
                    f"participants[{index}] must already be normalized"
                )
        if len(set(self.participants)) != len(self.participants):
            raise StructuredEventParseError(
                "participants must not contain duplicates"
            )
        _validate_time_range(
            self.scheduled_start,
            self.time_precision,
            self.scheduled_end,
            self.time_precision if self.scheduled_end is not None else None,
            context="structured event",
        )
