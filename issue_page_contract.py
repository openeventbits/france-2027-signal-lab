"""Canonical publication and projection contract for FR27 issue pages.

The public issue family is derived from the existing policy-agenda projection
and candidate agenda history.  Coverage, current candidate association and
historical candidate association deliberately remain separate data domains.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
import math
import unicodedata


SCHEMA_VERSION = "1.0"
PUBLIC_ORIGIN = "https://france2027.app"
CURRENT_ITEM_MIN = 3
CURRENT_SOURCE_DAY_MIN = 2
CURRENT_PUBLISHER_MIN = 2
HISTORICAL_ASSOCIATION_MIN = 8
HISTORICAL_DAY_MIN = 3
HISTORICAL_CANDIDATE_MIN = 2


class IssuePageContractError(ValueError):
    """Raised when an issue projection cannot fail closed safely."""


@dataclass(frozen=True)
class IssueDefinition:
    issue_id: str
    slug_fr: str
    slug_en: str
    label_fr: str
    label_en: str
    subtopics: tuple[tuple[str, str, str], ...]

    @property
    def routes(self) -> dict[str, str]:
        return {
            "fr": f"/enjeux/{self.slug_fr}/",
            "en": f"/en/issues/{self.slug_en}/",
        }


ISSUE_DEFINITIONS = (
    IssueDefinition(
        "economy_public_finances",
        "economie-finances-publiques",
        "economy-public-finances",
        "Économie & finances publiques",
        "Economy & public finances",
        (
            ("budget", "Budget", "Budget"),
            ("taxation", "Fiscalité", "Taxation"),
            ("growth_industry", "Croissance & industrie", "Growth & industry"),
            ("deficit_debt", "Déficit & dette", "Deficit & debt"),
        ),
    ),
    IssueDefinition(
        "work_purchasing_power_pensions",
        "travail-pouvoir-achat-retraites",
        "work-purchasing-power-pensions",
        "Travail, pouvoir d’achat & retraites",
        "Work, purchasing power & pensions",
        (
            ("pensions", "Retraites", "Pensions"),
            ("wages", "Salaires", "Wages"),
            ("purchasing_power", "Pouvoir d’achat", "Purchasing power"),
            ("employment", "Emploi", "Employment"),
            ("social_contributions", "Cotisations sociales", "Social contributions"),
        ),
    ),
    IssueDefinition(
        "immigration_identity_secularism",
        "immigration-identite-laicite",
        "immigration-identity-secularism",
        "Immigration, identité & laïcité",
        "Immigration, identity & secularism",
        (
            ("immigration", "Immigration", "Immigration"),
            (
                "nationality_integration",
                "Nationalité & intégration",
                "Nationality & integration",
            ),
            (
                "identity_secularism",
                "Identité & laïcité",
                "Identity & secularism",
            ),
            ("asylum", "Asile", "Asylum"),
        ),
    ),
    IssueDefinition(
        "security_justice",
        "securite-justice",
        "security-justice",
        "Sécurité & justice",
        "Security & justice",
        (
            ("security_policing", "Sécurité & police", "Security & policing"),
            ("crime", "Criminalité", "Crime"),
            (
                "prisons_sentencing",
                "Prisons & peines",
                "Prisons & sentencing",
            ),
            ("terrorism", "Terrorisme", "Terrorism"),
            ("justice_system", "Système judiciaire", "Justice system"),
        ),
    ),
    IssueDefinition(
        "health_education_public_services",
        "sante-education-services-publics",
        "health-education-public-services",
        "Santé, éducation & services publics",
        "Health, education & public services",
        (
            ("health", "Santé", "Health"),
            ("education", "Éducation", "Education"),
            ("public_services", "Services publics", "Public services"),
        ),
    ),
    IssueDefinition(
        "climate_energy_agriculture",
        "climat-energie-agriculture",
        "climate-energy-agriculture",
        "Climat, énergie & agriculture",
        "Climate, energy & agriculture",
        (
            (
                "climate_environment",
                "Climat & environnement",
                "Climate & environment",
            ),
            ("energy", "Énergie", "Energy"),
            ("agriculture", "Agriculture", "Agriculture"),
            ("transport", "Transports", "Transport"),
        ),
    ),
    IssueDefinition(
        "europe_defence_foreign_affairs",
        "europe-defense-affaires-etrangeres",
        "europe-defence-foreign-affairs",
        "Europe, défense & affaires étrangères",
        "Europe, defence & foreign affairs",
        (
            ("europe", "Europe", "Europe"),
            ("defence", "Défense", "Defence"),
            ("foreign_policy", "Politique étrangère", "Foreign policy"),
            ("ukraine_russia", "Ukraine & Russie", "Ukraine & Russia"),
            ("middle_east", "Moyen-Orient", "Middle East"),
        ),
    ),
    IssueDefinition(
        "institutions_democracy_territories",
        "institutions-democratie-territoires",
        "institutions-democracy-territories",
        "Institutions, démocratie & territoires",
        "Institutions, democracy & territories",
        (
            ("constitution", "Constitution", "Constitution"),
            ("democracy", "Démocratie", "Democracy"),
            ("parliament", "Parlement", "Parliament"),
            (
                "decentralisation",
                "Décentralisation & territoires",
                "Decentralisation & territories",
            ),
            ("electoral_reform", "Réforme électorale", "Electoral reform"),
        ),
    ),
)

ISSUE_BY_ID = {definition.issue_id: definition for definition in ISSUE_DEFINITIONS}
CANONICAL_ISSUE_IDS = tuple(definition.issue_id for definition in ISSUE_DEFINITIONS)


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IssuePageContractError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise IssuePageContractError(f"{field} must be an array")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise IssuePageContractError(f"{field} must be a non-negative integer")
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IssuePageContractError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise IssuePageContractError(f"{field} must be a finite number")
    return number


def _incidence(value: Any, field: str) -> float:
    number = _finite_number(value, field)
    if number < 0 or number > 1:
        raise IssuePageContractError(f"{field} must be between 0 and 1")
    return number


def _normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).casefold()


def _validate_iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise IssuePageContractError(f"{field} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise IssuePageContractError(f"{field} must be an ISO date") from error
    return value


@dataclass(frozen=True)
class IssuePeriodRow:
    issue_id: str
    numerator: int
    denominator: int
    raw_share: float


@dataclass(frozen=True)
class IssuePeriodMetric:
    start_date: str
    end_date: str
    denominator: int
    rows: tuple[IssuePeriodRow, ...]
    aggregation_unit: str = "issue_source_day"
    denominator_id: str = "accepted_relevant_news_source_days"


def build_issue_period_metric(
    topics: Any,
    *,
    start_date: str,
    end_date: str,
    daily_denominators: Any,
    allow_empty_denominator: bool = False,
) -> IssuePeriodMetric:
    """Canonical multilabel incidence: Issue publisher-days / accepted publisher-days.

    Inputs use Policy Agenda evolution's source_day_count vocabulary. Each
    publisher counts once per UTC date within each Issue and within the corpus.
    Missing observations are errors, not zero evidence. Only the page's existing
    empty-corpus presentation opts into a zero share; publication fails closed.
    """
    start = date.fromisoformat(_validate_iso_date(start_date, "incidence start"))
    end = date.fromisoformat(_validate_iso_date(end_date, "incidence end"))
    if start > end or start.isoformat() != start_date or end.isoformat() != end_date:
        raise IssuePageContractError("incidence period is invalid")
    expected = {
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    }

    def daily_counts(values: Any, label: str) -> dict[str, int]:
        result = {}
        for point in _require_list(values, label):
            point = _require_mapping(point, label + " observation")
            day = _validate_iso_date(point.get("date"), label + " date")
            if date.fromisoformat(day).isoformat() != day or day in result:
                raise IssuePageContractError(label + " dates must be canonical and unique")
            result[day] = _nonnegative_integer(
                point.get("source_day_count"), label + " source_day_count"
            )
        if not expected.issubset(result):
            raise IssuePageContractError(label + " is missing required period dates")
        return result

    accepted = daily_counts(daily_denominators, "accepted daily incidence")
    denominator = sum(accepted[day] for day in expected)
    if denominator == 0 and not allow_empty_denominator:
        raise IssuePageContractError("Issue incidence denominator must be positive")
    topic_index = {}
    for topic in _require_list(topics, "incidence topics"):
        topic = _require_mapping(topic, "incidence topic")
        issue_id = topic.get("id")
        if not isinstance(issue_id, str) or issue_id in topic_index:
            raise IssuePageContractError("incidence taxonomy contains an invalid or duplicate ID")
        topic_index[issue_id] = topic
    if set(topic_index) != set(CANONICAL_ISSUE_IDS):
        raise IssuePageContractError("incidence taxonomy must contain all canonical Issues")

    rows = []
    for definition in ISSUE_DEFINITIONS:
        issue_id = definition.issue_id
        counts = daily_counts(topic_index[issue_id].get("daily_activity"), issue_id)
        if any(counts[day] > accepted[day] for day in expected):
            raise IssuePageContractError(f"{issue_id} source-days exceed accepted source-days")
        numerator = sum(counts[day] for day in expected)
        rows.append(IssuePeriodRow(
            issue_id=issue_id,
            numerator=numerator,
            denominator=denominator,
            raw_share=numerator / denominator if denominator else 0.0,
        ))
    return IssuePeriodMetric(start_date, end_date, denominator, tuple(rows))


def build_issue_history_period_metric(
    payload: Any, *, start_date: str, end_date: str,
) -> IssuePeriodMetric:
    """Adapt retained history to page incidence without using its article shares.

    History publisher_count is the page's daily source_day_count, as retained
    by build_issue_coverage_history._snapshot_days. Its stored article-share
    fields remain legacy historical data, not the incidence authority.
    """
    validate_issue_coverage_history(payload)
    try:
        as_of = datetime.fromisoformat(payload.get("data_as_of", "").replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as error:
        raise IssuePageContractError("Issue history data_as_of is invalid") from error
    if as_of.tzinfo is None or payload["period"]["end_date"] != (
        as_of.astimezone(timezone.utc).date() - timedelta(days=1)
    ).isoformat():
        raise IssuePageContractError("Issue history must end on the latest complete UTC day")
    return build_issue_period_metric(
        [
            {"id": issue["id"], "daily_activity": [
                {"date": point["date"], "source_day_count": point["publisher_count"]}
                for point in issue["daily"]
            ]}
            for issue in payload["issues"]
        ],
        start_date=start_date,
        end_date=end_date,
        daily_denominators=[
            {"date": point["date"], "source_day_count": point["publisher_count"]}
            for point in payload["corpus"]["daily"]
        ],
    )


def validate_issue_coverage_history(payload: Any) -> dict[str, dict[str, Any]]:
    """Validate persistent article-derived history and return its issue index."""

    payload = _require_mapping(payload, "issue coverage history")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise IssuePageContractError("issue coverage history schema version mismatch")
    period = _require_mapping(payload.get("period"), "issue coverage history.period")
    start_text = _validate_iso_date(period.get("start_date"), "history start_date")
    end_text = _validate_iso_date(period.get("end_date"), "history end_date")
    start = date.fromisoformat(start_text)
    end = date.fromisoformat(end_text)
    expected_days = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]
    if start > end or period.get("days") != len(expected_days):
        raise IssuePageContractError("issue coverage history period is invalid")
    if period.get("day_boundary") != "UTC" or period.get("current_utc_day_excluded") is not True:
        raise IssuePageContractError("issue coverage history completeness contract is invalid")

    denominator = _require_mapping(payload.get("denominator"), "history denominator")
    if denominator.get("multilabel") is not True or not denominator.get("formula"):
        raise IssuePageContractError("issue coverage history denominator is invalid")
    corpus = _require_mapping(payload.get("corpus"), "history corpus")
    corpus_daily = _require_list(corpus.get("daily"), "history corpus.daily")
    if [item.get("date") for item in corpus_daily if isinstance(item, dict)] != expected_days:
        raise IssuePageContractError("issue coverage history corpus dates are not contiguous")
    corpus_by_day: dict[str, dict[str, Any]] = {}
    for point in corpus_daily:
        point = _require_mapping(point, "history corpus point")
        day = _validate_iso_date(point.get("date"), "history corpus date")
        _nonnegative_integer(point.get("item_count"), "history corpus item_count")
        _nonnegative_integer(point.get("publisher_count"), "history corpus publisher_count")
        if not isinstance(point.get("source_snapshot_at"), str):
            raise IssuePageContractError("history corpus source snapshot is invalid")
        corpus_by_day[day] = point
    if corpus.get("total_item_count") != sum(point["item_count"] for point in corpus_daily):
        raise IssuePageContractError("issue coverage history corpus total mismatch")
    if corpus.get("publisher_day_count") != sum(
        point["publisher_count"] for point in corpus_daily
    ):
        raise IssuePageContractError("issue coverage history publisher-day total mismatch")

    history_issues = _require_list(payload.get("issues"), "history issues")
    issue_by_id = {
        item.get("id"): _require_mapping(item, "history issue")
        for item in history_issues
        if isinstance(item, dict)
    }
    if set(issue_by_id) != set(CANONICAL_ISSUE_IDS):
        raise IssuePageContractError("issue coverage history taxonomy mismatch")
    for issue_id in CANONICAL_ISSUE_IDS:
        issue = issue_by_id[issue_id]
        daily = _require_list(issue.get("daily"), f"{issue_id} history daily")
        if [item.get("date") for item in daily if isinstance(item, dict)] != expected_days:
            raise IssuePageContractError(f"{issue_id} history dates are not contiguous")
        observed = []
        for point in daily:
            point = _require_mapping(point, f"{issue_id} history point")
            day = _validate_iso_date(point.get("date"), f"{issue_id} history date")
            item_count = _nonnegative_integer(
                point.get("item_count"), f"{issue_id} history item_count"
            )
            publisher_count = _nonnegative_integer(
                point.get("publisher_count"), f"{issue_id} history publisher_count"
            )
            if publisher_count > item_count:
                raise IssuePageContractError(f"{issue_id} history publisher count is invalid")
            corpus_point = corpus_by_day[day]
            if (
                point.get("corpus_item_count") != corpus_point["item_count"]
                or point.get("corpus_publisher_count") != corpus_point["publisher_count"]
            ):
                raise IssuePageContractError(f"{issue_id} history denominator mismatch")
            expected_share = (
                round(item_count / corpus_point["item_count"] * 100, 4)
                if corpus_point["item_count"]
                else 0.0
            )
            if point.get("corpus_share_percent") != expected_share:
                raise IssuePageContractError(f"{issue_id} history share mismatch")
            if item_count:
                observed.append(point)
        if issue.get("total_item_count") != sum(point["item_count"] for point in daily):
            raise IssuePageContractError(f"{issue_id} history total mismatch")
        if issue.get("publisher_day_count") != sum(
            point["publisher_count"] for point in daily
        ):
            raise IssuePageContractError(f"{issue_id} history publisher-day mismatch")
        if issue.get("active_day_count") != len(observed):
            raise IssuePageContractError(f"{issue_id} history active-day mismatch")
        first = observed[0]["date"] if observed else None
        last = observed[-1]["date"] if observed else None
        if issue.get("first_observation") != first or issue.get("last_observation") != last:
            raise IssuePageContractError(f"{issue_id} history observation range mismatch")
    return issue_by_id


def _candidate_route_map(
    candidate_routes: Iterable[dict[str, Any]] | None,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for candidate in candidate_routes or ():
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("candidate_name")
        routes = candidate.get("routes")
        if (
            isinstance(name, str)
            and isinstance(routes, dict)
            and isinstance(routes.get("fr"), str)
            and isinstance(routes.get("en"), str)
        ):
            result[_normalized_name(name)] = {
                "fr": routes["fr"],
                "en": routes["en"],
            }
    return result


def _source_evidence(item: Any) -> dict[str, Any]:
    item = _require_mapping(item, "policy_agenda.supporting_item")
    required = ("id", "publisher", "published_at", "headline", "url")
    for field in required:
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise IssuePageContractError(
                f"policy_agenda supporting item lacks {field}"
            )
    return {
        "id": item["id"],
        "publisher": item["publisher"],
        "published_at": item["published_at"],
        "date": item["published_at"][:10],
        "headline": item["headline"],
        "url": item["url"],
        "candidates": [
            name
            for name in item.get("candidates", [])
            if isinstance(name, str) and name.strip()
        ],
        "subtopics": [
            subtopic
            for subtopic in item.get("subtopics", [])
            if isinstance(subtopic, str) and subtopic
        ],
    }


def _history_by_issue(
    agenda_history: dict[str, Any],
    route_map: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    candidates = _require_list(
        agenda_history.get("candidates"),
        "candidate_agenda_history.candidates",
    )

    for issue_id in CANONICAL_ISSUE_IDS:
        daily_totals: Counter[str] = Counter()
        associations: list[dict[str, Any]] = []

        for candidate in candidates:
            candidate = _require_mapping(candidate, "candidate history record")
            name = candidate.get("candidate_name")
            candidate_id = candidate.get("candidate_id")
            if not isinstance(name, str) or not isinstance(candidate_id, str):
                raise IssuePageContractError("candidate history identity is invalid")

            per_day: list[dict[str, Any]] = []
            for observation in _require_list(
                candidate.get("daily_series"),
                f"candidate history {candidate_id}.daily_series",
            ):
                observation = _require_mapping(observation, "history observation")
                observed_date = _validate_iso_date(
                    observation.get("date"), "history observation date"
                )
                policy_counts = _require_mapping(
                    observation.get("policy_counts"), "history policy_counts"
                )
                if set(policy_counts) != set(CANONICAL_ISSUE_IDS):
                    raise IssuePageContractError(
                        "candidate history policy taxonomy does not match the "
                        "canonical issue taxonomy"
                    )
                count = _nonnegative_integer(
                    policy_counts[issue_id],
                    f"history {candidate_id}.{observed_date}.{issue_id}",
                )
                if count:
                    daily_totals[observed_date] += count
                    per_day.append({"date": observed_date, "count": count})

            if per_day:
                routes = route_map.get(_normalized_name(name))
                associations.append(
                    {
                        "candidate_id": candidate_id,
                        "candidate_name": name,
                        "association_count": sum(item["count"] for item in per_day),
                        "observed_days": len(per_day),
                        "first_observation": per_day[0]["date"],
                        "last_observation": per_day[-1]["date"],
                        "daily": per_day,
                        "routes": routes,
                    }
                )

        associations.sort(
            key=lambda item: (
                -item["association_count"],
                _normalized_name(item["candidate_name"]),
                item["candidate_id"],
            )
        )
        ordered_daily = [
            {"date": observed_date, "count": daily_totals[observed_date]}
            for observed_date in sorted(daily_totals)
        ]
        result[issue_id] = {
            "association_count": sum(daily_totals.values()),
            "candidate_count": len(associations),
            "observed_days": len(daily_totals),
            "first_observation": (
                ordered_daily[0]["date"] if ordered_daily else None
            ),
            "last_observation": (
                ordered_daily[-1]["date"] if ordered_daily else None
            ),
            "daily": ordered_daily,
            "candidates": associations,
        }

    return result


def _previous_public_ids(previous_manifest: Any) -> set[str]:
    if previous_manifest is None:
        return set()
    manifest = _require_mapping(previous_manifest, "previous issue manifest")
    pages = _require_list(manifest.get("pages"), "previous issue manifest.pages")
    result: set[str] = set()
    for page in pages:
        page = _require_mapping(page, "previous issue manifest page")
        issue_id = page.get("issue_id")
        if not isinstance(issue_id, str):
            raise IssuePageContractError("previous issue manifest page lacks issue_id")
        if issue_id not in ISSUE_BY_ID:
            raise IssuePageContractError(
                "previous issue manifest contains a non-canonical issue without "
                f"an explicit alias or merge: {issue_id}"
            )
        result.add(issue_id)
    return result


def _subtopics(
    definition: IssueDefinition,
    topic: dict[str, Any],
) -> list[dict[str, Any]]:
    counts = _require_list(topic.get("subtopic_counts"), "issue subtopic_counts")
    order = {
        subtopic_id: index
        for index, (subtopic_id, _fr, _en) in enumerate(definition.subtopics)
    }
    labels = {
        subtopic_id: {"fr": label_fr, "en": label_en}
        for subtopic_id, label_fr, label_en in definition.subtopics
    }
    projected: list[dict[str, Any]] = []
    for item in counts:
        item = _require_mapping(item, "issue subtopic count")
        subtopic_id = item.get("id")
        if subtopic_id not in order:
            raise IssuePageContractError(
                f"unknown subtopic {subtopic_id!r} for {definition.issue_id}"
            )
        count = _nonnegative_integer(item.get("item_count"), "subtopic item_count")
        if count:
            projected.append(
                {
                    "id": subtopic_id,
                    "labels": labels[subtopic_id],
                    "item_count": count,
                    "promotion": {
                        "eligible": False,
                        "route": None,
                        "phase": 1,
                    },
                }
            )
    projected.sort(key=lambda item: (-item["item_count"], order[item["id"]]))
    return projected


def _current_associations(
    topic: dict[str, Any],
    route_map: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    associations: list[dict[str, Any]] = []
    for item in _require_list(topic.get("candidate_counts"), "issue candidate_counts"):
        item = _require_mapping(item, "issue candidate count")
        name = item.get("candidate")
        if not isinstance(name, str) or not name.strip():
            raise IssuePageContractError("current candidate association lacks a name")
        count = _nonnegative_integer(
            item.get("item_count"), "current candidate association item_count"
        )
        associations.append(
            {
                "candidate_name": name,
                "item_count": count,
                "routes": route_map.get(_normalized_name(name)),
            }
        )
    associations.sort(
        key=lambda item: (-item["item_count"], _normalized_name(item["candidate_name"]))
    )
    return associations


def _related_issues(
    issues: list[dict[str, Any]],
) -> None:
    public_ids = {issue["issue_id"] for issue in issues if issue["public"]}
    order = {issue_id: index for index, issue_id in enumerate(CANONICAL_ISSUE_IDS)}
    evidence_by_issue = {
        issue["issue_id"]: {item["id"] for item in issue["evidence"]}
        for issue in issues
    }

    for issue in issues:
        related: list[dict[str, Any]] = []
        own = evidence_by_issue[issue["issue_id"]]
        for other in issues:
            other_id = other["issue_id"]
            if other_id == issue["issue_id"] or other_id not in public_ids:
                continue
            shared = sorted(own & evidence_by_issue[other_id])
            if shared:
                related.append(
                    {
                        "issue_id": other_id,
                        "labels": other["labels"],
                        "routes": other["routes"],
                        "cooccurrence_count": len(shared),
                        "evidence_ids": shared,
                    }
                )
        related.sort(
            key=lambda item: (
                -item["cooccurrence_count"],
                order[item["issue_id"]],
            )
        )
        issue["related_issues"] = related[:4]


def _campaign_agenda_summary(news_wire: dict[str, Any]) -> dict[str, Any]:
    """Project complete-week Campaign Agenda composition without reclassification."""

    agenda = _require_mapping(
        news_wire.get("campaign_agenda"),
        "news_wire.campaign_agenda",
    )
    if agenda.get("method") != "accepted_relevant_news_by_campaign_theme":
        raise IssuePageContractError("campaign_agenda method is invalid")

    evolution = _require_mapping(
        agenda.get("evolution"),
        "campaign_agenda.evolution",
    )
    comparison_days = _nonnegative_integer(
        evolution.get("comparison_days"),
        "campaign_agenda.evolution.comparison_days",
    )
    if comparison_days < 1:
        raise IssuePageContractError("campaign agenda comparison window is empty")

    previous_start = _validate_iso_date(
        evolution.get("previous_start"),
        "campaign agenda previous_start",
    )
    previous_end = _validate_iso_date(
        evolution.get("previous_end"),
        "campaign agenda previous_end",
    )
    latest_start = _validate_iso_date(
        evolution.get("latest_start"),
        "campaign agenda latest_start",
    )
    latest_end = _validate_iso_date(
        evolution.get("latest_end"),
        "campaign agenda latest_end",
    )

    topics = []
    for position, raw_topic in enumerate(
        _require_list(evolution.get("topics"), "campaign_agenda.evolution.topics")
    ):
        topic = _require_mapping(raw_topic, "campaign agenda evolution topic")
        topic_id = topic.get("id")
        label = topic.get("label")
        if not isinstance(topic_id, str) or not topic_id.strip():
            raise IssuePageContractError("campaign agenda topic lacks id")
        if not isinstance(label, str) or not label.strip():
            raise IssuePageContractError("campaign agenda topic lacks label")

        previous_count = 0
        latest_count = 0
        for raw_day in _require_list(
            topic.get("daily_activity"),
            f"campaign agenda {topic_id}.daily_activity",
        ):
            day = _require_mapping(raw_day, "campaign agenda daily activity")
            day_key = _validate_iso_date(
                day.get("date"),
                "campaign agenda daily date",
            )
            item_count = _nonnegative_integer(
                day.get("item_count"),
                "campaign agenda daily item_count",
            )
            if previous_start <= day_key <= previous_end:
                previous_count += item_count
            if latest_start <= day_key <= latest_end:
                latest_count += item_count

        topics.append(
            {
                "id": topic_id,
                "label": label,
                "position": position,
                "previous_item_count": previous_count,
                "latest_item_count": latest_count,
            }
        )

    previous_total = sum(item["previous_item_count"] for item in topics)
    latest_total = sum(item["latest_item_count"] for item in topics)

    for topic in topics:
        topic["previous_share"] = (
            round(topic["previous_item_count"] / previous_total, 6)
            if previous_total
            else 0.0
        )
        topic["latest_share"] = (
            round(topic["latest_item_count"] / latest_total, 6)
            if latest_total
            else 0.0
        )

    return {
        "method": agenda["method"],
        "metric": "classified_campaign_agenda_item_share",
        "comparison_days": comparison_days,
        "previous_start": previous_start,
        "previous_end": previous_end,
        "latest_start": latest_start,
        "latest_end": latest_end,
        "previous_total": previous_total,
        "latest_total": latest_total,
        "topics": topics,
    }


def project_issue_pages(
    news_wire: Any,
    agenda_history: Any,
    *,
    previous_manifest: Any = None,
    candidate_routes: Iterable[dict[str, Any]] | None = None,
    coverage_history: Any = None,
) -> dict[str, Any]:
    """Build the complete deterministic issue-page projection."""

    news_wire = _require_mapping(news_wire, "news_wire")
    agenda_history = _require_mapping(agenda_history, "candidate_agenda_history")
    policy = _require_mapping(news_wire.get("policy_agenda"), "news_wire.policy_agenda")
    topics = _require_list(policy.get("topics"), "policy_agenda.topics")
    evolution = _require_mapping(policy.get("evolution"), "policy_agenda.evolution")
    evolution_topics = _require_list(
        evolution.get("topics"), "policy_agenda.evolution.topics"
    )

    topic_by_id = {
        item.get("id"): _require_mapping(item, "policy agenda topic")
        for item in topics
        if isinstance(item, dict)
    }
    evolution_by_id = {
        item.get("id"): _require_mapping(item, "policy agenda evolution topic")
        for item in evolution_topics
        if isinstance(item, dict)
    }
    expected_ids = set(CANONICAL_ISSUE_IDS)
    if set(topic_by_id) != expected_ids or set(evolution_by_id) != expected_ids:
        raise IssuePageContractError(
            "policy agenda taxonomy does not exactly match the canonical root "
            "issue taxonomy; refusing to remove or invent public URLs"
        )

    history_taxonomies = _require_mapping(
        agenda_history.get("taxonomies"), "candidate_agenda_history.taxonomies"
    )
    history_policy = _require_list(
        history_taxonomies.get("policy"), "candidate_agenda_history.taxonomies.policy"
    )
    history_ids = {
        item.get("id") for item in history_policy if isinstance(item, dict)
    }
    if history_ids != expected_ids:
        raise IssuePageContractError(
            "candidate agenda history taxonomy does not exactly match the "
            "canonical root issue taxonomy"
        )

    period_start = _validate_iso_date(evolution.get("period_start"), "period_start")
    period_end = _validate_iso_date(evolution.get("period_end"), "period_end")
    comparison_days = _nonnegative_integer(
        evolution.get("comparison_days"),
        "policy_agenda.evolution.comparison_days",
    )
    if comparison_days < 1:
        raise IssuePageContractError("policy agenda comparison window is empty")
    previous_start = _validate_iso_date(
        evolution.get("previous_start"),
        "policy agenda previous_start",
    )
    previous_end = _validate_iso_date(
        evolution.get("previous_end"),
        "policy agenda previous_end",
    )
    latest_start = _validate_iso_date(
        evolution.get("latest_start"),
        "policy agenda latest_start",
    )
    latest_end = _validate_iso_date(
        evolution.get("latest_end"),
        "policy agenda latest_end",
    )
    period_start_date = date.fromisoformat(period_start)
    period_end_date = date.fromisoformat(period_end)
    previous_start_date = date.fromisoformat(previous_start)
    previous_end_date = date.fromisoformat(previous_end)
    latest_start_date = date.fromisoformat(latest_start)
    latest_end_date = date.fromisoformat(latest_end)
    if (
        period_start_date > period_end_date
        or (previous_end_date - previous_start_date).days + 1 != comparison_days
        or (latest_end_date - latest_start_date).days + 1 != comparison_days
        or previous_end_date + timedelta(days=1) != latest_start_date
        or previous_start_date < period_start_date
        or latest_end_date != period_end_date - timedelta(days=1)
    ):
        raise IssuePageContractError(
            "policy agenda complete-week comparison windows are inconsistent"
        )

    expected_period_dates = [
        (period_start_date + timedelta(days=offset)).isoformat()
        for offset in range((period_end_date - period_start_date).days + 1)
    ]
    if len(expected_period_dates) != 30:
        raise IssuePageContractError(
            "policy agenda coverage evolution must contain exactly 30 days"
        )
    accepted_daily = _require_list(
        evolution.get("accepted_daily_activity"),
        "policy_agenda.evolution.accepted_daily_activity",
    )
    accepted_by_date: dict[str, int] = {}
    accepted_dates: list[str] = []
    for observation in accepted_daily:
        observation = _require_mapping(
            observation,
            "policy agenda accepted daily observation",
        )
        observation_date = _validate_iso_date(
            observation.get("date"),
            "policy agenda accepted daily date",
        )
        accepted_dates.append(observation_date)
        accepted_by_date[observation_date] = _nonnegative_integer(
            observation.get("source_day_count"),
            "policy agenda accepted daily source_day_count",
        )
    if accepted_dates != expected_period_dates:
        raise IssuePageContractError(
            "policy agenda accepted daily dates do not match its period"
        )

    # Preserve the page's empty-corpus presentation while sharing incidence
    # calculation with social's strict, non-empty publication adapter.
    previous_metric = build_issue_period_metric(
        evolution_topics, start_date=previous_start, end_date=previous_end,
        daily_denominators=accepted_daily, allow_empty_denominator=True,
    )
    latest_metric = build_issue_period_metric(
        evolution_topics, start_date=latest_start, end_date=latest_end,
        daily_denominators=accepted_daily, allow_empty_denominator=True,
    )
    previous_rows = {row.issue_id: row for row in previous_metric.rows}
    latest_rows = {row.issue_id: row for row in latest_metric.rows}
    route_map = _candidate_route_map(candidate_routes)
    history = _history_by_issue(agenda_history, route_map)
    previously_public = _previous_public_ids(previous_manifest)
    issues: list[dict[str, Any]] = []

    for definition in ISSUE_DEFINITIONS:
        issue_id = definition.issue_id
        topic = topic_by_id[issue_id]
        series = evolution_by_id[issue_id]
        daily = _require_list(series.get("daily_activity"), "issue daily_activity")
        evolution_30d = []
        for observation in daily:
            observation = _require_mapping(observation, "issue daily observation")
            observation_date = _validate_iso_date(
                observation.get("date"), "daily date"
            )
            source_day_count = _nonnegative_integer(
                observation.get("source_day_count"), "daily source_day_count"
            )
            accepted_source_day_count = _nonnegative_integer(
                observation.get("accepted_source_day_count"),
                "daily accepted_source_day_count",
            )
            if (
                accepted_by_date.get(observation_date)
                != accepted_source_day_count
                or source_day_count > accepted_source_day_count
            ):
                raise IssuePageContractError(
                    f"{issue_id} daily incidence denominator is inconsistent"
                )
            evolution_30d.append(
                {
                    "date": observation_date,
                    "item_count": _nonnegative_integer(
                        observation.get("item_count"), "daily item_count"
                    ),
                    "source_day_count": source_day_count,
                }
            )
        if [item["date"] for item in evolution_30d] != expected_period_dates:
            raise IssuePageContractError(
                f"{issue_id} coverage evolution dates do not match its period"
            )
        coverage_item_count = sum(item["item_count"] for item in evolution_30d)
        if coverage_item_count != series.get("item_count"):
            raise IssuePageContractError(
                f"{issue_id} coverage evolution does not sum to its 30-day count"
            )

        previous_source_day_count = _nonnegative_integer(
            series.get("previous_source_day_count"),
            f"{issue_id} previous_source_day_count",
        )
        latest_source_day_count = _nonnegative_integer(
            series.get("latest_source_day_count"),
            f"{issue_id} latest_source_day_count",
        )
        reconstructed_previous_source_day_count = previous_rows[issue_id].numerator
        reconstructed_latest_source_day_count = latest_rows[issue_id].numerator
        if previous_source_day_count != reconstructed_previous_source_day_count:
            raise IssuePageContractError(
                f"{issue_id} previous_source_day_count is inconsistent with daily activity"
            )
        if latest_source_day_count != reconstructed_latest_source_day_count:
            raise IssuePageContractError(
                f"{issue_id} latest_source_day_count is inconsistent with daily activity"
            )

        raw_previous_incidence = previous_rows[issue_id].raw_share
        raw_latest_incidence = latest_rows[issue_id].raw_share
        previous_incidence = _incidence(
            series.get("previous_incidence"),
            f"{issue_id} previous_incidence",
        )
        latest_incidence = _incidence(
            series.get("latest_incidence"),
            f"{issue_id} latest_incidence",
        )
        incidence_change_pp = _finite_number(
            series.get("incidence_change_pp"),
            f"{issue_id} incidence_change_pp",
        )
        if previous_incidence != round(raw_previous_incidence, 6):
            raise IssuePageContractError(
                f"{issue_id} previous incidence is inconsistent with source-day counts"
            )
        if latest_incidence != round(raw_latest_incidence, 6):
            raise IssuePageContractError(
                f"{issue_id} latest incidence is inconsistent with source-day counts"
            )
        expected_change_pp = round(
            (raw_latest_incidence - raw_previous_incidence) * 100,
            3,
        )
        if incidence_change_pp != expected_change_pp:
            raise IssuePageContractError(
                f"{issue_id} incidence change is inconsistent with source incidence"
            )

        current_qualified = (
            coverage_item_count >= CURRENT_ITEM_MIN
            and _nonnegative_integer(
                series.get("source_day_count"), "issue source_day_count"
            )
            >= CURRENT_SOURCE_DAY_MIN
            and _nonnegative_integer(
                series.get("publisher_count"), "issue publisher_count"
            )
            >= CURRENT_PUBLISHER_MIN
        )
        historical = history[issue_id]
        historical_qualified = (
            historical["association_count"] >= HISTORICAL_ASSOCIATION_MIN
            and historical["observed_days"] >= HISTORICAL_DAY_MIN
            and historical["candidate_count"] >= HISTORICAL_CANDIDATE_MIN
        )
        public = current_qualified or historical_qualified or issue_id in previously_public
        if current_qualified:
            lifecycle = "current"
        elif historical_qualified:
            lifecycle = "historical"
        elif issue_id in previously_public:
            lifecycle = "dormant"
        else:
            lifecycle = "unpublished"

        evidence = [_source_evidence(item) for item in topic.get("supporting_items", [])]
        evidence.sort(key=lambda item: (item["published_at"], item["id"]), reverse=True)
        current_associations = _current_associations(topic, route_map)
        latest = evidence[0] if evidence else None
        issues.append(
            {
                "issue_id": issue_id,
                "labels": {"fr": definition.label_fr, "en": definition.label_en},
                "slugs": {"fr": definition.slug_fr, "en": definition.slug_en},
                "routes": definition.routes,
                "canonical": {
                    language: f"{PUBLIC_ORIGIN}{route}"
                    for language, route in definition.routes.items()
                },
                "public": public,
                "lifecycle": lifecycle,
                "qualification": {
                    "current": current_qualified,
                    "historical": historical_qualified,
                    "retained": issue_id in previously_public,
                },
                "current_coverage": {
                    "period_start": period_start,
                    "period_end": period_end,
                    "item_count": coverage_item_count,
                    "publisher_count": series["publisher_count"],
                    "publisher_names": topic.get("publisher_names", []),
                    "source_day_count": series["source_day_count"],
                    "active_day_count": series["active_day_count"],
                    "evolution_30d": evolution_30d,
                    "comparison_7d": {
                        "days": comparison_days,
                        "previous_start": previous_start,
                        "previous_end": previous_end,
                        "latest_start": latest_start,
                        "latest_end": latest_end,
                        "previous_source_day_count": previous_source_day_count,
                        "latest_source_day_count": latest_source_day_count,
                        "previous_incidence": previous_incidence,
                        "latest_incidence": latest_incidence,
                        "incidence_change_pp": incidence_change_pp,
                    },
                    "latest_observation": (
                        {
                            "id": latest["id"],
                            "date": latest["date"],
                            "publisher": latest["publisher"],
                            "headline": latest["headline"],
                            "url": latest["url"],
                        }
                        if latest
                        else None
                    ),
                },
                "current_candidate_associations": {
                    "candidate_count": len(current_associations),
                    "candidates": current_associations,
                },
                "historical_candidate_associations": historical,
                "subtopics": _subtopics(definition, topic),
                "evidence": evidence[:20],
                "related_issues": [],
            }
        )

    _related_issues(issues)
    history_index = (
        validate_issue_coverage_history(coverage_history)
        if coverage_history is not None
        else None
    )
    if history_index is not None:
        for issue in issues:
            issue["coverage_history"] = history_index[issue["issue_id"]]

    public_issues = [issue for issue in issues if issue["public"]]
    public_issues.sort(
        key=lambda issue: (
            -issue["current_coverage"]["item_count"],
            CANONICAL_ISSUE_IDS.index(issue["issue_id"]),
        )
    )
    evidence_records: list[dict[str, Any]] = []
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_by_url: dict[str, dict[str, Any]] = {}

    for issue in public_issues:
        for item in issue["evidence"]:
            id_match = evidence_by_id.get(item["id"])
            url_match = evidence_by_url.get(item["url"])

            if (
                id_match is not None
                and url_match is not None
                and id_match is not url_match
            ):
                first_index = evidence_records.index(id_match)
                second_index = evidence_records.index(url_match)
                if first_index <= second_index:
                    existing, duplicate = id_match, url_match
                else:
                    existing, duplicate = url_match, id_match

                for issue_id in duplicate["issue_ids"]:
                    if issue_id not in existing["issue_ids"]:
                        existing["issue_ids"].append(issue_id)

                for evidence_id, record in list(evidence_by_id.items()):
                    if record is duplicate:
                        evidence_by_id[evidence_id] = existing
                for evidence_url, record in list(evidence_by_url.items()):
                    if record is duplicate:
                        evidence_by_url[evidence_url] = existing
                evidence_records.remove(duplicate)
            else:
                existing = id_match or url_match

            if existing is None:
                existing = {**item, "issue_ids": []}
                evidence_records.append(existing)

            evidence_by_id[item["id"]] = existing
            evidence_by_url[item["url"]] = existing
            if issue["issue_id"] not in existing["issue_ids"]:
                existing["issue_ids"].append(issue["issue_id"])

    canonical_order = {
        issue_id: index
        for index, issue_id in enumerate(CANONICAL_ISSUE_IDS)
    }
    for item in evidence_records:
        item["issue_ids"].sort(key=canonical_order.__getitem__)

    latest_observations = sorted(
        evidence_records,
        key=lambda item: (item["published_at"], item["id"]),
        reverse=True,
    )[:20]

    current_publishers = sorted(
        {
            publisher
            for issue in public_issues
            for publisher in issue["current_coverage"]["publisher_names"]
            if isinstance(publisher, str) and publisher
        },
        key=_normalized_name,
    )
    current_candidates = sorted(
        {
            item["candidate_name"]
            for issue in public_issues
            for item in issue["current_candidate_associations"]["candidates"]
        },
        key=_normalized_name,
    )
    classified_item_count = _nonnegative_integer(
        policy.get("classified_item_count"), "policy_agenda.classified_item_count"
    )

    projection = {
        "schema_version": SCHEMA_VERSION,
        "live_source_snapshot": news_wire.get("generated_at"),
        "data_as_of": period_end,
        "period": {"start": period_start, "end": period_end, "days": 30},
        "metrics": {
            "public_issue_count": len(public_issues),
            "current_evidence_item_count": classified_item_count,
            "coverage_assignment_count": sum(
                issue["current_coverage"]["item_count"] for issue in public_issues
            ),
            "unique_publisher_count": len(current_publishers),
            "associated_candidate_count": len(current_candidates),
        },
        "publishers": current_publishers,
        "associated_candidates": current_candidates,
        "latest_observations": latest_observations,
        "campaign_agenda": _campaign_agenda_summary(news_wire),
        "issues": public_issues,
        "unpublished_issues": [issue for issue in issues if not issue["public"]],
    }
    if coverage_history is not None:
        projection["coverage_history"] = {
            "period": coverage_history["period"],
            "denominator": coverage_history["denominator"],
            "corpus": coverage_history["corpus"],
            "reconstruction": coverage_history["reconstruction"],
        }
    return projection



def issue_manifest_payload(projection: dict[str, Any]) -> dict[str, Any]:
    """Serialize current and historical public URL membership."""

    pages = [
        {
            "issue_id": issue["issue_id"],
            "lifecycle": issue["lifecycle"],
            "page_path_fr": issue["routes"]["fr"],
            "page_path_en": issue["routes"]["en"],
            "history_page_path_fr": (
                f"/enjeux/historique/{issue['slugs']['fr']}/"
            ),
            "history_page_path_en": (
                f"/en/issues/history/{issue['slugs']['en']}/"
            ),
        }
        for issue in projection["issues"]
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "data_as_of": projection["data_as_of"],
        "issue_count": len(pages),
        "page_count": len(pages) * 4 + 4,
        "hubs": {
            "fr": "/enjeux/",
            "en": "/en/issues/",
        },
        "history_hubs": {
            "fr": "/enjeux/historique/",
            "en": "/en/issues/history/",
        },
        "pages": pages,
    }




def validate_issue_manifest(payload: Any) -> None:
    payload = _require_mapping(payload, "issue manifest")

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise IssuePageContractError(
            "issue manifest schema version mismatch"
        )

    pages = _require_list(
        payload.get("pages"),
        "issue manifest.pages",
    )

    if payload.get("issue_count") != len(pages):
        raise IssuePageContractError(
            "issue manifest issue_count mismatch"
        )

    history_hubs = payload.get("history_hubs")
    legacy = history_hubs is None

    expected_page_count = (
        len(pages) * 2 + 2
        if legacy
        else len(pages) * 4 + 4
    )

    if payload.get("page_count") != expected_page_count:
        raise IssuePageContractError(
            "issue manifest page_count mismatch"
        )

    hubs = _require_mapping(
        payload.get("hubs"),
        "issue manifest.hubs",
    )

    if hubs != {
        "fr": "/enjeux/",
        "en": "/en/issues/",
    }:
        raise IssuePageContractError(
            "issue manifest current hubs mismatch"
        )

    if not legacy:
        history_hubs = _require_mapping(
            history_hubs,
            "issue manifest.history_hubs",
        )

        if history_hubs != {
            "fr": "/enjeux/historique/",
            "en": "/en/issues/history/",
        }:
            raise IssuePageContractError(
                "issue manifest history hubs mismatch"
            )

    seen = set()

    for page in pages:
        page = _require_mapping(
            page,
            "issue manifest page",
        )

        issue_id = page.get("issue_id")

        if issue_id not in ISSUE_BY_ID or issue_id in seen:
            raise IssuePageContractError(
                "issue manifest identity is invalid"
            )

        seen.add(issue_id)
        definition = ISSUE_BY_ID[issue_id]

        if page.get("page_path_fr") != definition.routes["fr"]:
            raise IssuePageContractError(
                "issue manifest French route mismatch"
            )

        if page.get("page_path_en") != definition.routes["en"]:
            raise IssuePageContractError(
                "issue manifest English route mismatch"
            )

        if not legacy:
            if page.get("history_page_path_fr") != (
                f"/enjeux/historique/{definition.slug_fr}/"
            ):
                raise IssuePageContractError(
                    "issue manifest French history route mismatch"
                )

            if page.get("history_page_path_en") != (
                f"/en/issues/history/{definition.slug_en}/"
            ):
                raise IssuePageContractError(
                    "issue manifest English history route mismatch"
                )

        if page.get("lifecycle") not in {
            "current",
            "historical",
            "dormant",
        }:
            raise IssuePageContractError(
                "issue manifest lifecycle is invalid"
            )
