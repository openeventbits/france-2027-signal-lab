"""Build the candidacy-status registry from a pinned French Wikipedia revision."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    active_candidate_ids,
    load_candidate_candidacy_status,
    project_active_monitoring_field,
    project_display_tiers,
    semantic_sha256,
    validate_candidate_candidacy_status,
)
from candidate_identity import (
    CandidateIdentityError,
    candidate_id,
    candidate_identity_map,
    canonical_candidate_name,
    normalized_candidate_key,
)

API_ENDPOINT = "https://fr.wikipedia.org/w/api.php"
PAGE_TITLE = "Élection présidentielle française de 2027"
SOURCE_PUBLISHER = "French Wikipedia"
PAGE_URL = (
    "https://fr.wikipedia.org/wiki/"
    + quote(PAGE_TITLE.replace(" ", "_"), safe="()_-")
)
USER_AGENT = "FR27CandidateUniverse/2.0 (public MediaWiki collector)"
SCHEMA_VERSION = "2.0"
DEFAULT_PREVIOUS_PATH = Path("candidate_candidacy_status.json")


class CandidateCandidacyFetchError(ValueError):
    """Raised when a MediaWiki snapshot cannot safely produce a registry."""


@dataclass(frozen=True)
class SectionRule:
    status: str
    display_tier: str
    status_note: str
    structured_kind: str


SECTION_RULES: dict[str, SectionRule] = {
    "Candidats déclarés": SectionRule(
        "declared",
        "main",
        "Listed in the French Wikipedia 2027 election page as a declared candidate.",
        "table",
    ),
    "Candidats déclarés dans le cadre d'une primaire": SectionRule(
        "primary_contender",
        "main",
        "Listed in the French Wikipedia 2027 election page as a primary contender.",
        "table",
    ),
    "Candidats pressentis": SectionRule(
        "active_potential",
        "secondary",
        "Listed in the French Wikipedia 2027 election page as a prospective candidate.",
        "table",
    ),
    "Candidatures retirées": SectionRule(
        "withdrawn",
        "hidden",
        "Listed in the French Wikipedia 2027 election page as a withdrawn candidate.",
        "list",
    ),
    "Candidats pressentis ayant décliné": SectionRule(
        "ruled_out",
        "hidden",
        "Listed in the French Wikipedia 2027 election page as having declined candidacy.",
        "list",
    ),
}

_ACTIVE_STATUSES = frozenset(
    {"declared", "primary_contender", "active_potential"}
)
_HEADING_TAGS = frozenset({"h2", "h3", "h4", "h5", "h6"})
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
_SKIP_TEXT_CLASSES = frozenset(
    {"reference", "cite-bracket", "datasortkey", "mw-editsection"}
)
_AGE_SUFFIX = re.compile(r"\s*\(\s*\d{1,3}\s+ans?\s*\)\s*\Z", re.IGNORECASE)
_REVISION_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

FetchJson = Callable[[Mapping[str, str]], Any]


@dataclass(frozen=True)
class RevisionSnapshot:
    revision_id: int
    revision_timestamp: str

    @property
    def revision_date(self) -> str:
        return self.revision_timestamp[:10]

    @property
    def permanent_url(self) -> str:
        return (
            "https://fr.wikipedia.org/w/index.php?"
            + urlencode({"title": PAGE_TITLE, "oldid": self.revision_id})
        )


@dataclass(frozen=True)
class ExtractedCandidate:
    candidate_name: str
    section_title: str
    requested_article_title: str | None
    wikipedia_article: dict[str, Any] | None = None

    @property
    def has_personal_article(self) -> bool:
        return self.requested_article_title is not None


@dataclass(frozen=True)
class FetchResult:
    revision: RevisionSnapshot
    candidates: tuple[ExtractedCandidate, ...]
    payload: dict[str, Any]
    raw_candidate_count: int
    preserved_candidate_ids: tuple[str, ...]
    new_candidate_ids: tuple[str, ...]
    name_changes: tuple[tuple[str, str, str], ...]
    semantic_changed: bool


@dataclass
class _HtmlNode:
    tag: str
    attrs: dict[str, str]
    children: list[_HtmlNode | str] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode("document", {})
        self._stack = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = _HtmlNode(
            tag.casefold(),
            {key.casefold(): value or "" for key, value in attrs},
        )
        self._stack[-1].children.append(node)
        if node.tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = _HtmlNode(
            tag.casefold(),
            {key.casefold(): value or "" for key, value in attrs},
        )
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.casefold()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == wanted:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


@dataclass
class _SectionState:
    semantic_stack: list[tuple[int, str]] = field(default_factory=list)
    found_sections: set[str] = field(default_factory=set)
    candidates: list[ExtractedCandidate] = field(default_factory=list)

    @property
    def owner(self) -> str | None:
        if not self.semantic_stack:
            return None
        return self.semantic_stack[-1][1]


def _fail(message: str) -> None:
    raise CandidateCandidacyFetchError(message)


def _classes(node: _HtmlNode) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _skip_text_node(node: _HtmlNode) -> bool:
    style = re.sub(r"\s+", "", node.attrs.get("style", "")).casefold()
    return (
        node.tag in {"script", "style", "sup"}
        or "display:none" in style
        or bool(_classes(node) & _SKIP_TEXT_CLASSES)
    )


def _text_content(node: _HtmlNode) -> str:
    parts: list[str] = []

    def visit(value: _HtmlNode | str) -> None:
        if isinstance(value, str):
            parts.append(value)
            return
        if _skip_text_node(value):
            return
        for child in value.children:
            visit(child)

    visit(node)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _text_before_break(node: _HtmlNode) -> str:
    parts: list[str] = []
    stopped = False

    def visit(value: _HtmlNode | str) -> None:
        nonlocal stopped
        if stopped:
            return
        if isinstance(value, str):
            parts.append(value)
            return
        if value.tag == "br":
            stopped = True
            return
        if _skip_text_node(value):
            return
        for child in value.children:
            visit(child)

    visit(node)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _descendants(node: _HtmlNode, tag: str) -> list[_HtmlNode]:
    found: list[_HtmlNode] = []

    def visit(current: _HtmlNode) -> None:
        for child in current.children:
            if not isinstance(child, _HtmlNode):
                continue
            if child.tag == tag:
                found.append(child)
            visit(child)

    visit(node)
    return found


def _direct_elements(node: _HtmlNode, tags: set[str]) -> list[_HtmlNode]:
    return [
        child
        for child in node.children
        if isinstance(child, _HtmlNode) and child.tag in tags
    ]


def _candidate_name_from_table_cell(cell: _HtmlNode) -> str:
    raw_name = _AGE_SUFFIX.sub("", _text_before_break(cell)).strip(" ,;:-")
    try:
        return canonical_candidate_name(raw_name)
    except CandidateIdentityError as error:
        raise CandidateCandidacyFetchError(
            f"candidate table contains a malformed name: {raw_name!r}"
        ) from error


def _candidate_name_from_list_item(item: _HtmlNode) -> str:
    leading = _text_content(item)
    raw_name = re.split(r"\s*(?:,|\()", leading, maxsplit=1)[0].strip()
    try:
        return canonical_candidate_name(raw_name)
    except CandidateIdentityError as error:
        raise CandidateCandidacyFetchError(
            f"candidate list contains a malformed name: {raw_name!r}"
        ) from error


def _personal_article_title(
    node: _HtmlNode,
    candidate_name: str,
) -> str | None:
    """Return the requested personal article title, never an identity ID."""

    wanted = normalized_candidate_key(candidate_name)
    for link in _descendants(node, "a"):
        href = link.attrs.get("href", "")
        parsed_href = urlsplit(href)
        if not parsed_href.path.startswith("/wiki/"):
            continue
        raw_title = unquote(parsed_href.path.removeprefix("/wiki/"))
        requested_title = raw_title.replace("_", " ").strip()
        if not requested_title or ":" in requested_title:
            continue
        link_text = _text_content(link)
        if not link_text:
            continue
        try:
            if normalized_candidate_key(link_text) == wanted:
                return canonical_candidate_name(requested_title)
        except CandidateIdentityError:
            continue
    return None


def _table_rows(table: _HtmlNode) -> list[_HtmlNode]:
    rows: list[_HtmlNode] = []

    def visit(node: _HtmlNode) -> None:
        for child in node.children:
            if not isinstance(child, _HtmlNode):
                continue
            if child.tag == "table":
                continue
            if child.tag == "tr":
                rows.append(child)
            else:
                visit(child)

    visit(table)
    return rows


def _extract_candidate_table(
    table: _HtmlNode,
    section_title: str,
) -> list[ExtractedCandidate]:
    rows = _table_rows(table)
    candidate_column: int | None = None
    header_index: int | None = None
    for index, row in enumerate(rows):
        cells = _direct_elements(row, {"th", "td"})
        for cell_index, cell in enumerate(cells):
            header = _text_content(cell)
            if re.match(r"^Candidat(?:e|s)?\b", header, re.IGNORECASE):
                candidate_column = cell_index
                header_index = index
                break
        if candidate_column is not None:
            break
    if candidate_column is None or header_index is None:
        return []

    extracted: list[ExtractedCandidate] = []
    for row in rows[header_index + 1 :]:
        cells = _direct_elements(row, {"th", "td"})
        if not cells:
            continue
        if candidate_column >= len(cells):
            _fail(
                f"candidate table row in {section_title!r} is missing "
                "its candidate cell"
            )
        cell = cells[candidate_column]
        if re.match(
            r"^Candidat(?:e|s)?\b",
            _text_content(cell),
            re.IGNORECASE,
        ):
            continue
        candidate_name = _candidate_name_from_table_cell(cell)
        extracted.append(
            ExtractedCandidate(
                candidate_name,
                section_title,
                _personal_article_title(cell, candidate_name),
            )
        )
    return extracted


def _extract_candidate_list(
    candidate_list: _HtmlNode,
    section_title: str,
) -> list[ExtractedCandidate]:
    extracted: list[ExtractedCandidate] = []
    for item in _direct_elements(candidate_list, {"li"}):
        candidate_name = _candidate_name_from_list_item(item)
        extracted.append(
            ExtractedCandidate(
                candidate_name,
                section_title,
                _personal_article_title(item, candidate_name),
            )
        )
    return extracted


def _record_heading(node: _HtmlNode, state: _SectionState) -> None:
    level = int(node.tag[1])
    title = _text_content(node)
    while state.semantic_stack and state.semantic_stack[-1][0] >= level:
        state.semantic_stack.pop()
    if title not in SECTION_RULES:
        return
    if title in state.found_sections:
        _fail(f"required semantic section appears more than once: {title!r}")
    state.found_sections.add(title)
    state.semantic_stack.append((level, title))


def _scan_document(node: _HtmlNode, state: _SectionState) -> None:
    for child in node.children:
        if not isinstance(child, _HtmlNode):
            continue
        if child.tag in _HEADING_TAGS:
            _record_heading(child, state)
            continue
        owner = state.owner
        if child.tag == "table":
            if owner is not None and SECTION_RULES[owner].structured_kind == "table":
                state.candidates.extend(_extract_candidate_table(child, owner))
            continue
        if child.tag == "ul":
            if owner is not None and SECTION_RULES[owner].structured_kind == "list":
                state.candidates.extend(_extract_candidate_list(child, owner))
            continue
        _scan_document(child, state)


def extract_candidates(parsed_html: str) -> list[ExtractedCandidate]:
    """Extract section-owned candidate records from MediaWiki parse HTML."""

    if not isinstance(parsed_html, str) or not parsed_html.strip():
        _fail("MediaWiki parse text must be non-empty HTML")
    parser = _TreeParser()
    try:
        parser.feed(parsed_html)
        parser.close()
    except Exception as error:
        raise CandidateCandidacyFetchError(
            "MediaWiki parse text is malformed HTML"
        ) from error

    state = _SectionState()
    _scan_document(parser.root, state)
    missing_sections = sorted(set(SECTION_RULES) - state.found_sections)
    if missing_sections:
        _fail(f"required semantic sections are missing: {missing_sections}")
    if not state.candidates:
        _fail("no candidates were extracted from required semantic sections")

    identities: dict[str, ExtractedCandidate] = {}
    for candidate in state.candidates:
        key = normalized_candidate_key(candidate.candidate_name)
        prior = identities.get(key)
        if prior is not None:
            if prior.section_title != candidate.section_title:
                _fail(
                    "candidate appears in conflicting semantic categories: "
                    f"{prior.candidate_name!r} in {prior.section_title!r} and "
                    f"{candidate.section_title!r}"
                )
            _fail(f"duplicate candidate identity: {candidate.candidate_name!r}")
        identities[key] = candidate

    try:
        candidate_identity_map(
            candidate.candidate_name for candidate in state.candidates
        )
    except CandidateIdentityError as error:
        raise CandidateCandidacyFetchError(
            f"candidate identity collision: {error}"
        ) from error

    if not any(
        SECTION_RULES[candidate.section_title].status in _ACTIVE_STATUSES
        for candidate in state.candidates
    ):
        _fail("no active candidates were extracted")
    return state.candidates


def _default_fetch_json(params: Mapping[str, str]) -> Any:
    request = Request(
        f"{API_ENDPOINT}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as error:
        raise CandidateCandidacyFetchError(
            f"MediaWiki API request failed: {error}"
        ) from error


def fetch_current_revision(
    fetch_json: FetchJson = _default_fetch_json,
) -> RevisionSnapshot:
    """Fetch the latest revision ID and timestamp for the configured page."""

    response = fetch_json(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "revisions",
            "rvprop": "ids|timestamp",
            "rvslots": "main",
            "rvlimit": "1",
            "titles": PAGE_TITLE,
        }
    )
    try:
        pages = response["query"]["pages"]
        if not isinstance(pages, list) or len(pages) != 1:
            raise TypeError("query.pages must contain exactly one page")
        page = pages[0]
        if not isinstance(page, dict) or page.get("missing") is True:
            raise TypeError("the configured page is missing")
        revisions = page["revisions"]
        if not isinstance(revisions, list) or len(revisions) != 1:
            raise TypeError("page.revisions must contain exactly one revision")
        revision = revisions[0]
        revision_id = revision["revid"]
        revision_timestamp = revision["timestamp"]
    except (KeyError, TypeError, IndexError) as error:
        raise CandidateCandidacyFetchError(
            f"malformed MediaWiki revision response: {error}"
        ) from error

    if type(revision_id) is not int or revision_id <= 0:
        _fail("MediaWiki revision ID is missing or invalid")
    if not isinstance(revision_timestamp, str) or not _REVISION_TIMESTAMP.fullmatch(
        revision_timestamp
    ):
        _fail("MediaWiki revision timestamp is missing or invalid")
    try:
        parsed_timestamp = datetime.fromisoformat(
            revision_timestamp.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise CandidateCandidacyFetchError(
            "MediaWiki revision timestamp is invalid"
        ) from error
    if parsed_timestamp.tzinfo != timezone.utc:
        _fail("MediaWiki revision timestamp must be UTC")
    return RevisionSnapshot(revision_id, revision_timestamp)


def fetch_parsed_revision(
    revision_id: int,
    fetch_json: FetchJson = _default_fetch_json,
) -> str:
    """Fetch parsed HTML for exactly ``revision_id`` using ``oldid``."""

    response = fetch_json(
        {
            "action": "parse",
            "format": "json",
            "formatversion": "2",
            "oldid": str(revision_id),
            "prop": "text",
            "disabletoc": "1",
        }
    )
    try:
        parsed = response["parse"]
        parsed_revision_id = parsed["revid"]
        parsed_title = parsed["title"]
        parsed_html = parsed["text"]
    except (KeyError, TypeError) as error:
        raise CandidateCandidacyFetchError(
            f"malformed MediaWiki parse response: {error}"
        ) from error
    if parsed_revision_id != revision_id:
        _fail(
            "MediaWiki parse response revision does not match requested oldid: "
            f"expected {revision_id}, got {parsed_revision_id!r}"
        )
    if parsed_title != PAGE_TITLE:
        _fail(
            "MediaWiki parse response title does not match configured page: "
            f"{parsed_title!r}"
        )
    if not isinstance(parsed_html, str) or not parsed_html.strip():
        _fail("MediaWiki parse response text is missing or invalid")
    return parsed_html


def _canonical_article_url(title: str) -> str:
    article_path = quote(title.replace(" ", "_"), safe="()_-")
    return f"https://fr.wikipedia.org/wiki/{article_path}"


def _resolved_article_record(
    page: Any,
    requested_title: str,
) -> dict[str, Any]:
    if not isinstance(page, dict) or page.get("missing") is True:
        raise CandidateCandidacyFetchError(
            f"linked personal article is missing: {requested_title!r}"
        )
    try:
        page_id = page["pageid"]
        namespace = page["ns"]
        canonical_title = page["title"]
    except KeyError as error:
        raise CandidateCandidacyFetchError(
            f"malformed MediaWiki article response for {requested_title!r}: "
            f"{error}"
        ) from error
    if type(page_id) is not int or page_id <= 0:
        _fail(
            f"MediaWiki article page_id is invalid for {requested_title!r}"
        )
    if namespace != 0:
        _fail(
            f"MediaWiki personal article is not in the main namespace: "
            f"{requested_title!r}"
        )
    try:
        title = canonical_candidate_name(canonical_title)
    except CandidateIdentityError as error:
        raise CandidateCandidacyFetchError(
            f"MediaWiki canonical article title is invalid for "
            f"{requested_title!r}: {error}"
        ) from error
    if title != canonical_title:
        _fail(
            f"MediaWiki canonical article title is not normalized: "
            f"{canonical_title!r}"
        )
    return {
        "page_id": page_id,
        "title": title,
        "url": _canonical_article_url(title),
    }


def _resolve_wikipedia_article_batch(
    titles: list[str],
    fetch_json: FetchJson = _default_fetch_json,
) -> dict[str, dict[str, Any]]:
    """Resolve one MediaWiki API batch of canonical requested titles."""

    if not titles:
        return {}
    response = fetch_json(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "info",
            "redirects": "1",
            "titles": "|".join(titles),
        }
    )
    try:
        query = response["query"]
        pages = query["pages"]
        normalized = query.get("normalized", [])
        redirects = query.get("redirects", [])
        if not isinstance(pages, list):
            raise TypeError("query.pages must be a list")
        if not isinstance(normalized, list) or not isinstance(redirects, list):
            raise TypeError("query title mappings must be lists")
    except (KeyError, TypeError) as error:
        raise CandidateCandidacyFetchError(
            f"malformed MediaWiki article response: {error}"
        ) from error

    transitions: dict[str, str] = {}
    for context, mappings in (
        ("normalized", normalized),
        ("redirects", redirects),
    ):
        for mapping in mappings:
            try:
                source = canonical_candidate_name(mapping["from"])
                destination = canonical_candidate_name(mapping["to"])
            except (KeyError, TypeError, CandidateIdentityError) as error:
                raise CandidateCandidacyFetchError(
                    f"malformed MediaWiki {context} mapping: {error}"
                ) from error
            prior = transitions.get(source)
            if prior is not None and prior != destination:
                _fail(
                    "conflicting MediaWiki article title mappings for "
                    f"{source!r}"
                )
            transitions[source] = destination

    pages_by_title: dict[str, dict[str, Any]] = {}
    for page in pages:
        article = _resolved_article_record(page, "batch response")
        title = article["title"]
        if title in pages_by_title:
            _fail(f"duplicate MediaWiki article page title: {title!r}")
        pages_by_title[title] = article

    resolved: dict[str, dict[str, Any]] = {}
    for requested_title in titles:
        final_title = requested_title
        seen: set[str] = set()
        while final_title in transitions:
            if final_title in seen:
                _fail(
                    "cyclic MediaWiki article title mapping for "
                    f"{requested_title!r}"
                )
            seen.add(final_title)
            final_title = transitions[final_title]
        article = pages_by_title.get(final_title)
        if article is None:
            _fail(
                "MediaWiki article response did not resolve requested title: "
                f"{requested_title!r}"
            )
        resolved[requested_title] = copy.deepcopy(article)
    return resolved


def resolve_wikipedia_articles(
    requested_titles: list[str],
    fetch_json: FetchJson = _default_fetch_json,
) -> dict[str, dict[str, Any]]:
    """Resolve article identities in API batches without a roster-size limit."""

    titles: list[str] = []
    for requested_title in requested_titles:
        try:
            title = canonical_candidate_name(requested_title)
        except CandidateIdentityError as error:
            raise CandidateCandidacyFetchError(
                "requested Wikipedia article title must be non-empty text"
            ) from error
        if title not in titles:
            titles.append(title)
    resolved: dict[str, dict[str, Any]] = {}
    for start in range(0, len(titles), 50):
        resolved.update(
            _resolve_wikipedia_article_batch(
                titles[start : start + 50],
                fetch_json,
            )
        )
    return resolved


def resolve_wikipedia_article(
    requested_title: str,
    fetch_json: FetchJson = _default_fetch_json,
) -> dict[str, Any]:
    """Resolve one redirect and return stable French Wikipedia page identity."""

    try:
        title = canonical_candidate_name(requested_title)
    except CandidateIdentityError as error:
        raise CandidateCandidacyFetchError(
            "requested Wikipedia article title must be non-empty text"
        ) from error
    return resolve_wikipedia_articles([title], fetch_json)[title]


def resolve_candidate_articles(
    candidates: list[ExtractedCandidate],
    fetch_json: FetchJson = _default_fetch_json,
) -> list[ExtractedCandidate]:
    """Resolve every linked article; unlinked candidates remain valid."""

    requested_titles = [
        candidate.requested_article_title
        for candidate in candidates
        if candidate.requested_article_title is not None
    ]
    article_cache = resolve_wikipedia_articles(requested_titles, fetch_json)
    resolved: list[ExtractedCandidate] = []
    for candidate in candidates:
        requested_title = candidate.requested_article_title
        article = None
        if requested_title is not None:
            article = article_cache[
                canonical_candidate_name(requested_title)
            ]
        resolved.append(
            replace(
                candidate,
                wikipedia_article=copy.deepcopy(article),
            )
        )
    return resolved


def load_previous_registry(path: str | Path) -> dict[str, Any]:
    """Load a required last-good registry for identity reconciliation."""

    previous_path = Path(path)
    if not previous_path.is_file():
        raise CandidateCandidacyFetchError(
            f"previous registry does not exist: {previous_path}; "
            "use --no-previous only for an intentional bootstrap"
        )
    try:
        return load_candidate_candidacy_status(previous_path)
    except (OSError, json.JSONDecodeError, CandidateCandidacyStatusError) as error:
        raise CandidateCandidacyFetchError(
            f"previous registry is unavailable or invalid: {error}"
        ) from error


def _previous_names(candidate: Mapping[str, Any]) -> list[str]:
    value = candidate.get("previous_names", [])
    return list(value) if isinstance(value, list) else []


def _previous_article(candidate: Mapping[str, Any]) -> dict[str, Any] | None:
    value = candidate.get("wikipedia_article")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def reconcile_candidate_identities(
    extracted: list[ExtractedCandidate],
    previous_registry: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any] | None], tuple[str, ...], tuple[str, ...]]:
    """Match raw candidates to prior identities without creating records."""

    if previous_registry is None:
        return (
            {candidate.candidate_name: None for candidate in extracted},
            (),
            (),
        )
    try:
        validate_candidate_candidacy_status(previous_registry)
    except CandidateCandidacyStatusError as error:
        raise CandidateCandidacyFetchError(
            f"previous registry is invalid: {error}"
        ) from error

    previous = previous_registry["candidates"]
    by_page_id: dict[int, list[dict[str, Any]]] = {}
    by_current_name: dict[str, list[dict[str, Any]]] = {}
    by_alias: dict[str, list[dict[str, Any]]] = {}
    for candidate in previous:
        article = candidate.get("wikipedia_article")
        if isinstance(article, dict):
            by_page_id.setdefault(article["page_id"], []).append(candidate)
        by_current_name.setdefault(
            normalized_candidate_key(candidate["candidate_name"]),
            [],
        ).append(candidate)
        for previous_name in _previous_names(candidate):
            by_alias.setdefault(
                normalized_candidate_key(previous_name),
                [],
            ).append(candidate)

    matches: dict[str, dict[str, Any] | None] = {}
    matched_previous_ids: set[str] = set()
    preserved: list[str] = []
    for candidate in extracted:
        possible: dict[str, dict[str, Any]] = {}
        article = candidate.wikipedia_article
        if article is not None:
            for match in by_page_id.get(article["page_id"], []):
                possible[match["candidate_id"]] = match
        name_key = normalized_candidate_key(candidate.candidate_name)
        for match in by_current_name.get(name_key, []):
            possible[match["candidate_id"]] = match
        for match in by_alias.get(name_key, []):
            possible[match["candidate_id"]] = match
        if len(possible) > 1:
            _fail(
                "ambiguous previous candidate identity for "
                f"{candidate.candidate_name!r}: {sorted(possible)}"
            )
        match = next(iter(possible.values()), None)
        if match is not None:
            identifier = match["candidate_id"]
            if identifier in matched_previous_ids:
                _fail(
                    "multiple raw candidates reconcile to previous identity: "
                    f"{identifier}"
                )
            matched_previous_ids.add(identifier)
            preserved.append(identifier)
        matches[candidate.candidate_name] = match
    return matches, tuple(sorted(preserved)), tuple(sorted(matched_previous_ids))


def _section_for_previous_status(status: str) -> str | None:
    for title, rule in SECTION_RULES.items():
        if rule.status == status:
            return title
    return None


def validate_extraction_anomalies(
    extracted: list[ExtractedCandidate],
    previous_registry: dict[str, Any] | None,
    matches: Mapping[str, dict[str, Any] | None],
) -> None:
    """Reject catastrophic raw-source losses before retaining absences.

    Explicit moves to withdrawn or ruled-out sections remain matched identities
    and therefore are transitions, not disappearances.
    """

    if not extracted:
        _fail("raw candidate extraction is empty")
    if not any(
        SECTION_RULES[candidate.section_title].display_tier
        in {"main", "secondary"}
        for candidate in extracted
    ):
        _fail("active raw candidate extraction is empty")
    if previous_registry is None:
        return

    previous = previous_registry["candidates"]
    # Identities already marked temporarily_missing were not present in the
    # immediately preceding raw snapshot.  Do not count them again as a fresh
    # loss on every later refresh; only newly absent, previously-present
    # identities belong in the delta guard.
    previously_present = [
        candidate
        for candidate in previous
        if candidate.get("upstream_presence", "present") == "present"
    ]
    matched_ids = {
        match["candidate_id"]
        for match in matches.values()
        if match is not None
    }
    disappeared = [
        candidate
        for candidate in previously_present
        if candidate["candidate_id"] not in matched_ids
    ]
    if len(disappeared) <= 1:
        return

    raw_section_counts = {
        title: sum(candidate.section_title == title for candidate in extracted)
        for title in SECTION_RULES
    }
    previous_section_members: dict[str, list[dict[str, Any]]] = {
        title: [] for title in SECTION_RULES
    }
    for candidate in previously_present:
        title = _section_for_previous_status(candidate["status"])
        if title is not None:
            previous_section_members[title].append(candidate)
    for title, members in previous_section_members.items():
        unexplained = [
            candidate
            for candidate in members
            if candidate["candidate_id"] not in matched_ids
        ]
        if len(members) >= 2 and raw_section_counts[title] == 0 and unexplained:
            _fail(
                "configured semantic section unexpectedly became empty: "
                f"{title!r} previously had {len(members)} candidates"
            )

    total_threshold = max(
        2,
        min(3, math.ceil(len(previously_present) * 0.20)),
    )
    if len(disappeared) >= total_threshold:
        _fail(
            "catastrophic unexplained candidate disappearance: "
            f"{len(disappeared)} of {len(previously_present)} previously "
            "present identities"
        )

    previous_active = set(active_candidate_ids(previous_registry))
    disappeared_active = [
        candidate
        for candidate in disappeared
        if candidate["candidate_id"] in previous_active
    ]
    active_threshold = max(
        2,
        min(2, math.ceil(len(previous_active) * 0.15)),
    )
    if len(disappeared_active) >= active_threshold:
        _fail(
            "catastrophic unexplained active-candidate disappearance: "
            f"{len(disappeared_active)} of {len(previous_active)} previous "
            "active identities"
        )


def _status_source_fields(
    revision: RevisionSnapshot,
    rule: SectionRule,
) -> dict[str, str]:
    return {
        "status_as_of": revision.revision_date,
        "source_date": revision.revision_date,
        "source_url": revision.permanent_url,
        "source_title": PAGE_TITLE,
        "source_publisher": SOURCE_PUBLISHER,
        "status_note": rule.status_note,
    }


def _retained_status_source_fields(
    previous: Mapping[str, Any],
) -> dict[str, str]:
    return {
        field: previous[field]
        for field in (
            "status_as_of",
            "source_date",
            "source_url",
            "source_title",
            "source_publisher",
            "status_note",
        )
    }


def _sorted_previous_names(
    previous: Mapping[str, Any] | None,
    current_name: str,
) -> list[str]:
    names = set(_previous_names(previous or {}))
    if previous is not None and previous["candidate_name"] != current_name:
        names.add(previous["candidate_name"])
    names.discard(current_name)
    return sorted(names, key=lambda name: (name.casefold(), name))


def _build_payload_details(
    revision: RevisionSnapshot,
    parsed_html: str,
    *,
    previous_registry: dict[str, Any] | None = None,
    article_resolver: Callable[[str], dict[str, Any]] | None = None,
    article_fetch_json: FetchJson | None = None,
) -> tuple[
    dict[str, Any],
    tuple[ExtractedCandidate, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str, str], ...],
]:
    extracted = extract_candidates(parsed_html)
    if article_resolver is not None and article_fetch_json is not None:
        _fail("only one Wikipedia article resolution strategy may be used")
    if article_fetch_json is not None:
        extracted = resolve_candidate_articles(extracted, article_fetch_json)
    elif article_resolver is not None:
        extracted = [
            replace(
                candidate,
                wikipedia_article=(
                    article_resolver(candidate.requested_article_title)
                    if candidate.requested_article_title is not None
                    else None
                ),
            )
            for candidate in extracted
        ]

    (
        matches,
        _matched_present,
        _matched_previous,
    ) = reconcile_candidate_identities(extracted, previous_registry)
    validate_extraction_anomalies(extracted, previous_registry, matches)

    previous_candidates = (
        previous_registry["candidates"] if previous_registry is not None else []
    )
    previous_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in previous_candidates
    }
    preserved = tuple(sorted(previous_by_id))
    used_ids = set(previous_by_id)
    records: list[dict[str, Any]] = []
    new_ids: list[str] = []
    name_changes: list[tuple[str, str, str]] = []
    present_ids: set[str] = set()

    for candidate in extracted:
        rule = SECTION_RULES[candidate.section_title]
        previous = matches[candidate.candidate_name]
        if previous is None:
            try:
                identifier = candidate_id(candidate.candidate_name)
            except CandidateIdentityError as error:
                raise CandidateCandidacyFetchError(
                    f"candidate identity allocation failed: {error}"
                ) from error
            if identifier in used_ids:
                _fail(
                    "new candidate ID collides with an existing stable ID: "
                    f"{identifier}"
                )
            used_ids.add(identifier)
            new_ids.append(identifier)
            source_fields = _status_source_fields(revision, rule)
        else:
            identifier = previous["candidate_id"]
            if previous["candidate_name"] != candidate.candidate_name:
                name_changes.append(
                    (
                        identifier,
                        previous["candidate_name"],
                        candidate.candidate_name,
                    )
                )
            if (
                previous["status"] != rule.status
                or previous["display_tier"] != rule.display_tier
            ):
                source_fields = _status_source_fields(revision, rule)
            else:
                source_fields = _retained_status_source_fields(previous)
        present_ids.add(identifier)
        article = candidate.wikipedia_article
        if article is None and previous is not None:
            article = _previous_article(previous)
        records.append(
            {
                "candidate_id": identifier,
                "candidate_name": candidate.candidate_name,
                "status": rule.status,
                "display_tier": rule.display_tier,
                "upstream_presence": "present",
                "wikipedia_article": copy.deepcopy(article),
                "previous_names": _sorted_previous_names(
                    previous,
                    candidate.candidate_name,
                ),
                **source_fields,
            }
        )

    for previous in previous_candidates:
        if previous["candidate_id"] in present_ids:
            continue
        retained = {
            field: copy.deepcopy(previous[field])
            for field in (
                "candidate_id",
                "candidate_name",
                "status",
                "display_tier",
            )
        }
        retained.update(
            {
                "upstream_presence": "temporarily_missing",
                "wikipedia_article": _previous_article(previous),
                "previous_names": sorted(
                    _previous_names(previous),
                    key=lambda name: (name.casefold(), name),
                ),
                **_retained_status_source_fields(previous),
            }
        )
        records.append(retained)

    records.sort(
        key=lambda candidate: (
            candidate["candidate_name"].casefold(),
            candidate["candidate_id"],
        )
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status_as_of": revision.revision_date,
        "source": {
            "publisher": SOURCE_PUBLISHER,
            "page_title": PAGE_TITLE,
            "page_url": PAGE_URL,
            "revision_id": revision.revision_id,
            "revision_timestamp": revision.revision_timestamp,
            "revision_url": revision.permanent_url,
        },
        "candidates": records,
    }
    try:
        validate_candidate_candidacy_status(payload)
    except CandidateCandidacyStatusError as error:
        raise CandidateCandidacyFetchError(
            f"generated candidacy-status contract is invalid: {error}"
        ) from error
    return (
        payload,
        tuple(extracted),
        preserved,
        tuple(sorted(new_ids)),
        tuple(sorted(name_changes)),
    )


def build_payload(
    revision: RevisionSnapshot,
    parsed_html: str,
    *,
    previous_registry: dict[str, Any] | None = None,
    article_resolver: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], tuple[ExtractedCandidate, ...]]:
    """Build and validate one deterministic schema-v2 registry payload."""

    payload, extracted, _preserved, _new_ids, _name_changes = (
        _build_payload_details(
            revision,
            parsed_html,
            previous_registry=previous_registry,
            article_resolver=article_resolver,
        )
    )
    return payload, extracted


def fetch_candidate_candidacy_status(
    fetch_json: FetchJson = _default_fetch_json,
    *,
    previous_registry: dict[str, Any] | None = None,
) -> FetchResult:
    """Fetch metadata, parse its exact revision, and build the registry."""

    revision = fetch_current_revision(fetch_json)
    parsed_html = fetch_parsed_revision(revision.revision_id, fetch_json)
    details = _build_payload_details(
        revision,
        parsed_html,
        previous_registry=previous_registry,
        article_fetch_json=fetch_json,
    )
    payload, candidates, preserved, new_ids, name_changes = details
    semantic_changed = (
        previous_registry is None
        or semantic_sha256(payload) != semantic_sha256(previous_registry)
    )
    return FetchResult(
        revision=revision,
        candidates=candidates,
        payload=payload,
        raw_candidate_count=len(candidates),
        preserved_candidate_ids=preserved,
        new_candidate_ids=new_ids,
        name_changes=name_changes,
        semantic_changed=semantic_changed,
    )


def serialize_payload(payload: Any) -> str:
    """Validate and serialize a registry deterministically as UTF-8 JSON."""

    try:
        validate_candidate_candidacy_status(payload)
    except CandidateCandidacyStatusError as error:
        raise CandidateCandidacyFetchError(
            f"generated candidacy-status contract is invalid: {error}"
        ) from error
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_payload_atomic(payload: Any, output_path: str | Path) -> None:
    """Validate fully, then atomically replace ``output_path``."""

    serialized = serialize_payload(payload)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate candidate_candidacy_status.json from an exact French "
            "Wikipedia revision"
        )
    )
    parser.add_argument("--output", required=True, type=Path)
    previous_group = parser.add_mutually_exclusive_group()
    previous_group.add_argument(
        "--previous",
        type=Path,
        default=DEFAULT_PREVIOUS_PATH,
        help=(
            "validated last-good registry used for stable identity and "
            "lifecycle reconciliation"
        ),
    )
    previous_group.add_argument(
        "--no-previous",
        action="store_true",
        help="intentional bootstrap without a prior registry",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    previous_registry = (
        None
        if args.no_previous
        else load_previous_registry(args.previous)
    )
    result = fetch_candidate_candidacy_status(
        previous_registry=previous_registry,
    )
    write_payload_atomic(result.payload, args.output)
    counts: dict[str, int] = {}
    for candidate in result.payload["candidates"]:
        status = candidate["status"]
        counts[status] = counts.get(status, 0) + 1
    projection = project_display_tiers(result.payload)
    active_projection = project_active_monitoring_field(result.payload)
    article_candidates = [
        candidate
        for candidate in result.payload["candidates"]
        if candidate["wikipedia_article"] is not None
    ]
    print(
        json.dumps(
            {
                "revision_id": result.revision.revision_id,
                "revision_timestamp": result.revision.revision_timestamp,
                "raw_candidate_count": result.raw_candidate_count,
                "reconciled_candidate_count": len(
                    result.payload["candidates"]
                ),
                "main_count": projection["counts"]["main"],
                "secondary_count": projection["counts"]["secondary"],
                "hidden_count": projection["counts"]["hidden"],
                "active_count": active_projection["counts"]["active"],
                "temporarily_missing_count": sum(
                    candidate["upstream_presence"] == "temporarily_missing"
                    for candidate in result.payload["candidates"]
                ),
                "status_counts": counts,
                "candidates_with_article_page_id": len(article_candidates),
                "candidates_without_personal_article": [
                    candidate["candidate_name"]
                    for candidate in result.payload["candidates"]
                    if candidate["wikipedia_article"] is None
                ],
                "preserved_candidate_ids": list(
                    result.preserved_candidate_ids
                ),
                "new_candidate_ids": list(result.new_candidate_ids),
                "name_changes": [
                    {
                        "candidate_id": identifier,
                        "previous_name": previous_name,
                        "candidate_name": candidate_name,
                    }
                    for identifier, previous_name, candidate_name
                    in result.name_changes
                ],
                "semantic_changed": result.semantic_changed,
                "semantic_sha256": semantic_sha256(result.payload),
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
