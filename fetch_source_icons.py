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
MAX_POLICY_BYTES = 2_000_000
MAX_SURFACE_BYTES = 20_000_000

# Authoritative organisation origins. Icons are still discovered and
# downloaded automatically from each site's declared icon metadata.
POLLSTER_HOMEPAGES = {
    "Elabe": "https://elabe.fr/",
    "Verian": "https://www.veriangroup.com/fr/",
    "OpinionWay": "https://www.opinion-way.com/",
    "Ifop": "https://www.ifop.com/",
    "Harris Interactive": "https://harris-interactive.fr/",
}

# Selected discovery publishers whose icons are required on prominent
# dashboard surfaces but which are not direct news-wire feed targets.
PRIORITY_DISCOVERY_PUBLISHER_HOMEPAGES = {
    "Le Figaro": "https://www.lefigaro.fr/",
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


def common_origin_icon_candidates(
    homepage_url: str,
) -> list[dict[str, str]]:
    """Return standard same-origin icon locations."""

    parsed = urlsplit(homepage_url)

    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError(
            f"Invalid HTTPS homepage for icon fallback: {homepage_url}"
        )

    origin = f"https://{parsed.netloc}/"

    return [
        {
            "href": urljoin(
                origin,
                "/apple-touch-icon.png",
            ),
            "rel": "fallback apple-touch-icon",
            "sizes": "180x180",
            "type": "image/png",
        },
        {
            "href": urljoin(
                origin,
                "/favicon.ico",
            ),
            "rel": "fallback icon",
            "sizes": "",
            "type": "image/x-icon",
        },
    ]


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

    candidates.extend(
        common_origin_icon_candidates(final_homepage)
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



def normalize_publisher_name(value: str) -> str:
    """Return a stable comparison key for publisher labels."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_hostname(value: str) -> str:
    """Normalize a hostname or HTTPS URL for origin comparison."""

    text = str(value or "").strip()

    if "://" in text:
        hostname = urlsplit(text).hostname or ""
    else:
        hostname = text.split("/", 1)[0].split(":", 1)[0]

    hostname = hostname.casefold().strip(".")

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def load_bounded_json(
    path: Path,
    *,
    maximum_bytes: int,
) -> Any:
    """Read a bounded JSON file."""

    raw = path.read_bytes()

    if len(raw) > maximum_bytes:
        raise RuntimeError(
            f"{path} exceeds {maximum_bytes} bytes"
        )

    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Could not parse {path}: {error}"
        ) from error


def publisher_policy_targets(
    policy_path: Path,
) -> list[dict[str, str]]:
    """Load enabled publisher origins from publisher_policy.json."""

    payload = load_bounded_json(
        policy_path,
        maximum_bytes=MAX_POLICY_BYTES,
    )

    if not isinstance(payload, dict):
        raise RuntimeError(
            "publisher policy must be a JSON object"
        )

    targets: list[dict[str, str]] = []

    for domain, record in payload.items():
        if not isinstance(domain, str) or not domain.strip():
            raise RuntimeError(
                "publisher policy contains an invalid domain"
            )

        if not isinstance(record, dict):
            raise RuntimeError(
                f"publisher policy record is not an object: {domain}"
            )

        if record.get("enabled") is not True:
            continue

        name = str(record.get("name") or "").strip()
        hostname = canonical_hostname(domain)

        if (
            not name
            or not hostname
            or "/" in domain
            or "://" in domain
        ):
            raise RuntimeError(
                f"invalid enabled publisher policy record: {domain}"
            )

        targets.append(
            {
                "name": name,
                "feed_url": f"https://{hostname}/",
                "entity_type": "publisher",
                "domain": hostname,
            }
        )

    return targets


def walk_json_records(value: Any):
    """Yield every object contained in a JSON value."""

    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from walk_json_records(child)

    elif isinstance(value, list):
        for child in value:
            yield from walk_json_records(child)


def surface_icon_requests(
    surface_paths: list[Path],
) -> list[dict[str, str]]:
    """Extract icon requests from public dashboard payloads."""

    requests: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for path in surface_paths:
        if not path.exists():
            continue

        payload = load_bounded_json(
            path,
            maximum_bytes=MAX_SURFACE_BYTES,
        )

        for record in walk_json_records(payload):
            icon_key = str(
                record.get("source_icon_key") or ""
            ).strip()

            if not icon_key:
                continue

            primary_source = record.get("primary_source")
            primary_name = ""
            primary_url = ""

            if isinstance(primary_source, dict):
                primary_name = str(
                    primary_source.get("name") or ""
                ).strip()
                primary_url = str(
                    primary_source.get("url") or ""
                ).strip()

            identity = (
                normalize_publisher_name(icon_key),
                normalize_publisher_name(primary_name),
                canonical_hostname(primary_url),
            )

            if identity in seen:
                continue

            seen.add(identity)

            requests.append(
                {
                    "icon_key": icon_key,
                    "primary_name": primary_name,
                    "primary_url": primary_url,
                }
            )

    return requests


def dynamic_surface_targets(
    *,
    policy_path: Path,
    surface_paths: list[Path],
) -> list[dict[str, str]]:
    """Resolve surfaced publishers to enabled policy origins."""

    policy_targets = publisher_policy_targets(policy_path)

    by_name: dict[str, list[dict[str, str]]] = {}
    by_domain: dict[str, dict[str, str]] = {}

    for target in policy_targets:
        name_key = normalize_publisher_name(target["name"])
        by_name.setdefault(name_key, []).append(target)

        domain = target["domain"]

        if (
            domain in by_domain
            and by_domain[domain]["name"] != target["name"]
        ):
            raise RuntimeError(
                f"conflicting publisher policy domain: {domain}"
            )

        by_domain[domain] = target

    resolved: dict[str, dict[str, str]] = {}

    for request in surface_icon_requests(surface_paths):
        candidates: list[dict[str, str]] = []

        for label in (
            request["icon_key"],
            request["primary_name"],
        ):
            key = normalize_publisher_name(label)

            if not key:
                continue

            matches = by_name.get(key, [])

            if len(matches) > 1:
                raise RuntimeError(
                    f"ambiguous publisher policy name: {label}"
                )

            candidates.extend(matches)

        request_domain = canonical_hostname(
            request["primary_url"]
        )

        if request_domain in by_domain:
            candidates.append(by_domain[request_domain])

        unique_candidates = {
            (
                candidate["name"],
                candidate["domain"],
            ): candidate
            for candidate in candidates
        }

        if not unique_candidates:
            print(
                "UNRESOLVED "
                f"{request['icon_key']}: "
                "no enabled publisher-policy match"
            )
            continue

        domains = {
            candidate["domain"]
            for candidate in unique_candidates.values()
        }

        if len(domains) != 1:
            raise RuntimeError(
                "conflicting publisher resolution for "
                f"{request['icon_key']}: "
                + ", ".join(sorted(domains))
            )

        target = next(
            iter(unique_candidates.values())
        )

        resolved[target["name"]] = {
            "name": target["name"],
            "feed_url": target["feed_url"],
            "entity_type": "publisher",
        }

    return sorted(
        resolved.values(),
        key=lambda target: normalize_publisher_name(
            target["name"]
        ),
    )


def merge_unique_icon_target(
    targets: list[dict[str, str]],
    seen: dict[str, dict[str, str]],
    target: dict[str, str],
) -> None:
    """Add one target, rejecting conflicting same-name origins."""

    name = str(target.get("name") or "").strip()
    feed_url = str(target.get("feed_url") or "").strip()
    entity_type = str(
        target.get("entity_type") or ""
    ).strip()

    if not name or not feed_url or not entity_type:
        raise RuntimeError(
            "source-icon target is missing required fields"
        )

    key = normalize_publisher_name(name)
    previous = seen.get(key)

    if previous is not None:
        previous_host = canonical_hostname(
            previous["feed_url"]
        )
        current_host = canonical_hostname(feed_url)

        if previous_host != current_host:
            raise RuntimeError(
                "conflicting source-icon targets for "
                f"{name}: {previous_host} versus {current_host}"
            )

        return

    normalized = {
        "name": name,
        "feed_url": feed_url,
        "entity_type": entity_type,
    }

    seen[key] = normalized
    targets.append(normalized)


def configured_icon_targets(
    *,
    publisher_policy_path: Path | None = None,
    surface_paths: list[Path] | None = None,
) -> list[dict[str, str]]:
    """Return configured and dynamically surfaced icon targets."""

    targets: list[dict[str, str]] = []
    seen: dict[str, dict[str, str]] = {}

    for source in SOURCES:
        merge_unique_icon_target(
            targets,
            seen,
            {
                "name": source["name"],
                "feed_url": source["feed_url"],
                "entity_type": "publisher",
            },
        )

    for publisher, homepage in (
        PRIORITY_DISCOVERY_PUBLISHER_HOMEPAGES.items()
    ):
        merge_unique_icon_target(
            targets,
            seen,
            {
                "name": publisher,
                "feed_url": homepage,
                "entity_type": "publisher",
            },
        )

    for pollster, homepage in POLLSTER_HOMEPAGES.items():
        merge_unique_icon_target(
            targets,
            seen,
            {
                "name": pollster,
                "feed_url": homepage,
                "entity_type": "pollster",
            },
        )

    if publisher_policy_path is not None:
        for target in dynamic_surface_targets(
            policy_path=publisher_policy_path,
            surface_paths=surface_paths or [],
        ):
            merge_unique_icon_target(
                targets,
                seen,
                target,
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
    errors: list[str] = []

    try:
        candidates = discover_icon_candidates(homepage_url)
    except Exception as error:
        errors.append(
            f"{homepage_url}: "
            f"{type(error).__name__}: {error}"
        )
        candidates = common_origin_icon_candidates(
            homepage_url
        )

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


def cached_record_matches_target(
    record: dict[str, Any] | None,
    target: dict[str, str],
    repository_root: Path,
) -> bool:
    """Require a valid cache from the same publisher origin."""

    if not valid_cached_record(record, repository_root):
        return False

    cached_host = canonical_hostname(
        str(record.get("homepage_url") or "")
    )
    target_host = canonical_hostname(
        homepage_from_feed(target["feed_url"])
    )

    return cached_host == target_host


def build_icon_records(
    *,
    targets: list[dict[str, str]],
    existing: dict[str, dict[str, Any]],
    icons_dir: Path,
    repository_root: Path,
    refresh: bool,
    retry_errors: bool,
) -> list[dict[str, Any]]:
    """Build records while preserving valid historical icon caches."""

    records: list[dict[str, Any]] = []
    targeted_names: set[str] = set()

    for target in targets:
        publisher = target["name"]
        entity_type = target["entity_type"]
        targeted_names.add(publisher)

        existing_record = existing.get(publisher)

        if (
            not refresh
            and cached_record_matches_target(
                existing_record,
                target,
                repository_root,
            )
        ):
            cached_record = dict(existing_record)
            cached_record["entity_type"] = entity_type
            records.append(cached_record)
            print(
                f"CACHED  {publisher}: "
                f"{cached_record['path']}"
            )
            continue

        if (
            not refresh
            and not retry_errors
            and isinstance(existing_record, dict)
            and existing_record.get("status") == "error"
            and canonical_hostname(
                str(
                    existing_record.get("homepage_url")
                    or ""
                )
            )
            == canonical_hostname(
                homepage_from_feed(target["feed_url"])
            )
        ):
            retained_error = dict(existing_record)
            retained_error["entity_type"] = entity_type
            records.append(retained_error)
            print(
                f"DEFERRED {publisher}: prior failure retained"
            )
            continue

        try:
            record = retrieve_source_icon(
                publisher=publisher,
                feed_url=target["feed_url"],
                icons_dir=icons_dir,
                repository_root=repository_root,
            )
        except Exception as error:
            try:
                homepage_url = homepage_from_feed(
                    target["feed_url"]
                )
            except Exception:
                homepage_url = None

            record = {
                "publisher": publisher,
                "status": "error",
                "homepage_url": homepage_url,
                "icon_url": None,
                "path": None,
                "mime_type": None,
                "retrieved_at": utc_now_text(),
                "error": (
                    f"{type(error).__name__}: {error}"
                ),
            }

        record["entity_type"] = entity_type
        records.append(record)

        if record["status"] == "ok":
            print(f"FETCHED {publisher}: {record['path']}")
        else:
            print(f"FAILED  {publisher}: {record['error']}")

    # Never delete a previously successful icon merely because its
    # publisher temporarily disappears from the current 14-day surface.
    for publisher in sorted(
        existing,
        key=normalize_publisher_name,
    ):
        if publisher in targeted_names:
            continue

        record = existing[publisher]

        if not valid_cached_record(
            record,
            repository_root,
        ):
            continue

        retained = dict(record)
        retained.setdefault("entity_type", "publisher")
        records.append(retained)
        print(f"RETAINED {publisher}: {retained['path']}")

    records.sort(
        key=lambda record: (
            str(record.get("entity_type") or ""),
            normalize_publisher_name(
                str(record.get("publisher") or "")
            ),
        )
    )

    return records


def manifest_projection(payload: Any) -> Any:
    """Remove timestamps that do not represent icon-content change."""

    if isinstance(payload, dict):
        return {
            key: manifest_projection(value)
            for key, value in payload.items()
            if key not in {
                "generated_at",
                "retrieved_at",
            }
        }

    if isinstance(payload, list):
        return [
            manifest_projection(value)
            for value in payload
        ]

    return payload


def write_manifest_if_changed(
    *,
    output_path: Path,
    payload: dict[str, Any],
) -> bool:
    """Atomically write only substantive manifest changes."""

    existing_payload: Any = None

    if output_path.exists():
        try:
            existing_payload = json.loads(
                output_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            existing_payload = None

    if (
        existing_payload is not None
        and manifest_projection(existing_payload)
        == manifest_projection(payload)
    ):
        print("UNCHANGED source-icons manifest")
        return False

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
    return True


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
        "--publisher-policy",
        type=Path,
        default=Path("publisher_policy.json"),
    )
    parser.add_argument(
        "--surface-data",
        type=Path,
        action="append",
        default=[],
        help=(
            "Public JSON payload used to discover surfaced "
            "source_icon_key values. May be repeated."
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Redownload icons even when a valid local cache exists."
        ),
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help=(
            "Retry existing failed targets. Missing targets are "
            "always attempted."
        ),
    )

    arguments = parser.parse_args()

    repository_root = Path.cwd().resolve()
    output_path = arguments.output.resolve()
    icons_dir = arguments.icons_dir.resolve()
    policy_path = arguments.publisher_policy.resolve()

    surface_paths = [
        path.resolve()
        for path in arguments.surface_data
    ]

    if not surface_paths:
        surface_paths = [
            path.resolve()
            for path in (
                Path("recent_changes.json"),
                Path("news_wire.json"),
            )
            if path.exists()
        ]

    icons_dir.mkdir(parents=True, exist_ok=True)

    existing = load_existing_manifest(output_path)

    targets = configured_icon_targets(
        publisher_policy_path=policy_path,
        surface_paths=surface_paths,
    )

    records = build_icon_records(
        targets=targets,
        existing=existing,
        icons_dir=icons_dir,
        repository_root=repository_root,
        refresh=arguments.refresh,
        retry_errors=arguments.retry_errors,
    )

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_text(),
        "method": (
            "publisher_declared_icon_or_manifest_icon_with_"
            "favicon_fallback_and_dynamic_surface_discovery"
        ),
        "sources": records,
    }

    expected_publishers = {
        str(record.get("publisher") or "")
        for record in records
    }

    validate_manifest(
        payload,
        repository_root,
        expected_publishers,
    )

    changed = write_manifest_if_changed(
        output_path=output_path,
        payload=payload,
    )

    successful = sum(
        record["status"] == "ok"
        for record in records
    )

    print()
    print("Source icon cache generated.")
    print(f"Successful icons: {successful}/{len(records)}")
    print(f"Manifest: {output_path}")
    print(f"Icon directory: {icons_dir}")
    print(f"Substantive manifest change: {changed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
