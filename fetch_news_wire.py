#!/usr/bin/env python3
"""Build the FR27 Signal Lab election news wire from direct publisher RSS feeds."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import ssl
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


SOURCES = (
    {
        "name": "Public Sénat",
        "feed_url": "https://www.publicsenat.fr/feed",
    },
    {
        "name": "LCP",
        "feed_url": "https://lcp.fr/rss-actualites.xml",
    },
    {
        "name": "Franceinfo Politique",
        "feed_url": "https://www.franceinfo.fr/politique.rss",
    },
    {
        "name": "France 24 Français",
        "feed_url": "https://www.france24.com/fr/rss",
    },
    {
        "name": "RFI France",
        "feed_url": "https://www.rfi.fr/fr/france/rss",
    },
)

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "xtor",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

ELECTION_PATTERNS = (
    re.compile(r"\bpresidentielle(?:\s+francaise)?(?:\s+de)?\s+2027\b"),
    re.compile(r"\belection\s+presidentielle\b"),
    re.compile(r"\bprochaine\s+presidentielle\b"),
    re.compile(r"\bcourse\s+a\s+l\s+elysee\b"),
    re.compile(r"\belysee\s+2027\b"),
    re.compile(r"\bcandidat(?:e|ure)?\s+a\s+l\s+election\s+presidentielle\b"),
)


def normalize(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()

    if not text:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_feed_datetime(value: Any) -> datetime | None:
    text = clean_text(value)

    if not text:
        return None

    try:
        parsed = parsedate_to_datetime(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def canonical_url(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    parts = urlsplit(text)

    retained_query = [
        (key, query_value)
        for key, query_value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if key.lower() not in TRACKING_PARAMETERS
    ]

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower().removeprefix("www."),
            parts.path.rstrip("/"),
            urlencode(retained_query),
            "",
        )
    )


def request_bytes(url: str) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/xml, text/xml, */*;q=0.5"
            ),
            "User-Agent": "Mozilla/5.0 FR27SignalLab-news-wire/1.0",
        },
    )

    with urlopen(
        request,
        timeout=60,
        context=ssl.create_default_context(),
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                f"{url} returned HTTP {response.status}"
            )

        return response.read(), response.geturl()


def first_child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if local_name(child.tag) in names:
            if child.text and child.text.strip():
                return clean_text(child.text)

    return ""


def entry_link(element: ET.Element) -> str:
    for child in element:
        if local_name(child.tag) != "link":
            continue

        href = str(child.attrib.get("href") or "").strip()

        if href:
            relationship = str(
                child.attrib.get("rel") or "alternate"
            ).lower()

            if relationship in {"", "alternate"}:
                return href

        if child.text and child.text.strip():
            return child.text.strip()

    return ""


def parse_feed(
    raw: bytes,
    publisher: str,
    feed_url: str,
) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    entries: list[dict[str, Any]] = []

    for element in root.iter():
        if local_name(element.tag) not in {"item", "entry"}:
            continue

        headline = first_child_text(element, {"title"})
        url = entry_link(element)
        published_text = first_child_text(
            element,
            {"pubdate", "published", "updated", "date"},
        )
        published_at = parse_feed_datetime(published_text)

        if not headline or not url or published_at is None:
            continue

        entries.append(
            {
                "publisher": publisher,
                "feed_url": feed_url,
                "headline": headline,
                "url": url,
                "canonical_url": canonical_url(url),
                "published_at": published_at,
            }
        )

    if not entries:
        raise RuntimeError(
            f"{publisher} feed contained no usable dated entries"
        )

    return entries


def find_event_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    if isinstance(payload, dict):
        for key in ("polls", "events", "rows", "data"):
            value = payload.get(key)

            if isinstance(value, list):
                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

    raise RuntimeError(
        "Could not locate the poll-event list in polls.json"
    )


def recent_candidate_roster(
    polls_path: Path,
    generated_at: datetime,
    days: int = 183,
) -> tuple[list[str], str]:
    payload = json.loads(
        polls_path.read_text(encoding="utf-8")
    )
    events = find_event_list(payload)
    cutoff = generated_at.date() - timedelta(days=days)
    names: set[str] = set()

    for event in events:
        event_round = str(event.get("round") or "").strip()

        if event_round and event_round != "first_round":
            continue

        event_date = None

        for field in (
            "publication_date",
            "published_date",
            "fieldwork_end",
            "fieldwork_start",
        ):
            event_date = parse_iso_date(event.get(field))

            if event_date is not None:
                break

        if event_date is None or event_date < cutoff:
            continue

        candidates = event.get("candidates")

        if not isinstance(candidates, list):
            continue

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            name = str(candidate.get("name") or "").strip()

            if name:
                names.add(name)

    if not names:
        raise RuntimeError(
            "No candidates appeared in first-round polling "
            "during the previous six months"
        )

    return sorted(names), cutoff.isoformat()


def explicit_election_match(normalized_headline: str) -> bool:
    return any(
        pattern.search(normalized_headline)
        for pattern in ELECTION_PATTERNS
    )


def make_item_id(canonical: str, publisher: str, headline: str) -> str:
    identity = canonical or f"{publisher}|{headline}"

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:20]


def public_item(
    entry: dict[str, Any],
    candidates: list[str],
    explicit_election: bool,
) -> dict[str, Any]:
    return {
        "id": make_item_id(
            entry["canonical_url"],
            entry["publisher"],
            entry["headline"],
        ),
        "publisher": entry["publisher"],
        "published_at": (
            entry["published_at"]
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "headline": entry["headline"],
        "url": entry["url"],
        "explicit_election": explicit_election,
        "candidates": candidates,
    }


def validate_output(payload: dict[str, Any]) -> None:
    sources = payload.get("sources")
    election_news = payload.get("election_news")
    candidate_watch = payload.get("candidate_watch")

    if not isinstance(sources, list) or len(sources) != len(SOURCES):
        raise RuntimeError("Unexpected source-status structure")

    successful_sources = [
        source
        for source in sources
        if source.get("status") == "ok"
    ]

    if len(successful_sources) < 4:
        raise RuntimeError(
            f"Only {len(successful_sources)} publisher feeds succeeded"
        )

    for list_name, items in (
        ("election_news", election_news),
        ("candidate_watch", candidate_watch),
    ):
        if not isinstance(items, list):
            raise RuntimeError(f"{list_name} is not a list")

        ids: set[str] = set()

        for item in items:
            required = {
                "id",
                "publisher",
                "published_at",
                "headline",
                "url",
                "explicit_election",
                "candidates",
            }

            if set(item) != required:
                raise RuntimeError(
                    f"{list_name} item has unexpected fields"
                )

            if not item["headline"] or not item["publisher"]:
                raise RuntimeError(
                    f"{list_name} contains an empty headline or publisher"
                )

            if not str(item["url"]).startswith(("http://", "https://")):
                raise RuntimeError(
                    f"{list_name} contains an invalid URL"
                )

            if item["id"] in ids:
                raise RuntimeError(
                    f"{list_name} contains duplicate item ids"
                )

            ids.add(item["id"])

    if not election_news and not candidate_watch:
        raise RuntimeError(
            "The generated wire contains no matching news items"
        )


def build_wire(
    polls_path: Path,
    window_days: int,
    max_items: int,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    window_start = generated_at - timedelta(days=window_days)
    candidates, candidate_cutoff = recent_candidate_roster(
        polls_path,
        generated_at,
    )
    normalized_candidates = {
        candidate: normalize(candidate)
        for candidate in candidates
    }

    source_status: list[dict[str, Any]] = []
    all_entries: list[dict[str, Any]] = []

    for source in SOURCES:
        started_at = datetime.now(timezone.utc)

        try:
            raw, final_feed_url = request_bytes(source["feed_url"])
            entries = parse_feed(
                raw,
                source["name"],
                final_feed_url,
            )
            recent_entries = [
                entry
                for entry in entries
                if entry["published_at"] >= window_start
            ]
            latest = max(
                (
                    entry["published_at"]
                    for entry in entries
                ),
                default=None,
            )

            source_status.append(
                {
                    "name": source["name"],
                    "feed_url": final_feed_url,
                    "status": "ok",
                    "items_seen": len(entries),
                    "recent_items": len(recent_entries),
                    "latest_published_at": (
                        latest.isoformat().replace("+00:00", "Z")
                        if latest is not None
                        else None
                    ),
                    "error": None,
                }
            )
            all_entries.extend(recent_entries)
        except Exception as error:
            source_status.append(
                {
                    "name": source["name"],
                    "feed_url": source["feed_url"],
                    "status": "error",
                    "items_seen": 0,
                    "recent_items": 0,
                    "latest_published_at": None,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

        elapsed = (
            datetime.now(timezone.utc) - started_at
        ).total_seconds()

        source_status[-1]["response_seconds"] = round(elapsed, 2)

    deduplicated: dict[str, dict[str, Any]] = {}

    for entry in sorted(
        all_entries,
        key=lambda item: item["published_at"],
        reverse=True,
    ):
        key = (
            entry["canonical_url"]
            or normalize(entry["headline"])
        )

        if key not in deduplicated:
            deduplicated[key] = entry

    election_news: list[dict[str, Any]] = []
    candidate_watch: list[dict[str, Any]] = []

    for entry in deduplicated.values():
        normalized_headline = normalize(entry["headline"])
        matched_candidates = [
            candidate
            for candidate, normalized_name
            in normalized_candidates.items()
            if normalized_name in normalized_headline
        ]
        is_election_news = explicit_election_match(
            normalized_headline
        )
        item = public_item(
            entry,
            matched_candidates,
            is_election_news,
        )

        if is_election_news:
            election_news.append(item)

        if matched_candidates:
            candidate_watch.append(item)

    election_news.sort(
        key=lambda item: item["published_at"],
        reverse=True,
    )
    candidate_watch.sort(
        key=lambda item: item["published_at"],
        reverse=True,
    )

    election_news = election_news[:max_items]
    candidate_watch = candidate_watch[:max_items]

    payload = {
        "schema_version": 1,
        "generated_at": (
            generated_at.isoformat().replace("+00:00", "Z")
        ),
        "window_days": window_days,
        "candidate_roster": {
            "rule": (
                "Figures appearing in first-round polling "
                "during the previous six months"
            ),
            "cutoff_date": candidate_cutoff,
            "count": len(candidates),
            "names": candidates,
        },
        "sources": source_status,
        "counts": {
            "successful_sources": sum(
                source["status"] == "ok"
                for source in source_status
            ),
            "unique_recent_feed_items": len(deduplicated),
            "election_news": len(election_news),
            "candidate_watch": len(candidate_watch),
        },
        "election_news": election_news,
        "candidate_watch": candidate_watch,
    }

    validate_output(payload)

    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--polls",
        type=Path,
        default=Path("polls.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("news_wire.json"),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=60,
    )
    arguments = parser.parse_args()

    if arguments.window_days < 1:
        raise RuntimeError("--window-days must be positive")

    if arguments.max_items < 1:
        raise RuntimeError("--max-items must be positive")

    payload = build_wire(
        arguments.polls,
        arguments.window_days,
        arguments.max_items,
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_output = arguments.output.with_suffix(
        arguments.output.suffix + ".tmp"
    )

    temporary_output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary_output.replace(arguments.output)

    counts = payload["counts"]

    print("Election News Wire generated.")
    print(
        f"Candidate roster: "
        f"{payload['candidate_roster']['count']}"
    )
    print(
        f"Successful feeds: "
        f"{counts['successful_sources']}/{len(SOURCES)}"
    )
    print(
        f"Unique recent feed items: "
        f"{counts['unique_recent_feed_items']}"
    )
    print(
        f"Election News items: "
        f"{counts['election_news']}"
    )
    print(
        f"Candidate Watch items: "
        f"{counts['candidate_watch']}"
    )
    print(f"Output: {arguments.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())