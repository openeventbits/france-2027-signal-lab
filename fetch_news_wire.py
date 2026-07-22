#!/usr/bin/env python3
"""Build the FR27 Signal Lab election news wire from direct publisher RSS feeds."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import ssl
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


SOURCE_CONFIG_PATH = Path(__file__).with_name("news_sources.json")
SOURCES = tuple(
    json.loads(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
)

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "xtor",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

ELECTION_PATTERNS = (
    re.compile(r"\bpresidentielle(?:\s+francaise)?(?:\s+de)?\s+2027\b"),
    re.compile(r"\belection\s+presidentielle\b"),
    re.compile(r"\bprochaine\s+presidentielle\b"),
    re.compile(r"\bcourse\s+a\s+l\s+elysee\b"),
    re.compile(r"\belysee\s+2027\b"),
    re.compile(r"\bcandidat(?:e|ure)?\s+a\s+l\s+election\s+presidentielle\b"),
)

CAMPAIGN_AGENDA_TOPICS = (
    {
        "id": "legal_eligibility",
        "label": "Legal status & eligibility",
        "terms": (
            "parquet national financier",
            "cour de cassation",
            "ineligibilite",
            "condamnation",
            "proces",
            "bracelet electronique",
            "delinquante",
            "relaxe",
            "assigne",
            "porte plainte",
            "depose plainte",
            "echoue a faire annuler",
            "rejette le recours",
            "rejette sa demande",
            "mis en examen",
            "mise en examen",
            "ouvre une enquete",
            "reste eligible",
            "devient ineligible",
        ),
    },
    {
        "id": "selection_strategy",
        "label": "Primaries & party strategy",
        "terms": (
            "primaire",
            "vote du 9 juillet",
            "vote organise",
            "strategie de designation",
            "designation d un candidat",
            "designer un candidat",
            "fragilise",
            "acte la rupture",
            "se prononce pour une primaire",
            "enterre la primaire",
            "investiture",
            "est designe",
            "est designee",
            "nomination",
        ),
    },
    {
        "id": "candidacies_endorsements",
        "label": "Candidacies & endorsements",
        "terms": (
            "annonce sa candidature",
            "je suis candidate",
            "candidature",
            "se lancer dans la course",
            "soutient",
            "soutien",
            "officialise sa candidature",
            "se declare candidat",
            "se declare candidate",
            "se prepare",
            "entree en campagne",
            "lance sa campagne",
            "ralliement",
            "rejoint",
            "quitte",
            "alliance",
        ),
    },
    {
        "id": "rules_calendar",
        "label": "Rules, calendar & campaign mechanics",
        "terms": (
            "500 signatures",
            "parrainage",
            "dates du premier et du second tour",
            "premier et du second tour fixes",
            "niches parlementaires",
            "referendum",
            "conseil constitutionnel",
            "loi electorale",
            "financement de campagne",
            "temps de parole",
            "pluralisme",
        ),
    },
    {
        "id": "positioning_integrity",
        "label": "Positioning & political image",
        "terms": (
            "probite",
            "ordre et le serieux",
            "redresser la france",
            "incarner",
            "renouveler",
            "presente son programme",
            "devoile son programme",
            "propose un referendum",
            "organise un meeting",
            "reunit ses soutiens",
        ),
    },
    {
        "id": "polls_race",
        "label": "Polling & race narratives",
        "terms": (
            "sondage",
            "sondages",
            "predisant la victoire",
            "victoire de",
        ),
    },
)

CAMPAIGN_AGENDA_SUPPORT_LIMIT = 5
CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS = 2
MATERIAL_TOPIC_IDS = {
    "legal_eligibility",
    "selection_strategy",
    "candidacies_endorsements",
    "rules_calendar",
    "positioning_integrity",
    "polls_race",
}
ELECTION_CONTEXT_TERMS = (
    "presidentielle",
    "election presidentielle",
    "elysee",
    "campagne",
    "candidature",
    "candidat",
    "candidate",
    "primaire",
    "investiture",
    "parrainage",
    "500 signatures",
)
PARTY_CONTEXT_TERMS = (
    "parti socialiste",
    "ps",
    "rassemblement national",
    "rn",
    "renaissance",
    "les republicains",
    "lr",
    "la france insoumise",
    "lfi",
    "place publique",
    "les ecologistes",
    "horizons",
    "modem",
)


STRICT_NOTABLE_TERMS = {
    "legal_eligibility": (
        "parquet national financier",
        "cour de cassation",
        "ineligibilite",
        "condamnation",
        "relaxe",
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
        "mis en examen",
        "mise en examen",
        "ouvre une enquete",
        "reste eligible",
        "devient ineligible",
    ),
    "selection_strategy": (
        "primaire fermee",
        "primaire ouverte",
        "decline la primaire",
        "se prononce pour une primaire",
        "enterre la primaire",
        "acte la rupture",
        "vote du 9 juillet",
        "vote organise",
        "strategie de designation",
        "designation d un candidat",
        "designer un candidat",
        "investiture",
        "est designe",
        "est designee",
    ),
    "candidacies_endorsements": (
        "annonce sa candidature",
        "officialise sa candidature",
        "se declare candidat",
        "se declare candidate",
        "je suis candidat",
        "je suis candidate",
        "se lance dans la course",
        "se lancer dans la course",
        "se retire de la course",
        "renonce a se presenter",
        "se prepare",
        "entree en campagne",
        "lance sa campagne",
        "rejoint la campagne",
        "quitte la campagne",
        "ralliement",
        "soutient la candidature",
        "soutien a la candidature",
        "soutient",
    ),
    "rules_calendar": (
        "500 signatures",
        "parrainage",
        "dates du premier et du second tour",
        "premier et du second tour fixes",
        "calendrier de l election",
        "calendrier presidentiel",
        "loi electorale",
        "financement de campagne",
        "temps de parole",
        "pluralisme",
    ),
    "positioning_integrity": (
        "presente son programme",
        "devoile son programme",
        "propose un referendum",
        "envisage un referendum",
        "envisageant la piste d un referendum",
        "organise un meeting",
        "reunit ses soutiens",
    ),
    "polls_race": (
        "sondage",
        "sondages",
    ),
}

NON_PRESIDENTIAL_ELECTION_TERMS = (
    "senatoriales",
    "legislatives",
    "municipales",
    "europeennes",
    "regionales",
    "departementales",
)


def normalize(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()

    if not text:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_feed_datetime(value: Any) -> datetime | None:
    text = clean_text(value)

    if not text:
        return None

    try:
        parsed = parsedate_to_datetime(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def canonical_url(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    parts = urlsplit(text)

    retained_query = [
        (key, query_value)
        for key, query_value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if key.lower() not in TRACKING_PARAMETERS
    ]

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower().removeprefix("www."),
            parts.path.rstrip("/"),
            urlencode(retained_query),
            "",
        )
    )


def request_bytes(url: str) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/xml, text/xml, */*;q=0.5"
            ),
            "User-Agent": "Mozilla/5.0 FR27SignalLab-news-wire/1.0",
        },
    )

    with urlopen(
        request,
        timeout=60,
        context=ssl.create_default_context(),
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                f"{url} returned HTTP {response.status}"
            )

        content = response.read()

        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            content = gzip.decompress(content)

        return content, response.geturl()


def first_child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if local_name(child.tag) in names:
            if child.text and child.text.strip():
                return clean_text(child.text)

    return ""


def entry_link(element: ET.Element) -> str:
    for child in element:
        if local_name(child.tag) != "link":
            continue

        href = str(child.attrib.get("href") or "").strip()

        if href:
            relationship = str(
                child.attrib.get("rel") or "alternate"
            ).lower()

            if relationship in {"", "alternate"}:
                return href

        if child.text and child.text.strip():
            return child.text.strip()

    return ""


def parse_feed(
    raw: bytes,
    publisher: str,
    feed_url: str,
) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    entries: list[dict[str, Any]] = []

    for element in root.iter():
        if local_name(element.tag) not in {"item", "entry"}:
            continue

        headline = first_child_text(element, {"title"})
        url = entry_link(element)
        published_text = first_child_text(
            element,
            {"pubdate", "published", "updated", "date"},
        )
        summary = first_child_text(
            element,
            {"description", "summary", "content", "encoded"},
        )
        published_at = parse_feed_datetime(published_text)

        if not headline or not url or published_at is None:
            continue

        entries.append(
            {
                "publisher": publisher,
                "feed_url": feed_url,
                "headline": headline,
                "summary": summary,
                "url": url,
                "canonical_url": canonical_url(url),
                "published_at": published_at,
            }
        )

    if not entries:
        raise RuntimeError(
            f"{publisher} feed contained no usable dated entries"
        )

    return entries


def find_event_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    if isinstance(payload, dict):
        for key in ("polls", "events", "rows", "data"):
            value = payload.get(key)

            if isinstance(value, list):
                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

    raise RuntimeError(
        "Could not locate the poll-event list in polls.json"
    )


def recent_candidate_roster(
    polls_path: Path,
    generated_at: datetime,
    days: int = 183,
) -> tuple[list[str], str]:
    payload = json.loads(
        polls_path.read_text(encoding="utf-8")
    )
    events = find_event_list(payload)
    cutoff = generated_at.date() - timedelta(days=days)
    names: set[str] = set()

    for event in events:
        event_round = str(event.get("round") or "").strip()

        if event_round and event_round != "first_round":
            continue

        event_date = None

        for field in (
            "publication_date",
            "published_date",
            "fieldwork_end",
            "fieldwork_start",
        ):
            event_date = parse_iso_date(event.get(field))

            if event_date is not None:
                break

        if event_date is None or event_date < cutoff:
            continue

        candidates = event.get("candidates")

        if not isinstance(candidates, list):
            continue

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            name = str(candidate.get("name") or "").strip()

            if name:
                names.add(name)

    if not names:
        raise RuntimeError(
            "No candidates appeared in first-round polling "
            "during the previous six months"
        )

    return sorted(names), cutoff.isoformat()


def explicit_election_match(normalized_headline: str) -> bool:
    return any(
        pattern.search(normalized_headline)
        for pattern in ELECTION_PATTERNS
    )


def campaign_agenda_term_matches(
    normalized_headline: str,
    terms: tuple[str, ...],
) -> list[str]:
    padded = f" {normalized_headline} "
    return [
        term
        for term in terms
        if f" {term} " in padded
    ]


def classify_campaign_agenda(
    normalized_headline: str,
) -> dict[str, Any]:
    scored_topics: list[
        tuple[int, int, dict[str, Any], list[str]]
    ] = []

    for position, topic in enumerate(CAMPAIGN_AGENDA_TOPICS):
        matches = campaign_agenda_term_matches(
            normalized_headline,
            topic["terms"],
        )

        if matches:
            scored_topics.append(
                (len(matches), -position, topic, matches)
            )

    if not scored_topics:
        return {
            "id": "other_campaign",
            "label": "Other campaign coverage",
            "matched_terms": [],
        }

    _score, _position, topic, matches = max(
        scored_topics,
        key=lambda item: (item[0], item[1]),
    )

    return {
        "id": topic["id"],
        "label": topic["label"],
        "matched_terms": matches,
    }


def classify_notable_development(
    normalized_text: str,
    matched_candidates: list[str],
    source: dict[str, Any],
    normalized_headline: str | None = None,
) -> dict[str, Any] | None:
    """Return only concrete developments tied to the presidential race.

    The full RSS text may provide context, but a politics-section source is not
    itself evidence that an ordinary law, ministerial decision, appointment,
    or another election is a presidential-race development.
    """

    del source  # source scope is metadata, not a substitute for race context

    headline_text = normalized_headline or normalized_text
    strict_topics: list[
        tuple[int, int, dict[str, Any], list[str]]
    ] = []
    for position, topic in enumerate(CAMPAIGN_AGENDA_TOPICS):
        # A material action or outcome must appear in the headline.
        # The RSS summary may establish election context, but it must never
        # manufacture the event itself.
        strict_matches = campaign_agenda_term_matches(
            headline_text,
            STRICT_NOTABLE_TERMS.get(topic["id"], ()),
        )
        if strict_matches:
            strict_topics.append(
                (len(strict_matches), -position, topic, strict_matches)
            )

    if not strict_topics:
        return None

    _score, _position, topic, strict_matches = max(
        strict_topics,
        key=lambda item: (item[0], item[1]),
    )
    topic_id = topic["id"]

    padded_text = f" {normalized_text} "
    padded_headline = f" {headline_text} "
    has_election_context = any(
        term in normalized_text
        for term in ELECTION_CONTEXT_TERMS
    )
    has_presidential_context = any(
        term in normalized_text
        for term in (
            "presidentielle",
            "election presidentielle",
            "elysee",
            "course a l elysee",
        )
    )
    has_other_election_context = any(
        term in normalized_text
        for term in NON_PRESIDENTIAL_ELECTION_TERMS
    )
    has_party_context = any(
        f" {term} " in padded_text
        for term in PARTY_CONTEXT_TERMS
    )
    has_party_in_headline = any(
        f" {term} " in padded_headline
        for term in PARTY_CONTEXT_TERMS
    )
    has_candidate_in_headline = any(
        normalize(candidate) in headline_text
        for candidate in matched_candidates
        if normalize(candidate)
    )

    result = {
        "id": topic_id,
        "label": topic["label"],
        "matched_terms": strict_matches,
    }

    if topic_id == "legal_eligibility":
        # Candidate-specific legal consequences may matter without the word
        # "presidential", but the monitored figure must be in the headline.
        return result if has_candidate_in_headline else None

    if has_other_election_context and not has_presidential_context:
        return None

    if topic_id == "selection_strategy":
        return result if (
            has_election_context
            and (
                has_candidate_in_headline
                or has_party_in_headline
                or has_party_context
            )
        ) else None

    if topic_id == "candidacies_endorsements":
        return result if (
            has_election_context
            and (has_candidate_in_headline or has_party_in_headline)
        ) else None

    if topic_id == "rules_calendar":
        return result if has_presidential_context else None

    if topic_id == "positioning_integrity":
        return result if (
            has_presidential_context and has_candidate_in_headline
        ) else None

    if topic_id == "polls_race":
        return result if has_presidential_context else None

    return None


def build_campaign_agenda(
    relevant_news: list[dict[str, Any]],
    window_days: int,
) -> dict[str, Any]:
    topic_items: dict[str, list[dict[str, Any]]] = {}
    topic_labels: dict[str, str] = {}

    for item in relevant_news:
        if item.get("development_category"):
            classification = {
                "id": item["development_category"],
                "label": item.get("development_label") or item["development_category"],
                "matched_terms": item.get("matched_terms", []),
            }
        else:
            classification = classify_campaign_agenda(
                normalize(item["headline"])
            )
        topic_id = classification["id"]
        topic_labels[topic_id] = classification["label"]

        topic_items.setdefault(topic_id, []).append(
            {
                "id": item["id"],
                "publisher": item["publisher"],
                "published_at": item["published_at"],
                "headline": item["headline"],
                "url": item["url"],
                "candidates": item["candidates"],
                "matched_terms": classification["matched_terms"],
            }
        )

    topics: list[dict[str, Any]] = []

    for topic_id, items in topic_items.items():
        items.sort(
            key=lambda item: item["published_at"],
            reverse=True,
        )
        publishers = sorted(
            {item["publisher"] for item in items}
        )
        active_days = sorted(
            {item["published_at"][:10] for item in items}
        )
        source_days = {
            (item["publisher"], item["published_at"][:10])
            for item in items
        }

        topics.append(
            {
                "id": topic_id,
                "label": topic_labels[topic_id],
                "item_count": len(items),
                "publisher_count": len(publishers),
                "publisher_names": publishers,
                "source_day_count": len(source_days),
                "active_day_count": len(active_days),
                "display_eligible": (
                    len(source_days)
                    >= CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
                ),
                "supporting_items": items[
                    :CAMPAIGN_AGENDA_SUPPORT_LIMIT
                ],
            }
        )

    topics.sort(
        key=lambda topic: (
            -topic["display_eligible"],
            -topic["source_day_count"],
            -topic["item_count"],
            topic["label"],
        )
    )

    return {
        "window_days": window_days,
        "input_item_count": len(relevant_news),
        "method": "accepted_relevant_news_by_campaign_theme",
        "display_min_source_days": (
            CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        ),
        "topics": topics,
    }


def make_item_id(canonical: str, publisher: str, headline: str) -> str:
    identity = canonical or f"{publisher}|{headline}"

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:20]


def public_item(
    entry: dict[str, Any],
    candidates: list[str],
    explicit_election: bool,
) -> dict[str, Any]:
    return {
        "id": make_item_id(
            entry["canonical_url"],
            entry["publisher"],
            entry["headline"],
        ),
        "publisher": entry["publisher"],
        "published_at": (
            entry["published_at"]
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "headline": entry["headline"],
        "url": entry["url"],
        "explicit_election": explicit_election,
        "candidates": candidates,
    }


def public_notable_item(
    entry: dict[str, Any],
    candidates: list[str],
    classification: dict[str, Any],
) -> dict[str, Any]:
    item = public_item(entry, candidates, False)
    item.update(
        {
            "development_category": classification["id"],
            "development_label": classification["label"],
            "matched_terms": classification["matched_terms"],
        }
    )
    return item


def limit_items(items: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
    """Return every item when max_items is zero; otherwise apply a safety cap."""

    return items if max_items == 0 else items[:max_items]


def validate_output(payload: dict[str, Any]) -> None:
    sources = payload.get("sources")
    election_news = payload.get("election_news")
    notable_developments = payload.get("notable_developments")
    candidate_watch = payload.get("candidate_watch")

    campaign_agenda = payload.get("campaign_agenda")

    if not isinstance(campaign_agenda, dict):
        raise RuntimeError("campaign_agenda is not an object")

    agenda_topics = campaign_agenda.get("topics")

    if not isinstance(agenda_topics, list):
        raise RuntimeError("campaign_agenda topics is not a list")

    agenda_ids: set[str] = set()

    for topic in agenda_topics:
        required = {
            "id",
            "label",
            "item_count",
            "publisher_count",
            "publisher_names",
            "source_day_count",
            "active_day_count",
            "display_eligible",
            "supporting_items",
        }

        if set(topic) != required:
            raise RuntimeError(
                "campaign_agenda topic has unexpected fields"
            )

        if topic["id"] in agenda_ids:
            raise RuntimeError(
                "campaign_agenda contains duplicate topic ids"
            )

        if topic["item_count"] < len(topic["supporting_items"]):
            raise RuntimeError(
                "campaign_agenda supporting item count is invalid"
            )

        agenda_ids.add(topic["id"])

    if not isinstance(sources, list) or len(sources) != len(SOURCES):
        raise RuntimeError("Unexpected source-status structure")

    successful_sources = [
        source
        for source in sources
        if source.get("status") == "ok"
    ]

    if len(successful_sources) < 4:
        raise RuntimeError(
            f"Only {len(successful_sources)} publisher feeds succeeded"
        )

    for list_name, items in (
        ("election_news", election_news),
        ("candidate_watch", candidate_watch),
    ):
        if not isinstance(items, list):
            raise RuntimeError(f"{list_name} is not a list")

        ids: set[str] = set()

        for item in items:
            required = {
                "id",
                "publisher",
                "published_at",
                "headline",
                "url",
                "explicit_election",
                "candidates",
            }

            if set(item) != required:
                raise RuntimeError(
                    f"{list_name} item has unexpected fields"
                )

            if not item["headline"] or not item["publisher"]:
                raise RuntimeError(
                    f"{list_name} contains an empty headline or publisher"
                )

            if not str(item["url"]).startswith(("http://", "https://")):
                raise RuntimeError(
                    f"{list_name} contains an invalid URL"
                )

            if item["id"] in ids:
                raise RuntimeError(
                    f"{list_name} contains duplicate item ids"
                )

            ids.add(item["id"])

    if not isinstance(notable_developments, list):
        raise RuntimeError("notable_developments is not a list")
    notable_ids: set[str] = set()
    for item in notable_developments:
        required = {
            "id",
            "publisher",
            "published_at",
            "headline",
            "url",
            "explicit_election",
            "candidates",
            "development_category",
            "development_label",
            "matched_terms",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError("notable_developments item has unexpected fields")
        if item["development_category"] not in MATERIAL_TOPIC_IDS:
            raise RuntimeError("notable_developments has an invalid category")
        if not isinstance(item["matched_terms"], list) or not item["matched_terms"]:
            raise RuntimeError("notable_developments lacks material matched terms")
        if item["id"] in notable_ids:
            raise RuntimeError("notable_developments contains duplicate item ids")
        notable_ids.add(item["id"])

    expected_counts = {
        "election_news": len(election_news),
        "notable_developments": len(notable_developments),
        "relevant_news": len(election_news) + len(notable_developments),
        "candidate_watch": len(candidate_watch),
    }
    for field, expected in expected_counts.items():
        if payload.get("counts", {}).get(field) != expected:
            raise RuntimeError(f"News-wire count {field} is invalid")

    if not election_news and not notable_developments and not candidate_watch:
        raise RuntimeError(
            "The generated wire contains no matching news items"
        )


def build_wire(
    polls_path: Path,
    window_days: int,
    max_items: int,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    window_start = generated_at - timedelta(days=window_days)
    candidates, candidate_cutoff = recent_candidate_roster(
        polls_path,
        generated_at,
    )
    normalized_candidates = {
        candidate: normalize(candidate)
        for candidate in candidates
    }

    source_status: list[dict[str, Any]] = []
    all_entries: list[dict[str, Any]] = []

    for source in SOURCES:
        started_at = datetime.now(timezone.utc)

        try:
            raw, final_feed_url = request_bytes(source["feed_url"])
            entries = parse_feed(
                raw,
                source["name"],
                final_feed_url,
            )
            recent_entries = [
                entry
                for entry in entries
                if entry["published_at"] >= window_start
            ]
            for entry in entries:
                entry["source_id"] = source["source_id"]
                entry["politics_specific"] = bool(source.get("politics_specific"))

            latest = max(
                (
                    entry["published_at"]
                    for entry in entries
                ),
                default=None,
            )

            source_status.append(
                {
                    "name": source["name"],
                    "feed_url": final_feed_url,
                    "status": "ok",
                    "items_seen": len(entries),
                    "recent_items": len(recent_entries),
                    "latest_published_at": (
                        latest.isoformat().replace("+00:00", "Z")
                        if latest is not None
                        else None
                    ),
                    "error": None,
                }
            )
            all_entries.extend(recent_entries)
        except Exception as error:
            source_status.append(
                {
                    "name": source["name"],
                    "feed_url": source["feed_url"],
                    "status": "error",
                    "items_seen": 0,
                    "recent_items": 0,
                    "latest_published_at": None,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

        elapsed = (
            datetime.now(timezone.utc) - started_at
        ).total_seconds()

        source_status[-1]["response_seconds"] = round(elapsed, 2)

    deduplicated: dict[str, dict[str, Any]] = {}

    for entry in sorted(
        all_entries,
        key=lambda item: item["published_at"],
        reverse=True,
    ):
        key = (
            entry["canonical_url"]
            or normalize(entry["headline"])
        )

        if key not in deduplicated:
            deduplicated[key] = entry

    election_news: list[dict[str, Any]] = []
    notable_developments: list[dict[str, Any]] = []
    candidate_watch: list[dict[str, Any]] = []

    source_by_id = {source["source_id"]: source for source in SOURCES}

    for entry in deduplicated.values():
        combined_text = normalize(
            f"{entry['headline']} {entry.get('summary') or ''}"
        )
        matched_candidates = [
            candidate
            for candidate, normalized_name
            in normalized_candidates.items()
            if normalized_name in combined_text
        ]
        is_election_news = explicit_election_match(combined_text)
        base_item = public_item(
            entry,
            matched_candidates,
            is_election_news,
        )

        if is_election_news:
            election_news.append(base_item)
        else:
            source = source_by_id.get(entry.get("source_id"), {})
            classification = classify_notable_development(
                combined_text,
                matched_candidates,
                source,
                normalize(entry["headline"]),
            )
            if classification is not None:
                notable_developments.append(
                    public_notable_item(
                        entry,
                        matched_candidates,
                        classification,
                    )
                )

        if matched_candidates:
            candidate_watch.append(base_item)

    for items in (election_news, notable_developments, candidate_watch):
        items.sort(
            key=lambda item: item["published_at"],
            reverse=True,
        )

    election_news = limit_items(election_news, max_items)
    notable_developments = limit_items(notable_developments, max_items)
    candidate_watch = limit_items(candidate_watch, max_items)

    campaign_agenda = build_campaign_agenda(
        [*election_news, *notable_developments],
        window_days,
    )

    payload = {
        "schema_version": 1,
        "generated_at": (
            generated_at.isoformat().replace("+00:00", "Z")
        ),
        "window_days": window_days,
        "candidate_roster": {
            "rule": (
                "Figures appearing in first-round polling "
                "during the previous six months"
            ),
            "cutoff_date": candidate_cutoff,
            "count": len(candidates),
            "names": candidates,
        },
        "sources": source_status,
        "counts": {
            "successful_sources": sum(
                source["status"] == "ok"
                for source in source_status
            ),
            "unique_recent_feed_items": len(deduplicated),
            "election_news": len(election_news),
            "notable_developments": len(notable_developments),
            "relevant_news": len(election_news) + len(notable_developments),
            "candidate_watch": len(candidate_watch),
        },
        "campaign_agenda": campaign_agenda,
        "election_news": election_news,
        "notable_developments": notable_developments,
        "candidate_watch": candidate_watch,
    }

    validate_output(payload)

    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--polls",
        type=Path,
        default=Path("polls.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("news_wire.json"),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
    )
    arguments = parser.parse_args()

    if arguments.window_days < 1:
        raise RuntimeError("--window-days must be positive")

    if arguments.max_items < 0:
        raise RuntimeError("--max-items must be zero (unlimited) or positive")

    payload = build_wire(
        arguments.polls,
        arguments.window_days,
        arguments.max_items,
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_output = arguments.output.with_suffix(
        arguments.output.suffix + ".tmp"
    )

    temporary_output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary_output.replace(arguments.output)

    counts = payload["counts"]

    print("Election News Wire generated.")
    print(
        f"Candidate roster: "
        f"{payload['candidate_roster']['count']}"
    )
    print(
        f"Successful feeds: "
        f"{counts['successful_sources']}/{len(SOURCES)}"
    )
    print(
        f"Unique recent feed items: "
        f"{counts['unique_recent_feed_items']}"
    )
    print(
        f"Election News items: "
        f"{counts['election_news']}"
    )
    print(
        f"Notable Development items: "
        f"{counts['notable_developments']}"
    )
    print(
        f"All relevant news items: "
        f"{counts['relevant_news']}"
    )
    print(
        f"Candidate Watch items: "
        f"{counts['candidate_watch']}"
    )
    print(f"Output: {arguments.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
