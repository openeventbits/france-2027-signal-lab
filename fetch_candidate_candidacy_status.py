"""Build the candidacy-status registry from a pinned French Wikipedia revision."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    validate_candidate_candidacy_status,
)
from candidate_identity import (
    CandidateIdentityError,
    candidate_identity_map,
    canonical_candidate_name,
    normalized_candidate_key,
)

API_ENDPOINT = "https://fr.wikipedia.org/w/api.php"
PAGE_TITLE = "Élection présidentielle française de 2027"
SOURCE_PUBLISHER = "French Wikipedia"
USER_AGENT = "FR27CandidateUniverse/1.0 (public MediaWiki collector)"


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
    has_personal_article: bool


@dataclass(frozen=True)
class FetchResult:
    revision: RevisionSnapshot
    candidates: tuple[ExtractedCandidate, ...]
    payload: dict[str, Any]


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


def _has_personal_article(node: _HtmlNode, candidate_name: str) -> bool:
    wanted = normalized_candidate_key(candidate_name)
    for link in _descendants(node, "a"):
        href = link.attrs.get("href", "")
        if not href.startswith("/wiki/") or ":" in href.removeprefix("/wiki/"):
            continue
        link_text = _text_content(link)
        if not link_text:
            continue
        try:
            if normalized_candidate_key(link_text) == wanted:
                return True
        except CandidateIdentityError:
            continue
    return False


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
                _has_personal_article(cell, candidate_name),
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
                _has_personal_article(item, candidate_name),
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


def build_payload(
    revision: RevisionSnapshot,
    parsed_html: str,
) -> tuple[dict[str, Any], tuple[ExtractedCandidate, ...]]:
    """Build and validate a deterministic registry payload."""

    extracted = extract_candidates(parsed_html)
    try:
        identities = candidate_identity_map(
            candidate.candidate_name for candidate in extracted
        )
    except CandidateIdentityError as error:
        raise CandidateCandidacyFetchError(
            f"candidate identity collision: {error}"
        ) from error

    records: list[dict[str, str]] = []
    for candidate in extracted:
        rule = SECTION_RULES[candidate.section_title]
        records.append(
            {
                "candidate_id": identities[candidate.candidate_name],
                "candidate_name": candidate.candidate_name,
                "status": rule.status,
                "display_tier": rule.display_tier,
                "status_as_of": revision.revision_date,
                "source_date": revision.revision_date,
                "source_url": revision.permanent_url,
                "source_title": PAGE_TITLE,
                "source_publisher": SOURCE_PUBLISHER,
                "status_note": rule.status_note,
            }
        )
    records.sort(
        key=lambda candidate: (
            candidate["candidate_name"].casefold(),
            candidate["candidate_id"],
        )
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "status_as_of": revision.revision_date,
        "candidates": records,
    }
    try:
        validate_candidate_candidacy_status(payload)
    except CandidateCandidacyStatusError as error:
        raise CandidateCandidacyFetchError(
            f"generated candidacy-status contract is invalid: {error}"
        ) from error
    return payload, tuple(extracted)


def fetch_candidate_candidacy_status(
    fetch_json: FetchJson = _default_fetch_json,
) -> FetchResult:
    """Fetch metadata, parse its exact revision, and build the registry."""

    revision = fetch_current_revision(fetch_json)
    parsed_html = fetch_parsed_revision(revision.revision_id, fetch_json)
    payload, candidates = build_payload(revision, parsed_html)
    return FetchResult(revision, candidates, payload)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate candidate_candidacy_status.json from an exact French "
            "Wikipedia revision"
        )
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    result = fetch_candidate_candidacy_status()
    write_payload_atomic(result.payload, args.output)
    counts: dict[str, int] = {}
    for candidate in result.payload["candidates"]:
        status = candidate["status"]
        counts[status] = counts.get(status, 0) + 1
    print(
        json.dumps(
            {
                "revision_id": result.revision.revision_id,
                "revision_timestamp": result.revision.revision_timestamp,
                "candidate_count": len(result.payload["candidates"]),
                "status_counts": counts,
                "candidates_without_personal_article": [
                    candidate.candidate_name
                    for candidate in result.candidates
                    if not candidate.has_personal_article
                ],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
