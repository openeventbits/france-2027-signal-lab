"""Discover and persist official Commission des sondages notice records."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from commission_notice_coverage import (
    CommissionCoverageError,
    synchronize_notice_coverage,
    validate_notice_coverage,
)


INDEX_URL = "https://www.commission-des-sondages.fr/notices/"
SOURCE_NAME = "Commission des sondages"
SCHEMA_VERSION = "1.0"
USER_AGENT = "France2027SignalLab/1.0 (contact: malatazen@gmail.com)"
OFFICIAL_HOST = "www.commission-des-sondages.fr"
CLASSIFICATIONS = {
    "eligible",
    "excluded_non_voting",
    "ambiguous",
    "unsupported",
}
ROUND_NAMES = {"first_round", "second_round"}

MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}

INSTITUTE_PATTERNS = (
    (r"\bTOLUNA\s+HARRIS\s+INTERACTIVE\b", "Harris Interactive"),
    (r"\bHARRIS\s+INTERACTIVE\b", "Harris Interactive"),
    (r"\bIPSOS\s+BVA\b", "Ipsos"),
    (r"\bOPINION\s*WAY\b", "OpinionWay"),
    (r"\bCLUSTER\s*17\b", "Cluster17"),
    (r"\bVERIAN\b", "Verian"),
    (r"\bYOUGOV\b", "YouGov"),
    (r"\bELABE\b", "Elabe"),
    (r"\bIFOP\b", "Ifop"),
    (r"\bODOXA\b", "Odoxa"),
    (r"\bCSA\b", "CSA"),
    (r"\bPIG[ÉE]!\b", "Pigé!"),
    (r"\bSAGIS\b", "Sagis"),
)

POSITIVE_LISTING_PATTERNS = (
    r"\bintentions?\s+de\s+vote\b",
    r"\bpresidentiell?e?\s+(?:de\s+)?2027\b",
    r"\belection\s+presidentielle\s+(?:de\s+)?2027\b",
    r"\bpr\s*2027\b",
    r"\bpresitrack\b",
    r"\biv\b",
    r"\b1er\s+tour\b",
    r"\bpremier\s+tour\b",
    r"\b2(?:e|eme|nd)\s+tour\b",
    r"\bsecond\s+tour\b",
)

NEGATIVE_LISTING_PATTERNS = (
    r"\bpopularite\b",
    r"\bapprobation\b",
    r"\bconfiance\b",
    r"\bimage\b",
    r"\bnotoriete\b",
    r"\bstature\b",
    r"\bpersonnalites?\b",
    r"\btableau\s+de\s+bord\b",
    r"\btbd\b",
    r"\bbarometre\b",
    r"\bobservatoire\s+politique\b",
    r"\bpresident\s+ideal\b",
    r"\bbon\s+president\b",
)


class CommissionNoticeError(ValueError):
    """Raised when official notice discovery cannot be trusted."""


@dataclass(frozen=True)
class FetchResult:
    """One official HTTP response after redirects."""

    content: bytes
    final_url: str
    content_type: str


@dataclass(frozen=True)
class ListingDecision:
    """The listing-level eligibility decision."""

    classification: str
    reason: str
    inspect_document: bool
    strongly_eligible: bool = False


@dataclass
class DiscoveryResult:
    """An in-memory registry plus non-fatal diagnostics."""

    registry: dict[str, Any]
    diagnostics: list[str]


FetchFunction = Callable[[str, str], FetchResult]


def normalize_text(value: str) -> str:
    """Normalize accents, capitalization, punctuation, and whitespace."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).split()
    )


def _require_official_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or (parsed.hostname or "").casefold() != OFFICIAL_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 80, 443}
    ):
        raise CommissionNoticeError(
            f"notice URL is outside the official origin for the Commission: {value!r}"
        )
    return value


