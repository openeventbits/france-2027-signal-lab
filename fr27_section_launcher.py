"""Canonical static section disclosure for FR27 masthead hosts.

Builders render links on the server; the shared JavaScript only controls disclosure.
The CLI refreshes the authored dashboard and Polling hub shells, idempotently.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
# One registry owns order, localized labels, and route prefixes (including history).
FAMILIES = (
    ("candidates", ("CANDIDATS", "/candidates/"), ("CANDIDATES", "/en/candidates/")),
    ("polls", ("SONDAGES", "/sondages/"), ("POLLS", "/en/sondages/")),
    ("issues", ("ENJEUX", "/enjeux/"), ("ISSUES", "/en/issues/")),
    ("agenda", ("AGENDA", "/agenda/"), ("AGENDA", "/en/agenda/")),
)
ASSETS = '''  <link rel="stylesheet" href="/assets/fr27-section-launcher.css">
  <script src="/assets/fr27-section-launcher.js" defer></script>'''


def family_for_path(path: str) -> str | None:
    path = urlsplit(path).path
    for family, fr, en in FAMILIES:
        if any(path == route.rstrip("/") or path.startswith(route) for _, route in (fr, en)):
            return family
    return None


def render_section_menu(language: str, path: str) -> str:
    if language not in {"fr", "en"}:
        raise ValueError("unsupported launcher language")
    active = family_for_path(path)
    label = "Sections du site" if language == "fr" else "Site sections"
    rows = []
    for family, fr, en in FAMILIES:
        text, route = fr if language == "fr" else en
        current = ' aria-current="true"' if family == active else ""
        rows.append(f'        <a class="fr27-section-row" href="{route}" data-section-family="{family}"{current}>'
                    f'<span class="fr27-section-label">{text}</span></a>')
    return ('<!-- FR27_SECTION_MENU_START -->\n'
            f'      <nav class="fr27-section-menu" id="fr27-section-menu" aria-label="{label}" hidden>\n'
            + "\n".join(rows) + '\n      </nav>\n      <!-- FR27_SECTION_MENU_END -->')


def _button(mark_class: str, icon: str, language: str) -> str:
    label = "Explorer les sections" if language == "fr" else "Explore sections"
    return (f'<button class="{mark_class} fr27-section-launcher-trigger" type="button" '
            f'aria-label="{label}" aria-expanded="false" aria-controls="fr27-section-menu">'
            f'<span class="fr27-section-icon" aria-hidden="true">{icon}</span>'
            '<span class="fr27-section-caret" aria-hidden="true"></span></button>')


def _finish_header(header: str, language: str, path: str) -> str:
    if "data-fr27-section-launcher" not in header:
        header = re.sub(r'(<header\b[^>]*)(>)', r'\1 data-fr27-section-launcher\2', header, count=1)
    menu = render_section_menu(language, path)
    if "<!-- FR27_SECTION_MENU_START -->" in header:
        return re.sub(r'<!-- FR27_SECTION_MENU_START -->.*?<!-- FR27_SECTION_MENU_END -->',
                      lambda _: menu, header, count=1, flags=re.DOTALL)
    return header.replace("</header>", f"{menu}\n    </header>", 1)


def prepare_section_header(header: str, language: str, path: str) -> str:
    """Thin static-shell adapter: retain the authored SVG, Home link and controls."""
    brand = re.search(r'<a class="candidate-brand"[^>]*>.*?</a>', header, re.DOTALL)
    if not brand:
        raise ValueError("launcher requires the authored Home wordmark")
    mark = re.search(r'<span class="candidate-mark"[^>]*>(.*?)</span>', brand.group(), re.DOTALL)
    if mark:
        wordmark = brand.group().replace(mark.group(), "").replace("\n        \n", "\n")
        replacement = ('<!-- FR27_SECTION_BRAND_START -->\n'
                       '      <div class="fr27-masthead-brand">\n'
                       f'        {_button("candidate-mark", mark[1], language)}\n'
                       f'        {wordmark}\n      </div>\n      <!-- FR27_SECTION_BRAND_END -->')
        header = header[:brand.start()] + replacement + header[brand.end():]
    else:
        button = re.search(r'<button class="candidate-mark fr27-section-launcher-trigger".*?</button>', header, re.DOTALL)
        if not button:
            raise ValueError("launcher requires one authored signal tile")
        icon = re.search(r'<svg\b.*?</svg>', button.group(), re.DOTALL)
        if not icon:
            raise ValueError("launcher signal SVG is missing")
        header = header[:button.start()] + _button("candidate-mark", icon.group(), language) + header[button.end():]
    return _finish_header(header, language, path)


def prepare_dashboard_header(header: str, language: str) -> str:
    """Dashboard adapter leaves brand-copy, tools and shell geometry intact."""
    mark = re.search(r'<div class="mark" aria-hidden="true">(.*?)</div>', header, re.DOTALL)
    if mark:
        header = header[:mark.start()] + _button("mark", mark[1], language) + header[mark.end():]
    else:
        button = re.search(r'<button class="mark fr27-section-launcher-trigger".*?</button>', header, re.DOTALL)
        if not button:
            raise ValueError("dashboard launcher requires one authored signal tile")
        icon = re.search(r'<span class="fr27-section-icon" aria-hidden="true">(.*?)</span>', button.group(), re.DOTALL)
        if not icon:
            raise ValueError("dashboard signal SVG is missing")
        header = header[:button.start()] + _button("mark", icon[1], language) + header[button.end():]
    return _finish_header(header, language, "/en/" if language == "en" else "/")


def install_section_launcher(document: str, language: str) -> str:
    canonical = re.search(r'<link\b[^>]*rel="canonical"[^>]*href="([^"]+)"', document)
    if not canonical:
        raise ValueError("launcher requires a canonical route")
    document, count = re.subn(
        r'<header class="(?:candidate-masthead|masthead)".*?</header>',
        lambda match: prepare_section_header(match.group(), language, canonical[1])
        if match.group().startswith('<header class="candidate-masthead"')
        else prepare_dashboard_header(match.group(), language),
        document, count=1, flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("launcher requires exactly one masthead")
    if '/assets/fr27-section-launcher.css"' not in document:
        document = document.replace("</head>", ASSETS + "\n</head>", 1)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for language, relative in (("fr", "index.html"), ("en", "en/index.html"),
                               ("fr", "sondages/index.html"), ("en", "en/sondages/index.html")):
        target = args.root / relative
        source = target.read_text(encoding="utf-8")
        rendered = install_section_launcher(source, language)
        if args.check:
            if rendered != source:
                raise SystemExit(f"stale authored launcher: {relative}")
        elif rendered != source:
            target.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"refreshed authored shell {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
