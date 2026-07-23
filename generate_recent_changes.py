#!/usr/bin/env python3
"""Compose the compact Recent Changes Ledger from existing public data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fetch_news_wire import SOURCES, canonical_url, normalize


SCHEMA_VERSION = 1
WINDOW_DAYS = 14
MAX_ITEMS = 0  # zero means retain every qualifying change in the window
PARIS = ZoneInfo("Europe/Paris")
MONTH_ABBREVIATIONS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
VALID_CATEGORIES = {"campaign", "polling", "runoff", "fact_check", "legal"}
TRUSTED_CHANGE_DATE_KINDS = {
    "source_published",
    "official_event",
    "first_seen",
    "fieldwork_ended",
    "review_published",
    "ruling_or_decision",
}
STRONG_CAMPAIGN_ACTION_PHRASES = (
    "annonce sa candidature",
    "annonce etre candidat",
    "annonce etre candidate",
    "officialise sa candidature",
    "se declare candidat",
    "se declare candidate",
    "je suis candidat",
    "je suis candidate",
    "se lance dans la course",
    "se lancer dans la course",
    "se retire de la course",
    "renonce a se presenter",
    "decline la primaire",
    "entree en campagne",
    "lance sa campagne",
    "est investi",
    "est investie",
    "est designe",
    "est designee",
    "rallie",
    "ralliement",
    "soutient la candidature",
    "soutien a la candidature",
    "apporte son soutien",
    "soutien d",
    "soutenus par",
    "appelle a voter pour",
)
RETROSPECTIVE_CAMPAIGN_HEADLINE_PHRASES = (
    "longue liste des",
    "liste des dirigeants",
    "retour sur les soutiens",
    "histoire des soutiens",
)
CONTEXTUAL_CAMPAIGN_ACTION_PHRASES = (
    "se prepare",
    "acte la rupture",
    "decide d enterrer la primaire",
    "enterre la primaire",
    "se prononce pour une primaire",
    "modifie le processus de primaire",
    "change le processus de primaire",
    "annonce un vote",
    "fixe la date du vote",
    "convoque un vote",
    "organise un meeting",
    "annonce un meeting",
    "reunit ses soutiens",
    "presente son programme",
    "devoile son programme",
    "s engage a",
    "propose un accord",
    "propose une alliance",
    "propose une coalition",
    "conclut un accord",
    "rejoint une alliance",
    "quitte une coalition",
    "pose ses conditions",
    "fixe un ultimatum",
    "ultimatum",
)
MATERIAL_LEGAL_ACTION_PHRASES = (
    "assigne",
    "porte plainte",
    "depose plainte",
    "echoue a faire annuler",
    "rejette le recours",
    "rejette sa demande",
    "confirme la condamnation",
    "annule la condamnation",
    "est condamne",
    "est condamnee",
    "est relaxe",
    "est relaxee",
    "reste eligible",
    "devient ineligible",
    "est mis en examen",
    "est mise en examen",
    "ouvre une enquete",
    "ouvre une investigation",
    "statue sur l eligibilite",
    "decision sur l eligibilite",
)
PRESIDENTIAL_RULE_ACTION_PHRASES = (
    "parquet national financier",
    "investigations visant des candidats",
    "regles de parrainage",
    "parrainage presidentiel",
    "500 signatures",
    "calendrier de l election presidentielle",
    "dates du premier tour",
    "dates du second tour",
    "financement de la campagne presidentielle",
    "comptes de campagne",
    "temps de parole",
    "pluralisme",
    "regles audiovisuelles",
)
PRESIDENTIAL_CONTEXT_PHRASES = (
    "presidentielle",
    "election presidentielle",
    "course a l elysee",
    "elysee",
    "campagne presidentielle",
    "primaire presidentielle",
    "pour 2027",
)
NON_PRESIDENTIAL_ELECTION_PHRASES = (
    "senatoriales",
    "legislatives",
    "municipales",
    "europeennes",
    "regionales",
    "departementales",
)

REQUIRED_ITEM_FIELDS = {
    "id",
    "category",
    "headline",
    "summary",
    "trusted_change_at",
    "trusted_change_date_kind",
    "published_at",
    "event_date",
    "detected_at",
    "generated_at",
    "primary_source",
    "source_icon_key",
    "candidate_ids",
    "candidate_names",
    "supporting_source_count",
    "supporting_sources",
    "related_destination",
}
STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du",
    "elle", "en", "et", "est", "il", "la", "le", "les", "leur", "lui",
    "mais", "ne", "ou", "par", "pas", "plus", "pour", "presidentielle",
    "que", "qui", "sa", "se", "ses", "son", "sur", "un", "une", "2027",
}
ACTION_GROUPS = {
    "candidacy": (
        "annonce sa candidature", "candidature", "candidate", "candidat",
        "se lancer dans la course", "course a l elysee", "primaire",
    ),
    "endorsement": (
        "soutien",
        "soutient",
        "ralliement",
        "alliance",
        "propose un accord",
        "propose une alliance",
        "propose une coalition",
        "conclut un accord",
        "rejoint une alliance",
        "quitte une coalition",
        "pose ses conditions",
        "fixe un ultimatum",
        "ultimatum",
        "tend la main",
    ),
    "selection": ("designation", "vote organise", "nomination", "primaire"),
    "procedure": ("parrainage", "500 signatures", "dates du premier", "calendrier"),
    "legal": (
        "condamnation", "condamne", "ineligibilite", "cour de cassation",
        "parquet national financier", "proces", "relaxe", "decision",
    ),
}
ICON_KEY_ALIASES = {
    "franceinfo": "Franceinfo Politique",
    "LCP — Actualités": "LCP",
    "LCP Actualités": "LCP",
    "France 24 — France": "France 24 Français",
}


class LedgerError(RuntimeError):
    """Raised when a public ledger contract is invalid."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_hash(*parts: Any, length: int = 24) -> str:
    identity = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:length]


