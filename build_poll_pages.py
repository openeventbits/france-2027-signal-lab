from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from poll_ballot_labels import RN_CONDITIONAL_OPTION
from poll_studies import compatibility_pages, load_binding
from poll_scope import RETROSPECTIVE
from poll_source_tables import (load_source_tables, published_source_pages,
                                render_source_card, source_table_for_wave)
from urllib.parse import urlparse

from fr27_section_launcher import ASSETS as SECTION_LAUNCHER_ASSETS, prepare_section_header


ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "poll_pages_manifest.json"
SCHEMA_VERSION = "1.0"

FR_MONTHS = (
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

EN_MONTHS = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

FR_MONTHS_ABBREVIATED = (
    "",
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)

EN_MONTHS_ABBREVIATED = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


class PollPageError(ValueError):
    pass


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    # Keep unchanged wave-page bytes intact in Windows checkouts as well.
    if path.is_file() and path.read_bytes().replace(b"\r\n", b"\n") == content:
        return
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


def _iso_parts(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not match:
        raise PollPageError(f"Invalid ISO date: {value!r}")
    return tuple(int(part) for part in match.groups())


def format_date(value: str, language: str) -> str:
    year, month, day = _iso_parts(value)
    if language == "fr":
        return f"{day} {FR_MONTHS[month]} {year}"
    return f"{day} {EN_MONTHS[month]} {year}"


def format_date_range(start: str, end: str, language: str) -> str:
    start_year, start_month, start_day = _iso_parts(start)
    end_year, end_month, end_day = _iso_parts(end)

    if (start_year, start_month, start_day) == (
        end_year,
        end_month,
        end_day,
    ):
        return format_date(start, language)

    if language == "fr":
        full_months = FR_MONTHS
        abbreviated_months = FR_MONTHS_ABBREVIATED
    else:
        full_months = EN_MONTHS
        abbreviated_months = EN_MONTHS_ABBREVIATED

    if start_year == end_year and start_month == end_month:
        return (
            f"{start_day}–{end_day} "
            f"{full_months[start_month]} {start_year}"
        )

    if start_year == end_year:
        return (
            f"{start_day} {abbreviated_months[start_month]}–"
            f"{end_day} {abbreviated_months[end_month]} {start_year}"
        )

    return (
        f"{start_day} {abbreviated_months[start_month]} {start_year}–"
        f"{end_day} {abbreviated_months[end_month]} {end_year}"
    )


def format_integer(value: Any, language: str) -> str:
    if value is None:
        return "—"
    number = int(value)
    text = f"{number:,}"
    if language == "fr":
        return text.replace(",", "\u202f")
    return text


def format_score(value: Any, language: str) -> str:
    if not isinstance(value, (int, float)):
        return "—"

    if float(value).is_integer():
        text = str(int(value))
    else:
        text = f"{float(value):.1f}".rstrip("0").rstrip(".")

    if language == "fr":
        text = text.replace(".", ",")

    return f"{text} %"


def format_points(value: float, language: str) -> str:
    if float(value).is_integer():
        text = str(int(value))
    else:
        text = f"{value:.1f}".rstrip("0").rstrip(".")

    if language == "fr":
        text = text.replace(".", ",")
        return f"{text} pts"

    return f"{text} pts"


def candidate_label(candidate: dict[str, Any], language: str = "fr") -> str:
    label = str(
        candidate.get("display_names", {}).get(language)
        or candidate.get("published_candidate_name")
        or candidate.get("candidate_name")
        or ""
    ).strip()

    label = re.sub(r"^Generic\s+", "", label, flags=re.IGNORECASE)
    return label or "—"


def _safe_source_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return value


def wave_sources(wave: dict[str, Any]) -> list[str]:
    values: list[str] = []

    for value in wave.get("source_urls", []):
        safe = _safe_source_url(value)
        if safe and safe not in values:
            values.append(safe)

    for scenario in wave.get("scenarios", []):
        safe = _safe_source_url(scenario.get("source_url"))
        if safe and safe not in values:
            values.append(safe)

    return values


def source_domain(url: str) -> str:
    host = (urlparse(url).hostname or url).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_block(document: str, marker: str, closing_tag: str) -> str:
    start = document.find(marker)
    if start < 0:
        raise PollPageError(f"Template marker not found: {marker}")

    end = document.find(closing_tag, start)
    if end < 0:
        raise PollPageError(f"Template closing tag not found: {closing_tag}")

    return document[start : end + len(closing_tag)]


def _site_favicon_link(template_root: Path) -> str:
    document = (
        template_root / "index.html"
    ).read_text(encoding="utf-8")

    matches = re.findall(
        r'<link\s+rel="icon"\s+'
        r'type="image/svg\+xml"\s+'
        r'href="data:image/svg\+xml;base64,[^"]+">',
        document,
        flags=re.IGNORECASE,
    )

    if len(matches) != 1:
        raise PollPageError(
            "Root template must expose exactly one SVG favicon."
        )

    return matches[0]


def _site_og_image_url(template_root: Path) -> str:
    document = (
        template_root / "index.html"
    ).read_text(encoding="utf-8")

    matches = re.findall(
        r'<meta\s+property="og:image"\s+'
        r'content="([^"]+)">',
        document,
        flags=re.IGNORECASE,
    )

    if len(matches) != 1:
        raise PollPageError(
            "Root template must expose exactly one og:image."
        )

    value = matches[0]

    if not value.startswith(
        "https://france2027.app/assets/og-cover.png"
    ):
        raise PollPageError(
            "Root og:image is not the FR27 OG cover."
        )

    return value


def load_shell_templates(template_root: Path) -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}

    for language, relative in (
        ("fr", Path("sondages/index.html")),
        ("en", Path("en/sondages/index.html")),
    ):
        source = (template_root / relative).read_text(encoding="utf-8")

        templates[language] = {
            "header": prepare_section_header(
                _extract_block(source, '<header class="candidate-masthead"', "</header>"),
                language,
                "/" + relative.parent.as_posix() + "/",
            ),
            "footer": _extract_block(
                source,
                '<footer id="candidate-app-hud"',
                "</footer>",
            ),
        }

    return templates


def _language_nav(language: str, wave: dict[str, Any]) -> str:
    if language == "fr":
        return (
            '<nav class="candidate-language" aria-label="Langue de l’interface">'
            f'<a href="{_escape(wave["page_path_fr"])}" lang="fr" hreflang="fr" '
            'aria-label="Français" aria-current="page">FR</a>'
            '<span aria-hidden="true">|</span>'
            f'<a href="{_escape(wave["page_path_en"])}" lang="en" hreflang="en" '
            'aria-label="English">EN</a>'
            "</nav>"
        )

    return (
        '<nav class="candidate-language" aria-label="Interface language">'
        f'<a href="{_escape(wave["page_path_fr"])}" lang="fr" hreflang="fr" '
        'aria-label="Français">FR</a>'
        '<span aria-hidden="true">|</span>'
        f'<a href="{_escape(wave["page_path_en"])}" lang="en" hreflang="en" '
        'aria-label="English" aria-current="page">EN</a>'
        "</nav>"
    )


def prepare_header(
    header: str,
    language: str,
    wave: dict[str, Any],
) -> str:
    nav = _language_nav(language, wave)

    result, count = re.subn(
        r'<nav class="candidate-language".*?</nav>',
        nav,
        header,
        count=1,
        flags=re.DOTALL,
    )

    if count != 1:
        raise PollPageError("Could not replace standalone language navigation.")

    return result


def prepare_footer(
    footer: str,
    wave_count: int,
) -> str:
    result, count = re.subn(
        r'(<strong id="fr27-hud-polls-value">)(?:\d+|—)(</strong>)',
        rf"\g<1>{wave_count}\g<2>",
        footer,
        count=1,
    )

    if count != 1:
        raise PollPageError("Could not update HUD poll count.")

    return result


def page_title(wave: dict[str, Any], language: str) -> str:
    pollster = wave["pollster"]
    start = format_date(wave["fieldwork_start"], language)
    end = format_date(wave["fieldwork_end"], language)
    sample = format_integer(wave.get("sample_size"), language)

    if language == "fr":
        return f"Sondage présidentiel {pollster} — {start}–{end} — n={sample} | France 2027"

    return f"{pollster} Presidential Poll — {start}–{end} — n={sample} | France 2027"


def page_description(wave: dict[str, Any], language: str) -> str:
    pollster = wave["pollster"]
    start = format_date(wave["fieldwork_start"], language)
    end = format_date(wave["fieldwork_end"], language)
    sample = format_integer(wave.get("sample_size"), language)
    count = wave["scenario_count"]

    if language == "fr":
        plural = "scénario publié" if count == 1 else "scénarios publiés"
        return (
            f"Sondage {pollster}, terrain du {start} au {end}, "
            f"échantillon n={sample}, {count} {plural}. "
            "Résultats détaillés et sources publiées."
        )

    plural = "published scenario" if count == 1 else "published scenarios"
    return (
        f"{pollster} poll, fieldwork {start} to {end}, "
        f"sample n={sample}, {count} {plural}. "
        "Detailed results and published sources."
    )


def scenario_status(scenario: dict[str, Any], language: str) -> str:
    partial = bool(scenario.get("partial_scenario"))

    if language == "fr":
        return "SCÉNARIO PARTIEL" if partial else "SCÉNARIO COMPLET"

    return "PARTIAL SCENARIO" if partial else "COMPLETE SCENARIO"


def render_scenario(
    scenario: dict[str, Any],
    index: int,
    language: str,
    *,
    open_by_default: bool = False,
) -> str:
    candidates = scenario.get("candidates", [])
    historical = scenario.get("election_scope") == RETROSPECTIVE
    scope_label = ("ARCHIVES RÉTROSPECTIVES 2022" if language == "fr" else "2022 RETROSPECTIVE ARCHIVE") if historical else ""
    scope_badge = f'<span class="poll-detail-scope">{scope_label}</span>' if historical else ""
    review = scenario.get("scope_review", {})
    evidence = _safe_source_url(review.get("evidence_url"))
    scope_evidence = (
        f'<p class="poll-detail-note">{scope_label} · '
        + ("Exclu de la vue 2027. Référence de classement" if language == "fr" else "Excluded from the 2027 view. Scope evidence")
        + f': <a href="{_escape(evidence)}" target="_blank" rel="noopener noreferrer">'
        + _escape(review.get("evidence_locator", {}).get(language, "")) + '</a></p>'
        if historical and evidence else ""
    )

    names = [
        candidate_label(candidate, language)
        for candidate in candidates
        if candidate_label(candidate, language) != "—"
    ]

    round_label = "PREMIER TOUR" if language == "fr" else "FIRST ROUND"
    scenario_word = "SCÉNARIO" if language == "fr" else "SCENARIO"
    candidate_heading = "CANDIDAT" if language == "fr" else "CANDIDATE"
    score_heading = "SCORE PUBLIÉ" if language == "fr" else "PUBLISHED SCORE"
    source_label = "SOURCE ↗"
    event_label = "ID ÉVÉNEMENT" if language == "fr" else "EVENT ID"

    partial = bool(scenario.get("partial_scenario"))
    status_class = "is-partial" if partial else "is-complete"

    if language == "fr":
        status_label = "SCÉNARIO PARTIEL" if partial else "SCÉNARIO COMPLET"
        candidate_count_label = (
            "CANDIDAT" if len(candidates) == 1 else "CANDIDATS"
        )
        open_label = "OUVRIR"
        collapse_label = "RÉDUIRE"
        published_total_label = "TOTAL PUBLIÉ"
        source_available = "SOURCE DISPONIBLE"
        source_unavailable = "SOURCE INDISPONIBLE"
    else:
        status_label = "PARTIAL SCENARIO" if partial else "COMPLETE SCENARIO"
        candidate_count_label = (
            "CANDIDATE" if len(candidates) == 1 else "CANDIDATES"
        )
        open_label = "OPEN"
        collapse_label = "COLLAPSE"
        published_total_label = "PUBLISHED TOTAL"
        source_available = "SOURCE AVAILABLE"
        source_unavailable = "SOURCE UNAVAILABLE"

    rows = []

    for candidate in candidates:
        rows.append(
            "<tr>"
            f"<td>{_escape(candidate_label(candidate, language))}</td>"
            f'<td class="poll-detail-score">'
            f'{_escape(format_score(candidate.get("score"), language))}'
            "</td>"
            "</tr>"
        )

    source = _safe_source_url(scenario.get("source_url"))

    source_markup = ""
    if source:
        source_markup = (
            f'<a href="{_escape(source)}" target="_blank" '
            f'rel="noopener noreferrer">{source_label}</a>'
        )

    reported_total = scenario.get("reported_total")

    total_markup = ""
    total_meta = ""

    if isinstance(reported_total, (int, float)):
        total_value = format_score(reported_total, language)
        total_markup = (
            f"<span>{published_total_label}: {_escape(total_value)}</span>"
        )
        total_meta = (
            f"<span>{published_total_label} {_escape(total_value)}</span>"
        )

    source_meta = source_available if source else source_unavailable
    open_attr = " open" if open_by_default else ""
    reviewed_anchor = (
        f'<span id="scenario-{_escape(scenario["event_id"])}"></span>'
        if scenario.get("document_hypothesis") else ""
    )
    document_label = (
        f'<span>{_escape(scenario["source_pollster"])} · '
        f'{_escape(scenario["document_hypothesis"])} (PDF p. {_escape(scenario["document_page"])})</span>'
        if scenario.get("document_hypothesis") else ""
    )

    return (
        f'<details class="poll-detail-scenario" '
        f'id="scenario-{index}" '
        f'data-scenario-index="{index}"{open_attr}>'
        '<summary class="poll-detail-scenario-summary">'
        '<div class="poll-detail-scenario-summary-main">'
        '<div class="poll-detail-scenario-kicker">'
        f'<span class="poll-detail-scenario-number">'
        f"{scenario_word} {index}"
        "</span>"
        f'<span class="poll-detail-scenario-status {status_class}">'
        f"{status_label}"
        "</span>"
        f"{scope_badge}"
        "</div>"
        f"<h3>{round_label} — {_escape(', '.join(names))}</h3>"
        '<div class="poll-detail-scenario-meta">'
        f"<span>{len(candidates)} {candidate_count_label}</span>"
        f"{total_meta}"
        f"<span>{source_meta}</span>"
        "</div>"
        "</div>"
        '<span class="poll-detail-scenario-toggle" aria-hidden="true">'
        f'<span class="poll-detail-scenario-toggle-text" '
        f'data-open-label="{_escape(open_label)}" '
        f'data-close-label="{_escape(collapse_label)}">'
        f"{collapse_label if open_by_default else open_label}"
        "</span>"
        '<i class="poll-detail-scenario-toggle-icon"></i>'
        "</span>"
        "</summary>"
        '<div class="poll-detail-scenario-body">'
        f"{scope_evidence}"
        f"{reviewed_anchor}"
        '<div class="poll-detail-table-wrap">'
        '<table class="poll-detail-table">'
        "<thead><tr>"
        f"<th>{candidate_heading}</th>"
        f"<th>{score_heading}</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        '<div class="poll-detail-scenario-foot">'
        f"{document_label}"
        f'<span>{event_label}: {_escape(scenario.get("event_id", "—"))}</span>'
        f"{total_markup}"
        f"{source_markup}"
        "</div>"
        "</div>"
        "</details>"
    )


def candidate_variation_rows(
    wave: dict[str, Any],
    language: str,
) -> list[str]:
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for scenario in wave.get("scenarios", []):
        if scenario.get("election_scope") == RETROSPECTIVE:
            continue
        for candidate in scenario.get("candidates", []):
            # This review changes only the explicit 10205 conditional option;
            # retain existing summaries for unrelated generic ballot labels.
            if candidate.get("candidate_name") == RN_CONDITIONAL_OPTION:
                continue
            score = candidate.get("score")
            if not isinstance(score, (int, float)):
                continue

            key = str(candidate.get("candidate_id") or candidate_label(candidate, language))

            if key not in records:
                records[key] = {
                    "name": candidate_label(candidate, language),
                    "scores": [],
                }
                order.append(key)

            records[key]["scores"].append(float(score))

    rows: list[str] = []

    for key in order:
        record = records[key]
        scores = record["scores"]

        if len(scores) < 2:
            continue

        minimum = min(scores)
        maximum = max(scores)
        spread = maximum - minimum

        tested_label = "TESTÉ DANS" if language == "fr" else "TESTED IN"
        scenario_word = (
            "SCÉNARIO" if len(scores) == 1 else "SCÉNARIOS"
        ) if language == "fr" else (
            "SCENARIO" if len(scores) == 1 else "SCENARIOS"
        )

        rows.append(
            '<div class="poll-detail-summary-row">'
            '<span>'
            f'<span class="poll-detail-variation-name">{_escape(record["name"])}</span>'
            f" · {tested_label} {len(scores)} {scenario_word}"
            "</span>"
            "<strong>"
            f"{_escape(format_score(minimum, language))}–"
            f"{_escape(format_score(maximum, language))} "
            f"· Δ {_escape(format_points(spread, language))}"
            "</strong>"
            "</div>"
        )

    return rows



def nearby_waves(
    waves: list[dict[str, Any]],
    index: int,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """
    Return the nearest waves in corpus chronology.

    The explorer is ordered newest to oldest. Selection is based
    only on chronological proximity in that ordered corpus.
    """
    if index < 0 or index >= len(waves):
        raise PollPageError(
            f"Wave index outside corpus: {index}"
        )

    if limit <= 0:
        return []

    ranked = sorted(
        (
            (
                abs(candidate_index - index),
                candidate_index,
                candidate,
            )
            for candidate_index, candidate
            in enumerate(waves)
            if candidate_index != index
        ),
        key=lambda item: (
            item[0],
            item[1],
        ),
    )

    selected = ranked[:limit]

    # Present the selected cards in normal corpus chronology:
    # newer -> older.
    selected.sort(
        key=lambda item: item[1]
    )

    return [
        candidate
        for _distance, _index, candidate
        in selected
    ]


def render_related_polls(
    waves: list[dict[str, Any]],
    language: str,
    poll_lab_href: str,
) -> str:
    if not waves:
        return ""

    if language == "fr":
        eyebrow = "POURSUIVRE L’EXPLORATION"
        title = "AUTRES SONDAGES"
        open_label = "OUVRIR LE SONDAGE →"
        view_all = "VOIR TOUS LES SONDAGES →"
        scenario_single = "SCÉNARIO"
        scenario_plural = "SCÉNARIOS"
        candidate_single = "CANDIDAT"
        candidate_plural = "CANDIDATS"
    else:
        eyebrow = "CONTINUE EXPLORING"
        title = "MORE POLLS"
        open_label = "OPEN POLL →"
        view_all = "VIEW ALL POLLS →"
        scenario_single = "SCENARIO"
        scenario_plural = "SCENARIOS"
        candidate_single = "CANDIDATE"
        candidate_plural = "CANDIDATES"

    cards: list[str] = []

    for wave in waves:
        href = (
            wave["page_path_fr"]
            if language == "fr"
            else wave["page_path_en"]
        )

        date_range = format_date_range(
            wave["fieldwork_start"],
            wave["fieldwork_end"],
            language,
        )

        scenario_count = int(
            wave.get("scenario_count", 0)
        )

        candidate_count = len(
            wave.get("candidate_ids", [])
        )

        scenario_word = (
            scenario_single
            if scenario_count == 1
            else scenario_plural
        )

        candidate_word = (
            candidate_single
            if candidate_count == 1
            else candidate_plural
        )

        cards.append(
            f'<a class="poll-detail-related-card" '
            f'href="{_escape(href)}">'
            '<span class="poll-detail-related-pollster">'
            f'{_escape(wave["pollster"])}'
            "</span>"
            '<span class="poll-detail-related-date">'
            f"{_escape(date_range)}"
            "</span>"
            '<span class="poll-detail-related-meta">'
            f"<span>{scenario_count} {scenario_word}</span>"
            f"<span>{candidate_count} {candidate_word}</span>"
            "</span>"
            '<span class="poll-detail-related-open">'
            f"{open_label}"
            "</span>"
            "</a>"
        )

    return (
        '<section class="poll-detail-panel poll-detail-related" '
        'aria-labelledby="related-polls-title">'
        '<div class="poll-detail-panel-head">'
        "<div>"
        f'<div class="poll-detail-eyebrow">{eyebrow}</div>'
        f'<h2 id="related-polls-title">{title}</h2>'
        "</div>"
        f'<span class="poll-detail-panel-status">{len(waves)}</span>'
        "</div>"
        '<div class="poll-detail-related-grid">'
        f'{"".join(cards)}'
        "</div>"
        '<div class="poll-detail-related-footer">'
        f'<a class="poll-detail-related-all" '
        f'href="{_escape(poll_lab_href)}">'
        f"{view_all}"
        "</a>"
        "</div>"
        "</section>"
    )


def render_document(*, language, head, content, asset_prefix, header, footer,
                    structured_metadata=""):
    """Existing poll-detail shell, also used by the unregistered evidence page."""
    document = f'''<!doctype html>
<html lang="{language}">
<head>
{head}  <link rel="stylesheet" href="{asset_prefix}/fr27-ui.css">
  <link rel="stylesheet" href="{asset_prefix}/polling-page-shell.css">
  <link rel="stylesheet" href="{asset_prefix}/poll-page.css">

{structured_metadata}  <script src="{asset_prefix}/fr27-ui.js" defer></script>
  <script src="{asset_prefix}/poll-page.js" defer></script>
{SECTION_LAUNCHER_ASSETS}
</head>
<body class="polling-page poll-detail-page">
  <main class="polling-shell">
{header}

{content}

{footer}
  </main>
</body>
</html>
'''
    return ("\n".join(line.rstrip() for line in document.splitlines()) + "\n").encode("utf-8")


def render_page(
    wave: dict[str, Any],
    *,
    language: str,
    wave_count: int,
    header: str,
    footer: str,
    favicon: str,
    og_image_url: str,
    related_waves: list[dict[str, Any]],
    source_table: dict[str, Any] | None = None,
) -> bytes:
    if language not in {"fr", "en"}:
        raise PollPageError(f"Unsupported page language: {language}")

    canonical = (
        f"https://france2027.app{wave['page_path_fr']}"
        if language == "fr"
        else f"https://france2027.app{wave['page_path_en']}"
    )

    canonical_fr = f"https://france2027.app{wave['page_path_fr']}"
    canonical_en = f"https://france2027.app{wave['page_path_en']}"

    title = page_title(wave, language)
    description = page_description(wave, language)

    asset_prefix = "../../assets" if language == "fr" else "../../../assets"

    start = format_date(wave["fieldwork_start"], language)
    end = format_date(wave["fieldwork_end"], language)
    fieldwork_range = format_date_range(
        wave["fieldwork_start"],
        wave["fieldwork_end"],
        language,
    )
    sample = format_integer(wave.get("sample_size"), language)
    scenarios = int(wave["scenario_count"])
    candidate_count = len(wave.get("candidate_ids", []))
    sources = wave_sources(wave)

    prepared_header = prepare_header(header, language, wave)
    prepared_footer = prepare_footer(footer, wave_count)

    if language == "fr":
        home = "ACCUEIL"
        polls = "SONDAGES"
        eyebrow = "VAGUE DE SONDAGE · PREMIER TOUR"
        deck = (
            f"Résultats publiés par {wave['pollster']} pour une vague de terrain "
            f"du {start} au {end}. Les scénarios sont présentés séparément afin "
            "de préserver la composition exacte des bulletins testés."
        )
        tooltip_label = "À propos de cette vague de sondage"
        metric_pollster = "INSTITUT"
        metric_fieldwork = "TERRAIN"
        metric_sample = "ÉCHANTILLON"
        metric_scenarios = "SCÉNARIOS"
        metric_candidates = "CANDIDATS TESTÉS"
        scenarios_eyebrow = "RÉSULTATS PUBLIÉS"
        scenarios_title = "SCÉNARIOS DE LA VAGUE"
        variation_eyebrow = "MÊME SONDAGE · BULLETINS DIFFÉRENTS"
        variation_title = "VARIATION ENTRE SCÉNARIOS PUBLIÉS"
        open_source = "SOURCE ↗"
        boundary = (
            "<span>AUCUNE MOYENNE DE SONDAGES</span>"
            "<span>AUCUNE PRÉVISION</span>"
            "<span>AUCUN CONSEIL DE VOTE</span>"
        )
        no_variation = (
            "Cette vague ne contient pas plusieurs observations publiées "
            "pour un même candidat à travers différents scénarios."
        )
        scenario_status = (
            f"{scenarios} SCÉNARIO" if scenarios == 1 else f"{scenarios} SCÉNARIOS"
        )
    else:
        home = "HOME"
        polls = "POLLS"
        eyebrow = "FIRST-ROUND POLL WAVE"
        deck = (
            f"Published results from {wave['pollster']} for fieldwork conducted "
            f"from {start} to {end}. Scenarios are kept separate to preserve "
            "the exact composition of the ballots tested."
        )
        tooltip_label = "About this poll wave"
        metric_pollster = "POLLSTER"
        metric_fieldwork = "FIELDWORK"
        metric_sample = "SAMPLE"
        metric_scenarios = "SCENARIOS"
        metric_candidates = "CANDIDATES TESTED"
        scenarios_eyebrow = "PUBLISHED RESULTS"
        scenarios_title = "WAVE SCENARIOS"
        variation_eyebrow = "SAME POLL · DIFFERENT BALLOTS"
        variation_title = "VARIATION ACROSS PUBLISHED SCENARIOS"
        open_source = "SOURCE ↗"
        boundary = (
            "<span>NO POLLING AVERAGES</span>"
            "<span>NO FORECAST</span>"
            "<span>NO VOTING ADVICE</span>"
        )
        no_variation = (
            "This wave does not contain multiple published observations "
            "for the same candidate across different scenarios."
        )
        scenario_status = (
            f"{scenarios} SCENARIO" if scenarios == 1 else f"{scenarios} SCENARIOS"
        )

    first_source_cta = ""
    if sources:
        first_source_cta = (
            f'<a class="poll-detail-source-cta" href="{_escape(sources[0])}" '
            f'target="_blank" rel="noopener noreferrer">{open_source}</a>'
        )

    scenario_markup = "".join(
        render_scenario(
            scenario,
            index,
            language,
            open_by_default=(scenarios == 1),
        )
        for index, scenario in enumerate(wave["scenarios"], start=1)
    )

    historical_count = sum(s.get("election_scope") == RETROSPECTIVE for s in wave["scenarios"])
    scope_note = ""
    if historical_count:
        archive_href = ("/sondages/" if language == "fr" else "/en/sondages/") + "#historical-archive"
        plural = "s" if historical_count > 1 else ""
        text = (f"{historical_count} scénario{plural} rétrospectif{plural} 2022 conservé{plural} ; {scenarios - historical_count} dans la vue 2027."
                if language == "fr" else f"{historical_count} retrospective 2022 scenario{plural} retained; {scenarios - historical_count} in the 2027 view.")
        label = "Archives rétrospectives 2022" if language == "fr" else "2022 retrospective archive"
        scope_note = f'<p class="poll-detail-note">{text} <a href="{archive_href}">{label} →</a></p>\n      '

    if source_table is not None:
        scenario_markup += "\n        " + render_source_card(source_table, language)

    variation_rows = candidate_variation_rows(wave, language)

    if variation_rows:
        variation_markup = "".join(variation_rows)
    else:
        variation_markup = (
            f'<div class="poll-detail-note">{_escape(no_variation)}</div>'
        )

    poll_lab_href = "/sondages/" if language == "fr" else "/en/sondages/"

    related_polls_markup = render_related_polls(
        related_waves,
        language,
        poll_lab_href,
    )

    home_href = "/" if language == "fr" else "/en/"
    home_url = f"https://france2027.app{home_href}"
    poll_lab_url = f"https://france2027.app{poll_lab_href}"

    breadcrumb_current = (
        f"{wave['pollster']} · {start}–{end}"
    )

    og_locale = "fr_FR" if language == "fr" else "en_GB"
    og_locale_alternate = "en_GB" if language == "fr" else "fr_FR"

    if language == "fr":
        expand_all_label = "TOUT OUVRIR"
        collapse_all_label = "TOUT RÉDUIRE"
        variation_expand_label = "OUVRIR"
    else:
        expand_all_label = "EXPAND ALL"
        collapse_all_label = "COLLAPSE ALL"
        variation_expand_label = "OPEN"

    scenario_controls_markup = ""

    if scenarios > 1:
        scenario_controls_markup = (
            '<div class="poll-detail-panel-actions">'
            f'<button type="button" data-poll-expand-all>'
            f"{expand_all_label}"
            "</button>"
            f'<button type="button" data-poll-collapse-all>'
            f"{collapse_all_label}"
            "</button>"
            "</div>"
        )

    variation_panel_markup = ""

    if variation_rows:
        variation_panel_markup = (
            '<details class="poll-detail-panel '
            'poll-detail-side-disclosure poll-detail-variation-panel">'
            '<summary class="poll-detail-side-summary">'
            "<div>"
            f'<div class="poll-detail-eyebrow">{variation_eyebrow}</div>'
            f"<h2>{variation_title}</h2>"
            "</div>"
            '<span class="poll-detail-side-summary-action">'
            f"{variation_expand_label}"
            '<i class="poll-detail-side-summary-icon"></i>'
            "</span>"
            "</summary>"
            '<div class="poll-detail-summary-list">'
            f"{variation_markup}"
            "</div>"
            "</details>"
        )

    structured = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": title,
        "description": description,
        "url": canonical,
        "inLanguage": language,
        "temporalCoverage": (
            f"{wave['fieldwork_start']}/{wave['fieldwork_end']}"
        ),
        "creator": {
            "@type": "Organization",
            "name": "France 2027 Signal Lab",
            "url": "https://france2027.app/",
        },
        "isBasedOn": sources,
    }

    structured_json = json.dumps(
        structured,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    breadcrumb_structured = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": home,
                "item": home_url,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": polls,
                "item": poll_lab_url,
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": breadcrumb_current,
                "item": canonical,
            },
        ],
    }

    breadcrumb_json = json.dumps(
        breadcrumb_structured,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    head = f'''  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <title>{_escape(title)}</title>
  <meta name="description" content="{_escape(description)}">

  <link rel="canonical" href="{_escape(canonical)}">
  <link rel="alternate" hreflang="fr" href="{_escape(canonical_fr)}">
  <link rel="alternate" hreflang="en" href="{_escape(canonical_en)}">
  <link rel="alternate" hreflang="x-default" href="{_escape(canonical_fr)}">
  {favicon}

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="France 2027 Signal Lab">
  <meta property="og:locale" content="{og_locale}">
  <meta property="og:locale:alternate" content="{og_locale_alternate}">
  <meta property="og:title" content="{_escape(title)}">
  <meta property="og:description" content="{_escape(description)}">
  <meta property="og:url" content="{_escape(canonical)}">
  <meta property="og:image" content="{_escape(og_image_url)}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="France 2027 Signal Lab election dashboard">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{_escape(og_image_url)}">
  <meta name="twitter:title" content="{_escape(title)}">
  <meta name="twitter:description" content="{_escape(description)}">

'''
    structured_metadata = f'''  <script type="application/ld+json">{structured_json}</script>
  <script type="application/ld+json">{breadcrumb_json}</script>
'''
    content = f'''    <div class="poll-detail-content">
      <nav class="poll-detail-breadcrumb" aria-label="Breadcrumb">
        <a href="{home_href}">{home}</a>
        <span class="poll-detail-breadcrumb-separator" aria-hidden="true">/</span>
        <a href="{poll_lab_href}">{polls}</a>
        <span class="poll-detail-breadcrumb-separator" aria-hidden="true">/</span>
        <span aria-current="page">{_escape(breadcrumb_current)}</span>
      </nav>

      <section class="poll-detail-hero" aria-labelledby="poll-wave-title">
        <div class="poll-detail-hero-main">
          <div>
            <div class="poll-detail-eyebrow">{eyebrow}</div>
            <div class="poll-detail-title-line">
              <h1 class="poll-detail-title" id="poll-wave-title">{_escape(wave['pollster'])}</h1>

              <span class="poll-detail-tooltip-wrap">
                <button
                  type="button"
                  class="poll-detail-tooltip-trigger"
                  data-poll-tooltip-trigger
                  aria-label="{_escape(tooltip_label)}"
                  aria-describedby="poll-wave-note"
                  aria-controls="poll-wave-note"
                  aria-expanded="false"
                >i</button>

                <span
                  class="poll-detail-tooltip"
                  id="poll-wave-note"
                  role="tooltip"
                >{_escape(deck)}</span>
              </span>
            </div>
          </div>
          {first_source_cta}
        </div>

        <div class="poll-detail-metrics">
          <div class="poll-detail-metric">
            <span>{metric_pollster}</span>
            <strong>{_escape(wave['pollster'])}</strong>
          </div>
          <div class="poll-detail-metric poll-detail-metric-fieldwork">
            <span>{metric_fieldwork}</span>
            <strong>{_escape(fieldwork_range)}</strong>
          </div>
          <div class="poll-detail-metric">
            <span>{metric_sample}</span>
            <strong>n={_escape(sample)}</strong>
          </div>
          <div class="poll-detail-metric">
            <span>{metric_scenarios}</span>
            <strong>{scenarios}</strong>
          </div>
          <div class="poll-detail-metric">
            <span>{metric_candidates}</span>
            <strong>{candidate_count}</strong>
          </div>
        </div>

        <div class="poll-detail-boundary">
          {boundary}
        </div>
      </section>

      {scope_note}{variation_panel_markup}

      <section
        class="poll-detail-panel poll-detail-results"
        aria-labelledby="wave-scenarios-title"
      >
        <div class="poll-detail-panel-head">
          <div>
            <div class="poll-detail-eyebrow">{scenarios_eyebrow}</div>
            <h2 id="wave-scenarios-title">{scenarios_title}</h2>
          </div>

          <div class="poll-detail-panel-tools">
            <span class="poll-detail-panel-status">{scenario_status}</span>
            {scenario_controls_markup}
          </div>
        </div>

        <div class="poll-detail-scenario-list">
          {scenario_markup}
        </div>
      </section>

      {related_polls_markup}
    </div>'''
    return render_document(
        language=language, head=head, content=content,
        asset_prefix=asset_prefix, header=prepared_header, footer=prepared_footer,
        structured_metadata=structured_metadata,
    )


def render_source_evidence_page(*, language, template_root=ROOT):
    """Render Bonnal locally; deliberately absent from expected_artifacts/routes.

    The /preview/ URLs are local navigation targets, never numerical wave IDs.
    This function returns bytes only and does not write or register any route.
    """
    if language not in {"fr", "en"}:
        raise PollPageError(f"Unsupported page language: {language}")
    table = load_source_tables()["tables"]["10264"]["table"]
    fr = language == "fr"
    shell = load_shell_templates(Path(template_root))[language]
    preview_paths = {f"page_path_{lang}": f"/preview/evidence/10264/{lang}/"
                     for lang in ("fr", "en")}
    header = prepare_header(shell["header"], language, preview_paths)
    explorer = _load_json(Path(template_root) / "poll_explorer.json")
    footer = prepare_footer(shell["footer"], len(explorer["waves"]))
    bases = {base["scope"]: base["count"] for base in table["respondent_bases"]}
    adults = f"{bases['adults']:,}".replace(",", " " if fr else ",")
    metrics = [("INSTITUT" if fr else "POLLSTER", table["institute"]),
               ("TERRAIN" if fr else "FIELDWORK", format_date_range(
                   table["fieldwork_start"], table["fieldwork_end"], language)),
               ("ADULTES" if fr else "ADULTS", adults),
               ("INSCRITS" if fr else "REGISTERED VOTERS", str(bases["registered_voters"])),
               ("CERTAINS D’ALLER VOTER" if fr else "CERTAIN TO VOTE", str(bases["certain_to_vote"]))]
    core = (
        '<nav class="poll-detail-breadcrumb" aria-label="Breadcrumb">'
        '<a href="/preview/">APERÇUS / PREVIEWS</a> / NOTICE 10264</nav>'
        '<section class="poll-detail-hero"><div class="poll-detail-hero-main"><div>'
        f'<div class="poll-detail-eyebrow">{"APERÇU LOCAL · DOCUMENT SOURCE" if fr else "LOCAL PREVIEW · SOURCE DOCUMENT"}</div>'
        '<h1 class="poll-detail-title">OpinionWay / Sébastien Bonnal</h1></div></div>'
        '<div class="poll-detail-metrics">' + ''.join(f'<div class="poll-detail-metric"><span>{label}</span><strong>{value}</strong></div>' for label, value in metrics) +
        '</div><div class="poll-detail-boundary"><span>' +
        ('AUCUNE VAGUE NUMÉRIQUE ASSOCIÉE · AUCUN ÉVÉNEMENT CRÉÉ' if fr else 'NO ASSOCIATED NUMERICAL WAVE · NO EVENT CREATED') +
        '</span></div></section><section class="poll-detail-panel poll-detail-results">'
        '<div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">'
        + ('DOCUMENT VÉRIFIÉ' if fr else 'VERIFIED DOCUMENT') + '</div><h2>'
        + ('TABLEAU PUBLIÉ' if fr else 'PUBLISHED TABLE') + '</h2></div></div>'
        '<div class="poll-detail-scenario-list">' + render_source_card(table, language, standalone=True) + '</div></section>'
    )
    head = ('  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '  <meta name="color-scheme" content="dark">\n'
            '  <meta name="robots" content="noindex,nofollow">\n'
            '<title>OpinionWay / Sébastien Bonnal · '
            + ("aperçu source local" if fr else "local source preview")
            + '</title>\n  ' + _site_favicon_link(Path(template_root)) + '\n\n')
    return render_document(language=language, head=head, asset_prefix="/assets",
                           header=header, footer=footer,
                           content='<div class="poll-detail-content">' + core + '</div>')


def render_published_source_page(notice, *, language, template_root=ROOT):
    """Render an explicitly reviewed documentary route, never a numerical wave."""
    if language not in {"fr", "en"}:
        raise PollPageError(f"Unsupported page language: {language}")
    record = load_source_tables()
    if notice not in record["standalone_pages"]:
        raise PollPageError("Source table has no reviewed public route")
    table = record["tables"][notice]["table"]
    paths = record["standalone_pages"][notice]
    fr = language == "fr"
    root = Path(template_root)
    shell = load_shell_templates(root)[language]
    hub = "/sondages/" if fr else "/en/sondages/"
    canonical = "https://france2027.app" + paths[f"page_path_{language}"]
    title = (f"Sondage {table['institute']} pour {table['commissioner']}" if fr
             else f"{table['institute']} poll for {table['commissioner']}")
    date_label = (format_date(table["publication_date"], language) if table.get("publication_date")
                  else format_date_range(table["fieldwork_start"], table["fieldwork_end"], language))
    title += " · " + date_label
    row_count = len(table["rows"])
    description = (f"Tableau source vérifié du premier tour : {row_count} candidats, valeurs publiées et bornes <1%. Aucune observation numérique ajoutée."
                   if fr else f"Verified first-round source table: {row_count} candidates, published values and <1% bounds. No numerical observation added.")
    bases = {b["scope"]: b["count"] for b in table["respondent_bases"]}
    metrics = [("TERRAIN" if fr else "FIELDWORK", format_date_range(table["fieldwork_start"], table["fieldwork_end"], language)),
               ("ADULTES · 18 ANS ET PLUS" if fr else "ADULTS · AGED 18+", format_integer(bases["adults"], language)),
               ("INSCRITS" if fr else "REGISTERED VOTERS", format_integer(bases["registered_voters"], language)),
               ("CERTAINS DE VOTER · 9+10" if fr else "CERTAIN TO VOTE · 9+10", format_integer(bases["certain_to_vote"], language)),
               ("BASE EXPRIMÉE · PREMIER TOUR" if fr else "EXPRESSED BASE · FIRST ROUND",
                format_integer(bases["expressed_certain_voters"], language) if "expressed_certain_voters" in bases
                else ("Non vérifiée" if fr else "Unverified"))]
    non_expression = table["methodology"]["non_expression"]["result"]["literal"]
    if fr:
        paragraphs = [
            "Une configuration documentaire du premier tour, sans observation numérique dans le Polling Lab. Les 13 lignes publiées sont conservées ; <1% désigne une borne supérieure stricte, jamais un score exact. Aucun résultat n’est remplacé ni normalisé, même si le sous-total des valeurs exactes atteint 100%.",
            "Population : personnes inscrites sur les listes électorales, issues d’un échantillon représentatif de la population française de 18 ans et plus. Questionnaire auto-administré en ligne (CAWI), méthode des quotas : sexe, âge, catégorie socioprofessionnelle, catégorie d’agglomération et région.",
            "Colonne retenue : « Publié », page 12. Redressement sociodémographique + vote au premier tour de la présidentielle de 2022 + vote au premier tour des législatives de 2024, parmi les certains d’aller voter (notes 9+10). Les colonnes brutes ou alternatives ne remplacent pas les valeurs publiées.",
            f"N’expriment pas d’intention de vote : {non_expression}, publié séparément. Ce pourcentage repose sur le redressement sociodémographique de l’ensemble des répondants (méthodologie p. 3) ; il ne s’ajoute pas aux 13 résultats candidats. Le questionnaire (p. 5) propose aussi « Vous voteriez blanc ou nul » et « Vous vous abstiendriez », sans résultat candidat distinct dans cette colonne.",
            ("La base exprimée du premier tour est de 680 personnes (p. 12), distincte des 731 certains d’aller voter."
             if notice == "10333" else "La base exprimée du premier tour n’a pas été vérifiée. Les mentions de gabarit « 903 personnes » du PDF ne remplacent ni les 1 043 adultes, ni les 978 inscrits, ni les 731 certains d’aller voter vérifiés aux pages 3–4."),
            "Les trois scénarios de second tour de cette étude sont déjà présents sous forme d’observations numériques distinctes. Ils restent inchangés et ne sont pas reproduits ici. Leur présence ne rend pas le premier tour numériquement complet."
        ]
        states = [("SOURCE_DOCUMENT_VERIFIED", "Document source vérifié"),
                  ("DOCUMENTARY_COVERAGE_PUBLISHED", "Tableau documentaire publié"),
                  ("NUMERICAL_OBSERVATION_ABSENT", "Observation numérique du premier tour absente")]
    else:
        paragraphs = [
            "One documentary first-round configuration, with no numerical observation in the Polling Lab. All 13 published rows are preserved; <1% denotes a strict upper bound, never an exact score. Results are never substituted or normalized, even when the exact-value subtotal reaches 100%.",
            "Population: registered voters drawn from a representative sample of French adults aged 18+. Self-administered online questionnaire (CAWI), quota sampling by sex, age, occupation, size of urban area and region.",
            "Selected column: ‘Publié’, page 12. Sociodemographic weighting + first-round vote in the 2022 presidential election + first-round vote in the 2024 legislative election, among respondents certain to vote (ratings 9+10). Raw or alternative columns never replace published values.",
            f"Not expressing a voting intention: {non_expression}, published separately. This percentage uses sociodemographic weighting across all respondents (methodology p. 3); it is not added to the 13 candidate results. The questionnaire (p. 5) also offers ‘Vous voteriez blanc ou nul’ (blank or invalid ballot) and ‘Vous vous abstiendriez’ (abstention), with no separate candidate score in this column.",
            ("The first-round expressed base is 680 people (p. 12), distinct from the 731 respondents certain to vote."
             if notice == "10333" else "The first-round expressed base has not been verified. The PDF’s ‘903 people’ template labels do not override the 1,043 adults, 978 registered voters or 731 respondents certain to vote verified on pages 3–4."),
            "This study’s three second-round scenarios already exist as separate numerical observations. They remain unchanged and are not duplicated here. Their presence does not make first-round numerical coverage complete."
        ]
        states = [("SOURCE_DOCUMENT_VERIFIED", "Source document verified"),
                  ("DOCUMENTARY_COVERAGE_PUBLISHED", "Documentary table published"),
                  ("NUMERICAL_OBSERVATION_ABSENT", "First-round numerical observation absent")]
    attribution = ("Institut : OpinionWay · Commanditaire : CNEWS · Publication :" if fr
                   else "Pollster: OpinionWay · Commissioner: CNEWS · Published:") + " " + date_label
    runoff_link = (f'<p><a href="{_escape(table["source"]["pdf_url"])}#page=13" target="_blank" rel="noopener noreferrer">'
                   + ("Second tour dans le document original (p. 13–15)" if fr else "Second round in the original document (pp. 13–15)") + ' ↗</a></p>')
    if notice == "10264":
        attribution = ("Institut : OpinionWay · Commanditaire : Sébastien Bonnal · Terrain :" if fr
                       else "Pollster: OpinionWay · Commissioner: Sébastien Bonnal · Fieldwork:") + " " + date_label
        metrics[-1] = (metrics[-1][0], "Non publiée" if fr else "Not reported")
        runoff_link = ""
        paragraphs = ([
            "Une configuration documentaire du premier tour. Les 11 résultats publiés sont conservés ; <1% est une borne supérieure stricte, pas un score exact. Le tableau entier reste exclu des graphiques, comparaisons, classements et décomptes numériques.",
            "Le document désigne Sébastien Bonnal comme commanditaire et acheteur (p. 2). « Facebook » est le libellé de la liste de la Commission, pas le commanditaire attesté par le PDF. La notice est répertoriée le 15 septembre 2026 ; la date de publication de l’étude n’est pas confirmée. Le terrain vérifié est du 2 au 4 septembre 2026.",
            "Population : 1 034 adultes de 18 ans et plus, dont 951 inscrits sur les listes électorales. Les 700 certains d’aller voter (notes 9+10) constituent une base distincte ; ce nombre n’est pas présenté comme une base de suffrages exprimés. La base exprimée n’est pas publiée. Les mentions de gabarit « 903 personnes » ne remplacent pas ces bases vérifiées (pp. 3–4 et 12).",
            "Questionnaire auto-administré en ligne (CAWI), méthode des quotas : sexe, âge, catégorie socioprofessionnelle, catégorie d’agglomération et région. Colonne conservée : « Publié », p. 12. Redressement sociodémographique + vote au premier tour de la présidentielle de 2022 parmi les certains d’aller voter (notes 9+10), selon la méthodologie p. 3. Aucune colonne alternative n’est substituée.",
            "N’expriment pas d’intention de vote : 13%, publié séparément sur le redressement sociodémographique de l’ensemble des répondants. Ce résultat ne s’ajoute pas aux 11 résultats candidats. Le questionnaire p. 5 propose aussi le vote blanc ou nul et l’abstention, sans leur attribuer ici de score candidat.",
            "La publication de ce document ne constitue pas une observation numérique et ne résout pas l’avertissement de couverture numérique de la notice 10264. Aucun score exact n’est déduit de la borne <1% ni du sous-total des valeurs exactes."
        ] if fr else [
            "One documentary first-round configuration. All 11 published results are preserved; <1% is a strict upper bound, not an exact score. The entire table stays outside numerical charts, comparisons, rankings and polling counts.",
            "The document identifies Sébastien Bonnal as commissioner and purchaser (p. 2). ‘Facebook’ is the Commission listing label, not the commissioner authenticated by the PDF. The notice is listed on 15 September 2026; the study’s publication date is unconfirmed. Verified fieldwork ran from 2 to 4 September 2026.",
            "Population: 1,034 adults aged 18+, including 951 registered voters. The 700 respondents certain to vote (ratings 9+10) are a separate base; this is not presented as an expressed-vote count. The expressed base is not reported. The ‘903 people’ template labels do not override these verified bases (pp. 3–4 and 12).",
            "Self-administered online questionnaire (CAWI), quota sampling by sex, age, occupation, size of urban area and region. Preserved column: ‘Publié’, p. 12. Sociodemographic weighting + first-round vote in the 2022 presidential election among respondents certain to vote (ratings 9+10), as specified on p. 3. No alternative column is substituted.",
            "Not expressing a voting intention: 13%, reported separately using sociodemographic weighting across all respondents. It is not added to the 11 candidate results. The questionnaire on p. 5 also offers blank or invalid ballots and abstention, without assigning them candidate scores here.",
            "Publishing this document does not create a numerical observation or resolve notice 10264’s numerical-coverage warning. No exact score is inferred from the <1% bound or the exact-value subtotal."
        ])
    meta = ''.join(f'<div class="poll-detail-metric"><span>{_escape(label)}</span><strong>{_escape(value)}</strong></div>' for label, value in metrics)
    notes = ''.join(f'<p>{_escape(p)}</p>' for p in paragraphs)
    state_markup = ''.join(f'<span data-coverage-state="{key}">{_escape(label)}</span>' for key, label in states)
    core = f'''<div class="poll-detail-content poll-source-page">
      <nav class="poll-detail-breadcrumb" aria-label="Breadcrumb"><a href="{hub}">POLLING LAB</a> / NOTICE {notice}</nav>
      <section class="poll-detail-hero"><div class="poll-detail-hero-main"><div>
        <div class="poll-detail-eyebrow">{"DOCUMENT SOURCE · PREMIER TOUR" if fr else "SOURCE DOCUMENT · FIRST ROUND"}</div>
        <h1 class="poll-detail-title">{_escape(title)}</h1>
        <p>{_escape(attribution)}</p>
      </div></div><div class="poll-detail-metrics">{meta}</div>
      <div class="poll-detail-boundary">{state_markup}</div></section>
      <section class="poll-detail-panel poll-detail-results"><div class="poll-detail-panel-head"><div>
        <div class="poll-detail-eyebrow">NOTICE {notice} · PDF p. 12 · PUBLIÉ</div>
        <h2>{"RÉSULTATS PUBLIÉS" if fr else "PUBLISHED RESULTS"}</h2></div></div>
        <div class="poll-detail-scenario-list">{render_source_card(table, language, standalone=True)}</div>
      </section>
      <section class="poll-detail-panel poll-source-notes"><h2>{"LECTURE ET MÉTHODE" if fr else "READING THE TABLE AND METHODOLOGY"}</h2>{notes}
        {runoff_link}
        <details><summary>{"Authentification du document" if fr else "Document authentication"}</summary><p>SHA-256: <code>{table["source"]["pdf_sha256"]}</code></p><p>{_escape(table["source_table_id"])}</p></details>
        <p><a class="poll-detail-back-cta" href="{hub}#source-evidence">{"DOCUMENTS DU POLLING LAB" if fr else "POLLING LAB DOCUMENTS"} →</a></p>
      </section></div>'''
    head = f'''  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <title>{_escape(title)} · {"Document source" if fr else "Source evidence"} | France 2027 Signal Lab</title>
  <meta name="description" content="{_escape(description)}">
  <link rel="canonical" href="{canonical}">
  <link rel="alternate" hreflang="fr" href="https://france2027.app{paths['page_path_fr']}">
  <link rel="alternate" hreflang="en" href="https://france2027.app{paths['page_path_en']}">
  <link rel="alternate" hreflang="x-default" href="https://france2027.app{paths['page_path_fr']}">
  {_site_favicon_link(root)}
  <meta property="og:type" content="website">
  <meta property="og:title" content="{_escape(title)}">
  <meta property="og:description" content="{_escape(description)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{_site_og_image_url(root)}">
'''
    return render_document(language=language, head=head, content=core, asset_prefix="/assets",
                           header=prepare_header(shell["header"], language, paths),
                           footer=prepare_footer(shell["footer"], len(_load_json(root / "poll_explorer.json")["waves"])))


def render_compatibility_page(page, *, language, shell, wave_count):
    """Serve legacy fragments as real links; never a second analytical wave."""
    fr = language == "fr"
    canonical = "https://france2027.app" + page[f"canonical_path_{language}"]
    canonical_fr = "https://france2027.app" + page["canonical_path_fr"]
    canonical_en = "https://france2027.app" + page["canonical_path_en"]
    title = "Cluster17 / Politico · 19–22 octobre 2026" if fr else "Cluster17 / Politico · 19–22 October 2026"
    description = ("Les trois hypothèses de cette enquête sont réunies sur une seule page."
                   if fr else "The three hypotheses from this study are together on one page.")
    heading = "Retrouver les scénarios" if fr else "Find the scenarios"
    links = []
    members = {m["event_id"]: m for m in load_binding()["members"]}
    for index, event_id in enumerate(page["legacy_scenario_event_ids"], 1):
        label = members[event_id]["document_hypothesis"]
        destination = canonical + "#scenario-" + event_id
        links.append(f'<section id="scenario-{index}"><span id="scenario-{event_id}"></span>'
                     f'<p><a href="{destination}">{label} · {"Voir le scénario" if fr else "View scenario"}</a></p></section>')
    head = f'''  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)} · France 2027 Signal Lab</title>
  <meta name="description" content="{_escape(description)}">
  <meta name="robots" content="noindex,follow">
  <link rel="canonical" href="{canonical}">
  <link rel="alternate" hreflang="fr" href="{canonical_fr}">
  <link rel="alternate" hreflang="en" href="{canonical_en}">
  <link rel="alternate" hreflang="x-default" href="{canonical_fr}">
'''
    content = (f'<section class="poll-detail-hero"><h1>{_escape(title)}</h1>'
               f'<p>{_escape(description)}</p><p><a href="{canonical}">{"Voir l’enquête complète" if fr else "View the complete study"}</a></p>'
               f'<h2>{heading}</h2>{"".join(links)}</section>')
    return render_document(language=language, head=head, content=content,
                           asset_prefix="/assets", header=prepare_header(shell[language]["header"], language, page),
                           footer=prepare_footer(shell[language]["footer"], wave_count))


def manifest_payload(waves: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "wave_count": len(waves),
        "page_count": len(waves) * 2,
        "source_page_count": len(published_source_pages()) * 2,
        "source_pages": published_source_pages(),
        "compatibility_page_count": len(compatibility_pages(waves)) * 2,
        "compatibility_pages": compatibility_pages(waves),
        "pages": [
            {
                "wave_id": wave["wave_id"],
                "page_slug": wave["page_slug"],
                "pollster": wave["pollster"],
                "fieldwork_start": wave["fieldwork_start"],
                "fieldwork_end": wave["fieldwork_end"],
                "page_path_fr": wave["page_path_fr"],
                "page_path_en": wave["page_path_en"],
            }
            for wave in waves
        ],
    }


def serialize_manifest(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def page_file_from_url(path: str) -> Path:
    if not path.startswith("/") or not path.endswith("/"):
        raise PollPageError(f"Invalid generated page path: {path!r}")

    relative = Path(path.strip("/"))

    if relative.parts[:1] == ("sondages",):
        pass
    elif relative.parts[:2] == ("en", "sondages"):
        pass
    else:
        raise PollPageError(
            f"Generated poll page path escapes allowed roots: {path!r}"
        )

    return relative / "index.html"


def validate_explorer(explorer: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(explorer, dict):
        raise PollPageError("poll_explorer.json is not an object.")

    waves = explorer.get("waves")

    if not isinstance(waves, list) or not waves:
        raise PollPageError("poll_explorer.json contains no poll waves.")

    seen_wave_ids: set[str] = set()
    seen_slugs: set[str] = set()
    seen_paths: set[str] = set()

    required = {
        "wave_id",
        "page_slug",
        "page_path_fr",
        "page_path_en",
        "pollster",
        "fieldwork_start",
        "fieldwork_end",
        "scenario_count",
        "scenarios",
    }

    for wave in waves:
        if not isinstance(wave, dict):
            raise PollPageError("Malformed poll wave.")

        missing = required - set(wave)
        if missing:
            raise PollPageError(
                f"Poll wave missing page fields: {sorted(missing)}"
            )

        wave_id = wave["wave_id"]
        slug = wave["page_slug"]

        if wave_id in seen_wave_ids:
            raise PollPageError(f"Duplicate wave_id: {wave_id}")
        seen_wave_ids.add(wave_id)

        if slug in seen_slugs:
            raise PollPageError(f"Duplicate page_slug: {slug}")
        seen_slugs.add(slug)

        for key in ("page_path_fr", "page_path_en"):
            path = wave[key]
            page_file_from_url(path)
            if path in seen_paths:
                raise PollPageError(f"Duplicate generated page path: {path}")
            seen_paths.add(path)

    return waves


def expected_artifacts(
    explorer: dict[str, Any],
    *,
    template_root: Path,
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    waves = validate_explorer(explorer)
    shell = load_shell_templates(template_root)
    favicon = _site_favicon_link(template_root)
    og_image_url = _site_og_image_url(template_root)
    wave_count = len(waves)
    source_record = load_source_tables()

    artifacts: dict[Path, bytes] = {}

    for index, wave in enumerate(waves):
        source_table = source_table_for_wave(wave, source_record)
        related = nearby_waves(
            waves,
            index,
            limit=6,
        )

        for language in ("fr", "en"):
            path_key = "page_path_fr" if language == "fr" else "page_path_en"
            relative = page_file_from_url(wave[path_key])

            artifacts[relative] = render_page(
                wave,
                language=language,
                wave_count=wave_count,
                header=shell[language]["header"],
                footer=shell[language]["footer"],
                favicon=favicon,
                og_image_url=og_image_url,
                related_waves=related,
                source_table=source_table,
            )

    manifest = manifest_payload(waves)
    for page in manifest["compatibility_pages"]:
        for language in ("fr", "en"):
            relative = page_file_from_url(page[f"page_path_{language}"])
            if relative in artifacts:
                raise PollPageError("Compatibility route collides with a numerical wave")
            artifacts[relative] = render_compatibility_page(
                page, language=language, shell=shell, wave_count=wave_count)
    for page in manifest["source_pages"]:
        for language in ("fr", "en"):
            relative = page_file_from_url(page[f"page_path_{language}"])
            if relative in artifacts:
                raise PollPageError("Source evidence route collides with a numerical wave")
            artifacts[relative] = render_published_source_page(
                page["notice_id"], language=language, template_root=template_root)
    artifacts[Path(MANIFEST_NAME)] = serialize_manifest(manifest)

    return artifacts, manifest


def _registered_page_files(manifest: dict[str, Any]) -> set[Path]:
    files: set[Path] = set()

    for page in (manifest.get("pages", []) + manifest.get("source_pages", [])
                 + manifest.get("compatibility_pages", [])):
        if not isinstance(page, dict):
            continue

        for key in ("page_path_fr", "page_path_en"):
            value = page.get(key)
            if isinstance(value, str):
                try:
                    files.add(page_file_from_url(value))
                except PollPageError:
                    continue

    return files


def _remove_stale_registered_pages(
    output_root: Path,
    expected: set[Path],
) -> list[Path]:
    manifest_path = output_root / MANIFEST_NAME

    if not manifest_path.exists():
        return []

    try:
        prior = _load_json(manifest_path)
    except (json.JSONDecodeError, OSError):
        return []

    stale = sorted(_registered_page_files(prior) - expected)
    removed: list[Path] = []

    for relative in stale:
        target = output_root / relative

        if target.exists():
            target.unlink()
            removed.append(relative)

        parent = target.parent
        try:
            parent.rmdir()
        except OSError:
            pass

    return removed


def build_from_paths(
    explorer_path: Path | str = "poll_explorer.json",
    *,
    output_root: Path | str = ".",
    template_root: Path | str = ".",
) -> dict[str, Any]:
    output_root = Path(output_root)
    template_root = Path(template_root)

    explorer = _load_json(Path(explorer_path))

    artifacts, manifest = expected_artifacts(
        explorer,
        template_root=template_root,
    )

    expected_pages = {
        relative
        for relative in artifacts
        if relative.name == "index.html"
    }

    _remove_stale_registered_pages(output_root, expected_pages)

    for relative, content in artifacts.items():
        _atomic_write(output_root / relative, content)

    return manifest


def check_from_paths(
    explorer_path: Path | str = "poll_explorer.json",
    *,
    output_root: Path | str = ".",
    template_root: Path | str = ".",
) -> list[str]:
    output_root = Path(output_root)
    template_root = Path(template_root)

    explorer = _load_json(Path(explorer_path))

    artifacts, _manifest = expected_artifacts(
        explorer,
        template_root=template_root,
    )

    errors: list[str] = []

    for relative, expected in artifacts.items():
        target = output_root / relative

        if not target.exists():
            errors.append(f"missing: {relative.as_posix()}")
            continue

        actual = target.read_bytes()

        if actual.replace(b"\r\n", b"\n") != expected:
            errors.append(f"out of date: {relative.as_posix()}")

    expected_page_files = {
        relative
        for relative in artifacts
        if relative.name == "index.html"
    }

    for root_relative in (Path("sondages"), Path("en/sondages")):
        root = output_root / root_relative

        if not root.exists():
            continue

        for candidate in root.glob("*/index.html"):
            relative = candidate.relative_to(output_root)

            if relative not in expected_page_files:
                # Only flag directories that match the generated route shape.
                slug = candidate.parent.name
                if re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+-[0-9a-f]{16}",
                    slug,
                ):
                    errors.append(f"stale generated page: {relative.as_posix()}")

    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic FR27 bilingual poll-wave pages"
    )
    parser.add_argument("--explorer", default="poll_explorer.json")
    parser.add_argument("--output-root", default=".")
    parser.add_argument("--template-root", default=".")
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)

    try:
        if arguments.check:
            errors = check_from_paths(
                arguments.explorer,
                output_root=arguments.output_root,
                template_root=arguments.template_root,
            )

            if errors:
                for error in errors:
                    print(f"poll page check: {error}")
                return 1

            explorer = _load_json(arguments.explorer)
            waves = validate_explorer(explorer)

            print(
                f"poll page check clean: {len(waves)} waves, "
                f"{len(waves) * 2} numerical pages, "
                f"{len(published_source_pages()) * 2} documentary pages"
            )
            return 0

        manifest = build_from_paths(
            arguments.explorer,
            output_root=arguments.output_root,
            template_root=arguments.template_root,
        )

    except (PollPageError, OSError, json.JSONDecodeError) as error:
        print(f"poll page error: {error}")
        return 1

    print(
        f"built poll pages: {manifest['wave_count']} waves, "
        f"{manifest['page_count']} numerical pages, "
        f"{manifest['source_page_count']} documentary pages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