class _OfficialRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _require_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_official_url(
    url: str,
    method: str = "GET",
    *,
    timeout: int = 20,
) -> FetchResult:
    """Fetch one official URL while rejecting off-origin redirects."""
    _require_official_url(url)
    request = Request(
        url,
        method=method,
        headers={"User-Agent": USER_AGENT},
    )
    opener = build_opener(_OfficialRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        final_url = _require_official_url(response.geturl())
        content = response.read() if method != "HEAD" else b""
        content_type = response.headers.get_content_type()
    return FetchResult(content, final_url, content_type)


def _month_context(anchor: Any) -> tuple[int, int]:
    headings = anchor.xpath(
        "ancestor::dd[1]//*[self::h1 or self::h2 or self::h3][1]"
    )
    if not headings:
        raise CommissionNoticeError(
            "notice listing lacks a recognizable month heading"
        )
    heading = normalize_text(headings[0].text_content())
    year_matches = re.findall(r"\b(20\d{2})\b", heading)
    month_matches = [
        month_number
        for month_name, month_number in MONTHS.items()
        if re.search(rf"\b{month_name}\b", heading)
    ]
    if len(year_matches) != 1 or len(month_matches) != 1:
        raise CommissionNoticeError(
            f"unrecognized notice month heading: {headings[0].text_content()!r}"
        )
    return int(year_matches[0]), month_matches[0]


def _filename_notice_identity(href: str) -> tuple[str, str] | None:
    path = unquote(urlparse(href).path)
    filename = path.rsplit("/", 1)[-1]
    if not re.search(r"\.(?:pdf|docx?|odt)$", filename, re.IGNORECASE):
        return None
    match = re.match(r"(\d{4,})(?:[-_\s]*([a-z]))?(?:[-_.\s]|$)", filename)
    if not match:
        return None
    return match.group(1), (match.group(2) or "").casefold()


def _visible_notice_identity(title: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*(\d{4,})(?:\s+([a-z]))?\s+\S+", title, re.I)
    if not match:
        return None
    return match.group(1), (match.group(2) or "").casefold()


def _media_route_identity(href: str) -> str | None:
    match = re.search(r"/notices/medias/fichiers/add/(\d+)/?$", urlparse(href).path)
    return f"commission-media:{match.group(1)}" if match else None


def notice_identity(title: str, href: str) -> str:
    """Derive a stable identity without using arbitrary title numbers."""
    visible = _visible_notice_identity(title)
    filename = _filename_notice_identity(href)
    if visible and filename and visible != filename:
        raise CommissionNoticeError(
            "conflicting visible and filename notice identifiers: "
            f"{visible!r} versus {filename!r}"
        )
    primary = visible or filename
    if primary:
        number, suffix = primary
        return f"commission:{number}{suffix}"
    media_identity = _media_route_identity(href)
    if media_identity:
        return media_identity
    raise CommissionNoticeError(
        f"notice listing has no stable Commission identifier: {title!r}"
    )


def _listed_date(title: str, year: int, month: int) -> str | None:
    visible = _visible_notice_identity(title)
    remainder = title
    if visible:
        remainder = re.sub(
            r"^\s*\d{4,}(?:\s+[a-z])?\s+",
            "",
            title,
            count=1,
            flags=re.I,
        )
    days = [
        int(match.group(1))
        for match in re.finditer(r"\b([0-3]?\d)(?:er)?\b", remainder, re.I)
        if 1 <= int(match.group(1)) <= 31
    ]
    if not days:
        return None
    try:
        return date(year, month, days[-1]).isoformat()
    except ValueError as error:
        raise CommissionNoticeError(
            f"invalid listed date in notice title: {title!r}"
        ) from error


def _category(title: str) -> str:
    match = re.match(
        r"^\s*\d{4,}(?:\s+[a-z])?\s+([^\s]+)",
        title,
        re.I,
    )
    if not match:
        return "unknown"
    return match.group(1)


def _listing_parties(
    title: str,
    listed_date: str | None,
) -> tuple[str | None, str | None]:
    institute_match: re.Match[str] | None = None
    institute: str | None = None
    for pattern, canonical in INSTITUTE_PATTERNS:
        match = re.search(pattern, title, re.I)
        if match and (
            institute_match is None or len(match.group(0)) > len(institute_match.group(0))
        ):
            institute_match = match
            institute = canonical
    if institute_match is None:
        return None, None

    commissioner = title[institute_match.end() :]
    commissioner = re.sub(
        r"\b(?:[0-3]?\d)(?:er)?\s+"
        r"(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
        r"septembre|octobre|novembre|d[ée]cembre)\b",
        " ",
        commissioner,
        flags=re.I,
    )
    if listed_date:
        day = int(listed_date[-2:])
        commissioner = re.sub(
            rf"\b0?{day}(?:er)?\b",
            " ",
            commissioner,
            flags=re.I,
        )
    commissioner = re.sub(r"\s+", " ", commissioner).strip(" -–—")
    return institute, commissioner or None


def parse_notice_index(
    page_html: str | bytes,
    *,
    index_url: str = INDEX_URL,
) -> list[dict[str, Any]]:
    """Parse stable listing records in deterministic document order."""
    _require_official_url(index_url)
    try:
        document = lxml_html.fromstring(page_html)
    except (TypeError, ValueError) as error:
        raise CommissionNoticeError("malformed Commission notice index HTML") from error

    anchors = document.xpath(
        "//a[contains(concat(' ', normalize-space(@class), ' '), "
        "' pdf_download ') and @href]"
    )
    if not anchors:
        anchors = document.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), "
            "' download-line ')]//a[@href]"
        )
    if not anchors:
        raise CommissionNoticeError(
            "official index yielded no recognizable notice records"
        )

    records: list[dict[str, Any]] = []
    by_identity: dict[str, dict[str, Any]] = {}
    for document_order, anchor in enumerate(anchors):
        title = re.sub(r"\s+", " ", anchor.text_content()).strip()
        href = str(anchor.get("href", "")).strip()
        if not title or not href:
            raise CommissionNoticeError("notice listing has blank title or URL")
        absolute_url = _require_official_url(urljoin(index_url, href))
        notice_id = notice_identity(title, absolute_url)
        year, month = _month_context(anchor)
        listed_date = _listed_date(title, year, month)
        institute, commissioner = _listing_parties(title, listed_date)
        record = {
            "notice_id": notice_id,
            "listed_date": listed_date,
            "category": _category(title),
            "title": title,
            "institute": institute,
            "commissioner": commissioner,
            "listed_url": absolute_url,
            "resolved_url": absolute_url,
            "document_order": document_order,
        }
        existing = by_identity.get(notice_id)
        if existing is None:
            by_identity[notice_id] = record
            records.append(record)
            continue
        comparable = {
            key: value
            for key, value in record.items()
            if key != "document_order"
        }
        prior_comparable = {
            key: value
            for key, value in existing.items()
            if key != "document_order"
        }
        if comparable != prior_comparable:
            raise CommissionNoticeError(
                f"conflicting duplicate listing rows for {notice_id}"
            )

    return records


