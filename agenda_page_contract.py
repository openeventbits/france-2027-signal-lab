"""Canonical publication contract for the bilingual FR27 Agenda family.

Campaign Agenda coverage and candidate-topic associations are deliberately
separate data domains.  This module projects publication state from the
current Campaign Agenda and its topic-oriented coverage history; candidate
history is accepted only as an independently validated association source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from candidate_agenda_history_contract import (
    CandidateAgendaHistoryContractError,
    validate_candidate_agenda_history,
)
from fetch_news_wire import (
    CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS,
    CAMPAIGN_AGENDA_EVOLUTION_DAYS,
    CAMPAIGN_AGENDA_TOPICS,
    POLICY_AGENDA_TOPICS,
)


SCHEMA_VERSION = "1.0"
HISTORY_SCHEMA_VERSION = "1.0"
CURRENT_SOURCE_DAY_MIN = CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
ROLLING_HISTORY_DAYS = CAMPAIGN_AGENDA_EVOLUTION_DAYS


class AgendaPageContractError(ValueError):
    """Raised when Agenda publication data cannot fail closed safely."""


@dataclass(frozen=True)
class AgendaDefinition:
    topic_id: str
    label_fr: str
    slug_fr: str
    label_en: str
    slug_en: str

    @property
    def routes(self) -> dict[str, str]:
        return {
            "fr": f"/agenda/{self.slug_fr}/",
            "en": f"/en/agenda/{self.slug_en}/",
            "history_fr": f"/agenda/historique/{self.slug_fr}/",
            "history_en": f"/en/agenda/history/{self.slug_en}/",
        }


AGENDA_DEFINITIONS = (
    AgendaDefinition(
        "legal_eligibility",
        "Affaires judiciaires et éligibilité",
        "affaires-judiciaires-eligibilite",
        "Legal cases & eligibility",
        "legal-cases-eligibility",
    ),
    AgendaDefinition(
        "selection_strategy",
        "Primaires et stratégies partisanes",
        "primaires-strategies-partisanes",
        "Primaries & party strategy",
        "primaries-party-strategy",
    ),
    AgendaDefinition(
        "candidacies_endorsements",
        "Candidatures et soutiens",
        "candidatures-soutiens",
        "Candidacies & endorsements",
        "candidacies-endorsements",
    ),
    AgendaDefinition(
        "rules_calendar",
        "Règles, calendrier et organisation de la campagne",
        "regles-calendrier-organisation-campagne",
        "Rules, calendar & campaign mechanics",
        "rules-calendar-campaign-mechanics",
    ),
    AgendaDefinition(
        "positioning_integrity",
        "Positionnement et image politique",
        "positionnement-image-politique",
        "Positioning & political image",
        "positioning-political-image",
    ),
    AgendaDefinition(
        "polls_race",
        "Sondages et rapports de force",
        "sondages-rapports-de-force",
        "Polling & race narratives",
        "polling-race-narratives",
    ),
)

AGENDA_BY_ID = {definition.topic_id: definition for definition in AGENDA_DEFINITIONS}
CANONICAL_AGENDA_IDS = tuple(definition.topic_id for definition in AGENDA_DEFINITIONS)
POLICY_AGENDA_IDS = frozenset(topic["id"] for topic in POLICY_AGENDA_TOPICS)


def _validate_locked_taxonomy() -> None:
    source = tuple((topic["id"], topic["label"]) for topic in CAMPAIGN_AGENDA_TOPICS)
    locked = tuple(
        (definition.topic_id, definition.label_en)
        for definition in AGENDA_DEFINITIONS
    )
    if locked != source:
        raise AgendaPageContractError(
            "locked Agenda definitions do not match CAMPAIGN_AGENDA_TOPICS"
        )
    if len(AGENDA_BY_ID) != len(AGENDA_DEFINITIONS):
        raise AgendaPageContractError("locked Agenda definitions contain duplicate ids")
    if len({item.slug_fr for item in AGENDA_DEFINITIONS}) != len(AGENDA_DEFINITIONS):
        raise AgendaPageContractError("locked Agenda definitions contain duplicate FR slugs")
    if len({item.slug_en for item in AGENDA_DEFINITIONS}) != len(AGENDA_DEFINITIONS):
        raise AgendaPageContractError("locked Agenda definitions contain duplicate EN slugs")
    if set(CANONICAL_AGENDA_IDS) & POLICY_AGENDA_IDS:
        raise AgendaPageContractError("Agenda and Policy Agenda ids overlap")


_validate_locked_taxonomy()


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgendaPageContractError(f"{field} must be an object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise AgendaPageContractError(f"{field} must be an array")
    return value


def _count(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise AgendaPageContractError(f"{field} must be a non-negative integer")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgendaPageContractError(f"{field} must be a number")
    return float(value)


def _date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise AgendaPageContractError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise AgendaPageContractError(f"{field} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise AgendaPageContractError(f"{field} must be a canonical ISO date")
    return parsed


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AgendaPageContractError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AgendaPageContractError(f"{field} must be a timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AgendaPageContractError(f"{field} must be timezone-aware")
    return parsed


def _expected_dates(start: date, end: date) -> list[str]:
    if start > end:
        raise AgendaPageContractError("Agenda history period is empty")
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _topic_index(value: Any, field: str) -> dict[str, dict[str, Any]]:
    rows = _list(value, field)
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"{field}[{index}]")
        topic_id = row.get("id")
        if topic_id not in AGENDA_BY_ID:
            raise AgendaPageContractError(f"{field} contains an unknown taxonomy id")
        if topic_id in result:
            raise AgendaPageContractError(f"{field} contains a duplicate topic")
        if row.get("label") != AGENDA_BY_ID[topic_id].label_en:
            raise AgendaPageContractError(f"{field} contains a non-canonical label")
        result[topic_id] = row
    return result


def validate_agenda_coverage_history(payload: Any) -> dict[str, dict[str, Any]]:
    """Validate persistent single-label Agenda history and return its topic index."""

    payload = _mapping(payload, "agenda coverage history")
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise AgendaPageContractError("Agenda history schema version mismatch")
    data_as_of = _timestamp(payload.get("data_as_of"), "history.data_as_of")

    period = _mapping(payload.get("period"), "history.period")
    start = _date(period.get("start_date"), "history.period.start_date")
    end = _date(period.get("end_date"), "history.period.end_date")
    dates = _expected_dates(start, end)
    if period.get("days") != len(dates):
        raise AgendaPageContractError("Agenda history day count mismatch")
    if period.get("day_boundary") != "UTC" or period.get("current_utc_day_excluded") is not True:
        raise AgendaPageContractError("Agenda history complete-day contract is invalid")
    if end >= data_as_of.date():
        raise AgendaPageContractError("Agenda history includes the current partial UTC day")

    reconstruction = _mapping(payload.get("reconstruction"), "history.reconstruction")
    if reconstruction.get("classification_source") != (
        "retained news_wire.json campaign_agenda.evolution snapshots"
    ):
        raise AgendaPageContractError(
            "Agenda history must use retained published Campaign Agenda classifications"
        )
    if reconstruction.get("prohibited_proxy") != (
        "candidate_agenda_history.json is not used as media-volume history"
    ):
        raise AgendaPageContractError("Agenda history prohibited-proxy contract is invalid")

    denominator = _mapping(payload.get("denominator"), "history.denominator")
    if denominator.get("single_label") is not True:
        raise AgendaPageContractError("Agenda history must use a single-label denominator")

    daily_rows = _list(payload.get("daily"), "history.daily")
    if [row.get("date") if isinstance(row, dict) else None for row in daily_rows] != dates:
        raise AgendaPageContractError("Agenda history dates are not contiguous")
    day_index: dict[str, tuple[int, int]] = {}
    for row in daily_rows:
        row = _mapping(row, "history daily point")
        day = row["date"]
        items = _count(
            row.get("total_classified_agenda_items"),
            f"history.daily.{day}.total_classified_agenda_items",
        )
        source_days = _count(
            row.get("total_agenda_topic_source_days"),
            f"history.daily.{day}.total_agenda_topic_source_days",
        )
        _timestamp(row.get("source_snapshot_at"), f"history.daily.{day}.source_snapshot_at")
        day_index[day] = (items, source_days)

    topics = _list(payload.get("topics"), "history.topics")
    if [topic.get("id") if isinstance(topic, dict) else None for topic in topics] != list(
        CANONICAL_AGENDA_IDS
    ):
        raise AgendaPageContractError(
            "Agenda history topics must contain every canonical topic in source order"
        )

    topic_index: dict[str, dict[str, Any]] = {}
    summed_items = {day: 0 for day in dates}
    summed_source_days = {day: 0 for day in dates}
    for definition, raw_topic in zip(AGENDA_DEFINITIONS, topics):
        topic = _mapping(raw_topic, f"history topic {definition.topic_id}")
        topic_id = topic.get("id")
        if topic_id in topic_index:
            raise AgendaPageContractError("Agenda history contains a duplicate topic")
        if topic.get("labels") != {
            "fr": definition.label_fr,
            "en": definition.label_en,
        }:
            raise AgendaPageContractError(f"{topic_id} history labels mismatch")
        points = _list(topic.get("daily"), f"{topic_id}.daily")
        if [point.get("date") if isinstance(point, dict) else None for point in points] != dates:
            raise AgendaPageContractError(f"{topic_id} history dates are not contiguous")

        total_items = 0
        total_source_days = 0
        observed: list[dict[str, Any]] = []
        for point in points:
            point = _mapping(point, f"{topic_id} daily point")
            day = point["date"]
            item_count = _count(point.get("item_count"), f"{topic_id}.{day}.item_count")
            source_day_count = _count(
                point.get("source_day_count"), f"{topic_id}.{day}.source_day_count"
            )
            if source_day_count > item_count:
                raise AgendaPageContractError(f"{topic_id}.{day} source days exceed items")
            day_items, day_source_days = day_index[day]
            if point.get("total_classified_agenda_items") != day_items or point.get(
                "total_agenda_topic_source_days"
            ) != day_source_days:
                raise AgendaPageContractError(f"{topic_id}.{day} denominator mismatch")
            expected_item_share = item_count / day_items if day_items else 0.0
            expected_source_share = (
                source_day_count / day_source_days if day_source_days else 0.0
            )
            if _number(
                point.get("topic_item_share"), f"{topic_id}.{day}.item share"
            ) != expected_item_share:
                raise AgendaPageContractError(f"{topic_id}.{day} item share mismatch")
            if _number(
                point.get("topic_source_day_share"), f"{topic_id}.{day}.source-day share"
            ) != expected_source_share:
                raise AgendaPageContractError(f"{topic_id}.{day} source-day share mismatch")
            total_items += item_count
            total_source_days += source_day_count
            summed_items[day] += item_count
            summed_source_days[day] += source_day_count
            if item_count:
                observed.append(point)

        if (
            topic.get("total_items") != total_items
            or topic.get("total_source_days") != total_source_days
        ):
            raise AgendaPageContractError(f"{topic_id} history totals mismatch")
        if topic.get("active_days") != len(observed):
            raise AgendaPageContractError(f"{topic_id} active-day total mismatch")
        if topic.get("first_observation") != (observed[0]["date"] if observed else None):
            raise AgendaPageContractError(f"{topic_id} first observation mismatch")
        if topic.get("last_observation") != (observed[-1]["date"] if observed else None):
            raise AgendaPageContractError(f"{topic_id} last observation mismatch")

        peak = min(
            points,
            key=lambda point: (
                -point["source_day_count"],
                -point["item_count"],
                point["date"],
            ),
        )
        if topic.get("peak_day") != {
            "date": peak["date"],
            "item_count": peak["item_count"],
            "source_day_count": peak["source_day_count"],
        }:
            raise AgendaPageContractError(f"{topic_id} peak-day mismatch")

        rolling = [
            sum(
                point["source_day_count"]
                for point in points[index - ROLLING_HISTORY_DAYS + 1 : index + 1]
            )
            for index in range(ROLLING_HISTORY_DAYS - 1, len(points))
        ]
        rolling_max = max(rolling, default=0)
        historical = rolling_max >= CURRENT_SOURCE_DAY_MIN
        if topic.get("maximum_rolling_30d_source_days") != rolling_max:
            raise AgendaPageContractError(f"{topic_id} rolling maximum mismatch")
        if topic.get("historical_qualified") is not historical:
            raise AgendaPageContractError(f"{topic_id} historical qualification mismatch")
        topic_index[topic_id] = topic

    for day in dates:
        if summed_items[day] != day_index[day][0]:
            raise AgendaPageContractError(
                f"Agenda single-label item denominator does not reconcile on {day}"
            )
        if summed_source_days[day] != day_index[day][1]:
            raise AgendaPageContractError(
                f"Agenda source-day denominator does not reconcile on {day}"
            )
    return topic_index


def validate_candidate_history_compatibility(payload: Any) -> None:
    """Validate candidate history without treating associations as coverage."""

    try:
        validate_candidate_agenda_history(payload)
    except CandidateAgendaHistoryContractError as error:
        raise AgendaPageContractError(
            f"candidate Agenda history is incompatible: {error}"
        ) from error
    campaign = payload["taxonomies"]["campaign"]
    actual = tuple((row["id"], row["label"]) for row in campaign)
    expected = tuple((item.topic_id, item.label_en) for item in AGENDA_DEFINITIONS)
    if actual != expected:
        raise AgendaPageContractError(
            "candidate Agenda history campaign taxonomy does not match the page contract"
        )


def _previously_public_ids(previous_manifest: Any) -> set[str]:
    if previous_manifest is None:
        return set()
    manifest = _mapping(previous_manifest, "previous Agenda manifest")
    pages = _list(manifest.get("pages"), "previous Agenda manifest.pages")
    result: set[str] = set()
    for raw in pages:
        page = _mapping(raw, "previous Agenda manifest page")
        topic_id = page.get("topic_id")
        if topic_id not in AGENDA_BY_ID:
            raise AgendaPageContractError(
                "previous Agenda manifest contains an unknown taxonomy id"
            )
        if topic_id in result:
            raise AgendaPageContractError("previous Agenda manifest contains a duplicate topic")
        result.add(topic_id)
    return result


def _current_projection(
    news_wire: Any,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    news = _mapping(news_wire, "news_wire")
    agenda = _mapping(news.get("campaign_agenda"), "news_wire.campaign_agenda")
    if agenda.get("display_min_source_days") != CURRENT_SOURCE_DAY_MIN:
        raise AgendaPageContractError("Campaign Agenda display threshold mismatch")
    base = _topic_index(agenda.get("topics"), "campaign_agenda.topics")
    for topic_id, topic in base.items():
        source_days = _count(topic.get("source_day_count"), f"{topic_id}.source_day_count")
        _count(topic.get("item_count"), f"{topic_id}.item_count")
        _count(topic.get("publisher_count"), f"{topic_id}.publisher_count")
        expected = source_days >= CURRENT_SOURCE_DAY_MIN
        if topic.get("display_eligible") is not expected:
            raise AgendaPageContractError(f"{topic_id} display eligibility mismatch")

    evolution = _mapping(agenda.get("evolution"), "campaign_agenda.evolution")
    evolution_topics = _topic_index(evolution.get("topics"), "campaign_agenda.evolution.topics")
    return base, evolution_topics, evolution


def project_agenda_pages(
    news_wire: Any,
    coverage_history: Any,
    *,
    previous_manifest: Any = None,
    candidate_history: Any = None,
) -> dict[str, Any]:
    """Project canonical Agenda topics and lifecycle without rendering pages."""

    base, evolution_topics, evolution = _current_projection(news_wire)
    history_topics = validate_agenda_coverage_history(coverage_history)
    if candidate_history is not None:
        validate_candidate_history_compatibility(candidate_history)
    previously_public = _previously_public_ids(previous_manifest)

    topics = []
    for definition in AGENDA_DEFINITIONS:
        topic_id = definition.topic_id
        base_topic = base.get(topic_id)
        evolution_topic = evolution_topics.get(topic_id)
        current_qualified = bool(
            base_topic is not None and base_topic["display_eligible"]
        )
        historical_qualified = bool(history_topics[topic_id]["historical_qualified"])
        was_previously_public = topic_id in previously_public
        retained = (
            was_previously_public
            and not current_qualified
            and not historical_qualified
        )
        if current_qualified:
            lifecycle = "current"
        elif historical_qualified:
            lifecycle = "historical"
        elif retained:
            lifecycle = "dormant"
        else:
            lifecycle = "unpublished"
        public = current_qualified or historical_qualified or was_previously_public
        topics.append(
            {
                "topic_id": topic_id,
                "labels": {"fr": definition.label_fr, "en": definition.label_en},
                "slugs": {"fr": definition.slug_fr, "en": definition.slug_en},
                "routes": definition.routes,
                "public": public,
                "lifecycle": lifecycle,
                "qualification": {
                    "current": current_qualified,
                    "historical": historical_qualified,
                    "retained_previously_public": retained,
                },
                # These remain separate because their windows and roles differ.
                "current_base_projection": base_topic,
                "current_evolution_projection": evolution_topic,
                "coverage_history": history_topics[topic_id],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": news_wire.get("generated_at"),
        "source": {
            "current": "news_wire.json:campaign_agenda",
            "history": "agenda_coverage_history.json",
            "candidate_associations": (
                "candidate_agenda_history.json" if candidate_history is not None else None
            ),
        },
        "current_contract": {
            "minimum_source_days": CURRENT_SOURCE_DAY_MIN,
            "qualification_source": "campaign_agenda.topics.display_eligible",
        },
        "evolution_period": {
            key: evolution.get(key)
            for key in (
                "period_days",
                "period_start",
                "period_end",
                "period_end_partial",
                "comparison_days",
                "latest_start",
                "latest_end",
                "previous_start",
                "previous_end",
            )
        },
        "topics": topics,
    }


def agenda_manifest_payload(projection: Any) -> dict[str, Any]:
    """Return the future page-family manifest payload; this function does not write it."""

    projection = _mapping(projection, "Agenda projection")
    public_topics = [topic for topic in projection["topics"] if topic["public"]]
    pages = []
    for topic in public_topics:
        pages.append(
            {
                "topic_id": topic["topic_id"],
                "labels": topic["labels"],
                "slugs": topic["slugs"],
                "lifecycle": topic["lifecycle"],
                "current_qualified": topic["qualification"]["current"],
                "historical_qualified": topic["qualification"]["historical"],
                "retained_previously_public": topic["qualification"][
                    "retained_previously_public"
                ],
                "page_path_fr": topic["routes"]["fr"],
                "page_path_en": topic["routes"]["en"],
                "history_page_path_fr": topic["routes"]["history_fr"],
                "history_page_path_en": topic["routes"]["history_en"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": projection.get("generated_at"),
        "source": projection.get("source"),
        "public_topic_count": len(pages),
        "page_count": 4 + 4 * len(pages),
        "hubs": {"fr": "/agenda/", "en": "/en/agenda/"},
        "history_hubs": {"fr": "/agenda/historique/", "en": "/en/agenda/history/"},
        "pages": pages,
    }


def validate_agenda_manifest(payload: Any) -> None:
    """Validate the future Agenda manifest schema and canonical routes."""

    manifest = _mapping(payload, "Agenda manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise AgendaPageContractError("Agenda manifest schema version mismatch")
    pages = _list(manifest.get("pages"), "Agenda manifest.pages")
    if manifest.get("public_topic_count") != len(pages):
        raise AgendaPageContractError("Agenda manifest public topic count mismatch")
    if manifest.get("page_count") != 4 + 4 * len(pages):
        raise AgendaPageContractError("Agenda manifest page count mismatch")
    if manifest.get("hubs") != {"fr": "/agenda/", "en": "/en/agenda/"}:
        raise AgendaPageContractError("Agenda manifest hubs mismatch")
    if manifest.get("history_hubs") != {
        "fr": "/agenda/historique/",
        "en": "/en/agenda/history/",
    }:
        raise AgendaPageContractError("Agenda manifest history hubs mismatch")

    seen: set[str] = set()
    for raw in pages:
        page = _mapping(raw, "Agenda manifest page")
        topic_id = page.get("topic_id")
        if topic_id not in AGENDA_BY_ID:
            raise AgendaPageContractError("Agenda manifest contains an unknown topic")
        if topic_id in seen:
            raise AgendaPageContractError("Agenda manifest contains a duplicate topic")
        seen.add(topic_id)
        definition = AGENDA_BY_ID[topic_id]
        if page.get("labels") != {"fr": definition.label_fr, "en": definition.label_en}:
            raise AgendaPageContractError("Agenda manifest labels mismatch")
        if page.get("slugs") != {"fr": definition.slug_fr, "en": definition.slug_en}:
            raise AgendaPageContractError("Agenda manifest slugs mismatch")
        routes = definition.routes
        for field, route_key in (
            ("page_path_fr", "fr"),
            ("page_path_en", "en"),
            ("history_page_path_fr", "history_fr"),
            ("history_page_path_en", "history_en"),
        ):
            if page.get(field) != routes[route_key]:
                raise AgendaPageContractError(f"Agenda manifest {field} mismatch")
        if page.get("lifecycle") not in {"current", "historical", "dormant"}:
            raise AgendaPageContractError("Agenda manifest lifecycle is invalid")
        current = page.get("current_qualified")
        historical = page.get("historical_qualified")
        retained = page.get("retained_previously_public")
        if not all(type(value) is bool for value in (current, historical, retained)):
            raise AgendaPageContractError("Agenda manifest qualification flags are invalid")
        expected_lifecycle = (
            "current" if current else "historical" if historical else "dormant"
        )
        if page["lifecycle"] != expected_lifecycle or not (current or historical or retained):
            raise AgendaPageContractError("Agenda manifest lifecycle does not reconcile")
