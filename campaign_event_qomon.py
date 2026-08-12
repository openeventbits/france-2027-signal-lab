"""Bounded collection from public Qomon Action Hubs and action calendars."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

from campaign_event_attribution import attribute_structured_events
from campaign_event_ics import parse_ics_events
from campaign_event_observation import build_campaign_event_observations
from campaign_event_structured import StructuredEventParseError, StructuredEventRecord
from http_fetch import HttpFetchResult, fetch_news_route

__all__ = [
    "QomonCollectorConfigurationError",
    "QomonCollectorError",
    "QomonCollectorResult",
    "build_qomon_events",
]


class QomonCollectorError(ValueError):
    """Raised when bounded Qomon collection cannot complete safely."""


class QomonCollectorConfigurationError(QomonCollectorError):
    """Raised when a source is incompatible with the Qomon collector."""


@dataclass(frozen=True, slots=True)
class QomonCollectorResult:
    """Source observations, attribution rejections, and bounded diagnostics."""

    observations: tuple[dict[str, Any], ...]
    attribution_rejected_records: int
    actions_discovered: int = 0
    action_pages_attempted: int = 0
    ics_urls_discovered: int = 0
    ics_records_parsed: int = 0
    merged_records: int = 0

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple or any(
            type(observation) is not dict for observation in self.observations
        ):
            raise QomonCollectorConfigurationError(
                "observations must be a tuple of plain dictionaries"
            )
        for field_name in (
            "attribution_rejected_records",
            "actions_discovered",
            "action_pages_attempted",
            "ics_urls_discovered",
            "ics_records_parsed",
            "merged_records",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise QomonCollectorConfigurationError(
                    f"{field_name} must be a non-negative integer"
                )


@dataclass(frozen=True, slots=True)
class _PageFacts:
    title: str | None
    description: str | None
    location_name: str | None
    organization: str | None
    participants: tuple[str, ...]
    ics_url: str


@dataclass(frozen=True, slots=True)
class _MergedAction:
    record: StructuredEventRecord
    action_url: str
    ics_url: str
    raw_ics_location: str | None
    page_location: str | None
    action_id: str | None


MAX_HUB_LINKS = 1024
MAX_ACTION_PAGES = 64
MAX_ACTION_LINKS = 512
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_ICS_BYTES = 2 * 1024 * 1024

QOMON_CALENDAR_HOSTNAME = "action.qomon.org"
QOMON_CALENDAR_PORT = 443

_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name(
    "campaign_event_sources.json"
)
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype\s+html|html)\b", re.IGNORECASE)
_ACTION_PATH = re.compile(
    r"/action/[a-z0-9]+-[a-z0-9][a-z0-9-]*/\Z",
    re.ASCII | re.IGNORECASE,
)
_VOID_ELEMENTS = frozenset(
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


_LIVE_VENUE_CARD_CLASSES = frozenset(
    {
        "bg-pinkLighted",
        "flex",
        "flex-col",
        "justify-between",
        "p-6",
        "rounded-2xl",
        "w-full",
    }
)


def _is_qomon_map_url(value: str | None) -> bool:
    if value is None:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() == "https"
        and parsed.hostname is not None
        and parsed.hostname.casefold() == "www.google.com"
        and parsed.path == "/maps/search/"
    )


def _normalized_text(parts: list[str]) -> str | None:
    text = unicodedata.normalize("NFC", " ".join("".join(parts).split()))
    if not text or "\x00" in text:
        return None
    return text


class _QomonHtmlParser(HTMLParser):
    def __init__(self, *, maximum_links: int) -> None:
        super().__init__(convert_charrefs=True)
        self.maximum_links = maximum_links
        self.hrefs: list[str] = []
        self.title: str | None = None
        self.description: str | None = None
        self.location_name: str | None = None
        self.organization: str | None = None
        self.participants: list[str] = []
        self._capture_field: str | None = None
        self._capture_depth = 0
        self._capture_parts: list[str] = []
        self._venue_depth = 0
        self._venue_has_map_link = False
        self._venue_lines: list[str] = []
        self._venue_line_depth = 0
        self._venue_line_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag_name = tag.casefold()
        attributes = {
            name.casefold(): value for name, value in attrs if value is not None
        }
        if tag_name == "a" and len(self.hrefs) < self.maximum_links:
            href = attributes.get("href")
            if href is not None:
                self.hrefs.append(href)

        class_tokens = frozenset(attributes.get("class", "").split())
        if self._venue_depth:
            if tag_name == "a" and _is_qomon_map_url(attributes.get("href")):
                self._venue_has_map_link = True
            if self._venue_line_depth:
                if tag_name == "br":
                    self._venue_line_parts.append(" ")
                elif tag_name not in _VOID_ELEMENTS:
                    self._venue_line_depth += 1
            elif tag_name == "p" and "class" not in attributes:
                self._venue_line_depth = 1
                self._venue_line_parts = []
            if tag_name not in _VOID_ELEMENTS:
                self._venue_depth += 1
        elif (
            tag_name == "div"
            and _LIVE_VENUE_CARD_CLASSES.issubset(class_tokens)
        ):
            self._venue_depth = 1
            self._venue_has_map_link = False
            self._venue_lines = []

        if self._capture_field is not None:
            if tag_name == "br":
                self._capture_parts.append(" ")
                return
            if tag_name in _VOID_ELEMENTS:
                return
            self._capture_depth += 1
            return

        itemprop = {
            token.casefold() for token in attributes.get("itemprop", "").split()
        }
        qomon_field = attributes.get("data-qomon-field", "").casefold()
        capture_field: str | None = None
        if tag_name == "h1" or qomon_field == "title":
            capture_field = "title"
        elif (
            "description-container" in class_tokens
            or "description" in itemprop
            or qomon_field == "description"
        ):
            capture_field = "description"
        elif (
            tag_name == "address"
            or "address" in itemprop
            or qomon_field in {"address", "location"}
        ):
            capture_field = "location_name"
        elif "organizer" in itemprop or qomon_field == "organizer":
            capture_field = "organization"
        elif (
            itemprop.intersection({"attendee", "performer"})
            or qomon_field == "participant"
        ):
            capture_field = "participant"
        if capture_field is not None:
            self._capture_field = capture_field
            self._capture_depth = 1
            self._capture_parts = []

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a" or len(self.hrefs) >= self.maximum_links:
            return
        href = dict(attrs).get("href")
        if href is not None:
            self.hrefs.append(href)

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._capture_parts.append(data)
        if self._venue_line_depth:
            self._venue_line_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._venue_line_depth:
            self._venue_line_depth -= 1
            if not self._venue_line_depth:
                value = _normalized_text(self._venue_line_parts)
                self._venue_line_parts = []
                if value is not None:
                    self._venue_lines.append(value)
        if self._venue_depth:
            self._venue_depth -= 1
            if not self._venue_depth:
                if (
                    self.location_name is None
                    and self._venue_has_map_link
                    and self._venue_lines
                ):
                    self.location_name = " ".join(self._venue_lines)
                self._venue_has_map_link = False
                self._venue_lines = []
                self._venue_line_depth = 0
                self._venue_line_parts = []

        if self._capture_field is None:
            return
        self._capture_depth -= 1
        if self._capture_depth:
            return
        field_name = self._capture_field
        value = _normalized_text(self._capture_parts)
        self._capture_field = None
        self._capture_parts = []
        if value is None:
            return
        if field_name == "participant":
            if value not in self.participants:
                self.participants.append(value)
        elif getattr(self, field_name) is None:
            setattr(self, field_name, value)


def _parse_html(
    value: bytes, *, context: str, maximum_links: int
) -> _QomonHtmlParser:
    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise QomonCollectorError(f"{context} is not valid UTF-8") from error
    if not _HTML_DOCUMENT.search(text):
        raise QomonCollectorError(
            f"{context} is not a recognizable HTML document"
        )
    parser = _QomonHtmlParser(maximum_links=maximum_links)
    try:
        parser.feed(text)
        parser.close()
    except (AssertionError, TypeError, ValueError) as error:
        raise QomonCollectorError(f"{context} is malformed HTML") from error
    return parser


def _origin(
    url: Any, *, context: str, configuration: bool = False
) -> tuple[str, str, int]:
    error_type = (
        QomonCollectorConfigurationError if configuration else QomonCollectorError
    )
    if not isinstance(url, str) or not url:
        raise error_type(f"{context} must be absolute HTTPS")
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as error:
        raise error_type(f"{context} must be absolute HTTPS") from error
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise error_type(f"{context} must be absolute HTTPS")
    return url, parsed.hostname.casefold(), port


def _same_origin_url(
    href: Any, *, base_url: str, hostname: str, port: int
) -> str | None:
    if not isinstance(href, str) or not href.strip():
        return None
    try:
        parsed = urlsplit(urljoin(base_url, href.strip()))
        parsed_port = parsed.port or 443
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != hostname
        or parsed_port != port
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    netloc = hostname if port == 443 else f"{hostname}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, hostname: str, port: int) -> None:
        super().__init__()
        self.hostname = hostname
        self.port = port

    def redirect_request(
        self,
        request: Any,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Any:
        if _same_origin_url(
            new_url,
            base_url=request.full_url,
            hostname=self.hostname,
            port=self.port,
        ) is None:
            raise QomonCollectorError(
                "redirect target leaves the approved HTTPS origin"
            )
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


class _OriginLockedOpener:
    def __init__(self, *, hostname: str, port: int) -> None:
        self.hostname = hostname
        self.port = port

    def __call__(
        self, request: Any, *, timeout: int | float, context: Any
    ) -> Any:
        opener = build_opener(
            HTTPSHandler(context=context),
            _SameOriginRedirectHandler(hostname=self.hostname, port=self.port),
        )
        return opener.open(request, timeout=timeout)


def _fetch_body(
    url: str,
    *,
    hostname: str,
    port: int,
    context: str,
    maximum_bytes: int,
    fetch_callable: Callable[..., HttpFetchResult],
) -> tuple[bytes, str]:
    try:
        arguments: dict[str, Any] = {"max_response_bytes": maximum_bytes}
        if fetch_callable is fetch_news_route:
            arguments["opener"] = _OriginLockedOpener(
                hostname=hostname, port=port
            )
        result = fetch_callable(url, **arguments)
    except Exception as error:
        raise QomonCollectorError(f"{context} fetch failed: {error}") from error
    if not isinstance(result, HttpFetchResult):
        raise QomonCollectorError(f"{context} fetch returned an invalid result")
    if not result.success or result.status_code != 200 or result.not_modified:
        detail = result.failure_message or f"HTTP {result.status_code}"
        raise QomonCollectorError(f"{context} fetch failed: {detail}")
    if result.response_body is None:
        raise QomonCollectorError(f"{context} fetch returned no response body")
    final_url = _same_origin_url(
        result.final_url, base_url=url, hostname=hostname, port=port
    )
    if final_url is None:
        raise QomonCollectorError(f"{context} redirected off the approved origin")
    return result.response_body, final_url


def _source_origin(source: dict[str, Any]) -> tuple[str, str, int]:
    if type(source) is not dict:
        raise QomonCollectorConfigurationError(
            "source must be a validated plain dictionary"
        )
    collection = source.get("collection")
    if (
        type(collection) is not dict
        or collection.get("discovery_method") != "custom"
        or collection.get("parser_family") != "custom"
        or collection.get("attribution_policy") != "explicit_participant"
        or collection.get("collector_family") != "qomon"
    ):
        raise QomonCollectorConfigurationError(
            "collector requires custom discovery and parsing, "
            "explicit_participant attribution, and the qomon family"
        )
    return _origin(source.get("url"), context="source URL", configuration=True)


def _action_urls(
    hub_html: bytes, *, hub_url: str, hostname: str, port: int
) -> tuple[str, ...]:
    parser = _parse_html(
        hub_html, context="Qomon hub page", maximum_links=MAX_HUB_LINKS
    )
    actions: set[str] = set()
    for href in parser.hrefs:
        resolved = _same_origin_url(
            href, base_url=hub_url, hostname=hostname, port=port
        )
        if resolved is None:
            continue
        parsed = urlsplit(resolved)
        if _ACTION_PATH.fullmatch(parsed.path):
            netloc = hostname if port == 443 else f"{hostname}:{port}"
            actions.add(urlunsplit(("https", netloc, parsed.path, "", "")))
    return tuple(sorted(actions)[:MAX_ACTION_PAGES])


def _looks_like_ics_href(href: str) -> bool:
    try:
        return urlsplit(href.strip()).path.casefold().endswith(".ics")
    except ValueError:
        return href.strip().casefold().endswith(".ics")


def _trusted_calendar_url(href: str) -> str | None:
    if not _looks_like_ics_href(href):
        return None
    try:
        parsed = urlsplit(href.strip())
        port = parsed.port or 443
    except ValueError as error:
        raise QomonCollectorError("action page contains an invalid ICS URL") from error
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != QOMON_CALENDAR_HOSTNAME
        or port != QOMON_CALENDAR_PORT
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise QomonCollectorError(
            "action page ICS URL is outside the trusted Qomon calendar origin"
        )
    return urlunsplit(
        ("https", QOMON_CALENDAR_HOSTNAME, parsed.path, parsed.query, "")
    )


def _page_facts(value: bytes, *, context: str) -> _PageFacts:
    parser = _parse_html(
        value, context=context, maximum_links=MAX_ACTION_LINKS
    )
    calendar_urls = {
        url
        for href in parser.hrefs
        if (url := _trusted_calendar_url(href)) is not None
    }
    if not calendar_urls:
        raise QomonCollectorError(
            "Qomon action page has no literal trusted public ICS link"
        )
    if len(calendar_urls) != 1:
        raise QomonCollectorError(
            "Qomon action page has multiple trusted public ICS links"
        )
    return _PageFacts(
        title=parser.title,
        description=parser.description,
        location_name=parser.location_name,
        organization=parser.organization,
        participants=tuple(parser.participants),
        ics_url=next(iter(calendar_urls)),
    )


def _qomon_action_id(event_url: str | None) -> str | None:
    if event_url is None:
        return None
    try:
        parsed = urlsplit(event_url)
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != "qomon.app.link"
        or parsed.path != "/action"
    ):
        return None
    identifiers = parse_qs(parsed.query, strict_parsing=False).get("id", [])
    if (
        len(identifiers) != 1
        or not identifiers[0].isascii()
        or not identifiers[0].isdigit()
    ):
        return None
    return identifiers[0]


def _merged_record(
    record: StructuredEventRecord, page: _PageFacts
) -> StructuredEventRecord:
    location_name = page.location_name
    if location_name is None and record.location_name != record.timezone:
        location_name = record.location_name
    try:
        return replace(
            record,
            description=page.description or record.description,
            location_name=location_name,
            address=page.location_name or record.address,
            organization=page.organization or record.organization,
            participants=page.participants or record.participants,
        )
    except StructuredEventParseError as error:
        raise QomonCollectorError(f"merged Qomon event is invalid: {error}") from error


def _deduplicate_merged(events: list[_MergedAction]) -> tuple[_MergedAction, ...]:
    by_uid: dict[str, _MergedAction] = {}
    for event in events:
        uid = event.record.external_id
        if uid is None:
            raise QomonCollectorError("Qomon ICS event is missing a stable UID")
        prior = by_uid.get(uid)
        if prior is not None and prior.record != event.record:
            raise QomonCollectorError(
                f"conflicting duplicate Qomon source identity: {uid}"
            )
        if prior is None:
            by_uid[uid] = event
    return tuple(by_uid[uid] for uid in sorted(by_uid))


def _extract_qomon_events(
    *,
    source: dict[str, Any],
    fetch_callable: Callable[..., HttpFetchResult],
) -> tuple[tuple[_MergedAction, ...], int, int]:
    hub_url, hub_hostname, hub_port = _source_origin(source)
    hub_body, final_hub_url = _fetch_body(
        hub_url,
        hostname=hub_hostname,
        port=hub_port,
        context="Qomon hub page",
        maximum_bytes=MAX_HTML_BYTES,
        fetch_callable=fetch_callable,
    )
    actions = _action_urls(
        hub_body,
        hub_url=final_hub_url,
        hostname=hub_hostname,
        port=hub_port,
    )

    merged: list[_MergedAction] = []
    parsed_records = 0
    for action_url in actions:
        action_body, final_action_url = _fetch_body(
            action_url,
            hostname=hub_hostname,
            port=hub_port,
            context="Qomon action page",
            maximum_bytes=MAX_HTML_BYTES,
            fetch_callable=fetch_callable,
        )
        page = _page_facts(action_body, context="Qomon action page")
        ics_body, final_ics_url = _fetch_body(
            page.ics_url,
            hostname=QOMON_CALENDAR_HOSTNAME,
            port=QOMON_CALENDAR_PORT,
            context="Qomon ICS payload",
            maximum_bytes=MAX_ICS_BYTES,
            fetch_callable=fetch_callable,
        )
        try:
            records = parse_ics_events(ics_body)
        except StructuredEventParseError as error:
            raise QomonCollectorError(
                f"Qomon ICS payload is malformed: {error}"
            ) from error
        if len(records) != 1:
            raise QomonCollectorError(
                "Qomon action ICS must contain exactly one VEVENT"
            )
        parsed_records += 1
        record = records[0]
        merged.append(
            _MergedAction(
                record=_merged_record(record, page),
                action_url=final_action_url,
                ics_url=final_ics_url,
                raw_ics_location=record.location_name,
                page_location=page.location_name,
                action_id=_qomon_action_id(record.event_url),
            )
        )
    return _deduplicate_merged(merged), len(actions), parsed_records


def _deduplicate_observations(
    observations: list[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    by_key: dict[str, dict[str, Any]] = {}
    for observation in observations:
        event_key = observation.get("event_key")
        if not isinstance(event_key, str):
            raise QomonCollectorConfigurationError(
                "observation is missing a string event_key"
            )
        prior = by_key.get(event_key)
        if prior is not None and prior != observation:
            raise QomonCollectorError(
                f"conflicting duplicate source event: {event_key}"
            )
        by_key[event_key] = observation
    return tuple(by_key[key] for key in sorted(by_key))


def build_qomon_events(
    *,
    source: dict[str, Any],
    observed_at: str,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> QomonCollectorResult:
    """Collect one approved public Qomon Action Hub deterministically."""

    merged, actions_discovered, parsed_records = _extract_qomon_events(
        source=source, fetch_callable=fetch_callable
    )
    observations: list[dict[str, Any]] = []
    attribution_rejected_records = 0
    for event in merged:
        attribution = attribute_structured_events(
            (event.record,),
            source=source,
            candidate_registry_path=candidate_registry_path,
        )
        attribution_rejected_records += attribution.rejected_records
        observation_batch = build_campaign_event_observations(
            attribution.accepted,
            source=source,
            observed_at=observed_at,
            evidence_url=event.action_url,
            candidate_registry_path=candidate_registry_path,
            source_registry_path=source_registry_path,
        )
        observations.extend(observation_batch.observations)

    return QomonCollectorResult(
        observations=_deduplicate_observations(observations),
        attribution_rejected_records=attribution_rejected_records,
        actions_discovered=actions_discovered,
        action_pages_attempted=actions_discovered,
        ics_urls_discovered=actions_discovered,
        ics_records_parsed=parsed_records,
        merged_records=len(merged),
    )