def classify_listing(record: dict[str, Any]) -> ListingDecision:
    """Apply the first-stage eligibility gate to listing metadata."""
    category = normalize_text(str(record.get("category", "")))
    title = normalize_text(str(record.get("title", "")))
    if category != "pres":
        return ListingDecision(
            "excluded_non_voting",
            f"non-presidential category {record.get('category')!r}",
            False,
        )

    positive = [
        pattern
        for pattern in POSITIVE_LISTING_PATTERNS
        if re.search(pattern, title)
    ]
    if positive:
        return ListingDecision(
            "ambiguous",
            f"listing has voting-intention marker {positive[0]!r}",
            True,
            True,
        )

    negative = [
        pattern
        for pattern in NEGATIVE_LISTING_PATTERNS
        if re.search(pattern, title)
    ]
    if negative:
        return ListingDecision(
            "excluded_non_voting",
            f"listing is an explicit non-voting survey ({negative[0]!r})",
            False,
        )

    return ListingDecision(
        "ambiguous",
        "presidential listing requires document confirmation",
        True,
    )


def confirm_document_eligibility(text: str) -> tuple[bool, list[str], str]:
    """Require explicit 2027 presidential voting-intention evidence."""
    normalized = normalize_text(text)
    year_evidence = bool(
        re.search(
            r"\b(?:election\s+)?presidentielle(?:\s+de)?\s+2027\b",
            normalized,
        )
        or re.search(r"\bpr\s*2027\b", normalized)
        or re.search(
            r"\b2027\b.{0,80}\b(?:election\s+)?presidentielle\b",
            normalized,
        )
    )
    voting_evidence = bool(
        re.search(r"\bintentions?\s+de\s+vote\b", normalized)
        or re.search(
            r"\bsi\s+le\s+(?:1er|premier|2e|2eme|2nd|second)\s+tour\b"
            r".{0,180}\b(?:voteriez|vote)\b",
            normalized,
        )
    )

    rounds: list[str] = []
    if re.search(r"\b(?:1er|premier)\s+tour\b", normalized):
        rounds.append("first_round")
    if re.search(r"\b(?:2e|2eme|2nd|second)\s+tour\b", normalized):
        rounds.append("second_round")

    if year_evidence and voting_evidence:
        detail = "document confirms 2027 presidential voting intentions"
        if rounds:
            detail += f" ({', '.join(rounds)})"
        return True, rounds, detail
    missing = []
    if not year_evidence:
        missing.append("2027 presidential context")
    if not voting_evidence:
        missing.append("voting-intention language")
    return False, rounds, "document lacks " + " and ".join(missing)


