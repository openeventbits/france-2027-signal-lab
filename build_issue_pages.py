"""Build the bilingual FR27 Issues / Enjeux public URL family."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from build_poll_pages import (
    _site_favicon_link,
    _site_og_image_url,
    format_date,
    format_date_range,
    load_shell_templates,
    prepare_footer,
)
from candidate_page_contract import project_candidate_route_index
from issue_page_contract import (
    IssuePageContractError,
    issue_manifest_payload,
    project_issue_pages,
    validate_issue_manifest,
)


ROOT = Path(__file__).resolve().parent
NEWS_WIRE_PATH = ROOT / "news_wire.json"
AGENDA_HISTORY_PATH = ROOT / "candidate_agenda_history.json"
ISSUE_COVERAGE_HISTORY_PATH = ROOT / "issue_coverage_history.json"
CANDIDATE_REGISTRY_PATH = ROOT / "candidate_candidacy_status.json"
MANIFEST_PATH = ROOT / "issue_pages_manifest.json"


class IssuePageBuildError(ValueError):
    """Raised when issue artifacts cannot be rendered safely."""


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
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


def _json_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def _localized(issue: dict[str, Any], language: str) -> str:
    return issue["labels"][language]


def _prepare_header(
    header: str,
    *,
    language: str,
    route_fr: str,
    route_en: str,
) -> str:
    if language == "fr":
        nav = (
            '<nav class="candidate-language" aria-label="Langue de l’interface">'
            f'<a href="{_h(route_fr)}" lang="fr" hreflang="fr" '
            'aria-label="Français" aria-current="page">FR</a>'
            '<span aria-hidden="true">|</span>'
            f'<a href="{_h(route_en)}" lang="en" hreflang="en" '
            'aria-label="English">EN</a></nav>'
        )
    else:
        nav = (
            '<nav class="candidate-language" aria-label="Interface language">'
            f'<a href="{_h(route_fr)}" lang="fr" hreflang="fr" '
            'aria-label="Français">FR</a>'
            '<span aria-hidden="true">|</span>'
            f'<a href="{_h(route_en)}" lang="en" hreflang="en" '
            'aria-label="English" aria-current="page">EN</a></nav>'
        )
    prepared, count = re.subn(
        r'<nav class="candidate-language".*?</nav>',
        nav,
        header,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise IssuePageBuildError("could not prepare issue language navigation")
    return prepared


def _sparkline(issue: dict[str, Any], *, large: bool = False) -> str:
    series = issue["current_coverage"]["evolution_30d"]
    values = [item["item_count"] for item in series]
    width = 520 if large else 180
    height = 108 if large else 42
    inset = 5
    maximum = max(values) if values else 0
    scale = maximum or 1
    points = " ".join(
        f"{inset + index * (width - 2 * inset) / max(1, len(values) - 1):.2f},"
        f"{height - inset - value * (height - 2 * inset) / scale:.2f}"
        for index, value in enumerate(values)
    )
    label = ", ".join(
        f"{item['date']}: {item['item_count']}" for item in series
    )
    class_name = "issue-coverage-sparkline is-large" if large else "issue-coverage-sparkline"
    return (
        f'<svg class="{class_name}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{_h(label)}" preserveAspectRatio="none">'
        f"<title>{_h(label)}</title>"
        f'<polyline points="{points}"></polyline>'
        "</svg>"
    )


def _date(value: str | None, language: str) -> str:
    return format_date(value, language) if value else "—"


def _period(start: str | None, end: str | None, language: str) -> str:
    if not start or not end:
        return "—"
    return format_date_range(start, end, language)


def _lifecycle_label(lifecycle: str, language: str) -> str:
    labels = {
        "fr": {"current": "ACTUEL", "historical": "HISTORIQUE", "dormant": "DORMANT"},
        "en": {"current": "CURRENT", "historical": "HISTORICAL", "dormant": "DORMANT"},
    }
    return labels[language][lifecycle]


def _head(
    *,
    language: str,
    title: str,
    description: str,
    canonical: str,
    canonical_fr: str,
    canonical_en: str,
    favicon: str,
    og_image: str,
    structured: list[dict[str, Any]],
) -> str:
    og_locale = "fr_FR" if language == "fr" else "en_GB"
    other_locale = "en_GB" if language == "fr" else "fr_FR"
    structured_markup = "\n  ".join(
        f'<script type="application/ld+json">{_json_script(item)}</script>'
        for item in structured
    )
    return f'''<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <title>{_h(title)}</title>
  <meta name="description" content="{_h(description)}">
  <link rel="canonical" href="{_h(canonical)}">
  <link rel="alternate" hreflang="fr" href="{_h(canonical_fr)}">
  <link rel="alternate" hreflang="en" href="{_h(canonical_en)}">
  <link rel="alternate" hreflang="x-default" href="{_h(canonical_fr)}">
  {favicon}
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="France 2027 Signal Lab">
  <meta property="og:locale" content="{og_locale}">
  <meta property="og:locale:alternate" content="{other_locale}">
  <meta property="og:title" content="{_h(title)}">
  <meta property="og:description" content="{_h(description)}">
  <meta property="og:url" content="{_h(canonical)}">
  <meta property="og:image" content="{_h(og_image)}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="France 2027 Signal Lab election dashboard">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{_h(og_image)}">
  <meta name="twitter:title" content="{_h(title)}">
  <meta name="twitter:description" content="{_h(description)}">
  <link rel="stylesheet" href="/assets/fr27-ui.css">
  <link rel="stylesheet" href="/assets/polling-lab.css">
  <link rel="stylesheet" href="/assets/poll-page.css">
  <link rel="stylesheet" href="/assets/polling-page-shell.css">
  <link rel="stylesheet" href="/assets/issues.css">
  {structured_markup}
  <script src="/assets/fr27-ui.js" defer></script>
  <script src="/assets/poll-page.js" defer></script>
  <script src="/assets/issues.js" defer></script>
</head>'''


def _breadcrumb_json(
    *,
    language: str,
    canonical: str,
    issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    home_name = "Accueil" if language == "fr" else "Home"
    hub_name = "Enjeux" if language == "fr" else "Issues"
    home_url = f"https://france2027.app{'/en/' if language == 'en' else '/'}"
    hub_url = f"https://france2027.app{'/en/issues/' if language == 'en' else '/enjeux/'}"
    elements = [
        {"@type": "ListItem", "position": 1, "name": home_name, "item": home_url},
        {"@type": "ListItem", "position": 2, "name": hub_name, "item": hub_url},
    ]
    if issue is not None:
        elements.append(
            {
                "@type": "ListItem",
                "position": 3,
                "name": _localized(issue, language),
                "item": canonical,
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }



def _heat_strip(
    issue: dict[str, Any],
    *,
    language: str,
    shared_maximum: int | None = None,
) -> str:
    series = issue["current_coverage"]["evolution_30d"]

    maximum = (
        shared_maximum
        if shared_maximum is not None
        else max(
            (point["item_count"] for point in series),
            default=0,
        )
    )

    scale = maximum or 1
    count = len(series)
    cells = []

    for index, point in enumerate(series):
        value = point["item_count"]

        if index >= count - 7:
            period_class = "is-recent"
        elif index >= count - 14:
            period_class = "is-previous"
        else:
            period_class = "is-older"

        intensity = (
            0.055
            if value == 0
            else 0.20 + 0.80 * (value / scale)
        )

        date_label = _date(point["date"], language)

        if language == "fr":
            unit = "article" if value == 1 else "articles"
        else:
            unit = "item" if value == 1 else "items"

        title = f"{date_label} · {value} {unit}"

        cells.append(
            f'<span class="issue-heat-cell {period_class}" '
            f'style="--issue-heat:{intensity:.3f}" '
            f'title="{_h(title)}"></span>'
        )

    aria = (
        "Profil quotidien de couverture sur 30 jours"
        if language == "fr"
        else "Daily 30-day coverage profile"
    )

    return (
        f'<div class="issue-heat-strip" '
        f'role="img" aria-label="{_h(aria)}">'
        + "".join(cells)
        + "</div>"
    )


def _evolution_matrix(
    issues: list[dict[str, Any]],
    language: str,
) -> str:
    if not issues:
        raise IssuePageBuildError(
            "cannot render empty issue evolution matrix"
        )

    shared_maximum = max(
        (
            point["item_count"]
            for issue in issues
            for point in issue["current_coverage"]["evolution_30d"]
        ),
        default=0,
    )

    reference = issues[0]["current_coverage"]["evolution_30d"]

    start_label = (
        _date(reference[0]["date"], language)
        if reference
        else "—"
    )
    end_label = (
        _date(reference[-1]["date"], language)
        if reference
        else "—"
    )

    rows = []

    for issue in issues:
        coverage = issue["current_coverage"]

        rows.append(
            f'''<article class="issue-evolution-row">
              <a class="issue-evolution-name" href="{_h(issue["routes"][language])}">{_h(_localized(issue, language))}</a>
              {_heat_strip(issue, language=language, shared_maximum=shared_maximum)}
              <div class="issue-evolution-total"><strong>{coverage["item_count"]}</strong><small>{"ARTICLES · 30 J" if language == "fr" else "ITEMS · 30D"}</small></div>
            </article>'''
        )

    older = "ANTÉRIEUR" if language == "fr" else "EARLIER"
    previous = "7 J PRÉC." if language == "fr" else "PREV. 7D"
    recent = "7 J RÉCENTS" if language == "fr" else "RECENT 7D"

    legend_label = (
        "Légende de période"
        if language == "fr"
        else "Period legend"
    )

    return f'''<div class="issue-evolution-matrix">
      <div class="issue-evolution-meta">
        <span>{_h(start_label)} → {_h(end_label)}</span>
        <div class="issue-evolution-legend" aria-label="{_h(legend_label)}">
          <span class="is-older"><i></i>{older}</span>
          <span class="is-previous"><i></i>{previous}</span>
          <span class="is-recent"><i></i>{recent}</span>
        </div>
      </div>
      <div class="issue-evolution-rows">{''.join(rows)}</div>
    </div>'''


def _hub_activity_row(issue: dict[str, Any], language: str) -> str:
    coverage = issue["current_coverage"]
    coverage_history = issue["coverage_history"]
    associations = issue["current_candidate_associations"]
    latest = coverage["latest_observation"]
    latest_date = _date(latest["date"], language) if latest else "—"
    subtopics = ", ".join(item["labels"][language] for item in issue["subtopics"])
    link_label = "OUVRIR" if language == "fr" else "OPEN"
    item_word = "articles" if language == "fr" else "items"
    publisher_word = "médias" if language == "fr" else "publishers"
    history = issue["coverage_history"]
    return f'''<article class="issue-activity-row" data-issue-row data-name="{_h(_localized(issue, language).casefold())}" data-state="{_h(issue['lifecycle'])}">
      <button class="issue-activity-select" type="button" data-issue-select
        data-label="{_h(_localized(issue, language))}"
        data-state-label="{_h(_lifecycle_label(issue['lifecycle'], language))}"
        data-state="{_h(issue['lifecycle'])}"
        data-items="{coverage['item_count']}"
        data-publishers="{coverage['publisher_count']}"
        data-days="{coverage['active_day_count']}"
        data-candidates="{associations['candidate_count']}"
        data-latest="{_h(latest_date)}"
        data-subtopics="{_h(subtopics or '—')}"
        data-history-items="{history['total_item_count']}"
        data-history-days="{history['active_day_count']}"
        data-history-start="{_h(_date(history['first_observation'], language))}"
        data-history-peak="{history['peak']['item_count']} · {_h(_date(history['peak']['date'], language))}"
        data-href="{_h(issue['routes'][language])}">
        <span class="issue-activity-name">{_h(_localized(issue, language))}</span>
        {_heat_strip(issue, language=language)}
        <span class="issue-activity-number"><strong>{coverage['item_count']}</strong><small>{item_word}</small></span>
        <span class="issue-activity-number"><strong>{coverage['publisher_count']}</strong><small>{publisher_word}</small></span>
        <span class="issue-activity-latest"><small>{'DERNIÈRE OBS.' if language == 'fr' else 'LATEST OBS.'}</small><strong>{_h(latest_date)}</strong></span>
        <span class="issue-state is-{_h(issue['lifecycle'])}">{_h(_lifecycle_label(issue['lifecycle'], language))}</span>
      </button>
      <a class="issue-row-link" href="{_h(issue['routes'][language])}" aria-label="{_h(link_label + ' — ' + _localized(issue, language))}">{link_label} →</a>
    </article>'''


def _inspector(issue: dict[str, Any], language: str) -> str:
    coverage = issue["current_coverage"]
    latest = coverage["latest_observation"]
    associations = issue["current_candidate_associations"]
    history = issue["coverage_history"]
    words = {
        "fr": ("ARTICLES · 30 J", "MÉDIAS · 30 J", "JOURS ACTIFS", "SOUS-THÈMES", "CANDIDATS", "DERNIÈRE OBSERVATION", "OUVRIR L’ENJEU →", "ARTICLES · HISTORIQUE", "JOURS ACTIFS · HISTORIQUE", "PREMIÈRE OBSERVATION", "PIC JOURNALIER"),
        "en": ("ITEMS · 30D", "PUBLISHERS · 30D", "ACTIVE DAYS", "SUBTOPICS", "CANDIDATES", "LATEST OBSERVATION", "OPEN ISSUE →", "ITEMS · HISTORY", "ACTIVE DAYS · HISTORY", "FIRST OBSERVATION", "DAILY PEAK"),
    }[language]
    return f'''<div class="issue-inspector-content" id="issue-inspector-content">
      <div class="issue-inspector-title-row"><h3 data-inspector-label>{_h(_localized(issue, language))}</h3><span class="issue-state is-{_h(issue['lifecycle'])}" data-inspector-state>{_h(_lifecycle_label(issue['lifecycle'], language))}</span></div>
      <dl class="issue-inspector-grid">
        <div><dt>{words[0]}</dt><dd data-inspector-items>{coverage['item_count']}</dd></div>
        <div><dt>{words[1]}</dt><dd data-inspector-publishers>{coverage['publisher_count']}</dd></div>
        <div><dt>{words[2]}</dt><dd data-inspector-days>{coverage['active_day_count']}</dd></div>
        <div><dt>{words[4]}</dt><dd data-inspector-candidates>{associations['candidate_count']}</dd></div>
        <div><dt>{words[7]}</dt><dd data-inspector-history-items>{history['total_item_count']}</dd></div>
        <div><dt>{words[8]}</dt><dd data-inspector-history-days>{history['active_day_count']}</dd></div>
      </dl>
      <div class="issue-inspector-meta"><span>{words[3]}</span><strong data-inspector-subtopics>{_h(', '.join(item['labels'][language] for item in issue['subtopics']) or '—')}</strong></div>
      <div class="issue-inspector-meta"><span>{words[5]}</span><strong data-inspector-latest>{_h(_date(latest['date'], language) if latest else '—')}</strong></div>
      <div class="issue-inspector-history-meta"><div><span>{words[9]}</span><strong data-inspector-history-start>{_h(_date(history['first_observation'], language))}</strong></div><div><span>{words[10]}</span><strong data-inspector-history-peak>{history['peak']['item_count']} · {_h(_date(history['peak']['date'], language))}</strong></div></div>
      <a class="issue-inspector-open" data-inspector-link href="{_h(issue['routes'][language])}">{words[6]}</a>
    </div>'''


def _evidence_row(item: dict[str, Any], language: str) -> str:
    source_label = "SOURCE ↗"
    return f'''<article class="issue-evidence-row">
      <div class="issue-evidence-source"><strong>{_h(item['publisher'])}</strong><time datetime="{_h(item['date'])}">{_h(_date(item['date'], language))}</time></div>
      <h3>{_h(item['headline'])}</h3>
      <a href="{_h(item['url'])}" target="_blank" rel="noopener noreferrer">{source_label}</a>
    </article>'''


def _decimal(value: float, language: str, digits: int = 1) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if language == "fr" else text


def _incidence_label(value: float, language: str) -> str:
    return f"{_decimal(value * 100, language)}%"


def _signed_pp(value: float, language: str) -> str:
    if value > 0:
        sign = "+"
    elif value < 0:
        sign = "−"
    else:
        sign = ""
    return f"{sign}{_decimal(abs(value), language)}pp"


def _history_comparison_projection(
    projection: dict[str, Any],
    *,
    window_days: int = 28,
) -> dict[str, Any]:
    history_meta = projection["coverage_history"]
    period = history_meta["period"]
    period_start = date.fromisoformat(period["start_date"])
    latest_end = date.fromisoformat(period["end_date"])
    latest_start = latest_end - timedelta(days=window_days - 1)
    previous_end = latest_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)
    if previous_start < period_start:
        raise IssuePageBuildError(
            "historical coverage does not contain two complete comparison windows"
        )

    corpus_daily = history_meta["corpus"]["daily"]

    def in_window(value: str, start: date, end: date) -> bool:
        current = date.fromisoformat(value)
        return start <= current <= end

    previous_corpus_items = sum(
        point["item_count"]
        for point in corpus_daily
        if in_window(point["date"], previous_start, previous_end)
    )
    latest_corpus_items = sum(
        point["item_count"]
        for point in corpus_daily
        if in_window(point["date"], latest_start, latest_end)
    )
    if previous_corpus_items <= 0 or latest_corpus_items <= 0:
        raise IssuePageBuildError("historical comparison corpus is empty")

    issues: dict[str, dict[str, Any]] = {}
    for issue in projection["issues"]:
        daily = issue["coverage_history"]["daily"]
        previous_points = [
            point
            for point in daily
            if in_window(point["date"], previous_start, previous_end)
        ]
        latest_points = [
            point
            for point in daily
            if in_window(point["date"], latest_start, latest_end)
        ]
        previous_items = sum(point["item_count"] for point in previous_points)
        latest_items = sum(point["item_count"] for point in latest_points)
        previous_incidence = previous_items / previous_corpus_items
        latest_incidence = latest_items / latest_corpus_items
        issues[issue["issue_id"]] = {
            "previous_start": previous_start.isoformat(),
            "previous_end": previous_end.isoformat(),
            "latest_start": latest_start.isoformat(),
            "latest_end": latest_end.isoformat(),
            "previous_item_count": previous_items,
            "latest_item_count": latest_items,
            "previous_incidence": previous_incidence,
            "latest_incidence": latest_incidence,
            "incidence_change_pp": (latest_incidence - previous_incidence) * 100,
            "previous_active_days": sum(
                point["item_count"] > 0 for point in previous_points
            ),
            "latest_active_days": sum(
                point["item_count"] > 0 for point in latest_points
            ),
            "previous_publisher_days": sum(
                point["publisher_count"] for point in previous_points
            ),
            "latest_publisher_days": sum(
                point["publisher_count"] for point in latest_points
            ),
        }

    return {
        "window_days": window_days,
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "latest_start": latest_start.isoformat(),
        "latest_end": latest_end.isoformat(),
        "previous_corpus_items": previous_corpus_items,
        "latest_corpus_items": latest_corpus_items,
        "issues": issues,
    }


def _issue_microbars(
    issue: dict[str, Any],
    language: str,
    *,
    history_comparison: dict[str, Any] | None = None,
) -> str:
    historical = history_comparison is not None
    if historical:
        series = issue["coverage_history"]["daily"]
        comparison = history_comparison
    else:
        coverage = issue["current_coverage"]
        comparison = coverage["comparison_7d"]
        series = coverage["evolution_30d"]
    maximum = max((point["item_count"] for point in series), default=0) or 1
    bars = []
    values = []

    for point in series:
        day = point["date"]
        value = point["item_count"]
        values.append(str(value))
        if comparison["previous_start"] <= day <= comparison["previous_end"]:
            period_class = "is-previous"
        elif comparison["latest_start"] <= day <= comparison["latest_end"]:
            period_class = "is-recent"
        elif day > comparison["latest_end"]:
            period_class = "is-partial"
        else:
            period_class = "is-older"

        height = 6 if value == 0 else max(12, value / maximum * 100)
        unit = (
            "article" if language == "fr" and value == 1
            else "articles" if language == "fr"
            else "item" if value == 1
            else "items"
        )
        title = f"{_date(day, language)} · {value} {unit}"
        bars.append(
            f'<i class="{period_class}" style="--issue-bar:{height:.1f}%" '
            f'title="{_h(title)}"></i>'
        )

    if historical:
        aria = (
            "Articles historiques par jour UTC : "
            if language == "fr"
            else "Historical items by UTC day: "
        ) + ", ".join(values)
        style = f' style="--issue-history-columns:{len(series)}"'
    else:
        aria = (
            "Articles par jour sur 30 jours : "
            if language == "fr"
            else "Daily items over 30 days: "
        ) + ", ".join(values)
        style = ""

    return (
        f'<div class="issue-card-microbars"{style} role="img" aria-label="{_h(aria)}">'
        + "".join(bars)
        + "</div>"
    )


def _issue_card(
    issue: dict[str, Any],
    language: str,
    *,
    history_comparison: dict[str, Any] | None = None,
) -> str:
    historical = history_comparison is not None
    if historical:
        coverage = issue["coverage_history"]
        comparison = history_comparison
        state = "HISTORIQUE" if language == "fr" else "HISTORICAL"
        open_label = (
            "OUVRIR LE DOSSIER HISTORIQUE →"
            if language == "fr"
            else "OPEN HISTORY DOSSIER →"
        )
        item_label = "ARTICLES · HIST." if language == "fr" else "ITEMS · HISTORY"
        publisher_label = "JOURS OBSERVÉS" if language == "fr" else "OBSERVED DAYS"
        incidence_label = "INCIDENCE · 28 J" if language == "fr" else "INCIDENCE · 28D"
        delta_label = "VS 28 J PRÉC." if language == "fr" else "VS PREV. 28D"
        subtopic_label = "PIC JOURNALIER" if language == "fr" else "DAILY PEAK"
        main_subtopic = (
            f'{coverage["peak"]["item_count"]} · '
            f'{_date(coverage["peak"]["date"], language)}'
        )
        href = _history_route(issue, language)
        first_count = coverage["total_item_count"]
        second_count = coverage["active_day_count"]
        state_class = "historical"
        volume = coverage["total_item_count"]
    else:
        coverage = issue["current_coverage"]
        comparison = coverage["comparison_7d"]
        subtopic = issue["subtopics"][0] if issue["subtopics"] else None
        state = _lifecycle_label(issue["lifecycle"], language)
        open_label = "OUVRIR LE DOSSIER →" if language == "fr" else "OPEN DOSSIER →"
        item_label = "ARTICLES · 30 J" if language == "fr" else "ITEMS · 30D"
        publisher_label = "MÉDIAS · 30 J" if language == "fr" else "PUBLISHERS · 30D"
        incidence_label = "INCIDENCE · 7 J" if language == "fr" else "INCIDENCE · 7D"
        delta_label = "VS 7 J PRÉC." if language == "fr" else "VS PREV. 7D"
        subtopic_label = "SOUS-THÈME" if language == "fr" else "SUBTOPIC"
        main_subtopic = subtopic["labels"][language] if subtopic else "—"
        href = issue["routes"][language]
        first_count = coverage["item_count"]
        second_count = coverage["publisher_count"]
        state_class = issue["lifecycle"]
        volume = coverage["item_count"]
    label = _localized(issue, language)

    return f'''<a
      class="issue-card"
      href="{_h(href)}"
      data-issue-card
      data-name="{_h(label)}"
      data-sort-activity="{comparison["latest_incidence"]:.6f}"
      data-sort-movement="{abs(comparison["incidence_change_pp"]):.3f}"
      data-sort-volume="{volume}"
      data-sort-label="{_h(label.casefold())}"
    >
      <span class="issue-card-head">
        <strong>{_h(label)}</strong>
        <span class="issue-state is-{_h(state_class)}">{_h(state)}</span>
      </span>
      <span class="issue-card-counts">
        <span><strong>{first_count}</strong><small>{item_label}</small></span>
        <span><strong>{second_count}</strong><small>{publisher_label}</small></span>
      </span>
      {_issue_microbars(issue, language, history_comparison=history_comparison)}
      <span class="issue-card-window">
        <span><strong>{_h(_incidence_label(comparison["latest_incidence"], language))}</strong><small>{incidence_label}</small></span>
        <span><strong>{_h(_signed_pp(comparison["incidence_change_pp"], language))}</strong><small>{delta_label}</small></span>
      </span>
      <span class="issue-card-subtopic"><small>{subtopic_label}</small><strong>{_h(main_subtopic)}</strong></span>
      <span class="issue-card-open">{open_label}</span>
    </a>'''


def _movement_method_note(language: str) -> str:
    return (
        "Incidence = jours-sources de l’enjeu ÷ jours-sources de toute la couverture présidentielle retenue dans la même semaine complète. La comparaison porte sur deux fenêtres complètes de 7 jours. Les enjeux sont multi-étiquettes : les pourcentages peuvent se chevaucher."
        if language == "fr"
        else "Incidence = issue source-days ÷ source-days across all retained presidential coverage in the same complete week. The comparison uses two complete 7-day windows. Issues are multi-label, so percentages can overlap."
    )


def _campaign_agenda_method_note(language: str) -> str:
    return (
        "Chaque article classé dans l’Agenda de campagne reçoit une seule catégorie. Les barres montrent la part de chaque catégorie parmi les articles classés pendant chaque semaine complète ; les articles retenus mais non classés dans l’Agenda ne sont pas inclus dans cette composition."
        if language == "fr"
        else "Each article classified into Campaign Agenda receives one category. The bars show each category’s share among classified articles in each complete week; retained articles not classified into Campaign Agenda are excluded from this composition."
    )


def _movement_chart(
    issues: list[dict[str, Any]],
    language: str,
    *,
    history_comparison: dict[str, Any] | None = None,
) -> str:
    historical = history_comparison is not None

    def comparison_for(issue: dict[str, Any]) -> dict[str, Any]:
        if historical:
            return history_comparison["issues"][issue["issue_id"]]
        return issue["current_coverage"]["comparison_7d"]

    ordered = sorted(
        issues,
        key=lambda issue: (
            -abs(comparison_for(issue)["incidence_change_pp"]),
            -comparison_for(issue)["latest_incidence"],
            _localized(issue, language).casefold(),
        ),
    )
    maximum = max(
        (
            value
            for issue in issues
            for value in (
                comparison_for(issue)["previous_incidence"] * 100,
                comparison_for(issue)["latest_incidence"] * 100,
            )
        ),
        default=0.0,
    ) or 1.0

    rows = []
    for issue in ordered:
        comparison = comparison_for(issue)
        previous = comparison["previous_incidence"] * 100
        latest = comparison["latest_incidence"] * 100
        previous_pos = previous / maximum * 100
        latest_pos = latest / maximum * 100
        low = min(previous_pos, latest_pos)
        span = abs(previous_pos - latest_pos)
        rows.append(
            f'''<div class="issue-dumbbell-row">
              <a href="{_h(_history_route(issue, language) if historical else issue["routes"][language])}">{_h(_localized(issue, language))}</a>
              <span class="issue-dumbbell-track" aria-hidden="true">
                <i class="issue-dumbbell-connector" style="--issue-low:{low:.3f}%;--issue-span:{span:.3f}%"></i>
                <i class="issue-dumbbell-dot is-previous" style="--issue-position:{previous_pos:.3f}%"></i>
                <i class="issue-dumbbell-dot is-recent" style="--issue-position:{latest_pos:.3f}%"></i>
              </span>
              <span class="issue-dumbbell-values">
                <span>{_h(_decimal(previous, language))}%</span>
                <b aria-hidden="true">→</b>
                <span>{_h(_decimal(latest, language))}%</span>
              </span>
              <strong class="issue-dumbbell-delta">{_h(_signed_pp(comparison["incidence_change_pp"], language))}</strong>
            </div>'''
        )

    reference = comparison_for(issues[0])
    previous_period = _period(
        reference["previous_start"],
        reference["previous_end"],
        language,
    )
    latest_period = _period(
        reference["latest_start"],
        reference["latest_end"],
        language,
    )
    if historical:
        previous_label = "28 J ANTÉRIEURS" if language == "fr" else "EARLIER 28D"
        latest_label = "28 J RÉCENTS" if language == "fr" else "RECENT 28D"
    else:
        previous_label = "SEMAINE PRÉC." if language == "fr" else "PREVIOUS WEEK"
        latest_label = "7 J RÉCENTS" if language == "fr" else "RECENT 7D"
    scale_label = _decimal(maximum, language)

    return f'''<div class="issue-dumbbell">

      <div class="issue-dumbbell-list">{''.join(rows)}</div>
      <div class="issue-dumbbell-legend" aria-label="{'Légende des périodes comparées' if language == 'fr' else 'Compared-period legend'}">
        <span class="issue-dumbbell-legend-item">
          <i class="is-previous" aria-hidden="true"></i>
          <strong>{previous_label}</strong>
          <small>{_h(previous_period)}</small>
        </span>
        <span class="issue-dumbbell-legend-item">
          <i class="is-recent" aria-hidden="true"></i>
          <strong>{latest_label}</strong>
          <small>{_h(latest_period)}</small>
        </span>
      </div>
    </div>'''


_CAMPAIGN_AGENDA_FR = {
    "legal_eligibility": "Affaires judiciaires et éligibilité",
    "selection_strategy": "Primaires et stratégies partisanes",
    "candidacies_endorsements": "Candidatures et soutiens",
    "rules_calendar": "Règles, calendrier et organisation de la campagne",
    "positioning_integrity": "Positionnement et image politique",
    "polls_race": "Sondages et rapports de force",
}


def _campaign_agenda_label(topic: dict[str, Any], language: str) -> str:
    if language == "fr":
        return _CAMPAIGN_AGENDA_FR.get(topic["id"], topic["label"])
    return topic["label"]


def _campaign_agenda_bar(
    topics: list[dict[str, Any]],
    *,
    field: str,
    language: str,
    class_name: str,
    aria_label: str | None = None,
) -> str:
    segments = []
    for index, topic in enumerate(topics, start=1):
        share = topic[field]
        percent = share * 100
        label = _campaign_agenda_label(topic, language)
        inner = f"<b>{index}</b>" if percent >= 7 else ""
        segments.append(
            f'<span class="issue-agenda-segment {class_name}" '
            f'style="--agenda-share:{percent:.6f}%" '
            f'title="{_h(label)} · {_h(_decimal(percent, language))}%">'
            f'{inner}</span>'
        )
    aria = aria_label or (
        "Composition de l’Agenda de campagne"
        if language == "fr"
        else "Campaign Agenda composition"
    )
    return (
        f'<div class="issue-agenda-bar" role="img" aria-label="{_h(aria)}">'
        + "".join(segments)
        + "</div>"
    )


def _campaign_agenda_panel(
    summary: dict[str, Any],
    language: str,
    *,
    historical_cadence: bool = False,
) -> str:
    topics = summary["topics"]
    previous_period = _period(
        summary["previous_start"],
        summary["previous_end"],
        language,
    )
    latest_period = _period(
        summary["latest_start"],
        summary["latest_end"],
        language,
    )
    if historical_cadence:
        previous_label = "28 J ANTÉRIEURS" if language == "fr" else "EARLIER 28D"
        latest_label = "28 J RÉCENTS" if language == "fr" else "RECENT 28D"
        aria_label = (
            "Répartition des jours-enjeux actifs"
            if language == "fr"
            else "Active issue-day distribution"
        )
    else:
        previous_label = "SEMAINE PRÉCÉDENTE" if language == "fr" else "PREVIOUS WEEK"
        latest_label = "7 J RÉCENTS" if language == "fr" else "RECENT 7D"
        aria_label = None
    previous_bar = _campaign_agenda_bar(
        topics,
        field="previous_share",
        language=language,
        class_name="is-previous",
        aria_label=aria_label,
    )
    latest_bar = _campaign_agenda_bar(
        topics,
        field="latest_share",
        language=language,
        class_name="is-recent",
        aria_label=aria_label,
    )

    legend = []
    for index, topic in enumerate(topics, start=1):
        previous = topic["previous_share"] * 100
        latest = topic["latest_share"] * 100
        legend.append(
            f'''<div class="issue-agenda-topic">
              <span class="issue-agenda-key">{index}</span>
              <span>{_h(_campaign_agenda_label(topic, language))}</span>
              <strong>{_h(_decimal(previous, language))}%</strong>
              <strong>{_h(_decimal(latest, language))}%</strong>
            </div>'''
        )

    return f'''<div class="issue-agenda-composition">
      <div class="issue-agenda-period">
        <div><span><strong>{previous_label}</strong><small>{_h(previous_period)} · n={summary["previous_total"]}</small></span>{previous_bar}</div>
        <div><span><strong>{latest_label}</strong><small>{_h(latest_period)} · n={summary["latest_total"]}</small></span>{latest_bar}</div>
      </div>
      <div class="issue-agenda-legend-head" aria-hidden="true">
        <span></span><span></span><strong>{'PRÉC.' if language == 'fr' else 'PREV.'}</strong><strong>{'RÉCENT' if language == 'fr' else 'RECENT'}</strong>
      </div>
      <div class="issue-agenda-topics">{''.join(legend)}</div>
    </div>'''


def _hub_evidence_row(
    item: dict[str, Any],
    *,
    issues_by_id: dict[str, dict[str, Any]],
    language: str,
    history: bool = False,
) -> str:
    badges = []
    for issue_id in item["issue_ids"]:
        issue = issues_by_id.get(issue_id)
        if issue is None:
            continue
        badges.append(
            f'<a class="issue-evidence-issue" href="{_h(_history_route(issue, language) if history else issue["routes"][language])}">'
            f'{_h(_localized(issue, language))}</a>'
        )

    return f'''<article class="issue-evidence-row issue-hub-evidence-row">
      <div class="issue-evidence-badges">{''.join(badges)}</div>
      <div class="issue-evidence-source"><strong>{_h(item["publisher"])}</strong><time datetime="{_h(item["date"])}">{_h(_date(item["date"], language))}</time></div>
      <h3>{_h(item["headline"])}</h3>
      <a class="issue-evidence-external" href="{_h(item["url"])}" target="_blank" rel="noopener noreferrer">SOURCE ↗</a>
    </article>'''


def _render_issue_hub_document(
    *,
    language: str,
    head: str,
    header: str,
    footer: str,
    body_classes: str,
    breadcrumb: str,
    copy: dict[str, str],
    descriptor_label: str,
    metrics_label: str,
    metric_values: tuple[Any, Any, Any, Any, str],
    landscape_eyebrow: str,
    landscape_status: str,
    issue_cards: str,
    movement_eyebrow: str,
    movement_status: str,
    movement_method_label: str,
    movement_method_note: str,
    movement_chart: str,
    companion_eyebrow: str,
    companion_status: str,
    companion_method_label: str,
    companion_method_note: str,
    companion_panel: str,
    latest_rows: str,
    latest_count: int,
    gateway_eyebrow: str,
    gateway_status: str,
    gateway_summary: str,
    gateway_period: str,
    gateway_href: str,
    gateway_label: str,
) -> bytes:
    french = language == "fr"
    document = f'''<!doctype html>
<html lang="{language}">
{head}
<body class="{body_classes}">
  <main class="polling-shell">
{header}
    {breadcrumb}
    <section class="polling-intro issues-intro" aria-labelledby="issues-title"><div class="polling-eyebrow">{copy['eyebrow']}</div><div class="polling-title-row issues-hub-title-row"><h1 id="issues-title">{copy['title']}</h1><span class="polling-title-info-wrap"><button class="polling-title-info" type="button" aria-label="{_h(descriptor_label)}" aria-describedby="issues-hub-method-note">i</button><span class="polling-title-tooltip" id="issues-hub-method-note" role="tooltip">{_h(copy['descriptor'])}</span></span></div></section>
    <section class="polling-metrics issues-metrics" aria-label="{_h(metrics_label)}">
      <div class="polling-metric"><span class="polling-metric-label">{copy['metric_issues']}</span><strong>{metric_values[0]}</strong></div>
      <div class="polling-metric"><span class="polling-metric-label">{copy['metric_items']}</span><strong>{metric_values[1]}</strong></div>
      <div class="polling-metric"><span class="polling-metric-label">{copy['metric_publishers']}</span><strong>{metric_values[2]}</strong></div>
      <div class="polling-metric"><span class="polling-metric-label">{copy['metric_candidates']}</span><strong>{metric_values[3]}</strong></div>
      <div class="polling-metric polling-metric-period"><span class="polling-metric-label">{copy['metric_period']}</span><strong>{_h(metric_values[4])}</strong></div>
    </section>

    <section class="polling-section issues-landscape-panel" aria-labelledby="issues-landscape-title">
      <div class="polling-section-head"><div><div class="polling-eyebrow">{landscape_eyebrow}</div><h2 id="issues-landscape-title">{copy['landscape']}</h2></div><span class="polling-panel-status">{landscape_status}</span></div>
      <div class="issue-landscape-toolbar">
        <div class="issue-landscape-search"><input id="issue-search" type="search" placeholder="{_h(copy['search'])}" data-issue-search aria-label="{_h(copy['search'])}"></div>
        <div class="issue-sort-controls" role="group" aria-label="{'Trier les enjeux' if french else 'Sort issues'}">
          <button type="button" data-issue-sort="activity" aria-pressed="true">{copy['sort_activity']}</button>
          <button type="button" data-issue-sort="movement" aria-pressed="false">{copy['sort_movement']}</button>
          <button type="button" data-issue-sort="volume" aria-pressed="false">{copy['sort_volume']}</button>
          <button type="button" data-issue-sort="az" aria-pressed="false">{copy['sort_az']}</button>
        </div>
      </div>
      <div class="issue-card-grid" data-issue-card-grid>{issue_cards}</div>
      <div class="issue-empty-state" data-issue-empty hidden>{'Aucun enjeu ne correspond à cette recherche.' if french else 'No issue matches this search.'}</div>
    </section>

    <div class="issues-comparison-grid">
      <section class="polling-section issues-movement-panel" aria-labelledby="issues-movement-title">
        <div class="polling-section-head"><div><div class="polling-eyebrow">{movement_eyebrow}</div><div class="polling-title-row"><h2 id="issues-movement-title">{copy['moving']}</h2><span class="polling-title-info-wrap"><button class="polling-title-info" type="button" aria-label="{_h(movement_method_label)}" aria-describedby="issues-movement-note">i</button><span class="polling-title-tooltip" id="issues-movement-note" role="tooltip">{_h(movement_method_note)}</span></span></div></div><span class="polling-panel-status">{movement_status}</span></div>
        {movement_chart}
      </section>
      <section class="polling-section issues-agenda-panel" aria-labelledby="issues-agenda-title">
        <div class="polling-section-head"><div><div class="polling-eyebrow">{companion_eyebrow}</div><div class="polling-title-row"><h2 id="issues-agenda-title">{copy['campaign_agenda']}</h2><span class="polling-title-info-wrap"><button class="polling-title-info" type="button" aria-label="{_h(companion_method_label)}" aria-describedby="issues-agenda-note">i</button><span class="polling-title-tooltip" id="issues-agenda-note" role="tooltip">{_h(companion_method_note)}</span></span></div></div><span class="polling-panel-status">{companion_status}</span></div>
        {companion_panel}
      </section>
    </div>

    <section class="polling-section issues-latest" aria-labelledby="issues-latest-title">
      <div class="polling-section-head"><div><div class="polling-eyebrow">EVIDENCE</div><h2 id="issues-latest-title">{copy['latest']}</h2></div><span class="polling-panel-status">{latest_count} {'ÉLÉMENTS' if french else 'ITEMS'}</span></div>
      <div class="issue-evidence-list">{latest_rows}</div>
    </section>

    <section class="polling-section issue-history-gateway is-compact" aria-labelledby="issues-history-gateway-title">
      <div class="polling-section-head"><div><div class="polling-eyebrow">{gateway_eyebrow}</div><h2 id="issues-history-gateway-title">{copy['history']}</h2></div><span class="polling-panel-status">{gateway_status}</span></div>
      <div class="issue-history-gateway-body"><div><strong>{gateway_summary}</strong><span>{_h(gateway_period)}</span></div><a class="issue-history-gateway-cta" href="{gateway_href}">{gateway_label}</a></div>
    </section>
{footer}
  </main>
</body>
</html>
'''
    return ("\n".join(line.rstrip() for line in document.splitlines()) + "\n").encode("utf-8")


def render_hub(
    projection: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
) -> bytes:
    french = language == "fr"
    route = "/enjeux/" if french else "/en/issues/"
    canonical = f"https://france2027.app{route}"
    title = "Enjeux 2027 — Observatoire des enjeux | France 2027" if french else "France 2027 Issues Lab — Source-linked issue coverage"
    description = (
        "Couverture sourcée des enjeux de la présidentielle française de 2027, avec évolution sur 30 jours et associations de candidats observées."
        if french
        else "Source-linked coverage of issues in France's 2027 presidential race, with 30-day evolution and observed candidate associations."
    )
    canonical_fr = "https://france2027.app/enjeux/"
    canonical_en = "https://france2027.app/en/issues/"
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical,
        "inLanguage": language,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(projection["issues"]),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": _localized(issue, language),
                    "url": issue["canonical"][language],
                }
                for index, issue in enumerate(projection["issues"], start=1)
            ],
        },
    }
    head = _head(
        language=language,
        title=title,
        description=description,
        canonical=canonical,
        canonical_fr=canonical_fr,
        canonical_en=canonical_en,
        favicon=favicon,
        og_image=og_image,
        structured=[collection, _breadcrumb_json(language=language, canonical=canonical)],
    )
    header = _prepare_header(
        shell["header"],
        language=language,
        route_fr="/enjeux/",
        route_en="/en/issues/",
    )
    issues = projection["issues"]
    if not issues:
        raise IssuePageBuildError("cannot render an empty public issue hub")

    metrics = projection["metrics"]
    issues_by_id = {issue["issue_id"]: issue for issue in issues}
    landscape_issues = sorted(
        issues,
        key=lambda issue: (
            -issue["current_coverage"]["comparison_7d"]["latest_incidence"],
            -issue["current_coverage"]["comparison_7d"]["latest_source_day_count"],
            _localized(issue, language).casefold(),
        ),
    )
    issue_cards = "\n".join(
        _issue_card(issue, language)
        for issue in landscape_issues
    )

    latest_observations = projection["latest_observations"][:6]
    latest_rows = "\n".join(
        _hub_evidence_row(
            item,
            issues_by_id=issues_by_id,
            language=language,
        )
        for item in latest_observations
    )
    period_text = _period(
        projection["period"]["start"],
        projection["period"]["end"],
        language,
    )
    history_period = projection["coverage_history"]["period"]

    copy = {
        "home": "ACCUEIL" if french else "HOME",
        "breadcrumb": "ENJEUX" if french else "ISSUES",
        "eyebrow": "ENJEUX" if french else "ISSUES",
        "title": "OBSERVATOIRE DES ENJEUX" if french else "ISSUES LAB",
        "descriptor": (
            "Couverture électorale sourcée par enjeu. Volume médiatique et association ne décrivent pas une position politique."
            if french
            else "Source-linked election coverage by issue. Media volume and association do not describe a policy position."
        ),
        "metric_issues": "ENJEUX" if french else "ISSUES",
        "metric_items": "ARTICLES DISTINCTS · 30 J" if french else "DISTINCT ITEMS · 30D",
        "metric_publishers": "MÉDIAS · 30 J" if french else "PUBLISHERS · 30D",
        "metric_candidates": "CANDIDATS ASSOCIÉS" if french else "ASSOCIATED CANDIDATES",
        "metric_period": "PÉRIODE" if french else "PERIOD",
        "landscape": "PAYSAGE DES ENJEUX" if french else "ISSUE LANDSCAPE",
        "search": "Rechercher un enjeu" if french else "Search issues",
        "sort_activity": "ACTIVITÉ" if french else "ACTIVITY",
        "sort_movement": "MOUVEMENT" if french else "MOVEMENT",
        "sort_volume": "VOLUME",
        "sort_az": "A–Z",
        "moving": "CE QUI BOUGE" if french else "WHAT’S MOVING",
        "campaign_agenda": "AGENDA DE CAMPAGNE" if french else "CAMPAIGN AGENDA",
        "latest": "DERNIÈRES OBSERVATIONS SOURCÉES" if french else "LATEST SOURCE-LINKED OBSERVATIONS",
        "history": "HISTORIQUE DES ENJEUX" if french else "ISSUE HISTORY",
    }

    return _render_issue_hub_document(
        language=language,
        head=head,
        header=header,
        footer=shell["footer"],
        body_classes="polling-page issues-page issues-hub-page",
        breadcrumb=(
            f'<nav class="polling-breadcrumb" aria-label="{"Fil d’Ariane" if french else "Breadcrumb"}">'
            f'<a href="{"/" if french else "/en/"}">{copy["home"]}</a>'
            f'<span aria-hidden="true">/</span><span aria-current="page">{copy["breadcrumb"]}</span></nav>'
        ),
        copy=copy,
        descriptor_label=(
            "À propos de l’Observatoire des enjeux" if french else "About Issues Lab"
        ),
        metrics_label="Couverture des enjeux" if french else "Issue coverage",
        metric_values=(
            metrics["public_issue_count"],
            metrics["current_evidence_item_count"],
            metrics["unique_publisher_count"],
            metrics["associated_candidate_count"],
            period_text,
        ),
        landscape_eyebrow="30 J",
        landscape_status=f'{len(issues)} {copy["metric_issues"]} · 30 J',
        issue_cards=issue_cards,
        movement_eyebrow=(
            "COMPARAISON · SEMAINES COMPLÈTES"
            if french
            else "COMPARISON · COMPLETE WEEKS"
        ),
        movement_status="INCIDENCE",
        movement_method_label=(
            "Méthode de calcul de l’incidence"
            if french
            else "Incidence calculation method"
        ),
        movement_method_note=_movement_method_note(language),
        movement_chart=_movement_chart(issues, language),
        companion_eyebrow=(
            "CE DONT PARLE LA CAMPAGNE" if french else "CAMPAIGN THEMES"
        ),
        companion_status="ÉTIQUETTE UNIQUE" if french else "SINGLE-LABEL",
        companion_method_label=(
            "Méthode de composition de l’Agenda de campagne"
            if french
            else "Campaign Agenda composition method"
        ),
        companion_method_note=_campaign_agenda_method_note(language),
        companion_panel=_campaign_agenda_panel(
            projection["campaign_agenda"], language
        ),
        latest_rows=latest_rows,
        latest_count=len(latest_observations),
        gateway_eyebrow="HISTORIQUE DISPONIBLE" if french else "HISTORY AVAILABLE",
        gateway_status=(
            f'{history_period["days"]} {"JOURS" if french else "DAYS"}'
        ),
        gateway_summary=(
            f'{len(issues)} {"ENJEUX SUIVIS" if french else "ISSUES TRACKED"}'
        ),
        gateway_period=_period(
            history_period["start_date"],
            history_period["end_date"],
            language,
        ),
        gateway_href="/enjeux/historique/" if french else "/en/issues/history/",
        gateway_label=(
            "EXPLORER L’HISTORIQUE →" if french else "EXPLORE HISTORY →"
        ),
    )


def _candidate_rows(
    issue: dict[str, Any],
    language: str,
    *,
    candidates: list[dict[str, Any]] | None = None,
) -> str:
    selected = (
        issue["current_candidate_associations"]["candidates"]
        if candidates is None
        else candidates
    )
    maximum = max(
        (
            candidate["item_count"]
            for candidate in issue["current_candidate_associations"]["candidates"]
        ),
        default=1,
    ) or 1

    rows = []

    for candidate in selected:
        name = _h(candidate["candidate_name"])
        routes = candidate["routes"]
        item_count = candidate["item_count"]
        magnitude = item_count / maximum

        label_items = (
            "article"
            if language == "fr" and item_count == 1
            else "articles"
            if language == "fr"
            else "item"
            if item_count == 1
            else "items"
        )

        route = (
            routes.get(language)
            if isinstance(routes, dict)
            else None
        )

        if route:
            identity = f'<a href="{_h(route)}">{name}</a>'
        else:
            identity = f'<span>{name}</span>'

        rows.append(
            f'<li data-item-count="{item_count}">{identity}'
            f'<strong>{item_count} {label_items}</strong>'
            f'<i class="issue-candidate-magnitude" '
            f'style="--issue-candidate-share:{magnitude:.6f}" aria-hidden="true"></i>'
            f'</li>'
        )

    return "\n".join(rows)


def _history_candidate_ledgers(issue: dict[str, Any], language: str) -> str:
    candidates = issue["historical_candidate_associations"]["candidates"]
    maximum = max(
        (candidate["association_count"] for candidate in candidates),
        default=1,
    ) or 1
    split = (len(candidates) + 1) // 2

    def ledger_rows(items: list[dict[str, Any]]) -> str:
        rows = []
        for candidate in items:
            routes = candidate["routes"]
            route = routes.get(language) if isinstance(routes, dict) else None
            name = _h(candidate["candidate_name"])
            identity = (
                f'<a href="{_h(route)}">{name}</a>'
                if route
                else f"<span>{name}</span>"
            )
            count = candidate["association_count"]
            association_label = "association" if count == 1 else "associations"
            period = _period(
                candidate["first_observation"],
                candidate["last_observation"],
                language,
            )
            rows.append(
                f'<li data-association-count="{count}">'
                f'<div class="issue-history-candidate-primary">{identity}'
                f'<strong>{count} {association_label}</strong></div>'
                f'<span class="issue-history-candidate-period">{_h(period)}</span>'
                f'<i class="issue-history-candidate-magnitude" '
                f'style="--issue-history-candidate-share:{count / maximum:.6f}" '
                f'aria-hidden="true"></i>'
                f'</li>'
            )
        return "\n".join(rows)

    return "".join(
        f'<ul class="issue-history-candidate-column '
        f'issue-history-candidate-column-{column_name}">'
        f'{ledger_rows(items)}</ul>'
        for column_name, items in (
            ("a", candidates[:split]),
            ("b", candidates[split:]),
        )
    )


def _subtopic_rows(issue: dict[str, Any], language: str) -> str:
    maximum = max((item["item_count"] for item in issue["subtopics"]), default=1)
    return "\n".join(
        f'<li><div><span>{_h(item["labels"][language])}</span><strong>{item["item_count"]}</strong></div><i style="--issue-subtopic-share:{item["item_count"] / maximum:.6f}"></i></li>'
        for item in issue["subtopics"]
    )


def _issue_note_tooltip(
    *,
    tooltip_id: str,
    label: str,
    content: str,
    warning: bool = False,
    align_end: bool = False,
) -> str:
    modifiers = ""
    if warning:
        modifiers += " is-warning"
    if align_end:
        modifiers += " is-align-end"
    return (
        f'<span class="issue-note-tooltip{modifiers}">'
        f'<button class="issue-note-tooltip-trigger" type="button" '
        f'aria-label="{_h(label)}" aria-describedby="{_h(tooltip_id)}">i</button>'
        f'<span class="issue-note-tooltip-body" id="{_h(tooltip_id)}" '
        f'role="tooltip">{_h(content)}</span>'
        f'</span>'
    )


def _current_activity_microbars(issue: dict[str, Any], language: str) -> str:
    coverage = issue["current_coverage"]
    comparison = coverage["comparison_7d"]
    series = coverage["evolution_30d"]
    maximum = max((point["item_count"] for point in series), default=0) or 1
    bars = []

    for point in series:
        point_date = point["date"]
        if comparison["previous_start"] <= point_date <= comparison["previous_end"]:
            period_class = "is-previous"
        elif comparison["latest_start"] <= point_date <= comparison["latest_end"]:
            period_class = "is-latest"
        elif point_date > comparison["latest_end"]:
            period_class = "is-partial"
        else:
            period_class = "is-older"

        value = point["item_count"]
        height = 4.0 if value == 0 else 18.0 + 82.0 * value / maximum
        unit = (
            "article" if language == "fr" and value == 1
            else "articles" if language == "fr"
            else "item" if value == 1
            else "items"
        )
        title = f"{_date(point_date, language)} · {value} {unit}"
        bars.append(
            f'<i class="issue-detail-activity-bar {period_class}" '
            f'data-date="{_h(point_date)}" style="--issue-bar:{height:.2f}%" '
            f'title="{_h(title)}"></i>'
        )

    aria = (
        "Activité quotidienne de couverture actuelle"
        if language == "fr"
        else "Daily current coverage activity"
    )
    return (
        f'<div class="issue-detail-activity-bars" '
        f'style="--issue-activity-columns:{len(series)}" role="img" '
        f'aria-label="{_h(aria)}">'
        + "".join(bars)
        + "</div>"
    )


def _compact_history_microbars(issue: dict[str, Any], language: str) -> str:
    history = issue["coverage_history"]
    series = history["daily"]
    maximum = max((point["item_count"] for point in series), default=0) or 1
    bars = []

    for point in series:
        value = point["item_count"]
        height = 4.0 if value == 0 else 16.0 + 84.0 * value / maximum
        unit = (
            "article" if language == "fr" and value == 1
            else "articles" if language == "fr"
            else "item" if value == 1
            else "items"
        )
        title = f"{_date(point['date'], language)} · {value} {unit}"
        bars.append(
            f'<i class="issue-compact-history-bar" '
            f'style="--issue-bar:{height:.2f}%" title="{_h(title)}"></i>'
        )

    aria = (
        "Profil historique compact de la couverture"
        if language == "fr"
        else "Compact historical coverage profile"
    )
    return (
        f'<div class="issue-compact-history-bars" '
        f'style="--issue-history-columns:{len(series)}" role="img" '
        f'aria-label="{_h(aria)}">'
        + "".join(bars)
        + "</div>"
    )


def _current_evidence(issue: dict[str, Any], language: str) -> str:
    visible = issue["evidence"][:8]
    archived = issue["evidence"][8:]
    rendered = [
        '<div class="issue-evidence-list issue-current-evidence-visible">',
        *(_evidence_row(item, language) for item in visible),
        "</div>",
    ]
    if archived:
        count = len(archived)
        summary = (
            f"{count} PREUVES ANTÉRIEURES"
            if language == "fr"
            else f"{count} EARLIER EVIDENCE ITEMS"
        )
        rendered.extend(
            (
                '<details class="issue-evidence-archive">',
                f"<summary>{summary}</summary>",
                '<div class="issue-evidence-list issue-current-evidence-archived">',
                *(_evidence_row(item, language) for item in archived),
                "</div>",
                "</details>",
            )
        )
    return "\n".join(rendered)



def _history_route(
    issue: dict[str, Any],
    language: str,
) -> str:
    if language == "fr":
        return (
            f"/enjeux/historique/"
            f"{issue['slugs']['fr']}/"
        )

    return (
        f"/en/issues/history/"
        f"{issue['slugs']['en']}/"
    )


def _history_hub_route(language: str) -> str:
    return (
        "/enjeux/historique/"
        if language == "fr"
        else "/en/issues/history/"
    )


def _history_heat_strip(
    issue: dict[str, Any],
    *,
    language: str,
    volume_maximum: int | None = None,
    share_maximum: float | None = None,
    dual_mode: bool = False,
) -> str:
    daily = issue["coverage_history"]["daily"]

    vmax = (
        volume_maximum
        if volume_maximum is not None
        else max(
            (
                point["item_count"]
                for point in daily
            ),
            default=0,
        )
    )

    smax = (
        share_maximum
        if share_maximum is not None
        else max(
            (
                point["corpus_share_percent"]
                for point in daily
            ),
            default=0.0,
        )
    )

    vscale = vmax or 1
    sscale = smax or 1.0

    cells = []

    for point in daily:
        volume = point["item_count"]
        share = point["corpus_share_percent"]

        volume_alpha = (
            0.045
            if volume == 0
            else 0.18 + 0.82 * (volume / vscale)
        )

        share_alpha = (
            0.045
            if share == 0
            else 0.18 + 0.82 * (share / sscale)
        )

        date_label = _date(
            point["date"],
            language,
        )

        if language == "fr":
            title = (
                f"{date_label} · "
                f"{volume} articles · "
                f"{share:.2f} % du corpus"
            )
        else:
            title = (
                f"{date_label} · "
                f"{volume} items · "
                f"{share:.2f}% of corpus"
            )

        if dual_mode:
            cell = (
                '<span class="issue-history-heat-cell" '
                f'title="{_h(title)}">'
                '<i data-history-series="volume" '
                f'style="--issue-history-heat:'
                f'{volume_alpha:.3f}"></i>'
                '<i data-history-series="share" '
                f'style="--issue-history-heat:'
                f'{share_alpha:.3f}" '
                'hidden></i>'
                '</span>'
            )
        else:
            cell = (
                '<span '
                'class="issue-history-heat-cell" '
                f'style="--issue-history-heat:'
                f'{volume_alpha:.3f}" '
                f'title="{_h(title)}">'
                '</span>'
            )

        cells.append(cell)

    aria = (
        "Profil quotidien historique de couverture"
        if language == "fr"
        else "Daily historical coverage profile"
    )

    return (
        '<div class="issue-history-heat-strip" '
        f'role="img" '
        f'aria-label="{_h(aria)}">'
        + "".join(cells)
        + "</div>"
    )


def _history_monitor_row(
    issue: dict[str, Any],
    language: str,
) -> str:
    history = issue["coverage_history"]
    associations = (
        issue["historical_candidate_associations"]
    )

    label = _localized(
        issue,
        language,
    )

    first = _date(
        history["first_observation"],
        language,
    )

    latest = _date(
        history["last_observation"],
        language,
    )

    peak = (
        f'{history["peak"]["item_count"]} · '
        f'{_date(history["peak"]["date"], language)}'
    )

    route = _history_route(
        issue,
        language,
    )

    return f'''<article
      class="issue-history-monitor-row"
      data-issue-row
      data-name="{_h(label.casefold())}"
      data-state="{_h(issue["lifecycle"])}">
      <button
        class="issue-history-monitor-select"
        type="button"
        data-issue-select
        data-label="{_h(label)}"
        data-state="{_h(issue["lifecycle"])}"
        data-state-label="{_h(_lifecycle_label(issue["lifecycle"], language))}"
        data-items="{history["total_item_count"]}"
        data-publishers="{history["active_day_count"]}"
        data-days="{history["peak"]["item_count"]}"
        data-candidates="{associations["candidate_count"]}"
        data-history-items="{_h(first)}"
        data-history-days="{_h(latest)}"
        data-subtopics="—"
        data-latest="{_h(latest)}"
        data-history-start="{_h(first)}"
        data-history-peak="{_h(peak)}"
        data-href="{_h(route)}">
        <span class="issue-history-monitor-name">{_h(label)}</span>
        {_history_heat_strip(issue, language=language)}
        <span class="issue-history-monitor-number">
          <strong>{history["total_item_count"]}</strong>
          <small>{"ARTICLES" if language == "fr" else "ITEMS"}</small>
        </span>
        <span class="issue-history-monitor-number">
          <strong>{history["active_day_count"]}</strong>
          <small>{"JOURS ACTIFS" if language == "fr" else "ACTIVE DAYS"}</small>
        </span>
        <span class="issue-history-monitor-number">
          <strong>{history["peak"]["item_count"]}</strong>
          <small>{"PIC" if language == "fr" else "PEAK"}</small>
        </span>
        <span class="issue-history-monitor-latest">
          <small>{"DERNIÈRE OBS." if language == "fr" else "LATEST OBS."}</small>
          <strong>{_h(latest)}</strong>
        </span>
      </button>
      <a
        class="issue-row-link"
        href="{_h(route)}">
        {"OUVRIR →" if language == "fr" else "OPEN →"}
      </a>
    </article>'''


def _history_inspector(
    issue: dict[str, Any],
    language: str,
) -> str:
    history = issue["coverage_history"]

    associations = (
        issue["historical_candidate_associations"]
    )

    first = _date(
        history["first_observation"],
        language,
    )

    latest = _date(
        history["last_observation"],
        language,
    )

    peak = (
        f'{history["peak"]["item_count"]} · '
        f'{_date(history["peak"]["date"], language)}'
    )

    if language == "fr":
        words = (
            "ARTICLES · HISTORIQUE",
            "JOURS ACTIFS",
            "PIC JOURNALIER",
            "CANDIDATS ASSOCIÉS",
            "PREMIÈRE OBS.",
            "DERNIÈRE OBS.",
            "OUVRIR LE DOSSIER HISTORIQUE →",
        )
    else:
        words = (
            "ITEMS · HISTORY",
            "ACTIVE DAYS",
            "DAILY PEAK",
            "ASSOCIATED CANDIDATES",
            "FIRST OBS.",
            "LATEST OBS.",
            "OPEN HISTORY DOSSIER →",
        )

    return f'''<div
      class="issue-inspector-content"
      id="issue-inspector-content">
      <div class="issue-inspector-title-row">
        <h3 data-inspector-label>{_h(_localized(issue, language))}</h3>
        <span
          class="issue-state is-{_h(issue["lifecycle"])}"
          data-inspector-state>
          {_h(_lifecycle_label(issue["lifecycle"], language))}
        </span>
      </div>

      <dl class="issue-inspector-grid">
        <div>
          <dt>{words[0]}</dt>
          <dd data-inspector-items>{history["total_item_count"]}</dd>
        </div>
        <div>
          <dt>{words[1]}</dt>
          <dd data-inspector-publishers>{history["active_day_count"]}</dd>
        </div>
        <div>
          <dt>{words[2]}</dt>
          <dd data-inspector-days>{history["peak"]["item_count"]}</dd>
        </div>
        <div>
          <dt>{words[3]}</dt>
          <dd data-inspector-candidates>{associations["candidate_count"]}</dd>
        </div>
        <div>
          <dt>{words[4]}</dt>
          <dd data-inspector-history-items>{_h(first)}</dd>
        </div>
        <div>
          <dt>{words[5]}</dt>
          <dd data-inspector-history-days>{_h(latest)}</dd>
        </div>
      </dl>

      <div class="issue-history-inspector-hidden" hidden>
        <span data-inspector-subtopics>—</span>
        <span data-inspector-latest>{_h(latest)}</span>
        <span data-inspector-history-start>{_h(first)}</span>
        <span data-inspector-history-peak>{_h(peak)}</span>
      </div>

      <a
        class="issue-inspector-open"
        data-inspector-link
        href="{_h(_history_route(issue, language))}">
        {words[6]}
      </a>
    </div>'''


def _history_evolution_matrix(
    issues: list[dict[str, Any]],
    language: str,
) -> str:
    vmax = max(
        (
            point["item_count"]
            for issue in issues
            for point
            in issue["coverage_history"]["daily"]
        ),
        default=0,
    )

    smax = max(
        (
            point["corpus_share_percent"]
            for issue in issues
            for point
            in issue["coverage_history"]["daily"]
        ),
        default=0.0,
    )

    period = (
        issues[0]["coverage_history"]["daily"]
    )

    rows = []

    for issue in issues:
        history = issue["coverage_history"]

        rows.append(
            f'''<article class="issue-history-evolution-row">
              <a
                class="issue-evolution-name"
                href="{_h(_history_route(issue, language))}">
                {_h(_localized(issue, language))}
              </a>
              {_history_heat_strip(
                  issue,
                  language=language,
                  volume_maximum=vmax,
                  share_maximum=smax,
                  dual_mode=True,
              )}
              <div class="issue-evolution-total">
                <strong>{history["total_item_count"]}</strong>
                <small>{"ARTICLES" if language == "fr" else "ITEMS"}</small>
              </div>
            </article>'''
        )

    return f'''<div
      class="issue-history-matrix"
      data-history-panel
      data-volume-maximum="{vmax}"
      data-share-maximum="{smax:.2f}">
      <div class="issue-history-toolbar">
        <div
          class="polling-segments issue-history-modes"
          aria-label="{"Mode de l’historique" if language == "fr" else "History mode"}">
          <button
            type="button"
            data-history-mode="volume"
            aria-pressed="true">
            VOLUME
          </button>
          <button
            type="button"
            data-history-mode="share"
            aria-pressed="false">
            {"PART DU CORPUS" if language == "fr" else "CORPUS SHARE"}
          </button>
        </div>
        <span data-history-unit>
          {"ARTICLES PAR JOUR" if language == "fr" else "ITEMS PER DAY"}
        </span>
      </div>

      <div class="issue-history-matrix-period">
        <span>{_h(_date(period[0]["date"], language))}</span>
        <strong data-history-scale>
          0–{vmax} {"articles" if language == "fr" else "items"}
        </strong>
        <span>{_h(_date(period[-1]["date"], language))}</span>
      </div>

      <div class="issue-history-evolution-rows">
        {''.join(rows)}
      </div>
    </div>'''


def _history_daily_table(
    issue: dict[str, Any],
    language: str,
) -> str:
    rows = []

    for point in issue["coverage_history"]["daily"]:
        labels = (
            ("DATE", "ARTICLES", "MÉDIAS", "CORPUS", "PART")
            if language == "fr"
            else ("DATE", "ITEMS", "PUBLISHERS", "CORPUS", "SHARE")
        )
        rows.append(
            f'''<tr>
              <td data-label="{labels[0]}">
                <time datetime="{_h(point["date"])}">
                  {_h(_date(point["date"], language))}
                </time>
              </td>
              <td data-label="{labels[1]}">{point["item_count"]}</td>
              <td data-label="{labels[2]}">{point["publisher_count"]}</td>
              <td data-label="{labels[3]}">{point["corpus_item_count"]}</td>
              <td data-label="{labels[4]}">{point["corpus_share_percent"]:.2f}%</td>
            </tr>'''
        )

    return f'''<div class="issue-history-table-wrap issue-history-daily-ledger">
      <table class="issue-history-table">
        <thead>
          <tr>
            <th>DATE</th>
            <th>{"ARTICLES" if language == "fr" else "ITEMS"}</th>
            <th>{"MÉDIAS" if language == "fr" else "PUBLISHERS"}</th>
            <th>CORPUS</th>
            <th>{"PART" if language == "fr" else "SHARE"}</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>'''


def _historical_evidence(
    projection: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    period = projection["coverage_history"]["period"]
    start = period["start_date"]
    end = period["end_date"]
    merged: dict[tuple[str, str], dict[str, Any]] = {}

    for issue in projection["issues"]:
        for item in issue["evidence"]:
            if not start <= item["date"] <= end:
                continue
            key = (item["id"], item["url"])
            observed = merged.setdefault(
                key,
                {
                    **item,
                    "issue_ids": [],
                },
            )
            observed["issue_ids"].append(issue["issue_id"])

    issue_order = {
        issue["issue_id"]: index
        for index, issue in enumerate(projection["issues"])
    }
    rows = []
    for item in merged.values():
        item["issue_ids"] = sorted(
            set(item["issue_ids"]),
            key=issue_order.__getitem__,
        )
        rows.append(item)
    rows.sort(
        key=lambda item: (
            item["date"],
            item.get("published_at", ""),
            item["id"],
        ),
        reverse=True,
    )
    if len(rows) < limit:
        raise IssuePageBuildError(
            f"historical hub needs {limit} source-linked observations; found {len(rows)}"
        )
    return rows[:limit]


def _historical_movement_method_note(
    comparison: dict[str, Any],
    language: str,
) -> str:
    previous = _period(
        comparison["previous_start"],
        comparison["previous_end"],
        language,
    )
    latest = _period(
        comparison["latest_start"],
        comparison["latest_end"],
        language,
    )
    if language == "fr":
        return (
            "Incidence historique = articles de l’enjeu ÷ articles uniques du "
            "corpus accepté dans chaque fenêtre. Deux fenêtres adjacentes de 28 "
            f"jours UTC complets sont comparées : {previous}, puis {latest}. "
            "Les enjeux sont multi-étiquettes : les pourcentages peuvent se chevaucher."
        )
    return (
        "Historical incidence = issue items ÷ unique accepted corpus items in each "
        "window. Two adjacent 28-day windows of complete UTC days are compared: "
        f"{previous}, then {latest}. Issues are multi-label, so percentages can overlap."
    )


def _historical_cadence_method_note(
    comparison: dict[str, Any],
    language: str,
) -> str:
    previous = _period(
        comparison["previous_start"],
        comparison["previous_end"],
        language,
    )
    latest = _period(
        comparison["latest_start"],
        comparison["latest_end"],
        language,
    )
    if language == "fr":
        return (
            "Aucun historique de l’Agenda de campagne à étiquette unique n’est "
            "disponible dans cette source. Ce panneau compare à la place les "
            "jours UTC avec au moins un article par enjeu, sur les mêmes fenêtres : "
            f"{previous} et {latest}. Les barres répartissent les jours-enjeux actifs."
        )
    return (
        "This source contains no historical single-label Campaign Agenda series. "
        "This panel instead compares UTC days with at least one item for each issue "
        f"over the same windows: {previous} and {latest}. Bars distribute active issue-days."
    )


def _historical_cadence_summary(
    issues: list[dict[str, Any]],
    comparison: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    previous_total = sum(
        comparison["issues"][issue["issue_id"]]["previous_active_days"]
        for issue in issues
    )
    latest_total = sum(
        comparison["issues"][issue["issue_id"]]["latest_active_days"]
        for issue in issues
    )
    topics = []
    for position, issue in enumerate(issues):
        values = comparison["issues"][issue["issue_id"]]
        previous = values["previous_active_days"]
        latest = values["latest_active_days"]
        topics.append(
            {
                "id": issue["issue_id"],
                "label": _localized(issue, language),
                "position": position,
                "previous_share": previous / previous_total if previous_total else 0.0,
                "latest_share": latest / latest_total if latest_total else 0.0,
            }
        )
    return {
        "previous_start": comparison["previous_start"],
        "previous_end": comparison["previous_end"],
        "latest_start": comparison["latest_start"],
        "latest_end": comparison["latest_end"],
        "previous_total": previous_total,
        "latest_total": latest_total,
        "topics": topics,
    }


def render_history_hub(
    projection: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
) -> bytes:
    french = language == "fr"
    issues = projection["issues"]
    if not issues:
        raise IssuePageBuildError("cannot render an empty historical issue hub")

    history_meta = projection["coverage_history"]
    period = history_meta["period"]
    corpus = history_meta["corpus"]
    comparison = _history_comparison_projection(projection)
    issues_by_id = {issue["issue_id"]: issue for issue in issues}
    route = _history_hub_route(language)
    canonical = f"https://france2027.app{route}"
    canonical_fr = "https://france2027.app/enjeux/historique/"
    canonical_en = "https://france2027.app/en/issues/history/"
    title = (
        "Historique des enjeux 2027 | France 2027"
        if french
        else "France 2027 Issue History | Issues Lab"
    )
    description = (
        "Historique sourcé de la couverture des enjeux de la présidentielle française de 2027."
        if french
        else "Source-linked historical issue coverage for France's 2027 presidential race."
    )
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical,
        "inLanguage": language,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(issues),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": _localized(issue, language),
                    "url": (
                        "https://france2027.app"
                        + _history_route(issue, language)
                    ),
                }
                for index, issue in enumerate(issues, start=1)
            ],
        },
    }
    head = _head(
        language=language,
        title=title,
        description=description,
        canonical=canonical,
        canonical_fr=canonical_fr,
        canonical_en=canonical_en,
        favicon=favicon,
        og_image=og_image,
        structured=[
            collection,
            _breadcrumb_json(language=language, canonical=canonical),
        ],
    )
    header = _prepare_header(
        shell["header"],
        language=language,
        route_fr="/enjeux/historique/",
        route_en="/en/issues/history/",
    )
    landscape_issues = sorted(
        issues,
        key=lambda issue: (
            -comparison["issues"][issue["issue_id"]]["latest_incidence"],
            -comparison["issues"][issue["issue_id"]]["latest_item_count"],
            _localized(issue, language).casefold(),
        ),
    )
    issue_cards = "\n".join(
        _issue_card(
            issue,
            language,
            history_comparison=comparison["issues"][issue["issue_id"]],
        )
        for issue in landscape_issues
    )
    evidence = _historical_evidence(projection)
    latest_rows = "\n".join(
        _hub_evidence_row(
            item,
            issues_by_id=issues_by_id,
            language=language,
            history=True,
        )
        for item in evidence
    )
    period_text = _period(
        period["start_date"],
        period["end_date"],
        language,
    )
    current_period_text = _period(
        projection["period"]["start"],
        projection["period"]["end"],
        language,
    )
    historical_assignments = sum(
        issue["coverage_history"]["total_item_count"]
        for issue in issues
    )
    cadence = _historical_cadence_summary(
        issues,
        comparison,
        language,
    )

    copy = {
        "home": "ACCUEIL" if french else "HOME",
        "breadcrumb": "HISTORIQUE" if french else "HISTORY",
        "eyebrow": "ENJEUX · HISTORIQUE" if french else "ISSUES · HISTORY",
        "title": "HISTORIQUE DES ENJEUX" if french else "ISSUE HISTORY",
        "descriptor": (
            "Couverture historique article-dérivée sur des jours UTC complets. "
            "Les enjeux sont multi-étiquettes et ne décrivent ni position, ni soutien, "
            "ni priorité politique d’un candidat. Cartes : volume historique, jours "
            "observés et pic journalier. Tri : Activité = incidence des 28 derniers "
            "jours complets ; Mouvement = variation absolue face aux 28 jours "
            "précédents ; Volume = total historique ; A–Z = libellé."
            if french
            else "Article-derived historical coverage over complete UTC days. "
            "Issues are multi-label and do not describe candidate positions, "
            "endorsements, or priorities. Cards show historical volume, observed "
            "days, and the daily peak. Sorts: Activity = incidence in the latest "
            "28 complete days; Movement = absolute change versus the prior 28 days; "
            "Volume = historical total; A–Z = label."
        ),
        "metric_issues": "ENJEUX" if french else "ISSUES",
        "metric_items": (
            "ASSIGNATIONS D’ENJEU" if french else "ISSUE ASSIGNMENTS"
        ),
        "metric_publishers": (
            "ARTICLES · CORPUS" if french else "CORPUS ITEMS"
        ),
        "metric_candidates": (
            "MÉDIAS · CORPUS" if french else "CORPUS PUBLISHERS"
        ),
        "metric_period": "PÉRIODE" if french else "PERIOD",
        "landscape": (
            "PAYSAGE HISTORIQUE DES ENJEUX"
            if french
            else "HISTORICAL ISSUE LANDSCAPE"
        ),
        "search": (
            "Rechercher un enjeu historique"
            if french
            else "Search historical issues"
        ),
        "sort_activity": "ACTIVITÉ" if french else "ACTIVITY",
        "sort_movement": "MOUVEMENT" if french else "MOVEMENT",
        "sort_volume": "VOLUME",
        "sort_az": "A–Z",
        "moving": (
            "ÉVOLUTION HISTORIQUE"
            if french
            else "HISTORICAL MOVEMENT"
        ),
        "campaign_agenda": (
            "CADENCE DE COUVERTURE"
            if french
            else "COVERAGE CADENCE"
        ),
        "latest": (
            "OBSERVATIONS HISTORIQUES SOURCÉES"
            if french
            else "SOURCE-LINKED HISTORICAL OBSERVATIONS"
        ),
        "history": "ENJEUX ACTUELS" if french else "CURRENT ISSUES",
    }

    breadcrumb = (
        f'<nav class="polling-breadcrumb" aria-label="{"Fil d’Ariane" if french else "Breadcrumb"}">'
        f'<a href="{"/" if french else "/en/"}">{copy["home"]}</a>'
        f'<span aria-hidden="true">/</span>'
        f'<a href="{"/enjeux/" if french else "/en/issues/"}">'
        f'{"ENJEUX" if french else "ISSUES"}</a>'
        f'<span aria-hidden="true">/</span>'
        f'<span aria-current="page">{copy["breadcrumb"]}</span></nav>'
    )

    return _render_issue_hub_document(
        language=language,
        head=head,
        header=header,
        footer=shell["footer"],
        body_classes=(
            "polling-page issues-page issues-hub-page issues-history-page"
        ),
        breadcrumb=breadcrumb,
        copy=copy,
        descriptor_label=(
            "Méthode de l’historique des enjeux"
            if french
            else "Issue history method"
        ),
        metrics_label=(
            "Couverture historique des enjeux"
            if french
            else "Historical issue coverage"
        ),
        metric_values=(
            len(issues),
            historical_assignments,
            corpus["total_item_count"],
            corpus["publisher_count"],
            period_text,
        ),
        landscape_eyebrow=(
            f'{period["days"]} J UTC'
            if french
            else f'{period["days"]} UTC DAYS'
        ),
        landscape_status=(
            f'{len(issues)} {copy["metric_issues"]} · {period["days"]} J'
            if french
            else f'{len(issues)} {copy["metric_issues"]} · {period["days"]} DAYS'
        ),
        issue_cards=issue_cards,
        movement_eyebrow=(
            "COMPARAISON · JOURS UTC COMPLETS"
            if french
            else "COMPARISON · COMPLETE UTC DAYS"
        ),
        movement_status="INCIDENCE",
        movement_method_label=(
            "Méthode de comparaison historique"
            if french
            else "Historical comparison method"
        ),
        movement_method_note=_historical_movement_method_note(
            comparison,
            language,
        ),
        movement_chart=_movement_chart(
            issues,
            language,
            history_comparison=comparison,
        ),
        companion_eyebrow=(
            "SUBSTITUT HISTORIQUE DÉFENDABLE"
            if french
            else "DEFENSIBLE HISTORICAL SUBSTITUTE"
        ),
        companion_status=(
            "MULTI-ÉTIQUETTES" if french else "MULTI-LABEL"
        ),
        companion_method_label=(
            "Pourquoi la cadence remplace l’Agenda de campagne"
            if french
            else "Why cadence replaces Campaign Agenda"
        ),
        companion_method_note=_historical_cadence_method_note(
            comparison,
            language,
        ),
        companion_panel=_campaign_agenda_panel(
            cadence,
            language,
            historical_cadence=True,
        ),
        latest_rows=latest_rows,
        latest_count=len(evidence),
        gateway_eyebrow=(
            "PROJECTION ACTUELLE" if french else "CURRENT PROJECTION"
        ),
        gateway_status="30 J" if french else "30D",
        gateway_summary=(
            "REVENIR AUX 30 DERNIERS JOURS"
            if french
            else "RETURN TO THE LATEST 30 DAYS"
        ),
        gateway_period=current_period_text,
        gateway_href="/enjeux/" if french else "/en/issues/",
        gateway_label=(
            "VOIR LES ENJEUX ACTUELS →"
            if french
            else "VIEW CURRENT ISSUES →"
        ),
    )




def _history_detail_bars(
    issue: dict[str, Any],
    language: str,
) -> str:
    history = issue["coverage_history"]
    daily = history["daily"]

    volume_max = max(
        (point["item_count"] for point in daily),
        default=0,
    ) or 1

    share_max = max(
        (point["corpus_share_percent"] for point in daily),
        default=0.0,
    ) or 1.0

    cells = []
    aria_values = []

    for point in daily:
        volume = point["item_count"]
        share = point["corpus_share_percent"]

        volume_height = (
            3.0
            if volume == 0
            else 14.0 + 86.0 * volume / volume_max
        )

        share_height = (
            3.0
            if share == 0
            else 14.0 + 86.0 * share / share_max
        )

        date_label = _date(point["date"], language)

        unit = (
            "article"
            if language == "fr" and volume == 1
            else "articles"
            if language == "fr"
            else "item"
            if volume == 1
            else "items"
        )

        share_suffix = (
            "du corpus"
            if language == "fr"
            else "of corpus"
        )

        title = (
            f"{date_label} · {volume} {unit} · "
            f"{share:.2f}% {share_suffix}"
        )

        aria_values.append(
            f"{point['date']}: {volume}"
        )

        cells.append(
            '<span class="issue-history-detail-bar" '
            f'title="{_h(title)}">'
            '<i data-history-series="volume" '
            f'style="--issue-history-bar:{volume_height:.2f}%"></i>'
            '<i data-history-series="share" '
            f'style="--issue-history-bar:{share_height:.2f}%" '
            'hidden></i>'
            '</span>'
        )

    mode_label = (
        "Mode de l’historique"
        if language == "fr"
        else "History mode"
    )

    share_label = (
        "PART DU CORPUS"
        if language == "fr"
        else "CORPUS SHARE"
    )

    unit_label = (
        "ARTICLES PAR JOUR"
        if language == "fr"
        else "ITEMS PER DAY"
    )

    scale_unit = (
        "articles"
        if language == "fr"
        else "items"
    )

    aria = (
        "Historique quotidien des articles : "
        if language == "fr"
        else "Daily historical items: "
    ) + ", ".join(aria_values)

    return (
        '<div class="issue-history-visual is-detail" '
        'data-history-panel '
        f'data-volume-maximum="{volume_max}" '
        f'data-share-maximum="{share_max:.2f}">'
        '<div class="issue-history-toolbar">'
        '<div class="polling-segments issue-history-modes" '
        f'aria-label="{_h(mode_label)}">'
        '<button type="button" data-history-mode="volume" '
        'aria-pressed="true">VOLUME</button>'
        '<button type="button" data-history-mode="share" '
        f'aria-pressed="false">{_h(share_label)}</button>'
        '</div>'
        f'<span data-history-unit>{_h(unit_label)}</span>'
        '</div>'
        '<div class="issue-history-detail-bars" '
        f'style="--issue-history-columns:{len(daily)}" '
        f'role="img" aria-label="{_h(aria)}">'
        + "".join(cells)
        + '</div>'
        '<div class="issue-history-axis">'
        f'<span>{_h(_date(daily[0]["date"], language))}</span>'
        f'<strong data-history-scale>0–{volume_max} {_h(scale_unit)}</strong>'
        f'<span>{_h(_date(daily[-1]["date"], language))}</span>'
        '</div>'
        '</div>'
    )


def _history_peak_days(
    issue: dict[str, Any],
    language: str,
    *,
    limit: int = 5,
) -> str:
    active = [
        point
        for point in issue["coverage_history"]["daily"]
        if point["item_count"] > 0
    ]

    ranked = sorted(
        active,
        key=lambda point: (
            -point["item_count"],
            point["date"],
        ),
    )[:limit]

    if not ranked:
        return (
            '<p class="issue-detail-note">'
            + (
                "Aucun jour actif observé."
                if language == "fr"
                else "No active day observed."
            )
            + "</p>"
        )

    maximum = ranked[0]["item_count"] or 1
    rows = []

    for point in ranked:
        count = point["item_count"]
        date_label = _date(point["date"], language)

        unit = (
            "article"
            if language == "fr" and count == 1
            else "articles"
            if language == "fr"
            else "item"
            if count == 1
            else "items"
        )

        share_suffix = (
            "du corpus"
            if language == "fr"
            else "of corpus"
        )

        title = (
            f"{date_label} · {count} {unit} · "
            f"{point['corpus_share_percent']:.2f}% {share_suffix}"
        )

        rows.append(
            f'<li data-peak-day="{_h(point["date"])}" '
            f'title="{_h(title)}">'
            '<div class="issue-history-peak-day-primary">'
            f'<time datetime="{_h(point["date"])}">{_h(date_label)}</time>'
            f'<strong>{count}</strong>'
            '</div>'
            '<i class="issue-history-peak-day-magnitude" '
            f'style="--issue-history-peak-share:{count / maximum:.6f}" '
            'aria-hidden="true"></i>'
            '</li>'
        )

    return (
        '<ol class="issue-history-peak-days">'
        + "".join(rows)
        + "</ol>"
    )


def render_history_detail(
    projection: dict[str, Any],
    issue: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
) -> bytes:
    french = language == "fr"

    label = _localized(
        issue,
        language,
    )

    history = issue["coverage_history"]
    historical = (
        issue["historical_candidate_associations"]
    )

    route = _history_route(
        issue,
        language,
    )

    canonical = (
        "https://france2027.app"
        + route
    )

    canonical_fr = (
        "https://france2027.app"
        + _history_route(issue, "fr")
    )

    canonical_en = (
        "https://france2027.app"
        + _history_route(issue, "en")
    )

    title = (
        f"Historique — {label} | France 2027"
        if french
        else f"{label} — Coverage history | France 2027"
    )

    description = (
        f"Historique sourcé de la couverture de {label} depuis "
        f"{_date(history['first_observation'], language)}."
        if french
        else
        f"Source-linked coverage history for {label} since "
        f"{_date(history['first_observation'], language)}."
    )

    head = _head(
        language=language,
        title=title,
        description=description,
        canonical=canonical,
        canonical_fr=canonical_fr,
        canonical_en=canonical_en,
        favicon=favicon,
        og_image=og_image,
        structured=[
            _breadcrumb_json(
                language=language,
                canonical=canonical,
            )
        ],
    )

    header = _prepare_header(
        shell["header"],
        language=language,
        route_fr=_history_route(
            issue,
            "fr",
        ),
        route_en=_history_route(
            issue,
            "en",
        ),
    )

    denominator_note = (
        projection["coverage_history"][
            "denominator"
        ][
            "note_fr"
            if french
            else "note_en"
        ]
    )
    method_label = "Note méthodologique" if french else "Method note"
    denominator_tooltip = _issue_note_tooltip(
        tooltip_id="issue-history-denominator-note",
        label=method_label,
        content=denominator_note,
)
    candidate_note = (
        "Une association indique qu’un candidat et cet enjeu apparaissent "
        "dans la même couverture retenue. Elle ne décrit ni soutien, ni "
        "opposition, ni priorité, ni idéologie, ni position politique, ni "
        "engagement de programme."
        if french
        else "An association means that a candidate and this issue appear "
        "in the same retained coverage. It does not imply support, opposition, "
        "priority, ideology, a political position, or a programme or manifesto "
        "commitment."
    )
    candidate_tooltip = _issue_note_tooltip(
        tooltip_id="issue-history-candidate-note",
        label="Note d’association" if french else "Association note",
        content=candidate_note,
        warning=True,
    )
    candidate_ledgers = _history_candidate_ledgers(issue, language)
    observation_count = len(history["daily"])
    peak_day_count = min(
        5,
        sum(
            1
            for point in history["daily"]
            if point["item_count"] > 0
        ),
    )

    document = f'''<!doctype html>
<html lang="{language}">
{head}
<body class="polling-page poll-detail-page issues-page issue-detail-page issue-history-detail-page">
  <main class="polling-shell">
{header}

    <div class="poll-detail-content">

      <nav
        class="poll-detail-breadcrumb"
        aria-label="{"Fil d’Ariane" if french else "Breadcrumb"}">
        <a href="{"/" if french else "/en/"}">
          {"ACCUEIL" if french else "HOME"}
        </a>

        <span
          class="poll-detail-breadcrumb-separator"
          aria-hidden="true">/</span>

        <a href="{"/enjeux/" if french else "/en/issues/"}">
          {"ENJEUX" if french else "ISSUES"}
        </a>

        <span
          class="poll-detail-breadcrumb-separator"
          aria-hidden="true">/</span>

        <a href="{_h(_history_hub_route(language))}">
          {"HISTORIQUE" if french else "HISTORY"}
        </a>

        <span
          class="poll-detail-breadcrumb-separator"
          aria-hidden="true">/</span>

        <span aria-current="page">
          {_h(label)}
        </span>
      </nav>

      <section class="poll-detail-hero issue-detail-hero" aria-labelledby="issue-history-title">
        <div class="poll-detail-hero-main">
          <div>
            <div class="poll-detail-eyebrow">
              {"ENJEU · HISTORIQUE" if french else "ISSUE · HISTORY"}
            </div>

            <div class="poll-detail-title-line">
              <h1 class="poll-detail-title" id="issue-history-title">
                {_h(label)}
              </h1>

              <span
                class="issue-state is-{_h(issue["lifecycle"])}">
                {_h(_lifecycle_label(issue["lifecycle"], language))}
              </span>
            </div>
          </div>

        </div>

        <div class="poll-detail-metrics">
          <div class="poll-detail-metric">
            <span>
              {"ARTICLES · HISTORIQUE" if french else "ITEMS · HISTORY"}
            </span>
            <strong>{history["total_item_count"]}</strong>
          </div>

          <div class="poll-detail-metric">
            <span>
              {"JOURS ACTIFS" if french else "ACTIVE DAYS"}
            </span>
            <strong>{history["active_day_count"]}</strong>
          </div>

          <div class="poll-detail-metric">
            <span>
              {"PIC JOURNALIER" if french else "DAILY PEAK"}
            </span>
            <strong>{history["peak"]["item_count"]}</strong>
          </div>

          <div class="poll-detail-metric">
            <span>
              {"PREMIÈRE OBS." if french else "FIRST OBS."}
            </span>
            <strong>
              {_h(_date(history["first_observation"], language))}
            </strong>
          </div>

          <div class="poll-detail-metric poll-detail-metric-fieldwork">
            <span>
              {"DERNIÈRE OBS." if french else "LATEST OBS."}
            </span>
            <strong>
              {_h(_date(history["last_observation"], language))}
            </strong>
          </div>
        </div>

      </section>

      <div class="issue-history-detail-grid issue-history-detail-top-grid">
        <section class="poll-detail-panel issue-history-detail-evolution" aria-labelledby="issue-history-coverage-title">
          <div class="poll-detail-panel-head">
            <div>
              <div class="poll-detail-eyebrow">LONGITUDINAL</div>
              <div class="issue-note-title-line">
                <h2 id="issue-history-coverage-title">
                  {"HISTORIQUE DE LA COUVERTURE" if french else "COVERAGE HISTORY"}
                </h2>
                {denominator_tooltip}
              </div>
            </div>
            <span class="poll-detail-panel-status">
              {history["active_day_count"]}
              {" JOURS ACTIFS" if french else " ACTIVE DAYS"}
            </span>
          </div>
          {_history_detail_bars(issue, language)}
        </section>

        <aside class="poll-detail-panel issue-history-context issue-history-peaks" aria-labelledby="issue-history-peaks-title">
          <div class="poll-detail-panel-head">
            <div>
              <div class="poll-detail-eyebrow">
                {"REPÈRES" if french else "HIGHLIGHTS"}
              </div>
              <h2 id="issue-history-peaks-title">
                {"JOURS MARQUANTS" if french else "PEAK DAYS"}
              </h2>
            </div>
            <span class="poll-detail-panel-status">
              {peak_day_count} {"JOURS" if french else "DAYS"}
            </span>
          </div>
          {_history_peak_days(issue, language)}
        </aside>
      </div>

      <section class="poll-detail-panel issue-history issue-history-candidates" aria-labelledby="issue-history-candidates-title">
        <div class="poll-detail-panel-head">
          <div>
            <div class="poll-detail-eyebrow">
              {"DOMAINE SÉPARÉ" if french else "SEPARATE DOMAIN"}
            </div>
            <div class="issue-note-title-line">
              <h2 id="issue-history-candidates-title">
                {"HISTORIQUE DES ASSOCIATIONS CANDIDAT × ENJEU" if french else "CANDIDATE × ISSUE ASSOCIATION HISTORY"}
              </h2>
              {candidate_tooltip}
            </div>
          </div>
          <span class="poll-detail-panel-status">
            {historical["candidate_count"]} {"CANDIDATS" if french else "CANDIDATES"}
          </span>
        </div>
        <div class="issue-history-candidate-ledgers">
          {candidate_ledgers}
        </div>
      </section>

      <section class="poll-detail-panel issue-history-daily" aria-labelledby="issue-history-daily-title">
        <div class="poll-detail-panel-head">
          <div>
            <div class="poll-detail-eyebrow">
              {"DONNÉES" if french else "DATA"}
            </div>
            <h2 id="issue-history-daily-title">
              {"REGISTRE JOUR PAR JOUR" if french else "DAY-BY-DAY LEDGER"}
            </h2>
          </div>
          <span class="poll-detail-panel-status">
            {observation_count} {"JOURS" if french else "DAYS"}
          </span>
        </div>
        {_history_daily_table(issue, language)}
      </section>

      <div class="issue-history-detail-actions">
        <a
          class="poll-detail-back-cta issue-history-current-cta"
          href="{_h(issue["routes"][language])}">
          {"VOIR L’ÉTAT ACTUEL →" if french else "VIEW CURRENT STATE →"}
        </a>

        <a
          class="poll-detail-back-cta issue-history-hub-cta"
          href="{_h(_history_hub_route(language))}">
          {"TOUT L’HISTORIQUE DES ENJEUX →" if french else "ALL ISSUE HISTORY →"}
        </a>
      </div>

    </div>

{shell["footer"]}
  </main>
</body>
</html>'''

    return (
        "\n".join(
            line.rstrip()
            for line in document.splitlines()
        )
        + "\n"
    ).encode("utf-8")


def render_detail(
    projection: dict[str, Any],
    issue: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
) -> bytes:
    french = language == "fr"
    label = _localized(issue, language)
    canonical = issue["canonical"][language]
    coverage = issue["current_coverage"]
    comparison = coverage["comparison_7d"]
    coverage_history = issue["coverage_history"]
    current_associations = issue["current_candidate_associations"]
    title = (
        f"{label} — Enjeu 2027 | France 2027"
        if french
        else f"{label} — France 2027 issue dossier"
    )
    description = (
        f"Dossier sourcé sur {label} : {coverage['item_count']} articles, {coverage['publisher_count']} médias et évolution de couverture sur 30 jours."
        if french
        else f"Source-linked dossier on {label}: {coverage['item_count']} items, {coverage['publisher_count']} publishers and 30-day coverage evolution."
    )
    head = _head(
        language=language,
        title=title,
        description=description,
        canonical=canonical,
        canonical_fr=issue["canonical"]["fr"],
        canonical_en=issue["canonical"]["en"],
        favicon=favicon,
        og_image=og_image,
        structured=[_breadcrumb_json(language=language, canonical=canonical, issue=issue)],
    )
    header = _prepare_header(
        shell["header"],
        language=language,
        route_fr=issue["routes"]["fr"],
        route_en=issue["routes"]["en"],
    )
    evidence = _current_evidence(issue, language)
    related = "\n".join(
        f'<a href="{_h(item["routes"][language])}" '
        f'data-related-issue="{_h(item["issue_id"])}" '
        f'data-evidence-count="{len(item["evidence_ids"])}">'
        f'<span>{_h(item["labels"][language])}</span>'
        f'<small>{item["cooccurrence_count"]} '
        f'{"co-occurrences" if language == "en" else "co-occurrences"}</small>'
        f'<strong>→</strong></a>'
        for item in issue["related_issues"]
    )
    if not related:
        related = f'<p class="issue-detail-note">{"Aucune cooccurrence observée dans les preuves publiées." if french else "No co-occurrence observed in published evidence."}</p>'
    candidate_items = current_associations["candidates"]
    candidate_split = (len(candidate_items) + 1) // 2
    candidate_columns = "".join(
        f'<ul class="issue-candidate-column issue-candidate-column-{column_name}">'
        f'{_candidate_rows(issue, language, candidates=candidates)}'
        '</ul>'
        for column_name, candidates in (
            ("a", candidate_items[:candidate_split]),
            ("b", candidate_items[candidate_split:]),
        )
    )

    evidence_total = len(issue["evidence"])
    evidence_visible = min(8, evidence_total)
    evidence_status = (
        f'{evidence_total} {"ÉLÉMENT" if evidence_total == 1 else "ÉLÉMENTS"} · '
        f'{evidence_visible} {"AFFICHÉ" if evidence_visible == 1 else "AFFICHÉS"}'
        if french
        else f'{evidence_total} {"ITEM" if evidence_total == 1 else "ITEMS"} · '
        f'{evidence_visible} SHOWN'
    )
    history_status = (
        f'{_date(coverage_history["first_observation"], language)} → '
        f'{_date(coverage_history["last_observation"], language)}'
    )

    copy = {
        "home": "ACCUEIL" if french else "HOME",
        "hub": "ENJEUX" if french else "ISSUES",
        "eyebrow": "ENJEU · COUVERTURE ÉLECTORALE" if french else "ISSUE · ELECTION COVERAGE",
        "cta": "VOIR LES PREUVES ↓" if french else "VIEW EVIDENCE ↓",
        "items": "ARTICLES · 30 J" if french else "ITEMS · 30D",
        "publishers": "MÉDIAS · 30 J" if french else "PUBLISHERS · 30D",
        "days": "JOURS ACTIFS · 30 J" if french else "ACTIVE DAYS · 30D",
        "candidates": "CANDIDATS DANS LA COUVERTURE · 30 J" if french else "CANDIDATES IN COVERAGE · 30D",
        "weekly_incidence": "INCIDENCE HEBDOMADAIRE" if french else "WEEKLY INCIDENCE",
        "weekly_latest": "DERNIÈRE SEM. COMPLÈTE" if french else "LATEST COMPLETE WEEK",
        "weekly_delta": "VS SEM. COMPLÈTE PRÉC." if french else "VS PREVIOUS COMPLETE WEEK",
        "activity": "ACTIVITÉ ACTUELLE" if french else "CURRENT ACTIVITY",
        "subtopics": "SOUS-THÈMES OBSERVÉS" if french else "OBSERVED SUBTOPICS",
        "candidate_associations": "ASSOCIATIONS ACTUELLES DE CANDIDATS" if french else "CURRENT CANDIDATE ASSOCIATIONS",
        "published": "DERNIÈRES PREUVES SOURCÉES" if french else "LATEST SOURCE-LINKED EVIDENCE",
        "compact_history": "HISTORIQUE COMPACT" if french else "COMPACT HISTORY",
        "related": "ENJEUX CO-OCCURRENTS" if french else "CO-OCCURRING ISSUES",
        "all": "TOUS LES ENJEUX →" if french else "ALL ISSUES →",
        "history_cta": "VOIR L’HISTORIQUE DE CET ENJEU →" if french else "VIEW THIS ISSUE’S HISTORY →",
        "subtopic_note": "Les sous-thèmes peuvent se chevaucher ; les barres indiquent une magnitude relative et non des parts totalisant 100 %." if french else "Subtopics can overlap; bars show relative magnitude, not shares that sum to 100%.",
        "candidate_note": "Une association indique qu’un candidat et cet enjeu apparaissent dans la même couverture retenue. Elle ne décrit ni soutien, ni opposition, ni priorité, ni idéologie, ni position politique, ni engagement de programme." if french else "An association means that a candidate and this issue appear in the same retained coverage. It does not imply support, opposition, priority, ideology, a political position, or a programme or manifesto commitment.",
        "related_note": "Preuves publiées communes ; pas une similarité idéologique ou programmatique." if french else "Shared published evidence; not ideological or policy similarity.",
    }
    method_label = "Note méthodologique" if french else "Method note"
    incidence_method_tooltip = _issue_note_tooltip(
        tooltip_id="issue-incidence-method-note",
        label=method_label,
        content=(
            "Jours-sources de cet enjeu ÷ jours-sources de couverture présidentielle retenue."
            if french
            else "Source-days for this issue ÷ accepted presidential-coverage source-days."
        ),
    )
    previous_period_label = (
        f"Semaine complète · {_period(comparison['previous_start'], comparison['previous_end'], language)}"
        if french
        else f"Complete week · {_period(comparison['previous_start'], comparison['previous_end'], language)}"
    )
    previous_date_tooltip = (
        '<span class="issue-note-tooltip-body issue-incidence-date-tooltip" '
        'id="issue-incidence-previous-dates" role="tooltip">'
        f"{_h(previous_period_label)}</span>"
    )

    latest_period_label = (
        f"Semaine complète · {_period(comparison['latest_start'], comparison['latest_end'], language)}"
        if french
        else f"Complete week · {_period(comparison['latest_start'], comparison['latest_end'], language)}"
    )
    latest_date_tooltip = (
        '<span class="issue-note-tooltip-body issue-incidence-date-tooltip" '
        'id="issue-incidence-latest-dates" role="tooltip">'
        f"{_h(latest_period_label)}</span>"
    )
    subtopic_tooltip = _issue_note_tooltip(
        tooltip_id="issue-subtopics-note",
        label=method_label,
        content=copy["subtopic_note"],
    )
    candidate_tooltip = _issue_note_tooltip(
        tooltip_id="issue-candidate-cooccurrence-note",
        label="Note de co-occurrence" if french else "Co-occurrence note",
        content=copy["candidate_note"],
        warning=True,
    )
    related_tooltip = _issue_note_tooltip(
        tooltip_id="issue-related-evidence-note",
        label=method_label,
        content=copy["related_note"],
    )
    document = f'''<!doctype html>
<html lang="{language}">
{head}
<body class="polling-page poll-detail-page issues-page issue-detail-page issue-current-detail-page">
  <main class="polling-shell">
{header}
    <div class="poll-detail-content">
      <nav class="poll-detail-breadcrumb" aria-label="{'Fil d’Ariane' if french else 'Breadcrumb'}"><a href="{'/' if french else '/en/'}">{copy['home']}</a><span class="poll-detail-breadcrumb-separator" aria-hidden="true">/</span><a href="{'/enjeux/' if french else '/en/issues/'}">{copy['hub']}</a><span class="poll-detail-breadcrumb-separator" aria-hidden="true">/</span><span aria-current="page">{_h(label)}</span></nav>
      <section class="poll-detail-hero issue-detail-hero" aria-labelledby="issue-title"><div class="poll-detail-hero-main"><div><div class="poll-detail-eyebrow">{copy['eyebrow']}</div><div class="poll-detail-title-line"><h1 class="poll-detail-title" id="issue-title">{_h(label)}</h1><span class="issue-state is-{_h(issue['lifecycle'])}">{_h(_lifecycle_label(issue['lifecycle'], language))}</span></div></div></div>
        <div class="poll-detail-metrics issue-current-kpis"><div class="poll-detail-metric"><span>{copy['items']}</span><strong>{coverage['item_count']}</strong></div><div class="poll-detail-metric"><span>{copy['publishers']}</span><strong>{coverage['publisher_count']}</strong></div><div class="poll-detail-metric"><span>{copy['days']}</span><strong>{coverage['active_day_count']}</strong></div><div class="poll-detail-metric"><span>{copy['candidates']}</span><strong>{current_associations['candidate_count']}</strong></div><div class="issue-weekly-signal"><span class="issue-weekly-signal-title">{copy['weekly_incidence']}</span><div class="issue-weekly-signal-values"><div><span>{copy['weekly_latest']}</span><strong>{_h(_incidence_label(comparison['latest_incidence'], language))}</strong></div><div><span>{copy['weekly_delta']}</span><strong>{_h(_signed_pp(comparison['incidence_change_pp'], language))}</strong></div></div></div></div>
      </section>
      <div class="issue-current-detail-grid issue-current-top-grid">
        <section class="poll-detail-panel issue-current-activity" aria-labelledby="current-activity-title" data-previous-incidence="{comparison['previous_incidence']}" data-latest-incidence="{comparison['latest_incidence']}" data-incidence-change-pp="{comparison['incidence_change_pp']}"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{"ACTIVITÉ · 30 J" if french else "ACTIVITY · 30D"}</div><h2 id="current-activity-title">{copy['activity']}</h2></div><span class="poll-detail-panel-status">{coverage['item_count']} {"ARTICLES" if french else "ITEMS"}</span></div><div class="issue-current-activity-body"><div class="issue-current-activity-key"><strong>{"ARTICLES PAR JOUR" if french else "ITEMS PER DAY"}</strong><div class="issue-current-activity-legend" aria-label="{"Légende temporelle" if french else "Temporal legend"}"><span><i class="is-older"></i>{"ANTÉRIEUR" if french else "EARLIER"}</span><span><i class="is-previous"></i>{"SEM. COMPLÈTE PRÉC." if french else "PREVIOUS COMPLETE WEEK"}</span><span><i class="is-latest"></i>{"DERNIÈRE SEM. COMPLÈTE" if french else "LATEST COMPLETE WEEK"}</span><span><i class="is-partial"></i>{"PARTIEL" if french else "PARTIAL"}</span></div></div>{_current_activity_microbars(issue, language)}<div class="issue-current-activity-axis"><span>{_h(_date(coverage['period_start'], language))}</span><span>{_h(_date(coverage['period_end'], language))}</span></div><div class="issue-current-incidence"><div class="issue-note-title-line"><h3>{"INCIDENCE · SEMAINES COMPLÈTES" if french else "INCIDENCE · COMPLETE WEEKS"}</h3>{incidence_method_tooltip}</div><dl class="issue-current-comparison"><div class="is-previous issue-incidence-period" tabindex="0" aria-describedby="issue-incidence-previous-dates"><dt>{"PRÉCÉDENTE" if french else "PREVIOUS"}</dt><dd>{_h(_incidence_label(comparison['previous_incidence'], language))}</dd>{previous_date_tooltip}</div><div class="is-latest issue-incidence-period" tabindex="0" aria-describedby="issue-incidence-latest-dates"><dt>{"DERNIÈRE" if french else "LATEST"}</dt><dd>{_h(_incidence_label(comparison['latest_incidence'], language))}</dd>{latest_date_tooltip}</div><div class="is-delta"><dt>{"ÉVOLUTION" if french else "CHANGE"}</dt><dd>{_h(_signed_pp(comparison['incidence_change_pp'], language))}</dd></div></dl></div></div></section>
        <section class="poll-detail-panel issue-subtopics" aria-labelledby="subtopics-title"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{"TAXONOMIE OBSERVÉE" if french else "OBSERVED TAXONOMY"}</div><div class="issue-note-title-line"><h2 id="subtopics-title">{copy['subtopics']}</h2>{subtopic_tooltip}</div></div><span class="poll-detail-panel-status">{len(issue['subtopics'])}</span></div><ol class="issue-subtopics-scroll">{_subtopic_rows(issue, language)}</ol></section>
      </div>
      <section class="poll-detail-panel issue-candidates issue-current-candidates" aria-labelledby="candidate-associations-title"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{"CO-OCCURRENCE CANDIDATS · 30 J" if french else "CANDIDATE CO-OCCURRENCE · 30D"}</div><div class="issue-note-title-line"><h2 id="candidate-associations-title">{copy['candidate_associations']}</h2>{candidate_tooltip}</div></div><span class="poll-detail-panel-status">{current_associations['candidate_count']}</span></div><div class="issue-candidate-ledgers">{candidate_columns}</div></section>
      <section class="poll-detail-panel issue-published-evidence issue-current-evidence" id="published-evidence" aria-labelledby="published-evidence-title"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">SOURCE-LINKED</div><h2 id="published-evidence-title">{copy['published']}</h2></div><span class="poll-detail-panel-status">{_h(evidence_status)}</span></div>{evidence}</section>
      <div class="issue-current-detail-grid issue-current-bottom-grid">
        <section class="poll-detail-panel issue-compact-history" aria-labelledby="compact-history-title"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{"LONGUE DURÉE" if french else "LONG-RANGE"}</div><h2 id="compact-history-title">{copy['compact_history']}</h2></div><span class="poll-detail-panel-status">{_h(history_status)}</span></div><div class="issue-compact-history-body"><dl class="issue-compact-history-meta"><div><dt>{"PREMIÈRE OBS." if french else "FIRST OBS."}</dt><dd>{_h(_date(coverage_history['first_observation'], language))}</dd></div><div><dt>{"DERNIÈRE OBS." if french else "LATEST OBS."}</dt><dd>{_h(_date(coverage_history['last_observation'], language))}</dd></div><div><dt>{"ARTICLES" if french else "ITEMS"}</dt><dd>{coverage_history['total_item_count']}</dd></div><div><dt>{"JOURS ACTIFS" if french else "ACTIVE DAYS"}</dt><dd>{coverage_history['active_day_count']}</dd></div></dl>{_compact_history_microbars(issue, language)}</div></section>
        <section class="poll-detail-panel issue-related issue-cooccurring" aria-labelledby="related-issues-title"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{"INTERSECTION DE PREUVES" if french else "EVIDENCE INTERSECTION"}</div><div class="issue-note-title-line"><h2 id="related-issues-title">{copy['related']}</h2>{related_tooltip}</div></div><span class="poll-detail-panel-status">{len(issue['related_issues'])}</span></div><div class="issue-related-list issue-related-scroll">{related}</div></section>
      </div>
      <div class="issue-detail-crosslinks">
        <a class="poll-detail-back-cta issue-history-detail-cta" href="{_h(_history_route(issue, language))}">{copy['history_cta']}</a>
        <a class="poll-detail-back-cta issue-all-cta" href="{'/enjeux/' if french else '/en/issues/'}">{copy['all']}</a>
      </div>
    </div>
{shell['footer']}
  </main>
</body>
</html>
'''
    return ("\n".join(line.rstrip() for line in document.splitlines()) + "\n").encode("utf-8")


def serialize_manifest(payload: dict[str, Any]) -> bytes:
    validate_issue_manifest(payload)
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def build_from_paths(
    *,
    root: Path = ROOT,
    news_wire_path: Path = NEWS_WIRE_PATH,
    agenda_history_path: Path = AGENDA_HISTORY_PATH,
    coverage_history_path: Path = ISSUE_COVERAGE_HISTORY_PATH,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
    manifest_path: Path = MANIFEST_PATH,
    write: bool = True,
) -> dict[str, Any]:
    previous_manifest = _load_json(manifest_path) if manifest_path.exists() else None
    candidate_registry = _load_json(candidate_registry_path)
    candidate_index = project_candidate_route_index(candidate_registry, root)
    projection = project_issue_pages(
        _load_json(news_wire_path),
        _load_json(agenda_history_path),
        previous_manifest=previous_manifest,
        candidate_routes=candidate_index["candidates"],
        coverage_history=_load_json(coverage_history_path),
    )
    templates = load_shell_templates(root)
    poll_manifest = _load_json(root / "poll_pages_manifest.json")
    wave_count = poll_manifest.get("wave_count")
    if type(wave_count) is not int or wave_count < 0:
        raise IssuePageBuildError("poll page manifest wave_count is invalid")
    for template in templates.values():
        template["footer"] = prepare_footer(template["footer"], wave_count)
    favicon = _site_favicon_link(root)
    og_image = _site_og_image_url(root)
    artifacts: dict[Path, bytes] = {
        Path("enjeux/index.html"): render_hub(
            projection,
            language="fr",
            shell=templates["fr"],
            favicon=favicon,
            og_image=og_image,
        ),
        Path("en/issues/index.html"): render_hub(
            projection,
            language="en",
            shell=templates["en"],
            favicon=favicon,
            og_image=og_image,
        ),
        Path("enjeux/historique/index.html"): render_history_hub(
            projection,
            language="fr",
            shell=templates["fr"],
            favicon=favicon,
            og_image=og_image,
        ),
        Path("en/issues/history/index.html"): render_history_hub(
            projection,
            language="en",
            shell=templates["en"],
            favicon=favicon,
            og_image=og_image,
        ),
    }
    for issue in projection["issues"]:
        artifacts[
            Path("enjeux") / issue["slugs"]["fr"] / "index.html"
        ] = render_detail(
            projection,
            issue,
            language="fr",
            shell=templates["fr"],
            favicon=favicon,
            og_image=og_image,
        )
        artifacts[
            Path("en") / "issues" / issue["slugs"]["en"] / "index.html"
        ] = render_detail(
            projection,
            issue,
            language="en",
            shell=templates["en"],
            favicon=favicon,
            og_image=og_image,
        )

        artifacts[
            Path("enjeux")
            / "historique"
            / issue["slugs"]["fr"]
            / "index.html"
        ] = render_history_detail(
            projection,
            issue,
            language="fr",
            shell=templates["fr"],
            favicon=favicon,
            og_image=og_image,
        )

        artifacts[
            Path("en")
            / "issues"
            / "history"
            / issue["slugs"]["en"]
            / "index.html"
        ] = render_history_detail(
            projection,
            issue,
            language="en",
            shell=templates["en"],
            favicon=favicon,
            og_image=og_image,
        )

    manifest = issue_manifest_payload(projection)
    manifest_bytes = serialize_manifest(manifest)

    if write:
        for relative, content in artifacts.items():
            _atomic_write(root / relative, content)
        _atomic_write(manifest_path, manifest_bytes)

    return {"projection": projection, "manifest": manifest, "artifacts": artifacts}




def _generated_issue_files(root: Path) -> set[Path]:
    files: set[Path] = set()

    for issue_root in (
        root / "enjeux",
        root / "en" / "issues",
    ):
        if not issue_root.exists():
            continue

        for candidate in issue_root.rglob(
            "index.html"
        ):
            files.add(
                candidate.relative_to(root)
            )

    return files



def _route_to_file(route: str) -> Path:
    return Path(route.strip("/")) / "index.html"


def check_from_paths(
    *,
    root: Path = ROOT,
    news_wire_path: Path = NEWS_WIRE_PATH,
    agenda_history_path: Path = AGENDA_HISTORY_PATH,
    coverage_history_path: Path = ISSUE_COVERAGE_HISTORY_PATH,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> list[str]:
    result = build_from_paths(
        root=root,
        news_wire_path=news_wire_path,
        agenda_history_path=agenda_history_path,
        coverage_history_path=coverage_history_path,
        candidate_registry_path=candidate_registry_path,
        manifest_path=manifest_path,
        write=False,
    )

    errors: list[str] = []
    artifacts = result["artifacts"]

    for relative, expected in artifacts.items():
        target = root / relative
        if not target.exists():
            errors.append(f"missing: {relative.as_posix()}")
        elif target.read_bytes() != expected:
            errors.append(f"out of date: {relative.as_posix()}")

    expected_manifest = serialize_manifest(result["manifest"])
    if not manifest_path.exists():
        errors.append(f"missing: {manifest_path.name}")
    elif manifest_path.read_bytes() != expected_manifest:
        errors.append(f"out of date: {manifest_path.name}")

    expected_pages = {
        relative
        for relative in artifacts
        if relative.name == "index.html"
    }

    for stale in sorted(_generated_issue_files(root) - expected_pages):
        errors.append(f"stale generated issue page: {stale.as_posix()}")

    return errors


def thin_page_audit(result: dict[str, Any], root: Path) -> list[str]:
    import html as _html
    import re as _re

    findings: list[str] = []

    issue_by_page: dict[Path, dict[str, Any]] = {}
    for issue in result["projection"]["issues"]:
        routes = issue.get("routes", {})

        for language in ("fr", "en"):
            route = routes.get(language)

            if route:
                issue_by_page[
                    _route_to_file(route)
                ] = issue

            history_route = _history_route(
                issue,
                language,
            )

            issue_by_page[
                _route_to_file(history_route)
            ] = issue

    for relative in sorted(issue_by_page):
        target = root / relative

        if not target.exists():
            findings.append(f"missing page: {relative.as_posix()}")
            continue

        text = target.read_text(encoding="utf-8")

        visible = _re.sub(
            r"<script\b.*?</script>",
            " ",
            text,
            flags=_re.I | _re.S,
        )
        visible = _re.sub(
            r"<style\b.*?</style>",
            " ",
            visible,
            flags=_re.I | _re.S,
        )
        visible = _re.sub(r"<[^>]+>", " ", visible)
        visible = _html.unescape(
            _re.sub(r"\s+", " ", visible)
        ).strip()

        if len(visible) < 900:
            findings.append(
                "suspiciously little visible content: "
                f"{relative.as_posix()} ({len(visible)} chars)"
            )

        lower = text.lower()

        if "<h1" not in lower:
            findings.append(f"missing H1: {relative.as_posix()}")

        if 'rel="canonical"' not in text:
            findings.append(f"missing canonical: {relative.as_posix()}")

        if 'hreflang="fr"' not in text or 'hreflang="en"' not in text:
            findings.append(
                f"missing hreflang pair: {relative.as_posix()}"
            )

        if (
            '<link rel="icon"' not in text
            and 'rel="shortcut icon"' not in text
        ):
            findings.append(f"missing favicon: {relative.as_posix()}")

        issue = issue_by_page[relative]
        records = issue.get("current_coverage", {}).get("records", [])

        if records and 'target="_blank"' not in text:
            findings.append(
                "evidence exists but source links are missing: "
                f"{relative.as_posix()}"
            )

    return findings


def route_census(result: dict[str, Any]) -> dict[str, Any]:
    projection = result["projection"]
    manifest = result["manifest"]
    issues = projection["issues"]

    density = []

    for issue in issues:
        labels = issue.get("labels", {})
        routes = issue.get("routes", {})
        current = issue.get("current_coverage", {})
        current_assoc = issue.get("current_candidate_associations", {})
        historical = issue.get(
            "historical_candidate_associations",
            {},
        )
        coverage_history = issue.get("coverage_history", {})
        qualification = issue.get("qualification", {})
        subtopics = issue.get("subtopics", current.get("subtopics", []))

        if isinstance(subtopics, dict):
            subtopic_count = len(subtopics)
        elif isinstance(subtopics, list):
            subtopic_count = len(subtopics)
        else:
            subtopic_count = 0

        candidates = current_assoc.get("candidates", [])

        density.append(
            {
                "id": issue.get("issue_id"),
                "label_fr": labels.get("fr"),
                "label_en": labels.get("en"),
                "lifecycle": issue.get("lifecycle"),
                "qualifies_current": qualification.get("current"),
                "qualifies_historical": qualification.get("historical"),
                "current_item_count": current.get("item_count"),
                "current_publisher_count": current.get("publisher_count"),
                "current_source_day_count": current.get(
                    "source_day_count",
                    current.get("publisher_day_count"),
                ),
                "current_active_day_count": current.get("active_day_count"),
                "current_candidate_count": current_assoc.get(
                    "candidate_count",
                    len(candidates),
                ),
                "historical_candidate_association_count": historical.get(
                    "association_count"
                ),
                "historical_observed_day_count": historical.get(
                    "observed_day_count",
                    len(historical.get("daily", [])),
                ),
                "coverage_history_item_count": coverage_history.get(
                    "total_item_count"
                ),
                "coverage_history_active_day_count": coverage_history.get(
                    "active_day_count"
                ),
                "first_observation": coverage_history.get(
                    "first_observation",
                    historical.get("first_observation"),
                ),
                "last_observation": coverage_history.get(
                    "last_observation",
                    historical.get("last_observation"),
                ),
                "subtopic_count": subtopic_count,
                "route_fr": routes.get("fr"),
                "route_en": routes.get("en"),
            }
        )

    return {
        "public_issue_count": manifest["issue_count"],
        "page_count": manifest["page_count"],
        "fr_hub_count": 2,
        "en_hub_count": 2,
        "fr_individual_route_count": len(issues) * 2,
        "en_individual_route_count": len(issues) * 2,
        "fr_routes": [
            issue.get("routes", {}).get("fr")
            for issue in issues
        ],
        "en_routes": [
            issue.get("routes", {}).get("en")
            for issue in issues
        ],
        "fr_history_routes": [
            _history_route(issue, "fr")
            for issue in issues
        ],
        "en_history_routes": [
            _history_route(issue, "en")
            for issue in issues
        ],
        "taxonomy_density": density,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build FR27 bilingual issue pages")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--news-wire", type=Path, default=NEWS_WIRE_PATH)
    parser.add_argument("--agenda-history", type=Path, default=AGENDA_HISTORY_PATH)
    parser.add_argument(
        "--coverage-history", type=Path, default=ISSUE_COVERAGE_HISTORY_PATH
    )
    parser.add_argument("--candidate-registry", type=Path, default=CANDIDATE_REGISTRY_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--census", action="store_true")
    parser.add_argument("--thin-audit", action="store_true")
    return parser


HISTORY_COLORS = (
    "#39d7ff",
    "#6d8cff",
    "#a98cff",
    "#42d6a4",
    "#ffbd58",
    "#ff7f92",
    "#7be0d6",
    "#c4d36f",
)


def _history_polyline(
    daily: list[dict[str, Any]],
    field: str,
    maximum: float,
    *,
    width: int = 1000,
    height: int = 238,
) -> str:
    left, right, top, bottom = 20, 12, 13, 19
    scale = maximum or 1
    return " ".join(
        f"{left + index * (width - left - right) / max(1, len(daily) - 1):.2f},"
        f"{height - bottom - float(point[field]) * (height - top - bottom) / scale:.2f}"
        for index, point in enumerate(daily)
    )


def _history_chart(
    issues: list[dict[str, Any]],
    *,
    language: str,
    detail: bool = False,
) -> str:
    if not issues:
        raise IssuePageBuildError("cannot render empty issue coverage history")
    period = issues[0]["coverage_history"]["daily"]
    volume_max = max(
        point["item_count"]
        for issue in issues
        for point in issue["coverage_history"]["daily"]
    )
    share_max = max(
        point["corpus_share_percent"]
        for issue in issues
        for point in issue["coverage_history"]["daily"]
    )
    paths = []
    legend = []
    for index, issue in enumerate(issues):
        history = issue["coverage_history"]
        color = HISTORY_COLORS[index % len(HISTORY_COLORS)]
        volume_points = _history_polyline(history["daily"], "item_count", volume_max)
        share_points = _history_polyline(
            history["daily"], "corpus_share_percent", share_max
        )
        label = _localized(issue, language)
        paths.append(
            f'<g class="issue-history-series" style="--issue-history-color:{color}">'
            f'<polyline data-history-series="volume" points="{volume_points}"><title>{_h(label)} — {history["total_item_count"]} {"articles" if language == "fr" else "items"}</title></polyline>'
            f'<polyline data-history-series="share" points="{share_points}" hidden><title>{_h(label)} — {"part quotidienne du corpus" if language == "fr" else "daily corpus share"}</title></polyline>'
            "</g>"
        )
        peak_label = _date(history["peak"]["date"], language)
        legend.append(
            f'<a class="issue-history-legend-item" href="{_h(issue["routes"][language])}" style="--issue-history-color:{color}"><i></i><span>{_h(label)}</span><strong>{history["total_item_count"]}</strong><small>{history["active_day_count"]} {"jours actifs" if language == "fr" else "active days"} · {"pic" if language == "fr" else "peak"} {history["peak"]["item_count"]} · {_h(peak_label)}</small></a>'
        )
    chart_label = (
        "Historique quotidien du volume de couverture des enjeux"
        if language == "fr"
        else "Daily issue coverage volume history"
    )
    detail_class = " is-detail" if detail else ""
    legend_markup = "" if detail else f'<div class="issue-history-legend">{"".join(legend)}</div>'
    return f'''<div class="issue-history-visual{detail_class}" data-history-panel data-volume-maximum="{volume_max}" data-share-maximum="{share_max:.2f}">
      <div class="issue-history-toolbar"><div class="polling-segments issue-history-modes" aria-label="{'Mode de l’historique' if language == 'fr' else 'History mode'}"><button type="button" data-history-mode="volume" aria-pressed="true">VOLUME</button><button type="button" data-history-mode="share" aria-pressed="false">{'PART DU CORPUS' if language == 'fr' else 'CORPUS SHARE'}</button></div><span data-history-unit>{'ARTICLES PAR JOUR' if language == 'fr' else 'ITEMS PER DAY'}</span></div>
      <div class="issue-history-chart"><svg viewBox="0 0 1000 238" role="img" aria-label="{_h(chart_label)}" preserveAspectRatio="none"><g class="issue-history-grid"><line x1="20" y1="13" x2="988" y2="13"></line><line x1="20" y1="64.5" x2="988" y2="64.5"></line><line x1="20" y1="116" x2="988" y2="116"></line><line x1="20" y1="167.5" x2="988" y2="167.5"></line><line x1="20" y1="219" x2="988" y2="219"></line></g>{''.join(paths)}</svg><div class="issue-history-axis"><span>{_h(_date(period[0]['date'], language))}</span><strong data-history-scale>0–{volume_max} {'articles' if language == 'fr' else 'items'}</strong><span>{_h(_date(period[-1]['date'], language))}</span></div></div>
      {legend_markup}
    </div>'''
def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)

    common = {
        "root": arguments.root,
        "news_wire_path": arguments.news_wire,
        "agenda_history_path": arguments.agenda_history,
        "coverage_history_path": arguments.coverage_history,
        "candidate_registry_path": arguments.candidate_registry,
        "manifest_path": arguments.manifest,
    }

    try:
        if arguments.check:
            errors = check_from_paths(**common)

            if errors:
                for error in errors:
                    print(f"issue page check: {error}")
                return 1

            manifest = _load_json(arguments.manifest)
            print(
                "issue page check clean: "
                f"{manifest['issue_count']} issues, "
                f"{manifest['page_count']} routes"
            )
            return 0

        if arguments.census or arguments.thin_audit:
            result = build_from_paths(
                **common,
                write=False,
            )

            if arguments.census:
                print(
                    json.dumps(
                        route_census(result),
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            if arguments.thin_audit:
                findings = thin_page_audit(
                    result,
                    arguments.root,
                )

                if findings:
                    for finding in findings:
                        print(f"issue thin-page audit: {finding}")
                    return 1

                print("issue thin-page audit clean")

            return 0

        result = build_from_paths(**common)

    except (
        IssuePageContractError,
        IssuePageBuildError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(f"issue page build error: {error}")
        return 1

    manifest = result["manifest"]
    print(
        "built issue pages: "
        f"{manifest['issue_count']} public issues, "
        f"{manifest['page_count']} routes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
