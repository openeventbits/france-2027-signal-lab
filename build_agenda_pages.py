"""Build the bilingual FR27 Campaign Agenda static page family."""

from __future__ import annotations

import argparse
import copy
from datetime import date, timedelta
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from agenda_page_contract import (
    AgendaPageContractError,
    agenda_manifest_payload,
    project_agenda_pages,
    validate_agenda_manifest,
)
from build_poll_pages import (
    _site_favicon_link,
    _site_og_image_url,
    format_date,
    format_date_range,
    load_shell_templates,
    prepare_footer,
)
from candidate_page_contract import project_candidate_route_index


ROOT = Path(__file__).resolve().parent
NEWS_WIRE_PATH = ROOT / "news_wire.json"
AGENDA_HISTORY_PATH = ROOT / "candidate_agenda_history.json"
COVERAGE_HISTORY_PATH = ROOT / "agenda_coverage_history.json"
CANDIDATE_REGISTRY_PATH = ROOT / "candidate_candidacy_status.json"
MANIFEST_PATH = ROOT / "agenda_pages_manifest.json"
ORIGIN = "https://france2027.app"


class AgendaPageBuildError(ValueError):
    """Raised when Agenda page artifacts cannot be rendered safely."""


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


def _document(markup: str) -> bytes:
    return ("\n".join(line.rstrip() for line in markup.splitlines()) + "\n").encode(
        "utf-8"
    )


def _json_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", r"<\/"
    )


def _date(value: str | None, language: str) -> str:
    return format_date(value, language) if value else "—"


def _period(start: str | None, end: str | None, language: str) -> str:
    return format_date_range(start, end, language) if start and end else "—"


def _decimal(value: float, language: str, digits: int = 1) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if language == "fr" else text


def _signed(value: float, language: str, suffix: str = "") -> str:
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{_decimal(abs(value), language)}{suffix}"


def _lifecycle_label(value: str, language: str) -> str:
    labels = {
        "fr": {"current": "ACTUEL", "historical": "HISTORIQUE", "dormant": "DORMANT"},
        "en": {"current": "CURRENT", "historical": "HISTORICAL", "dormant": "DORMANT"},
    }
    return labels[language][value]


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
        raise AgendaPageBuildError("could not prepare Agenda language navigation")
    return prepared