def extract_document_text(document: FetchResult) -> str:
    """Extract auditable text without retaining the notice body."""
    content_type = document.content_type.casefold()
    if document.content.startswith(b"%PDF") or content_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(document.content))
            pages = [
                page.extract_text() or ""
                for page in reader.pages
            ]
        except Exception as error:
            raise CommissionNoticeError(
                f"could not extract official PDF text: {document.final_url}"
            ) from error
        text = "\n".join(pages).strip()
        if not text:
            raise CommissionNoticeError(
                f"official PDF has no extractable text: {document.final_url}"
            )
        return text
    if content_type in {"text/html", "application/xhtml+xml"}:
        try:
            from lxml import html as lxml_html

            root = lxml_html.fromstring(document.content.decode("utf-8"))
        except (TypeError, ValueError) as error:
            raise CommissionNoticeError(
                f"could not parse official HTML notice: {document.final_url}"
            ) from error
        return re.sub(r"\s+", " ", root.text_content()).strip()
    raise CommissionNoticeError(
        "unsupported official notice document type "
        f"{document.content_type!r}: {document.final_url}"
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def empty_registry() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "index_url": INDEX_URL,
        "notices": [],
    }


def load_registry(path: Path | str) -> dict[str, Any]:
    registry_path = Path(path)
    if not registry_path.exists():
        return empty_registry()
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CommissionNoticeError(
            f"could not read Commission notice registry: {registry_path}"
        ) from error
    validate_registry(payload)
    return payload


def _identity_sort_key(notice_id: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"commission:(\d+)([a-z]?)", notice_id)
    if match:
        return (0, int(match.group(1)), match.group(2))
    media = re.fullmatch(r"commission-media:(\d+)", notice_id)
    if media:
        return (1, int(media.group(1)), "")
    return (2, 0, notice_id)


