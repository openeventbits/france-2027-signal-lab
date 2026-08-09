"""Bounded JSON-LD parser and production adapter for the audited TF1/LCI article."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from campaign_event_attribution import (
    AttributedStructuredEvent,
    CandidateAttributionBatch,
    CandidateAttributionConfigurationError,
)
from campaign_event_observation import build_campaign_event_observations
from campaign_event_structured import StructuredEventRecord
from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    candidacy_status_by_id,
    load_candidate_candidacy_status,
    project_display_tiers,
)
from http_fetch import HttpFetchResult, fetch_news_route

__all__ = [
    "TF1_LCI_URL",
    "Tf1LciAdapterError",
    "Tf1LciAdapterResult",
    "attribute_tf1_lci_events",
    "parse_tf1_lci_html",
    "fetch_tf1_lci",
    "build_tf1_lci_events",
]


class Tf1LciAdapterError(ValueError):
    """Raised when the audited TF1/LCI article cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class Tf1LciAdapterResult:
    """Source-owned observations plus bounded attribution rejections."""

    observations: tuple[dict[str, Any], ...]
    attribution_rejected_records: int

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple or any(
            type(observation) is not dict for observation in self.observations
        ):
            raise Tf1LciAdapterError(
                "observations must be a tuple of plain dictionaries"
            )
        if (
            type(self.attribution_rejected_records) is not int
            or self.attribution_rejected_records < 0
        ):
            raise Tf1LciAdapterError(
                "attribution_rejected_records must be a non-negative integer"
            )


TF1_LCI_URL = (
    "https://www.tf1info.fr/politique/"
    "election-presidentielle-2027-lci-organisera-le-27-aout-un-grand-debat-"
    "avec-sept-candidats-declares-ou-pressentis-2455591.html"
)
_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name("candidate_candidacy_status.json")
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name("campaign_event_sources.json")
_SUPPORTED_CANDIDATES = {
    "jean-luc-melenchon": "Jean-Luc Mélenchon",
    "bruno-retailleau": "Bruno Retailleau",
    "gabriel-attal": "Gabriel Attal",
    "marine-le-pen": "Marine Le Pen",
    "raphael-glucksmann": "Raphaël Glucksmann",
    "marine-tondelier": "Marine Tondelier",
    "edouard-philippe": "Édouard Philippe",
    "francois-hollande": "François Hollande",
}
_FIRST_DEBATE_CANDIDATE_IDS = (
    "jean-luc-melenchon",
    "bruno-retailleau",
    "gabriel-attal",
    "marine-le-pen",
    "raphael-glucksmann",
    "marine-tondelier",
    "edouard-philippe",
)
_SECOND_DEBATE_CANDIDATE_IDS = ("francois-hollande", "edouard-philippe")
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype\s+html|html)\b", re.IGNORECASE)


def _clean_text(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split()))


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture = False
        self._chunks: list[str] = []
        self.payloads: list[Any] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "script":
            return
        attr_map = {key.casefold(): value for key, value in attrs if key}
        if (attr_map.get("type") or "").casefold() == "application/ld+json":
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
        if not raw:
            return
        try:
            self.payloads.append(json.loads(raw))
        except json.JSONDecodeError:
            return


def _iter_json_objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_objects(child)


def _coerce_html(value: bytes | str) -> str:
    if isinstance(value, bytes):
        try:
            html = value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise Tf1LciAdapterError("TF1/LCI response is not valid UTF-8") from error
    elif isinstance(value, str):
        html = value
    else:
        raise Tf1LciAdapterError("TF1/LCI response body must be bytes or text")
    if not _HTML_DOCUMENT.search(html):
        raise Tf1LciAdapterError("TF1/LCI response is not an HTML document")
    return html


def _article_payload(html: str) -> dict[str, Any]:
    parser = _JsonLdParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:
        raise Tf1LciAdapterError(f"TF1/LCI HTML parsing failed: {error}") from error

    article_candidates: list[dict[str, Any]] = []
    for payload in parser.payloads:
        for obj in _iter_json_objects(payload):
            article_type = obj.get("@type")
            is_article = (
                "NewsArticle" in article_type
                if isinstance(article_type, list)
                else article_type == "NewsArticle"
            )
            body = obj.get("articleBody")
            if is_article and isinstance(body, str) and body.strip():
                article_candidates.append(obj)
    if not article_candidates:
        raise Tf1LciAdapterError("TF1/LCI NewsArticle JSON-LD is missing articleBody")
    audited = [
        item
        for item in article_candidates
        if all(
            token.casefold() in item["articleBody"].casefold()
            for token in ("27 août", "16h45", "LCI")
        )
    ]
    if len(audited) != 1:
        raise Tf1LciAdapterError(
            "TF1/LCI audited NewsArticle JSON-LD is missing or ambiguous"
        )
    return audited[0]


