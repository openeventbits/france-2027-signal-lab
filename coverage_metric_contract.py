"""Shared analytical metric contract for FR27 public pages and social publishing.

No HTML, Buffer, network or publication-state logic belongs here.
The module turns published history artifacts into explicit, auditable
metric snapshots with deterministic display arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from agenda_page_contract import AGENDA_DEFINITIONS
from issue_page_contract import ISSUE_DEFINITIONS


PUBLIC_ORIGIN = "https://france2027.app"

WINDOW_COMPLETE_DAY = "complete_day"
WINDOW_COMPLETE_WEEK = "complete_week"

ISSUES_DAILY_METRIC_ID = "issues_article_presence_share_complete_day"
ISSUES_WEEKLY_METRIC_ID = "issues_article_presence_share_complete_week"

AGENDA_DAILY_METRIC_ID = "agenda_source_day_share_complete_day"
AGENDA_WEEKLY_METRIC_ID = "agenda_source_day_share_complete_week"


class MetricContractError(ValueError):
    """Raised when a metric cannot be constructed without ambiguity."""


@dataclass(frozen=True)
class MetricRow:
    entity_id: str
    label_fr: str
    label_en: str

    previous_raw: float
    current_raw: float

    previous_display: float
    current_display: float
    display_delta: float

    previous_evidence: int
    current_evidence: int

    previous_denominator: int
    current_denominator: int

    canonical_url_fr: str
    canonical_url_en: str


@dataclass(frozen=True)
class MetricSnapshot:
    metric_id: str
    family: str

    aggregation_unit: str
    denominator_id: str
    window_mode: str

    as_of: str
    source_artifact: str

    previous_start: str
    previous_end: str
    current_start: str
    current_end: str

    interpretation_boundary_fr: str
    interpretation_boundary_en: str

    rows: tuple[MetricRow, ...]


def display_round(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(
            Decimal("0.1"),
            rounding=ROUND_HALF_UP,
        )
    )


def display_triplet(
    previous_raw: float,
    current_raw: float,
) -> tuple[float, float, float]:
    previous_display = display_round(previous_raw)
    current_display = display_round(current_raw)

    display_delta = display_round(
        current_display - previous_display
    )

    if display_delta != display_round(
        current_display - previous_display
    ):
        raise MetricContractError(
            "display delta does not reconcile with displayed endpoints"
        )

    return (
        previous_display,
        current_display,
        display_delta,
    )


def _require_mapping(
    value: Any,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MetricContractError(
            f"{label} must be an object"
        )
    return value


def _require_rows(
    value: Any,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise MetricContractError(
            f"{label} must be an array"
        )

    result = []

    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise MetricContractError(
                f"{label}[{index}] must be an object"
            )
        result.append(row)

    return result


def _iso_date(
    value: Any,
    label: str,
) -> str:
    if not isinstance(value, str):
        raise MetricContractError(
            f"{label} must be an ISO date"
        )

    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise MetricContractError(
            f"{label} must be an ISO date"
        ) from error

    if parsed.isoformat() != value:
        raise MetricContractError(
            f"{label} must be a canonical ISO date"
        )

    return value


def _ordered_dates(
    rows: list[dict[str, Any]],
) -> list[str]:
    dates = [
        _iso_date(row.get("date"), "date")
        for row in rows
    ]

    if dates != sorted(dates):
        raise MetricContractError(
            "metric history dates must be sorted"
        )

    if len(set(dates)) != len(dates):
        raise MetricContractError(
            "metric history dates must be unique"
        )

    return dates


def _calendar_range(
    start: date,
    end: date,
) -> tuple[str, ...]:
    return tuple(
        (start + timedelta(days=offset)).isoformat()
        for offset in range(
            (end - start).days + 1
        )
    )


def _complete_day_windows(
    available_dates: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    dates = tuple(available_dates)

    if len(dates) < 2:
        raise MetricContractError(
            "complete-day comparison requires two complete days"
        )

    return (
        (dates[-2],),
        (dates[-1],),
    )


def _complete_week_windows(
    available_dates: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    dates = tuple(available_dates)

    if not dates:
        raise MetricContractError(
            "complete-week comparison requires history"
        )

    available = set(dates)
    final_available = date.fromisoformat(dates[-1])

    current_end = final_available - timedelta(
        days=(final_available.weekday() + 1) % 7
    )
    current_start = current_end - timedelta(days=6)

    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    previous = _calendar_range(
        previous_start,
        previous_end,
    )
    current = _calendar_range(
        current_start,
        current_end,
    )

    missing = [
        day
        for day in (*previous, *current)
        if day not in available
    ]

    if missing:
        raise MetricContractError(
            "history does not contain two complete Monday-Sunday weeks"
        )

    return previous, current


def _windows(
    available_dates: Iterable[str],
    window_mode: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    dates = tuple(available_dates)

    if window_mode == WINDOW_COMPLETE_DAY:
        return _complete_day_windows(dates)

    if window_mode == WINDOW_COMPLETE_WEEK:
        return _complete_week_windows(dates)

    raise MetricContractError(
        f"unsupported window mode: {window_mode}"
    )


def _share(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        raise MetricContractError(
            "metric denominator must be positive"
        )

    if numerator < 0:
        raise MetricContractError(
            "metric numerator must be non-negative"
        )

    return numerator / denominator * 100.0


def _make_row(
    *,
    entity_id: str,
    label_fr: str,
    label_en: str,
    previous_evidence: int,
    current_evidence: int,
    previous_denominator: int,
    current_denominator: int,
    canonical_url_fr: str,
    canonical_url_en: str,
) -> MetricRow:
    previous_raw = _share(
        previous_evidence,
        previous_denominator,
    )

    current_raw = _share(
        current_evidence,
        current_denominator,
    )

    (
        previous_display,
        current_display,
        display_delta,
    ) = display_triplet(
        previous_raw,
        current_raw,
    )

    return MetricRow(
        entity_id=entity_id,
        label_fr=label_fr,
        label_en=label_en,
        previous_raw=previous_raw,
        current_raw=current_raw,
        previous_display=previous_display,
        current_display=current_display,
        display_delta=display_delta,
        previous_evidence=previous_evidence,
        current_evidence=current_evidence,
        previous_denominator=previous_denominator,
        current_denominator=current_denominator,
        canonical_url_fr=canonical_url_fr,
        canonical_url_en=canonical_url_en,
    )


def _sum_field(
    rows: list[dict[str, Any]],
    dates: set[str],
    field: str,
) -> int:
    return sum(
        int(row.get(field) or 0)
        for row in rows
        if str(row.get("date") or "") in dates
    )


def build_issue_metric_snapshot(
    payload: dict[str, Any],
    *,
    window_mode: str,
) -> MetricSnapshot:
    root = _require_mapping(
        payload,
        "issue coverage history",
    )

    corpus = _require_mapping(
        root.get("corpus"),
        "issue coverage history corpus",
    )

    corpus_daily = _require_rows(
        corpus.get("daily"),
        "issue corpus daily",
    )

    dates = _ordered_dates(corpus_daily)

    previous_dates, current_dates = _windows(
        dates,
        window_mode,
    )

    previous_set = set(previous_dates)
    current_set = set(current_dates)

    previous_denominator = _sum_field(
        corpus_daily,
        previous_set,
        "item_count",
    )

    current_denominator = _sum_field(
        corpus_daily,
        current_set,
        "item_count",
    )

    if previous_denominator <= 0 or current_denominator <= 0:
        raise MetricContractError(
            "issue comparison corpus is empty"
        )

    issue_index = {
        str(row.get("id") or ""): row
        for row in _require_rows(
            root.get("issues"),
            "issue history issues",
        )
    }

    rows = []

    for definition in ISSUE_DEFINITIONS:
        issue = issue_index.get(definition.issue_id)

        if issue is None:
            raise MetricContractError(
                f"missing issue history: {definition.issue_id}"
            )

        daily = _require_rows(
            issue.get("daily"),
            f"{definition.issue_id}.daily",
        )

        previous_evidence = _sum_field(
            daily,
            previous_set,
            "item_count",
        )

        current_evidence = _sum_field(
            daily,
            current_set,
            "item_count",
        )

        rows.append(
            _make_row(
                entity_id=definition.issue_id,
                label_fr=definition.label_fr,
                label_en=definition.label_en,
                previous_evidence=previous_evidence,
                current_evidence=current_evidence,
                previous_denominator=previous_denominator,
                current_denominator=current_denominator,
                canonical_url_fr=(
                    PUBLIC_ORIGIN + definition.routes["fr"]
                ),
                canonical_url_en=(
                    PUBLIC_ORIGIN + definition.routes["en"]
                ),
            )
        )

    metric_id = (
        ISSUES_DAILY_METRIC_ID
        if window_mode == WINDOW_COMPLETE_DAY
        else ISSUES_WEEKLY_METRIC_ID
    )

    return MetricSnapshot(
        metric_id=metric_id,
        family="issues",
        aggregation_unit="issue_classified_article",
        denominator_id="accepted_relevant_news_article_corpus",
        window_mode=window_mode,
        as_of=str(root.get("data_as_of") or ""),
        source_artifact="issue_coverage_history.json",
        previous_start=previous_dates[0],
        previous_end=previous_dates[-1],
        current_start=current_dates[0],
        current_end=current_dates[-1],
        interpretation_boundary_fr=(
            "Présence dans la couverture électorale suivie ; "
            "ne mesure pas l’opinion publique. "
            "Les catégories sont multilabel."
        ),
        interpretation_boundary_en=(
            "Presence in monitored election coverage; "
            "not a measure of public opinion. "
            "Categories are multilabel."
        ),
        rows=tuple(rows),
    )


def build_agenda_metric_snapshot(
    payload: dict[str, Any],
    *,
    window_mode: str,
) -> MetricSnapshot:
    root = _require_mapping(
        payload,
        "Agenda coverage history",
    )

    daily_denominators = _require_rows(
        root.get("daily"),
        "Agenda history daily",
    )

    dates = _ordered_dates(daily_denominators)

    previous_dates, current_dates = _windows(
        dates,
        window_mode,
    )

    previous_set = set(previous_dates)
    current_set = set(current_dates)

    previous_denominator = _sum_field(
        daily_denominators,
        previous_set,
        "total_agenda_topic_source_days",
    )

    current_denominator = _sum_field(
        daily_denominators,
        current_set,
        "total_agenda_topic_source_days",
    )

    if previous_denominator <= 0 or current_denominator <= 0:
        raise MetricContractError(
            "Agenda source-day denominator is empty"
        )

    topic_index = {
        str(row.get("id") or ""): row
        for row in _require_rows(
            root.get("topics"),
            "Agenda history topics",
        )
    }

    rows = []

    for definition in AGENDA_DEFINITIONS:
        topic = topic_index.get(definition.topic_id)

        if topic is None:
            raise MetricContractError(
                f"missing Agenda history: {definition.topic_id}"
            )

        daily = _require_rows(
            topic.get("daily"),
            f"{definition.topic_id}.daily",
        )

        previous_evidence = _sum_field(
            daily,
            previous_set,
            "source_day_count",
        )

        current_evidence = _sum_field(
            daily,
            current_set,
            "source_day_count",
        )

        rows.append(
            _make_row(
                entity_id=definition.topic_id,
                label_fr=definition.label_fr,
                label_en=definition.label_en,
                previous_evidence=previous_evidence,
                current_evidence=current_evidence,
                previous_denominator=previous_denominator,
                current_denominator=current_denominator,
                canonical_url_fr=(
                    PUBLIC_ORIGIN + definition.routes["fr"]
                ),
                canonical_url_en=(
                    PUBLIC_ORIGIN + definition.routes["en"]
                ),
            )
        )

    if (
        sum(row.previous_evidence for row in rows)
        != previous_denominator
    ):
        raise MetricContractError(
            "previous Agenda source-day denominator does not reconcile"
        )

    if (
        sum(row.current_evidence for row in rows)
        != current_denominator
    ):
        raise MetricContractError(
            "current Agenda source-day denominator does not reconcile"
        )

    metric_id = (
        AGENDA_DAILY_METRIC_ID
        if window_mode == WINDOW_COMPLETE_DAY
        else AGENDA_WEEKLY_METRIC_ID
    )

    return MetricSnapshot(
        metric_id=metric_id,
        family="agenda",
        aggregation_unit="agenda_topic_source_day",
        denominator_id="all_canonical_agenda_topic_source_days",
        window_mode=window_mode,
        as_of=str(root.get("data_as_of") or ""),
        source_artifact="agenda_coverage_history.json",
        previous_start=previous_dates[0],
        previous_end=previous_dates[-1],
        current_start=current_dates[0],
        current_end=current_dates[-1],
        interpretation_boundary_fr=(
            "Composition de la couverture de campagne "
            "classée dans l’agenda suivi ; ne mesure pas "
            "les priorités déclarées des candidats."
        ),
        interpretation_boundary_en=(
            "Composition of monitored campaign coverage "
            "classified into the campaign agenda; not a "
            "measure of candidates’ stated priorities."
        ),
        rows=tuple(rows),
    )


def rank_movers(
    snapshot: MetricSnapshot,
    *,
    limit: int = 5,
    excluded_entity_ids: Iterable[str] = (),
    require_full: bool = False,
) -> tuple[MetricRow, ...]:
    excluded = set(excluded_entity_ids)

    rows = [
        row
        for row in snapshot.rows
        if row.entity_id not in excluded
    ]

    rows.sort(
        key=lambda row: (
            -abs(row.display_delta),
            -(row.current_evidence + row.previous_evidence),
            row.entity_id,
        )
    )

    if require_full and len(rows) < limit:
        return ()

    return tuple(rows[:limit])


def rank_current_share(
    snapshot: MetricSnapshot,
    *,
    limit: int = 5,
    excluded_entity_ids: Iterable[str] = (),
    require_full: bool = False,
) -> tuple[MetricRow, ...]:
    excluded = set(excluded_entity_ids)

    rows = [
        row
        for row in snapshot.rows
        if row.entity_id not in excluded
    ]

    rows.sort(
        key=lambda row: (
            -row.current_display,
            -row.current_evidence,
            row.entity_id,
        )
    )

    if require_full and len(rows) < limit:
        return ()

    return tuple(rows[:limit])
