"""Resolve source URLs for manual research; no publishing or evidence mutation."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Iterable
from urllib.parse import urlsplit

GOOGLE_NEWS_HOSTS = frozenset({"news.google.com"})


def _valid_http_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else ""


def _url_host(value: str) -> str:
    try:
        return (urlsplit(value).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _is_google_news_url(value: str) -> bool:
    return _url_host(_valid_http_url(value)) in GOOGLE_NEWS_HOSTS


def _decode_google_news_urls(urls: list[str]) -> dict[str, str]:
    unique = list(dict.fromkeys(url for url in urls if _is_google_news_url(url)))
    if not unique:
        return {}
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError as exc:
        raise RuntimeError(
            "Google News URL resolution requires googlenewsdecoder==0.2.1; "
            "install the optional tools/research-requirements.txt"
        ) from exc

    try:
        result = gnewsdecoder(unique, timeout=15.0)
    except Exception as exc:  # third-party decoder/network boundary
        print(f"WARNING: Google News batch decode failed: {exc}", file=sys.stderr)
        return {}

    rows = result if isinstance(result, list) else [result]
    resolved: dict[str, str] = {}
    for source, row in zip(unique, rows):
        if not isinstance(row, dict):
            continue
        success = row.get("success")
        if success is None:
            success = row.get("status")
        decoded = _valid_http_url(row.get("decoded_url"))
        if success and decoded and not _is_google_news_url(decoded):
            resolved[source] = decoded
    return resolved


def resolve_publisher_urls(urls: Iterable[str]) -> dict[str, str]:
    clean = list(dict.fromkeys(_valid_http_url(url) for url in urls if _valid_http_url(url)))
    resolved = {url: url for url in clean if not _is_google_news_url(url)}
    google = [url for url in clean if _is_google_news_url(url)]
    resolved.update(_decode_google_news_urls(google))
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+", help="Source URLs to inspect")
    args = parser.parse_args(argv)
    try:
        resolved = resolve_publisher_urls(args.urls)
    except RuntimeError as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(resolved, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
