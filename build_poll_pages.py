from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


class PollPageError(ValueError):
    pass


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


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


def candidate_label(candidate: dict[str, Any]) -> str:
    label = str(
        candidate.get("published_candidate_name")
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


def load_shell_templates(template_root: Path) -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}

    for language, relative in (
        ("fr", Path("sondages/index.html")),
        ("en", Path("en/sondages/index.html")),
    ):
        source = (template_root / relative).read_text(encoding="utf-8")

        templates[language] = {
            "header": _extract_block(
                source,
                '<header class="candidate-masthead"',
                "</header>",
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
        r'(<strong id="fr27-hud-polls-value">)\d+(</strong>)',
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

    names = [
        candidate_label(candidate)
        for candidate in candidates
        if candidate_label(candidate) != "—"
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
            f"<td>{_escape(candidate_label(candidate))}</td>"
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
        for candidate in scenario.get("candidates", []):
            score = candidate.get("score")
            if not isinstance(score, (int, float)):
                continue

            key = str(candidate.get("candidate_id") or candidate_label(candidate))

            if key not in records:
                records[key] = {
                    "name": candidate_label(candidate),
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



def render_scenario_navigation(
    wave: dict[str, Any],
    language: str,
) -> str:
    rows: list[str] = []

    for index, scenario in enumerate(wave.get("scenarios", []), start=1):
        candidates = scenario.get("candidates", [])
        partial = bool(scenario.get("partial_scenario"))

        if language == "fr":
            status = "PARTIEL" if partial else "COMPLET"
            candidate_word = (
                "CANDIDAT" if len(candidates) == 1 else "CANDIDATS"
            )
            aria = f"Ouvrir le scénario {index}"
        else:
            status = "PARTIAL" if partial else "COMPLETE"
            candidate_word = (
                "CANDIDATE" if len(candidates) == 1 else "CANDIDATES"
            )
            aria = f"Open scenario {index}"

        status_class = "is-partial" if partial else "is-complete"

        rows.append(
            f'<a class="poll-detail-scenario-nav-link" '
            f'href="#scenario-{index}" '
            f'data-scenario-target="scenario-{index}" '
            f'aria-label="{_escape(aria)}">'
            f'<span class="poll-detail-scenario-nav-number">'
            f"{index:02d}"
            "</span>"
            '<span class="poll-detail-scenario-nav-copy">'
            f'<strong class="{status_class}">{status}</strong>'
            f"<small>{len(candidates)} {candidate_word}</small>"
            "</span>"
            "</a>"
        )

    return "".join(rows)

def render_sources(wave: dict[str, Any], language: str) -> str:
    rows = []

    for number, url in enumerate(wave_sources(wave), start=1):
        domain = source_domain(url)
        label = (
            f"SOURCE PUBLIÉE {number}"
            if language == "fr"
            else f"PUBLISHED SOURCE {number}"
        )

        rows.append(
            '<div class="poll-detail-source-item">'
            f"<strong>{_escape(label)}</strong>"
            f"<span>{_escape(domain)}</span>"
            f'<a href="{_escape(url)}" target="_blank" rel="noopener noreferrer">'
            f"{'OUVRIR LA SOURCE ↗' if language == 'fr' else 'OPEN SOURCE ↗'}"
            "</a>"
            "</div>"
        )

    if rows:
        return "".join(rows)

    return (
        '<div class="poll-detail-note">'
        + (
            "Aucune URL de source publiée n’est disponible pour cette vague."
            if language == "fr"
            else "No published source URL is available for this wave."
        )
        + "</div>"
    )


def render_navigation_link(
    target: dict[str, Any] | None,
    language: str,
    direction: str,
) -> str:
    if direction == "newer":
        label = "VAGUE PLUS RÉCENTE" if language == "fr" else "NEWER WAVE"
    else:
        label = "VAGUE PRÉCÉDENTE" if language == "fr" else "OLDER WAVE"

    if target is None:
        unavailable = "AUCUNE" if language == "fr" else "NONE"
        return (
            '<div class="poll-detail-nav-placeholder">'
            f"<small>{label}</small><strong>{unavailable}</strong>"
            "</div>"
        )

    href = (
        target["page_path_fr"]
        if language == "fr"
        else target["page_path_en"]
    )

    date = format_date(target["fieldwork_end"], language)

    return (
        f'<a href="{_escape(href)}">'
        f"<small>{label}</small>"
        f"<strong>{_escape(target['pollster'])} · {_escape(date)}</strong>"
        "</a>"
    )


def render_page(
    wave: dict[str, Any],
    *,
    language: str,
    wave_count: int,
    header: str,
    footer: str,
    newer: dict[str, Any] | None,
    older: dict[str, Any] | None,
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
        metric_pollster = "INSTITUT"
        metric_fieldwork = "TERRAIN"
        metric_sample = "ÉCHANTILLON"
        metric_scenarios = "SCÉNARIOS"
        metric_candidates = "CANDIDATS TESTÉS"
        scenarios_eyebrow = "RÉSULTATS PUBLIÉS"
        scenarios_title = "SCÉNARIOS DE LA VAGUE"
        variation_eyebrow = "MÊME SONDAGE · BULLETINS DIFFÉRENTS"
        variation_title = "VARIATION ENTRE SCÉNARIOS PUBLIÉS"
        sources_eyebrow = "PREUVES"
        sources_title = "SOURCES PUBLIÉES"
        navigation_eyebrow = "RÉPERTOIRE"
        navigation_title = "VAGUES ADJACENTES"
        open_source = "SOURCE ↗"
        back = "RETOUR AU POLLING LAB"
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
        metric_pollster = "POLLSTER"
        metric_fieldwork = "FIELDWORK"
        metric_sample = "SAMPLE"
        metric_scenarios = "SCENARIOS"
        metric_candidates = "CANDIDATES TESTED"
        scenarios_eyebrow = "PUBLISHED RESULTS"
        scenarios_title = "WAVE SCENARIOS"
        variation_eyebrow = "SAME POLL · DIFFERENT BALLOTS"
        variation_title = "VARIATION ACROSS PUBLISHED SCENARIOS"
        sources_eyebrow = "EVIDENCE"
        sources_title = "PUBLISHED SOURCES"
        navigation_eyebrow = "DIRECTORY"
        navigation_title = "ADJACENT WAVES"
        open_source = "SOURCE ↗"
        back = "BACK TO POLLING LAB"
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

    variation_rows = candidate_variation_rows(wave, language)

    if variation_rows:
        variation_markup = "".join(variation_rows)
    else:
        variation_markup = (
            f'<div class="poll-detail-note">{_escape(no_variation)}</div>'
        )

    poll_lab_href = "/sondages/" if language == "fr" else "/en/sondages/"

    home_href = "/" if language == "fr" else "/en/"
    home_url = f"https://france2027.app{home_href}"
    poll_lab_url = f"https://france2027.app{poll_lab_href}"

    breadcrumb_current = (
        f"{wave['pollster']} · {start}–{end}"
    )

    og_locale = "fr_FR" if language == "fr" else "en_GB"
    og_locale_alternate = "en_GB" if language == "fr" else "fr_FR"

    if language == "fr":
        overview_eyebrow = "VAGUE"
        overview_title = "VUE D’ENSEMBLE"
        scenario_nav_eyebrow = "RÉPERTOIRE"
        scenario_nav_title = "NAVIGATION DES SCÉNARIOS"
        expand_all_label = "TOUT OUVRIR"
        collapse_all_label = "TOUT RÉDUIRE"
        overview_sources_label = "SOURCES"
        variation_expand_label = "OUVRIR"
    else:
        overview_eyebrow = "WAVE"
        overview_title = "WAVE OVERVIEW"
        scenario_nav_eyebrow = "DIRECTORY"
        scenario_nav_title = "SCENARIO NAVIGATION"
        expand_all_label = "EXPAND ALL"
        collapse_all_label = "COLLAPSE ALL"
        overview_sources_label = "SOURCES"
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

    overview_markup = (
        '<section class="poll-detail-panel poll-detail-overview" '
        'aria-labelledby="wave-overview-title">'
        '<div class="poll-detail-panel-head">'
        "<div>"
        f'<div class="poll-detail-eyebrow">{overview_eyebrow}</div>'
        f'<h2 id="wave-overview-title">{overview_title}</h2>'
        "</div>"
        "</div>"
        '<div class="poll-detail-overview-list">'
        '<div class="poll-detail-summary-row">'
        f"<span>{metric_scenarios}</span><strong>{scenarios}</strong>"
        "</div>"
        '<div class="poll-detail-summary-row">'
        f"<span>{metric_candidates}</span><strong>{candidate_count}</strong>"
        "</div>"
        '<div class="poll-detail-summary-row">'
        f"<span>{metric_sample}</span><strong>n={_escape(sample)}</strong>"
        "</div>"
        '<div class="poll-detail-summary-row">'
        f"<span>{metric_fieldwork}</span>"
        f"<strong>{_escape(start)} → {_escape(end)}</strong>"
        "</div>"
        '<div class="poll-detail-summary-row">'
        f"<span>{overview_sources_label}</span>"
        f"<strong>{len(sources)}</strong>"
        "</div>"
        "</div>"
        "</section>"
    )

    scenario_nav_markup = ""

    if scenarios > 1:
        scenario_nav_markup = (
            '<section class="poll-detail-panel poll-detail-scenario-nav" '
            'aria-labelledby="scenario-navigation-title">'
            '<div class="poll-detail-panel-head">'
            "<div>"
            f'<div class="poll-detail-eyebrow">{scenario_nav_eyebrow}</div>'
            f'<h2 id="scenario-navigation-title">{scenario_nav_title}</h2>'
            "</div>"
            f'<span class="poll-detail-panel-status">{scenarios}</span>'
            "</div>"
            '<nav class="poll-detail-scenario-nav-list" '
            'aria-label="Scenario navigation">'
            f"{render_scenario_navigation(wave, language)}"
            "</nav>"
            "</section>"
        )

    variation_panel_markup = ""

    if variation_rows:
        variation_panel_markup = (
            '<details class="poll-detail-panel '
            'poll-detail-side-disclosure">'
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

    document = f'''<!doctype html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <title>{_escape(title)}</title>
  <meta name="description" content="{_escape(description)}">

  <link rel="canonical" href="{_escape(canonical)}">
  <link rel="alternate" hreflang="fr" href="{_escape(canonical_fr)}">
  <link rel="alternate" hreflang="en" href="{_escape(canonical_en)}">
  <link rel="alternate" hreflang="x-default" href="{_escape(canonical_fr)}">

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="France 2027 Signal Lab">
  <meta property="og:locale" content="{og_locale}">
  <meta property="og:locale:alternate" content="{og_locale_alternate}">
  <meta property="og:title" content="{_escape(title)}">
  <meta property="og:description" content="{_escape(description)}">
  <meta property="og:url" content="{_escape(canonical)}">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{_escape(title)}">
  <meta name="twitter:description" content="{_escape(description)}">

  <link rel="stylesheet" href="{asset_prefix}/fr27-ui.css">
  <link rel="stylesheet" href="{asset_prefix}/polling-page-shell.css">
  <link rel="stylesheet" href="{asset_prefix}/poll-page.css">

  <script type="application/ld+json">{structured_json}</script>
  <script type="application/ld+json">{breadcrumb_json}</script>
  <script src="{asset_prefix}/fr27-ui.js" defer></script>
  <script src="{asset_prefix}/poll-page.js" defer></script>
</head>
<body class="polling-page poll-detail-page">
  <main class="polling-shell">
{prepared_header}

    <div class="poll-detail-content">
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
            <h1 class="poll-detail-title" id="poll-wave-title">{_escape(wave['pollster'])}</h1>
            <p class="poll-detail-deck">{_escape(deck)}</p>
          </div>
          {first_source_cta}
        </div>

        <div class="poll-detail-metrics">
          <div class="poll-detail-metric">
            <span>{metric_pollster}</span>
            <strong>{_escape(wave['pollster'])}</strong>
          </div>
          <div class="poll-detail-metric">
            <span>{metric_fieldwork}</span>
            <strong>{_escape(start)} → {_escape(end)}</strong>
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

      <div class="poll-detail-grid">
        <div class="poll-detail-main-column">
          <section class="poll-detail-panel" aria-labelledby="wave-scenarios-title">
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
        </div>

        <aside class="poll-detail-side-column">
          {overview_markup}

          {scenario_nav_markup}

          {variation_panel_markup}

          <section class="poll-detail-panel" aria-labelledby="wave-sources-title">
            <div class="poll-detail-panel-head">
              <div>
                <div class="poll-detail-eyebrow">{sources_eyebrow}</div>
                <h2 id="wave-sources-title">{sources_title}</h2>
              </div>
              <span class="poll-detail-panel-status">{len(sources)}</span>
            </div>

            <div class="poll-detail-source-list">
              {render_sources(wave, language)}
            </div>
          </section>

          <section class="poll-detail-panel" aria-labelledby="wave-navigation-title">
            <div class="poll-detail-panel-head">
              <div>
                <div class="poll-detail-eyebrow">{navigation_eyebrow}</div>
                <h2 id="wave-navigation-title">{navigation_title}</h2>
              </div>
            </div>

            <div class="poll-detail-nav">
              {render_navigation_link(newer, language, "newer")}
              {render_navigation_link(older, language, "older")}
            </div>

            <div class="poll-detail-back">
              <a class="poll-detail-back-cta" href="{poll_lab_href}">{back}</a>
            </div>
          </section>
        </aside>
      </div>
    </div>

{prepared_footer}
  </main>
</body>
</html>
'''

    return document.encode("utf-8")


def manifest_payload(waves: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "wave_count": len(waves),
        "page_count": len(waves) * 2,
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
    wave_count = len(waves)

    artifacts: dict[Path, bytes] = {}

    for index, wave in enumerate(waves):
        newer = waves[index - 1] if index > 0 else None
        older = waves[index + 1] if index + 1 < len(waves) else None

        for language in ("fr", "en"):
            path_key = "page_path_fr" if language == "fr" else "page_path_en"
            relative = page_file_from_url(wave[path_key])

            artifacts[relative] = render_page(
                wave,
                language=language,
                wave_count=wave_count,
                header=shell[language]["header"],
                footer=shell[language]["footer"],
                newer=newer,
                older=older,
            )

    manifest = manifest_payload(waves)
    artifacts[Path(MANIFEST_NAME)] = serialize_manifest(manifest)

    return artifacts, manifest


def _registered_page_files(manifest: dict[str, Any]) -> set[Path]:
    files: set[Path] = set()

    for page in manifest.get("pages", []):
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

        if actual != expected:
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
                f"{len(waves) * 2} pages"
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
        f"{manifest['page_count']} bilingual pages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())