def _head(
    *,
    language: str,
    title: str,
    description: str,
    route: str,
    route_fr: str,
    route_en: str,
    favicon: str,
    og_image: str,
    structured: list[dict[str, Any]],
) -> str:
    canonical = ORIGIN + route
    canonical_fr = ORIGIN + route_fr
    canonical_en = ORIGIN + route_en
    og_locale = "fr_FR" if language == "fr" else "en_GB"
    alternate_locale = "en_GB" if language == "fr" else "fr_FR"
    json_ld = "\n  ".join(
        f'<script type="application/ld+json">{_json_script(value)}</script>'
        for value in structured
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
  <meta property="og:locale:alternate" content="{alternate_locale}">
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
  <link rel="stylesheet" href="/assets/agenda.css">
  {json_ld}
  <script src="/assets/fr27-ui.js" defer></script>
  <script src="/assets/poll-page.js" defer></script>
  <script src="/assets/agenda.js" defer></script>
</head>'''


def _breadcrumb_json(
    *,
    language: str,
    route: str,
    topic: dict[str, Any] | None = None,
    history: bool = False,
) -> dict[str, Any]:
    hub_route = "/agenda/" if language == "fr" else "/en/agenda/"
    history_route = "/agenda/historique/" if language == "fr" else "/en/agenda/history/"
    entries = [
        ("Accueil" if language == "fr" else "Home", "/" if language == "fr" else "/en/"),
        ("Agenda", hub_route),
    ]
    if history:
        entries.append(("Historique" if language == "fr" else "History", history_route))
    if topic is not None:
        entries.append((topic["labels"][language], route))
    elif route not in {hub_route, history_route}:
        entries.append(("Agenda", route))
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": ORIGIN + item_route,
            }
            for index, (name, item_route) in enumerate(entries, start=1)
        ],
    }


def _candidate_routes_index(candidate_routes: Any) -> dict[str, dict[str, str]]:
    if not isinstance(candidate_routes, list):
        raise AgendaPageBuildError("candidate route index must be an array")
    result: dict[str, dict[str, str]] = {}
    for candidate in candidate_routes:
        candidate_id = candidate.get("candidate_id") if isinstance(candidate, dict) else None
        routes = candidate.get("routes") if isinstance(candidate, dict) else None
        if not isinstance(candidate_id, str) or not isinstance(routes, dict):
            raise AgendaPageBuildError("candidate route index contains an invalid entry")
        if candidate_id in result:
            raise AgendaPageBuildError("candidate route index contains a duplicate id")
        result[candidate_id] = routes
    return result


def _candidate_associations(
    candidate_history: dict[str, Any],
    candidate_routes: dict[str, dict[str, str]],
    *,
    topic_id: str,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    totals_by_day: dict[str, int] = {}
    candidates = []
    for candidate in candidate_history["candidates"]:
        selected = [
            row
            for row in candidate["daily_series"]
            if period_start <= row["date"] <= period_end
        ]
        observations = [
            (row["date"], row["campaign_counts"][topic_id])
            for row in selected
            if row["campaign_counts"][topic_id] > 0
        ]
        association_count = sum(count for _day, count in observations)
        if not association_count:
            continue
        for day, count in observations:
            totals_by_day[day] = totals_by_day.get(day, 0) + count
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate["candidate_name"],
                "routes": candidate_routes.get(candidate["candidate_id"], {}),
                "association_count": association_count,
                "observed_days": len(observations),
                "first_association": observations[0][0],
                "last_association": observations[-1][0],
            }
        )
    candidates.sort(
        key=lambda item: (
            -item["association_count"],
            item["candidate_name"].casefold(),
            item["candidate_id"],
        )
    )
    return {
        "period_start": period_start,
        "period_end": period_end,
        "candidate_count": len(candidates),
        "association_count": sum(item["association_count"] for item in candidates),
        "observed_days": len(totals_by_day),
        "candidates": candidates,
        "daily": [
            {"date": day, "association_count": totals_by_day[day]}
            for day in sorted(totals_by_day)
        ],
    }


def _calendar_series(start: str, end: str) -> list[dict[str, Any]]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    return [
        {
            "date": (first + timedelta(days=offset)).isoformat(),
            "item_count": 0,
            "source_day_count": 0,
        }
        for offset in range((last - first).days + 1)
    ]


def _window_comparison(
    topic: dict[str, Any],
    all_topics: list[dict[str, Any]],
    period: dict[str, Any],
) -> dict[str, Any]:
    series = topic["daily_activity"]
    previous_start = period["previous_start"]
    previous_end = period["previous_end"]
    latest_start = period["latest_start"]
    latest_end = period["latest_end"]

    def total(rows: list[dict[str, Any]], field: str, start: str, end: str) -> int:
        return sum(row[field] for row in rows if start <= row["date"] <= end)

    previous_source_days = total(series, "source_day_count", previous_start, previous_end)
    latest_source_days = total(series, "source_day_count", latest_start, latest_end)
    previous_items = total(series, "item_count", previous_start, previous_end)
    latest_items = total(series, "item_count", latest_start, latest_end)
    previous_denominator = sum(
        total(row["daily_activity"], "source_day_count", previous_start, previous_end)
        for row in all_topics
    )
    latest_denominator = sum(
        total(row["daily_activity"], "source_day_count", latest_start, latest_end)
        for row in all_topics
    )
    previous_share = previous_source_days / previous_denominator if previous_denominator else 0.0
    latest_share = latest_source_days / latest_denominator if latest_denominator else 0.0
    return {
        "previous_start": previous_start,
        "previous_end": previous_end,
        "latest_start": latest_start,
        "latest_end": latest_end,
        "previous_item_count": previous_items,
        "latest_item_count": latest_items,
        "previous_source_day_count": previous_source_days,
        "latest_source_day_count": latest_source_days,
        "source_day_change": latest_source_days - previous_source_days,
        "previous_agenda_share": previous_share,
        "latest_agenda_share": latest_share,
        "agenda_share_change_pp": (latest_share - previous_share) * 100,
    }


def _history_comparison(
    topic: dict[str, Any],
    all_topics: list[dict[str, Any]],
    *,
    window_days: int = 28,
) -> dict[str, Any]:
    period_end = date.fromisoformat(topic["coverage_history"]["daily"][-1]["date"])
    latest_start = period_end - timedelta(days=window_days - 1)
    previous_end = latest_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)

    def selected(subject: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
        return [
            point
            for point in subject["coverage_history"]["daily"]
            if start.isoformat() <= point["date"] <= end.isoformat()
        ]

    previous_points = selected(topic, previous_start, previous_end)
    latest_points = selected(topic, latest_start, period_end)
    if len(previous_points) != window_days or len(latest_points) != window_days:
        raise AgendaPageBuildError("Agenda history lacks two complete comparison windows")
    previous_sd = sum(point["source_day_count"] for point in previous_points)
    latest_sd = sum(point["source_day_count"] for point in latest_points)
    previous_denominator = sum(
        sum(point["source_day_count"] for point in selected(row, previous_start, previous_end))
        for row in all_topics
    )
    latest_denominator = sum(
        sum(point["source_day_count"] for point in selected(row, latest_start, period_end))
        for row in all_topics
    )
    previous_share = previous_sd / previous_denominator if previous_denominator else 0.0
    latest_share = latest_sd / latest_denominator if latest_denominator else 0.0
    return {
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "latest_start": latest_start.isoformat(),
        "latest_end": period_end.isoformat(),
        "previous_source_day_count": previous_sd,
        "latest_source_day_count": latest_sd,
        "previous_agenda_share": previous_share,
        "latest_agenda_share": latest_share,
        "agenda_share_change_pp": (latest_share - previous_share) * 100,
    }


def _enrich_projection(
    projection: dict[str, Any],
    candidate_history: dict[str, Any],
    candidate_routes: list[dict[str, Any]],
) -> dict[str, Any]:
    result = copy.deepcopy(projection)
    topics = [topic for topic in result["topics"] if topic["public"]]
    route_index = _candidate_routes_index(candidate_routes)
    period = result["evolution_period"]
    evolution_topics = []
    for topic in topics:
        current = topic["current_evolution_projection"]
        if current is None:
            current = {
                "id": topic["topic_id"],
                "label": topic["labels"]["en"],
                "item_count": 0,
                "publisher_count": 0,
                "source_day_count": 0,
                "active_day_count": 0,
                "display_eligible": False,
                "daily_activity": _calendar_series(period["period_start"], period["period_end"]),
                "matched_term_counts": [],
            }
            topic["current_evolution_projection"] = current
        evolution_topics.append(current)

    for topic in topics:
        base = topic["current_base_projection"] or {
            "item_count": 0,
            "publisher_count": 0,
            "publisher_names": [],
            "source_day_count": 0,
            "active_day_count": 0,
            "display_eligible": False,
            "supporting_item_count": 0,
            "omitted_item_count": 0,
            "supporting_items": [],
        }
        current = topic["current_evolution_projection"]
        topic["current"] = {
            "item_count": current["item_count"],
            "source_day_count": current["source_day_count"],
            "active_day_count": current["active_day_count"],
            "publisher_count": base["publisher_count"],
            "publisher_names": base["publisher_names"],
            "daily_activity": current["daily_activity"],
            "matched_term_counts": current["matched_term_counts"],
            "supporting_item_count": base["supporting_item_count"],
            "omitted_item_count": base["omitted_item_count"],
            "supporting_items": base["supporting_items"],
            "comparison": _window_comparison(current, evolution_topics, period),
        }
        topic["current_candidate_associations"] = _candidate_associations(
            candidate_history,
            route_index,
            topic_id=topic["topic_id"],
            period_start=period["period_start"],
            period_end=period["period_end"],
        )
        history_period = topic["coverage_history"]["daily"]
        topic["historical_candidate_associations"] = _candidate_associations(
            candidate_history,
            route_index,
            topic_id=topic["topic_id"],
            period_start=history_period[0]["date"],
            period_end=history_period[-1]["date"],
        )
        topic["history_comparison"] = _history_comparison(topic, topics)
        topic["canonical"] = {
            "fr": ORIGIN + topic["routes"]["fr"],
            "en": ORIGIN + topic["routes"]["en"],
            "history_fr": ORIGIN + topic["routes"]["history_fr"],
            "history_en": ORIGIN + topic["routes"]["history_en"],
        }

    evidence: dict[tuple[str, str], dict[str, Any]] = {}
    for topic in topics:
        for item in topic["current"]["supporting_items"]:
            key = (str(item["id"]), item["url"])
            row = evidence.setdefault(
                key,
                {
                    **item,
                    "date": item["published_at"][:10],
                    "topic_ids": [],
                },
            )
            row["topic_ids"].append(topic["topic_id"])
    latest_evidence = sorted(
        evidence.values(),
        key=lambda item: (
            item["published_at"],
            item["publisher"].casefold(),
            item["headline"].casefold(),
            str(item["id"]),
        ),
        reverse=True,
    )
    publishers = {
        publisher
        for topic in topics
        for publisher in topic["current"]["publisher_names"]
    }
    candidate_ids = {
        candidate["candidate_id"]
        for topic in topics
        for candidate in topic["current_candidate_associations"]["candidates"]
    }
    result["topics"] = topics
    result["latest_evidence"] = latest_evidence
    result["metrics"] = {
        "public_topic_count": len(topics),
        "classified_item_count": sum(topic["current"]["item_count"] for topic in topics),
        "source_day_count": sum(topic["current"]["source_day_count"] for topic in topics),
        "publisher_count": len(publishers),
        "candidate_count": len(candidate_ids),
    }
    return result


def _tooltip(identifier: str, label: str, content: str, *, warning: bool = False) -> str:
    modifier = " is-warning" if warning else ""
    return (
        f'<span class="agenda-note-tooltip{modifier}">'
        f'<button class="agenda-note-tooltip-trigger" type="button" '
        f'aria-label="{_h(label)}" aria-describedby="{_h(identifier)}">i</button>'
        f'<span class="agenda-note-tooltip-body" id="{_h(identifier)}" '
        f'role="tooltip">{_h(content)}</span></span>'
    )


def _microbars(
    daily: list[dict[str, Any]],
    *,
    language: str,
    field: str = "source_day_count",
    class_name: str = "agenda-card-microbars",
) -> str:
    maximum = max((point[field] for point in daily), default=0) or 1
    bars = []
    child_class = (
        "agenda-detail-activity-bar"
        if class_name == "agenda-detail-activity-bars"
        else ""
    )
    for point in daily:
        value = point[field]
        height = 4.0 if value == 0 else 16.0 + 84.0 * value / maximum
        title = f"{_date(point['date'], language)} · {value}"
        bars.append(
            f'<i class="{child_class}" style="--agenda-bar:{height:.2f}%" '
            f'title="{_h(title)}"></i>'
        )
    return (
        f'<div class="{class_name}" style="--agenda-history-columns:{len(daily)};'
        f'--agenda-activity-columns:{len(daily)}" role="img" '
        f'aria-label="{_h(", ".join(str(point[field]) for point in daily))}">'
        + "".join(bars)
        + "</div>"
    )


def _topic_card(topic: dict[str, Any], language: str, *, history: bool = False) -> str:
    label = topic["labels"][language]
    if history:
        data = topic["coverage_history"]
        comparison = topic["history_comparison"]
        route = topic["routes"]["history_fr" if language == "fr" else "history_en"]
        count_one = data["total_source_days"]
        count_two = data["active_days"]
        volume = data["total_items"]
        microbars = _microbars(data["daily"], language=language)
        signal = f'{data["peak_day"]["source_day_count"]} · {_date(data["peak_day"]["date"], language)}'
        first_label = "JOURS-SOURCES · HIST." if language == "fr" else "SOURCE-DAYS · HISTORY"
        second_label = "JOURS ACTIFS" if language == "fr" else "ACTIVE DAYS"
        signal_label = "PIC JOURNALIER" if language == "fr" else "DAILY PEAK"
        state = "HISTORIQUE" if language == "fr" else "HISTORICAL"
        state_class = "historical"
        open_label = "OUVRIR LE DOSSIER HISTORIQUE →" if language == "fr" else "OPEN HISTORY DOSSIER →"
    else:
        data = topic["current"]
        comparison = data["comparison"]
        route = topic["routes"][language]
        count_one = data["source_day_count"]
        count_two = data["publisher_count"]
        volume = data["item_count"]
        microbars = _microbars(data["daily_activity"], language=language)
        signals = data["matched_term_counts"]
        signal = signals[0]["term"] if signals else "—"
        first_label = "JOURS-SOURCES · 30 J" if language == "fr" else "SOURCE-DAYS · 30D"
        second_label = "MÉDIAS · BASE" if language == "fr" else "PUBLISHERS · BASE"
        signal_label = "SIGNAL ASSOCIÉ" if language == "fr" else "ASSOCIATED SIGNAL"
        state = _lifecycle_label(topic["lifecycle"], language)
        state_class = topic["lifecycle"]
        open_label = "OUVRIR LE DOSSIER →" if language == "fr" else "OPEN DOSSIER →"
    latest_share = comparison["latest_agenda_share"]
    delta = comparison["agenda_share_change_pp"]
    return f'''<a class="agenda-card" href="{_h(route)}" data-agenda-card
      data-name="{_h(label)}" data-sort-activity="{latest_share:.8f}"
      data-sort-movement="{abs(delta):.4f}" data-sort-volume="{volume}"
      data-sort-label="{_h(label.casefold())}">
      <span class="agenda-card-head"><strong>{_h(label)}</strong><span class="agenda-state is-{_h(state_class)}">{_h(state)}</span></span>
      <span class="agenda-card-counts"><span><strong>{count_one}</strong><small>{first_label}</small></span><span><strong>{count_two}</strong><small>{second_label}</small></span></span>
      {microbars}
      <span class="agenda-card-window"><span><strong>{_h(_decimal(latest_share * 100, language))}%</strong><small>{'PART AGENDA' if language == 'fr' else 'AGENDA SHARE'}</small></span><span><strong>{_h(_signed(delta, language, 'pp'))}</strong><small>{'VS PÉRIODE PRÉC.' if language == 'fr' else 'VS PREV. PERIOD'}</small></span></span>
      <span class="agenda-card-subtopic"><small>{signal_label}</small><strong>{_h(signal)}</strong></span>
      <span class="agenda-card-open">{open_label}</span>
    </a>'''


def _movement_chart(topics: list[dict[str, Any]], language: str, *, history: bool = False) -> str:
    def comparison(topic: dict[str, Any]) -> dict[str, Any]:
        return topic["history_comparison"] if history else topic["current"]["comparison"]

    ordered = sorted(
        topics,
        key=lambda topic: (
            -abs(comparison(topic)["agenda_share_change_pp"]),
            -comparison(topic)["latest_agenda_share"],
            topic["labels"][language].casefold(),
        ),
    )
    maximum = max(
        (
            value
            for topic in topics
            for value in (
                comparison(topic)["previous_agenda_share"] * 100,
                comparison(topic)["latest_agenda_share"] * 100,
            )
        ),
        default=0.0,
    ) or 1.0
    rows = []
    for topic in ordered:
        data = comparison(topic)
        previous = data["previous_agenda_share"] * 100
        latest = data["latest_agenda_share"] * 100
        previous_position = previous / maximum * 100
        latest_position = latest / maximum * 100
        low = min(previous_position, latest_position)
        span = abs(previous_position - latest_position)
        route = topic["routes"][
            ("history_fr" if language == "fr" else "history_en") if history else language
        ]
        rows.append(
            f'''<div class="agenda-dumbbell-row"><a href="{_h(route)}">{_h(topic["labels"][language])}</a>
              <span class="agenda-dumbbell-track" aria-hidden="true"><i class="agenda-dumbbell-connector" style="--agenda-low:{low:.3f}%;--agenda-span:{span:.3f}%"></i><i class="agenda-dumbbell-dot is-previous" style="--agenda-position:{previous_position:.3f}%"></i><i class="agenda-dumbbell-dot is-recent" style="--agenda-position:{latest_position:.3f}%"></i></span>
              <span class="agenda-dumbbell-values"><span>{_h(_decimal(previous, language))}%</span><b aria-hidden="true">→</b><span>{_h(_decimal(latest, language))}%</span></span>
              <strong class="agenda-dumbbell-delta">{_h(_signed(data["agenda_share_change_pp"], language, "pp"))}</strong></div>'''
        )
    reference = comparison(topics[0])
    return f'''<div class="agenda-dumbbell"><div class="agenda-dumbbell-list">{"".join(rows)}</div>
      <div class="agenda-dumbbell-legend"><span class="agenda-dumbbell-legend-item"><i class="is-previous"></i><strong>{'PÉRIODE PRÉCÉDENTE' if language == 'fr' else 'PREVIOUS PERIOD'}</strong><small>{_h(_period(reference["previous_start"], reference["previous_end"], language))}</small></span><span class="agenda-dumbbell-legend-item"><i class="is-recent"></i><strong>{'PÉRIODE RÉCENTE' if language == 'fr' else 'RECENT PERIOD'}</strong><small>{_h(_period(reference["latest_start"], reference["latest_end"], language))}</small></span></div></div>'''


def _composition(topics: list[dict[str, Any]], language: str) -> str:
    ordered = sorted(topics, key=lambda topic: topic["labels"][language].casefold())

    def bar(field: str, class_name: str) -> str:
        return '<div class="agenda-agenda-bar">' + "".join(
            f'<span class="agenda-agenda-segment {class_name}" style="--agenda-share:{topic["current"]["comparison"][field] * 100:.6f}%" title="{_h(topic["labels"][language])}"></span>'
            for topic in ordered
        ) + "</div>"

    reference = ordered[0]["current"]["comparison"]
    previous_total = sum(topic["current"]["comparison"]["previous_source_day_count"] for topic in ordered)
    latest_total = sum(topic["current"]["comparison"]["latest_source_day_count"] for topic in ordered)
    legend = "".join(
        f'<div class="agenda-agenda-topic"><span class="agenda-agenda-key">{index}</span><span>{_h(topic["labels"][language])}</span><strong>{_h(_decimal(topic["current"]["comparison"]["previous_agenda_share"] * 100, language))}%</strong><strong>{_h(_decimal(topic["current"]["comparison"]["latest_agenda_share"] * 100, language))}%</strong></div>'
        for index, topic in enumerate(ordered, start=1)
    )
    return f'''<div class="agenda-agenda-composition"><div class="agenda-agenda-period">
      <div><span><strong>{'SEMAINE PRÉCÉDENTE' if language == 'fr' else 'PREVIOUS WEEK'}</strong><small>{_h(_period(reference["previous_start"], reference["previous_end"], language))} · n={previous_total}</small></span>{bar("previous_agenda_share", "is-previous")}</div>
      <div><span><strong>{'7 J RÉCENTS' if language == 'fr' else 'RECENT 7D'}</strong><small>{_h(_period(reference["latest_start"], reference["latest_end"], language))} · n={latest_total}</small></span>{bar("latest_agenda_share", "is-recent")}</div></div>
      <div class="agenda-agenda-legend-head"><span></span><span></span><strong>{'PRÉC.' if language == 'fr' else 'PREV.'}</strong><strong>{'RÉCENT' if language == 'fr' else 'RECENT'}</strong></div><div class="agenda-agenda-topics">{legend}</div></div>'''


def _evidence_row(
    item: dict[str, Any],
    language: str,
    *,
    badges: str = "",
    hub: bool = False,
) -> str:
    source = (
        f'<div class="agenda-evidence-source"><strong>{_h(item["publisher"])}</strong>'
        f'<time datetime="{_h(item["date"])}">{_h(_date(item["date"], language))}</time></div>'
    )
    headline = f"<h3>{_h(item['headline'])}</h3>"
    external_class = " agenda-evidence-external" if hub else ""
    external = (
        f'<a class="{external_class.strip()}" href="{_h(item["url"])}" '
        f'target="_blank" rel="noopener noreferrer">SOURCE ↗</a>'
        if hub
        else
        f'<a href="{_h(item["url"])}" target="_blank" '
        f'rel="noopener noreferrer">SOURCE ↗</a>'
    )

    if hub:
        return (
            '<article class="agenda-evidence-row agenda-hub-evidence-row">'
            + badges
            + source
            + headline
            + external
            + "</article>"
        )

    return (
        '<article class="agenda-evidence-row">'
        + source
        + headline
        + badges
        + external
        + "</article>"
    )


def _candidate_rows(data: dict[str, Any], language: str, *, historical: bool = False) -> str:
    candidates = data["candidates"]
    if not candidates:
        return f'<p class="agenda-detail-note">{"Aucune association candidat × thème observée sur cette période." if language == "fr" else "No candidate × topic association was observed in this period."}</p>'
    maximum = candidates[0]["association_count"] or 1
    rows = []
    for candidate in candidates:
        route = candidate["routes"].get(language)
        name = _h(candidate["candidate_name"])
        identity = f'<a href="{_h(route)}">{name}</a>' if route else f"<span>{name}</span>"
        count = candidate["association_count"]
        if historical:
            rows.append(
                f'<li><div class="agenda-history-candidate-primary">{identity}<strong>{count} associations</strong></div><span class="agenda-history-candidate-period">{_h(_period(candidate["first_association"], candidate["last_association"], language))} · {candidate["observed_days"]} {"jours" if language == "fr" else "days"}</span><i class="agenda-history-candidate-magnitude" style="--agenda-history-candidate-share:{count / maximum:.6f}"></i></li>'
            )
        else:
            rows.append(
                f'<li>{identity}<strong>{count} {"associations"}</strong><i class="agenda-candidate-magnitude" style="--agenda-candidate-share:{count / maximum:.6f}"></i></li>'
            )
    return "".join(rows)


def _history_visual(topic: dict[str, Any], language: str, *, compact: bool = False) -> str:
    daily = topic["coverage_history"]["daily"]
    maximum = max((point["source_day_count"] for point in daily), default=0) or 1
    share_maximum = max((point["topic_source_day_share"] * 100 for point in daily), default=0.0) or 1.0
    cells = []
    for point in daily:
        source_days = point["source_day_count"]
        share = point["topic_source_day_share"] * 100
        source_height = 3 if not source_days else 14 + 86 * source_days / maximum
        share_height = 3 if not share else 14 + 86 * share / share_maximum
        cells.append(
            f'<span class="agenda-history-detail-bar" title="{_h(_date(point["date"], language))} · {source_days} · {_decimal(share, language, 2)}%"><i data-history-series="volume" style="--agenda-history-bar:{source_height:.2f}%"></i><i data-history-series="share" style="--agenda-history-bar:{share_height:.2f}%" hidden></i></span>'
        )
    detail = "" if compact else " is-detail"
    return f'''<div class="agenda-history-visual{detail}" data-history-panel data-volume-maximum="{maximum}" data-share-maximum="{share_maximum:.2f}"><div class="agenda-history-toolbar"><div class="polling-segments agenda-history-modes"><button type="button" data-history-mode="volume" aria-pressed="true">{'JOURS-SOURCES' if language == 'fr' else 'SOURCE-DAYS'}</button><button type="button" data-history-mode="share" aria-pressed="false">{'PART AGENDA' if language == 'fr' else 'AGENDA SHARE'}</button></div><span data-history-unit>{'JOURS-SOURCES PAR JOUR' if language == 'fr' else 'SOURCE-DAYS PER DAY'}</span></div><div class="agenda-history-detail-bars" style="--agenda-history-columns:{len(daily)}">{"".join(cells)}</div><div class="agenda-history-axis"><span>{_h(_date(daily[0]["date"], language))}</span><strong data-history-scale>0–{maximum} {'jours-sources' if language == 'fr' else 'source-days'}</strong><span>{_h(_date(daily[-1]["date"], language))}</span></div></div>'''


def _history_overview(topics: list[dict[str, Any]], language: str) -> str:
    rows = []
    for topic in topics:
        daily = topic["coverage_history"]["daily"]
        maximum = max((point["source_day_count"] for point in daily), default=0) or 1
        cells = "".join(
            f'<span class="agenda-history-heat-cell" '
            f'style="--agenda-history-heat:{0.04 + 0.96 * point["source_day_count"] / maximum:.6f}" '
            f'title="{_h(_date(point["date"], language))} · {point["source_day_count"]}"></span>'
            for point in daily
        )
        rows.append(
            f'<article class="agenda-history-evolution-row"><a class="agenda-evolution-name" '
            f'href="{_h(topic["routes"]["history_fr" if language == "fr" else "history_en"])}">'
            f'{_h(topic["labels"][language])}</a><div class="agenda-history-heat-strip" '
            f'style="grid-template-columns:repeat({len(daily)},minmax(2px,1fr))">{cells}</div>'
            f'<div class="agenda-evolution-total"><strong>{topic["coverage_history"]["total_source_days"]}</strong>'
            f'<small>{"JOURS-SOURCES" if language == "fr" else "SOURCE-DAYS"}</small></div></article>'
        )
    return '<div class="agenda-history-evolution-rows">' + "".join(rows) + "</div>"


def _hub_common(
    projection: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
    history: bool,
) -> bytes:
    french = language == "fr"
    topics = projection["topics"]
    route = (
        "/agenda/historique/" if french and history else
        "/en/agenda/history/" if history else
        "/agenda/" if french else "/en/agenda/"
    )
    route_fr = "/agenda/historique/" if history else "/agenda/"
    route_en = "/en/agenda/history/" if history else "/en/agenda/"
    title = (
        "Historique de l’Agenda de campagne | France 2027"
        if french and history
        else "France 2027 Campaign Agenda History"
        if history
        else "Agenda 2027 — Observatoire de la campagne | France 2027"
        if french
        else "France 2027 Campaign Agenda Lab"
    )
    description = (
        "Historique descriptif des thèmes de campagne observés dans le corpus de sources suivi."
        if french and history
        else "Descriptive history of campaign themes observed in the monitored source corpus."
        if history
        else "Thèmes récurrents de campagne observés dans le corpus de sources suivi pour la présidentielle française de 2027."
        if french
        else "Recurring campaign themes observed in the monitored source corpus for France’s 2027 presidential election."
    )
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": ORIGIN + route,
        "inLanguage": language,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(topics),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": topic["labels"][language],
                    "url": ORIGIN
                    + topic["routes"][
                        ("history_fr" if french else "history_en") if history else language
                    ],
                }
                for index, topic in enumerate(topics, start=1)
            ],
        },
    }
    head = _head(
        language=language,
        title=title,
        description=description,
        route=route,
        route_fr=route_fr,
        route_en=route_en,
        favicon=favicon,
        og_image=og_image,
        structured=[collection, _breadcrumb_json(language=language, route=route, history=history)],
    )
    header = _prepare_header(
        shell["header"], language=language, route_fr=route_fr, route_en=route_en
    )
    cards = "".join(_topic_card(topic, language, history=history) for topic in topics)
    period = projection["coverage_history_period"] if history else projection["evolution_period"]
    period_start = period["start_date"] if history else period["period_start"]
    period_end = period["end_date"] if history else period["period_end"]
    if history:
        metric_values = (
            len(topics),
            sum(topic["coverage_history"]["total_items"] for topic in topics),
            sum(topic["coverage_history"]["total_source_days"] for topic in topics),
            sum(topic["coverage_history"]["active_days"] for topic in topics),
        )
        movement = _movement_chart(topics, language, history=True)
        companion = _history_overview(topics, language)
        gateway = "/agenda/" if french else "/en/agenda/"
    else:
        metric_values = (
            projection["metrics"]["public_topic_count"],
            projection["metrics"]["classified_item_count"],
            projection["metrics"]["source_day_count"],
            projection["metrics"]["publisher_count"],
        )
        movement = _movement_chart(topics, language)
        companion = _composition(topics, language)
        gateway = "/agenda/historique/" if french else "/en/agenda/history/"
    descriptor = (
        "Mesure descriptive des thèmes électoraux récurrents observés dans le corpus suivi. Ni opinion publique, ni priorités des électeurs ou des candidats, ni mesure représentative de tous les médias, ni prévision."
        if french
        else "A descriptive measure of recurring election themes observed in the monitored corpus. It is not public opinion, voter or candidate priorities, a representative measure of all media, or a forecast."
    )
    breadcrumb = (
        f'<nav class="polling-breadcrumb" aria-label="{"Fil d’Ariane" if french else "Breadcrumb"}"><a href="{"/" if french else "/en/"}">{"ACCUEIL" if french else "HOME"}</a><span>/</span>'
        + (f'<a href="{"/agenda/" if french else "/en/agenda/"}">AGENDA</a><span>/</span><span aria-current="page">{"HISTORIQUE" if french else "HISTORY"}</span>' if history else '<span aria-current="page">AGENDA</span>')
        + "</nav>"
    )
    evidence_rows = ""
    if not history:
        topic_by_id = {topic["topic_id"]: topic for topic in topics}
        for item in projection["latest_evidence"][:8]:
            badges = '<div class="agenda-evidence-badges">' + "".join(
                f'<a class="agenda-evidence-agenda" href="{_h(topic_by_id[topic_id]["routes"][language])}">{_h(topic_by_id[topic_id]["labels"][language])}</a>'
                for topic_id in item["topic_ids"]
            ) + "</div>"
            evidence_rows += _evidence_row(
                item,
                language,
                badges=badges,
                hub=True,
            )
    body_class = "polling-page agenda-page agenda-hub-page" + (" agenda-history-page" if history else "")
    return _document(f'''<!doctype html><html lang="{language}">{head}<body class="{body_class}"><main class="polling-shell">{header}
      {breadcrumb}
      <section class="polling-intro agenda-intro"><div class="polling-eyebrow">{'AGENDA · HISTORIQUE' if history and french else 'AGENDA · HISTORY' if history else 'AGENDA'}</div><div class="polling-title-row agenda-hub-title-row"><h1>{'HISTORIQUE DE L’AGENDA' if history and french else 'AGENDA HISTORY' if history else 'OBSERVATOIRE DE L’AGENDA' if french else 'CAMPAIGN AGENDA LAB'}</h1>{_tooltip('agenda-hub-method', 'Méthode' if french else 'Method', descriptor)}</div></section>
      <section class="polling-metrics agenda-metrics" aria-label="{'Indicateurs' if french else 'Metrics'}"><div class="polling-metric"><span class="polling-metric-label">{'THÈMES' if french else 'TOPICS'}</span><strong>{metric_values[0]}</strong></div><div class="polling-metric"><span class="polling-metric-label">{'ARTICLES CLASSÉS' if french else 'CLASSIFIED ITEMS'}</span><strong>{metric_values[1]}</strong></div><div class="polling-metric"><span class="polling-metric-label">{'JOURS-SOURCES' if french else 'SOURCE-DAYS'}</span><strong>{metric_values[2]}</strong></div><div class="polling-metric"><span class="polling-metric-label">{'JOURS ACTIFS' if history and french else 'ACTIVE DAYS' if history else 'MÉDIAS' if french else 'PUBLISHERS'}</span><strong>{metric_values[3]}</strong></div><div class="polling-metric polling-metric-period"><span class="polling-metric-label">{'PÉRIODE' if french else 'PERIOD'}</span><strong>{_h(_period(period_start, period_end, language))}</strong></div></section>
      <section class="polling-section agenda-landscape-panel"><div class="polling-section-head"><div><div class="polling-eyebrow">{'HISTORIQUE' if history and french else 'HISTORY' if history else '30 J' if french else '30D'}</div><h2>{'PAYSAGE HISTORIQUE DES THÈMES' if history and french else 'HISTORICAL TOPIC LANDSCAPE' if history else 'PAYSAGE DES THÈMES' if french else 'TOPIC LANDSCAPE'}</h2></div><span class="polling-panel-status">{len(topics)} {'THÈMES' if french else 'TOPICS'}</span></div><div class="agenda-landscape-toolbar"><div class="agenda-landscape-search"><input type="search" data-agenda-search placeholder="{'Rechercher un thème' if french else 'Search topics'}"></div><div class="agenda-sort-controls"><button type="button" data-agenda-sort="activity" aria-pressed="true">{'ACTIVITÉ' if french else 'ACTIVITY'}</button><button type="button" data-agenda-sort="movement" aria-pressed="false">{'MOUVEMENT' if french else 'MOVEMENT'}</button><button type="button" data-agenda-sort="volume" aria-pressed="false">VOLUME</button><button type="button" data-agenda-sort="az" aria-pressed="false">A–Z</button></div></div><div class="agenda-card-grid" data-agenda-card-grid>{cards}</div><div class="agenda-empty-state" data-agenda-empty hidden>{'Aucun thème correspondant.' if french else 'No matching topic.'}</div></section>
      <div class="agenda-comparison-grid"><section class="polling-section agenda-movement-panel"><div class="polling-section-head"><div><div class="polling-eyebrow">{'COMPARAISON' if french else 'COMPARISON'}</div><h2>{'ÉVOLUTION HISTORIQUE' if history and french else 'HISTORICAL MOVEMENT' if history else 'CE QUI BOUGE' if french else 'WHAT’S MOVING'}</h2></div><span class="polling-panel-status">{'PART AGENDA' if french else 'AGENDA SHARE'}</span></div>{movement}</section><section class="polling-section agenda-agenda-panel"><div class="polling-section-head"><div><div class="polling-eyebrow">{'LONGUE DURÉE' if history and french else 'LONG RANGE' if history else 'SEMAINES COMPLÈTES' if french else 'COMPLETE WEEKS'}</div><h2>{'ÉVOLUTION DES JOURS-SOURCES' if history and french else 'SOURCE-DAY EVOLUTION' if history else 'COMPOSITION DE L’AGENDA' if french else 'AGENDA COMPOSITION'}</h2></div><span class="polling-panel-status">{'ÉTIQUETTE UNIQUE' if french else 'SINGLE-LABEL'}</span></div>{companion}</section></div>
      {f'<section class="polling-section agenda-latest"><div class="polling-section-head"><div><div class="polling-eyebrow">SOURCES</div><h2>{"PREUVES SOURCÉES RÉCENTES" if french else "LATEST SOURCE-LINKED EVIDENCE"}</h2></div><span class="polling-panel-status">{min(8, len(projection["latest_evidence"]))}</span></div><div class="agenda-evidence-list">{evidence_rows}</div></section>' if not history else f'<section class="polling-section agenda-latest"><div class="polling-section-head"><div><div class="polling-eyebrow">{"MÉTHODE" if french else "METHOD"}</div><h2>{"PÉRIMÈTRE HISTORIQUE" if french else "HISTORICAL BOUNDARY"}</h2></div></div><p class="agenda-detail-note">{_h(descriptor)} {"Les séries utilisent uniquement des jours UTC complets et les classifications publiées conservées." if french else "Series use complete UTC days and retained published classifications only."}</p></section>'}
      <section class="polling-section agenda-history-gateway is-compact"><div class="polling-section-head"><div><div class="polling-eyebrow">{'PROJECTION ACTUELLE' if history and french else 'CURRENT PROJECTION' if history else 'HISTORIQUE DISPONIBLE' if french else 'HISTORY AVAILABLE'}</div><h2>{'AGENDA ACTUEL' if history and french else 'CURRENT AGENDA' if history else 'HISTORIQUE DE L’AGENDA' if french else 'AGENDA HISTORY'}</h2></div><span class="polling-panel-status">{len(topics)}</span></div><div class="agenda-history-gateway-body"><div><strong>{'REVENIR AUX 30 DERNIERS JOURS' if history and french else 'RETURN TO THE LATEST 30 DAYS' if history else 'EXPLORER LA SÉRIE COMPLÈTE' if french else 'EXPLORE THE COMPLETE SERIES'}</strong><span>{_h(_period(period_start, period_end, language))}</span></div><a class="agenda-history-gateway-cta" href="{gateway}">{'OUVRIR →' if french else 'OPEN →'}</a></div></section>
      {shell["footer"]}</main></body></html>''')


def _current_detail(
    projection: dict[str, Any],
    topic: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
) -> bytes:
    french = language == "fr"
    label = topic["labels"][language]
    route = topic["routes"][language]
    current = topic["current"]
    comparison = current["comparison"]
    title = f"{label} — Agenda 2027 | France 2027" if french else f"{label} — France 2027 Agenda dossier"
    description = (
        f"Dossier descriptif sur {label} dans le corpus de campagne suivi : activité, signaux de classification et sources."
        if french
        else f"Descriptive dossier on {label} in the monitored campaign corpus: activity, classifier signals, and sources."
    )
    head = _head(
        language=language,
        title=title,
        description=description,
        route=route,
        route_fr=topic["routes"]["fr"],
        route_en=topic["routes"]["en"],
        favicon=favicon,
        og_image=og_image,
        structured=[_breadcrumb_json(language=language, route=route, topic=topic)],
    )
    header = _prepare_header(shell["header"], language=language, route_fr=topic["routes"]["fr"], route_en=topic["routes"]["en"])
    bars = _microbars(current["daily_activity"], language=language, class_name="agenda-detail-activity-bars")
    signals = "".join(
        f'<li><div><span>{_h(signal["term"])}</span><strong>{signal["item_count"]}</strong></div><i style="--agenda-subtopic-share:{signal["item_count"] / max(1, current["matched_term_counts"][0]["item_count"]):.6f}"></i></li>'
        for signal in current["matched_term_counts"]
    ) or f'<p class="agenda-detail-note">{"Aucun signal associé publié." if french else "No associated classifier signal published."}</p>'
    evidence = "".join(
        _evidence_row({**item, "date": item["published_at"][:10]}, language)
        for item in current["supporting_items"]
    ) or f'<p class="agenda-detail-note">{"Aucune preuve récente publiée." if french else "No recent evidence published."}</p>'
    omission = current["omitted_item_count"]
    candidates = topic["current_candidate_associations"]
    candidate_rows = _candidate_rows(candidates, language)
    sparse = ""
    if topic["lifecycle"] == "dormant":
        sparse = f'<div class="agenda-detail-note agenda-sparse-state">{"Ce thème est conservé parce qu’il a déjà été publié ; son activité actuelle est sous le seuil d’affichage." if french else "This topic is retained because it was previously published; current activity is below the display threshold."}</div>'
    candidate_note = (
        "Cooccurrences candidat × thème observées dans la couverture suivie. Elles ne décrivent ni soutien, ni position, ni priorité, ni engagement."
        if french
        else "Candidate × topic co-occurrences observed in monitored coverage. They do not describe endorsement, position, priority, or commitment."
    )
    history_route = topic["routes"]["history_fr" if french else "history_en"]
    return _document(f'''<!doctype html><html lang="{language}">{head}<body class="polling-page poll-detail-page agenda-page agenda-detail-page agenda-current-detail-page"><main class="polling-shell">{header}<div class="poll-detail-content">
      <nav class="poll-detail-breadcrumb"><a href="{'/' if french else '/en/'}">{'ACCUEIL' if french else 'HOME'}</a><span>/</span><a href="{'/agenda/' if french else '/en/agenda/'}">AGENDA</a><span>/</span><span aria-current="page">{_h(label)}</span></nav>
      <section class="poll-detail-hero agenda-detail-hero"><div class="poll-detail-hero-main"><div><div class="poll-detail-eyebrow">{'THÈME · AGENDA DE CAMPAGNE' if french else 'TOPIC · CAMPAIGN AGENDA'}</div><div class="poll-detail-title-line"><h1 class="poll-detail-title">{_h(label)}</h1><span class="agenda-state is-{_h(topic["lifecycle"])}">{_h(_lifecycle_label(topic["lifecycle"], language))}</span></div></div></div>{sparse}<div class="poll-detail-metrics agenda-current-kpis"><div class="poll-detail-metric"><span>{'JOURS-SOURCES · 30 J' if french else 'SOURCE-DAYS · 30D'}</span><strong>{current["source_day_count"]}</strong></div><div class="poll-detail-metric"><span>{'ARTICLES CLASSÉS · 30 J' if french else 'CLASSIFIED ITEMS · 30D'}</span><strong>{current["item_count"]}</strong></div><div class="poll-detail-metric"><span>{'MÉDIAS · BASE' if french else 'PUBLISHERS · BASE'}</span><strong>{current["publisher_count"]}</strong></div><div class="poll-detail-metric"><span>{'JOURS ACTIFS' if french else 'ACTIVE DAYS'}</span><strong>{current["active_day_count"]}</strong></div><div class="agenda-weekly-signal"><span class="agenda-weekly-signal-title">{'MOUVEMENT · SEMAINES COMPLÈTES' if french else 'MOVEMENT · COMPLETE WEEKS'}</span><div class="agenda-weekly-signal-values"><div><span>{'JOURS-SOURCES' if french else 'SOURCE-DAYS'}</span><strong>{_h(_signed(comparison["source_day_change"], language))}</strong></div><div><span>{'PART AGENDA' if french else 'AGENDA SHARE'}</span><strong>{_h(_signed(comparison["agenda_share_change_pp"], language, "pp"))}</strong></div></div></div></div></section>
      <div class="agenda-current-detail-grid agenda-current-top-grid"><section class="poll-detail-panel agenda-current-activity"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{'ACTIVITÉ · 30 J' if french else 'ACTIVITY · 30D'}</div><h2>{'ACTIVITÉ ACTUELLE' if french else 'CURRENT ACTIVITY'}</h2></div><span class="poll-detail-panel-status">{current["source_day_count"]} {'JOURS-SOURCES' if french else 'SOURCE-DAYS'}</span></div>{bars}<dl class="agenda-current-comparison"><div><dt>{'SEMAINE PRÉC.' if french else 'PREVIOUS WEEK'}</dt><dd>{comparison["previous_source_day_count"]}</dd><small>{_h(_period(comparison["previous_start"], comparison["previous_end"], language))}</small></div><div><dt>{'SEMAINE RÉCENTE' if french else 'RECENT WEEK'}</dt><dd>{comparison["latest_source_day_count"]}</dd><small>{_h(_period(comparison["latest_start"], comparison["latest_end"], language))}</small></div><div class="is-delta"><dt>{'PART AGENDA' if french else 'AGENDA SHARE'}</dt><dd>{_h(_decimal(comparison["latest_agenda_share"] * 100, language))}%</dd><small>{_h(_signed(comparison["agenda_share_change_pp"], language, "pp"))}</small></div></dl></section>
      <section class="poll-detail-panel agenda-subtopics"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{'CLASSIFICATION' if french else 'CLASSIFICATION'}</div><h2>{'SIGNAUX ASSOCIÉS' if french else 'ASSOCIATED CLASSIFIER SIGNALS'}</h2></div><span class="poll-detail-panel-status">{len(current["matched_term_counts"])}</span></div><ol class="agenda-subtopics-scroll">{signals}</ol></section></div>
      <section class="poll-detail-panel agenda-published-evidence agenda-current-evidence"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">SOURCES</div><h2>{'PREUVES RÉCENTES' if french else 'RECENT SUPPORTING EVIDENCE'}</h2></div><span class="poll-detail-panel-status">{current["supporting_item_count"]} {'PUBLIÉES' if french else 'PUBLISHED'} · {omission} {'OMISES' if french else 'OMITTED'}</span></div><div class="agenda-evidence-list agenda-current-evidence-visible">{evidence}</div>{f'<p class="agenda-detail-note">{omission} éléments supplémentaires ne sont pas affichés en raison du plafond de publication.</p>' if omission and french else f'<p class="agenda-detail-note">{omission} additional items are not shown because of the publication cap.</p>' if omission else ''}</section>
      <section class="poll-detail-panel agenda-candidates agenda-current-candidates"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{'DOMAINE SÉPARÉ' if french else 'SEPARATE DOMAIN'}</div><div class="agenda-note-title-line"><h2>{'COOCCURRENCES CANDIDAT × THÈME' if french else 'CANDIDATE × TOPIC CO-OCCURRENCES'}</h2>{_tooltip('agenda-candidate-note', 'Note', candidate_note, warning=True)}</div></div><span class="poll-detail-panel-status">{candidates["candidate_count"]}</span></div><div class="agenda-candidate-ledgers"><ul class="agenda-candidate-column">{candidate_rows}</ul></div></section>
      <section class="polling-section agenda-history-gateway is-compact"><div class="polling-section-head"><div><div class="polling-eyebrow">{'LONGUE DURÉE' if french else 'LONG RANGE'}</div><h2>{'HISTORIQUE DE CE THÈME' if french else 'THIS TOPIC’S HISTORY'}</h2></div><span class="polling-panel-status">{topic["coverage_history"]["total_source_days"]} {'JOURS-SOURCES' if french else 'SOURCE-DAYS'}</span></div><div class="agenda-history-gateway-body"><div><strong>{_h(_period(topic["coverage_history"]["first_observation"], topic["coverage_history"]["last_observation"], language))}</strong><span>{topic["coverage_history"]["active_days"]} {'jours actifs' if french else 'active days'}</span></div><a class="agenda-history-gateway-cta" href="{_h(history_route)}">{'VOIR L’HISTORIQUE →' if french else 'VIEW HISTORY →'}</a></div></section>
      </div>{shell["footer"]}</main></body></html>''')


def _history_detail(
    projection: dict[str, Any],
    topic: dict[str, Any],
    *,
    language: str,
    shell: dict[str, str],
    favicon: str,
    og_image: str,
) -> bytes:
    french = language == "fr"
    label = topic["labels"][language]
    history = topic["coverage_history"]
    route_key = "history_fr" if french else "history_en"
    route = topic["routes"][route_key]
    title = f"Historique — {label} | France 2027" if french else f"{label} — Agenda history | France 2027"
    description = (
        f"Historique descriptif de {label} dans le corpus de campagne suivi."
        if french
        else f"Descriptive history of {label} in the monitored campaign corpus."
    )
    head = _head(
        language=language,
        title=title,
        description=description,
        route=route,
        route_fr=topic["routes"]["history_fr"],
        route_en=topic["routes"]["history_en"],
        favicon=favicon,
        og_image=og_image,
        structured=[_breadcrumb_json(language=language, route=route, topic=topic, history=True)],
    )
    header = _prepare_header(shell["header"], language=language, route_fr=topic["routes"]["history_fr"], route_en=topic["routes"]["history_en"])
    ranked = sorted(
        [point for point in history["daily"] if point["item_count"]],
        key=lambda point: (-point["source_day_count"], -point["item_count"], point["date"]),
    )[:5]
    peak_max = ranked[0]["source_day_count"] if ranked else 1
    peaks = "".join(
        f'<li data-peak-day="{point["date"]}"><div class="agenda-history-peak-day-primary"><time>{_h(_date(point["date"], language))}</time><strong>{point["source_day_count"]}</strong></div><span>{point["item_count"]} {"articles" if french else "items"} · {_decimal(point["topic_source_day_share"] * 100, language, 2)}%</span><i class="agenda-history-peak-day-magnitude" style="--agenda-history-peak-share:{point["source_day_count"] / peak_max:.6f}"></i></li>'
        for point in ranked
    ) or f'<p class="agenda-detail-note">{"Aucun jour actif observé." if french else "No active day observed."}</p>'
    associations = topic["historical_candidate_associations"]
    candidate_rows = _candidate_rows(associations, language, historical=True)
    ledger = "".join(
        f'<tr><td data-label="DATE"><time datetime="{point["date"]}">{_h(_date(point["date"], language))}</time></td><td data-label="{"ARTICLES" if french else "ITEMS"}">{point["item_count"]}</td><td data-label="{"JOURS-SOURCES" if french else "SOURCE-DAYS"}">{point["source_day_count"]}</td><td data-label="{"TOTAL ARTICLES" if french else "TOTAL ITEMS"}">{point["total_classified_agenda_items"]}</td><td data-label="{"TOTAL JOURS-SOURCES" if french else "TOTAL SOURCE-DAYS"}">{point["total_agenda_topic_source_days"]}</td><td data-label="{"PART" if french else "SHARE"}">{_decimal(point["topic_source_day_share"] * 100, language, 2)}%</td></tr>'
        for point in history["daily"]
    )
    candidate_note = (
        "Associations candidat × thème observées, distinctes des volumes médiatiques. Un article peut produire plusieurs associations de candidats."
        if french
        else "Observed candidate × topic associations, separate from media volumes. One article may produce multiple candidate associations."
    )
    return _document(f'''<!doctype html><html lang="{language}">{head}<body class="polling-page poll-detail-page agenda-page agenda-detail-page agenda-history-detail-page"><main class="polling-shell">{header}<div class="poll-detail-content">
      <nav class="poll-detail-breadcrumb"><a href="{'/' if french else '/en/'}">{'ACCUEIL' if french else 'HOME'}</a><span>/</span><a href="{'/agenda/' if french else '/en/agenda/'}">AGENDA</a><span>/</span><a href="{'/agenda/historique/' if french else '/en/agenda/history/'}">{'HISTORIQUE' if french else 'HISTORY'}</a><span>/</span><span aria-current="page">{_h(label)}</span></nav>
      <section class="poll-detail-hero agenda-detail-hero"><div class="poll-detail-hero-main"><div><div class="poll-detail-eyebrow">{'THÈME · HISTORIQUE' if french else 'TOPIC · HISTORY'}</div><div class="poll-detail-title-line"><h1 class="poll-detail-title">{_h(label)}</h1><span class="agenda-state is-{_h(topic["lifecycle"])}">{_h(_lifecycle_label(topic["lifecycle"], language))}</span></div></div></div><div class="poll-detail-metrics"><div class="poll-detail-metric"><span>{'ARTICLES CLASSÉS' if french else 'CLASSIFIED ITEMS'}</span><strong>{history["total_items"]}</strong></div><div class="poll-detail-metric"><span>{'JOURS-SOURCES' if french else 'SOURCE-DAYS'}</span><strong>{history["total_source_days"]}</strong></div><div class="poll-detail-metric"><span>{'JOURS ACTIFS' if french else 'ACTIVE DAYS'}</span><strong>{history["active_days"]}</strong></div><div class="poll-detail-metric"><span>{'PREMIÈRE OBS.' if french else 'FIRST OBS.'}</span><strong>{_h(_date(history["first_observation"], language))}</strong></div><div class="poll-detail-metric"><span>{'MAX GLISSANT · 30 J' if french else 'MAX ROLLING · 30D'}</span><strong>{history["maximum_rolling_30d_source_days"]}</strong></div></div></section>
      <div class="agenda-history-detail-grid agenda-history-detail-top-grid"><section class="poll-detail-panel agenda-history-detail-evolution"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">LONGITUDINAL</div><h2>{'ÉVOLUTION JOURS-SOURCES / PART AGENDA' if french else 'SOURCE-DAY / AGENDA-SHARE EVOLUTION'}</h2></div><span class="poll-detail-panel-status">{history["active_days"]} {'JOURS ACTIFS' if french else 'ACTIVE DAYS'}</span></div>{_history_visual(topic, language)}</section><aside class="poll-detail-panel agenda-history-context agenda-history-peaks"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{'REPÈRES' if french else 'HIGHLIGHTS'}</div><h2>{'JOURS DE PIC' if french else 'PEAK DAYS'}</h2></div><span class="poll-detail-panel-status">{len(ranked)}</span></div><ol class="agenda-history-peak-days">{peaks}</ol></aside></div>
      <section class="poll-detail-panel agenda-history agenda-history-candidates"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{'DOMAINE SÉPARÉ' if french else 'SEPARATE DOMAIN'}</div><div class="agenda-note-title-line"><h2>{'REGISTRE DES ASSOCIATIONS CANDIDAT × THÈME' if french else 'CANDIDATE × TOPIC ASSOCIATION LEDGER'}</h2>{_tooltip('agenda-history-candidate-note', 'Note', candidate_note, warning=True)}</div></div><span class="poll-detail-panel-status">{associations["candidate_count"]}</span></div><div class="agenda-history-candidate-ledgers"><ul class="agenda-history-candidate-column">{candidate_rows}</ul></div></section>
      <section class="poll-detail-panel agenda-history-daily"><div class="poll-detail-panel-head"><div><div class="poll-detail-eyebrow">{'DONNÉES' if french else 'DATA'}</div><h2>{'REGISTRE JOUR PAR JOUR' if french else 'DAY-BY-DAY LEDGER'}</h2></div><span class="poll-detail-panel-status">{len(history["daily"])} {'JOURS' if french else 'DAYS'}</span></div><div class="agenda-history-table-wrap agenda-history-daily-ledger"><table class="agenda-history-table"><thead><tr><th>DATE</th><th>{'ARTICLES' if french else 'ITEMS'}</th><th>{'JOURS-SOURCES' if french else 'SOURCE-DAYS'}</th><th>{'TOTAL ARTICLES' if french else 'TOTAL ITEMS'}</th><th>{'TOTAL JOURS-SOURCES' if french else 'TOTAL SOURCE-DAYS'}</th><th>{'PART AGENDA' if french else 'AGENDA SHARE'}</th></tr></thead><tbody>{ledger}</tbody></table></div></section>
      <div class="agenda-history-detail-actions"><a class="poll-detail-back-cta agenda-history-current-cta" href="{_h(topic["routes"][language])}">{'VOIR L’ÉTAT ACTUEL →' if french else 'VIEW CURRENT STATE →'}</a><a class="poll-detail-back-cta agenda-history-hub-cta" href="{'/agenda/historique/' if french else '/en/agenda/history/'}">{'TOUT L’HISTORIQUE DE L’AGENDA →' if french else 'ALL AGENDA HISTORY →'}</a></div>
      </div>{shell["footer"]}</main></body></html>''')


def serialize_manifest(payload: dict[str, Any]) -> bytes:
    validate_agenda_manifest(payload)
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_from_paths(
    *,
    root: Path = ROOT,
    news_wire_path: Path = NEWS_WIRE_PATH,
    agenda_history_path: Path = AGENDA_HISTORY_PATH,
    coverage_history_path: Path = COVERAGE_HISTORY_PATH,
    candidate_registry_path: Path = CANDIDATE_REGISTRY_PATH,
    manifest_path: Path = MANIFEST_PATH,
    write: bool = True,
) -> dict[str, Any]:
    previous_manifest = _load_json(manifest_path) if manifest_path.exists() else None
    candidate_history = _load_json(agenda_history_path)
    candidate_registry = _load_json(candidate_registry_path)
    candidate_index = project_candidate_route_index(candidate_registry, root)
    base_projection = project_agenda_pages(
        _load_json(news_wire_path),
        _load_json(coverage_history_path),
        previous_manifest=previous_manifest,
        candidate_history=candidate_history,
    )
    projection = _enrich_projection(
        base_projection, candidate_history, candidate_index["candidates"]
    )
    coverage_history = _load_json(coverage_history_path)
    projection["coverage_history_period"] = coverage_history["period"]
    templates = load_shell_templates(root)
    poll_manifest = _load_json(root / "poll_pages_manifest.json")
    wave_count = poll_manifest.get("wave_count")
    if type(wave_count) is not int or wave_count < 0:
        raise AgendaPageBuildError("poll page manifest wave_count is invalid")
    for template in templates.values():
        template["footer"] = prepare_footer(template["footer"], wave_count)
    favicon = _site_favicon_link(root)
    og_image = _site_og_image_url(root)
    artifacts: dict[Path, bytes] = {
        Path("agenda/index.html"): _hub_common(projection, language="fr", shell=templates["fr"], favicon=favicon, og_image=og_image, history=False),
        Path("en/agenda/index.html"): _hub_common(projection, language="en", shell=templates["en"], favicon=favicon, og_image=og_image, history=False),
        Path("agenda/historique/index.html"): _hub_common(projection, language="fr", shell=templates["fr"], favicon=favicon, og_image=og_image, history=True),
        Path("en/agenda/history/index.html"): _hub_common(projection, language="en", shell=templates["en"], favicon=favicon, og_image=og_image, history=True),
    }
    for topic in projection["topics"]:
        artifacts[Path("agenda") / topic["slugs"]["fr"] / "index.html"] = _current_detail(projection, topic, language="fr", shell=templates["fr"], favicon=favicon, og_image=og_image)
        artifacts[Path("en") / "agenda" / topic["slugs"]["en"] / "index.html"] = _current_detail(projection, topic, language="en", shell=templates["en"], favicon=favicon, og_image=og_image)
        artifacts[Path("agenda") / "historique" / topic["slugs"]["fr"] / "index.html"] = _history_detail(projection, topic, language="fr", shell=templates["fr"], favicon=favicon, og_image=og_image)
        artifacts[Path("en") / "agenda" / "history" / topic["slugs"]["en"] / "index.html"] = _history_detail(projection, topic, language="en", shell=templates["en"], favicon=favicon, og_image=og_image)
    manifest = agenda_manifest_payload(projection)
    manifest_bytes = serialize_manifest(manifest)
    if write:
        for relative, content in artifacts.items():
            _atomic_write(root / relative, content)
        _atomic_write(manifest_path, manifest_bytes)
    return {"projection": projection, "manifest": manifest, "artifacts": artifacts}


def _generated_files(root: Path) -> set[Path]:
    files: set[Path] = set()
    for base in (root / "agenda", root / "en" / "agenda"):
        if base.exists():
            files.update(path.relative_to(root) for path in base.rglob("index.html"))
    return files


def _same_text_bytes(actual: bytes, expected: bytes) -> bool:
    try:
        actual_text = actual.decode("utf-8").replace("\r\n", "\n")
        expected_text = expected.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return False
    return actual_text == expected_text


def check_from_paths(**paths: Any) -> list[str]:
    result = build_from_paths(**paths, write=False)
    errors = []
    for relative, expected in result["artifacts"].items():
        target = paths.get("root", ROOT) / relative
        if not target.exists():
            errors.append(f"missing: {relative.as_posix()}")
        elif not _same_text_bytes(target.read_bytes(), expected):
            errors.append(f"out of date: {relative.as_posix()}")
    manifest_path = paths.get("manifest_path", MANIFEST_PATH)
    expected_manifest = serialize_manifest(result["manifest"])
    if not manifest_path.exists():
        errors.append(f"missing: {manifest_path.name}")
    elif not _same_text_bytes(manifest_path.read_bytes(), expected_manifest):
        errors.append(f"out of date: {manifest_path.name}")
    expected_pages = set(result["artifacts"])
    for stale in sorted(_generated_files(paths.get("root", ROOT)) - expected_pages):
        errors.append(f"stale generated Agenda page: {stale.as_posix()}")
    return errors


def thin_page_audit(result: dict[str, Any], root: Path) -> list[str]:
    findings = []
    for relative in sorted(result["artifacts"]):
        target = root / relative
        if not target.exists():
            findings.append(f"missing page: {relative.as_posix()}")
            continue
        text = target.read_text(encoding="utf-8")
        visible = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", text, flags=re.I | re.S)
        visible = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", visible))).strip()
        if len(visible) < 900:
            findings.append(f"suspiciously little visible content: {relative.as_posix()} ({len(visible)} chars)")
        for marker, label in (("<h1", "H1"), ('rel="canonical"', "canonical"), ('hreflang="fr"', "French alternate"), ('hreflang="en"', "English alternate"), ('hreflang="x-default"', "x-default")):
            if marker not in text:
                findings.append(f"missing {label}: {relative.as_posix()}")
        if "None" in text or ">null<" in text:
            findings.append(f"null leakage: {relative.as_posix()}")
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build FR27 bilingual Agenda pages")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--news-wire", type=Path, default=NEWS_WIRE_PATH)
    parser.add_argument("--agenda-history", type=Path, default=AGENDA_HISTORY_PATH)
    parser.add_argument("--coverage-history", type=Path, default=COVERAGE_HISTORY_PATH)
    parser.add_argument("--candidate-registry", type=Path, default=CANDIDATE_REGISTRY_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--thin-audit", action="store_true")
    return parser


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
                    print(f"Agenda page check: {error}")
                return 1
            manifest = _load_json(arguments.manifest)
            print(f"Agenda page check clean: {manifest['public_topic_count']} topics, {manifest['page_count']} routes")
            return 0
        if arguments.thin_audit:
            result = build_from_paths(**common, write=False)
            findings = thin_page_audit(result, arguments.root)
            if findings:
                for finding in findings:
                    print(f"Agenda thin-page audit: {finding}")
                return 1
            print("Agenda thin-page audit clean")
            return 0
        result = build_from_paths(**common)
    except (
        AgendaPageContractError,
        AgendaPageBuildError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(f"Agenda page build error: {error}")
        return 1
    manifest = result["manifest"]
    print(f"built Agenda pages: {manifest['public_topic_count']} public topics, {manifest['page_count']} routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
