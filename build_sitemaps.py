from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "route_registry.json"
INDEX_PATH = ROOT / "sitemap.xml"

BASE_URL = "https://france2027.app"


class SitemapError(ValueError):
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


def _family_filename(family: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]+", family):
        raise SitemapError(
            f"Invalid sitemap family: {family!r}"
        )

    return f"sitemap-{family}.xml"


def _validate_registry(
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    routes = registry.get("routes")

    if not isinstance(routes, list) or not routes:
        raise SitemapError(
            "Route registry has no routes."
        )

    seen: set[str] = set()

    for item in routes:
        if not isinstance(item, dict):
            raise SitemapError(
                "Malformed route registry entry."
            )

        required = (
            "route_id",
            "family",
            "canonical_url",
            "alternate_url_fr",
            "alternate_url_en",
            "x_default_url",
            "lastmod",
        )

        for field in required:
            value = item.get(field)

            if not isinstance(value, str) or not value:
                raise SitemapError(
                    f"Route entry missing {field}: "
                    f"{item.get('route_id')!r}"
                )

        canonical = item["canonical_url"]

        if canonical in seen:
            raise SitemapError(
                f"Duplicate sitemap URL: {canonical}"
            )

        seen.add(canonical)

    return routes


def _render_urlset(
    routes: list[dict[str, Any]],
) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<urlset '
            'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
        ),
    ]

    for item in sorted(
        routes,
        key=lambda route: route["canonical_url"],
    ):
        lines.extend(
            [
                "  <url>",
                (
                    "    <loc>"
                    f"{escape(item['canonical_url'])}"
                    "</loc>"
                ),
                (
                    "    <lastmod>"
                    f"{escape(item['lastmod'])}"
                    "</lastmod>"
                ),
                (
                    '    <xhtml:link rel="alternate" '
                    'hreflang="fr" '
                    f'href="{escape(item["alternate_url_fr"])}" />'
                ),
                (
                    '    <xhtml:link rel="alternate" '
                    'hreflang="en" '
                    f'href="{escape(item["alternate_url_en"])}" />'
                ),
                (
                    '    <xhtml:link rel="alternate" '
                    'hreflang="x-default" '
                    f'href="{escape(item["x_default_url"])}" />'
                ),
                "  </url>",
            ]
        )

    lines.append("</urlset>")

    return ("\n".join(lines) + "\n").encode("utf-8")


def _render_index(
    families: dict[str, list[dict[str, Any]]],
) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<sitemapindex '
            'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        ),
    ]

    for family in sorted(families):
        filename = _family_filename(family)

        lastmod = max(
            item["lastmod"]
            for item in families[family]
        )

        lines.extend(
            [
                "  <sitemap>",
                (
                    "    <loc>"
                    f"{BASE_URL}/{filename}"
                    "</loc>"
                ),
                (
                    "    <lastmod>"
                    f"{escape(lastmod)}"
                    "</lastmod>"
                ),
                "  </sitemap>",
            ]
        )

    lines.append("</sitemapindex>")

    return ("\n".join(lines) + "\n").encode("utf-8")


def expected_artifacts(
    registry: dict[str, Any],
) -> dict[Path, bytes]:
    routes = _validate_registry(registry)

    families: dict[str, list[dict[str, Any]]] = {}

    for route in routes:
        families.setdefault(
            route["family"],
            [],
        ).append(route)

    artifacts: dict[Path, bytes] = {
        Path("sitemap.xml"): _render_index(families)
    }

    for family, items in families.items():
        artifacts[Path(_family_filename(family))] = (
            _render_urlset(items)
        )

    return artifacts


def build_from_paths(
    registry_path: Path | str = REGISTRY_PATH,
    *,
    output_root: Path | str = ROOT,
) -> dict[Path, bytes]:
    registry = _load_json(registry_path)
    artifacts = expected_artifacts(registry)

    output_root = Path(output_root)

    for relative, content in artifacts.items():
        _atomic_write(
            output_root / relative,
            content,
        )

    return artifacts


def check_from_paths(
    registry_path: Path | str = REGISTRY_PATH,
    *,
    output_root: Path | str = ROOT,
) -> list[str]:
    registry = _load_json(registry_path)
    artifacts = expected_artifacts(registry)
    output_root = Path(output_root)

    errors: list[str] = []

    for relative, expected in artifacts.items():
        target = output_root / relative

        if not target.exists():
            errors.append(
                f"missing: {relative.as_posix()}"
            )
            continue

        if target.read_bytes() != expected:
            errors.append(
                f"out of date: {relative.as_posix()}"
            )

    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build FR27 sitemap index and family sitemaps"
        )
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY_PATH,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
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
            errors = check_from_paths(
                arguments.registry,
                output_root=arguments.output_root,
            )

            if errors:
                for error in errors:
                    print(f"sitemap check: {error}")
                return 1

            registry = _load_json(arguments.registry)

            print(
                "sitemap check clean: "
                f"{registry['route_count']} canonical URLs"
            )

            return 0

        artifacts = build_from_paths(
            arguments.registry,
            output_root=arguments.output_root,
        )

    except (
        SitemapError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"sitemap error: {error}")
        return 1

    print(
        "built sitemaps: "
        f"{len(artifacts) - 1} families + index"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())