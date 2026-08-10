"""Bounded, network-free iCalendar VEVENT structured-event parser."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from campaign_event_structured import (
    TARGET_TIMEZONE,
    StructuredEventParseError,
    StructuredEventRecord,
    _load_timezone,
    _normalize_text,
    _resolve_wall_time,
    _validate_time_range,
)

__all__ = ["parse_ics_events"]


_UTC = timezone.utc
_ICS_DATE = re.compile(r"\d{8}\Z", re.ASCII)
_ICS_DATETIME = re.compile(r"\d{8}T\d{6}Z?\Z", re.ASCII)
_RECURRENCE_PROPERTIES = frozenset(
    {"RRULE", "RDATE", "EXDATE", "RECURRENCE-ID"}
)
_SUPPORTED_PROPERTIES = frozenset(
    {
        "UID",
        "DTSTART",
        "DTEND",
        "SUMMARY",
        "DESCRIPTION",
        "LOCATION",
        "URL",
        "ORGANIZER",
        "STATUS",
    }
)
_EVENT_STATUSES = frozenset({"TENTATIVE", "CONFIRMED", "CANCELLED"})


@dataclass(frozen=True, slots=True)
class _Property:
    name: str
    params: dict[str, str]
    value: str


def _coerce_ics(value: str | bytes) -> str:
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise StructuredEventParseError(
                "iCalendar input must be valid UTF-8"
            ) from error
    elif isinstance(value, str):
        text = value
    else:
        raise StructuredEventParseError(
            "iCalendar input must be text or bytes"
        )
    if not text or "\x00" in text:
        raise StructuredEventParseError("iCalendar input is empty or malformed")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _unfold_lines(text: str) -> list[str]:
    unfolded: list[str] = []
    for line in text.split("\n"):
        if not line:
            continue
        if line.startswith((" ", "\t")):
            if not unfolded:
                raise StructuredEventParseError(
                    "iCalendar has an orphan folded line"
                )
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _split_unquoted(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quoted = False
    for index, character in enumerate(value):
        if character == '"':
            quoted = not quoted
        elif character == delimiter and not quoted:
            parts.append(value[start:index])
            start = index + 1
    if quoted:
        raise StructuredEventParseError(
            "iCalendar property has an unterminated quoted parameter"
        )
    parts.append(value[start:])
    return parts


def _parse_property(line: str) -> _Property:
    segments = _split_unquoted(line, ":")
    if len(segments) < 2:
        raise StructuredEventParseError(
            "iCalendar content line is missing ':'"
        )
    head = segments[0]
    raw_value = ":".join(segments[1:])
    head_parts = _split_unquoted(head, ";")
    name = head_parts[0].upper()
    if not name:
        raise StructuredEventParseError("iCalendar property name is empty")
    params: dict[str, str] = {}
    for supplied in head_parts[1:]:
        if "=" not in supplied:
            raise StructuredEventParseError(
                f"iCalendar {name} parameter is malformed"
            )
        key, raw_parameter = supplied.split("=", 1)
        key = key.upper()
        if not key or key in params:
            raise StructuredEventParseError(
                f"iCalendar {name} has a duplicate or empty parameter"
            )
        if len(raw_parameter) >= 2 and raw_parameter.startswith('"'):
            if not raw_parameter.endswith('"'):
                raise StructuredEventParseError(
                    f"iCalendar {name} parameter is malformed"
                )
            raw_parameter = raw_parameter[1:-1]
        if not raw_parameter:
            raise StructuredEventParseError(
                f"iCalendar {name} parameter is empty"
            )
        params[key] = raw_parameter
    return _Property(name=name, params=params, value=raw_value)


def _decode_text(value: str, *, context: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(value):
            raise StructuredEventParseError(
                f"{context} has a trailing escape"
            )
        escaped = value[index + 1]
        replacements = {
            "n": "\n",
            "N": "\n",
            ",": ",",
            ";": ";",
            "\\": "\\",
        }
        if escaped not in replacements:
            raise StructuredEventParseError(
                f"{context} has an unsupported escape"
            )
        decoded.append(replacements[escaped])
        index += 2
    return "".join(decoded)


def _single(
    properties: dict[str, _Property],
    name: str,
    *,
    required: bool = False,
) -> _Property | None:
    value = properties.get(name)
    if value is None and required:
        raise StructuredEventParseError(
            f"VEVENT is missing required {name}"
        )
    return value


def _parse_temporal(
    prop: _Property,
    *,
    context: str,
    default_timezone: str | None,
) -> tuple[str, str]:
    unsupported = set(prop.params) - {"VALUE", "TZID"}
    if unsupported:
        raise StructuredEventParseError(
            f"{context} has unsupported parameters: {sorted(unsupported)!r}"
        )
    value_kind = prop.params.get("VALUE", "DATE-TIME").upper()
    timezone_name = prop.params.get("TZID")
    if value_kind == "DATE":
        if timezone_name is not None:
            raise StructuredEventParseError(
                f"{context} date must not include TZID"
            )
        if not _ICS_DATE.fullmatch(prop.value):
            raise StructuredEventParseError(
                f"{context} is not a valid iCalendar date"
            )
        try:
            parsed = datetime.strptime(prop.value, "%Y%m%d").date()
        except ValueError as error:
            raise StructuredEventParseError(
                f"{context} is not a valid iCalendar date"
            ) from error
        return parsed.isoformat(), "date"
    if value_kind != "DATE-TIME" or not _ICS_DATETIME.fullmatch(prop.value):
        raise StructuredEventParseError(
            f"{context} is not a supported iCalendar datetime"
        )
    utc_value = prop.value.endswith("Z")
    if utc_value and timezone_name is not None:
        raise StructuredEventParseError(
            f"{context} UTC datetime must not include TZID"
        )
    raw = prop.value[:-1] if utc_value else prop.value
    try:
        parsed_datetime = datetime.strptime(raw, "%Y%m%dT%H%M%S")
    except ValueError as error:
        raise StructuredEventParseError(
            f"{context} is not a valid iCalendar datetime"
        ) from error
    if utc_value:
        aware = parsed_datetime.replace(tzinfo=_UTC)
    else:
        selected_timezone = timezone_name or default_timezone
        if selected_timezone is None:
            raise StructuredEventParseError(
                f"{context} datetime requires an explicit or default timezone"
            )
        zone = _load_timezone(selected_timezone, context=context)
        aware = _resolve_wall_time(parsed_datetime, zone, context=context)
    paris = _load_timezone(TARGET_TIMEZONE, context=context)
    return aware.astimezone(paris).isoformat(timespec="seconds"), "datetime"


def _event_record(
    supplied: list[_Property],
    *,
    event_index: int,
    default_timezone: str | None,
) -> StructuredEventRecord:
    properties: dict[str, _Property] = {}
    for prop in supplied:
        if prop.name in _RECURRENCE_PROPERTIES:
            raise StructuredEventParseError(
                f"VEVENT[{event_index}] recurrence semantics are unsupported"
            )
        if prop.name not in _SUPPORTED_PROPERTIES:
            continue
        if prop.name in properties:
            raise StructuredEventParseError(
                f"VEVENT[{event_index}] has duplicate {prop.name}"
            )
        properties[prop.name] = prop

    start_prop = _single(properties, "DTSTART", required=True)
    summary_prop = _single(properties, "SUMMARY", required=True)
    assert start_prop is not None and summary_prop is not None
    start, precision = _parse_temporal(
        start_prop,
        context=f"VEVENT[{event_index}].DTSTART",
        default_timezone=default_timezone,
    )
    end_prop = _single(properties, "DTEND")
    end = None
    end_precision = None
    if end_prop is not None:
        end, end_precision = _parse_temporal(
            end_prop,
            context=f"VEVENT[{event_index}].DTEND",
            default_timezone=default_timezone,
        )
    _validate_time_range(
        start,
        precision,
        end,
        end_precision,
        context=f"VEVENT[{event_index}]",
    )

    def decoded(name: str, *, multiline: bool = False) -> str | None:
        prop = _single(properties, name)
        if prop is None:
            return None
        return _normalize_text(
            _decode_text(prop.value, context=f"VEVENT[{event_index}].{name}"),
            context=f"VEVENT[{event_index}].{name}",
            multiline=multiline,
        )

    organizer_prop = _single(properties, "ORGANIZER")
    organization = None
    if organizer_prop is not None:
        raw_organizer = organizer_prop.params.get("CN", organizer_prop.value)
        organization = _normalize_text(
            _decode_text(
                raw_organizer,
                context=f"VEVENT[{event_index}].ORGANIZER",
            ),
            context=f"VEVENT[{event_index}].ORGANIZER",
        )

    status = decoded("STATUS")
    if status is not None:
        status = status.upper()
        if status not in _EVENT_STATUSES:
            raise StructuredEventParseError(
                f"VEVENT[{event_index}].STATUS is unsupported"
            )

    return StructuredEventRecord(
        title=decoded("SUMMARY") or "",
        scheduled_start=start,
        time_precision=precision,
        timezone=TARGET_TIMEZONE,
        source_format="ics",
        scheduled_end=end,
        description=decoded("DESCRIPTION", multiline=True),
        location_name=decoded("LOCATION"),
        organization=organization,
        event_url=decoded("URL"),
        external_id=decoded("UID"),
        source_status=status,
    )


def parse_ics_events(
    value: str | bytes,
    *,
    default_timezone: str | None = None,
) -> list[StructuredEventRecord]:
    """Parse VEVENT records in source order without performing network I/O."""

    if default_timezone is not None:
        _load_timezone(default_timezone, context="iCalendar default")
    stack: list[str] = []
    event_properties: list[_Property] | None = None
    events: list[list[_Property]] = []
    saw_calendar = False

    for line in _unfold_lines(_coerce_ics(value)):
        prop = _parse_property(line)
        if not stack and prop.name != "BEGIN":
            raise StructuredEventParseError(
                "iCalendar content outside VCALENDAR is not allowed"
            )
        if prop.name == "BEGIN":
            component = prop.value.upper()
            if not stack and component != "VCALENDAR":
                raise StructuredEventParseError(
                    "iCalendar content outside VCALENDAR is not allowed"
                )
            if component == "VCALENDAR":
                if stack or saw_calendar:
                    raise StructuredEventParseError(
                        "iCalendar must contain exactly one VCALENDAR"
                    )
                saw_calendar = True
            elif component == "VEVENT":
                if stack != ["VCALENDAR"]:
                    raise StructuredEventParseError(
                        "VEVENT must be a direct VCALENDAR component"
                    )
                event_properties = []
            elif component == "VALARM":
                if (
                    stack != ["VCALENDAR", "VEVENT"]
                    or event_properties is None
                ):
                    raise StructuredEventParseError(
                        "VALARM must be a direct VEVENT component"
                    )
            elif event_properties is not None:
                raise StructuredEventParseError(
                    "nested VEVENT components are unsupported"
                )
            stack.append(component)
            continue
        if prop.name == "END":
            component = prop.value.upper()
            if not stack or stack[-1] != component:
                raise StructuredEventParseError(
                    "iCalendar component boundaries are malformed"
                )
            stack.pop()
            if component == "VEVENT":
                assert event_properties is not None
                events.append(event_properties)
                event_properties = None
            continue
        if (
            event_properties is not None
            and stack == ["VCALENDAR", "VEVENT"]
        ):
            event_properties.append(prop)

    if not saw_calendar or stack:
        raise StructuredEventParseError(
            "iCalendar VCALENDAR boundaries are missing or malformed"
        )
    return [
        _event_record(
            properties,
            event_index=index,
            default_timezone=default_timezone,
        )
        for index, properties in enumerate(events)
    ]
