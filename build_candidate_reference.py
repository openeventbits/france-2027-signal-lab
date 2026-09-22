"""Build the fixed Marine Le Pen candidate-page reference projection.

This is intentionally a one-candidate reference builder, not a general page
generator.  It validates the authoritative FR27 artifacts, selects bounded
Marine-specific evidence, and writes the checked-in projection.  News Wire is
read only at build time and is never a browser dependency.
"""

from __future__ import annotations

import argparse
import html
import re
from html.parser import HTMLParser
import json
import os
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from build_candidate_signals import validate_candidate_signals
from campaign_events_contract import validate_campaign_events_artifact
from candidate_agenda_history_contract import validate_candidate_agenda_history
from candidate_attention_contract import validate_candidate_attention
from candidate_candidacy_status import (
    active_candidate_records,
    validate_candidate_candidacy_status,
)
from candidate_visibility_history_contract import (
    validate_candidate_visibility_history,
)
from fetch_claims_under_scrutiny import validate_public_bundle
from fetch_polls import validate_second_round_event
from generate_recent_changes import validate_recent_changes
from poll_contract import validate_poll_events


CANDIDATE_ID = "marine-le-pen"
SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "candidates" / CANDIDATE_ID / "data.json"
HTML_OUTPUT_PATH = ROOT / "candidates" / CANDIDATE_ID / "index.html"
HTML_OUTPUT_PATH_EN = ROOT / "en" / "candidates" / CANDIDATE_ID / "index.html"

MAX_RECENT_CHANGES = 6
MAX_RUNOFF_MATCHUPS = 8
MAX_RUNOFF_EVENTS_PER_MATCHUP = 3
MAX_TOP_PUBLISHERS = 10
MAX_STORY_CLUSTERS = 8
MAX_LATEST_COVERAGE = 12
MAX_SCRUTINY_REVIEWS = 12
MAX_UPCOMING_EVENTS = 6
MAX_RECENT_EVENTS = 8
MAX_AGENDA_TOPICS = 4

SOURCE_FILES = {
    "candidate_signals": "candidate_signals.json",
    "candidate_visibility_history": "candidate_visibility_history.json",
    "candidate_agenda_history": "candidate_agenda_history.json",
    "candidate_attention": "candidate_attention.json",
    "candidate_candidacy_status": "candidate_candidacy_status.json",
    "claims_under_scrutiny": "claims_under_scrutiny.json",
    "recent_changes": "recent_changes.json",
    "campaign_events": "campaign_events.json",
    "polls": "polls.json",
    "second_round_polls": "second_round_polls.json",
    "news_wire": "news_wire.json",
    "publication_manifest": "publication_manifest.json",
}


class CandidateReferenceError(ValueError):
    """Raised when the fixed reference cannot be derived safely."""


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_sources(root: Path = ROOT) -> dict[str, Any]:
    return {key: _load(root / filename) for key, filename in SOURCE_FILES.items()}


def _one(items: Iterable[dict[str, Any]], *, field: str, value: str) -> dict[str, Any]:
    matches = [item for item in items if item.get(field) == value]
    if len(matches) != 1:
        raise CandidateReferenceError(
            f"expected exactly one {field}={value!r}; found {len(matches)}"
        )
    return matches[0]


def validate_sources(sources: dict[str, Any], root: Path = ROOT) -> None:
    status = sources["candidate_candidacy_status"]
    signals = sources["candidate_signals"]
    polls = sources["polls"]
    news = sources["news_wire"]
    claims = sources["claims_under_scrutiny"]

    validate_candidate_candidacy_status(status)
    validate_candidate_signals(
        signals,
        polls=polls,
        news=news,
        claims=claims,
        candidacy_status=status,
    )
    active = active_candidate_records(status)
    validate_candidate_visibility_history(
        sources["candidate_visibility_history"], expected_candidates=status["candidates"]
    )
    validate_candidate_agenda_history(
        sources["candidate_agenda_history"], expected_candidates=status["candidates"]
    )
    validate_candidate_attention(
        sources["candidate_attention"], expected_candidates=active
    )
    validate_public_bundle(claims, candidacy_payload=status)
    validate_recent_changes(sources["recent_changes"])
    validate_campaign_events_artifact(
        sources["campaign_events"],
        candidate_registry_path=root / "candidate_candidacy_status.json",
        source_registry_path=root / "campaign_event_sources.json",
    )
    validate_poll_events(polls)
    runoff = sources["second_round_polls"]
    if runoff.get("schema_version") != "1.0" or not isinstance(runoff.get("events"), list):
        raise CandidateReferenceError("second_round_polls has an unsupported contract")
    for event in runoff["events"]:
        validate_second_round_event(event)

    candidate = _one(status["candidates"], field="candidate_id", value=CANDIDATE_ID)
    if candidate["candidate_name"] != "Marine Le Pen":
        raise CandidateReferenceError("canonical candidate name drifted")
    if candidate["status"] != "declared":
        raise CandidateReferenceError("Marine Le Pen is no longer declared")


def derive_hud_metrics(sources: dict[str, Any]) -> dict[str, int]:
    """Derive global HUD metrics from the dashboard's source contracts."""

    source_network = sources["publication_manifest"].get("source_network")
    if not isinstance(source_network, dict):
        raise CandidateReferenceError("publication_manifest source_network is missing")
    domains = source_network.get("approved_publisher_domains")
    if not isinstance(domains, int) or isinstance(domains, bool) or domains < 0:
        raise CandidateReferenceError(
            "publication_manifest approved_publisher_domains is invalid"
        )

    polls = sources["polls"]
    validate_poll_events(polls)
    poll_package_keys = {
        (
            event["pollster"],
            event["fieldwork_start"],
            event["fieldwork_end"],
            event["sample_size"],
        )
        for event in polls
        if event.get("round") == "first_round"
    }
    if not poll_package_keys:
        raise CandidateReferenceError("no first-round poll packages are available")
    return {"domains": domains, "poll_packages": len(poll_package_keys)}


def _event_date(value: dict[str, Any]) -> date:
    return date.fromisoformat(value["scheduled_start"][:10])


def _event_projection(event: dict[str, Any], lane: str) -> dict[str, Any]:
    evidence = event.get("evidence") or []
    first_source = evidence[0] if evidence else None
    return {
        "event_id": event["event_id"],
        "lane": lane,
        "event_type": event["event_type"],
        "title": event["title"],
        "scheduled_start": event["scheduled_start"],
        "time_precision": event["time_precision"],
        "timezone": event["timezone"],
        "organization": event.get("organization"),
        "location_name": event.get("location_name"),
        "locality": event.get("locality"),
        "status": event["status"],
        "evidence_status": event["evidence_status"],
        "source": (
            {
                "url": first_source["source_url"],
                "publisher": first_source["source_publisher"],
                "type": first_source["source_type"],
            }
            if first_source
            else None
        ),
    }


