"""Bounded parser and transport wrapper for the RN agenda listing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from campaign_events_contract import campaign_event_id
from candidate_candidacy_status import load_candidate_candidacy_status
from http_fetch import HttpFetchResult, fetch_news_route

__all__ = [
    "RnAgendaAdapterError",
    "parse_rn_agenda_html",
    "fetch_rn_agenda",
    "build_rn_agenda_events",
]


class RnAgendaAdapterError(ValueError):
    """Raised when the RN agenda cannot be fetched or parsed safely."""


RN_AGENDA_URL = "https://rassemblementnational.fr/agenda"
_PARIS = ZoneInfo("Europe/Paris")
_UTC = timezone.utc
_CANDIDATE_REGISTRY = Path(__file__).with_name("candidate_candidacy_status.json")
_SUPPORTED_CANDIDATES = {"Marine Le Pen": "marine-le-pen"}
_MONTHS = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}
_MONTH_PATTERN = "|".join(re.escape(month) for month in _MONTHS)
_FULL_DATE = re.compile(
    rf"(?<!\d)(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{4}})(?!\d)",
    re.IGNORECASE,
)
_DISPLAY_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])h([0-5]\d)(?!\d)")
_OBSERVED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_CAMPAIGN_CONTEXT = re.compile(r"\bcampagne\s+présidentielle\b", re.IGNORECASE)
_DEBATE_CONTEXT = re.compile(r"\bdébat\w*", re.IGNORECASE)
_NEGATIVE_LIFECYCLE = re.compile(
    r"(?<!\w)(?:annul(?:é|ée|és|ées)|annulation|"
    r"report(?:é|ée|és|ées)|déprogramm(?:é|ée|és|ées))(?!\w)",
    re.IGNORECASE,
)
_ORGANIZER = re.compile(
    r"\borganis(?:é|ée|e)\s+par\s+(?:(?:le|la)\s+|l['’])?([A-Z][A-Z0-9.-]{1,})\b"
)
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype\s+html|html)\b", re.IGNORECASE)
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


def _clean_text(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split()))


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    parent: _Node | None = None
    children: list[_Node | str] = field(default_factory=list)

    def text(self) -> str:
        parts: list[str] = []

        def collect(node: _Node) -> None:
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                else:
                    collect(child)

        collect(self)
        return _clean_text(" ".join(parts))

    def elements(self, *, include_self: bool = False) -> Iterator[_Node]:
        if include_self:
            yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield child
                yield from child.elements()


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = _Node(tag.casefold(), dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        if node.tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = _Node(tag.casefold(), dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.casefold()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)


def _parse_observed_at(value: str) -> str:
    if not isinstance(value, str) or not _OBSERVED_AT.fullmatch(value):
        raise RnAgendaAdapterError(
            "observed_at must be a canonical UTC RFC 3339 timestamp with seconds"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RnAgendaAdapterError("observed_at is not a valid timestamp") from error
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise RnAgendaAdapterError("observed_at must be canonical UTC")
    return value


def _coerce_html(html: str | bytes) -> str:
    if isinstance(html, bytes):
        try:
            text = html.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise RnAgendaAdapterError("RN agenda HTML must be valid UTF-8") from error
    elif isinstance(html, str):
        text = html
    else:
        raise RnAgendaAdapterError("RN agenda HTML must be text or bytes")
    if not text or "\x00" in text or not _HTML_DOCUMENT.search(text):
        raise RnAgendaAdapterError("RN agenda response is malformed or not HTML")
    return text


def _next_element_sibling(node: _Node) -> _Node | None:
    if node.parent is None:
        return None
    found = False
    for child in node.parent.children:
        if child is node:
            found = True
        elif found and isinstance(child, _Node):
            return child
    return None


def _is_agenda_region(node: _Node) -> bool:
    markers = " ".join(
        value or "" for key, value in node.attrs.items() if key in {"class", "id"}
    ).casefold()
    return "agenda" in markers or "divide-y" in markers


def _agenda_cards(root: _Node) -> list[_Node]:
    headings = [
        node
        for node in root.elements()
        if node.tag == "h1" and node.text().casefold() == "agenda"
    ]
    if len(headings) != 1:
        raise RnAgendaAdapterError("exactly one H1 Agenda is required")
    region = _next_element_sibling(headings[0])
    if region is None or not _is_agenda_region(region):
        raise RnAgendaAdapterError("Agenda content region cannot be identified")

    children = [child for child in region.children if isinstance(child, _Node)]
    if not children:
        return []
    if all(_node_looks_like_event(child) for child in children):
        return children
    if _node_looks_like_event(region):
        raise RnAgendaAdapterError("Agenda event boundaries are ambiguous")
    raise RnAgendaAdapterError("Agenda content region has unrecognized structure")


def _node_looks_like_event(node: _Node) -> bool:
    elements = list(node.elements(include_self=True))
    has_day = any(item.tag == "h2" and item.text().isdigit() for item in elements)
    has_time = any(
        item.tag == "h3" and _DISPLAY_TIME.fullmatch(item.text())
        for item in elements
    )
    return has_day or has_time


def _single_match(values: list[Any], context: str) -> Any:
    if len(values) != 1:
        raise RnAgendaAdapterError(f"event block requires exactly one {context}")
    return values[0]


def _resolve_paris_wall_time(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    """Resolve one ordinary Paris wall time and reject DST gaps or overlaps."""

    try:
        naive = datetime(year, month, day, hour, minute)
    except ValueError as error:
        raise RnAgendaAdapterError("event has an invalid local date or time") from error

    valid_candidates: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=_PARIS, fold=fold)
        round_trip = candidate.astimezone(_UTC).astimezone(_PARIS)
        if round_trip.replace(tzinfo=None) == naive:
            valid_candidates.append(candidate)

    if not valid_candidates:
        raise RnAgendaAdapterError("event has a nonexistent Europe/Paris local time")
    offsets = {candidate.utcoffset() for candidate in valid_candidates}
    if len(offsets) > 1:
        raise RnAgendaAdapterError("event has an ambiguous Europe/Paris local time")
    return valid_candidates[0]


def _extract_card(card: _Node, index: int) -> dict[str, Any]:
    elements = list(card.elements(include_self=True))
    positions = {id(node): position for position, node in enumerate(elements)}

    days = [
        node
        for node in elements
        if node.tag == "h2"
        and node.text().isdigit()
        and 1 <= int(node.text()) <= 31
    ]
    day_node = _single_match(days, f"day in event block {index}")
    day = int(day_node.text())

    months = [
        node
        for node in elements
        if node.tag == "p" and node.text().casefold() in _MONTHS
    ]
    month_node = _single_match(months, f"French month in event block {index}")
    month_text = month_node.text().casefold()

    times = [
        (node, _DISPLAY_TIME.fullmatch(node.text()))
        for node in elements
        if node.tag == "h3" and _DISPLAY_TIME.fullmatch(node.text())
    ]
    time_node, time_match = _single_match(
        times, f"displayed time in event block {index}"
    )
    assert time_match is not None
    hour, minute = int(time_match.group(1)), int(time_match.group(2))

    titles = [
        node
        for node in elements
        if node.tag == "h3"
        and positions[id(node)] > positions[id(time_node)]
        and not _DISPLAY_TIME.fullmatch(node.text())
        and node.text()
    ]
    title_node = _single_match(titles, f"title in event block {index}")
    title = title_node.text()

    paragraphs = [
        node
        for node in elements
        if node.tag == "p"
        and positions[id(node)] > positions[id(title_node)]
        and node.text()
    ]
    marked_descriptions = [
        node
        for node in paragraphs
        if {"description", "text-gray-800"}
        & set((node.attrs.get("class") or "").split())
    ]
    if len(marked_descriptions) > 1:
        raise RnAgendaAdapterError(f"event block {index} has ambiguous descriptions")
    if marked_descriptions:
        description_node = marked_descriptions[0]
    elif paragraphs:
        description_node = paragraphs[-1]
    else:
        raise RnAgendaAdapterError(f"event block {index} is missing description")
    description = description_node.text()

    if not (
        positions[id(day_node)]
        < positions[id(month_node)]
        < positions[id(time_node)]
        < positions[id(title_node)]
        < positions[id(description_node)]
    ):
        raise RnAgendaAdapterError(f"event block {index} fields are not coherent")

    date_matches = {
        (int(match.group(1)), match.group(2).casefold(), int(match.group(3)))
        for match in _FULL_DATE.finditer(description)
    }
    if not date_matches:
        raise RnAgendaAdapterError(
            f"event block {index} description lacks an explicit full date with year"
        )
    if len(date_matches) != 1:
        raise RnAgendaAdapterError(f"event block {index} has conflicting full dates")
    description_day, description_month, year = next(iter(date_matches))
    if description_day != day or description_month != month_text:
        raise RnAgendaAdapterError(f"event block {index} header/description date mismatch")

    description_times = {
        (int(match.group(1)), int(match.group(2)))
        for match in _DISPLAY_TIME.finditer(description)
    }
    if not description_times:
        raise RnAgendaAdapterError(
            f"event block {index} description lacks an explicit time"
        )
    if description_times != {(hour, minute)}:
        raise RnAgendaAdapterError(
            f"event block {index} displayed/description time mismatch"
        )

    local_start = _resolve_paris_wall_time(
        year,
        _MONTHS[month_text],
        day,
        hour,
        minute,
    )

    return {
        "title": title,
        "description": description,
        "local_text": _clean_text(card.text()),
        "scheduled_start": local_start.isoformat(timespec="seconds"),
        "date_key": local_start.strftime("%Y-%m-%d"),
        "time_key": local_start.strftime("%H%M"),
    }


def _canonical_candidate_mapping() -> dict[str, str]:
    try:
        registry = load_candidate_candidacy_status(_CANDIDATE_REGISTRY)
    except (OSError, ValueError) as error:
        raise RnAgendaAdapterError(
            f"canonical candidate registry is unavailable or invalid: {error}"
        ) from error
    return {
        candidate["candidate_name"]: candidate["candidate_id"]
        for candidate in registry["candidates"]
    }


def _contains_full_name(text: str, name: str) -> bool:
    return re.search(
        rf"(?<!\w){re.escape(name)}(?!\w)",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _build_event(
    card: dict[str, Any],
    observed_at: str,
    canonical_candidates: dict[str, str],
) -> dict[str, Any] | None:
    local_text = card["local_text"]
    has_campaign_context = _CAMPAIGN_CONTEXT.search(local_text) is not None
    supported = [
        (name, identifier)
        for name, identifier in _SUPPORTED_CANDIDATES.items()
        if _contains_full_name(local_text, name)
    ]
    if not has_campaign_context:
        return None

    unsupported = sorted(
        name
        for name in canonical_candidates.keys() - _SUPPORTED_CANDIDATES.keys()
        if _contains_full_name(local_text, name)
    )
    if unsupported:
        raise RnAgendaAdapterError(
            "presidential event contains unsupported canonical candidate name: "
            + ", ".join(unsupported)
        )
    if not supported:
        return None
    if len(supported) != 1:
        raise RnAgendaAdapterError("presidential event candidate mapping is ambiguous")
    candidate_name, candidate_id = supported[0]
    if canonical_candidates.get(candidate_name) != candidate_id:
        raise RnAgendaAdapterError(
            "canonical candidate registry must contain exactly "
            "Marine Le Pen -> marine-le-pen"
        )
    if _DEBATE_CONTEXT.search(local_text) is None:
        raise RnAgendaAdapterError("presidential event cannot be classified as debate")
    if _NEGATIVE_LIFECYCLE.search(local_text) is not None:
        raise RnAgendaAdapterError(
            "presidential debate has explicit negative lifecycle wording"
        )

    event_key = (
        f"rn-agenda-{candidate_id}-{card['date_key']}-{card['time_key']}-debate"
    )
    event: dict[str, Any] = {
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "event_type": "debate",
        "title": card["title"],
        "candidate_ids": [candidate_id],
        "candidate_names": [candidate_name],
        "scheduled_start": card["scheduled_start"],
        "time_precision": "datetime",
        "timezone": "Europe/Paris",
        "status": "scheduled",
        "status_as_of": observed_at[:10],
        "evidence_status": "verified",
        "last_verified_at": observed_at,
        "evidence": [
            {
                "source_id": "rn-agenda",
                "source_url": RN_AGENDA_URL,
                "source_publisher": "Rassemblement National",
                "source_type": "party_first_party",
                "evidence_type": "explicit_schedule",
            }
        ],
    }
    organizer_match = _ORGANIZER.search(card["description"])
    if organizer_match is not None and organizer_match.group(1) == "MEDEF":
        event["organization"] = "MEDEF"
    return event


def _event_sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
    scheduled = event["scheduled_start"]
    return (
        scheduled[:10],
        0,
        scheduled[11:19],
        2,
        tuple(event["candidate_ids"]),
        event["event_key"],
        event["event_id"],
    )


def parse_rn_agenda_html(
    html: str | bytes,
    *,
    observed_at: str,
) -> list[dict[str, Any]]:
    """Parse supplied RN agenda HTML without performing network access."""

    canonical_observed_at = _parse_observed_at(observed_at)
    parser = _TreeParser()
    try:
        parser.feed(_coerce_html(html))
        parser.close()
    except (ValueError, AssertionError) as error:
        raise RnAgendaAdapterError(f"RN agenda HTML is malformed: {error}") from error

    canonical_candidates = _canonical_candidate_mapping()

    events_by_key: dict[str, tuple[dict[str, Any], tuple[str, str]]] = {}
    for index, node in enumerate(_agenda_cards(parser.root)):
        card = _extract_card(node, index)
        event = _build_event(card, canonical_observed_at, canonical_candidates)
        if event is None:
            continue
        identity = event["event_key"]
        semantics = (repr(event), card["description"])
        prior = events_by_key.get(identity)
        if prior is None:
            events_by_key[identity] = (event, semantics)
        elif prior[1] != semantics:
            raise RnAgendaAdapterError(f"conflicting duplicate event identity: {identity}")

    return sorted(
        (record[0] for record in events_by_key.values()),
        key=_event_sort_key,
    )


def fetch_rn_agenda(
    *,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
) -> str:
    """Fetch only the registered RN agenda URL through the bounded HTTP utility."""

    try:
        result = fetch_callable(RN_AGENDA_URL)
    except Exception as error:
        raise RnAgendaAdapterError(f"RN agenda fetch failed: {error}") from error
    if not isinstance(result, HttpFetchResult):
        raise RnAgendaAdapterError("RN agenda fetch returned an invalid result")
    if not result.success or result.status_code != 200 or result.not_modified:
        detail = result.failure_message or f"HTTP {result.status_code}"
        raise RnAgendaAdapterError(f"RN agenda fetch failed: {detail}")
    if result.response_body is None:
        raise RnAgendaAdapterError("RN agenda fetch returned no response body")
    return _coerce_html(result.response_body)


def build_rn_agenda_events(
    *,
    observed_at: str,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
) -> list[dict[str, Any]]:
    """Fetch and parse the registered RN listing using an explicit observation time."""

    html = fetch_rn_agenda(fetch_callable=fetch_callable)
    return parse_rn_agenda_html(html, observed_at=observed_at)