def _iso_timestamp(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise CommissionNoticeError(f"{field} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CommissionNoticeError(f"{field} must be a UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CommissionNoticeError(f"{field} must use UTC")


def validate_registry(payload: Any) -> None:
    """Validate the tracked registry schema and deterministic ordering."""
    if not isinstance(payload, dict):
        raise CommissionNoticeError("notice registry must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CommissionNoticeError("notice registry schema_version must be 1.0")
    if payload.get("source") != SOURCE_NAME:
        raise CommissionNoticeError("notice registry has an unexpected source")
    if payload.get("index_url") != INDEX_URL:
        raise CommissionNoticeError("notice registry has an unexpected index_url")
    notices = payload.get("notices")
    if not isinstance(notices, list):
        raise CommissionNoticeError("notice registry notices must be a list")

    identities: set[str] = set()
    for index, notice in enumerate(notices):
        prefix = f"notice registry record {index}"
        if not isinstance(notice, dict):
            raise CommissionNoticeError(f"{prefix} must be an object")
        notice_id = notice.get("notice_id")
        if not isinstance(notice_id, str) or not re.fullmatch(
            r"commission:\d+[a-z]?|commission-media:\d+",
            notice_id,
        ):
            raise CommissionNoticeError(f"{prefix} has an invalid notice_id")
        if notice_id in identities:
            raise CommissionNoticeError(f"duplicate registry notice_id {notice_id}")
        identities.add(notice_id)
        if notice.get("classification") not in CLASSIFICATIONS:
            raise CommissionNoticeError(
                f"{notice_id} has an invalid classification"
            )
        reason = notice.get("classification_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise CommissionNoticeError(
                f"{notice_id} lacks a classification_reason"
            )
        for field in ("category", "title", "listed_url", "resolved_url"):
            if not isinstance(notice.get(field), str) or not notice[field].strip():
                raise CommissionNoticeError(f"{notice_id} lacks {field}")
        _require_official_url(notice["listed_url"])
        _require_official_url(notice["resolved_url"])
        listed_date = notice.get("listed_date")
        if listed_date is not None:
            try:
                if date.fromisoformat(listed_date).isoformat() != listed_date:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise CommissionNoticeError(
                    f"{notice_id} has an invalid listed_date"
                ) from error
        _iso_timestamp(
            notice.get("first_discovered_at"),
            f"{notice_id}.first_discovered_at",
        )
        digest = notice.get("content_sha256")
        if digest is not None and not (
            isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise CommissionNoticeError(
                f"{notice_id} has an invalid content_sha256"
            )
        rounds = notice.get("confirmed_rounds", [])
        if (
            not isinstance(rounds, list)
            or any(round_name not in ROUND_NAMES for round_name in rounds)
            or rounds != [
                round_name
                for round_name in ("first_round", "second_round")
                if round_name in rounds
            ]
        ):
            raise CommissionNoticeError(
                f"{notice_id} has invalid confirmed_rounds"
            )
        for nullable_text in ("institute", "commissioner", "parser"):
            value = notice.get(nullable_text)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise CommissionNoticeError(
                    f"{notice_id}.{nullable_text} must be text or null"
                )
        parser_name = notice.get("parser")
        if parser_name is not None:
            for field in (
                "pollster",
                "publication_date",
                "fieldwork_start",
                "fieldwork_end",
                "event_source_url",
            ):
                if not isinstance(notice.get(field), str) or not notice[field]:
                    raise CommissionNoticeError(
                        f"{notice_id} supported parser record lacks {field}"
                    )
            for field in (
                "listed_date",
                "publication_date",
                "fieldwork_start",
                "fieldwork_end",
            ):
                value = notice.get(field)
                if value is not None:
                    try:
                        if date.fromisoformat(value).isoformat() != value:
                            raise ValueError
                    except (TypeError, ValueError) as error:
                        raise CommissionNoticeError(
                            f"{notice_id} has an invalid {field}"
                        ) from error
            if (
                isinstance(notice.get("sample_size"), bool)
                or not isinstance(notice.get("sample_size"), int)
                or notice["sample_size"] < 1
                or isinstance(notice.get("expected_first_round_events"), bool)
                or not isinstance(notice.get("expected_first_round_events"), int)
                or notice["expected_first_round_events"] < 1
            ):
                raise CommissionNoticeError(
                    f"{notice_id} has invalid supported-parser counts"
                )
            _require_official_url(notice["event_source_url"])
            poll_commissioner = notice.get("poll_commissioner")
            if poll_commissioner is not None and (
                not isinstance(poll_commissioner, str)
                or not poll_commissioner.strip()
            ):
                raise CommissionNoticeError(
                    f"{notice_id}.poll_commissioner must be text or null"
                )
        try:
            validate_notice_coverage(
                notice,
                allow_missing_legacy_coverage=True,
            )
        except CommissionCoverageError as error:
            raise CommissionNoticeError(str(error)) from error

    expected_order = sorted(
        (notice["notice_id"] for notice in notices),
        key=_identity_sort_key,
        reverse=True,
    )
    actual_order = [notice["notice_id"] for notice in notices]
    if actual_order != expected_order:
        raise CommissionNoticeError(
            "notice registry records are not in deterministic identity order"
        )


def _merge_listing(
    listing: dict[str, Any],
    previous: dict[str, Any] | None,
    discovered_at: str,
) -> dict[str, Any]:
    record = dict(previous or {})
    for key in (
        "notice_id",
        "listed_date",
        "category",
        "title",
        "institute",
        "commissioner",
        "listed_url",
        "resolved_url",
    ):
        value = listing.get(key)
        if value is not None or key not in record:
            record[key] = value
    record.setdefault("classification", "ambiguous")
    record.setdefault(
        "classification_reason",
        "presidential listing requires document confirmation",
    )
    record.setdefault("first_discovered_at", discovered_at)
    record.setdefault("content_sha256", None)
    record.setdefault("confirmed_rounds", [])
    record.pop("document_order", None)
    return record


def discover_registry(
    existing: dict[str, Any],
    *,
    fetch: FetchFunction = fetch_official_url,
    discovered_at: str | None = None,
) -> DiscoveryResult:
    """Fetch, parse, classify, confirm, and merge the current official index."""
    validate_registry(existing)
    timestamp = discovered_at or _now_utc()
    _iso_timestamp(timestamp, "discovered_at")

    index_response = fetch(INDEX_URL, "GET")
    _require_official_url(index_response.final_url)
    listings = parse_notice_index(
        index_response.content,
        index_url=index_response.final_url,
    )
    previous_by_id = {
        notice["notice_id"]: notice
        for notice in existing["notices"]
    }
    merged_by_id = {
        notice_id: dict(notice)
        for notice_id, notice in previous_by_id.items()
    }
    diagnostics: list[str] = []

    for listing in listings:
        decision = classify_listing(listing)
        if normalize_text(str(listing["category"])) != "pres":
            continue
        notice_id = listing["notice_id"]
        previous = previous_by_id.get(notice_id)
        record = _merge_listing(listing, previous, timestamp)

        if not decision.inspect_document:
            record["classification"] = decision.classification
            record["classification_reason"] = decision.reason

            # An excluded listing does not need another network request.
            # Preserve a previously resolved official URL when possible;
            # otherwise the validated listed URL is sufficient provenance.
            if (
                previous
                and previous.get("listed_url") == record["listed_url"]
                and previous.get("resolved_url")
            ):
                record["resolved_url"] = _require_official_url(
                    previous["resolved_url"]
                )
            else:
                record["resolved_url"] = _require_official_url(
                    record["listed_url"]
                )
                diagnostics.append(
                    f"{notice_id}: excluded notice URL was not fetched; "
                    "using the validated listed URL"
                )

            merged_by_id[notice_id] = record
            continue

        try:
            document = fetch(record["listed_url"], "GET")
            record["resolved_url"] = _require_official_url(
                document.final_url
            )
            record["content_sha256"] = hashlib.sha256(document.content).hexdigest()
            extracted_text = extract_document_text(document)
            eligible, rounds, document_reason = confirm_document_eligibility(
                extracted_text
            )
        except Exception as error:
            if (
                previous
                and previous.get("classification") == "eligible"
                and previous.get("parser")
            ):
                raise CommissionNoticeError(
                    f"{notice_id}: existing eligible notice could not be fetched"
                ) from error
            if decision.strongly_eligible:
                if previous and previous.get("classification") == "eligible":
                    record["classification"] = previous["classification"]
                    record["classification_reason"] = previous[
                        "classification_reason"
                    ]
                    record["confirmed_rounds"] = previous.get(
                        "confirmed_rounds",
                        [],
                    )
                    diagnostics.append(
                        f"{notice_id}: retained prior eligible classification "
                        "because current document information was insufficient"
                    )
                    merged_by_id[notice_id] = record
                    continue
                record["classification"] = "unsupported"
                record["classification_reason"] = (
                    "listing indicates voting intentions but document inspection "
                    f"is unsupported: {error}"
                )
                record["confirmed_rounds"] = []
                diagnostics.append(
                    f"{notice_id}: strongly eligible notice is unsupported: {error}"
                )
                merged_by_id[notice_id] = record
                continue
            raise CommissionNoticeError(
                f"{notice_id}: ambiguous notice could not be inspected"
            ) from error

        record["confirmed_rounds"] = rounds
        if eligible:
            record["classification"] = "eligible"
            record["classification_reason"] = document_reason
        elif decision.strongly_eligible:
            if previous and previous.get("classification") == "eligible":
                record["classification"] = previous["classification"]
                record["classification_reason"] = previous[
                    "classification_reason"
                ]
                record["confirmed_rounds"] = previous.get(
                    "confirmed_rounds",
                    [],
                )
                diagnostics.append(
                    f"{notice_id}: retained prior eligible classification "
                    "because current evidence did not support a downgrade"
                )
            else:
                record["classification"] = "unsupported"
                record["classification_reason"] = (
                    f"{decision.reason}; {document_reason}"
                )
                diagnostics.append(
                    f"{notice_id}: strong listing evidence was not confirmed"
                )
        else:
            record["classification"] = "excluded_non_voting"
            record["classification_reason"] = document_reason
        merged_by_id[notice_id] = record

    for notice in merged_by_id.values():
        synchronize_notice_coverage(notice)

    merged = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "index_url": INDEX_URL,
        "notices": sorted(
            merged_by_id.values(),
            key=lambda notice: _identity_sort_key(notice["notice_id"]),
            reverse=True,
        ),
    }
    validate_registry(merged)
    return DiscoveryResult(merged, diagnostics)


def atomic_write_registry(path: Path | str, payload: dict[str, Any]) -> bool:
    """Atomically write only when the registry bytes have changed."""
    validate_registry(payload)
    destination = Path(path)
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    try:
        if destination.read_bytes() == serialized:
            return False
    except FileNotFoundError:
        pass

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return True


def registry_event_notices(
    registry: dict[str, Any],
) -> Iterable[dict[str, Any]]:
    """Return supported eligible records in registry order."""
    validate_registry(registry)
    return (
        notice
        for notice in registry["notices"]
        if notice["classification"] == "eligible" and notice.get("parser")
    )
