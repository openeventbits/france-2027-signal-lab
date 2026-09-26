from __future__ import annotations

import argparse
import hashlib
import html as html_module
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from candidate_page_contract import project_candidate_route_index


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "route_registry.json"
POLL_MANIFEST_PATH = ROOT / "poll_pages_manifest.json"
CANDIDATE_REGISTRY_PATH = ROOT / "candidate_candidacy_status.json"

SCHEMA_VERSION = "1.0"
BASE_URL = "https://france2027.app"


class RouteRegistryError(ValueError):
    pass


def _load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())

    try:
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _validate_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise RouteRegistryError(
            f"Invalid effective date: {value!r}"
        )
    return value


def _canonical_url(path: str) -> str:
    if not path.startswith("/"):
        raise RouteRegistryError(
            f"Canonical route must begin with '/': {path!r}"
        )
    return f"{BASE_URL}{path}"


def _source_file(path: str) -> Path:
    if path == "/":
        return Path("index.html")

    return Path(path.strip("/")) / "index.html"


def _extract_title(document: str) -> str:
    match = re.search(
        r"<title>(.*?)</title>",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match is None:
        raise RouteRegistryError(
            "Registered page has no <title>."
        )

    title = html_module.unescape(
        re.sub(r"\s+", " ", match.group(1)).strip()
    )

    if not title:
        raise RouteRegistryError(
            "Registered page has an empty <title>."
        )

    return title


def _extract_description(document: str) -> str:
    patterns = (
        r'<meta\s+name="description"\s+content="([^"]+)"',
        r'<meta\s+content="([^"]+)"\s+name="description"',
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match is not None:
            description = html_module.unescape(
                re.sub(r"\s+", " ", match.group(1)).strip()
            )

            if description:
                return description

    raise RouteRegistryError(
        "Registered page has no non-empty meta description."
    )


def _validate_canonical(
    document: str,
    expected_url: str,
    *,
    source_file: Path,
) -> None:
    pattern = re.compile(
        r'<link\s+rel="canonical"\s+href="([^"]+)"',
        flags=re.IGNORECASE,
    )

    matches = pattern.findall(document)

    if matches != [expected_url]:
        raise RouteRegistryError(
            f"{source_file.as_posix()}: canonical mismatch; "
            f"expected exactly {expected_url!r}, got {matches!r}"
        )


def _semantic_html_bytes(data: bytes) -> bytes:
    """
    Hash meaningful page content without global HUD counters whose
    updates should not make every historical route appear modified.
    """

    text = data.decode("utf-8")

    patterns = (
        (
            r'(<strong\s+id="fr27-hud-polls-value">)'
            r'.*?'
            r'(</strong>)',
            r"\g<1>__POLL_COUNT__\g<2>",
        ),
        (
            r'(<strong\s+id="fr27-hud-domains-value">)'
            r'.*?'
            r'(</strong>)',
            r"\g<1>__DOMAIN_COUNT__\g<2>",
        ),
    )

    for pattern, replacement in patterns:
        text = re.sub(
            pattern,
            replacement,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    text = re.sub(
        r'https://france2027\.app/assets/og-cover\.png'
        r'(?:\?v=[^"&<\s]+)?',
        (
            "https://france2027.app/assets/"
            "og-cover.png?v=__OG_VERSION__"
        ),
        text,
        flags=re.IGNORECASE,
    )

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return text.encode("utf-8")


def _content_hash(path: Path) -> str:
    return hashlib.sha256(
        _semantic_html_bytes(path.read_bytes())
    ).hexdigest()


def _semantic_json_bytes(path: Path) -> bytes:
    """
    Canonicalize JSON so formatting, indentation and object-key ordering
    do not alter a route's semantic content hash.
    """

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _semantic_text_bytes(path: Path) -> bytes:
    """
    Normalize line endings for semantic text dependencies.
    """

    text = path.read_text(encoding="utf-8")

    text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    return text.encode("utf-8")


def _polling_hub_content_hash(
    *,
    root: Path,
    source_path: Path,
) -> str:
    """
    Polling Lab hub content is rendered from both its HTML shell and
    published explorer/runtime dependencies.

    CSS is intentionally excluded: cosmetic changes must not advance
    sitemap lastmod.
    """

    explorer_path = root / "poll_explorer.json"
    runtime_path = root / "assets" / "polling-lab.js"

    for dependency in (
        explorer_path,
        runtime_path,
    ):
        if not dependency.exists():
            raise RouteRegistryError(
                "Polling Lab semantic dependency missing: "
                f"{dependency.relative_to(root).as_posix()}"
            )

    components = (
        (
            "html",
            _semantic_html_bytes(
                source_path.read_bytes()
            ),
        ),
        (
            "poll_explorer",
            _semantic_json_bytes(
                explorer_path
            ),
        ),
        (
            "polling_lab_js",
            _semantic_text_bytes(
                runtime_path
            ),
        ),
    )

    digest = hashlib.sha256()

    for label, content in components:
        encoded_label = label.encode("utf-8")

        digest.update(
            len(encoded_label).to_bytes(
                4,
                byteorder="big",
            )
        )
        digest.update(encoded_label)

        digest.update(
            len(content).to_bytes(
                8,
                byteorder="big",
            )
        )
        digest.update(content)

    return digest.hexdigest()


def _candidate_detail_content_hash(
    *,
    root: Path,
    source_path: Path,
    candidate_id: str,
) -> str:
    """Hash rendered detail HTML plus its canonical published projection.

    CSS is intentionally excluded so cosmetic-only changes do not advance a
    candidate route's semantic ``lastmod``.
    """

    data_path = (
        root
        / "candidates"
        / candidate_id
        / "data.json"
    )

    if not data_path.exists():
        raise RouteRegistryError(
            "Candidate semantic dependency missing: "
            f"{data_path.relative_to(root).as_posix()}"
        )

    components = (
        (
            "html",
            _semantic_html_bytes(source_path.read_bytes()),
        ),
        (
            "candidate_projection",
            _semantic_json_bytes(data_path),
        ),
    )
    digest = hashlib.sha256()

    for label, content in components:
        encoded_label = label.encode("utf-8")
        digest.update(
            len(encoded_label).to_bytes(4, byteorder="big")
        )
        digest.update(encoded_label)
        digest.update(
            len(content).to_bytes(8, byteorder="big")
        )
        digest.update(content)

    return digest.hexdigest()


def _route_content_hash(
    *,
    route: dict[str, Any],
    root: Path,
    source_path: Path,
) -> str:
    if (
        route.get("family") == "polls"
        and route.get("kind") == "hub"
    ):
        return _polling_hub_content_hash(
            root=root,
            source_path=source_path,
        )

    if (
        route.get("family") == "candidates"
        and route.get("kind")
        in {"candidate-detail", "candidate-archive"}
    ):
        return _candidate_detail_content_hash(
            root=root,
            source_path=source_path,
            candidate_id=route["entity_id"],
        )

    return _content_hash(source_path)


def _route_pair(
    *,
    route_key: str,
    family: str,
    kind: str,
    entity_id: str,
    path_fr: str,
    path_en: str,
) -> list[dict[str, Any]]:
    return [
        {
            "route_id": f"{route_key}:fr",
            "route_key": route_key,
            "family": family,
            "kind": kind,
            "entity_id": entity_id,
            "language": "fr",
            "path": path_fr,
            "alternate_fr": path_fr,
            "alternate_en": path_en,
            "x_default": path_fr,
        },
        {
            "route_id": f"{route_key}:en",
            "route_key": route_key,
            "family": family,
            "kind": kind,
            "entity_id": entity_id,
            "language": "en",
            "path": path_en,
            "alternate_fr": path_fr,
            "alternate_en": path_en,
            "x_default": path_fr,
        },
    ]


def discover_routes(
    poll_manifest: dict[str, Any],
    candidate_registry: dict[str, Any] | None = None,
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    routes.extend(
        _route_pair(
            route_key="home",
            family="core",
            kind="home",
            entity_id="home",
            path_fr="/",
            path_en="/en/",
        )
    )

    routes.extend(
        _route_pair(
            route_key="candidates",
            family="candidates",
            kind="hub",
            entity_id="candidates",
            path_fr="/candidates/",
            path_en="/en/candidates/",
        )
    )

    if candidate_registry is None:
        candidate_registry = _load_json(
            root / "candidate_candidacy_status.json"
        )

    candidate_index = project_candidate_route_index(
        candidate_registry,
        root,
    )

    for candidate in candidate_index["candidates"]:
        candidate_id = candidate["candidate_id"]
        routes.extend(
            _route_pair(
                route_key=f"candidate:{candidate_id}",
                family="candidates",
                kind=(
                    "candidate-detail"
                    if candidate["lifecycle"] == "active"
                    else "candidate-archive"
                ),
                entity_id=candidate_id,
                path_fr=candidate["routes"]["fr"],
                path_en=candidate["routes"]["en"],
            )
        )

    routes.extend(
        _route_pair(
            route_key="polling-lab",
            family="polls",
            kind="hub",
            entity_id="polling-lab",
            path_fr="/sondages/",
            path_en="/en/sondages/",
        )
    )

    pages = poll_manifest.get("pages")

    if not isinstance(pages, list):
        raise RouteRegistryError(
            "poll_pages_manifest.json has no pages array."
        )

    for page in pages:
        if not isinstance(page, dict):
            raise RouteRegistryError(
                "Malformed poll page manifest entry."
            )

        wave_id = page.get("wave_id")
        path_fr = page.get("page_path_fr")
        path_en = page.get("page_path_en")

        if not all(
            isinstance(value, str) and value
            for value in (wave_id, path_fr, path_en)
        ):
            raise RouteRegistryError(
                "Poll page manifest entry lacks route identity."
            )

        routes.extend(
            _route_pair(
                route_key=f"poll-wave:{wave_id}",
                family="polls",
                kind="poll-wave",
                entity_id=wave_id,
                path_fr=path_fr,
                path_en=path_en,
            )
        )

    return routes


def current_snapshot(
    *,
    root: Path,
    poll_manifest_path: Path,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    poll_manifest = _load_json(poll_manifest_path)
    candidate_registry = _load_json(candidate_registry_path)
    routes = discover_routes(
        poll_manifest,
        candidate_registry,
        root=root,
    )

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    snapshot: list[dict[str, Any]] = []

    for route in routes:
        route_id = route["route_id"]

        if route_id in seen_ids:
            raise RouteRegistryError(
                f"Duplicate route id: {route_id}"
            )
        seen_ids.add(route_id)

        canonical_url = _canonical_url(route["path"])

        if canonical_url in seen_urls:
            raise RouteRegistryError(
                f"Duplicate canonical URL: {canonical_url}"
            )
        seen_urls.add(canonical_url)

        relative_source = _source_file(route["path"])
        absolute_source = root / relative_source

        if not absolute_source.exists():
            raise RouteRegistryError(
                f"Registered page missing: "
                f"{relative_source.as_posix()}"
            )

        document = absolute_source.read_text(
            encoding="utf-8"
        )

        _validate_canonical(
            document,
            canonical_url,
            source_file=relative_source,
        )

        item = dict(route)
        item.update(
            {
                "canonical_url": canonical_url,
                "alternate_url_fr": _canonical_url(
                    route["alternate_fr"]
                ),
                "alternate_url_en": _canonical_url(
                    route["alternate_en"]
                ),
                "x_default_url": _canonical_url(
                    route["x_default"]
                ),
                "source_file": relative_source.as_posix(),
                "title": _extract_title(document),
                "description": _extract_description(document),
                "content_sha256": _route_content_hash(
                    route=route,
                    root=root,
                    source_path=absolute_source,
                ),
            }
        )

        snapshot.append(item)

    snapshot.sort(
        key=lambda item: (
            item["family"],
            item["route_key"],
            item["language"],
        )
    )

    return snapshot


def build_registry(
    *,
    root: Path = ROOT,
    poll_manifest_path: Path = POLL_MANIFEST_PATH,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
    existing_registry_path: Path = REGISTRY_PATH,
    effective_date: str,
) -> dict[str, Any]:
    effective_date = _validate_date(effective_date)

    snapshot = current_snapshot(
        root=root,
        poll_manifest_path=poll_manifest_path,
        candidate_registry_path=candidate_registry_path,
    )

    previous_by_id: dict[str, dict[str, Any]] = {}

    if existing_registry_path.exists():
        previous = _load_json(existing_registry_path)

        for item in previous.get("routes", []):
            if isinstance(item, dict):
                route_id = item.get("route_id")
                if isinstance(route_id, str):
                    previous_by_id[route_id] = item

    routes: list[dict[str, Any]] = []

    for item in snapshot:
        prior = previous_by_id.get(item["route_id"])

        preserve = (
            prior is not None
            and prior.get("content_sha256")
            == item["content_sha256"]
            and prior.get("canonical_url")
            == item["canonical_url"]
        )

        if preserve:
            lastmod = prior.get("lastmod")

            if not isinstance(lastmod, str):
                raise RouteRegistryError(
                    f"Prior route lacks lastmod: "
                    f"{item['route_id']}"
                )

            _validate_date(lastmod)
        else:
            lastmod = effective_date

        item["lastmod"] = lastmod
        routes.append(item)

    family_counts: dict[str, int] = {}

    for item in routes:
        family = item["family"]
        family_counts[family] = (
            family_counts.get(family, 0) + 1
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "route_count": len(routes),
        "family_counts": dict(
            sorted(family_counts.items())
        ),
        "routes": routes,
    }


def serialize_registry(
    payload: dict[str, Any],
) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def check_registry(
    *,
    root: Path = ROOT,
    poll_manifest_path: Path = POLL_MANIFEST_PATH,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
    registry_path: Path = REGISTRY_PATH,
) -> list[str]:
    if not registry_path.exists():
        return ["route_registry.json is missing"]

    registry = _load_json(registry_path)

    if registry.get("schema_version") != SCHEMA_VERSION:
        return ["route registry schema version mismatch"]

    snapshot = current_snapshot(
        root=root,
        poll_manifest_path=poll_manifest_path,
        candidate_registry_path=candidate_registry_path,
    )

    registered = registry.get("routes")

    if not isinstance(registered, list):
        return ["route registry routes array missing"]

    current_by_id = {
        item["route_id"]: item for item in snapshot
    }

    registered_by_id = {
        item.get("route_id"): item
        for item in registered
        if isinstance(item, dict)
        and isinstance(item.get("route_id"), str)
    }

    errors: list[str] = []

    if set(current_by_id) != set(registered_by_id):
        missing = sorted(
            set(current_by_id) - set(registered_by_id)
        )
        stale = sorted(
            set(registered_by_id) - set(current_by_id)
        )

        for route_id in missing:
            errors.append(
                f"missing route: {route_id}"
            )

        for route_id in stale:
            errors.append(
                f"stale route: {route_id}"
            )

    comparable_fields = (
        "route_key",
        "family",
        "kind",
        "entity_id",
        "language",
        "path",
        "canonical_url",
        "alternate_url_fr",
        "alternate_url_en",
        "x_default_url",
        "source_file",
        "title",
        "description",
        "content_sha256",
    )

    for route_id in sorted(
        set(current_by_id) & set(registered_by_id)
    ):
        current = current_by_id[route_id]
        stored = registered_by_id[route_id]

        for field in comparable_fields:
            if stored.get(field) != current.get(field):
                errors.append(
                    f"out of date: {route_id} ({field})"
                )

        lastmod = stored.get("lastmod")

        if (
            not isinstance(lastmod, str)
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}",
                lastmod,
            )
        ):
            errors.append(
                f"invalid lastmod: {route_id}"
            )

    if registry.get("route_count") != len(registered):
        errors.append(
            "route_count does not match routes array"
        )

    expected_family_counts: dict[str, int] = {}

    for item in registered:
        if not isinstance(item, dict):
            continue

        family = item.get("family")

        if isinstance(family, str):
            expected_family_counts[family] = (
                expected_family_counts.get(family, 0)
                + 1
            )

    if registry.get("family_counts") != dict(
        sorted(expected_family_counts.items())
    ):
        errors.append(
            "family_counts do not match routes array"
        )

    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the canonical FR27 public route registry"
        )
    )

    parser.add_argument(
        "--poll-manifest",
        type=Path,
        default=POLL_MANIFEST_PATH,
    )

    parser.add_argument(
        "--candidate-registry",
        type=Path,
        default=CANDIDATE_REGISTRY_PATH,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=REGISTRY_PATH,
    )

    parser.add_argument(
        "--effective-date",
    )

    parser.add_argument(
        "--check",
        action="store_true",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)

    try:
        if arguments.check:
            errors = check_registry(
                root=ROOT,
                poll_manifest_path=arguments.poll_manifest,
                candidate_registry_path=arguments.candidate_registry,
                registry_path=arguments.output,
            )

            if errors:
                for error in errors:
                    print(
                        f"route registry check: {error}"
                    )
                return 1

            payload = _load_json(arguments.output)

            print(
                "route registry check clean: "
                f"{payload['route_count']} routes"
            )
            return 0

        if not arguments.effective_date:
            raise RouteRegistryError(
                "--effective-date YYYY-MM-DD is required "
                "when writing the registry"
            )

        payload = build_registry(
            root=ROOT,
            poll_manifest_path=arguments.poll_manifest,
            candidate_registry_path=arguments.candidate_registry,
            existing_registry_path=arguments.output,
            effective_date=arguments.effective_date,
        )

        _atomic_write(
            arguments.output,
            serialize_registry(payload),
        )

    except (
        RouteRegistryError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"route registry error: {error}")
        return 1

    print(
        "built route registry: "
        f"{payload['route_count']} routes "
        f"across {len(payload['family_counts'])} families"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
