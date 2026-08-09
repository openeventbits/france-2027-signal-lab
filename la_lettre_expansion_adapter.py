"""Bounded structured-HTML production adapter for La Lettre de l'Expansion."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from campaign_event_attribution import attribute_structured_events
from campaign_event_observation import build_campaign_event_observations
from campaign_event_structured import StructuredEventRecord
from http_fetch import HttpFetchResult, fetch_news_route

__all__ = [
    "LA_LETTRE_EXPANSION_URL",
    "LaLettreExpansionAdapterError",
    "LaLettreExpansionAdapterResult",
    "parse_la_lettre_expansion_html",
    "fetch_la_lettre_expansion",
    "build_la_lettre_expansion_events",
]


class LaLettreExpansionAdapterError(ValueError):
    """Raised when the audited agenda cannot be fetched or parsed safely."""


@dataclass(frozen=True, slots=True)
class LaLettreExpansionAdapterResult:
    """Source-owned observations plus generic attribution rejections."""

    observations: tuple[dict[str, Any], ...]
    attribution_rejected_records: int

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple or any(
            type(observation) is not dict for observation in self.observations
        ):
            raise LaLettreExpansionAdapterError(
                "observations must be a tuple of plain dictionaries"
            )
        if (
            type(self.attribution_rejected_records) is not int
            or self.attribution_rejected_records < 0
        ):
            raise LaLettreExpansionAdapterError(
                "attribution_rejected_records must be a non-negative integer"
            )


LA_LETTRE_EXPANSION_URL = "https://www.lalettredelexpansion.com/article/71583/agenda"
_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name("candidate_candidacy_status.json")
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name("campaign_event_sources.json")
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype\s+html|html)\b", re.IGNORECASE)


def _clean_text(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split()))


class _ListItemParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._parts: list[str] = []
        self.items: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "li":
            if self._depth == 0:
                self._parts = []
            self._depth += 1

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "li" or self._depth == 0:
            return
        self._depth -= 1
        if self._depth == 0:
            text = _clean_text(" ".join(self._parts))
            if text:
                self.items.append(text)
            self._parts = []


def _coerce_html(value: bytes | str) -> str:
    if isinstance(value, bytes):
        try:
            html = value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise LaLettreExpansionAdapterError(
                "La Lettre response is not valid UTF-8"
            ) from error
    elif isinstance(value, str):
        html = value
    else:
        raise LaLettreExpansionAdapterError(
            "La Lettre response body must be bytes or text"
        )
    if not _HTML_DOCUMENT.search(html):
        raise LaLettreExpansionAdapterError("La Lettre response is not an HTML document")
    return html


def _audited_item(html: str) -> str:
    parser = _ListItemParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:
        raise LaLettreExpansionAdapterError(
            f"La Lettre HTML parsing failed: {error}"
        ) from error

    matches: list[str] = []
    for item in parser.items:
        folded = item.casefold()
        requirements = (
            "édouard philippe" in folded and "françois hollande" in folded,
            re.search(r"\bsamedi\s+29\s+août\b", item, re.IGNORECASE) is not None,
            re.search(
                r"\bdébat\s+entre\s+Édouard\s+Philippe\s+et\s+François\s+Hollande\b",
                item,
                re.IGNORECASE,
            )
            is not None,
            re.search(r"\bLCI\b", item, re.IGNORECASE) is not None,
            re.search(r"\bà\s+Sens\b", item, re.IGNORECASE) is not None,
            "laboratoire de la république" in folded,
        )
        if all(requirements):
            matches.append(item)
    if len(matches) != 1:
        raise LaLettreExpansionAdapterError(
            "La Lettre Hollande-Philippe debate is missing required audited facts or is ambiguous"
        )
    return matches[0]


def parse_la_lettre_expansion_html(
    html: bytes | str,
) -> tuple[StructuredEventRecord, ...]:
    """Parse the one bounded qualifying agenda item as structured source facts."""

    item = _audited_item(_coerce_html(html))
    return (
        StructuredEventRecord(
            title="Débat entre Édouard Philippe et François Hollande",
            scheduled_start="2026-08-29",
            time_precision="date",
            timezone="Europe/Paris",
            source_format="structured_html",
            description=item,
            locality="Sens",
            organization="Laboratoire de la République",
        ),
    )


def fetch_la_lettre_expansion(
    *,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
) -> str:
    """Fetch only the registered La Lettre agenda URL."""

    try:
        result = fetch_callable(LA_LETTRE_EXPANSION_URL)
    except Exception as error:
        raise LaLettreExpansionAdapterError(
            f"La Lettre agenda fetch failed: {error}"
        ) from error
    if not isinstance(result, HttpFetchResult):
        raise LaLettreExpansionAdapterError(
            "La Lettre agenda fetch returned an invalid result"
        )
    if not result.success or result.status_code != 200 or result.not_modified:
        detail = result.failure_message or f"HTTP {result.status_code}"
        raise LaLettreExpansionAdapterError(
            f"La Lettre agenda fetch failed: {detail}"
        )
    if result.response_body is None:
        raise LaLettreExpansionAdapterError(
            "La Lettre agenda fetch returned no response body"
        )
    return _coerce_html(result.response_body)


def build_la_lettre_expansion_events(
    *,
    source: dict[str, Any],
    observed_at: str,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> LaLettreExpansionAdapterResult:
    """Fetch, generically attribute, and build observations via Stage 2C."""

    structured = parse_la_lettre_expansion_html(
        fetch_la_lettre_expansion(fetch_callable=fetch_callable)
    )
    attribution = attribute_structured_events(
        structured,
        source=source,
        candidate_registry_path=candidate_registry_path,
    )
    observation_batch = build_campaign_event_observations(
        attribution.accepted,
        source=source,
        observed_at=observed_at,
        evidence_url=LA_LETTRE_EXPANSION_URL,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    return LaLettreExpansionAdapterResult(
        observations=observation_batch.observations,
        attribution_rejected_records=attribution.rejected_records,
    )