def slugify(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def icon_key(source_name: str) -> str:
    return ICON_KEY_ALIASES.get(source_name, source_name)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LedgerError(f"could not read {path}: {error}") from error


def previous_items(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except LedgerError:
        return {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }


def date_key(value: str) -> date | None:
    simple = parse_date(value)
    if simple:
        return simple
    parsed = parse_datetime(value)
    return parsed.astimezone(PARIS).date() if parsed else None


def date_sort_value(value: str) -> datetime:
    simple = parse_date(value)
    if simple:
        return datetime.combine(simple, time.min, tzinfo=PARIS).astimezone(timezone.utc)
    parsed = parse_datetime(value)
    if parsed:
        return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def display_date(value: str) -> str:
    parsed = date_key(value)
    if not parsed:
        return value
    return f"{parsed.day} {MONTH_ABBREVIATIONS[parsed.month - 1]} {parsed.year}"


def normalized_title(value: Any) -> str:
    return normalize(value)


def first_matching_phrase(text: str, phrases: Iterable[str]) -> str | None:
    return next((phrase for phrase in phrases if phrase in text), None)


def classify_news_change(
    item: dict[str, Any],
) -> tuple[str, str] | None:
    """Classify only concrete headline-level presidential-race changes.

    The headline must contain the material action or outcome. The RSS summary
    and the upstream ``explicit_election`` flag may confirm presidential
    context, but neither may manufacture an action absent from the headline.
    """

    headline = str(item.get("headline") or "").strip()
    headline_text = normalized_title(headline)
    summary_text = normalized_title(item.get("summary") or "")
    candidate_names = {
        str(name).strip()
        for name in item.get("candidates", [])
        if isinstance(name, str) and name.strip()
    }
    if not headline_text:
        return None

    has_candidate_in_headline = any(
        normalized_title(name) in headline_text
        for name in candidate_names
        if normalized_title(name)
    )
    has_presidential_context_in_headline = any(
        phrase in headline_text
        for phrase in PRESIDENTIAL_CONTEXT_PHRASES
    )
    has_presidential_context = (
        has_presidential_context_in_headline
        or bool(item.get("explicit_election"))
        or any(
            phrase in summary_text
            for phrase in PRESIDENTIAL_CONTEXT_PHRASES
        )
    )
    has_other_election_context = any(
        phrase in headline_text
        for phrase in NON_PRESIDENTIAL_ELECTION_PHRASES
    )

    # Legal action must be visible in the headline and must concern a
    # monitored candidate. A legal word found only in the summary is ignored.
    legal_phrase = first_matching_phrase(
        headline_text,
        MATERIAL_LEGAL_ACTION_PHRASES,
    )
    if legal_phrase and has_candidate_in_headline:
        return (
            "legal",
            "Concrete legal action or outcome involving a monitored candidate.",
        )

    # Race-wide rules and procedures need explicit presidential context in
    # the headline as well as a concrete institutional or procedural phrase.
    rule_phrase = first_matching_phrase(
        headline_text,
        PRESIDENTIAL_RULE_ACTION_PHRASES,
    )
    if rule_phrase and has_presidential_context_in_headline:
        return (
            "legal",
            "Concrete presidential-election legal or procedural development.",
        )

    if has_other_election_context and not has_presidential_context_in_headline:
        return None

    # Roundups and retrospective lists may contain an endorsement verb while
    # reporting no new endorsement. They remain relevant news, not changes.
    if first_matching_phrase(
        headline_text,
        RETROSPECTIVE_CAMPAIGN_HEADLINE_PHRASES,
    ):
        return None

    strong_campaign_phrase = first_matching_phrase(
        headline_text,
        STRONG_CAMPAIGN_ACTION_PHRASES,
    )
    if strong_campaign_phrase and (
        has_candidate_in_headline or has_presidential_context
    ):
        return (
            "campaign",
            "Concrete candidate, endorsement, selection or campaign-status change.",
        )

    contextual_campaign_phrase = first_matching_phrase(
        headline_text,
        CONTEXTUAL_CAMPAIGN_ACTION_PHRASES,
    )
    if contextual_campaign_phrase and has_presidential_context_in_headline:
        return (
            "campaign",
            "Concrete presidential campaign or selection-process development.",
        )

    return None


# Backward-compatible name for existing callers and tests.
def classify_candidate_watch_change(
    item: dict[str, Any],
) -> tuple[str, str] | None:
    return classify_news_change(item)


def title_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalized_title(value).split()
        if token not in STOPWORDS and len(token) > 2
    }


def action_groups(value: Any) -> set[str]:
    text = f" {normalized_title(value)} "
    return {
        group
        for group, phrases in ACTION_GROUPS.items()
        if any(f" {phrase} " in text for phrase in phrases)
    }


def person_entities(value: Any) -> set[str]:
    text = str(value or "")
    matches = re.findall(
        r"\b([A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+(?:[-'][A-ZÀ-ÖØ-Ý]?[a-zà-öø-ÿ]+)?"
        r"\s+[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+(?:[-'][A-ZÀ-ÖØ-Ý]?[a-zà-öø-ÿ]+)?)\b",
        text,
    )
    ignored = {"public senat", "france info", "france politique"}
    return {
        normalized_title(match)
        for match in matches
        if normalized_title(match) not in ignored
    }


def source_metadata(name: str, url: str, published_at: str | None) -> dict[str, Any]:
    return {"name": name, "url": url, "published_at": published_at}


def detected_at_for(
    item_id: str,
    prior: dict[str, dict[str, Any]],
    fallback: datetime,
) -> str:
    existing = prior.get(item_id, {}).get("detected_at")
    parsed = parse_datetime(existing)
    return utc_text(parsed or fallback)


def first_seen_value(records: Iterable[dict[str, Any]]) -> str | None:
    """Return the earliest explicitly stored ingestion/first-seen value."""

    values: list[tuple[datetime, str]] = []
    for record in records:
        for field in ("first_seen_at", "first_seen", "ingested_at"):
            raw = str(record.get(field) or "").strip()
            parsed_datetime = parse_datetime(raw)
            parsed_date = parse_date(raw)
            if parsed_datetime:
                values.append((parsed_datetime, utc_text(parsed_datetime)))
            elif parsed_date:
                values.append((
                    datetime.combine(parsed_date, time.min, tzinfo=PARIS).astimezone(timezone.utc),
                    parsed_date.isoformat(),
                ))
    return min(values, key=lambda item: item[0])[1] if values else None


def resolve_poll_change_date(
    records: Iterable[dict[str, Any]],
) -> tuple[str, str] | None:
    """Resolve a poll wave date without using generator/detection time."""

    records = list(records)
    publication_dates = sorted({
        parsed.isoformat()
        for record in records
        if (parsed := parse_date(record.get("publication_date"))) is not None
    })
    if publication_dates:
        return publication_dates[0], "source_published"

    first_seen = first_seen_value(records)
    if first_seen:
        return first_seen, "first_seen"

    fieldwork_ends = sorted({
        parsed.isoformat()
        for record in records
        if (parsed := parse_date(record.get("fieldwork_end"))) is not None
    })
    if fieldwork_ends:
        return fieldwork_ends[-1], "fieldwork_ended"

    return None


def news_entries(
    payload: dict[str, Any],
    prior: dict[str, dict[str, Any]],
    checked_at: datetime,
    diagnostics: Counter[str],
) -> list[dict[str, Any]]:
    generated = parse_datetime(payload.get("generated_at")) or checked_at
    election_items = payload.get("election_news")
    if not isinstance(election_items, list):
        raise LedgerError("news_wire election_news must be a list")
    notable_items = payload.get("notable_developments", [])
    if not isinstance(notable_items, list):
        raise LedgerError("news_wire notable_developments must be a list")
    candidate_items = payload.get("candidate_watch", [])
    if not isinstance(candidate_items, list):
        raise LedgerError("news_wire candidate_watch must be a list")

    entries: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    seen_urls: set[str] = set()

    def append_entry(
        item: dict[str, Any],
        *,
        category: str,
        summary: str,
    ) -> bool:
        published = parse_datetime(item.get("published_at"))
        url = canonical_url(item.get("url"))
        headline = str(item.get("headline") or "").strip()
        publisher = str(item.get("publisher") or "").strip()
        if not published:
            diagnostics["omitted_missing_trusted_date"] += 1
            diagnostics["omitted_news_missing_publication_date"] += 1
            return False
        if not headline or not publisher or not valid_url(url):
            diagnostics["omitted_invalid_record"] += 1
            return False

        source_id = str(item.get("id") or stable_hash(url, publisher, headline))
        if source_id in seen_source_ids or url in seen_urls:
            diagnostics["omitted_candidate_watch_duplicate"] += 1
            return False
        seen_source_ids.add(source_id)
        seen_urls.add(url)

        candidate_names = sorted(
            {
                str(name).strip()
                for name in item.get("candidates", [])
                if isinstance(name, str) and name.strip()
            }
        )
        headline_text = normalized_title(headline)
        padded_headline = f" {headline_text} "
        headline_candidate_entities = set()
        for name in candidate_names:
            normalized_name = normalized_title(name)
            if not normalized_name:
                continue
            surname = normalized_name.split()[-1]
            if (
                normalized_name in headline_text
                or f" {surname} " in padded_headline
            ):
                headline_candidate_entities.add(normalized_name)
        item_id = f"{category}-{source_id}"
        published_text = utc_text(published)
        entries.append(
            {
                "id": item_id,
                "category": category,
                "headline": headline,
                "summary": summary,
                "trusted_change_at": published_text,
                "trusted_change_date_kind": "source_published",
                "published_at": published_text,
                "event_date": None,
                "detected_at": detected_at_for(item_id, prior, generated),
                "generated_at": utc_text(checked_at),
                "primary_source": {"name": publisher, "url": url},
                "source_icon_key": icon_key(publisher),
                "candidate_ids": [slugify(name) for name in candidate_names],
                "candidate_names": candidate_names,
                "supporting_source_count": 0,
                "supporting_sources": [],
                "related_destination": "#signal-panel-agenda",
                "_entities": (
                    person_entities(headline)
                    | headline_candidate_entities
                ),
                "_source_id": source_id,
            }
        )
        return True

    # A single article can appear in several broad upstream lanes. Merge those
    # copies first, preserve candidate provenance, and classify the article only
    # once with the strict headline-first change gate below.
    unique_items: dict[str, dict[str, Any]] = {}
    for lane_name, lane_items in (
        ("election_news", election_items),
        ("notable_developments", notable_items),
        ("candidate_watch", candidate_items),
    ):
        for raw_item in lane_items:
            if not isinstance(raw_item, dict):
                continue
            url = canonical_url(raw_item.get("url"))
            source_id = str(
                raw_item.get("id")
                or stable_hash(
                    url,
                    raw_item.get("publisher"),
                    raw_item.get("headline"),
                )
            )
            key = source_id or url
            if key in unique_items:
                existing = unique_items[key]
                existing["candidates"] = sorted(
                    {
                        *[
                            str(name).strip()
                            for name in existing.get("candidates", [])
                            if isinstance(name, str) and name.strip()
                        ],
                        *[
                            str(name).strip()
                            for name in raw_item.get("candidates", [])
                            if isinstance(name, str) and name.strip()
                        ],
                    }
                )
                existing["explicit_election"] = bool(
                    existing.get("explicit_election")
                    or raw_item.get("explicit_election")
                )
                if not existing.get("summary") and raw_item.get("summary"):
                    existing["summary"] = raw_item.get("summary")
                existing["_lanes"].add(lane_name)
                diagnostics["omitted_candidate_watch_duplicate"] += 1
                continue

            item = dict(raw_item)
            item["_lanes"] = {lane_name}
            unique_items[key] = item

    for item in unique_items.values():
        classification = classify_news_change(item)
        if classification is None:
            diagnostics["omitted_news_non_material"] += 1
            if "candidate_watch" in item.get("_lanes", set()):
                diagnostics["omitted_candidate_watch_non_material"] += 1
            continue
        category, summary = classification
        append_entry(item, category=category, summary=summary)

    return cluster_news_entries(entries)


def news_entries_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["category"] != right["category"]:
        return False
    if left["primary_source"]["url"] == right["primary_source"]["url"]:
        return True
    if normalized_title(left["headline"]) == normalized_title(right["headline"]):
        return True

    left_date = date_key(left["trusted_change_at"])
    right_date = date_key(right["trusted_change_at"])
    if not left_date or not right_date or abs((left_date - right_date).days) > 1:
        return False

    # Same-day alliance proposal deduplication.
    # Merge reports only when they:
    # - are campaign items published on the same date;
    # - share a monitored political actor;
    # - both describe the same explicit outreach/negotiation action.
    left_text = normalized_title(left["headline"])
    right_text = normalized_title(right["headline"])
    shared_candidate_ids = (
        set(left.get("candidate_ids", []))
        & set(right.get("candidate_ids", []))
    )

    alliance_terms = (
        "accord",
        "alliance",
        "coalition",
        "ultimatum",
        "negociation",
    )

    same_day_alliance_proposal = (
        left["category"] == "campaign"
        and left_date == right_date
        and bool(shared_candidate_ids)
        and all(
            "tend" in text
            and "main" in text
            and "ecologistes" in text
            and any(term in text for term in alliance_terms)
            for text in (left_text, right_text)
        )
    )

    if same_day_alliance_proposal:
        return True

    left_tokens = title_tokens(left["headline"])
    right_tokens = title_tokens(right["headline"])
    union = left_tokens | right_tokens
    similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
    shared_entities = (
        set(left.get("_entities", set()))
        & set(right.get("_entities", set()))
    )
    shared_actions = (
        action_groups(left["headline"])
        & action_groups(right["headline"])
    )
    return similarity >= 0.68 or bool(
        shared_entities
        and shared_actions
        and similarity >= 0.30
    )


def cluster_news_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for entry in sorted(entries, key=lambda item: (date_sort_value(item["trusted_change_at"]), item["id"])):
        for cluster in clusters:
            if any(news_entries_match(entry, member) for member in cluster):
                cluster.append(entry)
                break
        else:
            clusters.append([entry])

    merged: list[dict[str, Any]] = []
    for cluster in clusters:
        primary = min(
            cluster,
            key=lambda item: (date_sort_value(item["trusted_change_at"]), item["primary_source"]["name"], item["id"]),
        )
        supporters = [item for item in cluster if item is not primary]
        result = {key: value for key, value in primary.items() if not key.startswith("_")}
        result["candidate_ids"] = sorted({candidate for item in cluster for candidate in item["candidate_ids"]})
        result["candidate_names"] = sorted({candidate for item in cluster for candidate in item["candidate_names"]})
        result["supporting_sources"] = [
            source_metadata(
                item["primary_source"]["name"],
                item["primary_source"]["url"],
                item["published_at"],
            )
            for item in supporters
        ]
        result["supporting_source_count"] = len(result["supporting_sources"])
        if supporters:
            result["summary"] = (
                primary["summary"] + " "
                + f"{len(supporters)} additional monitored publisher"
                + (" supports" if len(supporters) == 1 else "s support")
                + " the development."
            )
        merged.append(result)
    return merged


def poll_entries(
    events: Any,
    prior: dict[str, dict[str, Any]],
    checked_at: datetime,
    diagnostics: Counter[str],
) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        raise LedgerError("polls data must be a list")
    waves: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for event in events:
        if (
            not isinstance(event, dict)
            or event.get("round") != "first_round"
            or not event.get("event_id")
            or not event.get("scenario_key")
            or not isinstance(event.get("candidates"), list)
            or len(event["candidates"]) < 2
        ):
            continue
        key = (
            event.get("pollster"), event.get("fieldwork_start"), event.get("fieldwork_end"),
            event.get("sample_size"), event.get("publication_date"), canonical_url(event.get("source_url")),
        )
        waves.setdefault(key, []).append(event)

    entries: list[dict[str, Any]] = []
    for key, wave_events in waves.items():
        pollster, fieldwork_start, fieldwork_end, sample_size, publication_date, source_url = key
        if not pollster or not valid_url(source_url):
            diagnostics["omitted_invalid_record"] += 1
            continue
        event_ids = sorted(str(event["event_id"]) for event in wave_events)
        item_id = "polling-" + stable_hash(*event_ids)
        trusted_date = resolve_poll_change_date(wave_events)
        if not trusted_date:
            diagnostics["omitted_missing_trusted_date"] += 1
            diagnostics["omitted_polling_missing_trusted_date"] += 1
            continue
        trusted_change_at, trusted_kind = trusted_date
        published_text = trusted_change_at if trusted_kind == "source_published" else None
        sample_text = (
            f"{int(sample_size):,} respondents" if isinstance(sample_size, (int, float)) else "sample not stated"
        )
        hypothesis_count = len(wave_events)
        date_label = {
            "source_published": "Published",
            "first_seen": "First seen",
            "fieldwork_ended": "Fieldwork ended",
        }[trusted_kind]
        summary = (
            f"{date_label} {display_date(trusted_change_at)} · "
            f"fieldwork {fieldwork_start}–{fieldwork_end} · {sample_text}."
        )
        entries.append(
            {
                "id": item_id,
                "category": "polling",
                "headline": (
                    f"{pollster} first-round poll contains {hypothesis_count} published "
                    + ("hypothesis." if hypothesis_count == 1 else "hypotheses.")
                ),
                "summary": summary,
                "trusted_change_at": trusted_change_at,
                "trusted_change_date_kind": trusted_kind,
                "published_at": published_text,
                "event_date": None,
                "detected_at": detected_at_for(item_id, prior, checked_at),
                "generated_at": utc_text(checked_at),
                "primary_source": {"name": str(pollster), "url": source_url},
                "source_icon_key": icon_key(str(pollster)),
                "candidate_ids": [],
                "candidate_names": [],
                "supporting_source_count": 0,
                "supporting_sources": [],
                "related_destination": "#polling-evidence-lab",
            }
        )
    return entries


def runoff_entry(
    payload: dict[str, Any],
    second_round_payload: dict[str, Any],
    prior: dict[str, dict[str, Any]],
    checked_at: datetime,
    diagnostics: Counter[str],
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") == "insufficient":
        return []
    selected = payload.get("selected_matchup")
    if not isinstance(selected, dict):
        return []
    candidates = [str(name) for name in selected.get("candidates", []) if str(name).strip()]
    results = selected.get("results")
    if len(candidates) != 2 or not isinstance(results, list) or not results:
        diagnostics["omitted_invalid_record"] += 1
        return []
    valid_results = [
        result for result in results
        if isinstance(result, dict) and isinstance(result.get("margin"), (int, float))
        and valid_url(canonical_url(result.get("source_url")))
    ]
    if not valid_results:
        diagnostics["omitted_invalid_record"] += 1
        return []
    valid_results.sort(key=lambda item: (float(item["margin"]), str(item.get("pollster") or "")))
    primary = valid_results[0]
    fingerprint_source = {
        "status": payload.get("status"),
        "selected_matchup": selected,
        "common_matchups": payload.get("common_matchups", []),
        "pollsters": payload.get("pollsters", []),
    }
    fingerprint = stable_hash(json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True))
    item_id = "runoff-" + fingerprint
    second_round_events = second_round_payload.get("events")
    event_by_id = {
        str(event.get("event_id")): event
        for event in second_round_events
        if isinstance(event, dict) and event.get("event_id")
    } if isinstance(second_round_events, list) else {}
    evidence_events = [
        event_by_id[str(result.get("event_id"))]
        for result in valid_results
        if str(result.get("event_id")) in event_by_id
    ]
    trusted_date = resolve_poll_change_date(evidence_events)
    if not trusted_date:
        fieldwork_end = parse_date(payload.get("fieldwork_window", {}).get("end"))
        trusted_date = (
            (fieldwork_end.isoformat(), "fieldwork_ended")
            if fieldwork_end else None
        )
    if not trusted_date:
        diagnostics["omitted_missing_trusted_date"] += 1
        diagnostics["omitted_runoff_missing_evidence_date"] += 1
        return []
    trusted_change_at, trusted_kind = trusted_date
    detected_fallback = parse_datetime(payload.get("generated_at")) or checked_at
    detected = parse_datetime(prior.get(item_id, {}).get("detected_at")) or detected_fallback
    margins = sorted(float(result["margin"]) for result in valid_results)
    margin_text = (
        f"{margins[0]:g} points" if margins[0] == margins[-1]
        else f"{margins[0]:g}–{margins[-1]:g} points"
    )
    source_url = canonical_url(primary.get("source_url"))
    supporters = [
        source_metadata(
            str(result.get("pollster") or "Polling source"),
            canonical_url(result.get("source_url")),
            None,
        )
        for result in valid_results[1:]
    ]
    date_label = {
        "source_published": "Published",
        "first_seen": "First seen",
        "fieldwork_ended": "Fieldwork ended",
    }[trusted_kind]
    return [
        {
            "id": item_id,
            "category": "runoff",
            "headline": f"{candidates[0]} vs {candidates[1]} is the closest tested runoff.",
            "summary": (
                f"{date_label} {display_date(trusted_change_at)} · reported margins in the displayed "
                f"evidence span {margin_text}; no average is calculated."
            ),
            "trusted_change_at": trusted_change_at,
            "trusted_change_date_kind": trusted_kind,
            "published_at": trusted_change_at if trusted_kind == "source_published" else None,
            "event_date": None,
            "detected_at": utc_text(detected),
            "generated_at": utc_text(checked_at),
            "primary_source": {"name": str(primary.get("pollster") or "Polling source"), "url": source_url},
            "source_icon_key": icon_key(str(primary.get("pollster") or "Polling source")),
            "candidate_ids": [slugify(name) for name in candidates],
            "candidate_names": candidates,
            "supporting_source_count": len(supporters),
            "supporting_sources": supporters,
            "related_destination": "#closest-runoff-title",
        }
    ]


def fact_check_entries_match(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    if left["primary_source"]["url"] == right["primary_source"]["url"]:
        return True
    if normalized_title(left["headline"]) == normalized_title(right["headline"]):
        return True
    if normalized_title(left["primary_source"]["name"]) == normalized_title(
        right["primary_source"]["name"]
    ):
        return False

    left_date = date_key(left["trusted_change_at"])
    right_date = date_key(right["trusted_change_at"])
    if (
        not left_date
        or not right_date
        or abs((left_date - right_date).days) > 7
    ):
        return False

    shared_candidates = (
        set(left.get("candidate_ids", []))
        & set(right.get("candidate_ids", []))
    )
    if not shared_candidates:
        return False

    left_tokens = title_tokens(left["headline"])
    right_tokens = title_tokens(right["headline"])
    union = left_tokens | right_tokens
    similarity = (
        len(left_tokens & right_tokens) / len(union)
        if union
        else 0.0
    )
    return similarity >= 0.55


def cluster_fact_check_entries(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for entry in sorted(
        entries,
        key=lambda item: (
            date_sort_value(item["trusted_change_at"]),
            item["id"],
        ),
    ):
        for cluster in clusters:
            if any(
                fact_check_entries_match(entry, member)
                for member in cluster
            ):
                cluster.append(entry)
                break
        else:
            clusters.append([entry])

    merged: list[dict[str, Any]] = []
    for cluster in clusters:
        primary = max(
            cluster,
            key=lambda item: (
                date_sort_value(item["trusted_change_at"]),
                item["primary_source"]["name"],
                item["id"],
            ),
        )
        supporters = sorted(
            (item for item in cluster if item is not primary),
            key=lambda item: (
                date_sort_value(item["trusted_change_at"]),
                item["primary_source"]["name"],
                item["id"],
            ),
            reverse=True,
        )
        result = dict(primary)
        result["candidate_ids"] = sorted({
            candidate
            for item in cluster
            for candidate in item["candidate_ids"]
        })
        result["candidate_names"] = sorted({
            candidate
            for item in cluster
            for candidate in item["candidate_names"]
        })
        result["supporting_sources"] = [
            source_metadata(
                item["primary_source"]["name"],
                item["primary_source"]["url"],
                item["published_at"],
            )
            for item in supporters
        ]
        result["supporting_source_count"] = len(
            result["supporting_sources"]
        )
        if supporters:
            result["summary"] = (
                primary["summary"]
                + " "
                + f"{len(supporters)} additional publisher"
                + (" reviewed" if len(supporters) == 1 else "s reviewed")
                + " the same claim."
            )
        merged.append(result)
    return merged


def fact_check_entries(
    payload: dict[str, Any],
    prior: dict[str, dict[str, Any]],
    checked_at: datetime,
    diagnostics: Counter[str],
) -> list[dict[str, Any]]:
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        raise LedgerError("claims reviews must be a list")
    generated = parse_datetime(payload.get("generated_at")) or checked_at
    entries: list[dict[str, Any]] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        review_date = parse_date(review.get("review_date"))
        url = canonical_url(review.get("review_url"))
        headline = str(review.get("claim_text") or "").strip()
        publisher = str(review.get("publisher_name") or "").strip()
        if not review_date:
            diagnostics["omitted_missing_trusted_date"] += 1
            diagnostics["omitted_fact_check_missing_review_date"] += 1
            continue
        if not valid_url(url) or not headline or not publisher:
            diagnostics["omitted_invalid_record"] += 1
            continue
        source_id = str(review.get("id") or stable_hash(url, review_date, headline))
        item_id = "fact-check-" + source_id
        associations = review.get("candidate_associations", [])
        candidate_ids = sorted({
            str(association.get("candidate_id") or "").strip()
            for association in associations if isinstance(association, dict)
            and str(association.get("candidate_id") or "").strip()
        })
        candidate_names = sorted({
            str(association.get("candidate_name") or "").strip()
            for association in associations if isinstance(association, dict)
            and str(association.get("candidate_name") or "").strip()
        })
        summary_parts = [publisher]
        if review.get("rating"):
            summary_parts.append(f"rating: {review['rating']}")
        if review.get("claimant"):
            summary_parts.append(f"claimant: {review['claimant']}")
        entries.append(
            {
                "id": item_id,
                "category": "fact_check",
                "headline": headline,
                "summary": " · ".join(summary_parts) + ".",
                "trusted_change_at": review_date.isoformat(),
                "trusted_change_date_kind": "review_published",
                "published_at": review_date.isoformat(),
                "event_date": None,
                "detected_at": detected_at_for(item_id, prior, generated),
                "generated_at": utc_text(checked_at),
                "primary_source": {"name": publisher, "url": url},
                "source_icon_key": icon_key(publisher),
                "candidate_ids": candidate_ids,
                "candidate_names": candidate_names,
                "supporting_source_count": 0,
                "supporting_sources": [],
                "related_destination": "#signal-panel-fact-checks",
            }
        )
    return cluster_fact_check_entries(entries)


def valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def choose_unique_primary_urls(
    entries: Iterable[dict[str, Any]],
    diagnostics: Counter[str],
) -> list[dict[str, Any]]:
    priority = {"runoff": 0, "legal": 1, "campaign": 2, "fact_check": 3, "polling": 4}
    selected: dict[str, dict[str, Any]] = {}
    for entry in entries:
        url = entry["primary_source"]["url"]
        existing = selected.get(url)
        if existing is None or priority[entry["category"]] < priority[existing["category"]]:
            if existing is not None:
                diagnostics["omitted_duplicate_primary_url"] += 1
            selected[url] = entry
        else:
            diagnostics["omitted_duplicate_primary_url"] += 1
    return list(selected.values())


def compose_recent_changes(
    *,
    news: dict[str, Any],
    polls: Any,
    runoff: dict[str, Any],
    second_round: dict[str, Any],
    claims: dict[str, Any],
    previous: dict[str, dict[str, Any]],
    checked_at: datetime,
) -> dict[str, Any]:
    end_date = checked_at.astimezone(PARIS).date()
    start_date = end_date - timedelta(days=WINDOW_DAYS - 1)
    diagnostics: Counter[str] = Counter()
    entries = [
        *news_entries(news, previous, checked_at, diagnostics),
        *poll_entries(polls, previous, checked_at, diagnostics),
        *runoff_entry(runoff, second_round, previous, checked_at, diagnostics),
        *fact_check_entries(claims, previous, checked_at, diagnostics),
    ]
    window_entries: list[dict[str, Any]] = []
    for entry in entries:
        item_date = date_key(entry["trusted_change_at"])
        if item_date is None:
            diagnostics["omitted_missing_trusted_date"] += 1
        elif start_date <= item_date <= end_date:
            window_entries.append(entry)
        else:
            diagnostics["omitted_outside_window"] += 1
    entries = choose_unique_primary_urls(window_entries, diagnostics)
    category_priority = {"runoff": 0, "polling": 1, "legal": 2, "campaign": 3, "fact_check": 4}
    entries.sort(
        key=lambda item: (
            -date_sort_value(item["trusted_change_at"]).timestamp(),
            category_priority[item["category"]],
            item["id"],
        )
    )
    if MAX_ITEMS > 0 and len(entries) > MAX_ITEMS:
        diagnostics["omitted_over_output_limit"] += len(entries) - MAX_ITEMS
        entries = entries[:MAX_ITEMS]
    counts = Counter(item["category"] for item in entries)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_text(checked_at),
        "last_successful_check_at": utc_text(checked_at),
        "newest_trusted_change_at": entries[0]["trusted_change_at"] if entries else None,
        "oldest_trusted_change_at": entries[-1]["trusted_change_at"] if entries else None,
        "window": {
            "days": WINDOW_DAYS,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timezone": "Europe/Paris",
            "max_items": MAX_ITEMS,
        },
        "source_universe": [source["name"] for source in SOURCES],
        "counts": {
            "total": len(entries),
            **{category: counts.get(category, 0) for category in sorted(VALID_CATEGORIES)},
        },
        "diagnostics": {
            key: diagnostics.get(key, 0)
            for key in (
                "omitted_missing_trusted_date",
                "omitted_news_missing_publication_date",
                "omitted_news_non_material",
                "omitted_candidate_watch_non_material",
                "omitted_candidate_watch_duplicate",
                "omitted_polling_missing_trusted_date",
                "omitted_runoff_missing_evidence_date",
                "omitted_fact_check_missing_review_date",
                "omitted_invalid_record",
                "omitted_duplicate_primary_url",
                "omitted_outside_window",
                "omitted_over_output_limit",
            )
        },
        "items": entries,
    }
    validate_recent_changes(payload)
    return payload


def validate_recent_changes(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise LedgerError("top-level value must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError(f"schema_version must equal {SCHEMA_VERSION}")
    checked_at = parse_datetime(payload.get("last_successful_check_at"))
    if not checked_at or not parse_datetime(payload.get("generated_at")):
        raise LedgerError("generated_at and last_successful_check_at must be datetimes")
    window = payload.get("window")
    if not isinstance(window, dict) or window.get("days") != WINDOW_DAYS or window.get("max_items") != MAX_ITEMS:
        raise LedgerError("window contract is invalid")
    window_start = parse_date(window.get("start_date"))
    window_end = parse_date(window.get("end_date"))
    if not window_start or not window_end or (window_end - window_start).days != WINDOW_DAYS - 1:
        raise LedgerError("window dates do not describe 14 inclusive days")
    expected_sources = [source["name"] for source in SOURCES]
    if payload.get("source_universe") != expected_sources:
        raise LedgerError("source_universe must equal the configured publisher feeds")
    items = payload.get("items")
    if not isinstance(items, list):
        raise LedgerError("items must be a list")
    if MAX_ITEMS > 0 and len(items) > MAX_ITEMS:
        raise LedgerError(f"items must contain at most {MAX_ITEMS} entries")

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    previous_sort: datetime | None = None
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != REQUIRED_ITEM_FIELDS:
            raise LedgerError(f"item {index} has unexpected fields")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in seen_ids:
            raise LedgerError(f"item {index} has an invalid or duplicate id")
        seen_ids.add(item_id)
        if item.get("category") not in VALID_CATEGORIES:
            raise LedgerError(f"item {index} has an invalid category")
        headline = item.get("headline")
        title_key = normalized_title(headline)
        if not isinstance(headline, str) or not title_key or title_key in seen_titles:
            raise LedgerError(f"item {index} has an empty or duplicate normalized headline")
        seen_titles.add(title_key)
        source = item.get("primary_source")
        if not isinstance(source, dict) or set(source) != {"name", "url"} or not source.get("name"):
            raise LedgerError(f"item {index} has an invalid primary_source")
        url = source.get("url")
        if not valid_url(url) or url in seen_urls:
            raise LedgerError(f"item {index} has an invalid or duplicate primary URL")
        seen_urls.add(url)
        if not parse_datetime(item.get("detected_at")):
            raise LedgerError(f"item {index} has an invalid detected_at")
        if not parse_datetime(item.get("generated_at")):
            raise LedgerError(f"item {index} has an invalid generated_at")
        trusted_kind = item.get("trusted_change_date_kind")
        trusted_change_at = item.get("trusted_change_at")
        if trusted_kind not in TRUSTED_CHANGE_DATE_KINDS:
            raise LedgerError(f"item {index} has an invalid trusted date kind")
        if trusted_kind in {"source_published", "review_published"}:
            if not item.get("published_at") or trusted_change_at != item.get("published_at"):
                raise LedgerError(f"item {index} does not use its publication date")
        elif trusted_kind in {"official_event", "ruling_or_decision"}:
            if not item.get("event_date") or trusted_change_at != item.get("event_date"):
                raise LedgerError(f"item {index} does not use its official event date")
        elif item.get("published_at") is not None or item.get("event_date") is not None:
            raise LedgerError(f"item {index} fabricates publication/event provenance")
        item_day = date_key(str(trusted_change_at or ""))
        if not item_day or not window_start <= item_day <= window_end:
            raise LedgerError(f"item {index} falls outside the 14-day window")
        sort_value = date_sort_value(str(trusted_change_at))
        if previous_sort is not None and sort_value > previous_sort:
            raise LedgerError("items are not reverse chronological")
        previous_sort = sort_value
        if not isinstance(item.get("candidate_ids"), list) or not isinstance(item.get("candidate_names"), list):
            raise LedgerError(f"item {index} candidate fields must be arrays")
        supporters = item.get("supporting_sources")
        if not isinstance(supporters, list) or item.get("supporting_source_count") != len(supporters):
            raise LedgerError(f"item {index} supporting-source count is invalid")
        for supporter in supporters:
            if not isinstance(supporter, dict) or set(supporter) != {"name", "url", "published_at"} or not valid_url(supporter.get("url")):
                raise LedgerError(f"item {index} has invalid supporting-source metadata")

    counts = payload.get("counts")
    expected_counts = {
        "total": len(items),
        **{category: sum(item["category"] == category for item in items) for category in sorted(VALID_CATEGORIES)},
    }
    if counts != expected_counts:
        raise LedgerError("counts do not match items")
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict) or any(
        not isinstance(value, int) or value < 0
        for value in diagnostics.values()
    ):
        raise LedgerError("diagnostics must contain non-negative integer counts")
    expected_newest = items[0]["trusted_change_at"] if items else None
    expected_oldest = items[-1]["trusted_change_at"] if items else None
    if (
        payload.get("newest_trusted_change_at") != expected_newest
        or payload.get("oldest_trusted_change_at") != expected_oldest
    ):
        raise LedgerError("trusted newest/oldest metadata does not match the displayed items")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--news", type=Path, default=Path("news_wire.json"))
    parser.add_argument("--polls", type=Path, default=Path("polls.json"))
    parser.add_argument("--runoff", type=Path, default=Path("closest_tested_runoff.json"))
    parser.add_argument("--second-round", type=Path, default=Path("second_round_polls.json"))
    parser.add_argument("--claims", type=Path, default=Path("claims_under_scrutiny.json"))
    parser.add_argument("--output", type=Path, default=Path("recent_changes.json"))
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--checked-at", help="UTC ISO timestamp; defaults to now")
    parser.add_argument("--validate-only", type=Path)
    arguments = parser.parse_args()

    if arguments.validate_only:
        validate_recent_changes(load_json(arguments.validate_only))
        print(f"Validated Recent Changes Ledger: {arguments.validate_only}")
        return 0

    checked_at = parse_datetime(arguments.checked_at) if arguments.checked_at else utc_now()
    if not checked_at:
        raise SystemExit("--checked-at must be an ISO datetime")
    previous_path = arguments.previous or arguments.output
    payload = compose_recent_changes(
        news=load_json(arguments.news),
        polls=load_json(arguments.polls),
        runoff=load_json(arguments.runoff),
        second_round=load_json(arguments.second_round),
        claims=load_json(arguments.claims),
        previous=previous_items(previous_path),
        checked_at=checked_at,
    )
    atomic_write_json(arguments.output, payload)
    counts = payload["counts"]
    print(
        f"Generated {counts['total']} recent changes "
        f"({', '.join(f'{category}={counts[category]}' for category in sorted(VALID_CATEGORIES))})."
    )
    print(
        f"Window: {payload['window']['start_date']} to {payload['window']['end_date']} "
        f"· output: {arguments.output}"
    )
    print(
        "Omissions: "
        + ", ".join(
            f"{key}={value}"
            for key, value in payload["diagnostics"].items()
            if value
        )
        if any(payload["diagnostics"].values())
        else "Omissions: none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
