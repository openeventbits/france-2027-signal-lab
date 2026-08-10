"""Bounded generic collection from approved HTML agenda pages to linked iCalendar data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

from campaign_event_attribution import attribute_structured_events
from campaign_event_ics import parse_ics_events
from campaign_event_observation import build_campaign_event_observations
from campaign_event_structured import StructuredEventParseError
from http_fetch import HttpFetchResult, fetch_news_route

__all__ = [
    "LinkedIcsCollectorConfigurationError",
    "LinkedIcsCollectorError",
    "LinkedIcsCollectorResult",
    "build_linked_ics_events",
]


class LinkedIcsCollectorError(ValueError):
    """Raised when linked-event ICS collection cannot complete safely."""


class LinkedIcsCollectorConfigurationError(LinkedIcsCollectorError):
    """Raised when a source is incompatible with this collector."""


@dataclass(frozen=True, slots=True)
class LinkedIcsCollectorResult:
    """Source-owned observations plus ordinary attribution rejections."""

    observations: tuple[dict[str, Any], ...]
    attribution_rejected_records: int

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple or any(
            type(observation) is not dict for observation in self.observations
        ):
            raise LinkedIcsCollectorConfigurationError(
                "observations must be a tuple of plain dictionaries"
            )
        if (
            type(self.attribution_rejected_records) is not int
            or self.attribution_rejected_records < 0
        ):
            raise LinkedIcsCollectorConfigurationError(
                "attribution_rejected_records must be a non-negative integer"
            )


MAX_DIRECT_ICS_LINKS = 16
MAX_LINKS_PER_PAGE = 512
MAX_HTML_BYTES = 1024 * 1024
MAX_ICS_BYTES = 2 * 1024 * 1024

_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name(
    "campaign_event_sources.json"
)
_HTML_DOCUMENT = re.compile(
    r"<\s*(?:!doctype\s+html|html)\b",
    re.IGNORECASE,
)
class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a" or len(self.hrefs) >= MAX_LINKS_PER_PAGE:
            return
        for name, value in attrs:
            if name.casefold() == "href" and value is not None:
                self.hrefs.append(value)
                return


def _coerce_html(value: bytes, *, context: str) -> str:
    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise LinkedIcsCollectorError(f"{context} is not valid UTF-8") from error
    if not _HTML_DOCUMENT.search(text):
        raise LinkedIcsCollectorError(
            f"{context} is not a recognizable HTML document"
        )
    return text


def _extract_hrefs(value: bytes, *, context: str) -> tuple[str, ...]:
    parser = _HrefParser()
    try:
        parser.feed(_coerce_html(value, context=context))
        parser.close()
    except (AssertionError, TypeError, ValueError) as error:
        raise LinkedIcsCollectorError(f"{context} is malformed HTML") from error
    return tuple(parser.hrefs)


def _source_origin(source: dict[str, Any]) -> tuple[str, str, int]:
    if type(source) is not dict:
        raise LinkedIcsCollectorConfigurationError(
            "source must be a validated plain dictionary"
        )
    collection = source.get("collection")
    if (
        type(collection) is not dict
        or collection.get("collector_family") != "linked-ics"
        or collection.get("discovery_method") != "linked_event_pages"
        or collection.get("parser_family") != "ics"
    ):
        raise LinkedIcsCollectorConfigurationError(
            "collector requires the linked-ics family with linked_event_pages "
            "discovery and ics parsing"
        )
    source_url = source.get("url")
    if not isinstance(source_url, str):
        raise LinkedIcsCollectorConfigurationError(
            "source URL must be absolute HTTPS"
        )
    try:
        parsed = urlsplit(source_url)
        port = parsed.port or 443
    except ValueError as error:
        raise LinkedIcsCollectorConfigurationError(
            "source URL must be absolute HTTPS"
        ) from error
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise LinkedIcsCollectorConfigurationError(
            "source URL must be absolute HTTPS"
        )
    return source_url, parsed.hostname.casefold(), port


def _same_origin_url(
    href: Any,
    *,
    base_url: str,
    hostname: str,
    port: int,
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
    return urlunsplit(
        ("https", netloc, parsed.path or "/", parsed.query, "")
    )


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
            raise LinkedIcsCollectorError(
                "redirect target leaves the approved HTTPS origin"
            )
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


class _OriginLockedOpener:
    def __init__(self, *, hostname: str, port: int) -> None:
        self.hostname = hostname
        self.port = port

    def __call__(
        self,
        request: Any,
        *,
        timeout: int | float,
        context: Any,
    ) -> Any:
        opener = build_opener(
            HTTPSHandler(context=context),
            _SameOriginRedirectHandler(
                hostname=self.hostname,
                port=self.port,
            ),
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
        fetch_arguments: dict[str, Any] = {
            "max_response_bytes": maximum_bytes,
        }
        if fetch_callable is fetch_news_route:
            fetch_arguments["opener"] = _OriginLockedOpener(
                hostname=hostname,
                port=port,
            )
        result = fetch_callable(url, **fetch_arguments)
    except Exception as error:
        raise LinkedIcsCollectorError(f"{context} fetch failed: {error}") from error
    if not isinstance(result, HttpFetchResult):
        raise LinkedIcsCollectorError(f"{context} fetch returned an invalid result")
    if not result.success or result.status_code != 200 or result.not_modified:
        detail = result.failure_message or f"HTTP {result.status_code}"
        raise LinkedIcsCollectorError(f"{context} fetch failed: {detail}")
    if result.response_body is None:
        raise LinkedIcsCollectorError(f"{context} fetch returned no response body")
    final_url = _same_origin_url(
        result.final_url,
        base_url=url,
        hostname=hostname,
        port=port,
    )
    if final_url is None:
        raise LinkedIcsCollectorError(f"{context} redirected off the approved origin")
    return result.response_body, final_url


def _ics_urls(
    html: bytes,
    *,
    page_url: str,
    hostname: str,
    port: int,
    maximum_urls: int,
    context: str,
) -> tuple[str, ...]:
    urls: set[str] = set()
    for href in _extract_hrefs(html, context=context):
        resolved = _same_origin_url(
            href,
            base_url=page_url,
            hostname=hostname,
            port=port,
        )
        if resolved is not None and urlsplit(resolved).path.casefold().endswith(
            ".ics"
        ):
            urls.add(resolved)
    return tuple(sorted(urls)[:maximum_urls])


def _deduplicate_observations(
    observations: list[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    by_key: dict[str, dict[str, Any]] = {}
    for observation in observations:
        event_key = observation.get("event_key")
        if not isinstance(event_key, str):
            raise LinkedIcsCollectorConfigurationError(
                "observation is missing a string event_key"
            )
        prior = by_key.get(event_key)
        if prior is not None and prior != observation:
            raise LinkedIcsCollectorError(
                f"conflicting duplicate source event: {event_key}"
            )
        by_key[event_key] = observation
    return tuple(by_key[key] for key in sorted(by_key))


def build_linked_ics_events(
    *,
    source: dict[str, Any],
    observed_at: str,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> LinkedIcsCollectorResult:
    """Collect direct same-origin iCalendar links from one approved agenda."""

    source_url, hostname, port = _source_origin(source)
    agenda_body, agenda_url = _fetch_body(
        source_url,
        hostname=hostname,
        port=port,
        context="agenda page",
        maximum_bytes=MAX_HTML_BYTES,
        fetch_callable=fetch_callable,
    )
    discovered_ics_urls = _ics_urls(
        agenda_body,
        page_url=agenda_url,
        hostname=hostname,
        port=port,
        maximum_urls=MAX_DIRECT_ICS_LINKS,
        context="agenda page",
    )

    observations: list[dict[str, Any]] = []
    attribution_rejected_records = 0
    for ics_url in discovered_ics_urls:
        ics_body, final_ics_url = _fetch_body(
            ics_url,
            hostname=hostname,
            port=port,
            context="ICS payload",
            maximum_bytes=MAX_ICS_BYTES,
            fetch_callable=fetch_callable,
        )
        try:
            structured = parse_ics_events(ics_body)
        except StructuredEventParseError as error:
            raise LinkedIcsCollectorError(
                f"ICS payload is malformed: {error}"
            ) from error
        attribution = attribute_structured_events(
            structured,
            source=source,
            candidate_registry_path=candidate_registry_path,
        )
        attribution_rejected_records += attribution.rejected_records
        observation_batch = build_campaign_event_observations(
            attribution.accepted,
            source=source,
            observed_at=observed_at,
            evidence_url=final_ics_url,
            candidate_registry_path=candidate_registry_path,
            source_registry_path=source_registry_path,
        )
        observations.extend(observation_batch.observations)

    return LinkedIcsCollectorResult(
        observations=_deduplicate_observations(observations),
        attribution_rejected_records=attribution_rejected_records,
    )