def _article_year(payload: dict[str, Any]) -> int:
    value = payload.get("datePublished")
    if not isinstance(value, str):
        raise Tf1LciAdapterError("TF1/LCI NewsArticle JSON-LD is missing datePublished")
    match = re.match(r"(\d{4})-", value)
    if match is None:
        raise Tf1LciAdapterError("TF1/LCI datePublished is invalid")
    year = int(match.group(1))
    if year != 2026:
        raise Tf1LciAdapterError(
            "TF1/LCI audited article publication year changed unexpectedly"
        )
    return year


def _contains_full_name(text: str, name: str) -> bool:
    return re.search(
        rf"(?<!\w){re.escape(name)}(?!\w)", text, flags=re.IGNORECASE
    ) is not None


def parse_tf1_lci_html(html: bytes | str) -> tuple[StructuredEventRecord, ...]:
    """Parse exactly two audited debate records from NewsArticle articleBody."""

    payload = _article_payload(_coerce_html(html))
    body = _clean_text(payload["articleBody"])
    year = _article_year(payload)
    first_schedule = re.search(
        r"\b(?:le\s+)?jeudi\s+27\s+août\s+à\s+16h45\b",
        body,
        flags=re.IGNORECASE,
    )
    first_context = (
        "premier débat de la campagne présidentielle de 2027" in body.casefold()
        and "organisé par le medef" in body.casefold()
        and "court philippe-chatrier de roland-garros" in body.casefold()
    )
    first_candidates_present = all(
        _contains_full_name(body, _SUPPORTED_CANDIDATES[candidate_id])
        for candidate_id in _FIRST_DEBATE_CANDIDATE_IDS
    )
    if first_schedule is None or not first_context or not first_candidates_present:
        raise Tf1LciAdapterError(
            "TF1/LCI seven-candidate debate is missing required audited facts"
        )

    second_schedule = re.search(
        r"29\s+août.*?"
        r"(?:à|a)\s+Sens.*?"
        r"Puis\s+à\s+16h45,\s+il\s+présentera\s+un\s+débat\s+entre.*?"
        r"François\s+Hollande.*?Édouard\s+Philippe",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    second_candidates_present = all(
        _contains_full_name(body, _SUPPORTED_CANDIDATES[candidate_id])
        for candidate_id in _SECOND_DEBATE_CANDIDATE_IDS
    )
    if second_schedule is None or not second_candidates_present:
        raise Tf1LciAdapterError(
            "TF1/LCI Hollande-Philippe debate is missing required audited facts"
        )

    return (
        StructuredEventRecord(
            title="Grand débat de la campagne présidentielle sur LCI",
            scheduled_start=f"{year}-08-27T16:45:00+02:00",
            time_precision="datetime",
            timezone="Europe/Paris",
            source_format="json_ld",
            location_name="Court Philippe-Chatrier, Roland-Garros",
            organization="MEDEF",
        ),
        StructuredEventRecord(
            title="Débat entre François Hollande et Édouard Philippe sur LCI",
            scheduled_start=f"{year}-08-29T16:45:00+02:00",
            time_precision="datetime",
            timezone="Europe/Paris",
            source_format="json_ld",
            locality="Sens",
            organization="Laboratoire de la République",
        ),
    )


def _canonical_candidates(
    candidate_registry_path: str | Path,
) -> tuple[dict[str, tuple[str, str]], frozenset[str]]:
    try:
        registry = load_candidate_candidacy_status(candidate_registry_path)
        by_id = candidacy_status_by_id(registry)
        tiers = project_display_tiers(registry)
    except (OSError, ValueError, CandidateCandidacyStatusError) as error:
        raise CandidateAttributionConfigurationError(
            f"canonical candidate registry is unavailable or invalid: {error}"
        ) from error
    active_ids = set(tiers["main"]) | set(tiers["secondary"])
    resolved: dict[str, tuple[str, str]] = {}
    for candidate_id, expected_name in _SUPPORTED_CANDIDATES.items():
        entry = by_id.get(candidate_id)
        if entry is None or entry.get("candidate_name") != expected_name:
            raise CandidateAttributionConfigurationError(
                "canonical candidate registry does not match audited "
                f"TF1/LCI identity: {candidate_id} -> {expected_name}"
            )
        resolved[candidate_id] = (candidate_id, entry["candidate_name"])
    return resolved, frozenset(active_ids)


def _attributed_record(
    event: StructuredEventRecord,
    candidate_ids: tuple[str, ...],
    candidates: dict[str, tuple[str, str]],
) -> AttributedStructuredEvent:
    pairs = sorted(
        (candidates[candidate_id] for candidate_id in candidate_ids),
        key=lambda pair: (pair[1].casefold(), pair[0]),
    )
    return AttributedStructuredEvent(
        structured_event=event,
        candidate_ids=tuple(pair[0] for pair in pairs),
        candidate_names=tuple(pair[1] for pair in pairs),
        attribution_basis="explicit_participant",
    )


def attribute_tf1_lci_events(
    events: Iterable[StructuredEventRecord],
    *,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
) -> CandidateAttributionBatch:
    """Apply bounded article-specific participation attribution."""

    try:
        supplied = tuple(events)
    except TypeError as error:
        raise Tf1LciAdapterError("TF1/LCI structured events must be iterable") from error
    if len(supplied) != 2 or any(
        not isinstance(event, StructuredEventRecord) for event in supplied
    ):
        raise Tf1LciAdapterError(
            "TF1/LCI custom attribution requires exactly two structured records"
        )
    expected = (
        ("2026-08-27T16:45:00+02:00", "MEDEF", _FIRST_DEBATE_CANDIDATE_IDS),
        (
            "2026-08-29T16:45:00+02:00",
            "Laboratoire de la République",
            _SECOND_DEBATE_CANDIDATE_IDS,
        ),
    )
    candidates, active_ids = _canonical_candidates(candidate_registry_path)
    accepted: list[AttributedStructuredEvent] = []
    rejected_records = 0
    for event, (scheduled_start, organization, candidate_ids) in zip(
        supplied, expected
    ):
        if (
            event.scheduled_start != scheduled_start
            or event.organization != organization
            or event.source_format != "json_ld"
        ):
            raise Tf1LciAdapterError(
                "TF1/LCI custom attribution received unexpected event facts"
            )
        active_candidate_ids = tuple(
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id in active_ids
        )
        if len(active_candidate_ids) < 2:
            rejected_records += 1
            continue
        accepted.append(
            _attributed_record(event, active_candidate_ids, candidates)
        )
    return CandidateAttributionBatch(
        accepted=tuple(accepted), rejected_records=rejected_records
    )


def fetch_tf1_lci(
    *,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
) -> str:
    """Fetch only the registered TF1/LCI article through bounded HTTP."""

    try:
        result = fetch_callable(TF1_LCI_URL)
    except Exception as error:
        raise Tf1LciAdapterError(f"TF1/LCI article fetch failed: {error}") from error
    if not isinstance(result, HttpFetchResult):
        raise Tf1LciAdapterError("TF1/LCI article fetch returned an invalid result")
    if not result.success or result.status_code != 200 or result.not_modified:
        detail = result.failure_message or f"HTTP {result.status_code}"
        raise Tf1LciAdapterError(f"TF1/LCI article fetch failed: {detail}")
    if result.response_body is None:
        raise Tf1LciAdapterError("TF1/LCI article fetch returned no response body")
    return _coerce_html(result.response_body)


def build_tf1_lci_events(
    *,
    source: dict[str, Any],
    observed_at: str,
    fetch_callable: Callable[..., HttpFetchResult] = fetch_news_route,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> Tf1LciAdapterResult:
    """Fetch, attribute, and build source-owned observations via Stage 2C."""

    structured = parse_tf1_lci_html(fetch_tf1_lci(fetch_callable=fetch_callable))
    attribution = attribute_tf1_lci_events(
        structured, candidate_registry_path=candidate_registry_path
    )
    observation_batch = build_campaign_event_observations(
        attribution.accepted,
        source=source,
        observed_at=observed_at,
        evidence_url=TF1_LCI_URL,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    return Tf1LciAdapterResult(
        observations=observation_batch.observations,
        attribution_rejected_records=attribution.rejected_records,
    )