def _runoff_projection(events: list[dict[str, Any]], candidate_name: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        names = [entry["name"] for entry in event["candidates"]]
        if candidate_name not in names:
            continue
        opponent = next(name for name in names if name != candidate_name)
        scores = {entry["name"]: entry["score"] for entry in event["candidates"]}
        grouped.setdefault(opponent, []).append(
            {
                "event_id": event["event_id"],
                "pollster": event["pollster"],
                "fieldwork_start": event["fieldwork_start"],
                "fieldwork_end": event["fieldwork_end"],
                "sample_size": event["sample_size"],
                "candidate_score": scores[candidate_name],
                "opponent_score": scores[opponent],
                "source_url": event["source_url"],
            }
        )
    matchups: list[dict[str, Any]] = []
    for opponent, observations in grouped.items():
        ordered = sorted(
            observations,
            key=lambda item: (item["fieldwork_end"], item["event_id"]),
            reverse=True,
        )
        matchups.append(
            {
                "opponent": opponent,
                "observation_count": len(ordered),
                "latest_fieldwork_end": ordered[0]["fieldwork_end"],
                "observations": ordered[:MAX_RUNOFF_EVENTS_PER_MATCHUP],
            }
        )
    return sorted(
        matchups,
        key=lambda item: (item["latest_fieldwork_end"], item["opponent"]),
        reverse=True,
    )[:MAX_RUNOFF_MATCHUPS]


def _topic_projection(profile: dict[str, Any]) -> dict[str, Any]:
    topics = []
    for topic in profile["topics"]:
        count = topic.get("association_count", topic.get("count"))
        topics.append({"id": topic["id"], "count": count, "share": topic["share"]})
    return {
        "profile_mode": profile["profile_mode"],
        "period_start": profile["period_start"],
        "period_end": profile["period_end"],
        "day_count": profile.get("day_count", profile.get("window_days")),
        "association_count": profile["association_count"],
        "topics": topics,
    }


def build_projection(sources: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    validate_sources(sources, root)
    status_payload = sources["candidate_candidacy_status"]
    candidate_status = _one(
        status_payload["candidates"], field="candidate_id", value=CANDIDATE_ID
    )
    candidate_name = candidate_status["candidate_name"]
    signals_payload = sources["candidate_signals"]
    signals = _one(signals_payload["candidates"], field="candidate_id", value=CANDIDATE_ID)
    visibility = _one(
        sources["candidate_visibility_history"]["candidates"],
        field="candidate_id",
        value=CANDIDATE_ID,
    )
    agenda = _one(
        sources["candidate_agenda_history"]["candidates"],
        field="candidate_id",
        value=CANDIDATE_ID,
    )
    attention = _one(
        sources["candidate_attention"]["candidates"],
        field="candidate_id",
        value=CANDIDATE_ID,
    )

    polling = signals["polling"]
    if (
        polling["evidence_state"] != "reported"
        or polling["range_min"] != 33
        or polling["range_max"] != 36
        or polling["hypothesis_count"] != 5
    ):
        raise CandidateReferenceError(
            "current Marine polling evidence is not the locked 33-36 / 5-hypothesis package"
        )

    news = sources["news_wire"]
    period = news["candidate_visibility"]["current_period"]
    candidate_metric = _one(
        period["candidate_metrics"], field="candidate", value=candidate_name
    )
    current_records = [
        item
        for item in news["candidate_watch"]
        if candidate_name in item.get("candidates", [])
        and item.get("coverage_scope") in news["candidate_visibility"]["primary_scopes"]
        and period["start_date"] <= item["published_at"][:10] <= period["end_date"]
    ]
    current_records.sort(key=lambda item: (item["published_at"], item["id"]), reverse=True)
    publisher_counts = Counter(item["publisher"] for item in current_records)
    if len(current_records) != signals["campaign_attention"]["record_count"]:
        raise CandidateReferenceError(
            "projected campaign/election records do not reconcile to Candidate Signals"
        )
    if candidate_metric["record_count"] != signals["campaign_attention"]["record_count"]:
        raise CandidateReferenceError(
            "News Wire candidate metric does not reconcile to Candidate Signals"
        )
    if len(publisher_counts) != signals["campaign_attention"]["publisher_count"]:
        raise CandidateReferenceError(
            "projected publisher count does not reconcile to Candidate Signals"
        )

    claims = [
        review
        for review in sources["claims_under_scrutiny"]["reviews"]
        if any(
            association["candidate_id"] == CANDIDATE_ID
            for association in review.get("candidate_associations", [])
        )
    ]
    claims.sort(key=lambda item: (item["review_date"], item["id"]), reverse=True)
    review_projection = []
    for review in claims[:MAX_SCRUTINY_REVIEWS]:
        relationship = next(
            association["relationship"]
            for association in review["candidate_associations"]
            if association["candidate_id"] == CANDIDATE_ID
        )
        review_projection.append(
            {
                "id": review["id"],
                "review_url": review["review_url"],
                "publisher_name": review["publisher_name"],
                "review_date": review["review_date"],
                "claim_text": review["claim_text"],
                "claimant": review["claimant"],
                "rating": review["rating"],
                "relationship": relationship,
            }
        )

    changes = [
        item
        for item in sources["recent_changes"]["items"]
        if CANDIDATE_ID in item.get("candidate_ids", [])
    ][:MAX_RECENT_CHANGES]
    change_projection = [
        {
            "id": item["id"],
            "category": item["category"],
            "headline": item["headline"],
            "summary": item["summary"],
            "trusted_change_at": item["trusted_change_at"],
            "source": item["primary_source"],
        }
        for item in changes
    ]

    event_payload = sources["campaign_events"]
    all_events: list[tuple[str, dict[str, Any]]] = []
    for lane in ("campaign_events", "institutional_milestones", "event_watch"):
        all_events.extend(
            (lane, event)
            for event in event_payload[lane]
            if CANDIDATE_ID in event.get("candidate_ids", [])
        )
    reference_date = date.fromisoformat(period["end_date"])
    upcoming = sorted(
        (
            _event_projection(event, lane)
            for lane, event in all_events
            if _event_date(event) >= reference_date and event["status"] != "cancelled"
        ),
        key=lambda item: (item["scheduled_start"], item["event_id"]),
    )[:MAX_UPCOMING_EVENTS]
    recent = sorted(
        (
            _event_projection(event, lane)
            for lane, event in all_events
            if _event_date(event) < reference_date
        ),
        key=lambda item: (item["scheduled_start"], item["event_id"]),
        reverse=True,
    )[:MAX_RECENT_EVENTS]
    next_or_recent = upcoming[0] if upcoming else (recent[0] if recent else None)

    current_agenda = _topic_projection(signals["agenda_profile"])
    cumulative_agenda = _topic_projection(agenda["cumulative_profile"])
    top_topic_ids = [
        item["id"]
        for item in sorted(
            cumulative_agenda["topics"],
            key=lambda item: (item["count"], item["id"]),
            reverse=True,
        )
        if item["count"] > 0
    ][:MAX_AGENDA_TOPICS]
    agenda_evolution = [
        {
            "date": day["date"],
            "counts": {topic_id: day["policy_counts"][topic_id] for topic_id in top_topic_ids},
        }
        for day in agenda["daily_series"]
    ]

    media = signals["campaign_attention"]
    top_publishers = [
        {"publisher": publisher, "record_count": count, "share": round(count / len(current_records), 3)}
        for publisher, count in sorted(
            publisher_counts.items(), key=lambda item: (-item[1], item[0].casefold())
        )[:MAX_TOP_PUBLISHERS]
    ]
    top_clusters = [
        {
            "cluster_id": item["cluster_id"],
            "label": item["label"],
            "record_count": item["record_count"],
            "share": item["share"],
            "publisher_count": item["publisher_count"],
            "active_day_count": item["active_day_count"],
        }
        for item in candidate_metric["story_clusters"][:MAX_STORY_CLUSTERS]
    ]
    coverage = [
        {
            "id": item["id"],
            "publisher": item["publisher"],
            "published_at": item["published_at"],
            "headline": item["headline"],
            "url": item["url"],
            "coverage_scope": item["coverage_scope"],
        }
        for item in current_records[:MAX_LATEST_COVERAGE]
    ]

    source_generated = {
        name: payload.get("generated_at")
        for name, payload in sources.items()
        if isinstance(payload, dict) and payload.get("generated_at")
    }
    projection = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "candidate": {
            "candidate_id": CANDIDATE_ID,
            "candidate_name": candidate_name,
            "status": candidate_status["status"],
            "display_tier": candidate_status["display_tier"],
            "status_as_of": candidate_status["status_as_of"],
            "portrait_path": "/assets/candidates/lepen.png",
        },
        "dossier": {
            "polling": {
                "evidence_state": polling["evidence_state"],
                "range_min": polling["range_min"],
                "range_max": polling["range_max"],
                "hypothesis_count": polling["hypothesis_count"],
                "fieldwork_start": signals_payload["featured_polling_package"]["fieldwork_start"],
                "fieldwork_end": signals_payload["featured_polling_package"]["fieldwork_end"],
                "pollster": signals_payload["featured_polling_package"]["pollster"],
                "sample_size": signals_payload["featured_polling_package"]["sample_size"],
                "source_urls": signals_payload["featured_polling_package"]["source_urls"],
            },
            "media_pulse": media,
        },
        "now": {
            "latest_development": signals["latest_development"],
            "next_or_recent_event": next_or_recent,
            "recent_changes": change_projection,
        },
        "polling": {
            "current": {
                "evidence_state": polling["evidence_state"],
                "range_min": polling["range_min"],
                "range_max": polling["range_max"],
                "hypothesis_count": polling["hypothesis_count"],
                "fieldwork_start": signals_payload["featured_polling_package"]["fieldwork_start"],
                "fieldwork_end": signals_payload["featured_polling_package"]["fieldwork_end"],
                "pollster": signals_payload["featured_polling_package"]["pollster"],
                "sample_size": signals_payload["featured_polling_package"]["sample_size"],
                "source_urls": signals_payload["featured_polling_package"]["source_urls"],
            },
            "first_round_history": signals["poll_history"],
            "tested_runoffs": _runoff_projection(
                sources["second_round_polls"]["events"], candidate_name
            ),
        },
        "media": {
            "summary": media,
            "period": {"start_date": period["start_date"], "end_date": period["end_date"]},
            "recent_history": visibility["campaign_attention"]["daily_series"],
            "top_publishers": top_publishers,
            "top_story_clusters": top_clusters,
            "latest_coverage": coverage,
            "available_record_count": len(current_records),
        },
        "agenda": {
            "current": current_agenda,
            "since_tracking": cumulative_agenda,
            "evolution_topic_ids": top_topic_ids,
            "evolution": agenda_evolution,
        },
        "accountability": {
            "reviews": review_projection,
            "review_count": len(claims),
            "candidacy_evidence": {
                "status": candidate_status["status"],
                "status_as_of": candidate_status["status_as_of"],
                "source_date": candidate_status["source_date"],
                "source_url": candidate_status["source_url"],
                "source_title": candidate_status["source_title"],
                "source_publisher": candidate_status["source_publisher"],
                "status_note": candidate_status["status_note"],
            },
        },
        "attention": {
            key: attention[key]
            for key in (
                "evidence_state",
                "wikipedia_article",
                "latest_7_views",
                "previous_7_views",
                "change_7_pct",
                "latest_28_views",
                "previous_28_views",
                "change_28_pct",
                "latest_7_peak_date",
                "latest_7_peak_views",
                "period_peak_date",
                "period_peak_views",
                "interpretation_flag",
                "daily_series",
            )
        },
        "events": {"reference_date": reference_date.isoformat(), "upcoming": upcoming, "recent": recent},
        "freshness": {
            "candidate_signal_evidence_dates": signals_payload["evidence_dates"],
            "source_generated_at": source_generated,
            "media_period_end": period["end_date"],
            "agenda_data_as_of": sources["candidate_agenda_history"]["tracking"]["data_as_of"],
            "attention_period_end": sources["candidate_attention"]["period"]["end_date"],
        },
        "bounds": {
            "recent_changes": MAX_RECENT_CHANGES,
            "runoff_matchups": MAX_RUNOFF_MATCHUPS,
            "runoff_events_per_matchup": MAX_RUNOFF_EVENTS_PER_MATCHUP,
            "top_publishers": MAX_TOP_PUBLISHERS,
            "story_clusters": MAX_STORY_CLUSTERS,
            "latest_coverage": MAX_LATEST_COVERAGE,
            "scrutiny_reviews": MAX_SCRUTINY_REVIEWS,
            "upcoming_events": MAX_UPCOMING_EVENTS,
            "recent_events": MAX_RECENT_EVENTS,
            "agenda_topics": MAX_AGENDA_TOPICS,
        },
    }
    validate_projection(projection)
    return projection


def validate_projection(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise CandidateReferenceError("projection schema_version is invalid")
    if payload.get("candidate_id") != CANDIDATE_ID:
        raise CandidateReferenceError("projection candidate_id is invalid")
    candidate = payload.get("candidate", {})
    if candidate.get("candidate_id") != CANDIDATE_ID or candidate.get("status") != "declared":
        raise CandidateReferenceError("projection candidate identity/status is invalid")
    current = payload["polling"]["current"]
    if (current["range_min"], current["range_max"], current["hypothesis_count"]) != (33, 36, 5):
        raise CandidateReferenceError("projection polling headline evidence drifted")
    media = payload["media"]
    if media["available_record_count"] != payload["dossier"]["media_pulse"]["record_count"]:
        raise CandidateReferenceError("projection Media Pulse record count is inconsistent")
    if len(media["recent_history"]) != 29:
        raise CandidateReferenceError("projection media history must contain 29 complete days")
    bounds = payload["bounds"]
    bounded = {
        "recent_changes": len(payload["now"]["recent_changes"]),
        "runoff_matchups": len(payload["polling"]["tested_runoffs"]),
        "top_publishers": len(media["top_publishers"]),
        "story_clusters": len(media["top_story_clusters"]),
        "latest_coverage": len(media["latest_coverage"]),
        "scrutiny_reviews": len(payload["accountability"]["reviews"]),
        "upcoming_events": len(payload["events"]["upcoming"]),
        "recent_events": len(payload["events"]["recent"]),
    }
    for key, actual in bounded.items():
        if actual > bounds[key]:
            raise CandidateReferenceError(f"projection {key} exceeds its bound")
    for matchup in payload["polling"]["tested_runoffs"]:
        if len(matchup["observations"]) > bounds["runoff_events_per_matchup"]:
            raise CandidateReferenceError("runoff matchup exceeds observation bound")


def serialize_projection(payload: dict[str, Any]) -> bytes:
    validate_projection(payload)
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


RUNOFF_PORTRAITS_FR = {
    "Édouard Philippe": "/assets/candidates/philippe.png",
    "Jean-Luc Mélenchon": "/assets/candidates/melenchon.png",
    "Gabriel Attal": "/assets/candidates/attal.png",
    "Raphaël Glucksmann": "/assets/candidates/glucksmann.png",
    "François Hollande": "/assets/candidates/hollande.png",
    "Bruno Retailleau": "/assets/candidates/retailleau.png",
    "François Ruffin": "/assets/candidates/ruffin.png",
}


TOPIC_LABELS_FR = {
    "economy_public_finances": "Économie et finances publiques",
    "work_purchasing_power_pensions": "Travail, pouvoir d’achat et retraites",
    "immigration_identity_secularism": "Immigration, identité et laïcité",
    "security_justice": "Sécurité et justice",
    "health_education_public_services": "Santé, éducation et services publics",
    "climate_energy_agriculture": "Climat, énergie et agriculture",
    "europe_defence_foreign_affairs": "Europe, défense et affaires étrangères",
    "institutions_democracy_territories": "Institutions, démocratie et territoires",
}

CATEGORY_LABELS_FR = {
    "campaign": "CAMPAGNE",
    "fact_check": "VÉRIFICATION",
    "legal": "JURIDIQUE",
    "polling": "SONDAGE",
    "runoff": "SECOND TOUR",
}

EVENT_TYPE_LABELS_FR = {
    "campaign_launch": "LANCEMENT DE CAMPAGNE",
    "candidate_visit": "DÉPLACEMENT",
    "debate": "DÉBAT",
    "other": "AUTRE",
    "public_meeting": "RÉUNION PUBLIQUE",
    "rally": "MEETING",
}

SCOPE_LABELS_FR = {
    "campaign": "CAMPAGNE",
    "election": "ÉLECTION",
    "general": "GÉNÉRAL",
}

MONTHS_FR = (
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
)


def _h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fr_date(value: str | None) -> str:
    if not value:
        return "Date non publiée"
    parsed = date.fromisoformat(value[:10])
    return f"{parsed.day} {MONTHS_FR[parsed.month - 1]} {parsed.year}"


def _number(value: int | float) -> str:
    if isinstance(value, float) and not value.is_integer():
        return f"{value:g}".replace(".", ",")
    return f"{int(value):,}".replace(",", " ")


def _hypothesis_text(count: int) -> str:
    return f"{_number(count)} hypothèse" + ("" if count == 1 else "s")


def _percent(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}".replace(".", ",") + "%"


def _source_link(url: str, label: str = "Source ↗") -> str:
    return (
        f'<a class="candidate-source-link" href="{_h(url)}" '
        f'target="_blank" rel="noopener noreferrer">{_h(label)}</a>'
    )


def _archive_items(items: list[str], *, initial: int, label: str) -> str:
    rendered = []
    for index, item in enumerate(items):
        hidden = " hidden data-archive-extra" if index >= initial else ""
        rendered.append(f'<li{hidden}>{item}</li>')
    button = ""
    if len(items) > initial:
        button = (
            '<button class="candidate-archive-toggle" type="button" '
            f'data-archive-toggle aria-expanded="false">Afficher plus de {_h(label)}</button>'
        )
    return (
        f'<div class="candidate-archive" data-archive data-collapsed-label="Afficher plus de {_h(label)}" '
        f'data-expanded-label="Réduire"><ol class="candidate-evidence-list">'
        + "".join(rendered)
        + f"</ol>{button}</div>"
    )


def _agenda_count_label(count: int, singular: str, plural: str) -> str:
    return f'{_number(count)} {singular if count == 1 else plural}'


def _render_topic_profile(
    profile: dict[str, Any],
    topic_ids: list[str],
    period_label: str,
    tooltip_prefix: str,
) -> str:
    topics_by_id = {topic["id"]: topic for topic in profile["topics"]}
    rows = []

    for topic_id in topic_ids:
        topic = topics_by_id[topic_id]
        label = TOPIC_LABELS_FR[topic_id]
        tooltip_id = f'agenda-topic-{tooltip_prefix}-{topic_id}-note'
        share = _percent(topic["share"])
        association_count = _agenda_count_label(
            topic["count"], "association", "associations"
        )

        rows.append(
            '<li class="candidate-topic-row" tabindex="0" '
            f'data-topic-id="{_h(topic_id)}" '
            f'aria-describedby="{tooltip_id}" '
            f'aria-label="{_h(label)}. Part du profil : {share}. '
            f'{association_count}. Période : {period_label}.">'
            '<div class="candidate-topic-heading">'
            f'<span>{_h(label)}</span>'
            f'<strong>{share}</strong>'
            '</div>'
            '<span class="candidate-topic-track" aria-hidden="true">'
            f'<span class="candidate-topic-bar" style="--topic-share:{topic["share"]}"></span>'
            '</span>'
            f'<span class="candidate-chart-tooltip candidate-topic-tooltip" id="{tooltip_id}" role="tooltip">'
            f'<strong>{_h(label)}</strong>'
            f'<span>Part du profil : {share}</span>'
            f'<span>Associations : {_number(topic["count"])}</span>'
            f'<span>Période : {period_label}</span>'
            '</span>'
            '</li>'
        )

    return '<ul class="candidate-topic-list">' + "".join(rows) + '</ul>'

def _render_candidate_structure_html(
    payload: dict[str, Any], hud_metrics: dict[str, int] | None = None
) -> bytes:
    if hud_metrics is None:
        hud_metrics = derive_hud_metrics(load_sources(ROOT))
    """Render the fixed French reference page from the validated projection."""

    validate_projection(payload)
    candidate = payload["candidate"]
    dossier = payload["dossier"]
    current_poll = payload["polling"]["current"]
    media = payload["media"]
    attention = payload["attention"]
    poll_range = (
        f'{_number(current_poll["range_min"])}–{_number(current_poll["range_max"])}%'
    )
    poll_hypotheses = _hypothesis_text(current_poll["hypothesis_count"])
    poll_headline = f"{poll_range} · {poll_hypotheses}"

    change_items = []
    for item in payload["now"]["recent_changes"]:
        change_items.append(
            '<article class="candidate-ledger-item">'
            f'<div class="candidate-kicker">{_h(CATEGORY_LABELS_FR.get(item["category"], item["category"].replace("_", " ").upper()))}</div>'
            f'<h4>{_h(item["headline"])}</h4>'
            '<div class="candidate-meta">'
            f'<time datetime="{_h(item["trusted_change_at"])}">{_fr_date(item["trusted_change_at"])}</time>'
            f'{_source_link(item["source"]["url"], item["source"]["name"] + " ↗")}'
            "</div></article>"
        )

    runoff_matchups = payload["polling"]["tested_runoffs"]

    runoff_visible_count = sum(
        len(matchup["observations"]) for matchup in runoff_matchups
    )
    runoff_opponent_count = len(runoff_matchups)

    runoff_header_meta = (
        f'{_number(runoff_opponent_count)} adversaire'
        f'{"s" if runoff_opponent_count != 1 else ""}'
        f' · {_number(runoff_visible_count)} observation'
        f'{"s" if runoff_visible_count != 1 else ""} affichée'
        f'{"s" if runoff_visible_count != 1 else ""}'
    )

    runoff_groups = []

    for matchup in runoff_matchups:
        observations = matchup["observations"]
        visible_count = len(observations)
        total_count = matchup["observation_count"]

        if total_count > visible_count:
            group_meta = (
                f'{_number(total_count)} tests au total · '
                f'{_number(visible_count)} plus récents affichés'
            )
        else:
            group_meta = (
                f'{_number(total_count)} test'
                f'{"s" if total_count != 1 else ""} au total'
            )

        observation_cards = []

        for observation in observations:
            candidate_score = observation["candidate_score"]
            opponent_score = observation["opponent_score"]

            observation_cards.append(
                '<article class="candidate-runoff-card">'
                '<div class="candidate-runoff-card-head">'
                f'<strong>{_h(observation["pollster"])}</strong>'
                f'<span>{_fr_date(observation["fieldwork_start"])}'
                f' — {_fr_date(observation["fieldwork_end"])}</span>'
                '</div>'
                f'<div class="candidate-runoff-sample">Échantillon : '
                f'{_number(observation["sample_size"])}</div>'
                '<div class="candidate-runoff-split" '
                f'aria-label="{_h(candidate["candidate_name"])} '
                f'{_number(candidate_score)} %, '
                f'{_h(matchup["opponent"])} '
                f'{_number(opponent_score)} %">'
                f'<span class="candidate-runoff-score candidate-runoff-score-candidate">'
                f'{_number(candidate_score)}%</span>'
                '<span class="candidate-runoff-track" '
                f'style="--candidate-share:{candidate_score}%;" '
                'aria-hidden="true"></span>'
                f'<span class="candidate-runoff-score candidate-runoff-score-opponent">'
                f'{_number(opponent_score)}%</span>'
                '</div>'
                f'{_source_link(observation["source_url"])}'
                '</article>'
            )

        opponent_portrait = RUNOFF_PORTRAITS_FR.get(matchup["opponent"])

        opponent_initials = "".join(
            part[0]
            for part in matchup["opponent"].replace("-", " ").split()
            if part
        )[:2].upper()

        if opponent_portrait:
            opponent_portrait_html = (
                '<span class="candidate-runoff-opponent-portrait" aria-hidden="true">'
                f'<span>{_h(opponent_initials)}</span>'
                f'<img src="{_h(opponent_portrait)}" alt="" '
                'loading="lazy" decoding="async" onerror="this.remove()">'
                '</span>'
            )
        else:
            opponent_portrait_html = (
                '<span class="candidate-runoff-opponent-portrait" aria-hidden="true">'
                f'<span>{_h(opponent_initials)}</span>'
                '</span>'
            )

        runoff_groups.append(
            '<section class="candidate-runoff-group">'
            '<div class="candidate-runoff-group-head">'
            f'{opponent_portrait_html}'
            '<div class="candidate-runoff-group-copy">'
            f'<h4>{_h(matchup["opponent"])}</h4>'
            f'<span>{_h(group_meta)}</span>'
            '</div>'
            '</div>'
            '<div class="candidate-runoff-side-labels" aria-hidden="true">'
            f'<span>{_h(candidate["candidate_name"])}</span>'
            f'<span>{_h(matchup["opponent"])}</span>'
            '</div>'
            f'<div class="candidate-runoff-card-grid">{"".join(observation_cards)}</div>'
            '</section>'
        )

    publisher_items = [
        '<div class="candidate-ranked-copy">'
        f'<strong>{_h(item["publisher"])}</strong>'
        f'<span>{_number(item["record_count"])} articles · {_percent(item["share"])}</span>'
        '</div><span class="candidate-ranked-bar" aria-hidden="true">'
        f'<span style="--rank-share:{item["share"]}"></span></span>'
        for item in media["top_publishers"]
    ]
    cluster_items = [
        '<div class="candidate-cluster-copy">'
        f'<strong>{_h(item["label"])}</strong>'
        f'<span>{_number(item["record_count"])} articles · {_number(item["publisher_count"])} éditeurs</span>'
        "</div>"
        for item in media["top_story_clusters"]
    ]
    def render_coverage_item(item: dict[str, Any]) -> str:
        return (
            '<article class="candidate-coverage-item">'
            f'<div class="candidate-kicker">{_h(SCOPE_LABELS_FR.get(item["coverage_scope"], item["coverage_scope"].upper()))} · {_h(item["publisher"])}</div>'
            f'<h4><a href="{_h(item["url"])}" target="_blank" rel="noopener noreferrer">{_h(item["headline"])}</a></h4>'
            f'<time datetime="{_h(item["published_at"])}">{_fr_date(item["published_at"])}</time>'
            "</article>"
        )

    coverage_items = [render_coverage_item(item) for item in media["latest_coverage"]]
    actualite_coverage_items = coverage_items[:5]
    actualite_article_count = len(actualite_coverage_items)
    actualite_article_label = (
        f"{actualite_article_count} article"
        + ("" if actualite_article_count == 1 else "s")
    )
    actualite_coverage_html = (
        '<ol class="candidate-evidence-list">'
        + "".join(f"<li>{item}</li>" for item in actualite_coverage_items)
        + "</ol>"
        if actualite_coverage_items
        else '<div class="candidate-empty-state"><strong>Aucun article publié</strong><span>Les derniers articles associés à la candidate apparaîtront ici.</span></div>'
    )

    review_items = []
    for review in payload["accountability"]["reviews"]:
        relationship_label = "PAR" if review["relationship"] == "by" else "À PROPOS"
        review_items.append(
            '<article class="candidate-review-item">'
            f'<div class="candidate-review-tag is-{_h(review["relationship"])}">{relationship_label}</div>'
            f'<h4>{_h(review["claim_text"])}</h4>'
            f'<p class="candidate-review-rating">{_h(review["rating"])}</p>'
            '<div class="candidate-meta">'
            f'<span>{_h(review["publisher_name"])}</span>'
            f'<time datetime="{_h(review["review_date"])}">{_fr_date(review["review_date"])}</time>'
            f'{_source_link(review["review_url"])}'
            "</div></article>"
        )

    def render_event(event: dict[str, Any]) -> str:
        place = " · ".join(
            part for part in (event.get("location_name"), event.get("locality")) if part
        )
        source = event.get("source")
        return (
            '<article class="candidate-event-item">'
            f'<time datetime="{_h(event["scheduled_start"])}">{_fr_date(event["scheduled_start"])}</time>'
            f'<div><div class="candidate-kicker">{_h(EVENT_TYPE_LABELS_FR.get(event["event_type"], event["event_type"].replace("_", " ").upper()))}</div>'
            f'<h4>{_h(event["title"])}</h4>'
            f'<p>{_h(place or event.get("organization") or "Lieu non publié")}</p></div>'
            + (_source_link(source["url"], source["publisher"] + " ↗") if source else "")
            + "</article>"
        )

    actualite_upcoming_events = payload["events"]["upcoming"][:5]
    actualite_recent_events = payload["events"]["recent"][
        : 5 - len(actualite_upcoming_events)
    ]
    actualite_events = actualite_upcoming_events + actualite_recent_events
    actualite_event_meta_parts = []
    if actualite_upcoming_events:
        actualite_event_meta_parts.append(f"{len(actualite_upcoming_events)} à venir")
    if actualite_recent_events:
        recent_count = len(actualite_recent_events)
        actualite_event_meta_parts.append(
            f"{recent_count} récent" + ("" if recent_count == 1 else "s")
        )
    actualite_event_meta = " · ".join(actualite_event_meta_parts)
    actualite_events_html = (
        '<div class="candidate-actualite-event-feed">'
        + "".join(render_event(item) for item in actualite_events)
        + "</div>"
        if actualite_events
        else '<div class="candidate-empty-state"><strong>Aucun événement publié</strong><span>Les événements vérifiés apparaîtront ici dès qu’ils seront disponibles.</span></div>'
    )
    upcoming_html = "".join(render_event(item) for item in payload["events"]["upcoming"])
    recent_html = "".join(render_event(item) for item in payload["events"]["recent"])
    if not upcoming_html:
        upcoming_html = '<div class="candidate-empty-state"><strong>Aucun événement à venir vérifié</strong><span>Les événements apparaîtront ici dès publication d’une source admissible.</span></div>'
    if not recent_html:
        recent_html = '<div class="candidate-empty-state"><strong>Aucun événement récent</strong><span>Aucune activité récente n’est disponible dans l’archive publiée.</span></div>'

    evidence = payload["accountability"]["candidacy_evidence"]
    agenda_current = payload["agenda"]["current"]
    agenda_cumulative = payload["agenda"]["since_tracking"]
    agenda_topic_order = [
        topic["id"]
        for topic in sorted(
            agenda_current["topics"],
            key=lambda item: (-item["share"], item["id"]),
        )
    ]
    agenda_current_period = _agenda_count_label(
        agenda_current["day_count"], "dernier jour", "derniers jours"
    )
    agenda_current_topics = _render_topic_profile(
        agenda_current,
        agenda_topic_order,
        agenda_current_period,
        "current",
    )
    agenda_cumulative_topics = _render_topic_profile(
        agenda_cumulative,
        agenda_topic_order,
        "depuis le début du suivi",
        "cumulative",
    )
    agenda_current_meta = (
        _agenda_count_label(
            agenda_current["association_count"], "association", "associations"
        )
        + " · "
        + _agenda_count_label(agenda_current["day_count"], "jour", "jours")
    )
    agenda_cumulative_meta = (
        _agenda_count_label(
            agenda_cumulative["association_count"], "association", "associations"
        )
        + " · "
        + _agenda_count_label(agenda_cumulative["day_count"], "jour", "jours")
    )
    source_dates = payload["freshness"]["candidate_signal_evidence_dates"]

    document = f'''<!doctype html>
<html lang="fr" data-page-candidate-id="{CANDIDATE_ID}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta name="description" content="Dossier sourcé de Marine Le Pen pour l’élection présidentielle française de 2027 : sondages, couverture médiatique, agenda, vérifications et attention publique.">
  <meta name="theme-color" content="#050b14">
  <meta name="color-scheme" content="dark">
  <title>Marine Le Pen — France 2027 Signal Lab</title>
  <link rel="stylesheet" href="/assets/fr27-ui.css">
  <link rel="stylesheet" href="/assets/candidate-page-shell.css">
  <link rel="stylesheet" href="/assets/candidate-page.css">
  <script src="/assets/fr27-ui.js" defer></script>
  <script src="/assets/candidate-page.js" defer></script>
</head>
<body class="candidate-page">
  <main class="candidate-shell">
    <header class="candidate-masthead" aria-label="France 2027 Signal Lab">
      <a class="candidate-brand" href="/" aria-label="France 2027 Signal Lab — accueil">
        <span class="candidate-mark" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" focusable="false"><rect x="1" y="1" width="30" height="30" rx="8" fill="#071522"/><path d="M6 16A10 10 0 0 1 16 6M26 16A10 10 0 0 1 16 26" fill="none" stroke="#268cff" stroke-width="2" stroke-linecap="round"/><path d="M10 16A6 6 0 0 1 16 10M22 16A6 6 0 0 1 16 22" fill="none" stroke="#35d5ff" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="16" r="2.5" fill="#35d5ff"/></svg></span>
        <span class="candidate-brand-copy"><strong>FRANCE 2027 <em>SIGNAL LAB</em></strong><small>Signaux sourcés de la présidentielle française.</small></span>
      </a>
      <div class="candidate-masthead-tools">
        <nav class="candidate-language" aria-label="Langue de l’interface"><a href="/candidates/marine-le-pen/" lang="fr" hreflang="fr" aria-label="Français" aria-current="page">FR</a><span aria-hidden="true">|</span><a href="/en/" lang="en" hreflang="en" aria-label="English" title="Tableau de bord anglais">EN</a></nav>
        <div class="candidate-countdown" data-countdown aria-label="Compte à rebours avant le premier tour">
          <span class="candidate-countdown-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><rect x="4" y="6" width="16" height="14" rx="2"></rect><path d="M8 3v5M16 3v5M4 10h16"></path><path d="M8 14h2M12 14h2M16 14h1M8 17h2M12 17h2"></path></svg></span>
          <div class="candidate-countdown-copy"><strong class="candidate-countdown-value">—</strong><div class="candidate-countdown-text"><div class="candidate-countdown-line"><span class="candidate-countdown-unit">jours</span><span class="candidate-countdown-label">avant le premier tour</span></div><div class="candidate-countdown-date"><span>18 avr. 2027</span><span class="candidate-tooltip-mark" aria-hidden="true">i</span></div></div></div>
        </div>
      </div>
    </header>

    <nav class="candidate-breadcrumb" aria-label="Fil d’Ariane"><a href="/#candidates">CANDIDATS</a><span aria-hidden="true">/</span><span aria-current="page">MARINE LE PEN</span></nav>

    <section class="candidate-dossier" aria-labelledby="candidate-name">
      <img class="candidate-portrait" src="{_h(candidate["portrait_path"])}" alt="Portrait illustré de Marine Le Pen" width="160" height="160">
      <div class="candidate-dossier-copy">
        <div class="candidate-eyebrow">DOSSIER CANDIDAT</div>
        <h1 id="candidate-name">{_h(candidate["candidate_name"])}</h1>
        <div class="candidate-status-row"><span class="candidate-status">DÉCLARÉE</span><span>Statut vérifié au {_fr_date(candidate["status_as_of"])}</span></div>
        <p>Synthèse descriptive des données publiées par France 2027 Signal Lab. Aucune moyenne · aucune prévision · aucun conseil de vote.</p>
      </div>
      <dl class="candidate-dossier-metrics">
        <div><dt>DONNÉES DE SONDAGE</dt><dd>{poll_headline}</dd><small>{_h(current_poll["pollster"])} · terrain du {_fr_date(current_poll["fieldwork_start"])} au {_fr_date(current_poll["fieldwork_end"])}</small></div>
        <div><dt>MEDIA PULSE</dt><dd>{_percent(dossier["media_pulse"]["share"])}</dd><small>part de la couverture élection + campagne, pas un indicateur de soutien</small></div>
        <div><dt>ARTICLES</dt><dd>{_number(dossier["media_pulse"]["record_count"])}</dd><small>articles · {_number(dossier["media_pulse"]["active_day_count"])} jours actifs</small></div>
        <div><dt>ÉDITEURS</dt><dd>{_number(dossier["media_pulse"]["publisher_count"])}</dd><small>sur la fenêtre courante de 7 jours</small></div>
      </dl>
    </section>

    <nav class="candidate-local-nav" aria-label="Sections du dossier">
      <a href="#now">ACTUALITÉ</a><a href="#polling">SONDAGES</a><a href="#media">MÉDIAS</a><a href="#agenda">AGENDA</a><a href="#scrutiny">VÉRIFICATIONS</a><a href="#attention">ATTENTION</a><a href="#events">ÉVÉNEMENTS</a>
    </nav>

    <section class="candidate-section" id="now" aria-labelledby="now-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="now-title">ACTUALITÉ</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="now-note">i</button><span class="candidate-section-tooltip" id="now-note" role="tooltip">Derniers articles, événements et changements sourcés.</span></span></div></header>
      <div class="candidate-now-grid">
        <article class="candidate-panel candidate-latest-news"><div class="candidate-panel-head"><h3>DERNIÈRES ACTUALITÉS</h3><span>{actualite_article_label}</span></div><div class="candidate-panel-body">{actualite_coverage_html}</div></article>
        <article class="candidate-panel candidate-actualite-events"><div class="candidate-panel-head"><h3>ÉVÉNEMENTS</h3>{f'<span>{actualite_event_meta}</span>' if actualite_event_meta else ''}</div><div class="candidate-panel-body">{actualite_events_html}</div></article>
        <article class="candidate-panel candidate-recent-changes"><div class="candidate-panel-head"><h3>CE QUI A CHANGÉ</h3><span>{len(change_items)} éléments</span></div><div class="candidate-panel-body"><div class="candidate-ledger">{"".join(change_items)}</div></div></article>
      </div>
    </section>

    <section class="candidate-section" id="polling" aria-labelledby="polling-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="polling-title">SONDAGES</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="polling-note">i</button><span class="candidate-section-tooltip" id="polling-note" role="tooltip">Scores publiés par hypothèse. Aucune moyenne, aucun lissage ni interpolation.</span></span></div></header>
      <div class="candidate-polling-grid">
        <article class="candidate-panel candidate-current-poll"><div class="candidate-panel-head"><h3>DERNIÈRE VAGUE</h3></div><div class="candidate-panel-body"><div class="candidate-poll-readout"><strong>{poll_range}</strong><span>{poll_hypotheses}</span></div><p>Fourchette des scores publiés pour Marine Le Pen dans les cinq hypothèses testées lors de la dernière vague. France 2027 Signal Lab n’en calcule pas de moyenne.</p><dl class="candidate-compact-facts"><div><dt>Institut</dt><dd>{_h(current_poll["pollster"])}</dd></div><div><dt>Échantillon</dt><dd>{_number(current_poll["sample_size"])}</dd></div><div><dt>Terrain</dt><dd>{_fr_date(current_poll["fieldwork_start"])} — {_fr_date(current_poll["fieldwork_end"])}</dd></div></dl>{_source_link(current_poll["source_urls"][0], "Voir la source du sondage ↗")}</div></article>
        <article class="candidate-panel candidate-chart-panel candidate-poll-history-panel"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>HISTORIQUE DU PREMIER TOUR</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur l’historique du premier tour" aria-describedby="poll-history-note">i</button><span class="candidate-section-tooltip" id="poll-history-note" role="tooltip">Chaque marque représente une observation publiée. Une barre verticale indique la fourchette entre hypothèses lorsqu’elle existe. Aucune moyenne, aucun lissage ni interpolation.</span></span></div><span>{_number(payload["polling"]["first_round_history"]["observation_count"])} vagues</span></div><div class="candidate-panel-body"><div class="candidate-chart candidate-poll-history-chart" data-chart="poll-history" role="group" aria-label="Historique des scores publiés au premier tour de Marine Le Pen"><p class="candidate-chart-fallback">Du {_fr_date(payload["polling"]["first_round_history"]["period_start"])} au {_fr_date(payload["polling"]["first_round_history"]["period_end"])}. Activez JavaScript pour la visualisation interactive.</p></div></div></article>
      </div>
      <article class="candidate-panel candidate-runoff-panel"><div class="candidate-panel-head candidate-runoff-panel-head"><div class="candidate-panel-title-row"><h3>DUELS DE SECOND TOUR TESTÉS</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur les duels de second tour testés" aria-describedby="runoff-history-note">i</button><span class="candidate-section-tooltip" id="runoff-history-note" role="tooltip">Pour chaque duel, France 2027 Signal Lab affiche au maximum les trois observations les plus récentes, classées par fin de terrain. Les observations plus anciennes restent dans le corpus source. Aucune moyenne ni interpolation n’est calculée.</span></span></div><span>{runoff_header_meta}</span></div><div class="candidate-panel-body candidate-runoff-groups">{"".join(runoff_groups)}</div><p class="candidate-panel-foot">Uniquement les configurations effectivement testées et publiées. Aucune moyenne n’est calculée.</p></article>
    </section>

    <section class="candidate-section" id="media" aria-labelledby="media-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="media-title">MEDIA PULSE &amp; COUVERTURE</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="media-note">i</button><span class="candidate-section-tooltip" id="media-note" role="tooltip">Visibilité dans la couverture suivie : volume, éditeurs, composition et concentration.</span></span></div></header>
      <div class="candidate-media-grid">
        <article class="candidate-panel candidate-media-summary"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>MEDIA PULSE</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Définition de Media Pulse" aria-describedby="media-pulse-note">i</button><span class="candidate-section-tooltip" id="media-pulse-note" role="tooltip">Media Pulse mesure la part des articles associés à Marine Le Pen dans les périmètres « élection » et « campagne ». Il ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote.</span></span></div><span>7 derniers jours publiés</span></div><div class="candidate-panel-body"><div class="candidate-media-readout"><strong>{_percent(media["summary"]["share"])}</strong><span>PART DE LA COUVERTURE ÉLECTION + CAMPAGNE</span></div><p>Part des articles associés à Marine Le Pen dans les périmètres « élection » et « campagne ».</p><div class="candidate-stat-grid"><div><strong>{_number(media["summary"]["record_count"])}</strong><span>articles</span></div><div><strong>{_number(media["summary"]["publisher_count"])}</strong><span>éditeurs</span></div><div><strong>{_number(media["summary"]["story_cluster_count"])}</strong><span>groupes narratifs</span></div><div><strong>{_number(media["summary"]["active_day_count"])}</strong><span>jours actifs</span></div></div></div></article>
        <article class="candidate-panel candidate-chart-panel candidate-media-history-panel"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>TENDANCE RÉCENTE DE COUVERTURE</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur la tendance récente de couverture" aria-describedby="media-history-note">i</button><span class="candidate-section-tooltip" id="media-history-note" role="tooltip">Part quotidienne des articles du périmètre « élection + campagne » associés à Marine Le Pen. La série couvre 29 jours UTC complets et ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote.</span></span></div><span>29 jours complets · UTC</span></div><div class="candidate-panel-body"><div class="candidate-chart candidate-media-history-chart" data-chart="media-history" role="group" aria-label="Historique récent de la part quotidienne de couverture de Marine Le Pen"><p class="candidate-chart-fallback">Historique publié du {_fr_date(media["recent_history"][0]["date"])} au {_fr_date(media["recent_history"][-1]["date"])}.</p></div></div></article>
        <article class="candidate-panel candidate-media-structure-panel"><div class="candidate-panel-head"><h3>STRUCTURE DE LA COUVERTURE</h3></div><div class="candidate-panel-body"><div class="candidate-media-structure"><section class="candidate-media-structure-module candidate-media-scope-module"><h4>PÉRIMÈTRE</h4><div class="candidate-media-scope-grid"><div class="candidate-media-scope-item candidate-media-scope-election"><div class="candidate-media-scope-head"><span>ÉLECTION</span><strong>{_percent(media["summary"]["scope_shares"]["election"])}</strong></div><span class="candidate-media-scope-meta">{_number(media["summary"]["scope_counts"]["election"])} articles</span><span class="candidate-media-structure-track" aria-hidden="true"><span style="--structure-share:{media["summary"]["scope_shares"]["election"]}"></span></span></div><div class="candidate-media-scope-item candidate-media-scope-campaign"><div class="candidate-media-scope-head"><span>CAMPAGNE</span><strong>{_percent(media["summary"]["scope_shares"]["campaign"])}</strong></div><span class="candidate-media-scope-meta">{_number(media["summary"]["scope_counts"]["campaign"])} articles</span><span class="candidate-media-structure-track" aria-hidden="true"><span style="--structure-share:{media["summary"]["scope_shares"]["campaign"]}"></span></span></div></div></section><div class="candidate-media-structure-lower"><section class="candidate-media-structure-module"><h4>PLACEMENT DE LA MENTION</h4><div class="candidate-media-mention-grid"><div><span>Dans le titre</span><strong>{_number(media["summary"]["headline_match_count"])}</strong></div><div><span>Résumé uniquement</span><strong>{_number(media["summary"]["summary_only_match_count"])}</strong></div></div></section><section class="candidate-media-structure-module candidate-media-concentration"><h4>PREMIER ÉDITEUR</h4><div class="candidate-media-leading-publisher candidate-media-leading-publisher-only"><strong>{_h(media["summary"]["concentration"]["leading_publisher"])}</strong></div></section></div></div></div></article>
        <article class="candidate-panel candidate-publishers-panel"><div class="candidate-panel-head"><h3>PRINCIPAUX ÉDITEURS</h3><span>{len(publisher_items)} éditeurs</span></div><div class="candidate-panel-body"><ol class="candidate-ranked-list">{"".join(f'<li>{item}</li>' for item in publisher_items)}</ol></div></article>
        <article class="candidate-panel candidate-story-clusters-panel"><div class="candidate-panel-head"><h3>PRINCIPAUX GROUPES NARRATIFS</h3><span>{len(cluster_items)} groupes</span></div><div class="candidate-panel-body candidate-scroll-feed">{"".join(cluster_items)}</div></article>
        <article class="candidate-panel candidate-latest-coverage"><div class="candidate-panel-head"><h3>DERNIÈRE COUVERTURE</h3><span>{len(coverage_items)} articles</span></div><div class="candidate-panel-body candidate-scroll-feed">{"".join(coverage_items)}</div></article>
      </div>
    </section>

    <section class="candidate-section" id="agenda" aria-labelledby="agenda-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="agenda-title">AGENDA &amp; ENJEUX</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="agenda-note">i</button><span class="candidate-section-tooltip" id="agenda-note" role="tooltip">Thèmes associés à Marine Le Pen dans la couverture suivie. Ils décrivent la composition de la couverture médiatique, pas les priorités ou positions de la candidate.</span></span></div></header>
      <div class="candidate-agenda-grid">
        <article class="candidate-panel candidate-agenda-profile candidate-agenda-profile-current"><div class="candidate-panel-head"><h3>PROFIL THÉMATIQUE · 30 J</h3><span>{agenda_current_meta}</span></div><div class="candidate-panel-body">{agenda_current_topics}</div></article>
        <article class="candidate-panel candidate-agenda-profile candidate-agenda-profile-cumulative"><div class="candidate-panel-head"><h3>PROFIL THÉMATIQUE · DEPUIS LE DÉBUT</h3><span>{agenda_cumulative_meta}</span></div><div class="candidate-panel-body">{agenda_cumulative_topics}</div></article>
        <article class="candidate-panel candidate-chart-panel candidate-agenda-history-panel"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>ÉVOLUTION DES THÈMES</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur l’évolution des thèmes" aria-describedby="agenda-history-note">i</button><span class="candidate-section-tooltip" id="agenda-history-note" role="tooltip">Comptages quotidiens des associations thématiques, sans moyenne, lissage ni interpolation.</span></span></div><span>{len(payload["agenda"]["evolution_topic_ids"])} thèmes principaux</span></div><div class="candidate-panel-body"><div class="candidate-chart candidate-agenda-history-chart" data-chart="agenda-history" role="group" aria-label="Évolution quotidienne des thèmes associés à Marine Le Pen"><p class="candidate-chart-fallback">Série quotidienne du {_fr_date(agenda_cumulative["period_start"])} au {_fr_date(agenda_cumulative["period_end"])}.</p></div></div></article>
      </div>
    </section>

    <section class="candidate-section" id="scrutiny" aria-labelledby="scrutiny-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="scrutiny-title">VÉRIFICATIONS</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="scrutiny-note">i</button><span class="candidate-section-tooltip" id="scrutiny-note" role="tooltip">Vérifications publiées et source confirmant le statut de candidature.</span></span></div></header>
      <div class="candidate-accountability-grid">
        <article class="candidate-panel"><div class="candidate-panel-head"><h3>AFFIRMATIONS SOUS EXAMEN</h3><span>{payload["accountability"]["review_count"]} vérifications</span></div><div class="candidate-panel-body"><div class="candidate-scrutiny-key"><span><b>PAR</b> — affirmation attribuée à Marine Le Pen</span><span><b>À PROPOS</b> — Marine Le Pen est mentionnée ; l’affirmation est attribuée à une autre personne</span></div>{_archive_items(review_items, initial=4, label="vérifications")}<p class="candidate-method-note">Le nombre de vérifications publiées ne mesure pas l’exactitude globale d’une personnalité politique.</p></div></article>
        <article class="candidate-panel"><div class="candidate-panel-head"><h3>STATUT DE CANDIDATURE</h3><span>DÉCLARÉE</span></div><div class="candidate-panel-body"><div class="candidate-evidence-status"><span aria-hidden="true"></span><strong>Statut confirmé</strong></div><h4>{_h(evidence["source_title"])}</h4><p>Cette source documente l’annonce publique de candidature enregistrée par France 2027 Signal Lab.</p><dl class="candidate-compact-facts"><div><dt>Source</dt><dd>{_h(evidence["source_publisher"])}</dd></div><div><dt>Date de la source</dt><dd>{_fr_date(evidence["source_date"])}</dd></div><div><dt>Statut vérifié au</dt><dd>{_fr_date(evidence["status_as_of"])}</dd></div></dl>{_source_link(evidence["source_url"], "Ouvrir la source ↗")}</div></article>
      </div>
    </section>

    <section class="candidate-section" id="attention" aria-labelledby="attention-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="attention-title">ATTENTION PUBLIQUE</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="attention-note">i</button><span class="candidate-section-tooltip" id="attention-note" role="tooltip">Pages vues de l’article Wikipédia en français. Ce signal ne mesure pas le soutien.</span></span></div></header>
      <div class="candidate-attention-grid">
        <article class="candidate-panel"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>PAGES VUES WIKIPÉDIA</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur les pages vues Wikipédia" aria-describedby="attention-summary-note">i</button><span class="candidate-section-tooltip" id="attention-summary-note" role="tooltip">Les pages vues Wikipédia mesurent la consultation de l’article. Elles ne mesurent ni soutien, ni sentiment, ni approbation, ni intention de vote.</span></span></div><span>pages vues</span></div><div class="candidate-panel-body"><div class="candidate-stat-grid is-large"><div><strong>{_number(attention["latest_7_views"])}</strong><span>7 derniers jours</span></div><div><strong>{_number(attention["latest_28_views"])}</strong><span>28 derniers jours</span></div><div><strong>{_number(attention["latest_7_peak_views"])}</strong><span>pic sur 7 jours</span></div><div><strong>{_number(attention["period_peak_views"])}</strong><span>pic de période</span></div></div>{_source_link(attention["wikipedia_article"]["url"], "Ouvrir l’article Wikipédia ↗")}</div></article>
        <article class="candidate-panel candidate-chart-panel"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>HISTORIQUE DES PAGES VUES</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur l’historique des pages vues" aria-describedby="attention-history-note">i</button><span class="candidate-section-tooltip" id="attention-history-note" role="tooltip">Pages vues quotidiennes de l’article Wikipédia en français. Des visites répétées peuvent être incluses.</span></span></div><span>{len(attention["daily_series"])} jours</span></div><div class="candidate-panel-body"><div class="candidate-chart" data-chart="attention-history" role="img" aria-label="Pages vues quotidiennes de l’article Wikipédia de Marine Le Pen"><p class="candidate-chart-fallback">Historique du {_fr_date(attention["daily_series"][0]["date"])} au {_fr_date(attention["daily_series"][-1]["date"])}.</p></div></div></article>
      </div>
    </section>

    <section class="candidate-section" id="events" aria-labelledby="events-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="events-title">ÉVÉNEMENTS</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="events-note">i</button><span class="candidate-section-tooltip" id="events-note" role="tooltip">Événements de campagne publiés associés à Marine Le Pen.</span></span></div></header>
      <div class="candidate-events-grid"><article class="candidate-panel"><div class="candidate-panel-head"><h3>ÉVÉNEMENTS À VENIR</h3><span>au {_fr_date(payload["events"]["reference_date"])}</span></div><div class="candidate-panel-body candidate-event-list">{upcoming_html}</div></article><article class="candidate-panel"><div class="candidate-panel-head"><h3>ÉVÉNEMENTS RÉCENTS</h3><span>historique récent</span></div><div class="candidate-panel-body candidate-event-list">{recent_html}</div></article></div>
    </section>

    <section class="candidate-section candidate-sources" id="sources" aria-labelledby="sources-title">
      <header class="candidate-section-head"><div class="candidate-section-title-row"><h2 id="sources-title">SOURCES &amp; MÉTHODOLOGIE</h2><span class="candidate-section-info-wrap"><button class="candidate-section-info" type="button" aria-label="Contexte de cette section" aria-describedby="sources-note">i</button><span class="candidate-section-tooltip" id="sources-note" role="tooltip">Définitions, périmètres, sources et dates de mise à jour.</span></span></div></header>
      <div class="candidate-sources-grid"><article class="candidate-panel"><div class="candidate-panel-head"><h3>DÉFINITIONS</h3></div><div class="candidate-panel-body"><dl class="candidate-definition-list"><div><dt>Données de sondage</dt><dd>Fourchette des scores publiés dans les différentes hypothèses d’une même vague. Aucune moyenne n’est calculée.</dd></div><div><dt>Media Pulse</dt><dd>Part de la couverture « élection + campagne » associée à la candidate. Ce n’est pas une mesure d’opinion ou de soutien.</dd></div><div><dt>Attention Wikipédia</dt><dd>Pages vues de l’article français. Ce n’est pas une mesure de soutien, de sentiment ou d’intention de vote.</dd></div><div><dt>PAR / À PROPOS</dt><dd>PAR désigne l’auteur enregistré de l’affirmation. À PROPOS désigne une candidate mentionnée dans une affirmation attribuée à autrui.</dd></div></dl></div></article><article class="candidate-panel"><div class="candidate-panel-head"><div class="candidate-panel-title-row"><h3>FRAÎCHEUR DES DONNÉES</h3><span class="candidate-section-info-wrap candidate-panel-info-wrap"><button class="candidate-section-info" type="button" aria-label="Informations sur la fraîcheur des données" aria-describedby="sources-freshness-note">i</button><span class="candidate-section-tooltip" id="sources-freshness-note" role="tooltip">Données de France 2027 Signal Lab validées aux dates indiquées ci-dessus. Aucune moyenne · aucune prévision · aucun conseil de vote.</span></span></div></div><div class="candidate-panel-body"><dl class="candidate-compact-facts"><div><dt>Sondages</dt><dd>{_fr_date(source_dates["polling"])}</dd></div><div><dt>Couverture</dt><dd>{_fr_date(payload["freshness"]["media_period_end"])}</dd></div><div><dt>Agenda</dt><dd>{_fr_date(payload["freshness"]["agenda_data_as_of"])}</dd></div><div><dt>Attention</dt><dd>{_fr_date(payload["freshness"]["attention_period_end"])}</dd></div><div><dt>Vérifications</dt><dd>{_fr_date(source_dates["scrutiny"])}</dd></div><div><dt>Candidature</dt><dd>{_fr_date(candidate["status_as_of"])}</dd></div></dl></div></article></div>
    </section>

    <footer id="candidate-app-hud" class="fr27-app-hud" data-expanded="true" aria-label="Dock système France 2027 Signal Lab">
      <button class="fr27-app-hud-toggle" id="fr27-app-hud-toggle" type="button" aria-expanded="true" aria-controls="fr27-app-hud-surface" aria-label="Réduire le dock système" data-fr27-tooltip="Réduire le dock système"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6.5 8.5 12 14l5.5-5.5"></path></svg></button>
      <div class="fr27-app-hud-surface" id="fr27-app-hud-surface">
        <div class="fr27-app-hud-content fr27-linear-console" aria-hidden="false">
          <section class="fr27-linear-zone fr27-zone-live" aria-label="Heure de Paris"><div class="fr27-zone-meta"><span>PARIS</span><span>/ <span id="fr27-hud-paris-zone">UTC+2</span></span></div><div class="fr27-zone-main fr27-live-main"><time id="fr27-hud-paris-time" datetime="">--:--:--</time><span id="fr27-hud-paris-date">—</span></div></section>
          <section class="fr27-linear-zone fr27-zone-countdown" aria-label="Compte à rebours électoral"><div class="fr27-zone-title">COMPTE À REBOURS</div><div class="fr27-zone-main fr27-countdown-main"><div class="fr27-countdown-value-row"><strong id="fr27-hud-countdown-days">—</strong><span class="fr27-countdown-unit">JOURS</span></div><time class="fr27-countdown-date" datetime="2027-04-18">18 AVR 2027</time></div></section>
          <section class="fr27-linear-zone fr27-zone-infra" aria-label="Univers de sources et sondages"><div class="fr27-zone-infra-body"><div class="fr27-source-main">
            <div class="fr27-source-stat"><strong id="fr27-hud-domains-value">{hud_metrics["domains"]}</strong><span class="fr27-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="8"></circle><path d="M4 12h16"></path><path d="M12 4c2.2 2.2 3.3 4.9 3.3 8s-1.1 5.8-3.3 8"></path><path d="M12 4c-2.2 2.2-3.3 4.9-3.3 8s1.1 5.8 3.3 8"></path></svg></span><span class="fr27-hud-label-with-info" id="fr27-hud-domains-info" data-fr27-tooltip="Domaines éditeurs approuvés configurés dans l’univers de sources FR27. Il s’agit du registre surveillé, pas du nombre d’éditeurs représentés dans les actualités électorales retenues." data-fr27-tooltip-affordance="term" tabindex="0">DOMAINES</span></div>
            <div class="fr27-source-stat"><strong id="fr27-hud-polls-value">{hud_metrics["poll_packages"]}</strong><span class="fr27-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="9" cy="8.5" r="3"></circle><path d="M3.5 19c.6-3.3 2.4-5 5.5-5s4.9 1.7 5.5 5"></path><path d="M16 6.5a2.7 2.7 0 0 1 0 5.4"></path><path d="M15.5 14c2.7.3 4.2 1.8 4.8 4.5"></path></svg></span><span class="fr27-hud-label-with-info" id="fr27-hud-polls-info" data-fr27-tooltip="Paquets de sondages de premier tour distincts dans le corpus chargé, et non instituts. Les hypothèses partageant institut, dates de terrain et taille d’échantillon comptent pour un paquet." data-fr27-tooltip-affordance="term" tabindex="0">SONDAGES</span></div>
          </div></div></section>
          <section class="fr27-linear-zone fr27-zone-dashboard" aria-label="Tableau de bord principal"><a class="fr27-dashboard-cta" href="https://france2027.app/"><span>TABLEAU DE BORD</span><strong>OUVRIR LE MONITEUR ↗</strong></a></section>
          <section class="fr27-linear-zone fr27-zone-utility" aria-label="Liens utilitaires"><div class="fr27-linear-actions">
            <a class="fr27-hud-command github" href="https://github.com/openeventbits/france-2027-signal-lab" target="_blank" rel="noreferrer" data-fr27-tooltip="Voir le dépôt" aria-label="Ouvrir le dépôt GitHub"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 .5a12 12 0 0 0-3.79 23.39c.6.11.82-.26.82-.58v-2.04c-3.34.73-4.04-1.42-4.04-1.42-.55-1.37-1.33-1.73-1.33-1.73-1.09-.74.08-.73.08-.73 1.2.08 1.83 1.21 1.83 1.21 1.08 1.82 2.82 1.29 3.5.99.11-.76.42-1.29.76-1.59-2.67-.3-5.48-1.31-5.48-5.84 0-1.29.47-2.34 1.23-3.16-.12-.3-.53-1.53.12-3.18 0 0 1.01-.32 3.3 1.21a11.6 11.6 0 0 1 6 0c2.29-1.53 3.3-1.21 3.3-1.21.65 1.65.24 2.88.12 3.18.77.82 1.23 1.87 1.23 3.16 0 4.54-2.81 5.54-5.49 5.84.43.37.81 1.09.81 2.19v3.25c0 .32.22.7.83.58A12 12 0 0 0 12 .5Z"></path></svg></a>
            <button type="button" id="fr27-hud-email-toggle" class="fr27-hud-command email" data-fr27-tooltip="Contact" aria-label="Contacter France 2027 Signal Lab" aria-haspopup="dialog" aria-controls="fr27-hud-contact-popover" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3.25" y="5.5" width="17.5" height="13" rx="1.7"></rect><path d="m4.6 7.1 7.4 5.55 7.4-5.55"></path></svg></button>
            <a id="fr27-hud-share" class="fr27-hud-command share" href="https://x.com/fr27signal" target="_blank" rel="noopener noreferrer" data-fr27-tooltip="FR27 sur X · @fr27signal" aria-label="FR27 sur X · @fr27signal"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" stroke="none" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.264 2.25H8.09l4.713 6.231zm-1.161 17.52h1.833L7.095 4.126H5.127z"></path></svg></a>
            <button type="button" id="fr27-hud-info-toggle" class="fr27-hud-command" aria-haspopup="dialog" aria-controls="fr27-hud-info-popover" aria-expanded="false" data-fr27-tooltip="À propos de France 2027 Signal Lab" aria-label="Informations sur le projet"><svg class="fr27-info-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.25"></circle><path d="M12 10.8v5"></path><path d="M12 7.7h.01"></path></svg></button>
          </div></section>
        </div>
        <div class="fr27-app-hud-rail" aria-hidden="true"><i></i></div>
      </div>
      <aside class="fr27-hud-contact-popover" id="fr27-hud-contact-popover" aria-hidden="true" aria-label="Contacter France 2027 Signal Lab"><div class="fr27-hud-contact-head"><strong>CONTACT</strong><span>EMAIL</span></div><div class="fr27-hud-contact-address">contact@france2027.app</div><button type="button" class="fr27-hud-contact-copy" id="fr27-hud-contact-copy" aria-live="polite">COPIER L’ADRESSE</button></aside>
      <aside class="fr27-hud-info-popover" id="fr27-hud-info-popover" aria-hidden="true" aria-label="Informations sur le projet"><div class="fr27-hud-info-head"><strong>FRANCE 2027 SIGNAL LAB</strong><span>INTERFACE PUBLIQUE DE SUIVI</span></div><p>Suivi sourcé de la présidentielle française de 2027 à partir de sondages, d’éléments de campagne, de médias et de données d’attention publique.</p><div class="fr27-hud-info-rules"><div class="fr27-hud-info-rule-line primary"><span>DONNÉES PUBLIQUES</span><span>LIÉES AUX SOURCES</span><span>DESCRIPTIF</span></div><div class="fr27-hud-info-rule-line boundary"><span>AUCUNE MOYENNE DE SONDAGES</span><span>AUCUNE PRÉVISION</span><span>AUCUN CONSEIL DE VOTE</span></div></div><small class="fr27-hud-info-independence">Projet indépendant · aucune affiliation avec les candidats, partis, instituts de sondage, éditeurs ou autorités publiques suivis.</small><small class="fr27-hud-info-note">Les portraits des candidates et candidats sont des illustrations générées par IA à des fins d’identification visuelle.</small><div class="fr27-hud-info-rights"><strong>DROITS &amp; LICENCES</strong><span>POLYFORM NC · CC BY-NC 4.0</span><a href="https://github.com/openeventbits/france-2027-signal-lab/blob/main/NOTICE" target="_blank" rel="noopener noreferrer" aria-label="Ouvrir les détails des droits et licences dans un nouvel onglet">DÉTAILS ↗</a></div></aside>
      <div class="visually-hidden">Données descriptives issues de sources publiques. Aucune moyenne. Aucune prévision. Aucun conseil de vote.</div>
    </footer>
  </main>
  <script id="candidate-reference-metadata" type="application/json">{{"candidate_id":"{CANDIDATE_ID}","data_url":"/candidates/marine-le-pen/data.json","schema_version":"{SCHEMA_VERSION}"}}</script>
</body>
</html>
'''
    return document.encode("utf-8")



# ----------------------------------------------------------------------
# Candidate-page localization contract.
#
# The factual projection is language-neutral. The locked French renderer
# remains the structural source; English presentation is derived only from
# known interface text and attributes. Source-originated h4 content and
# published fact-check ratings remain in their original language.
# ----------------------------------------------------------------------

CANDIDATE_LOCALES = {
    "fr": {
        "lang": "fr",
        "locale_tag": "fr-FR",
        "canonical": "https://france2027.app/candidates/marine-le-pen/",
        "peer": "/en/candidates/marine-le-pen/",
        "home": "/",
        "dashboard": "https://france2027.app/",
        "title": "Marine Le Pen — France 2027 Signal Lab",
        "description": (
            "Dossier sourcé de Marine Le Pen pour l’élection présidentielle "
            "française de 2027 : sondages, couverture médiatique, agenda, "
            "vérifications et attention publique."
        ),
    },
    "en": {
        "lang": "en",
        "locale_tag": "en-GB",
        "canonical": "https://france2027.app/en/candidates/marine-le-pen/",
        "peer": "/candidates/marine-le-pen/",
        "home": "/en/",
        "dashboard": "https://france2027.app/en/",
        "title": "Marine Le Pen — Candidate Dossier | France 2027 Signal Lab",
        "description": (
            "Source-linked Marine Le Pen candidate dossier for France's 2027 "
            "presidential election: polls, media coverage, agenda, scrutiny and "
            "public attention. No averages, no forecast, no voting advice."
        ),
    },
}


_CANDIDATE_TEXT_EN = {
    "Signaux sourcés de la présidentielle française.": "Source-linked signals from the French presidential race.",
    "CANDIDATS": "CANDIDATES",
    "DOSSIER CANDIDAT": "CANDIDATE DOSSIER",
    "DÉCLARÉE": "DECLARED",
    "ACTUALITÉ": "NEWS",
    "SONDAGES": "POLLS",
    "MÉDIAS": "MEDIA",
    "AGENDA": "AGENDA",
    "VÉRIFICATIONS": "SCRUTINY",
    "ATTENTION": "ATTENTION",
    "ÉVÉNEMENTS": "EVENTS",
    "DERNIÈRES ACTUALITÉS": "LATEST NEWS",
    "CE QUI A CHANGÉ": "WHAT CHANGED",
    "DERNIÈRE VAGUE": "LATEST WAVE",
    "HISTORIQUE DU PREMIER TOUR": "FIRST-ROUND HISTORY",
    "DUELS DE SECOND TOUR TESTÉS": "TESTED RUNOFFS",
    "MEDIA PULSE & COUVERTURE": "MEDIA PULSE & COVERAGE",
    "MEDIA PULSE": "MEDIA PULSE",
    "STRUCTURE DE LA COUVERTURE": "COVERAGE STRUCTURE",
    "PÉRIMÈTRE": "SCOPE",
    "ÉLECTION": "ELECTION",
    "CAMPAGNE": "CAMPAIGN",
    "PLACEMENT DE LA MENTION": "MENTION PLACEMENT",
    "Dans le titre": "In headline",
    "Résumé uniquement": "Summary only",
    "PREMIER ÉDITEUR": "TOP PUBLISHER",
    "PRINCIPAUX ÉDITEURS": "TOP PUBLISHERS",
    "PRINCIPAUX GROUPES NARRATIFS": "TOP STORY CLUSTERS",
    "DERNIÈRE COUVERTURE": "LATEST COVERAGE",
    "AGENDA & ENJEUX": "AGENDA & ISSUES",
    "PROFIL THÉMATIQUE · 30 J": "TOPIC PROFILE · 30D",
    "PROFIL THÉMATIQUE · DEPUIS LE DÉBUT": "TOPIC PROFILE · SINCE START",
    "ÉVOLUTION DES THÈMES": "TOPIC EVOLUTION",
    "AFFIRMATIONS SOUS EXAMEN": "CLAIMS UNDER SCRUTINY",
    "STATUT DE CANDIDATURE": "CANDIDACY STATUS",
    "PAR": "BY",
    "À PROPOS": "ABOUT",
    "Statut confirmé": "Status confirmed",
    "ATTENTION PUBLIQUE": "PUBLIC ATTENTION",
    "PAGES VUES WIKIPÉDIA": "WIKIPEDIA PAGEVIEWS",
    "HISTORIQUE DES PAGES VUES": "PAGEVIEW HISTORY",
    "pages vues": "pageviews",
    "ÉVÉNEMENTS À VENIR": "UPCOMING EVENTS",
    "ÉVÉNEMENTS RÉCENTS": "RECENT EVENTS",
    "historique récent": "recent history",
    "SOURCES & MÉTHODOLOGIE": "SOURCES & METHODOLOGY",
    "DÉFINITIONS": "DEFINITIONS",
    "Données de sondage": "Polling data",
    "Attention Wikipédia": "Wikipedia attention",
    "PAR / À PROPOS": "BY / ABOUT",
    "FRAÎCHEUR DES DONNÉES": "DATA FRESHNESS",
    "Sondages": "Polls",
    "Couverture": "Coverage",
    "Vérifications": "Scrutiny",
    "Candidature": "Candidacy",
    "COMPTE À REBOURS": "COUNTDOWN",
    "JOURS": "DAYS",
    "DOMAINES": "DOMAINS",
    "TABLEAU DE BORD": "DASHBOARD",
    "OUVRIR LE MONITEUR ↗": "OPEN THE MONITOR ↗",
    "CONTACT": "CONTACT",
    "EMAIL": "EMAIL",
    "COPIER L’ADRESSE": "COPY ADDRESS",
    "INTERFACE PUBLIQUE DE SUIVI": "PUBLIC MONITORING INTERFACE",
    "DONNÉES PUBLIQUES": "PUBLIC DATA",
    "LIÉES AUX SOURCES": "SOURCE-LINKED",
    "DESCRIPTIF": "DESCRIPTIVE",
    "AUCUNE MOYENNE DE SONDAGES": "NO POLLING AVERAGE",
    "AUCUNE PRÉVISION": "NO FORECAST",
    "AUCUN CONSEIL DE VOTE": "NO VOTING ADVICE",
    "DROITS & LICENCES": "RIGHTS & LICENCES",
    "DÉTAILS ↗": "DETAILS ↗",
    "ARTICLES": "ARTICLES",
    "ÉDITEURS": "PUBLISHERS",
    "DÉPLACEMENT": "VISIT",
    "DÉBAT": "DEBATE",
    "LANCEMENT DE CAMPAGNE": "CAMPAIGN LAUNCH",
    "AUTRE": "OTHER",
    "VÉRIFICATION": "SCRUTINY",
    "Institut": "Pollster",
    "Échantillon": "Sample",
    "Terrain": "Fieldwork",
    "Source": "Source",
    "Date de la source": "Source date",
    "Statut vérifié au": "Status verified as of",
    "Réduire": "Show less",
    "Économie et finances publiques": "Economy and public finances",
    "Travail, pouvoir d’achat et retraites": "Work, purchasing power and pensions",
    "Immigration, identité et laïcité": "Immigration, identity and secularism",
    "Sécurité et justice": "Security and justice",
    "Santé, éducation et services publics": "Health, education and public services",
    "Climat, énergie et agriculture": "Climate, energy and agriculture",
    "Europe, défense et affaires étrangères": "Europe, defence and foreign affairs",
    "Institutions, démocratie et territoires": "Institutions, democracy and territories",

    "Derniers articles, événements et changements sourcés.":
        "Latest source-linked articles, events and changes.",
    "Scores publiés par hypothèse. Aucune moyenne, aucun lissage ni interpolation.":
        "Published scores by hypothesis. No average, smoothing or interpolation.",
    "Visibilité dans la couverture suivie : volume, éditeurs, composition et concentration.":
        "Visibility in monitored coverage: volume, publishers, composition and concentration.",
    "Thèmes associés à Marine Le Pen dans la couverture suivie. Ils décrivent la composition de la couverture médiatique, pas les priorités ou positions de la candidate.":
        "Topics associated with Marine Le Pen in monitored coverage. They describe the composition of media coverage, not the candidate's priorities or positions.",
    "Vérifications publiées et source confirmant le statut de candidature.":
        "Published reviews and the source confirming candidacy status.",
    "Pages vues de l’article Wikipédia en français. Ce signal ne mesure pas le soutien.":
        "Pageviews of the French-language Wikipedia article. This signal does not measure support.",
    "Événements de campagne publiés associés à Marine Le Pen.":
        "Published campaign events associated with Marine Le Pen.",
    "Définitions, périmètres, sources et dates de mise à jour.":
        "Definitions, scope, sources and update dates.",

    "Fourchette des scores publiés pour Marine Le Pen dans les cinq hypothèses testées lors de la dernière vague. France 2027 Signal Lab n’en calcule pas de moyenne.":
        "Range of published Marine Le Pen scores across the five hypotheses tested in the latest wave. France 2027 Signal Lab does not calculate an average.",
    "Chaque marque représente une observation publiée. Une barre verticale indique la fourchette entre hypothèses lorsqu’elle existe. Aucune moyenne, aucun lissage ni interpolation.":
        "Each mark represents a published observation. A vertical bar shows the range across hypotheses when one exists. No average, smoothing or interpolation.",
    "Pour chaque duel, France 2027 Signal Lab affiche au maximum les trois observations les plus récentes, classées par fin de terrain. Les observations plus anciennes restent dans le corpus source. Aucune moyenne ni interpolation n’est calculée.":
        "For each runoff, France 2027 Signal Lab shows at most the three most recent observations, ordered by fieldwork end date. Older observations remain in the source corpus. No average or interpolation is calculated.",
    "Uniquement les configurations effectivement testées et publiées. Aucune moyenne n’est calculée.":
        "Only configurations that were actually tested and published. No average is calculated.",

    "Media Pulse mesure la part des articles associés à Marine Le Pen dans les périmètres « élection » et « campagne ». Il ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote.":
        "Media Pulse measures Marine Le Pen's share of associated articles within the election and campaign scopes. It does not measure support, approval, sentiment or voting intention.",
    "PART DE LA COUVERTURE ÉLECTION + CAMPAGNE":
        "SHARE OF ELECTION + CAMPAIGN COVERAGE",
    "Part des articles associés à Marine Le Pen dans les périmètres « élection » et « campagne ».":
        "Share of articles associated with Marine Le Pen within the election and campaign scopes.",
    "Part quotidienne des articles du périmètre « élection + campagne » associés à Marine Le Pen. La série couvre 29 jours UTC complets et ne mesure ni soutien, ni approbation, ni sentiment, ni intention de vote.":
        "Daily share of election + campaign articles associated with Marine Le Pen. The series covers 29 complete UTC days and does not measure support, approval, sentiment or voting intention.",

    "Comptages quotidiens des associations thématiques, sans moyenne, lissage ni interpolation.":
        "Daily counts of topic associations, with no average, smoothing or interpolation.",
    "Le nombre de vérifications publiées ne mesure pas l’exactitude globale d’une personnalité politique.":
        "The number of published reviews does not measure a political figure's overall accuracy.",
    "Cette source documente l’annonce publique de candidature enregistrée par France 2027 Signal Lab.":
        "This source documents the public candidacy announcement recorded by France 2027 Signal Lab.",
    "Les pages vues Wikipédia mesurent la consultation de l’article. Elles ne mesurent ni soutien, ni sentiment, ni approbation, ni intention de vote.":
        "Wikipedia pageviews measure visits to the article. They do not measure support, sentiment, approval or voting intention.",
    "Pages vues quotidiennes de l’article Wikipédia en français. Des visites répétées peuvent être incluses.":
        "Daily pageviews of the French-language Wikipedia article. Repeat visits may be included.",

    "Fourchette des scores publiés dans les différentes hypothèses d’une même vague. Aucune moyenne n’est calculée.":
        "Range of published scores across the different hypotheses in the same wave. No average is calculated.",
    "Part de la couverture « élection + campagne » associée à la candidate. Ce n’est pas une mesure d’opinion ou de soutien.":
        "Share of election + campaign coverage associated with the candidate. It is not a measure of opinion or support.",
    "Pages vues de l’article français. Ce n’est pas une mesure de soutien, de sentiment ou d’intention de vote.":
        "Pageviews of the French-language article. This is not a measure of support, sentiment or voting intention.",
    "PAR désigne l’auteur enregistré de l’affirmation. À PROPOS désigne une candidate mentionnée dans une affirmation attribuée à autrui.":
        "BY identifies the recorded author of the claim. ABOUT identifies a candidate mentioned in a claim attributed to someone else.",
    "Données de France 2027 Signal Lab validées aux dates indiquées ci-dessus. Aucune moyenne · aucune prévision · aucun conseil de vote.":
        "France 2027 Signal Lab data validated as of the dates shown above. No average · no forecast · no voting advice.",

    "Aucun article publié": "No published articles",
    "Les derniers articles associés à la candidate apparaîtront ici.":
        "The latest articles associated with the candidate will appear here.",
    "Aucun événement publié": "No published events",
    "Les événements vérifiés apparaîtront ici dès qu’ils seront disponibles.":
        "Verified events will appear here when available.",
    "Aucun événement à venir vérifié": "No verified upcoming events",
    "Les événements apparaîtront ici dès publication d’une source admissible.":
        "Events will appear here when an eligible source is published.",
    "Aucun événement récent": "No recent events",
    "Aucune activité récente n’est disponible dans l’archive publiée.":
        "No recent activity is available in the published archive.",
    "Lieu non publié": "Location not published",

    "Voir la source du sondage ↗": "View poll source ↗",
    "Ouvrir la source ↗": "Open source ↗",
    "Ouvrir l’article Wikipédia ↗": "Open Wikipedia article ↗",

    "Domaines éditeurs approuvés configurés dans l’univers de sources FR27. Il s’agit du registre surveillé, pas du nombre d’éditeurs représentés dans les actualités électorales retenues.":
        "Approved publisher domains configured in the FR27 source universe. This is the monitored source registry, not the number of publishers represented in accepted election news.",
    "Paquets de sondages de premier tour distincts dans le corpus chargé, et non instituts. Les hypothèses partageant institut, dates de terrain et taille d’échantillon comptent pour un paquet.":
        "Distinct first-round poll packages in the loaded poll corpus, not pollsters. Reported hypotheses sharing the same pollster, fieldwork dates and sample size count as one poll package.",
    "Suivi sourcé de la présidentielle française de 2027 à partir de sondages, d’éléments de campagne, de médias et de données d’attention publique.":
        "Source-linked monitoring of France's 2027 presidential election using polls, campaign activity, media coverage and public-attention data.",
    "Projet indépendant · aucune affiliation avec les candidats, partis, instituts de sondage, éditeurs ou autorités publiques suivis.":
        "Independent project · no affiliation with the monitored candidates, parties, pollsters, publishers or public authorities.",
    "Les portraits des candidates et candidats sont des illustrations générées par IA à des fins d’identification visuelle.":
        "Candidate portraits are AI-generated illustrations used for visual identification.",
    "Données descriptives issues de sources publiques. Aucune moyenne. Aucune prévision. Aucun conseil de vote.":
        "Descriptive data from public sources. No average. No forecast. No voting advice.",
}


_CANDIDATE_TEXT_EN.update({
    "avant le premier tour": "before the first round",
    "Synthèse descriptive des données publiées par France 2027 Signal Lab. Aucune moyenne · aucune prévision · aucun conseil de vote.": (
        "Descriptive summary of data published by France 2027 Signal Lab. "
        "No average · no forecast · no voting advice."
    ),
    "DONNÉES DE SONDAGE": "POLLING DATA",
    "part de la couverture élection + campagne, pas un indicateur de soutien": (
        "share of election + campaign coverage, not a measure of support"
    ),
    "éditeurs": "publishers",
    "groupes narratifs": "story clusters",
    "jours actifs": "active days",
    "TENDANCE RÉCENTE DE COUVERTURE": "RECENT COVERAGE TREND",
})


_CANDIDATE_ATTR_EN = {
    "France 2027 Signal Lab — accueil": "France 2027 Signal Lab — home",
    "Langue de l’interface": "Interface language",
    "Compte à rebours avant le premier tour": "First-round election countdown",
    "Fil d’Ariane": "Breadcrumb",
    "Portrait illustré de Marine Le Pen": "Illustrated portrait of Marine Le Pen",
    "Sections du dossier": "Dossier sections",
    "Contexte de cette section": "Section context",
    "Informations sur l’historique du premier tour": "First-round history information",
    "Informations sur les duels de second tour testés": "Tested runoff information",
    "Définition de Media Pulse": "Media Pulse definition",
    "Informations sur la tendance récente de couverture": "Recent coverage trend information",
    "Informations sur l’évolution des thèmes": "Topic evolution information",
    "Informations sur les pages vues Wikipédia": "Wikipedia pageview information",
    "Informations sur l’historique des pages vues": "Pageview history information",
    "Informations sur la fraîcheur des données": "Data freshness information",
    "Dock système France 2027 Signal Lab": "France 2027 Signal Lab system dock",
    "Heure de Paris": "Paris time",
    "Compte à rebours électoral": "Election countdown",
    "Univers de sources et sondages": "Source and polling universe",
    "Tableau de bord principal": "Main dashboard",
    "Ouvrir le dépôt GitHub": "Open the GitHub repository",
    "Voir le dépôt": "View repository",
    "Contacter France 2027 Signal Lab": "Contact France 2027 Signal Lab",
    "À propos de France 2027 Signal Lab": "About France 2027 Signal Lab",
    "Informations sur le projet": "Project information",
    "Ouvrir les détails des droits et licences dans un nouvel onglet":
        "Open rights and licensing details in a new tab",
    "Réduire le dock système": "Collapse system dock",
    "Développer le dock système": "Expand system dock",
    "Afficher plus de vérifications": "Show more reviews",
    "Réduire": "Show less",
}


_CANDIDATE_ATTR_EN.update({
    "Historique des scores publiés au premier tour de Marine Le Pen": (
        "History of Marine Le Pen's published first-round scores"
    ),
    "Historique récent de la part quotidienne de couverture de Marine Le Pen": (
        "Recent history of Marine Le Pen's daily coverage share"
    ),
})


_MONTHS_EN = {
    "janv.": "Jan",
    "févr.": "Feb",
    "mars": "Mar",
    "avr.": "Apr",
    "mai": "May",
    "juin": "Jun",
    "juil.": "Jul",
    "août": "Aug",
    "sept.": "Sep",
    "oct.": "Oct",
    "nov.": "Nov",
    "déc.": "Dec",
}


def _candidate_date_en(value: str) -> str:
    result = value
    for fr_month, en_month in _MONTHS_EN.items():
        result = re.sub(
            rf"\b(\d{{1,2}})\s+{re.escape(fr_month)}\s+(\d{{4}})\b",
            rf"\1 {en_month} \2",
            result,
        )
    result = result.replace("18 AVR 2027", "18 APR 2027")
    return result


def _candidate_dynamic_en(value: str) -> str:
    text = _candidate_date_en(value)
    text = re.sub(r"(?<=\d)\u202f(?=\d)", ",", text)
    text = re.sub(r"(?<=\d),(?=\d{1,2}%\b)", ".", text)

    rules = (
        (r"^Statut vérifié au (.+)$", r"Status verified as of \1"),
        (r"^(\d+) hypothèse$", r"\1 hypothesis"),
        (r"^(\d+) hypothèses$", r"\1 hypotheses"),
        (r"^(\d+) vague$", r"\1 wave"),
        (r"^(\d+) vagues$", r"\1 waves"),
        (r"^(\d+) élément$", r"\1 item"),
        (r"^(\d+) éléments$", r"\1 items"),
        (r"^(\d+) éditeur$", r"\1 publisher"),
        (r"^(\d+) éditeurs$", r"\1 publishers"),
        (r"^(\d+) groupe$", r"\1 cluster"),
        (r"^(\d+) groupes$", r"\1 clusters"),
        (r"^(\d+) thème principal$", r"\1 main topic"),
        (r"^(\d+) thèmes principaux$", r"\1 main topics"),
        (r"^(\d+) vérification$", r"\1 review"),
        (r"^(\d+) vérifications$", r"\1 reviews"),
        (r"^(\d+) jour$", r"\1 day"),
        (r"^(\d+) jours$", r"\1 days"),
        (r"^(\d+) jours actifs$", r"\1 active days"),
        (r"^(\d+) derniers jours$", r"last \1 days"),
        (r"^(\d+) derniers jours publiés$", r"last \1 published days"),
        (r"^(\d+) jours complets · UTC$", r"\1 complete days · UTC"),
        (r"^(\d+) observation$", r"\1 observation"),
        (r"^(\d+) observations$", r"\1 observations"),
        (r"^(\d+) adversaire$", r"\1 opponent"),
        (r"^(\d+) adversaires$", r"\1 opponents"),
        (
            r"^(\d+) adversaire · (\d+) observation affichée$",
            r"\1 opponent · \2 observation shown",
        ),
        (
            r"^(\d+) adversaire · (\d+) observations affichées$",
            r"\1 opponent · \2 observations shown",
        ),
        (
            r"^(\d+) adversaires · (\d+) observation affichée$",
            r"\1 opponents · \2 observation shown",
        ),
        (
            r"^(\d+) adversaires · (\d+) observations affichées$",
            r"\1 opponents · \2 observations shown",
        ),
        (r"^(\d+) test au total$", r"\1 test total"),
        (r"^(\d+) tests au total$", r"\1 tests total"),
        (
            r"^(\d+) tests au total · (\d+) plus récents affichés$",
            r"\1 tests total · \2 most recent shown",
        ),
        (r"^Échantillon : (.+)$", r"Sample: \1"),
        (r"^(\d+) association$", r"\1 association"),
        (r"^(\d+) associations$", r"\1 associations"),
        (r"^(\d+) événement$", r"\1 event"),
        (r"^(\d+) événements$", r"\1 events"),
        (r"^(\d+) article$", r"\1 article"),
        (r"^(\d+) articles$", r"\1 articles"),
        (r"^(\d+) articles · (\d+) éditeur$", r"\1 articles · \2 publisher"),
        (r"^(\d+) articles · (\d+) éditeurs$", r"\1 articles · \2 publishers"),
        (r"^au (.+)$", r"as of \1"),
        (r"^Du (.+) au (.+)\.$", r"From \1 to \2."),
        (
            r"^articles · (\d+) jours actifs$",
            r"articles · \1 active days",
        ),
        (
            r"^Historique publié du (.+) au (.+)\.$",
            r"Published history from \1 to \2.",
        ),
        (r"^Historique du (.+) au (.+)\.$", r"History from \1 to \2."),
        (r"^Série quotidienne du (.+) au (.+)\.$", r"Daily series from \1 to \2."),
    )

    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)

    return text


def _candidate_translate_en(value: str, *, protected: bool = False) -> str:
    if protected:
        return value

    if value in _CANDIDATE_TEXT_EN:
        return _CANDIDATE_TEXT_EN[value]

    translated = _candidate_dynamic_en(value)

    # Small compositional interface fragments only.
    translated = translated.replace(" · éditeurs", " · publishers")
    translated = translated.replace(" · jours actifs", " · active days")

    return translated


class _CandidateEnglishHTMLParser(HTMLParser):
    _PROTECTED_CLASSES = {
        "candidate-review-rating",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []

    def _is_protected(self) -> bool:
        return any(protected for _, protected in self.stack)

    @staticmethod
    def _render_attrs(attrs: list[tuple[str, str | None]]) -> str:
        rendered: list[str] = []

        for key, value in attrs:
            if value is None:
                rendered.append(f" {key}")
                continue

            if key in {
                "aria-label",
                "title",
                "data-fr27-tooltip",
                "data-collapsed-label",
                "data-expanded-label",
                "alt",
            }:
                value = _CANDIDATE_ATTR_EN.get(
                    value,
                    _candidate_translate_en(value),
                )

            rendered.append(
                f' {key}="{html.escape(value, quote=True)}"'
            )

        return "".join(rendered)

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = ""
        for key, value in attrs:
            if key == "class" and value:
                classes = value
                break

        protected = (
            tag in {"script", "style", "h4"}
            or bool(set(classes.split()) & self._PROTECTED_CLASSES)
            or self._is_protected()
        )

        if tag == "h4":
            attrs = list(attrs)
            if not any(key == "lang" for key, _ in attrs):
                attrs.append(("lang", "fr"))

        self.parts.append(f"<{tag}{self._render_attrs(attrs)}>")
        self.stack.append((tag, protected))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(f"<{tag}{self._render_attrs(attrs)}/>")

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self._is_protected():
            self.parts.append(data)
            return

        match = re.fullmatch(r"(\s*)(.*?)(\s*)", data, re.DOTALL)
        if not match:
            self.parts.append(data)
            return

        leading, core, trailing = match.groups()
        translated = _candidate_translate_en(core)
        self.parts.append(
            leading + html.escape(translated, quote=False) + trailing
        )


def _candidate_apply_language_shell(document: str, lang: str) -> str:
    locale = CANDIDATE_LOCALES[lang]

    document, count = re.subn(
        r'<html lang="fr" data-page-candidate-id="marine-le-pen">',
        f'<html lang="{locale["lang"]}" data-page-candidate-id="marine-le-pen">',
        document,
        count=1,
    )
    if count != 1:
        raise CandidateReferenceError("candidate HTML lang shell drifted")

    document, count = re.subn(
        r'<meta name="description" content="[^"]*">',
        f'<meta name="description" content="{html.escape(locale["description"], quote=True)}">',
        document,
        count=1,
    )
    if count != 1:
        raise CandidateReferenceError("candidate meta description shell drifted")

    document, count = re.subn(
        r"<title>.*?</title>",
        f'<title>{html.escape(locale["title"])}</title>',
        document,
        count=1,
    )
    if count != 1:
        raise CandidateReferenceError("candidate title shell drifted")

    seo = (
        f'<link rel="canonical" href="{locale["canonical"]}">\n'
        '<link rel="alternate" hreflang="fr" '
        'href="https://france2027.app/candidates/marine-le-pen/">\n'
        '<link rel="alternate" hreflang="en" '
        'href="https://france2027.app/en/candidates/marine-le-pen/">\n'
        '<link rel="alternate" hreflang="x-default" '
        'href="https://france2027.app/candidates/marine-le-pen/">'
    )

    description_match = re.search(
        r'<meta name="description" content="[^"]*">',
        document,
    )
    if not description_match:
        raise CandidateReferenceError("candidate description insertion point drifted")

    document = (
        document[:description_match.end()]
        + "\n"
        + seo
        + document[description_match.end():]
    )

    if lang == "fr":
        language_nav = (
            '<nav class="candidate-language" aria-label="Langue de l’interface">'
            '<a href="/candidates/marine-le-pen/" lang="fr" hreflang="fr" '
            'aria-label="Français" aria-current="page">FR</a>'
            '<span aria-hidden="true">|</span>'
            '<a href="/en/candidates/marine-le-pen/" '
            'data-candidate-language-peer '
            'data-candidate-peer-base="/en/candidates/marine-le-pen/" '
            'lang="en" hreflang="en" aria-label="English" '
            'title="English candidate page">EN</a>'
            '</nav>'
        )
    else:
        language_nav = (
            '<nav class="candidate-language" aria-label="Interface language">'
            '<a href="/candidates/marine-le-pen/" '
            'data-candidate-language-peer '
            'data-candidate-peer-base="/candidates/marine-le-pen/" '
            'lang="fr" hreflang="fr" aria-label="Français" '
            'title="Page candidat en français">FR</a>'
            '<span aria-hidden="true">|</span>'
            '<a href="/en/candidates/marine-le-pen/" lang="en" hreflang="en" '
            'aria-label="English" aria-current="page">EN</a>'
            '</nav>'
        )

    document, count = re.subn(
        r'<nav class="candidate-language".*?</nav>',
        language_nav,
        document,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise CandidateReferenceError("candidate language navigation drifted")

    if lang == "en":
        document = document.replace(
            '<a class="candidate-brand" href="/"',
            '<a class="candidate-brand" href="/en/"',
            1,
        )
        document = document.replace(
            '<a href="/#candidates">CANDIDATS</a>',
            '<a href="/en/#candidates">CANDIDATES</a>',
            1,
        )
        document = document.replace(
            '<a class="fr27-dashboard-cta" href="https://france2027.app/">',
            '<a class="fr27-dashboard-cta" href="https://france2027.app/en/">',
            1,
        )

    return document


def render_html(
    payload: dict[str, Any],
    hud_metrics: dict[str, int] | None = None,
    *,
    lang: str = "fr",
) -> bytes:
    if lang not in CANDIDATE_LOCALES:
        raise CandidateReferenceError(f"unsupported candidate locale: {lang}")

    raw = _render_candidate_structure_html(payload, hud_metrics).decode("utf-8")
    raw = _candidate_apply_language_shell(raw, lang)

    if lang == "fr":
        return raw.encode("utf-8")

    parser = _CandidateEnglishHTMLParser()
    parser.feed(raw)
    parser.close()
    rendered = "".join(parser.parts)

    # HTMLParser lowercases attribute names; SVG viewBox is case-sensitive.
    rendered = rendered.replace(" viewbox=", " viewBox=")

    # Source-originated h4 content remains in its published language.
    # These three h4 elements are product-interface labels.
    interface_h4 = {
        "PÉRIMÈTRE": "SCOPE",
        "PLACEMENT DE LA MENTION": "MENTION PLACEMENT",
        "PREMIER ÉDITEUR": "TOP PUBLISHER",
    }
    for fr_label, en_label in interface_h4.items():
        rendered = rendered.replace(
            f'<h4 lang="fr">{fr_label}</h4>',
            f"<h4>{en_label}</h4>",
        )

    # English remains bound to the same language-neutral projection.
    if (
        '"data_url":"/candidates/marine-le-pen/data.json"'
        not in rendered
    ):
        raise CandidateReferenceError("English candidate data URL drifted")

    return rendered.encode("utf-8")



def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--html-output", type=Path, default=HTML_OUTPUT_PATH)
    parser.add_argument("--html-output-en", type=Path, default=HTML_OUTPUT_PATH_EN)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sources = load_sources(args.root)
    serialized = serialize_projection(build_projection(sources, args.root))
    projection = json.loads(serialized)
    hud_metrics = derive_hud_metrics(sources)
    rendered_html = render_html(projection, hud_metrics, lang="fr")
    rendered_html_en = render_html(projection, hud_metrics, lang="en")
    output = args.output if args.output.is_absolute() else args.root / args.output
    html_output = (
        args.html_output if args.html_output.is_absolute() else args.root / args.html_output
    )
    html_output_en = (
        args.html_output_en
        if args.html_output_en.is_absolute()
        else args.root / args.html_output_en
    )
    if args.check:
        if not output.exists() or output.read_bytes() != serialized:
            raise SystemExit(f"stale candidate reference projection: {output}")
        if not html_output.exists() or html_output.read_bytes() != rendered_html:
            raise SystemExit(f"stale candidate reference HTML: {html_output}")
        if not html_output_en.exists() or html_output_en.read_bytes() != rendered_html_en:
            raise SystemExit(f"stale English candidate reference HTML: {html_output_en}")
        print(f"candidate reference projection and bilingual HTML are current: {output}")
        return 0
    atomic_write(output, serialized)
    atomic_write(html_output, rendered_html)
    atomic_write(html_output_en, rendered_html_en)
    print(f"wrote {output}")
    print(f"wrote {html_output}")
    print(f"wrote {html_output_en}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
