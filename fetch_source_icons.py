#!/usr/bin/env python3
"""Automatically discover and locally cache monitored publisher site icons."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from fetch_news_wire import SOURCES


USER_AGENT = "Mozilla/5.0 FR27SignalLab-source-icons/1.0"
MAX_HTML_BYTES = 2_000_000
MAX_MANIFEST_BYTES = 500_000
MAX_ICON_BYTES = 1_000_000
MIN_ICON_BYTES = 32

# Authoritative organisation origins. Icons are still discovered and
# downloaded automatically from each site's declared icon metadata.
POLLSTER_HOMEPAGES = {
    "Elabe": "https://elabe.fr/",
    "Verian": "https://www.veriangroup.com/fr/",
    "OpinionWay": "https://www.opinion-way.com/",
    "Ifop": "https://www.ifop.com/",
    "Harris Interactive": "https://harris-interactive.fr/",
}

MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
}


class IconLinkParser(HTMLParser):
    """Collect icon and manifest links declared by a publisher homepage."""

    def __init__(self) -> None:
        super().__init__()
        self.icons: list[dict[str, str]] = []
        self.manifests: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "link":
            return

        attributes = {
            str(name).lower(): str(value or "").strip()
            for name, value in attrs
        }

        href = attributes.get("href", "")
        if not href:
            return

        rel_tokens = {
            token.lower()
            for token in attributes.get("rel", "").split()
            if token
        }

        if "manifest" in rel_tokens:
            self.manifests.append(href)

        if (
            "icon" in rel_tokens
            or "apple-touch-icon" in rel_tokens
            or "apple-touch-icon-precomposed" in rel_tokens
        ):
            self.icons.append(
                {
                    "href": href,
                    "rel": " ".join(sorted(rel_tokens)),
                    "sizes": attributes.get("sizes", ""),
                    "type": attributes.get("type", ""),
                }
            )


def utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "publisher"


def homepage_from_feed(feed_url: str) -> str:
    parsed = urlsplit(feed_url)

    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError(
            f"Configured feed does not use a valid HTTPS origin: {feed_url}"
        )

    return f"https://{parsed.netloc}/"


def request_bytes(
    url: str,
    *,
    accept: str,
    maximum_bytes: int,
    timeout: int = 25,
) -> tuple[bytes, str, str]:
    parsed = urlsplit(url)

    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError(f"Refusing non-HTTPS URL: {url}")

    request = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
        },
    )

    with urlopen(
        request,
        timeout=timeout,
        context=ssl.create_default_context(),
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                f"{url} returned HTTP {response.status}"
            )

        final_url = response.geturl()

        if urlsplit(final_url).scheme != "https":
            raise RuntimeError(
                f"Refusing redirect to non-HTTPS URL: {final_url}"
            )

        content = response.read(maximum_bytes + 1)

        if len(content) > maximum_bytes:
            raise RuntimeError(
                f"Response exceeded {maximum_bytes} bytes: {final_url}"
            )

        content_type = (
            response.headers.get_content_type()
            or ""
        ).lower()

        return content, final_url, content_type


def parse_size_score(value: str) -> int:
    if not value:
        return 0

    if value.strip().lower() == "any":
        return 10_000

    scores: list[int] = []

    for token in value.lower().split():
        match = re.fullmatch(r"(\d+)x(\d+)", token)

        if match:
            width, height = map(int, match.groups())
            scores.append(min(width, height))

    return max(scores, default=0)


def candidate_score(candidate: dict[str, str]) -> tuple[int, int, int]:
    declared_type = candidate.get("type", "").lower()
    href = candidate.get("href", "").lower()
    rel = candidate.get("rel", "").lower()

    format_score = 0

    if declared_type in MIME_EXTENSIONS:
        format_score = 4
    elif any(
        href.split("?", 1)[0].endswith(extension)
        for extension in (".png", ".ico", ".webp", ".jpg", ".jpeg")
    ):
        format_score = 3

    relation_score = 0

    if "apple-touch-icon" in rel:
        relation_score = 3
    elif "icon" in rel:
        relation_score = 2
    elif "manifest" in rel:
        relation_score = 1

    return (
        format_score,
        parse_size_score(candidate.get("sizes", "")),
        relation_score,
    )


def detect_icon_extension(
    content: bytes,
    content_type: str,
) -> tuple[str, str] | None:
    normalized_type = content_type.split(";", 1)[0].strip().lower()

    if normalized_type in MIME_EXTENSIONS:
        return normalized_type, MIME_EXTENSIONS[normalized_type]

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"

    if content.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon", ".ico"

    if (
        len(content) >= 12
        and content[:4] == b"RIFF"
        and content[8:12] == b"WEBP"
    ):
        return "image/webp", ".webp"

    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"

    return None


def manifest_icon_candidates(
    manifest_url: str,
) -> list[dict[str, str]]:
    try:
        raw, final_url, _content_type = request_bytes(
            manifest_url,
            accept="application/manifest+json, application/json;q=0.9",
            maximum_bytes=MAX_MANIFEST_BYTES,
        )

        payload = json.loads(raw.decode("utf-8-sig"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RuntimeError,
    ):
        return []

    icons = payload.get("icons")

    if not isinstance(icons, list):
        return []

    candidates: list[dict[str, str]] = []

    for icon in icons:
        if not isinstance(icon, dict):
            continue

        source = str(icon.get("src") or "").strip()

        if not source:
            continue

        candidates.append(
            {
                "href": urljoin(final_url, source),
                "rel": "manifest icon",
                "sizes": str(icon.get("sizes") or ""),
                "type": str(icon.get("type") or ""),
            }
        )

    return candidates


def discover_icon_candidates(
    homepage_url: str,
) -> list[dict[str, str]]:
    raw, final_homepage, _content_type = request_bytes(
        homepage_url,
        accept="text/html, application/xhtml+xml;q=0.9",
        maximum_bytes=MAX_HTML_BYTES,
    )

    parser = IconLinkParser()
    parser.feed(raw.decode("utf-8", errors="replace"))

    candidates: list[dict[str, str]] = []

    for candidate in parser.icons:
        candidates.append(
            {
                **candidate,
                "href": urljoin(
                    final_homepage,
                    candidate["href"],
                ),
            }
        )

    for manifest_reference in parser.manifests:
        manifest_url = urljoin(
            final_homepage,
            manifest_reference,
        )

        if urlsplit(manifest_url).scheme != "https":
            continue

        candidates.extend(
            manifest_icon_candidates(manifest_url)
        )

    candidates.append(
        {
            "href": urljoin(final_homepage, "/favicon.ico"),
            "rel": "fallback icon",
            "sizes": "",
            "type": "image/x-icon",
        }
    )

    deduplicated: dict[str, dict[str, str]] = {}

    for candidate in candidates:
        href = candidate.get("href", "")
        parsed = urlsplit(href)

        if parsed.scheme != "https" or not parsed.netloc:
            continue

        deduplicated.setdefault(href, candidate)

    return sorted(
        deduplicated.values(),
        key=candidate_score,
        reverse=True,
    )



def configured_icon_targets() -> list[dict[str, str]]:
    """Return monitored news publishers and supported polling institutes."""

    targets = [
        {
            "name": source["name"],
            "feed_url": source["feed_url"],
            "entity_type": "publisher",
        }
        for source in SOURCES
    ]

    targets.extend(
        {
            "name": pollster,
            "feed_url": homepage,
            "entity_type": "pollster",
        }
        for pollster, homepage in POLLSTER_HOMEPAGES.items()
    )

    return targets


def load_existing_manifest(
    output_path: Path,
) -> dict[str, dict[str, Any]]:
    if not output_path.exists():
        return {}

    try:
        payload = json.loads(
            output_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}

    source_records = payload.get("sources")

    if not isinstance(source_records, list):
        return {}

    return {
        str(record.get("publisher") or ""): record
        for record in source_records
        if isinstance(record, dict)
        and record.get("publisher")
    }


def valid_cached_record(
    record: dict[str, Any] | None,
    repository_root: Path,
) -> bool:
    if not isinstance(record, dict):
        return False

    if record.get("status") != "ok":
        return False

    relative_path = str(record.get("path") or "").strip()

    if not relative_path:
        return False

    cached_path = repository_root / relative_path

    return (
        cached_path.is_file()
        and cached_path.stat().st_size >= MIN_ICON_BYTES
    )


def retrieve_source_icon(
    *,
    publisher: str,
    feed_url: str,
    icons_dir: Path,
    repository_root: Path,
) -> dict[str, Any]:
    homepage_url = homepage_from_feed(feed_url)
    candidates = discover_icon_candidates(homepage_url)

    errors: list[str] = []

    for candidate in candidates:
        icon_url = candidate["href"]

        try:
            content, final_url, content_type = request_bytes(
                icon_url,
                accept=(
                    "image/png, image/x-icon, image/vnd.microsoft.icon, "
                    "image/webp, image/jpeg;q=0.9, */*;q=0.2"
                ),
                maximum_bytes=MAX_ICON_BYTES,
            )

            if len(content) < MIN_ICON_BYTES:
                raise RuntimeError(
                    "Icon response is empty or too small "
                    f"({len(content)} bytes)"
                )

            detected = detect_icon_extension(
                content,
                content_type,
            )

            if detected is None:
                raise RuntimeError(
                    "Unsupported or unrecognized image format"
                )

            mime_type, extension = detected
            filename = slugify(publisher) + extension
            destination = icons_dir / filename

            for stale_file in icons_dir.glob(
                slugify(publisher) + ".*"
            ):
                if stale_file != destination and stale_file.is_file():
                    stale_file.unlink()

            temporary = destination.with_suffix(
                destination.suffix + ".tmp"
            )

            temporary.write_bytes(content)
            temporary.replace(destination)

            relative_path = destination.relative_to(
                repository_root
            ).as_posix()

            return {
                "publisher": publisher,
                "status": "ok",
                "homepage_url": homepage_url,
                "icon_url": final_url,
                "path": relative_path,
                "mime_type": mime_type,
                "retrieved_at": utc_now_text(),
                "error": None,
            }

        except Exception as error:
            errors.append(
                f"{icon_url}: {type(error).__name__}: {error}"
            )

    return {
        "publisher": publisher,
        "status": "error",
        "homepage_url": homepage_url,
        "icon_url": None,
        "path": None,
        "mime_type": None,
        "retrieved_at": utc_now_text(),
        "error": " | ".join(errors[-3:]) or "No icon candidates found",
    }


def validate_manifest(
    payload: dict[str, Any],
    repository_root: Path,
    expected_publishers: set[str],
) -> None:
    sources = payload.get("sources")

    if not isinstance(sources, list):
        raise RuntimeError("source-icons sources must be a list")

    if len(sources) != len(expected_publishers):
        raise RuntimeError(
            "source-icons source count does not match configured targets"
        )

    publishers: set[str] = set()

    for source in sources:
        if not isinstance(source, dict):
            raise RuntimeError(
                "source-icons source record is not an object"
            )

        publisher = source.get("publisher")

        if not isinstance(publisher, str) or not publisher:
            raise RuntimeError(
                "source-icons source record has no publisher"
            )

        if publisher in publishers:
            raise RuntimeError(
                f"duplicate source-icons publisher: {publisher}"
            )

        publishers.add(publisher)

        if source.get("status") == "ok":
            relative_path = source.get("path")

            if (
                not isinstance(relative_path, str)
                or not relative_path
                or not (repository_root / relative_path).is_file()
            ):
                raise RuntimeError(
                    f"missing cached icon for {publisher}"
                )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("source_icons.json"),
    )

    parser.add_argument(
        "--icons-dir",
        type=Path,
        default=Path("assets/source-icons"),
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload icons even when a valid local cache exists.",
    )

    arguments = parser.parse_args()

    repository_root = Path.cwd().resolve()
    output_path = arguments.output.resolve()
    icons_dir = arguments.icons_dir.resolve()

    icons_dir.mkdir(parents=True, exist_ok=True)

    existing = load_existing_manifest(output_path)
    records: list[dict[str, Any]] = []
    targets = configured_icon_targets()

    for source in targets:
        publisher = source["name"]
        entity_type = source["entity_type"]
        existing_record = existing.get(publisher)

        if (
            not arguments.refresh
            and valid_cached_record(
                existing_record,
                repository_root,
            )
        ):
            cached_record = dict(existing_record)
            cached_record["entity_type"] = entity_type
            records.append(cached_record)
            print(f"CACHED  {publisher}: {cached_record['path']}")
            continue

        record = retrieve_source_icon(
            publisher=publisher,
            feed_url=source["feed_url"],
            icons_dir=icons_dir,
            repository_root=repository_root,
        )

        record["entity_type"] = entity_type
        records.append(record)

        if record["status"] == "ok":
            print(f"FETCHED {publisher}: {record['path']}")
        else:
            print(f"FAILED  {publisher}: {record['error']}")

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_text(),
        "method": (
            "publisher_declared_icon_or_manifest_icon_with_favicon_fallback"
        ),
        "sources": records,
    }

    validate_manifest(
        payload,
        repository_root,
        {target["name"] for target in targets},
    )

    temporary_output = output_path.with_suffix(
        output_path.suffix + ".tmp"
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

    temporary_output.replace(output_path)

    successful = sum(
        record["status"] == "ok"
        for record in records
    )

    print()
    print("Source icon cache generated.")
    print(f"Successful icons: {successful}/{len(records)}")
    print(f"Manifest: {output_path}")
    print(f"Icon directory: {icons_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
