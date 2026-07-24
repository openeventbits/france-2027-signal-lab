#!/usr/bin/env python3
"""Build the FR27 Signal Lab election news wire from direct and discovery feeds."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import re
from threading import BoundedSemaphore
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from http_fetch import (
    DEFAULT_MAX_RESPONSE_BYTES,
    HttpFetchResult,
    fetch_news_route,
)
from source_health import (
    load_source_health,
    update_source_health,
    write_source_health_atomic,
)


SOURCE_CONFIG_PATH = Path(__file__).with_name("news_sources.json")
SOURCES = tuple(
    json.loads(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
)
DISCOVERY_CONFIG_PATH = Path(__file__).with_name("discovery_queries.json")
DISCOVERY_QUERIES = tuple(
    json.loads(DISCOVERY_CONFIG_PATH.read_text(encoding="utf-8"))
)
PUBLISHER_POLICY_PATH = Path(__file__).with_name("publisher_policy.json")
PUBLISHER_POLICY = json.loads(
    PUBLISHER_POLICY_PATH.read_text(encoding="utf-8")
)

GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_PARAMETERS = {
    "hl": "fr",
    "gl": "FR",
    "ceid": "FR:fr",
}
DIRECT_ENTRY_LIMIT = 20
DISCOVERY_ENTRY_LIMIT = 10
PUBLISHER_SITE_ENTRY_LIMIT = 5
FETCH_TIMEOUT_SECONDS = 12
MAX_NEWS_RESPONSE_BYTES = DEFAULT_MAX_RESPONSE_BYTES
FETCH_WORKERS = 12
GOOGLE_NEWS_WORKERS = 4
GOOGLE_NEWS_SEMAPHORE = BoundedSemaphore(GOOGLE_NEWS_WORKERS)

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

INVENTORY_SCHEMA_VERSION = 3
INVENTORY_SUMMARY_MAX_CHARS = 1000
INVENTORY_ITEM_FIELDS = {
    "id",
    "source_id",
    "publisher",
    "feed_url",
    "politics_specific",
    "headline",
    "summary",
    "url",
    "canonical_url",
    "published_at",
    "first_seen_at",
    "last_seen_at",
    "candidate_names",
    "relevance_reason",
    "relevance_terms",
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
            "propose un accord",
            "propose une alliance",
            "propose une coalition",
            "conclut un accord",
            "rejoint une alliance",
            "quitte une coalition",
            "pose ses conditions",
            "fixe un ultimatum",
            "ultimatum",
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
        "propose un accord",
        "propose une alliance",
        "propose une coalition",
        "conclut un accord",
        "rejoint une alliance",
        "quitte une coalition",
        "pose ses conditions",
        "fixe un ultimatum",
        "ultimatum",
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

# Broad article-level relevance is intentionally less strict than the
# Recent Changes event gate, but generic office words such as "Elysee",
# "president", or a bare year must never establish race relevance.
RELEVANT_PRESIDENTIAL_TERMS = (
    "presidentielle",
    "election presidentielle",
    "prochaine presidentielle",
    "course a l elysee",
    "elysee 2027",
    "500 signatures",
    "parrainage presidentiel",
    "parrainages presidentiels",
)

RELEVANT_CAMPAIGN_TERMS = (
    "candidature",
    "candidat",
    "candidate",
    "campagne",
    "primaire",
    "investiture",
    "programme",
    "meeting",
    "ralliement",
    "soutien",
    "alliance",
    "coalition",
    "strategie",
    "sondage",
    "sondages",
    "intentions de vote",
    "presidentiable",
    "se prepare",
    "se lancer",
    "renonce",
    "se retire",
    "designation",
    "vote des adherents",
)

# A summary may confirm race relevance only when the headline already
# carries a plausible campaign, candidate, party, or selection cue.
RELEVANT_HEADLINE_SUPPORT_TERMS = (
    "2027",
    "parti",
    "calendrier",
    "accord",
    "ultimatum",
    "strategie",
    "positionnement",
    "entretien",
    "interview",
    "candidature",
    "candidat",
    "candidate",
    "campagne",
    "primaire",
    "investiture",
    "programme",
    "alliance",
    "coalition",
    "ralliement",
    "soutien",
    "sondage",
    "parrainage",
)

RELEVANT_ROUTINE_EXCLUSION_TERMS = (
    "reste au gouvernement",
    "rester au gouvernement",
    "demissionner du gouvernement",
    "ministre",
    "gouvernement",
    "loi",
    "projet de loi",
    "proposition de loi",
    "adopte la loi",
    "assemblee nationale",
    "parlement",
    "deputes",
    "senateurs",
    "commission des lois",
    "amendement",
    "defenseur des droits",
    "nomme",
    "nomination",
)

RELEVANT_LIFESTYLE_EXCLUSION_TERMS = (
    "joue au golf",
    "golf",
    "football",
    "sport",
    "concert",
    "festival",
    "vacances",
    "vie privee",
    "people",
    "mode",
    "cuisine",
    "jeu video",
)

HISTORICAL_PRESIDENTIAL_YEAR_PATTERN = re.compile(
    r"\b(?:election\s+)?presidentielle(?:\s+francaise)?(?:\s+de)?\s+((?:19|20)\d{2})\b"
)

STATIC_ENTITY_ROLE_SUFFIXES = (
    "premier ministre",
    "president",
    "presidente",
    "ministre",
    "depute",
    "deputee",
    "senateur",
    "senatrice",
    "candidat",
    "candidate",
)
STATIC_ENTITY_URL_PATTERN = re.compile(r"_DN-\d+(?:\.html)?$")


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


def normalize_domain(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""

    if "://" not in text:
        text = f"https://{text}"

    hostname = urlsplit(text).hostname or ""
    return hostname.lower().removeprefix("www.").rstrip(".")


def publisher_policy_match(domain: Any) -> tuple[str, dict[str, Any]] | None:
    normalized_domain = normalize_domain(domain)
    if not normalized_domain:
        return None

    matching_domains = [
        policy_domain
        for policy_domain in PUBLISHER_POLICY
        if (
            normalized_domain == policy_domain
            or normalized_domain.endswith(f".{policy_domain}")
        )
    ]
    if not matching_domains:
        return None

    policy_domain = max(matching_domains, key=len)
    return policy_domain, PUBLISHER_POLICY[policy_domain]


def build_google_news_url(query: str) -> str:
    parameters = {"q": query, **GOOGLE_NEWS_PARAMETERS}
    return f"{GOOGLE_NEWS_SEARCH_URL}?{urlencode(parameters)}"


def generate_discovery_queries(
    candidates: list[str],
    group_size: int = 4,
) -> list[dict[str, str]]:
    if group_size < 1:
        raise ValueError("group_size must be positive")

    queries = [
        {
            "id": str(query["id"]),
            "label": str(query["label"]),
            "query": str(query["query"]),
            "kind": "static",
        }
        for query in DISCOVERY_QUERIES
        if bool(query.get("enabled", True))
    ]

    for index in range(0, len(candidates), group_size):
        group = candidates[index:index + group_size]
        quoted_names = " OR ".join(
            f'"{candidate}"' for candidate in group
        )
        group_number = (index // group_size) + 1
        queries.append(
            {
                "id": f"candidate-group-{group_number:02d}",
                "label": f"Candidate group {group_number}",
                "query": (
                    f"({quoted_names}) "
                    "(présidentielle OR candidature OR campagne OR 2027) "
                    "when:3d"
                ),
                "kind": "candidate",
            }
        )

    seen_ids: set[str] = set()
    for query in queries:
        if not query["id"] or query["id"] in seen_ids:
            raise RuntimeError("Discovery query ids must be unique and non-empty")
        seen_ids.add(query["id"])
        query["feed_url"] = build_google_news_url(query["query"])

    return queries


def stable_slot(feed_id: str, interval_hours: int) -> int:
    if not isinstance(feed_id, str) or not feed_id.strip():
        raise ValueError("feed_id must be non-empty")
    if type(interval_hours) is not int or interval_hours < 1:
        raise ValueError("interval_hours must be positive")

    digest = hashlib.sha256(feed_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % interval_hours


def publisher_site_interval(tier: str) -> int:
    if tier == "core":
        return 3
    if tier == "extended":
        return 12
    raise ValueError(f"Unsupported publisher tier: {tier}")


def generate_publisher_site_feeds(
    policy: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    publisher_policy = PUBLISHER_POLICY if policy is None else policy
    feeds: list[dict[str, Any]] = []

    for domain in sorted(publisher_policy):
        record = publisher_policy[domain]
        if not bool(record.get("enabled", True)):
            continue
        if record.get("source_type") != "media":
            continue

        tier = str(record.get("tier") or "")
        interval_hours = publisher_site_interval(tier)
        feed_id = f"publisher-site:{domain}"
        query = (
            f"site:{domain} "
            "(\"présidentielle 2027\" OR \"élection présidentielle\" "
            "OR candidature OR primaire OR investiture OR sondage) "
            "when:7d"
        )
        feeds.append(
            {
                "id": feed_id,
                "label": f"{record['name']} — publisher site",
                "publisher": str(record["name"]),
                "domain": domain,
                "tier": tier,
                "query": query,
                "feed_url": build_google_news_url(query),
                "interval_hours": interval_hours,
                "slot": stable_slot(feed_id, interval_hours),
            }
        )

    feed_ids = [feed["id"] for feed in feeds]
    if len(feed_ids) != len(set(feed_ids)):
        raise RuntimeError("Publisher-site feed ids must be unique")

    return feeds


def publisher_site_feed_due(
    feed: dict[str, Any],
    now: datetime,
) -> bool:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    interval_hours = int(feed["interval_hours"])
    expected_slot = stable_slot(str(feed["id"]), interval_hours)
    if int(feed["slot"]) != expected_slot:
        raise ValueError("publisher-site feed slot is inconsistent")

    utc_now = now.astimezone(timezone.utc)
    return utc_now.hour % interval_hours == expected_slot


def build_source_health_routes(
    discovery_queries: list[dict[str, str]],
    publisher_site_feeds: list[dict[str, Any]],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    """Describe every configured route without changing fetch scheduling."""
    routes: list[dict[str, Any]] = []
    for source in SOURCES:
        routes.append(
            {
                "route_id": f"direct:{source['source_id']}",
                "route_type": "direct",
                "publisher": str(source["name"]),
                "domain": normalize_domain(source["feed_url"]),
                "enabled": True,
                "schedule_class": "hourly",
                "schedule_slot": None,
                "due_this_run": True,
            }
        )

    active_discovery_ids = {
        str(query["id"]) for query in discovery_queries
    }
    configured_static_ids: set[str] = set()
    for query in DISCOVERY_QUERIES:
        query_id = str(query["id"])
        configured_static_ids.add(query_id)
        enabled = bool(query.get("enabled", True))
        routes.append(
            {
                "route_id": f"discovery:{query_id}",
                "route_type": "shared_discovery",
                "publisher": None,
                "domain": None,
                "enabled": enabled,
                "schedule_class": "hourly",
                "schedule_slot": None,
                "due_this_run": enabled and query_id in active_discovery_ids,
            }
        )
    for query in discovery_queries:
        query_id = str(query["id"])
        if query_id in configured_static_ids:
            continue
        routes.append(
            {
                "route_id": f"discovery:{query_id}",
                "route_type": "shared_discovery",
                "publisher": None,
                "domain": None,
                "enabled": True,
                "schedule_class": "hourly",
                "schedule_slot": None,
                "due_this_run": True,
            }
        )

    active_site_feeds = {
        str(feed["id"]): feed for feed in publisher_site_feeds
    }
    for domain in sorted(PUBLISHER_POLICY):
        policy = PUBLISHER_POLICY[domain]
        if policy.get("source_type") != "media":
            continue
        tier = str(policy.get("tier") or "")
        interval_hours = publisher_site_interval(tier)
        route_id = f"publisher-site:{domain}"
        enabled = bool(policy.get("enabled", True))
        feed = active_site_feeds.get(route_id)
        slot = (
            int(feed["slot"])
            if feed is not None
            else stable_slot(route_id, interval_hours)
        )
        routes.append(
            {
                "route_id": route_id,
                "route_type": "publisher_site",
                "publisher": str(policy["name"]),
                "domain": domain,
                "enabled": enabled,
                "schedule_class": f"every_{interval_hours}_hours",
                "schedule_slot": slot,
                "due_this_run": (
                    enabled
                    and feed is not None
                    and publisher_site_feed_due(feed, generated_at)
                ),
            }
        )

    route_ids = [route["route_id"] for route in routes]
    if len(route_ids) != len(set(route_ids)):
        raise RuntimeError("Source-health route ids must be unique")
    return sorted(routes, key=lambda route: route["route_id"])


def endpoint_source_health_id(endpoint: dict[str, Any]) -> str:
    if endpoint["kind"] == "direct":
        return f"direct:{endpoint['id']}"
    if endpoint["kind"] == "discovery":
        return f"discovery:{endpoint['id']}"
    if endpoint["kind"] == "publisher_site":
        return str(endpoint["id"])
    raise ValueError(f"Unsupported endpoint kind: {endpoint['kind']}")


def source_entry_health_id(source_id: Any) -> str:
    value = str(source_id or "")
    if value in DIRECT_SOURCE_IDS:
        return f"direct:{value}"
    return value


def route_request_validators(
    previous_source_health: dict[str, Any] | None,
    route_id: str,
    request_url: str,
) -> tuple[str | None, str | None]:
    """Return validators only when they belong to this route and URL."""
    if previous_source_health is None:
        return None, None
    for route in previous_source_health.get("routes", []):
        if route.get("route_id") != route_id:
            continue
        if route.get("validator_url") != request_url:
            return None, None
        etag = route.get("etag")
        last_modified = route.get("last_modified")
        return (
            etag if isinstance(etag, str) else None,
            last_modified if isinstance(last_modified, str) else None,
        )
    return None, None


def google_news_source(element: ET.Element) -> tuple[str, str]:
    for child in element:
        if local_name(child.tag) != "source":
            continue
        name = clean_text(child.text or "")
        domain = normalize_domain(child.attrib.get("url"))
        return name, domain
    return "", ""


def remove_publisher_suffix(headline: str, publisher: str) -> str:
    cleaned_headline = clean_text(headline)
    cleaned_publisher = clean_text(publisher)
    if not cleaned_headline or not cleaned_publisher:
        return cleaned_headline

    suffix = re.compile(
        rf"\s+[-–—]\s+{re.escape(cleaned_publisher)}\s*$",
        flags=re.IGNORECASE,
    )
    return suffix.sub("", cleaned_headline).strip()


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
    *,
    google_news: bool = False,
    max_entries: int | None = None,
    allow_empty: bool = False,
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

        reported_publisher = ""
        publisher_domain = ""
        item_publisher = publisher

        if google_news:
            reported_publisher, publisher_domain = google_news_source(element)
            headline = remove_publisher_suffix(
                headline,
                reported_publisher,
            )
            item_publisher = reported_publisher

        if not headline or not url or published_at is None:
            continue

        entries.append(
            {
                "publisher": item_publisher,
                "reported_publisher": reported_publisher,
                "publisher_domain": publisher_domain,
                "feed_url": feed_url,
                "headline": headline,
                "summary": summary,
                "url": url,
                "canonical_url": canonical_url(url),
                "published_at": published_at,
            }
        )

    if not entries and not allow_empty:
        raise RuntimeError(
            f"{publisher} feed contained no usable dated entries"
        )

    entries.sort(
        key=lambda item: item["published_at"],
        reverse=True,
    )

    if max_entries is not None:
        return entries[:max_entries]

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


def discovery_rejection_reason(
    domain: str,
    policy_match: tuple[str, dict[str, Any]] | None,
) -> str | None:
    if not domain:
        return "unresolved_publisher_domain"
    if policy_match is None:
        return "publisher_not_approved"

    _policy_domain, policy = policy_match
    if not bool(policy.get("enabled", True)):
        return "publisher_disabled"
    if policy.get("source_type") != "media":
        return "non_media_publisher"
    return None


def accept_discovery_entries(
    entries: list[dict[str, Any]],
    query_id: str,
    *,
    source_id_prefix: str = "discovery",
    expected_policy_domain: str | None = None,
    transport: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    resolved_transport = transport or (
        "publisher_site"
        if source_id_prefix == "publisher-site"
        else "shared_discovery"
    )
    if resolved_transport not in {"shared_discovery", "publisher_site"}:
        raise ValueError("Unsupported discovery transport")

    expected_domain = normalize_domain(expected_policy_domain)
    if expected_policy_domain is not None and not expected_domain:
        raise ValueError("expected_policy_domain must resolve to a domain")

    for entry in entries:
        domain = normalize_domain(entry.get("publisher_domain"))
        policy_match = publisher_policy_match(domain)
        rejection_reason = discovery_rejection_reason(
            domain,
            policy_match,
        )

        if (
            rejection_reason is None
            and expected_domain
            and policy_match is not None
            and policy_match[0] != expected_domain
        ):
            rejection_reason = "publisher_site_domain_mismatch"

        if rejection_reason is not None:
            rejected.append(
                {
                    "domain": domain or "unresolved",
                    "reported_publisher": clean_text(
                        entry.get("reported_publisher")
                    ),
                    "query_id": query_id,
                    "headline": clean_text(entry.get("headline")),
                    "rejection_reason": rejection_reason,
                    "transport": resolved_transport,
                }
            )
            continue

        policy_domain, policy = policy_match
        normalized_entry = dict(entry)
        normalized_entry["publisher"] = str(policy["name"])
        normalized_entry["publisher_domain"] = policy_domain
        normalized_entry["source_id"] = (
            f"{source_id_prefix}:{query_id}"
            if source_id_prefix != "publisher-site"
            else query_id
        )
        normalized_entry["politics_specific"] = True
        accepted.append(normalized_entry)

    return accepted, rejected


def aggregate_discovered_publishers(
    rejected: list[dict[str, Any]],
) -> dict[str, Any]:
    by_domain: dict[str, dict[str, Any]] = {}

    for item in rejected:
        domain = item["domain"]
        bucket = by_domain.setdefault(
            domain,
            {
                "domain": domain,
                "reported_publishers": set(),
                "item_count": 0,
                "discovery_query_ids": set(),
                "sample_headlines": [],
                "rejection_reasons": set(),
                "transports": set(),
            },
        )
        reported = item.get("reported_publisher")
        if reported:
            bucket["reported_publishers"].add(reported)
        bucket["item_count"] += 1
        bucket["discovery_query_ids"].add(item["query_id"])
        bucket["rejection_reasons"].add(item["rejection_reason"])
        bucket["transports"].add(
            item.get("transport") or "shared_discovery"
        )
        headline = item.get("headline")
        if (
            headline
            and headline not in bucket["sample_headlines"]
            and len(bucket["sample_headlines"]) < 3
        ):
            bucket["sample_headlines"].append(headline)

    publishers = []
    for domain in sorted(by_domain):
        bucket = by_domain[domain]
        publishers.append(
            {
                "domain": domain,
                "reported_publishers": sorted(
                    bucket["reported_publishers"]
                ),
                "item_count": bucket["item_count"],
                "discovery_query_ids": sorted(
                    bucket["discovery_query_ids"]
                ),
                "sample_headlines": bucket["sample_headlines"],
                "rejection_reasons": sorted(
                    bucket["rejection_reasons"]
                ),
                "transports": sorted(bucket["transports"]),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": None,
        "publisher_count": len(publishers),
        "item_count": sum(
            publisher["item_count"] for publisher in publishers
        ),
        "publishers": publishers,
    }


def count_contributing_media_publishers(
    entries: list[dict[str, Any]],
    policy: dict[str, dict[str, Any]] | None = None,
) -> int:
    publisher_policy = PUBLISHER_POLICY if policy is None else policy
    enabled_media_names = {
        str(record["name"])
        for record in publisher_policy.values()
        if bool(record.get("enabled", True))
        and record.get("source_type") == "media"
    }
    return len(
        {
            str(entry.get("publisher") or "").strip()
            for entry in entries
            if str(entry.get("publisher") or "").strip()
            in enabled_media_names
        }
    )


DIRECT_SOURCE_IDS = frozenset(
    source["source_id"] for source in SOURCES
)


def is_direct_entry(entry: dict[str, Any]) -> bool:
    return str(entry.get("source_id") or "") in DIRECT_SOURCE_IDS


def entry_transport(entry: dict[str, Any]) -> str:
    source_id = str(entry.get("source_id") or "")
    if source_id in DIRECT_SOURCE_IDS:
        return "direct"
    if source_id.startswith("publisher-site:"):
        return "publisher_site"
    if source_id.startswith("discovery:"):
        return "shared_discovery"
    return "unknown"


TRANSPORT_PRIORITY = {
    "unknown": 0,
    "shared_discovery": 1,
    "publisher_site": 2,
    "direct": 3,
}


def transport_priority(entry: dict[str, Any]) -> int:
    return TRANSPORT_PRIORITY[entry_transport(entry)]


def article_signature(entry: dict[str, Any]) -> str:
    published_at = entry.get("published_at")
    if isinstance(published_at, datetime):
        publication_date = published_at.astimezone(timezone.utc).date().isoformat()
    else:
        parsed = parse_feed_datetime(published_at)
        publication_date = (
            parsed.astimezone(timezone.utc).date().isoformat()
            if parsed is not None
            else str(published_at or "")[:10]
        )

    return "|".join(
        (
            normalize(entry.get("publisher")),
            normalize(entry.get("headline")),
            publication_date,
        )
    )


def deduplicate_entries(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    retained: list[dict[str, Any]] = []
    by_url: dict[str, int] = {}
    by_signature: dict[str, int] = {}
    duplicates_removed = 0
    direct_precedence_replacements = 0
    publisher_site_precedence_replacements = 0
    direct_over_publisher_site_replacements = 0
    removed_by_transport = {
        "direct": 0,
        "publisher_site": 0,
        "shared_discovery": 0,
        "unknown": 0,
    }

    for entry in entries:
        url_key = inventory_identity(entry)
        signature = article_signature(entry)
        existing_index = by_url.get(url_key)
        if existing_index is None:
            existing_index = by_signature.get(signature)

        if existing_index is None:
            retained.append(entry)
            index = len(retained) - 1
            by_url[url_key] = index
            by_signature[signature] = index
            continue

        existing = retained[existing_index]
        existing_transport = entry_transport(existing)
        incoming_transport = entry_transport(entry)
        if transport_priority(entry) > transport_priority(existing):
            retained[existing_index] = entry
            by_url[inventory_identity(existing)] = existing_index
            by_url[url_key] = existing_index
            by_signature[signature] = existing_index
            removed_by_transport[existing_transport] += 1
            if (
                incoming_transport == "direct"
                and existing_transport == "shared_discovery"
            ):
                direct_precedence_replacements += 1
            elif (
                incoming_transport == "direct"
                and existing_transport == "publisher_site"
            ):
                direct_over_publisher_site_replacements += 1
            elif (
                incoming_transport == "publisher_site"
                and existing_transport == "shared_discovery"
            ):
                publisher_site_precedence_replacements += 1
        else:
            removed_by_transport[incoming_transport] += 1

        duplicates_removed += 1

    return retained, {
        "duplicates_removed": duplicates_removed,
        "direct_precedence_replacements": direct_precedence_replacements,
        "publisher_site_precedence_replacements": (
            publisher_site_precedence_replacements
        ),
        "direct_over_publisher_site_replacements": (
            direct_over_publisher_site_replacements
        ),
        "removed_by_transport": removed_by_transport,
    }


def explicit_election_match(normalized_headline: str) -> bool:
    return any(
        pattern.search(normalized_headline)
        for pattern in ELECTION_PATTERNS
    )


def current_presidential_matches(normalized_text: str) -> list[str]:
    """Return current-race signals without accepting historical elections."""

    text = normalize(normalized_text)
    historical_years = {
        match.group(1)
        for match in HISTORICAL_PRESIDENTIAL_YEAR_PATTERN.finditer(text)
    }
    if historical_years and "2027" not in historical_years:
        return []

    matches = campaign_agenda_term_matches(
        text,
        RELEVANT_PRESIDENTIAL_TERMS,
    )
    if explicit_election_match(text):
        matches.append("explicit_election")

    return sorted(set(matches))


def is_static_entity_page(
    headline: str,
    url: str,
    matched_candidates: list[str],
) -> bool:
    """Return True for topic/profile pages rather than published articles."""

    normalized_headline = normalize(headline)
    if not normalized_headline:
        return True

    normalized_candidates = [
        normalize(candidate)
        for candidate in matched_candidates
        if normalize(candidate)
    ]

    if normalized_headline in normalized_candidates:
        return True

    for candidate in normalized_candidates:
        if not normalized_headline.startswith(candidate + " "):
            continue
        suffix = normalized_headline[len(candidate):].strip()
        if suffix in STATIC_ENTITY_ROLE_SUFFIXES:
            return True

    path = urlsplit(str(url or "")).path
    return bool(STATIC_ENTITY_URL_PATTERN.search(path))


def classify_relevant_news(
    normalized_headline: str,
    normalized_summary: str,
    matched_candidates: list[str],
) -> dict[str, Any] | None:
    """Classify broad but genuine France 2027 article relevance.

    The headline establishes the article subject. A summary may confirm
    presidential context, but it cannot convert routine government,
    ordinary legislation, lifestyle coverage, or a historical election
    into current-race news.
    """

    headline = normalize(normalized_headline)
    summary = normalize(normalized_summary)

    candidate_in_headline = any(
        normalize(candidate) in headline
        for candidate in matched_candidates
        if normalize(candidate)
    )
    headline_party_matches = campaign_agenda_term_matches(
        headline,
        PARTY_CONTEXT_TERMS,
    )
    combined_party_matches = campaign_agenda_term_matches(
        " ".join(part for part in (headline, summary) if part),
        PARTY_CONTEXT_TERMS,
    )
    combined_campaign_matches = campaign_agenda_term_matches(
        " ".join(part for part in (headline, summary) if part),
        RELEVANT_CAMPAIGN_TERMS,
    )
    headline_support_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_HEADLINE_SUPPORT_TERMS,
    )
    headline_presidential_matches = current_presidential_matches(headline)
    summary_presidential_matches = current_presidential_matches(summary)
    other_election_matches = campaign_agenda_term_matches(
        headline,
        NON_PRESIDENTIAL_ELECTION_TERMS,
    )
    routine_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_ROUTINE_EXCLUSION_TERMS,
    )
    lifestyle_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_LIFESTYLE_EXCLUSION_TERMS,
    )

    # Headline subject exclusions are authoritative. A summary cannot
    # rescue lifestyle coverage or another type of election.
    if lifestyle_matches:
        return None
    if other_election_matches and not headline_presidential_matches:
        return None

    # A current presidential frame in the headline is sufficient, even
    # for analysis or commentary. Historical 2002/2007/2012 retrospectives
    # fail current_presidential_matches().
    if headline_presidential_matches:
        return {
            "reason": "presidential_context",
            "matched_terms": headline_presidential_matches,
        }

    # Routine government and ordinary legislative headlines remain out
    # unless the headline itself explicitly frames them around the race.
    if routine_matches:
        return None

    # The summary can confirm current presidential relevance only when
    # the headline already contains a candidate, named party, or clear
    # campaign/selection cue.
    if summary_presidential_matches and (
        candidate_in_headline
        or headline_party_matches
        or headline_support_matches
    ):
        return {
            "reason": "summary_confirmed_presidential_context",
            "matched_terms": sorted(
                set([
                    *summary_presidential_matches,
                    *headline_party_matches,
                    *headline_support_matches,
                ])
            ),
        }

    # Campaign terms from a summary are not enough by themselves. The
    # headline must name the monitored candidate or political formation.
    if combined_campaign_matches and (
        candidate_in_headline or headline_party_matches
    ):
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": sorted(
                set([
                    *combined_campaign_matches,
                    *combined_party_matches,
                ])
            ),
        }

    # Candidate profiles, interviews, commentary, legal coverage, and
    # substantive political positioning remain valid in this broad lane.
    if candidate_in_headline:
        return {
            "reason": "candidate_political_coverage",
            "matched_terms": ["candidate_in_headline"],
        }

    return None


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


def utc_iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def inventory_identity(entry: dict[str, Any]) -> str:
    canonical = canonical_url(
        entry.get("canonical_url") or entry.get("url")
    )

    if canonical:
        return canonical

    published = entry.get("published_at")
    if isinstance(published, datetime):
        published_text = utc_iso(published)
    else:
        published_text = str(published or "").strip()

    return "|".join(
        (
            str(entry.get("source_id") or ""),
            normalize(entry.get("headline")),
            published_text,
        )
    )


def inventory_summary(value: Any) -> str:
    summary = clean_text(value)
    if len(summary) <= INVENTORY_SUMMARY_MAX_CHARS:
        return summary
    return summary[:INVENTORY_SUMMARY_MAX_CHARS].rstrip()


def empty_inventory(window_days: int) -> dict[str, Any]:
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "generated_at": None,
        "window_days": window_days,
        "items": [],
    }


def load_inventory(
    path: Path | None,
    window_days: int,
) -> dict[str, Any]:
    if path is None or not path.exists():
        return empty_inventory(window_days)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Could not read news inventory {path}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError("News inventory must be an object")
    if payload.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise RuntimeError("Unsupported news inventory schema")
    if not isinstance(payload.get("items"), list):
        raise RuntimeError("News inventory items must be a list")

    seen_ids: set[str] = set()
    seen_keys: set[str] = set()

    for item in payload["items"]:
        if not isinstance(item, dict) or set(item) != INVENTORY_ITEM_FIELDS:
            raise RuntimeError(
                "News inventory item has unexpected fields"
            )
        if item["id"] in seen_ids:
            raise RuntimeError("News inventory contains duplicate ids")
        if parse_feed_datetime(item["published_at"]) is None:
            raise RuntimeError(
                "News inventory item has invalid published_at"
            )
        if parse_feed_datetime(item["first_seen_at"]) is None:
            raise RuntimeError(
                "News inventory item has invalid first_seen_at"
            )
        if parse_feed_datetime(item["last_seen_at"]) is None:
            raise RuntimeError(
                "News inventory item has invalid last_seen_at"
            )
        candidate_names = item.get("candidate_names")
        if (
            not isinstance(candidate_names, list)
            or any(
                not isinstance(candidate, str) or not candidate.strip()
                for candidate in candidate_names
            )
            or len(candidate_names) != len(set(candidate_names))
        ):
            raise RuntimeError(
                "News inventory item has invalid candidate_names"
            )
        relevance_reason = item.get("relevance_reason")
        relevance_terms = item.get("relevance_terms")
        if relevance_reason is not None and (
            not isinstance(relevance_reason, str)
            or not relevance_reason.strip()
        ):
            raise RuntimeError(
                "News inventory item has invalid relevance_reason"
            )
        if (
            not isinstance(relevance_terms, list)
            or any(
                not isinstance(term, str) or not term.strip()
                for term in relevance_terms
            )
            or len(relevance_terms) != len(set(relevance_terms))
        ):
            raise RuntimeError(
                "News inventory item has invalid relevance_terms"
            )
        if relevance_reason is None and relevance_terms:
            raise RuntimeError(
                "News inventory relevance terms require a reason"
            )
        key = inventory_identity(item)
        if key in seen_keys:
            raise RuntimeError(
                "News inventory contains duplicate article identities"
            )
        seen_ids.add(item["id"])
        seen_keys.add(key)

    return payload


def inventory_item_from_entry(
    entry: dict[str, Any],
    first_seen_at: str,
    last_seen_at: str,
) -> dict[str, Any]:
    canonical = canonical_url(
        entry.get("canonical_url") or entry.get("url")
    )
    identity = inventory_identity(entry)

    return {
        "id": hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:20],
        "source_id": str(entry.get("source_id") or ""),
        "publisher": str(entry.get("publisher") or ""),
        "feed_url": str(entry.get("feed_url") or ""),
        "politics_specific": bool(entry.get("politics_specific")),
        "headline": clean_text(entry.get("headline")),
        "summary": inventory_summary(entry.get("summary")),
        "url": str(entry.get("url") or "").strip(),
        "canonical_url": canonical,
        "published_at": utc_iso(entry["published_at"]),
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        # Preserve candidate associations derived from the complete RSS
        # title and summary before the stored summary is shortened.
        "candidate_names": sorted(
            {
                str(candidate).strip()
                for candidate in entry.get("candidate_names", [])
                if str(candidate).strip()
            }
        ),
        # Preserve broad relevance derived from the complete feed text
        # before the stored summary is shortened.
        "relevance_reason": (
            str(entry.get("relevance_reason")).strip()
            if entry.get("relevance_reason")
            else None
        ),
        "relevance_terms": sorted(
            {
                str(term).strip()
                for term in entry.get("relevance_terms", [])
                if str(term).strip()
            }
        ),
    }


def inventory_entry(item: dict[str, Any]) -> dict[str, Any]:
    published_at = parse_feed_datetime(item["published_at"])
    if published_at is None:
        raise RuntimeError(
            "News inventory item has invalid published_at"
        )

    return {
        "source_id": item["source_id"],
        "publisher": item["publisher"],
        "feed_url": item["feed_url"],
        "politics_specific": item["politics_specific"],
        "headline": item["headline"],
        "summary": item["summary"],
        "url": item["url"],
        "canonical_url": item["canonical_url"],
        "published_at": published_at,
        "candidate_names": list(item["candidate_names"]),
        "relevance_reason": item["relevance_reason"],
        "relevance_terms": list(item["relevance_terms"]),
    }


def merge_inventory(
    existing: dict[str, Any],
    current_entries: list[dict[str, Any]],
    generated_at: datetime,
    window_days: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    """Merge one feed snapshot into the retained rolling inventory."""

    window_start = generated_at - timedelta(days=window_days)
    seen_at = utc_iso(generated_at)
    retained: dict[str, dict[str, Any]] = {}
    retained_by_signature: dict[str, str] = {}
    expired_items = 0

    for item in existing.get("items", []):
        published_at = parse_feed_datetime(item.get("published_at"))
        if published_at is None or published_at < window_start:
            expired_items += 1
            continue
        key = inventory_identity(item)
        signature = article_signature(item)
        previous_key = retained_by_signature.get(signature)

        if previous_key is not None:
            previous = retained[previous_key]
            if transport_priority(item) > transport_priority(previous):
                del retained[previous_key]
                retained[key] = dict(item)
                retained_by_signature[signature] = key
            continue

        retained[key] = dict(item)
        retained_by_signature[signature] = key

    current_snapshot: dict[str, dict[str, Any]] = {}
    for entry in sorted(
        current_entries,
        key=lambda item: item["published_at"],
        reverse=True,
    ):
        if entry["published_at"] < window_start:
            continue
        key = inventory_identity(entry)
        if key not in current_snapshot:
            current_snapshot[key] = entry

    new_items = 0
    refreshed_items = 0

    for key, entry in current_snapshot.items():
        previous = retained.get(key)
        signature = article_signature(entry)
        signature_key = retained_by_signature.get(signature)

        if previous is None and signature_key is not None:
            signature_previous = retained[signature_key]

            if (
                transport_priority(entry)
                > transport_priority(signature_previous)
            ):
                previous = signature_previous
                del retained[signature_key]
            else:
                continue

        first_seen_at = (
            previous["first_seen_at"]
            if previous is not None
            else seen_at
        )
        candidate = inventory_item_from_entry(
            entry,
            first_seen_at,
            seen_at,
        )

        if previous is None:
            new_items += 1
            retained[key] = candidate
            retained_by_signature[signature] = key
            continue

        stable_candidate = dict(candidate)
        stable_candidate["last_seen_at"] = previous["last_seen_at"]

        if stable_candidate == previous:
            retained[key] = previous
        else:
            refreshed_items += 1
            retained[key] = candidate
        retained_by_signature[signature] = key

    items = sorted(
        retained.values(),
        key=lambda item: item["published_at"],
        reverse=True,
    )

    unchanged = (
        items == existing.get("items", [])
        and existing.get("window_days") == window_days
        and existing.get("schema_version") == INVENTORY_SCHEMA_VERSION
    )

    inventory_payload = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "generated_at": (
            existing.get("generated_at")
            if unchanged
            else seen_at
        ),
        "window_days": window_days,
        "items": items,
    }

    entries = [inventory_entry(item) for item in items]
    stats = {
        "current_feed_snapshot_items": len(current_snapshot),
        "new_items_discovered": new_items,
        "refreshed_inventory_items": refreshed_items,
        "expired_inventory_items": expired_items,
        "retained_inventory_items": len(items),
    }

    return inventory_payload, entries, stats


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


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


def public_relevant_item(
    entry: dict[str, Any],
    candidates: list[str],
    explicit_election: bool,
    classification: dict[str, Any],
) -> dict[str, Any]:
    item = public_item(entry, candidates, explicit_election)
    item.update(
        {
            "relevance_reason": classification["reason"],
            "relevance_terms": classification["matched_terms"],
        }
    )
    return item


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
    relevant_news = payload.get("relevant_news")
    candidate_watch = payload.get("candidate_watch")
    discovery = payload.get("discovery")

    if not isinstance(discovery, dict):
        raise RuntimeError("discovery is not an object")

    configured_queries = discovery.get("configured_queries")
    successful_queries = discovery.get("successful_queries")

    if type(configured_queries) is not int or configured_queries < 1:
        raise RuntimeError("discovery configured_queries is invalid")
    if (
        type(successful_queries) is not int
        or successful_queries < 0
        or successful_queries > configured_queries
    ):
        raise RuntimeError("discovery successful_queries is invalid")

    for field in (
        "accepted_items_before_deduplication",
        "accepted_items_after_deduplication",
        "quarantined_items",
        "distinct_accepted_publishers",
        "duplicates_removed",
        "direct_precedence_replacements",
    ):
        value = discovery.get(field)
        if type(value) is not int or value < 0:
            raise RuntimeError(f"discovery {field} is invalid")

    accepted_before = discovery[
        "accepted_items_before_deduplication"
    ]
    accepted_after = discovery[
        "accepted_items_after_deduplication"
    ]
    if accepted_after > accepted_before:
        raise RuntimeError(
            "discovery accepted item counts are inconsistent"
        )

    approved_domains = discovery.get("approved_publisher_domains")
    approved_media_domains = discovery.get("approved_media_domains")
    if type(approved_domains) is not int or approved_domains < 1:
        raise RuntimeError(
            "discovery approved_publisher_domains is invalid"
        )
    if (
        type(approved_media_domains) is not int
        or approved_media_domains < 1
        or approved_media_domains > approved_domains
    ):
        raise RuntimeError(
            "discovery approved_media_domains is invalid"
        )

    if (
        discovery["direct_precedence_replacements"]
        > discovery["duplicates_removed"]
    ):
        raise RuntimeError(
            "discovery direct precedence count is invalid"
        )

    discovery_queries = discovery.get("queries")
    if (
        not isinstance(discovery_queries, list)
        or len(discovery_queries) != configured_queries
    ):
        raise RuntimeError("discovery queries structure is invalid")

    discovery_query_ids: set[str] = set()
    successful_query_records = 0
    accepted_query_items = 0
    quarantined_query_items = 0
    for query in discovery_queries:
        if not isinstance(query, dict):
            raise RuntimeError("discovery query is not an object")

        query_id = query.get("id")
        if (
            not isinstance(query_id, str)
            or not query_id.strip()
            or query_id in discovery_query_ids
        ):
            raise RuntimeError("discovery query ids are invalid")
        discovery_query_ids.add(query_id)

        status = query.get("status")
        if status not in {"ok", "error"}:
            raise RuntimeError("discovery query status is invalid")
        successful_query_records += status == "ok"

        for field in ("accepted_items", "quarantined_items"):
            value = query.get(field)
            if type(value) is not int or value < 0:
                raise RuntimeError(
                    f"discovery query {field} is invalid"
                )
        accepted_query_items += query["accepted_items"]
        quarantined_query_items += query["quarantined_items"]

    if accepted_before != accepted_query_items:
        raise RuntimeError(
            "discovery accepted item count does not match queries"
        )
    if discovery["quarantined_items"] != quarantined_query_items:
        raise RuntimeError(
            "discovery quarantined item count does not match queries"
        )
    if successful_queries != successful_query_records:
        raise RuntimeError(
            "discovery successful_queries does not match statuses"
        )

    feed_coverage = payload.get("feed_coverage")
    if not isinstance(feed_coverage, dict):
        raise RuntimeError("feed_coverage is not an object")

    required_coverage_fields = {
        "configured_feeds",
        "direct_feeds",
        "shared_discovery_feeds",
        "publisher_site_feeds",
        "feeds_due_this_run",
        "feeds_successful_this_run",
        "publisher_site_feeds_due",
        "publisher_site_feeds_successful",
        "publisher_site_items_quarantined",
        "configured_media_publishers",
        "contributing_publishers_30d",
        "accepted_items_by_transport",
        "priority_replacements",
        "duplicates_removed_by_transport",
    }
    if set(feed_coverage) != required_coverage_fields:
        raise RuntimeError("feed_coverage has unexpected fields")

    for field in (
        "configured_feeds",
        "direct_feeds",
        "shared_discovery_feeds",
        "publisher_site_feeds",
        "feeds_due_this_run",
        "feeds_successful_this_run",
        "publisher_site_feeds_due",
        "publisher_site_feeds_successful",
        "publisher_site_items_quarantined",
        "configured_media_publishers",
        "contributing_publishers_30d",
    ):
        value = feed_coverage.get(field)
        if type(value) is not int or value < 0:
            raise RuntimeError(f"feed_coverage {field} is invalid")

    if feed_coverage["direct_feeds"] != len(SOURCES):
        raise RuntimeError("feed_coverage direct_feeds is invalid")
    if feed_coverage["shared_discovery_feeds"] != configured_queries:
        raise RuntimeError(
            "feed_coverage shared_discovery_feeds is invalid"
        )
    if (
        feed_coverage["publisher_site_feeds"]
        != feed_coverage["configured_media_publishers"]
    ):
        raise RuntimeError(
            "feed_coverage publisher-site publisher count is invalid"
        )
    if (
        feed_coverage["configured_media_publishers"]
        != approved_media_domains
    ):
        raise RuntimeError(
            "feed_coverage configured media publisher count is invalid"
        )
    configured_site_feeds = generate_publisher_site_feeds()
    if (
        feed_coverage["publisher_site_feeds"]
        != len(configured_site_feeds)
    ):
        raise RuntimeError(
            "feed_coverage publisher_site_feeds does not match policy"
        )
    generated_at = parse_feed_datetime(payload.get("generated_at"))
    if generated_at is None:
        raise RuntimeError("feed_coverage requires a valid generated_at")
    expected_site_feeds_due = sum(
        publisher_site_feed_due(feed, generated_at)
        for feed in configured_site_feeds
    )
    if (
        feed_coverage["publisher_site_feeds_due"]
        != expected_site_feeds_due
    ):
        raise RuntimeError(
            "feed_coverage publisher-site schedule count is invalid"
        )
    if feed_coverage["configured_feeds"] != sum(
        (
            feed_coverage["direct_feeds"],
            feed_coverage["shared_discovery_feeds"],
            feed_coverage["publisher_site_feeds"],
        )
    ):
        raise RuntimeError("feed_coverage configured feed count is invalid")

    hourly_feeds = (
        feed_coverage["direct_feeds"]
        + feed_coverage["shared_discovery_feeds"]
    )
    if not (
        hourly_feeds
        <= feed_coverage["feeds_due_this_run"]
        <= feed_coverage["configured_feeds"]
    ):
        raise RuntimeError("feed_coverage feeds_due_this_run is invalid")
    if (
        feed_coverage["feeds_due_this_run"]
        != hourly_feeds + feed_coverage["publisher_site_feeds_due"]
    ):
        raise RuntimeError("feed_coverage due feed counts are inconsistent")
    if (
        feed_coverage["feeds_successful_this_run"]
        > feed_coverage["feeds_due_this_run"]
    ):
        raise RuntimeError(
            "feed_coverage successful feed count is invalid"
        )
    if (
        feed_coverage["publisher_site_feeds_due"]
        > feed_coverage["publisher_site_feeds"]
        or feed_coverage["publisher_site_feeds_successful"]
        > feed_coverage["publisher_site_feeds_due"]
    ):
        raise RuntimeError(
            "feed_coverage publisher-site run counts are invalid"
        )
    if (
        feed_coverage["contributing_publishers_30d"]
        > feed_coverage["configured_media_publishers"]
    ):
        raise RuntimeError(
            "feed_coverage contributing publisher count is invalid"
        )

    accepted_by_transport = feed_coverage.get(
        "accepted_items_by_transport"
    )
    if (
        not isinstance(accepted_by_transport, dict)
        or set(accepted_by_transport)
        != {"direct", "publisher_site", "shared_discovery"}
        or any(
            type(value) is not int or value < 0
            for value in accepted_by_transport.values()
        )
    ):
        raise RuntimeError(
            "feed_coverage accepted_items_by_transport is invalid"
        )

    priority_replacements = feed_coverage.get("priority_replacements")
    if (
        not isinstance(priority_replacements, dict)
        or set(priority_replacements)
        != {
            "direct_over_shared_discovery",
            "direct_over_publisher_site",
            "publisher_site_over_shared_discovery",
        }
        or any(
            type(value) is not int or value < 0
            for value in priority_replacements.values()
        )
    ):
        raise RuntimeError(
            "feed_coverage priority_replacements is invalid"
        )
    if (
        priority_replacements["direct_over_shared_discovery"]
        != discovery["direct_precedence_replacements"]
    ):
        raise RuntimeError(
            "feed_coverage direct replacement count is inconsistent"
        )
    if (
        priority_replacements["direct_over_shared_discovery"]
        + priority_replacements[
            "publisher_site_over_shared_discovery"
        ]
        > discovery["duplicates_removed"]
    ):
        raise RuntimeError(
            "feed_coverage shared discovery replacement count is invalid"
        )

    removed_by_transport = feed_coverage.get(
        "duplicates_removed_by_transport"
    )
    if (
        not isinstance(removed_by_transport, dict)
        or set(removed_by_transport)
        != {"direct", "publisher_site", "shared_discovery", "unknown"}
        or any(
            type(value) is not int or value < 0
            for value in removed_by_transport.values()
        )
        or sum(removed_by_transport.values())
        < discovery["duplicates_removed"]
    ):
        raise RuntimeError(
            "feed_coverage duplicates_removed_by_transport is invalid"
        )
    if (
        removed_by_transport["shared_discovery"]
        != discovery["duplicates_removed"]
    ):
        raise RuntimeError(
            "feed_coverage shared discovery duplicate count is inconsistent"
        )
    if sum(priority_replacements.values()) > sum(
        removed_by_transport.values()
    ):
        raise RuntimeError(
            "feed_coverage priority replacement counts are invalid"
        )

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

    if feed_coverage["feeds_successful_this_run"] != sum(
        (
            len(successful_sources),
            successful_queries,
            feed_coverage["publisher_site_feeds_successful"],
        )
    ):
        raise RuntimeError(
            "feed_coverage successful feed counts are inconsistent"
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

    if not isinstance(relevant_news, list):
        raise RuntimeError("relevant_news is not a list")
    relevant_ids: set[str] = set()
    for item in relevant_news:
        required = {
            "id",
            "publisher",
            "published_at",
            "headline",
            "url",
            "explicit_election",
            "candidates",
            "relevance_reason",
            "relevance_terms",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError("relevant_news item has unexpected fields")
        if (
            not isinstance(item["relevance_reason"], str)
            or not item["relevance_reason"]
            or not isinstance(item["relevance_terms"], list)
        ):
            raise RuntimeError("relevant_news lacks relevance provenance")
        if item["id"] in relevant_ids:
            raise RuntimeError("relevant_news contains duplicate item ids")
        relevant_ids.add(item["id"])

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

    election_ids = {item["id"] for item in election_news}
    if not election_ids.issubset(relevant_ids):
        raise RuntimeError("election_news must be a subset of relevant_news")
    if not notable_ids.issubset(relevant_ids):
        raise RuntimeError(
            "notable_developments must be a subset of relevant_news"
        )

    expected_counts = {
        "election_news": len(election_news),
        "notable_developments": len(notable_developments),
        "relevant_news": len(relevant_news),
        "candidate_watch": len(candidate_watch),
    }
    for field, expected in expected_counts.items():
        if payload.get("counts", {}).get(field) != expected:
            raise RuntimeError(f"News-wire count {field} is invalid")

    counts = payload.get("counts", {})
    inventory_count = counts.get("retained_inventory_items")
    if not isinstance(inventory_count, int) or inventory_count < 0:
        raise RuntimeError("News-wire inventory count is invalid")
    if counts.get("unique_recent_feed_items") != inventory_count:
        raise RuntimeError(
            "News-wire unique item count must match the retained inventory"
        )
    for field in (
        "current_feed_snapshot_items",
        "new_items_discovered",
        "refreshed_inventory_items",
        "expired_inventory_items",
    ):
        if not isinstance(counts.get(field), int) or counts[field] < 0:
            raise RuntimeError(f"News-wire count {field} is invalid")

    if not relevant_news and not candidate_watch:
        raise RuntimeError(
            "The generated wire contains no matching news items"
        )


def build_wire(
    polls_path: Path,
    window_days: int,
    max_items: int,
    inventory_path: Path | None = None,
    discovered_publishers_path: Path | None = None,
    generated_at: datetime | None = None,
    health_route_configurations: list[dict[str, Any]] | None = None,
    health_attempts: list[dict[str, Any]] | None = None,
    previous_source_health: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    elif generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    else:
        generated_at = generated_at.astimezone(timezone.utc)

    window_start = generated_at - timedelta(days=window_days)
    candidates, candidate_cutoff = recent_candidate_roster(
        polls_path,
        generated_at,
    )
    normalized_candidates = {
        candidate: normalize(candidate)
        for candidate in candidates
    }
    discovery_queries = generate_discovery_queries(candidates)
    publisher_site_feeds = generate_publisher_site_feeds()
    if health_route_configurations is not None:
        health_route_configurations.extend(
            build_source_health_routes(
                discovery_queries,
                publisher_site_feeds,
                generated_at,
            )
        )
    due_publisher_site_feeds = [
        feed
        for feed in publisher_site_feeds
        if publisher_site_feed_due(feed, generated_at)
    ]

    endpoints: list[dict[str, Any]] = []
    for order, source in enumerate(SOURCES):
        endpoints.append(
            {
                "order": order,
                "kind": "direct",
                "id": source["source_id"],
                "name": source["name"],
                "feed_url": source["feed_url"],
                "source": source,
            }
        )
    for offset, query in enumerate(discovery_queries, start=len(SOURCES)):
        endpoints.append(
            {
                "order": offset,
                "kind": "discovery",
                "id": query["id"],
                "name": query["label"],
                "feed_url": query["feed_url"],
                "query": query,
            }
        )
    site_offset = len(SOURCES) + len(discovery_queries)
    for offset, feed in enumerate(
        due_publisher_site_feeds,
        start=site_offset,
    ):
        endpoints.append(
            {
                "order": offset,
                "kind": "publisher_site",
                "id": feed["id"],
                "name": feed["label"],
                "feed_url": feed["feed_url"],
                "publisher_site": feed,
            }
        )

    def fetch_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
        route_id = endpoint_source_health_id(endpoint)
        request_url = endpoint["feed_url"]
        etag, last_modified = route_request_validators(
            previous_source_health,
            route_id,
            request_url,
        )
        fetch_result: HttpFetchResult | None = None
        try:
            is_google_news = endpoint["kind"] in {
                "discovery",
                "publisher_site",
            }
            if is_google_news:
                with GOOGLE_NEWS_SEMAPHORE:
                    fetch_result = fetch_news_route(
                        request_url,
                        etag=etag,
                        last_modified=last_modified,
                        timeout=FETCH_TIMEOUT_SECONDS,
                        max_response_bytes=MAX_NEWS_RESPONSE_BYTES,
                    )
            else:
                fetch_result = fetch_news_route(
                    request_url,
                    etag=etag,
                    last_modified=last_modified,
                    timeout=FETCH_TIMEOUT_SECONDS,
                    max_response_bytes=MAX_NEWS_RESPONSE_BYTES,
                )

            if not fetch_result.success:
                return {
                    "endpoint": endpoint,
                    "status": "error",
                    "not_modified": False,
                    "final_feed_url": fetch_result.final_url,
                    "entries": [],
                    "error": (
                        f"{fetch_result.failure_category}: "
                        f"{fetch_result.failure_message}"
                    ),
                    "http_status": fetch_result.status_code,
                    "failure_category": fetch_result.failure_category,
                    "response_seconds": round(
                        fetch_result.elapsed_ms / 1000,
                        3,
                    ),
                    "attempts": fetch_result.attempts,
                    "etag": fetch_result.etag,
                    "last_modified": fetch_result.last_modified,
                    "request_url": request_url,
                    "response_bytes": fetch_result.response_bytes,
                    "retry_after_used": fetch_result.retry_after_used,
                }

            entry_limit = DIRECT_ENTRY_LIMIT
            if endpoint["kind"] == "discovery":
                entry_limit = DISCOVERY_ENTRY_LIMIT
            elif endpoint["kind"] == "publisher_site":
                entry_limit = PUBLISHER_SITE_ENTRY_LIMIT

            entries: list[dict[str, Any]] = []
            if not fetch_result.not_modified:
                if fetch_result.response_body is None:
                    raise RuntimeError(
                        "successful HTTP response is missing its body"
                    )
                entries = parse_feed(
                    fetch_result.response_body,
                    endpoint["name"],
                    fetch_result.final_url,
                    google_news=is_google_news,
                    max_entries=entry_limit,
                    allow_empty=True,
                )
            return {
                "endpoint": endpoint,
                "status": "ok",
                "not_modified": fetch_result.not_modified,
                "final_feed_url": fetch_result.final_url,
                "entries": entries,
                "error": None,
                "http_status": fetch_result.status_code,
                "failure_category": None,
                "response_seconds": round(
                    fetch_result.elapsed_ms / 1000,
                    3,
                ),
                "attempts": fetch_result.attempts,
                "etag": fetch_result.etag,
                "last_modified": fetch_result.last_modified,
                "request_url": request_url,
                "response_bytes": fetch_result.response_bytes,
                "retry_after_used": fetch_result.retry_after_used,
            }
        except Exception as error:
            failure_category = (
                "invalid_response"
                if fetch_result is not None
                else "unknown_error"
            )
            return {
                "endpoint": endpoint,
                "status": "error",
                "not_modified": False,
                "final_feed_url": (
                    fetch_result.final_url
                    if fetch_result is not None
                    else request_url
                ),
                "entries": [],
                "error": (
                    f"{failure_category}: "
                    f"{type(error).__name__}: {str(error)[:300]}"
                ),
                "http_status": (
                    fetch_result.status_code
                    if fetch_result is not None
                    else None
                ),
                "failure_category": failure_category,
                "response_seconds": (
                    round(fetch_result.elapsed_ms / 1000, 3)
                    if fetch_result is not None
                    else 0
                ),
                "attempts": (
                    fetch_result.attempts
                    if fetch_result is not None
                    else 1
                ),
                "etag": (
                    fetch_result.etag
                    if fetch_result is not None
                    else None
                ),
                "last_modified": (
                    fetch_result.last_modified
                    if fetch_result is not None
                    else None
                ),
                "request_url": request_url,
                "response_bytes": (
                    fetch_result.response_bytes
                    if fetch_result is not None
                    else 0
                ),
                "retry_after_used": (
                    fetch_result.retry_after_used
                    if fetch_result is not None
                    else False
                ),
            }

    fetched_by_order: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = {
            executor.submit(fetch_endpoint, endpoint): endpoint["order"]
            for endpoint in endpoints
        }
        for future in as_completed(futures):
            fetched_by_order[futures[future]] = future.result()

    source_status: list[dict[str, Any]] = []
    discovery_status: list[dict[str, Any]] = []
    publisher_site_status: list[dict[str, Any]] = []
    all_entries: list[dict[str, Any]] = []
    rejected_shared_discovery_entries: list[dict[str, Any]] = []
    rejected_publisher_site_entries: list[dict[str, Any]] = []
    accepted_discovery_items = 0

    for order in sorted(fetched_by_order):
        result = fetched_by_order[order]
        endpoint = result["endpoint"]
        entries = result["entries"]
        recent_entries = [
            entry
            for entry in entries
            if entry["published_at"] >= window_start
        ]
        latest = max(
            (entry["published_at"] for entry in entries),
            default=None,
        )

        if endpoint["kind"] == "direct":
            source = endpoint["source"]
            for entry in recent_entries:
                entry["source_id"] = source["source_id"]
                entry["politics_specific"] = bool(
                    source.get("politics_specific")
                )
            source_status.append(
                {
                    "name": source["name"],
                    "feed_url": result["final_feed_url"],
                    "status": result["status"],
                    "items_seen": len(entries),
                    "recent_items": len(recent_entries),
                    "latest_published_at": (
                        latest.isoformat().replace("+00:00", "Z")
                        if latest is not None
                        else None
                    ),
                    "error": result["error"],
                    "response_seconds": result["response_seconds"],
                }
            )
            all_entries.extend(recent_entries)
            continue

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        if result["status"] == "ok":
            is_publisher_site = endpoint["kind"] == "publisher_site"
            accepted, rejected = accept_discovery_entries(
                recent_entries,
                endpoint["id"],
                source_id_prefix=(
                    "publisher-site"
                    if is_publisher_site
                    else "discovery"
                ),
                expected_policy_domain=(
                    endpoint["publisher_site"]["domain"]
                    if is_publisher_site
                    else None
                ),
                transport=(
                    "publisher_site"
                    if is_publisher_site
                    else "shared_discovery"
                ),
            )
            if is_publisher_site:
                rejected_publisher_site_entries.extend(rejected)
            else:
                accepted_discovery_items += len(accepted)
                rejected_shared_discovery_entries.extend(rejected)
            all_entries.extend(accepted)

        status_record = {
            "id": endpoint["id"],
            "label": endpoint["name"],
            "feed_url": result["final_feed_url"],
            "status": result["status"],
            "items_seen": len(entries),
            "recent_items": len(recent_entries),
            "accepted_items": len(accepted),
            "quarantined_items": len(rejected),
            "latest_published_at": (
                latest.isoformat().replace("+00:00", "Z")
                if latest is not None
                else None
            ),
            "error": result["error"],
            "response_seconds": result["response_seconds"],
        }
        if endpoint["kind"] == "publisher_site":
            publisher_site_status.append(status_record)
        else:
            status_record["kind"] = endpoint["query"]["kind"]
            discovery_status.append(status_record)

    all_entries, deduplication_stats = deduplicate_entries(all_entries)

    # Candidate Watch and broad relevance are derived from the complete
    # feed title and summary before inventory_summary() shortens the stored
    # summary. The compact inventory therefore retains stable provenance.
    for entry in all_entries:
        normalized_headline = normalize(entry["headline"])
        normalized_summary = normalize(entry.get("summary") or "")
        complete_text = " ".join(
            part for part in (normalized_headline, normalized_summary)
            if part
        )
        entry["candidate_names"] = [
            candidate
            for candidate, normalized_name
            in normalized_candidates.items()
            if normalized_name in complete_text
        ]
        relevance = classify_relevant_news(
            normalized_headline,
            normalized_summary,
            entry["candidate_names"],
        )
        entry["relevance_reason"] = (
            relevance["reason"] if relevance is not None else None
        )
        entry["relevance_terms"] = (
            relevance["matched_terms"] if relevance is not None else []
        )

    existing_inventory = load_inventory(
        inventory_path,
        window_days,
    )
    inventory_payload, inventory_entries, inventory_stats = merge_inventory(
        existing_inventory,
        all_entries,
        generated_at,
        window_days,
    )

    deduplicated = {
        inventory_identity(entry): entry
        for entry in inventory_entries
    }

    election_news: list[dict[str, Any]] = []
    notable_developments: list[dict[str, Any]] = []
    relevant_news: list[dict[str, Any]] = []
    candidate_watch: list[dict[str, Any]] = []
    current_inventory_identities = {
        inventory_identity(entry) for entry in all_entries
    }
    current_election_identities: set[str] = set()

    source_by_id = {source["source_id"]: source for source in SOURCES}
    source_by_id.update(
        {
            f"discovery:{query['id']}": {"politics_specific": True}
            for query in discovery_queries
        }
    )
    source_by_id.update(
        {
            feed["id"]: {"politics_specific": True}
            for feed in publisher_site_feeds
        }
    )

    for entry in deduplicated.values():
        combined_text = normalize(
            f"{entry['headline']} {entry.get('summary') or ''}"
        )
        matched_candidates = [
            candidate
            for candidate in entry.get("candidate_names", [])
            if candidate in normalized_candidates
        ]
        normalized_headline = normalize(entry["headline"])
        normalized_summary = normalize(entry.get("summary") or "")

        # Topic/profile directory pages remain in the raw inventory but do not
        # enter Candidate Watch, Relevant News, Election News, or the ledger.
        if is_static_entity_page(
            entry["headline"],
            entry.get("url") or "",
            matched_candidates,
        ):
            continue

        source = source_by_id.get(entry.get("source_id"), {})
        development = classify_notable_development(
            combined_text,
            matched_candidates,
            source,
            normalized_headline,
        )

        relevance = None
        if entry.get("relevance_reason"):
            relevance = {
                "reason": entry["relevance_reason"],
                "matched_terms": list(entry.get("relevance_terms", [])),
            }
        else:
            relevance = classify_relevant_news(
                normalized_headline,
                normalized_summary,
                matched_candidates,
            )

        # Election News is a current-race headline lane. Historical election
        # retrospectives and summary-only presidential mentions do not qualify.
        current_election_terms = current_presidential_matches(
            normalized_headline
        )
        is_election_news = bool(
            current_election_terms and relevance is not None
        )
        base_item = public_item(
            entry,
            matched_candidates,
            is_election_news,
        )

        if is_election_news:
            election_news.append(base_item)
            identity = inventory_identity(entry)
            if identity in current_inventory_identities:
                current_election_identities.add(identity)
        elif development is not None:
            notable_developments.append(
                public_notable_item(
                    entry,
                    matched_candidates,
                    development,
                )
            )

        # Any concrete presidential development is relevant even when the
        # broader classifier has no separate contextual signal.
        if relevance is None and development is not None:
            relevance = {
                "reason": "concrete_presidential_development",
                "matched_terms": development["matched_terms"],
            }

        if relevance is not None:
            relevant_news.append(
                public_relevant_item(
                    entry,
                    matched_candidates,
                    is_election_news,
                    relevance,
                )
            )

        if matched_candidates:
            candidate_watch.append(base_item)

    for items in (
        election_news,
        notable_developments,
        relevant_news,
        candidate_watch,
    ):
        items.sort(
            key=lambda item: item["published_at"],
            reverse=True,
        )

    election_news = limit_items(election_news, max_items)
    notable_developments = limit_items(notable_developments, max_items)
    relevant_news = limit_items(relevant_news, max_items)
    candidate_watch = limit_items(candidate_watch, max_items)

    campaign_agenda = build_campaign_agenda(
        relevant_news,
        window_days,
    )

    discovered_publishers_payload = aggregate_discovered_publishers(
        rejected_shared_discovery_entries
        + rejected_publisher_site_entries
    )
    discovered_publishers_payload["generated_at"] = (
        generated_at.isoformat().replace("+00:00", "Z")
    )

    retained_shared_discovery_entries = [
        entry
        for entry in all_entries
        if entry_transport(entry) == "shared_discovery"
    ]
    retained_publisher_site_entries = [
        entry
        for entry in all_entries
        if entry_transport(entry) == "publisher_site"
    ]
    retained_direct_entries = [
        entry
        for entry in all_entries
        if entry_transport(entry) == "direct"
    ]
    contributing_media_publishers = (
        count_contributing_media_publishers(inventory_entries)
    )

    if health_attempts is not None:
        accepted_inventory_by_route: dict[str, int] = {}
        accepted_election_by_route: dict[str, int] = {}
        for entry in all_entries:
            route_id = source_entry_health_id(entry.get("source_id"))
            identity = inventory_identity(entry)
            retained_entry = deduplicated.get(identity)
            if (
                retained_entry is None
                or source_entry_health_id(retained_entry.get("source_id"))
                != route_id
            ):
                continue
            accepted_inventory_by_route[route_id] = (
                accepted_inventory_by_route.get(route_id, 0) + 1
            )
            if identity in current_election_identities:
                accepted_election_by_route[route_id] = (
                    accepted_election_by_route.get(route_id, 0) + 1
                )
        for order in sorted(fetched_by_order):
            result = fetched_by_order[order]
            route_id = endpoint_source_health_id(result["endpoint"])
            health_attempts.append(
                {
                    "route_id": route_id,
                    "success": result["status"] == "ok",
                    "not_modified": result["not_modified"],
                    "http_status": result["http_status"],
                    "failure_category": result["failure_category"],
                    "latency_ms": max(
                        0,
                        round(result["response_seconds"] * 1000),
                    ),
                    "attempts": result["attempts"],
                    "response_bytes": result["response_bytes"],
                    "etag": result["etag"],
                    "last_modified": result["last_modified"],
                    "request_url": result["request_url"],
                    "parsed_item_count": len(result["entries"]),
                    "accepted_inventory_count": (
                        accepted_inventory_by_route.get(route_id, 0)
                    ),
                    "accepted_election_news_count": (
                        accepted_election_by_route.get(route_id, 0)
                    ),
                }
            )

    configured_feeds = (
        len(SOURCES)
        + len(discovery_queries)
        + len(publisher_site_feeds)
    )
    feeds_due_this_run = len(endpoints)
    feeds_successful_this_run = (
        sum(source["status"] == "ok" for source in source_status)
        + sum(query["status"] == "ok" for query in discovery_status)
        + sum(
            feed["status"] == "ok"
            for feed in publisher_site_status
        )
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
        "discovery": {
            "configured_queries": len(discovery_queries),
            "successful_queries": sum(
                query["status"] == "ok"
                for query in discovery_status
            ),
            "accepted_items_before_deduplication": (
                accepted_discovery_items
            ),
            "accepted_items_after_deduplication": len(
                retained_shared_discovery_entries
            ),
            "quarantined_items": len(
                rejected_shared_discovery_entries
            ),
            "distinct_accepted_publishers": len(
                {
                    entry["publisher"]
                    for entry in retained_shared_discovery_entries
                }
            ),
            "approved_publisher_domains": len(PUBLISHER_POLICY),
            "approved_media_domains": sum(
                policy.get("source_type") == "media"
                and bool(policy.get("enabled", True))
                for policy in PUBLISHER_POLICY.values()
            ),
            "duplicates_removed": deduplication_stats[
                "removed_by_transport"
            ]["shared_discovery"],
            "direct_precedence_replacements": deduplication_stats[
                "direct_precedence_replacements"
            ],
            "queries": discovery_status,
        },
        "feed_coverage": {
            "configured_feeds": configured_feeds,
            "direct_feeds": len(SOURCES),
            "shared_discovery_feeds": len(discovery_queries),
            "publisher_site_feeds": len(publisher_site_feeds),
            # The due/success counters below describe only this payload's
            # generated_at run, not persistent rolling-health statistics.
            "feeds_due_this_run": feeds_due_this_run,
            "feeds_successful_this_run": feeds_successful_this_run,
            "publisher_site_feeds_due": len(
                due_publisher_site_feeds
            ),
            "publisher_site_feeds_successful": sum(
                feed["status"] == "ok"
                for feed in publisher_site_status
            ),
            "publisher_site_items_quarantined": len(
                rejected_publisher_site_entries
            ),
            "configured_media_publishers": len(
                publisher_site_feeds
            ),
            "contributing_publishers_30d": (
                contributing_media_publishers
            ),
            "accepted_items_by_transport": {
                "direct": len(retained_direct_entries),
                "publisher_site": len(
                    retained_publisher_site_entries
                ),
                "shared_discovery": len(
                    retained_shared_discovery_entries
                ),
            },
            "priority_replacements": {
                "direct_over_shared_discovery": deduplication_stats[
                    "direct_precedence_replacements"
                ],
                "direct_over_publisher_site": deduplication_stats[
                    "direct_over_publisher_site_replacements"
                ],
                "publisher_site_over_shared_discovery": deduplication_stats[
                    "publisher_site_precedence_replacements"
                ],
            },
            "duplicates_removed_by_transport": (
                deduplication_stats["removed_by_transport"]
            ),
        },
        "counts": {
            "successful_sources": sum(
                source["status"] == "ok"
                for source in source_status
            ),
            "current_feed_snapshot_items": inventory_stats[
                "current_feed_snapshot_items"
            ],
            "new_items_discovered": inventory_stats[
                "new_items_discovered"
            ],
            "refreshed_inventory_items": inventory_stats[
                "refreshed_inventory_items"
            ],
            "expired_inventory_items": inventory_stats[
                "expired_inventory_items"
            ],
            "retained_inventory_items": inventory_stats[
                "retained_inventory_items"
            ],
            # Backward-compatible public count: this now represents the
            # complete retained 30-day inventory, not just the current feeds.
            "unique_recent_feed_items": inventory_stats[
                "retained_inventory_items"
            ],
            "election_news": len(election_news),
            "notable_developments": len(notable_developments),
            "relevant_news": len(relevant_news),
            "candidate_watch": len(candidate_watch),
        },
        "campaign_agenda": campaign_agenda,
        "election_news": election_news,
        "notable_developments": notable_developments,
        "relevant_news": relevant_news,
        "candidate_watch": candidate_watch,
    }

    validate_output(payload)

    if discovered_publishers_path is not None:
        write_json_atomic(
            discovered_publishers_path,
            discovered_publishers_payload,
        )

    return payload, inventory_payload


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
        "--inventory",
        type=Path,
        default=Path("news_inventory.json"),
    )
    parser.add_argument(
        "--source-health",
        type=Path,
        default=Path("source_health.json"),
    )
    parser.add_argument(
        "--discovered-publishers",
        type=Path,
        default=None,
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

    previous_source_health = load_source_health(arguments.source_health)
    source_health_routes: list[dict[str, Any]] = []
    source_health_attempts: list[dict[str, Any]] = []
    generated_at = datetime.now(timezone.utc)
    payload, inventory_payload = build_wire(
        arguments.polls,
        arguments.window_days,
        arguments.max_items,
        arguments.inventory,
        arguments.discovered_publishers,
        generated_at,
        source_health_routes,
        source_health_attempts,
        previous_source_health,
    )
    source_health_payload = update_source_health(
        previous_source_health,
        source_health_routes,
        source_health_attempts,
        generated_at,
    )

    write_json_atomic(arguments.inventory, inventory_payload)
    write_json_atomic(arguments.output, payload)
    write_source_health_atomic(
        arguments.source_health,
        source_health_payload,
    )

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
    discovery = payload["discovery"]
    print(
        f"Successful discovery queries: "
        f"{discovery['successful_queries']}/"
        f"{discovery['configured_queries']}"
    )
    print(
        f"Accepted discovery items: "
        f"{discovery['accepted_items_after_deduplication']}"
    )
    print(
        f"Quarantined discovery items: "
        f"{discovery['quarantined_items']}"
    )
    print(
        f"Distinct discovery publishers: "
        f"{discovery['distinct_accepted_publishers']}"
    )
    feed_coverage = payload["feed_coverage"]
    print(
        f"Configured feeds: "
        f"{feed_coverage['configured_feeds']}"
    )
    print(
        f"Feeds due this run: "
        f"{feed_coverage['feeds_due_this_run']}"
    )
    print(
        f"Publisher-site feeds: "
        f"{feed_coverage['publisher_site_feeds_successful']}/"
        f"{feed_coverage['publisher_site_feeds_due']} successful this run"
    )
    print(
        f"Current feed snapshot items: "
        f"{counts['current_feed_snapshot_items']}"
    )
    print(
        f"New items discovered: "
        f"{counts['new_items_discovered']}"
    )
    print(
        f"Retained 30-day inventory items: "
        f"{counts['retained_inventory_items']}"
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
    print(f"Inventory: {arguments.inventory}")
    print(f"Output: {arguments.output}")
    print(f"Source health: {arguments.source_health}")
    if arguments.discovered_publishers is not None:
        print(
            f"Discovered publishers: "
            f"{arguments.discovered_publishers}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
