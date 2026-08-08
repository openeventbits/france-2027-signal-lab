"""Network-free Schema.org Event extraction from JSON-LD and HTML."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Iterator

from campaign_event_structured import (
    TARGET_TIMEZONE,
    StructuredEventParseError,
    StructuredEventRecord,
    _load_timezone,
    _normalize_iso_temporal,
    _normalize_text,
    _optional_text,
    _validate_time_range,
)

__all__ = ["parse_json_ld_events"]

_SCHEMA_EVENT_TYPES = frozenset(
    {
        "Event",
        "http://schema.org/Event",
        "https://schema.org/Event",
    }
)



_EVENT_TYPE_MARKER = re.compile(
    r'["\']@type["\']\s*:[^{}]{0,512}?["\']'
    r'(?:https?://schema\.org/)?Event/?["\']',
    re.IGNORECASE,
)


class _JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture = False
        self._chunks: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "script":
            return
        attr_map = {key.casefold(): value for key, value in attrs if key}
        content_type = (attr_map.get("type") or "").split(";", 1)[0]
        if content_type.strip().casefold() == "application/ld+json":
            if self._capture:
                raise StructuredEventParseError(
                    "nested JSON-LD script elements are malformed"
                )
            self._capture = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or not self._capture:
            return
        raw = "".join(self._chunks).strip()
        self._capture = False
        self._chunks = []
        if raw:
            self.blocks.append(raw)

    def close(self) -> None:
        super().close()
        if self._capture:
            raise StructuredEventParseError(
                "JSON-LD script element is not closed"
            )


def _coerce_input(value: str | bytes) -> str:
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise StructuredEventParseError(
                "JSON-LD input must be valid UTF-8"
            ) from error
    elif isinstance(value, str):
        text = value
    else:
        raise StructuredEventParseError(
            "JSON-LD input must be text or bytes"
        )
    if not text or "\x00" in text:
        raise StructuredEventParseError("JSON-LD input is empty or malformed")
    return text


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value}")


def _load_json(raw: str, *, context: str) -> Any:
    try:
        return json.loads(raw, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise StructuredEventParseError(f"{context} is malformed JSON") from error


def _html_payloads(html: str) -> list[Any]:
    parser = _JsonLdScriptParser()
    try:
        parser.feed(html)
        parser.close()
    except StructuredEventParseError:
        raise
    except Exception as error:
        raise StructuredEventParseError(
            f"HTML JSON-LD extraction failed: {error}"
        ) from error

    payloads: list[Any] = []
    for index, raw in enumerate(parser.blocks):
        try:
            payloads.append(_load_json(raw, context=f"JSON-LD block[{index}]"))
        except StructuredEventParseError:
            if _EVENT_TYPE_MARKER.search(raw):
                raise StructuredEventParseError(
                    f"JSON-LD block[{index}] contains a malformed Event object"
                ) from None
            # A clearly unrelated malformed third-party block is not event data.
            continue
    return payloads


def _is_event_type(value: Any) -> bool:
    supplied = value if isinstance(value, list) else [value]
    for item in supplied:
        if not isinstance(item, str):
            continue
        if item.rstrip("/") in _SCHEMA_EVENT_TYPES:
            return True
    return False


def _event_objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if _is_event_type(value.get("@type")):
            yield value
        for child in value.values():
            yield from _event_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _event_objects(child)


def _name_bearing(value: Any, *, context: str) -> str:
    if isinstance(value, str):
        return _normalize_text(value, context=context)
    if isinstance(value, dict):
        if "name" not in value:
            raise StructuredEventParseError(f"{context} is missing name")
        return _normalize_text(value["name"], context=f"{context}.name")
    if isinstance(value, list):
        names = [_name_bearing(item, context=context) for item in value]
        unique = list(dict.fromkeys(names))
        if len(unique) != 1:
            raise StructuredEventParseError(
                f"{context} has multiple values that cannot be represented"
            )
        return unique[0]
    raise StructuredEventParseError(
        f"{context} must be text or a name-bearing object"
    )


def _country_text(value: Any, *, context: str) -> str:
    if isinstance(value, dict):
        return _name_bearing(value, context=context)
    return _normalize_text(value, context=context)


def _address(
    value: Any,
    *,
    context: str,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, str):
        return _normalize_text(value, context=context), None
    if not isinstance(value, dict):
        raise StructuredEventParseError(
            f"{context} must be text or a PostalAddress object"
        )
    locality = _optional_text(
        value.get("addressLocality"),
        context=f"{context}.addressLocality",
    )
    components: list[str] = []
    for key in ("streetAddress", "postalCode", "addressLocality", "addressRegion"):
        if key in value:
            components.append(
                _normalize_text(value[key], context=f"{context}.{key}")
            )
    if "addressCountry" in value:
        components.append(
            _country_text(
                value["addressCountry"],
                context=f"{context}.addressCountry",
            )
        )
    return ", ".join(components) or None, locality


def _location(
    value: Any,
    *,
    context: str,
) -> tuple[str | None, str | None, str | None]:
    if value is None:
        return None, None, None
    if isinstance(value, str):
        return _normalize_text(value, context=context), None, None
    if isinstance(value, list):
        if len(value) != 1:
            raise StructuredEventParseError(
                f"{context} has multiple places that cannot be represented"
            )
        return _location(value[0], context=context)
    if not isinstance(value, dict):
        raise StructuredEventParseError(
            f"{context} must be text or a Place object"
        )
    location_name = _optional_text(
        value.get("name"),
        context=f"{context}.name",
    )
    address, locality = _address(
        value.get("address"),
        context=f"{context}.address",
    )
    return location_name, locality, address


def _event_record(
    event: dict[str, Any],
    *,
    index: int,
    default_timezone: str | None,
) -> StructuredEventRecord:
    context = f"Schema.org Event[{index}]"
    if "name" not in event:
        raise StructuredEventParseError(f"{context} is missing required name")
    if "startDate" not in event:
        raise StructuredEventParseError(
            f"{context} is missing required startDate"
        )
    title = _normalize_text(event["name"], context=f"{context}.name")
    start, precision = _normalize_iso_temporal(
        event["startDate"],
        context=f"{context}.startDate",
        default_timezone=default_timezone,
    )
    end = None
    end_precision = None
    if "endDate" in event:
        end, end_precision = _normalize_iso_temporal(
            event["endDate"],
            context=f"{context}.endDate",
            default_timezone=default_timezone,
        )
    _validate_time_range(
        start,
        precision,
        end,
        end_precision,
        context=context,
    )
    location_name, locality, address = _location(
        event.get("location"),
        context=f"{context}.location",
    )
    organization = None
    if "organizer" in event:
        organization = _name_bearing(
            event["organizer"],
            context=f"{context}.organizer",
        )

    return StructuredEventRecord(
        title=title,
        scheduled_start=start,
        time_precision=precision,
        timezone=TARGET_TIMEZONE,
        source_format="json_ld",
        scheduled_end=end,
        description=_optional_text(
            event.get("description"),
            context=f"{context}.description",
            multiline=True,
        ),
        location_name=location_name,
        locality=locality,
        address=address,
        organization=organization,
        event_url=_optional_text(
            event.get("url"),
            context=f"{context}.url",
        ),
        external_id=_optional_text(
            event.get("@id"),
            context=f"{context}.@id",
        ),
        source_status=_optional_text(
            event.get("eventStatus"),
            context=f"{context}.eventStatus",
        ),
    )


def parse_json_ld_events(
    value: str | bytes,
    *,
    default_timezone: str | None = None,
) -> list[StructuredEventRecord]:
    """Extract Schema.org Event facts without fetching or attribution.

    Raw malformed JSON always fails. In HTML, a malformed block that lexically
    declares an Event fails, while a clearly unrelated malformed block is
    ignored so that it cannot destroy valid Event data from another script.
    """

    if default_timezone is not None:
        _load_timezone(default_timezone, context="JSON-LD default")
    text = _coerce_input(value)
    if text.lstrip().startswith("<"):
        payloads = _html_payloads(text)
    else:
        payload = _load_json(text, context="JSON-LD input")
        if not isinstance(payload, (dict, list)):
            raise StructuredEventParseError(
                "JSON-LD input must contain an object or array"
            )
        payloads = [payload]

    events: list[dict[str, Any]] = []
    for payload in payloads:
        events.extend(_event_objects(payload))
    return [
        _event_record(
            event,
            index=index,
            default_timezone=default_timezone,
        )
        for index, event in enumerate(events)
    ]
