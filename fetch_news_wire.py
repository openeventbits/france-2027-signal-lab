#!/usr/bin/env python3
"""Build the FR27 Signal Lab election news wire from direct and discovery feeds."""

from __future__ import annotations
from news_scope import unanchored_presidential_context

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import math
import re
from threading import BoundedSemaphore
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    active_candidate_names,
    active_projection_provenance,
    load_candidate_candidacy_status,
)
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

NEWS_EXCLUSIONS_PATH = Path(__file__).with_name(
    "news_exclusions_manual.json"
)

GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_PARAMETERS = {
    "hl": "fr",
    "gl": "FR",
    "ceid": "FR:fr",
}
DIRECT_ENTRY_LIMIT = 20
DISCOVERY_ENTRY_LIMIT = 20
PUBLISHER_SITE_ENTRY_LIMIT = 5
FETCH_TIMEOUT_SECONDS = 12
MAX_NEWS_RESPONSE_BYTES = DEFAULT_MAX_RESPONSE_BYTES
FETCH_WORKERS = 12
GOOGLE_NEWS_WORKERS = 4
GOOGLE_NEWS_SEMAPHORE = BoundedSemaphore(GOOGLE_NEWS_WORKERS)

CANDIDATE_VISIBILITY_METHOD = "share_of_candidate_linked_records"
CANDIDACY_STATUS_SOURCE = "candidate_candidacy_status.json"
ACTIVE_CANDIDATE_ROSTER_RULE = "active_monitoring_field"
CANDIDATE_VISIBILITY_THRESHOLDS = {
    "minimum_period_records": 10,
    "minimum_period_publishers": 5,
    "minimum_common_publishers": 5,
    "minimum_publisher_overlap_ratio": 0.5,
    "maximum_record_count_ratio": 2.0,
}

CANDIDATE_COVERAGE_SCOPES = (
    "election",
    "campaign",
    "general",
)

CANDIDATE_VISIBILITY_PRIMARY_SCOPES = (
    "election",
    "campaign",
)
CANDIDATE_VISIBILITY_SECONDARY_SCOPE = "general"

STORY_CLUSTER_MIN_SHARED_TOKENS = 3
STORY_CLUSTER_MIN_JACCARD = 0.5
STORY_CLUSTER_STOPWORDS = frozenset({
    "afin",
    "ainsi",
    "alors",
    "apres",
    "avec",
    "avant",
    "avoir",
    "chez",
    "comme",
    "dans",
    "depuis",
    "des",
    "elle",
    "elles",
    "entre",
    "etre",
    "fait",
    "font",
    "leur",
    "leurs",
    "mais",
    "meme",
    "moins",
    "notre",
    "nous",
    "par",
    "pas",
    "plus",
    "pour",
    "quand",
    "que",
    "quel",
    "quelle",
    "qui",
    "sans",
    "ses",
    "son",
    "sont",
    "sous",
    "sur",
    "tous",
    "tout",
    "toute",
    "une",
    "vers",
    "vous",
    "candidat",
    "candidate",
    "candidats",
    "candidates",
    "candidature",
    "campagne",
    "election",
    "elections",
    "electoral",
    "electorale",
    "president",
    "presidente",
    "presidentiel",
    "presidentielle",
    "politique",
    "france",
    "francais",
    "francaise",
})

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

INVENTORY_SCHEMA_VERSION = 4
LEGACY_INVENTORY_SCHEMA_VERSION = 3
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
    "candidate_matches",
    "relevance_reason",
    "relevance_terms",
}
LEGACY_INVENTORY_ITEM_FIELDS = INVENTORY_ITEM_FIELDS - {"candidate_matches"}

# Poll sources sometimes alternate between full candidate names and compact
# labels. Canonicalization prevents those variants from becoming separate
# public identities. This map does not automatically approve surname-only
# matching in news text.
NEWS_CANDIDATE_NAME_OVERRIDES: dict[str, str] = {
    "Arthaud": "Nathalie Arthaud",
    "Attal": "Gabriel Attal",
    "Bardella": "Jordan Bardella",
    "Darmanin": "Gérald Darmanin",
    "de Villepin": "Dominique de Villepin",
    "Dupont-Aignan": "Nicolas Dupont-Aignan",
    "Faure": "Olivier Faure",
    "Hollande": "François Hollande",
    "Knafo": "Sarah Knafo",
    "Lecornu": "Sébastien Lecornu",
    "Mélenchon": "Jean-Luc Mélenchon",
    "Philippe": "Édouard Philippe",
    "Retailleau": "Bruno Retailleau",
    "Roussel": "Fabien Roussel",
    "Ruffin": "François Ruffin",
    "Tondelier": "Marine Tondelier",
    "Zemmour": "Éric Zemmour",
}

# Additional text aliases must be reviewed and demonstrated to be
# unambiguous before they are added here.
NEWS_CANDIDATE_ALIAS_OVERRIDES: dict[str, tuple[str, ...]] = {}
CANDIDATE_MATCH_LOCATIONS = ("headline", "summary")

ELECTION_PATTERNS = (
    re.compile(r"\bpresidentielle(?:\s+francaise)?(?:\s+de)?\s+2027\b"),
    re.compile(
        r"\b(?:election\s+presidentielle|elections\s+presidentielles)\b"
    ),
    re.compile(r"\bcandidat(?:e|s|es)?\s+aux\s+presidentielles\b"),
    re.compile(
        r"\b(?:prochain\s+scrutin\s+presidentiel|"
        r"scrutin\s+presidentiel(?:\s+a\s+venir)?)\b"
    ),
    re.compile(r"\bprochaine\s+presidentielle\b"),
    re.compile(r"\bcourse\s+a\s+l\s+elysee\b"),
    re.compile(r"\belysee\s+2027\b"),
    re.compile(r"\bcandidat(?:e|ure)?\s+a\s+l\s+election\s+presidentielle\b"),
    re.compile(r"\bsondages?\s+presidentiels?\b"),
)

CAMPAIGN_AGENDA_TOPICS = (
    {
        "id": "legal_eligibility",
        "label": "Legal cases & eligibility",
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
            "officialise sa candidature",
            "se declare candidat",
            "se declare candidate",
            "entree en campagne",
            "lance sa campagne",
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
            "financement de la campagne",
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

CAMPAIGN_AGENDA_SUPPORT_LIMIT = 20
CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS = 2
CAMPAIGN_AGENDA_EVOLUTION_DAYS = 30
CAMPAIGN_AGENDA_COMPARISON_DAYS = 7


POLICY_AGENDA_TOPICS = (
    {
        "id": "economy_public_finances",
        "label": "Economy & Public Finances",
        "terms": (
            "budget",
            "deficit public",
            "deficits publics",
            "dette publique",
            "finances publiques",
            "fiscalite",
            "impot",
            "impots",
            "taxation",
            "taxe",
            "taxes",
            "croissance",
            "reindustrialisation",
            "industrie",
            "politique industrielle",
            "pib",
        ),
        "subtopics": {
            "budget": (
                "budget",
                "finances publiques",
            ),
            "deficit_debt": (
                "deficit public",
                "deficits publics",
                "dette publique",
            ),
            "taxation": (
                "fiscalite",
                "impot",
                "impots",
                "taxation",
                "taxe",
                "taxes",
            ),
            "growth_industry": (
                "croissance",
                "reindustrialisation",
                "industrie",
                "politique industrielle",
                "pib",
            ),
        },
    },
    {
        "id": "work_purchasing_power_pensions",
        "label": "Work, Purchasing Power & Pensions",
        "terms": (
            "pouvoir d achat",
            "salaire",
            "salaires",
            "smic",
            "emploi",
            "chomage",
            "retraite",
            "retraites",
            "age legal de depart",
            "age de depart",
            "temps de travail",
            "droit du travail",
            "cotisations sociales",
        ),
        "subtopics": {
            "purchasing_power": (
                "pouvoir d achat",
            ),
            "wages": (
                "salaire",
                "salaires",
                "smic",
            ),
            "employment": (
                "emploi",
                "chomage",
                "temps de travail",
                "droit du travail",
            ),
            "pensions": (
                "retraite",
                "retraites",
                "age legal de depart",
                "age de depart",
            ),
            "social_contributions": (
                "cotisations sociales",
            ),
        },
    },
    {
        "id": "immigration_identity_secularism",
        "label": "Immigration, Identity & Secularism",
        "terms": (
            "immigration",
            "immigre",
            "immigres",
            "migrant",
            "migrants",
            "asile",
            "droit d asile",
            "nationalite",
            "integration",
            "laicite",
            "identite nationale",
            "oqtf",
            "frontieres",
        ),
        "subtopics": {
            "immigration": (
                "immigration",
                "immigre",
                "immigres",
                "migrant",
                "migrants",
                "frontieres",
            ),
            "asylum": (
                "asile",
                "droit d asile",
                "oqtf",
            ),
            "nationality_integration": (
                "nationalite",
                "integration",
            ),
            "identity_secularism": (
                "laicite",
                "identite nationale",
            ),
        },
    },
    {
        "id": "security_justice",
        "label": "Security & Justice",
        "terms": (
            "securite",
            "police",
            "gendarmerie",
            "delinquance",
            "criminalite",
            "prison",
            "prisons",
            "terrorisme",
            "narcotrafic",
            "trafic de drogue",
            "justice des mineurs",
            "peines planchers",
            "magistrats",
        ),
        "subtopics": {
            "security_policing": (
                "securite",
                "police",
                "gendarmerie",
            ),
            "crime": (
                "delinquance",
                "criminalite",
                "narcotrafic",
                "trafic de drogue",
            ),
            "prisons_sentencing": (
                "prison",
                "prisons",
                "peines planchers",
            ),
            "terrorism": (
                "terrorisme",
            ),
            "justice_system": (
                "justice des mineurs",
                "magistrats",
            ),
        },
    },
    {
        "id": "health_education_public_services",
        "label": "Health, Education & Public Services",
        "terms": (
            "sante",
            "hopital",
            "hopitaux",
            "medecin",
            "medecins",
            "soins",
            "deserts medicaux",
            "ecole",
            "education",
            "enseignant",
            "enseignants",
            "services publics",
            "fonction publique",
            "fonctionnaires",
            "ehpad",
        ),
        "subtopics": {
            "health": (
                "sante",
                "hopital",
                "hopitaux",
                "medecin",
                "medecins",
                "soins",
                "deserts medicaux",
                "ehpad",
            ),
            "education": (
                "ecole",
                "education",
                "enseignant",
                "enseignants",
            ),
            "public_services": (
                "services publics",
                "fonction publique",
                "fonctionnaires",
            ),
        },
    },
    {
        "id": "climate_energy_agriculture",
        "label": "Climate, Energy & Agriculture",
        "terms": (
            "climat",
            "ecologie",
            "transition ecologique",
            "environnement",
            "energie",
            "nucleaire",
            "eolien",
            "eoliennes",
            "energies renouvelables",
            "agriculture",
            "agriculteur",
            "agriculteurs",
            "agricole",
            "transport",
            "transports",
            "zfe",
        ),
        "subtopics": {
            "climate_environment": (
                "climat",
                "ecologie",
                "transition ecologique",
                "environnement",
            ),
            "energy": (
                "energie",
                "nucleaire",
                "eolien",
                "eoliennes",
                "energies renouvelables",
            ),
            "agriculture": (
                "agriculture",
                "agriculteur",
                "agriculteurs",
                "agricole",
            ),
            "transport": (
                "transport",
                "transports",
                "zfe",
            ),
        },
    },
    {
        "id": "europe_defence_foreign_affairs",
        "label": "Europe, Defence & Foreign Affairs",
        "terms": (
            "union europeenne",
            "commission europeenne",
            "parlement europeen",
            "otan",
            "defense",
            "armee",
            "armees",
            "service militaire",
            "ukraine",
            "russie",
            "gaza",
            "israel",
            "diplomatie",
            "politique etrangere",
            "relations internationales",
        ),
        "subtopics": {
            "europe": (
                "union europeenne",
                "commission europeenne",
                "parlement europeen",
            ),
            "defence": (
                "otan",
                "defense",
                "armee",
                "armees",
                "service militaire",
            ),
            "ukraine_russia": (
                "ukraine",
                "russie",
            ),
            "middle_east": (
                "gaza",
                "israel",
            ),
            "foreign_policy": (
                "diplomatie",
                "politique etrangere",
                "relations internationales",
            ),
        },
    },
    {
        "id": "institutions_democracy_territories",
        "label": "Institutions, Democracy & Territories",
        "terms": (
            "constitution",
            "reforme constitutionnelle",
            "decentralisation",
            "collectivites territoriales",
            "collectivites locales",
            "communes",
            "departements",
            "democratie",
            "institutions",
            "assemblee nationale",
            "proportionnelle",
            "scrutin proportionnel",
        ),
        "subtopics": {
            "constitution": (
                "constitution",
                "reforme constitutionnelle",
            ),
            "decentralisation": (
                "decentralisation",
                "collectivites territoriales",
                "collectivites locales",
                "communes",
                "departements",
            ),
            "democracy": (
                "democratie",
                "institutions",
            ),
            "parliament": (
                "assemblee nationale",
            ),
            "electoral_reform": (
                "proportionnelle",
                "scrutin proportionnel",
            ),
        },
    },
)

POLICY_AGENDA_SUPPORT_LIMIT = 20
POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS = 2
POLICY_AGENDA_EVOLUTION_DAYS = 30
POLICY_AGENDA_COMPARISON_DAYS = 7


POLICY_AGENDA_SUMMARY_BOILERPLATE_TERMS = (
    "france 3 regions",
    "public senat",
)

POLICY_AGENDA_HEALTH_PERSONAL_CONTEXT = (
    "fake news sur sa sante",
    "fake-news sur sa sante",
    "etat de sante",
    "etat de la sante",
)

POLICY_AGENDA_SECURITY_CIVIL_CONTEXT = (
    "securite civile",
    "beauvau de la securite civile",
)

POLICY_AGENDA_POLITICAL_UNIVERSITY_CONTEXT = (
    "universite d ete",
    "universites d ete",
)


POLICY_AGENDA_HEALTH_POLICY_CONTEXT = (
    "politique de sante",
    "sante publique",
    "systeme de sante",
    "systeme de soins",
    "assurance maladie",
    "securite sociale",
    "hopital",
    "hopitaux",
    "medecin",
    "medecins",
    "soins",
    "deserts medicaux",
    "urgences",
    "ehpad",
    "remboursement",
)

POLICY_AGENDA_EDUCATION_POLICY_CONTEXT = (
    "education nationale",
    "politique educative",
    "systeme educatif",
    "ecole publique",
    "ecoles publiques",
    "enseignement",
    "enseignant",
    "enseignants",
    "eleve",
    "eleves",
    "programme scolaire",
    "programmes scolaires",
    "classes",
    "baccalaureat",
    "parcoursup",
)



# These expressions occur frequently in ordinary institutional or
# legislative reporting. They contribute to Topic Coverage only when the
# headline itself has already been classified as current presidential news.
CAMPAIGN_AGENDA_CONTEXT_REQUIRED_TERMS = frozenset({
    "conseil constitutionnel",
    "niches parlementaires",
    "referendum",
})

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
        "bracelet electronique",
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
        "se prepare a entrer en campagne",
        "entree en campagne",
        "lance sa campagne",
        "rejoint la campagne",
        "quitte la campagne",
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
    "senat",
)

# Broad article-level relevance is intentionally less strict than the
# Recent Changes event gate, but generic office words such as "Elysee",
# "president", or a bare year must never establish race relevance.
RELEVANT_PRESIDENTIAL_TERMS = (
    "presidentielle",
    "presidentielles",
    "election presidentielle",
    "elections presidentielles",
    "prochaine presidentielle",
    "scrutin presidentiel",
    "prochain scrutin presidentiel",
    "course a l elysee",
    "elysee 2027",
    "500 signatures",
    "parrainage presidentiel",
    "parrainages presidentiels",
    "sondage presidentiel",
    "sondages presidentiels",
)

RELEVANT_CAMPAIGN_TERMS = (
    "candidature",
    "candidatures",
    "candidat",
    "candidats",
    "candidate",
    "candidates",
    "campagne",
    "primaire",
    "investiture",
    "programme",
    "meeting",
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

SUMMARY_CAMPAIGN_EXTRA_TERMS = (
    "nomination",
    "rassemblement",
    "retrait",
    "retire",
)

SUMMARY_HIGH_SPECIFICITY_SELECTION_TERMS = (
    "primaire",
    "investiture",
    "vote des adherents",
)

SUMMARY_PASSAGE_BOUNDARY_PATTERN = re.compile(
    r"(?:\r?\n+|(?<=[.!?;])\s+)"
)
ELYSEE_2027_OUTCOME_PATTERN = re.compile(
    r"\b(?:accede|acceder|accedera|accedait|parvient|parviendra)"
    r"\s+a\s+l\s+elysee(?:\s+en)?\s+2027\b"
)
ASSERTED_PRESIDENTIAL_CANDIDATE_PATTERN = re.compile(
    r"\b(?:(?:le|la|les|ces|un|une)\s+(?:deux\s+)?)?"
    r"candidat(?:e|s|es)?"
    r"(?:\s+[a-z0-9]+){0,3}\s+(?:a|pour)\s+(?:(?:l|la|le)\s+)?"
    r"(?:election\s+)?presidentielle(?:s)?(?:\s+de\s+2027)?\b"
)
COLLECTIVE_PRESIDENTIAL_CANDIDATE_PATTERN = re.compile(
    r"\bles\s+deux\s+candidat(?:e|s|es)?"
    r"(?:\s+[a-z0-9]+){0,3}\s+(?:a|pour)\s+(?:(?:l|la|le)\s+)?"
    r"(?:election\s+)?presidentielle(?:s)?(?:\s+de\s+2027)?\b"
)
SPECULATIVE_CANDIDACY_PATTERN = re.compile(
    r"\b(?:pourrait|pourraient|serait|seraient)\s+"
    r"(?:etre\s+)?candidat(?:e|s|es)?\b|"
    r"\b(?:pourrait|pourraient)\s+se\s+presenter\b"
)
SUMMARY_ANAPHORIC_ACTOR_PATTERN = re.compile(
    r"\b(?:le|la|les)\s+candidat(?:e|s|es)?\b|"
    r"\b(?:il|elle|ils|elles|ce\s+dernier|cette\s+derniere)\b"
)
SUMMARY_ACTOR_ACTION_TAIL_PATTERN = re.compile(
    r"^(?:\s+[a-z0-9]+){0,6}\s+\b(?:propose|menace|veut|annonce|"
    r"affirme|demande|denonce|appelle|ecrit|accuse|evoque|envisage|"
    r"entend|inscrit|s\s+exprime|avait\s+(?:evoque|envisage)|"
    r"s\s+oppose)\b"
)
SUMMARY_PARTY_ACTOR_ACTION_PATTERN = re.compile(
    r"\b(?:patron|patronne|chef|cheffe|leader)\s+"
    r"(?:du|de\s+la|des)\s+(?:parti|ecologistes|rn|renaissance|"
    r"horizons|ps|lr|lfi)\b(?:\s+[a-z0-9]+){0,6}\s+"
    r"\b(?:propose|menace|veut|annonce|affirme|demande|denonce|"
    r"appelle|ecrit|s\s+oppose)\b"
)
SUMMARY_CANDIDATE_SELECTION_PATTERN = re.compile(
    r"\b(?:designe|designer|nomme|nommer|choisit|choisir|prepare|"
    r"preparer|presente|presenter|selectionne|selectionner)\b"
    r"(?:\s+[a-z0-9]+){0,6}\s+\b(?:candidat|candidate)\b"
)
SUMMARY_PARTY_LEADER_CANDIDACY_PATTERN = re.compile(
    r"\bcandidature\s+d(?:e|u|es)?\s+(?:la\s+|le\s+|l\s+)?"
    r"(?:chef|cheffe|leader|patron|patronne|president|presidente)"
    r"(?:\s+[a-z0-9]+){0,6}"
)
SUMMARY_HEADLINE_CANDIDATE_REFERENCE_PATTERN = re.compile(
    r"\b(?:sa\s+candidature|son\s+investiture|aspirant\s+candidat|"
    r"aspirante\s+candidate|candidature\s+d(?:e|u|es)?\s+(?:la\s+|le\s+|l\s+)?"
    r"(?:chef|cheffe|leader|patron|patronne|president|presidente)"
    r"|(?:il|elle)(?:\s+[a-z0-9]+){0,4}\s+(?:vise|brigue|convoite))\b"
)
SUMMARY_ELECTORAL_CAMPAIGN_PATTERN = re.compile(
    r"\b(?:campagne\s+(?:presidentielle|electorale)"
    r"|campagne\s+(?:de|des|pour)\s+(?:l\s+)?"
    r"(?:election\s+presidentielle|elections\s+presidentielles)"
    r"|campagne\s+(?:de|pour)\s+2027"
    r"|en\s+campagne(?:\s+[a-z0-9]+){0,4}\s+(?:presidentielle|2027)"
    r"|deplacement\s+de\s+campagne)\b"
)
SUMMARY_WITHDRAWAL_PATTERN = re.compile(
    r"\b(?:renonce|renoncer|se\s+retire|retire|retrait)\b"
    r"(?:\s+[a-z0-9]+){0,8}\s+"
    r"\b(?:candidature|investiture|primaire|campagne\s+presidentielle)\b"
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
    "candidature",
    "candidat",
    "candidate",
    "campagne",
    "primaire",
    "investiture",
    "programme",
    "alliance",
    "coalition",
    "sondage",
    "parrainage",
    "propose",
    "presente",
    "promet",
    "explique",
    "detaille",
    "defend",
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
    r"\b(?:presidentielles?|election\s+presidentielle|"
    r"elections\s+presidentielles|scrutin\s+presidentiel)"
    r"(?:\s+francais(?:e|es)?)?"
    r"(?:\s+(?:de|en))?\s+((?:19|20)\d{2})\b"
)
HISTORICAL_RETROSPECTIVE_SUBJECT_PATTERN = re.compile(
    r"(?:"
    r"\b(?:aujourd\s+hui|retour\s+sur|archives?|souvenir)\b"
    r"(?:\s+[a-z0-9]+){0,8}\s+\b(?:l\s+)?election\s+de\s+"
    r"(?:19\d{2}|20(?:0\d|1\d|2[0-6]))\b|"
    r"\b(?:aujourd\s+hui\s+)?retour\s+en\s+"
    r"(?:19\d{2}|20(?:0\d|1\d|2[0-6]))\b"
    r")"
)
HISTORICAL_RETROSPECTIVE_HEADLINE_PATTERN = re.compile(
    r"(?:"
    r"\bretour\s+sur\s+(?:les\s+)?campagnes?\s+presidentielles?\b|"
    r"\bvisites?\s+presidentielles?\b"
    r"(?:\s+[a-z0-9]+){0,12}\s+\b(?:menait|mener)\s+campagne\b|"
    r"\bquels\s+etaient\s+les\s+resultats\b"
    r"(?:\s+[a-z0-9]+){0,8}\s+\b(?:19|20)\d{2}\b"
    r")"
)
FOREIGN_ELECTION_SUBJECT_PATTERN = re.compile(
    r"(?:"
    r"\b(?:bresil|madagascar|roumanie|iowa|etats\s+unis)\b|"
    r"\b(?:iowa|etats\s+unis|americain|americaine|americains|americaines|"
    r"bresil|bresilien|bresilienne|roumanie|roumain|roumaine)\b"
    r"(?:\s+[a-z0-9]+){0,12}\s+"
    r"\b(?:democrate|republicain|gouverneur|election|candidat|candidate)\b|"
    r"\b(?:democrate|republicain|gouverneur|election|candidat|candidate)\b"
    r"(?:\s+[a-z0-9]+){0,12}\s+"
    r"\b(?:iowa|etats\s+unis|americain|americaine|americains|americaines|"
    r"bresil|bresilien|bresilienne|roumanie|roumain|roumaine)\b"
    r")"
)
EXPLICIT_FRENCH_RACE_HEADLINE_PATTERN = re.compile(
    r"\b(?:presidentielle|election\s+presidentielle)\s+francaise\b|"
    r"\b(?:presidentielle|election\s+presidentielle|elysee)"
    r"(?:\s+[a-z0-9]+){0,8}\s+2027\b|"
    r"\b2027\b(?:\s+[a-z0-9]+){0,8}\s+"
    r"\b(?:presidentielle|election\s+presidentielle|elysee)\b"
)

RACE_QUALIFIED_LEGAL_ELIGIBILITY_PATTERN = re.compile(
    r"\b(?:"
    r"ineligibilite|"
    r"(?:reste|demeure|est|devient)\s+(?:in)?eligible|"
    r"ne\s+(?:peut|pourra)\s+plus\s+(?:etre\s+)?candidat(?:e)?|"
    r"peut\s+toujours\s+se\s+presenter|"
    r"(?:menace|compromet|empeche|preserve)\s+sa\s+candidature|"
    r"(?:menace\s+(?:du\s+)?|sous\s+)?bracelet\s+electronique"
    r"(?:\s+[a-z0-9]+){0,8}\s+\b(?:avant|pour|en)\s+2027"
    r")\b"
)
ELECTED_PRESIDENT_POSITIONING_PATTERN = re.compile(
    r"\b(?:"
    r"(?:s\s+il|si\s+elle)\s+(?:etait|est|sera|serait)\s+elu(?:e)?"
    r"(?:\s+president(?:e)?)?(?:\s+en\s+2027)?|"
    r"(?:devenait|deviendrait|devient|deviendra)\s+president(?:e)?|"
    r"serait\s+(?:le|la)\s+president(?:e)?"
    r")\b"
)
PROGRAMMATIC_POSITIONING_PATTERN = re.compile(
    r"\b(?:promet|propose|souhaite|veut|assure|affirme|annonce|presente|"
    r"detaille|defend|plan|programme|projet|reforme|referendum|mesure)\b|"
    r"\b(?:mettrait|mettra|mettre)\s+en\s+(?:oeuvre|uvre)\b"
)
DIRECT_PRESIDENTIAL_OFFICE_POSITIONING_PATTERN = re.compile(
    r"\b(?:devenait|deviendrait|devient|deviendra)\s+president(?:e)?\b|"
    r"\bserait\s+(?:le|la)\s+president(?:e)?\b|"
    r"\b(?:s\s+il|si\s+elle)\s+(?:etait|est|sera|serait)\s+"
    r"elu(?:e)?\s+president(?:e)?\b"
)
RACE_YEAR_CAMPAIGN_PATTERN = re.compile(
    r"(?:"
    r"\b2027\b(?:\s+[a-z0-9]+){0,8}\s+"
    r"\b(?:candidat|candidate|candidature|campagne|primaire|investiture|"
    r"programme|sondage|sondages|course)\b|"
    r"\b(?:candidat|candidate|candidature|campagne|primaire|investiture|"
    r"programme|sondage|sondages|course)\b"
    r"(?:\s+[a-z0-9]+){0,8}\s+\b2027\b"
    r")"
)
PRESIDENTIAL_CANDIDACY_PATTERN = re.compile(
    r"\b(?:"
    r"(?:candidat(?:e)?|candidature)\s+(?:a|pour)\s+(?:la\s+)?"
    r"(?:election\s+)?presidentielle|"
    r"se\s+presente\s+(?:a|pour)\s+(?:la\s+)?"
    r"(?:election\s+)?presidentielle|"
    r"candidat(?:e)?\s+(?:a|pour)\s+(?:l\s+)?elysee|"
    r"candidature\s+(?:a|pour)\s+(?:l\s+)?elysee|"
    r"(?:candidat(?:e)?|candidature)\s+(?:a|pour)\s+(?:la\s+)?"
    r"presidence\s+de\s+la\s+republique|"
    r"(?:ambition|ambitions)\s+presidentielle(?:s)?|"
    r"(?:candidat|candidate)\s+(?:de|pour)\s+(?:son|mon|notre|leur|le|la)\s+camp|"
    r"candidat(?:e)?\b(?:\s+[a-z0-9]+){0,10}\s+"
    r"\b(?:arriver|acceder|entrer|viser|conquerir)\s+a\s+l\s+elysee"
    r")\b"
)
PRESIDENTIAL_PROGRAMME_PATTERN = re.compile(
    r"\bprogramme\s+(?:presidentiel|presidentielle|electoral|electorale)\b"
)
PRESIDENTIAL_FIELD_PATTERN = re.compile(
    r"\b(?:pretendant|pretendants|pretendante|pretendantes|"
    r"candidat|candidats|candidate|candidates)\b"
    r"(?:\s+[a-z0-9]+){0,4}\s+a\s+la\s+presidentielle\b"
)
PRE_PRESIDENTIAL_ACTIVITY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:tour|tournee|deplacement|campagne|meeting|terrain)\b"
    r"(?:\s+[a-z0-9]+){0,6}\s+\bpre\s+presidentiel(?:le)?\b|"
    r"\bpre\s+presidentiel(?:le)?\b(?:\s+[a-z0-9]+){0,6}\s+"
    r"\b(?:tour|tournee|deplacement|campagne|meeting|terrain)\b"
    r")"
)
EXPLICIT_CAMPAIGN_ACTIVITY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:accelere|lance|entame|poursuit|continue|reprend|clot|clore|"
    r"boucle)\b\s+(?:sa|la|une)\s+campagne\b|"
    r"\bdirecteur\s+de\s+campagne\b|"
    r"\b(?:va\s+)?dirig(?:e|er|era)\b(?:\s+[a-z0-9]+){0,4}\s+"
    r"\b(?:la|sa|une)\s+campagne\b|"
    r"\bdans\s+la\s+campagne\s+(?:de|du|d)\b|"
    r"\bfaire\s+campagne\b(?!\s+pour\s+(?:la|le|une|un)?\s*"
    r"(?:vaccination|sensibilisation|sante))|"
    r"\b(?:tour|tournee|deplacement|escale|tro\s+breizh)\b"
    r"(?:\s+[a-z0-9]+){0,8}\s+\b(?:de|en)\s+campagne\b|"
    r"\ben\s+campagne\b(?!\s+(?:de|pour)\s+(?:la|le|une|un)?\s*"
    r"(?:vaccination|sensibilisation|publicite|sante))"
    r")"
)
IMPLICIT_2027_POSITIONING_PATTERN = re.compile(
    r"\b(?:pret|prete)\b(?:\s+[a-z0-9]+){0,4}\s+\ba\s+etre\s+"
    r"(?:le|la|un|une)\s+recours\b(?:\s+[a-z0-9]+){0,3}\s+\b2027\b"
)
CAMPAIGN_POLLING_RELATIONSHIP_PATTERN = re.compile(
    r"(?:"
    r"\bcampagne\b(?:\s+[a-z0-9]+){0,10}\s+\bsondages?\b|"
    r"\bsondages?\b(?:\s+[a-z0-9]+){0,10}\s+\bcampagne\b|"
    r"\bsondage\s+exclusif\b(?:\s+[a-z0-9]+){0,16}\s+"
    r"\b(?:coude\s+a\s+coude|intentions?\s+de\s+vote|second\s+tour)\b"
    r")"
)
CANDIDACY_RACE_CONSEQUENCE_PATTERN = re.compile(
    r"\bcandidature\b(?:\s+[a-z0-9]+){0,12}\s+"
    r"\b(?:rebat\s+les\s+cartes|francais\s+auront\s+le\s+dernier\s+mot)\b"
)
PARTY_LEADERSHIP_ELECTION_PATTERN = re.compile(
    r"\b(?:reelection|succession)\b|"
    r"\b(?:president|presidente|tete)\s+(?:du|de\s+la|des)\s+"
    r"(?:parti|rassemblement\s+national|rn|renaissance|horizons|ps|lr|lfi)\b"
)
ORDINARY_LEGAL_HEADLINE_PATTERN = re.compile(
    r"\b(?:"
    r"enquete|assigne|justice|deboute|faire\s+appel|porte\s+plainte|"
    r"depose\s+plainte|parquet|condamne|condamnee|condamnation|"
    r"lanceuse\s+d\s+alerte|mis\s+en\s+examen|mise\s+en\s+examen"
    r")\b"
)
LEGAL_TEMPORAL_PRESIDENTIAL_FRAME_PATTERN = re.compile(
    r"\ba\s+(?:[a-z0-9]+\s+){0,2}(?:mois|an|ans)\s+de\s+la\s+"
    r"presidentielle\b"
)
ELECTION_INTEGRITY_HEADLINE_PATTERN = re.compile(
    r"\b(?:ingerence|ingerences|desinformation|interference|"
    r"faux\s+comptes|campagne\s+de\s+manipulation|"
    r"election\s+(?:peut\s+etre\s+)?faussee|scrutin\s+fausse)\b"
)
SUMMARY_ELECTION_INTEGRITY_PATTERN = re.compile(
    r"\b(?:ingerence|ingerences|desinformation|interference|"
    r"operation\s+de\s+destabilisation|fausse\s+enquete|"
    r"(?:influencer|fausser|voler)\s+(?:la\s+)?(?:couverture|election|scrutin))\b"
)
FRENCH_ELECTION_INTEGRITY_PATTERN = re.compile(
    r"\b(?:voler|fausser)\s+(?:l\s+)?election\s+aux\s+francais\b|"
    r"\bsincerite\s+du\s+scrutin\s+presidentiel\b"
)
CURRENT_PRESIDENTIAL_TIMING_PATTERN = re.compile(
    r"\b(?:a|environ|moins\s+de)\s+[a-z0-9]+\s+mois\s+"
    r"(?:(?:de|avant)\s+(?:la|l)\s+"
    r"(?:election\s+)?presidentielle|du\s+scrutin)\b|"
    r"\b(?:avant|en\s+vue\s+de)\s+(?:la|l)\s+"
    r"(?:election\s+)?presidentielle\b"
)
FRENCH_RACE_INSTITUTION_PATTERN = re.compile(
    r"\bmatignon\b|\b500\s+parrainages\b"
)
PRESIDENTIAL_CAMPAIGN_FINANCE_PATTERN = re.compile(
    r"\bfinancement\s+(?:de\s+)?(?:la\s+)?campagne\s+presidentielle\b|"
    r"\bfinanc(?:er|ement)\b(?:\s+[a-z0-9]+){0,8}\s+"
    r"\b(?:campagne\s+presidentielle|candidat|candidats|candidate|candidates)\b"
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

ELECTORAL_SUPPORT_ACTION_PATTERN = re.compile(
    r"\b(?:"
    r"soutien|(?:je|tu)\s+soutiens|soutient|soutiennent|soutenir|"
    r"soutenu|soutenue|soutenus|soutenues|"
    r"appui|appuie|appuient|appuyer"
    r")\b"
)
ELECTORAL_RALLY_ACTION_PATTERN = re.compile(
    r"\b(?:se\s+rallie|se\s+rallient|rallie|rallient|"
    r"rallier|ralliement|ralliements)\b"
)
ELECTORAL_INTRINSIC_DESTINATION_PATTERN = re.compile(
    r"^(?:"
    r"candidature|candidat|candidate|candidats|candidates|"
    r"investiture|presidentielle|election\s+presidentielle|"
    r"second\s+tour"
    r")(?:\s|$)"
)
ELECTORAL_GENERIC_ACTOR_PATTERN = re.compile(
    r"^(?:candidat|candidate|candidats|candidates)(?:\s|$)"
)
ELECTORAL_QUALIFIED_DESTINATION_PATTERN = re.compile(
    r"^(?:"
    r"campagne\s+(?:presidentielle|electorale)|"
    r"(?:alliance|coalition)\s+(?:electorale|presidentielle)|"
    r"ticket\s+(?:presidentiel|electoral)"
    r")(?:\s|$)"
)
ELECTORAL_VOTE_SUPPORT_PATTERN = re.compile(
    r"\bappell(?:e|ent|er)\s+a\s+voter\s+pour\b"
)
ELECTORAL_DESTINATION_PREPOSITION_PATTERN = re.compile(
    r"^(?:(?:a|au|aux|pour|d|de|du|des)\s+)"
)
ELECTORAL_DESTINATION_ARTICLE_PATTERN = re.compile(
    r"^(?:(?:l|la|le|les|un|une)\s+)"
)
ELECTORAL_NOUN_ACTIONS = frozenset({
    "appui",
    "ralliement",
    "ralliements",
    "soutien",
})
ELECTORAL_SOURCE_PREPOSITIONS = frozenset({"d", "de", "du", "des"})
ELECTORAL_DESTINATION_PREPOSITIONS = frozenset({"a", "au", "aux", "pour"})
ELECTORAL_SOURCE_MAX_TOKENS = 6
ELECTORAL_SUPPORT_WINDOW_TOKENS = 10


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


def canonical_news_candidate_name(value: Any) -> str:
    """Return one reviewed public identity for a poll candidate label."""

    candidate = str(value or "").strip()
    normalized_candidate = normalize(candidate)

    if not normalized_candidate:
        return ""

    for alternate_name, canonical_name in (
        NEWS_CANDIDATE_NAME_OVERRIDES.items()
    ):
        if normalized_candidate in {
            normalize(alternate_name),
            normalize(canonical_name),
        }:
            return canonical_name

    return candidate


def canonical_news_candidate_roster(
    candidates: Any,
) -> list[str]:
    """Canonicalize and deterministically deduplicate candidate labels."""

    if not isinstance(candidates, (list, tuple, set, frozenset)):
        return []

    return sorted(
        {
            canonical
            for value in candidates
            if (
                canonical := canonical_news_candidate_name(value)
            )
        }
    )


def news_candidate_aliases(
    candidates: list[str],
) -> list[tuple[str, tuple[str, ...]]]:
    """Return deterministic, reviewed aliases for canonical candidates."""

    aliases_by_candidate: list[tuple[str, tuple[str, ...]]] = []

    for candidate in canonical_news_candidate_roster(candidates):
        normalized_full_name = normalize(candidate)
        aliases: set[str] = set()

        # A one-token roster label is not precise enough to become a
        # news alias.
        if len(normalized_full_name.split()) > 1:
            aliases.add(normalized_full_name)

        # Reviewed poll labels containing more than one token remain
        # useful exact text aliases. Surname-only labels remain excluded.
        aliases.update(
            normalized_alternate
            for alternate_name, canonical_name in (
                NEWS_CANDIDATE_NAME_OVERRIDES.items()
            )
            if (
                canonical_name == candidate
                and (
                    normalized_alternate := normalize(
                        alternate_name
                    )
                )
                and len(normalized_alternate.split()) > 1
            )
        )

        aliases.update(
            normalized_alias
            for alias in NEWS_CANDIDATE_ALIAS_OVERRIDES.get(
                candidate,
                (),
            )
            if (normalized_alias := normalize(alias))
        )

        if aliases:
            aliases_by_candidate.append((candidate, tuple(sorted(aliases))))

    return aliases_by_candidate


def normalized_alias_matches(normalized_text: str, alias: str) -> bool:
    """Match complete normalized token sequences, never partial tokens."""

    return f" {alias} " in f" {normalize(normalized_text)} "


def classify_structured_electoral_support(
    value: Any,
    matched_candidates: list[str] | None = None,
) -> dict[str, Any]:
    """Return bounded electoral-support evidence and ambiguity provenance.

    A support or rallying verb is not campaign evidence by itself. Its
    grammatical destination must begin with an electoral object, monitored
    candidate, or recognized party. Bounded source phrases may intervene only
    in explicit noun-source-destination constructions.
    """

    text = normalize(value)
    candidates = [
        normalized
        for candidate in (matched_candidates or [])
        if (normalized := normalize(candidate))
    ]
    matched_terms: set[str] = set()
    vote_matches = list(ELECTORAL_VOTE_SUPPORT_PATTERN.finditer(text))
    support_matches = list(ELECTORAL_SUPPORT_ACTION_PATTERN.finditer(text))
    rally_matches = list(ELECTORAL_RALLY_ACTION_PATTERN.finditer(text))

    party_destinations = {
        variant
        for party in PARTY_CONTEXT_TERMS
        for variant in (
            party,
            ELECTORAL_DESTINATION_ARTICLE_PATTERN.sub(
                "",
                party,
                count=1,
            ),
        )
    }

    def bounded_tail(match: re.Match[str]) -> str:
        return " ".join(
            text[match.end():].split()[:ELECTORAL_SUPPORT_WINDOW_TOKENS]
        )

    def destination_variants(tail: str) -> tuple[str, ...]:
        without_preposition = ELECTORAL_DESTINATION_PREPOSITION_PATTERN.sub(
            "",
            tail,
            count=1,
        )
        without_article = ELECTORAL_DESTINATION_ARTICLE_PATTERN.sub(
            "",
            without_preposition,
            count=1,
        )
        return tuple(dict.fromkeys((
            without_preposition,
            without_article,
        )))

    def starts_actor(destination: str) -> bool:
        return any(
            destination == candidate
            or destination.startswith(candidate + " ")
            for candidate in candidates
        ) or any(
            destination == party
            or destination.startswith(party + " ")
            for party in party_destinations
        )

    def starts_bound_actor(destination: str) -> bool:
        return (
            starts_actor(destination)
            or bool(ELECTORAL_GENERIC_ACTOR_PATTERN.match(destination))
        )

    def is_electoral_destination(tail: str) -> bool:
        for destination in destination_variants(tail):
            if (
                starts_actor(destination)
                or ELECTORAL_INTRINSIC_DESTINATION_PATTERN.match(destination)
                or ELECTORAL_QUALIFIED_DESTINATION_PATTERN.match(destination)
            ):
                return True

            for object_name in ("campagne", "ticket"):
                binding = re.match(
                    rf"^{object_name}\s+(?:d|de|du|des|pour)\s+(.+)$",
                    destination,
                )
                if binding and any(
                    starts_bound_actor(variant)
                    for variant in destination_variants(binding.group(1))
                ):
                    return True
        return False

    def source_to_electoral_destination(tail: str) -> bool:
        tokens = tail.split()
        if (
            len(tokens) < 3
            or tokens[0] not in ELECTORAL_SOURCE_PREPOSITIONS
        ):
            return False

        final_source_index = min(
            len(tokens) - 2,
            ELECTORAL_SOURCE_MAX_TOKENS + 1,
        )
        for index in range(2, final_source_index + 1):
            if tokens[index] not in ELECTORAL_DESTINATION_PREPOSITIONS:
                continue
            return is_electoral_destination(" ".join(tokens[index:]))
        return False

    def action_has_electoral_destination(match: re.Match[str]) -> bool:
        tail = bounded_tail(match)
        tokens = tail.split()
        is_noun_action = match.group() in ELECTORAL_NOUN_ACTIONS
        starts_with_source = bool(
            tokens and tokens[0] in ELECTORAL_SOURCE_PREPOSITIONS
        )
        is_au_soutien_destination = bool(
            match.group() == "soutien"
            and re.search(r"\bau\s*$", text[:match.start()])
        )

        if (
            is_noun_action
            and starts_with_source
            and not is_au_soutien_destination
        ):
            return source_to_electoral_destination(tail)
        return is_electoral_destination(tail)

    for match in support_matches:
        if action_has_electoral_destination(match):
            matched_terms.add("electoral_support")

    for match in rally_matches:
        if action_has_electoral_destination(match):
            matched_terms.add("electoral_rallying")

    for match in vote_matches:
        if action_has_electoral_destination(match):
            matched_terms.add("call_to_vote_for")

    return {
        "has_support_language": bool(
            support_matches or rally_matches or vote_matches
        ),
        "matched_terms": sorted(matched_terms),
    }


def match_news_candidates(
    headline: Any,
    summary: Any,
    candidates: list[str],
) -> list[dict[str, Any]]:
    """Return exact candidate matches with field-level provenance."""

    normalized_fields = {
        "headline": normalize(headline),
        "summary": normalize(summary),
    }
    matches: list[dict[str, Any]] = []

    for candidate, aliases in news_candidate_aliases(candidates):
        matched_aliases = [
            alias
            for alias in aliases
            if any(
                normalized_alias_matches(text, alias)
                for text in normalized_fields.values()
            )
        ]
        if not matched_aliases:
            continue

        locations = [
            location
            for location in CANDIDATE_MATCH_LOCATIONS
            if any(
                normalized_alias_matches(normalized_fields[location], alias)
                for alias in matched_aliases
            )
        ]
        matches.append(
            {
                "candidate": candidate,
                "matched_aliases": matched_aliases,
                "locations": locations,
            }
        )

    return matches


def candidate_names_from_matches(
    candidate_matches: list[dict[str, Any]],
) -> list[str]:
    return [match["candidate"] for match in candidate_matches]


def candidate_has_match_location(
    candidate_matches: list[dict[str, Any]],
    location: str,
) -> bool:
    return any(
        location in match.get("locations", [])
        for match in candidate_matches
    )


def validate_candidate_match_contract(
    candidates: Any,
    candidate_matches: Any,
    context: str,
) -> None:
    if (
        not isinstance(candidates, list)
        or any(
            not isinstance(candidate, str) or not candidate.strip()
            for candidate in candidates
        )
        or candidates != sorted(set(candidates))
    ):
        raise RuntimeError(f"{context} has invalid candidates")

    if not isinstance(candidate_matches, list):
        raise RuntimeError(f"{context} candidate_matches is not a list")

    matched_candidates: list[str] = []
    for match in candidate_matches:
        if not isinstance(match, dict) or set(match) != {
            "candidate",
            "matched_aliases",
            "locations",
        }:
            raise RuntimeError(
                f"{context} has malformed candidate_matches"
            )

        candidate = match["candidate"]
        matched_aliases = match["matched_aliases"]
        locations = match["locations"]
        if not isinstance(candidate, str) or not candidate.strip():
            raise RuntimeError(
                f"{context} candidate_matches has an empty candidate"
            )
        if (
            not isinstance(matched_aliases, list)
            or not matched_aliases
            or any(
                not isinstance(alias, str)
                or not alias.strip()
                or alias != normalize(alias)
                for alias in matched_aliases
            )
            or matched_aliases != sorted(set(matched_aliases))
        ):
            raise RuntimeError(
                f"{context} has invalid matched_aliases"
            )
        if (
            not isinstance(locations, list)
            or not locations
            or any(
                location not in CANDIDATE_MATCH_LOCATIONS
                for location in locations
            )
            or len(locations) != len(set(locations))
            or locations != [
                location
                for location in CANDIDATE_MATCH_LOCATIONS
                if location in locations
            ]
        ):
            raise RuntimeError(f"{context} has invalid match locations")
        matched_candidates.append(candidate)

    if matched_candidates != sorted(set(matched_candidates)):
        raise RuntimeError(
            f"{context} has duplicate or unsorted candidate matches"
        )
    if sorted(matched_candidates) != sorted(candidates):
        raise RuntimeError(
            f"{context} candidates disagree with candidate_matches"
        )


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


def load_news_exclusions(
    path: Path | None = None,
) -> set[str]:
    exclusion_path = NEWS_EXCLUSIONS_PATH if path is None else path

    if not exclusion_path.exists():
        return set()

    try:
        payload = json.loads(
            exclusion_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Invalid news exclusions file: {exclusion_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError("News exclusions payload must be an object")

    if payload.get("schema_version") != 1:
        raise RuntimeError(
            "Unsupported news exclusions schema_version"
        )

    values = payload.get("excluded_urls")
    if not isinstance(values, list):
        raise RuntimeError(
            "News exclusions excluded_urls must be an array"
        )

    excluded_urls: set[str] = set()

    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                "News exclusion URLs must be non-empty strings"
            )

        normalized = canonical_url(value)
        if not normalized:
            raise RuntimeError(
                "News exclusion URL could not be canonicalized"
            )

        excluded_urls.add(normalized)

    return excluded_urls


def apply_news_exclusions(
    existing_inventory: dict[str, Any],
    current_entries: list[dict[str, Any]],
    excluded_urls: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not excluded_urls:
        return existing_inventory, current_entries

    def retained(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            entry
            for entry in entries
            if canonical_url(
                entry.get("canonical_url") or entry.get("url")
            )
            not in excluded_urls
        ]

    filtered_inventory = dict(existing_inventory)
    filtered_inventory["items"] = retained(
        list(existing_inventory.get("items") or [])
    )

    return filtered_inventory, retained(current_entries)


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


def active_news_candidate_roster(
    candidacy_payload: Any,
) -> list[str]:
    """Return the validated main-and-secondary monitoring roster."""

    try:
        return active_candidate_names(candidacy_payload)
    except CandidateCandidacyStatusError as error:
        raise RuntimeError(
            f"Candidate candidacy registry is invalid: {error}"
        ) from error


def candidate_roster_metadata(
    candidacy_payload: Any,
) -> dict[str, Any]:
    """Describe the controlled active roster without poll-window metadata."""

    candidates = active_news_candidate_roster(candidacy_payload)
    metadata = {
        "source": CANDIDACY_STATUS_SOURCE,
        "rule": ACTIVE_CANDIDATE_ROSTER_RULE,
        "status_as_of": candidacy_payload["status_as_of"],
        "count": len(candidates),
        "names": candidates,
    }
    if candidacy_payload.get("schema_version") == "2.0":
        try:
            provenance = active_projection_provenance(candidacy_payload)
        except CandidateCandidacyStatusError as error:
            raise RuntimeError(
                f"Candidate candidacy registry is invalid: {error}"
            ) from error
        metadata["source_revision_id"] = provenance["source_revision_id"]
        metadata["source_revision_timestamp"] = provenance[
            "source_revision_timestamp"
        ]
    return metadata


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


def summary_campaign_context_evidence(
    raw_summary: Any,
    headline_party_matches: list[str],
    matched_candidates: list[str],
    candidate_matches: list[dict[str, Any]],
    headline_election_integrity: bool = False,
    headline_supports_summary_relationship: bool = False,
) -> list[str]:
    """Return campaign evidence confined to qualifying summary passages."""

    summary = html.unescape(str(raw_summary or ""))
    summary = re.sub(
        r"</?(?:br|div|h[1-6]|li|p)[^>]*>",
        "\n",
        summary,
        flags=re.IGNORECASE,
    )
    base_passages = [
        normalized
        for passage in SUMMARY_PASSAGE_BOUNDARY_PATTERN.split(summary)
        if (normalized := normalize(passage))
    ]
    passages = list(base_passages)
    # A short adjacent sentence may carry an anaphoric actor reference, as in
    # "Marine Tondelier ... présidentielle. La candidate ... campagne".
    # Only those explicitly linked pairs are joined; arbitrary neighboring
    # presidential sentences cannot rescue an unrelated article subject.
    for left, right in zip(base_passages, base_passages[1:]):
        if (
            SUMMARY_ANAPHORIC_ACTOR_PATTERN.search(right)
            and len(left.split()) + len(right.split()) <= 80
        ):
            passages.append(f"{left} {right}")
    candidate_aliases = sorted({
        alias
        for match in candidate_matches
        for alias in match.get("matched_aliases", [])
        if alias
    })
    candidate_in_headline = candidate_has_match_location(
        candidate_matches,
        "headline",
    )
    campaign_terms = tuple(dict.fromkeys((
        *RELEVANT_CAMPAIGN_TERMS,
        *SUMMARY_CAMPAIGN_EXTRA_TERMS,
    )))
    qualifying_evidence: set[str] = set()

    for passage in passages:
        passage_campaign_matches = campaign_agenda_term_matches(
            passage,
            campaign_terms,
        )
        passage_integrity = bool(
            SUMMARY_ELECTION_INTEGRITY_PATTERN.search(passage)
        )
        passage_presidential_anchors = set(
            current_presidential_matches(passage)
        )
        asserted_candidate_match = (
            ASSERTED_PRESIDENTIAL_CANDIDATE_PATTERN.search(passage)
        )
        asserted_candidate_relationship = bool(
            asserted_candidate_match
            and not SPECULATIVE_CANDIDACY_PATTERN.search(passage)
        )
        asserted_candidate_subject = bool(
            asserted_candidate_relationship
            and asserted_candidate_match
            and SUMMARY_ACTOR_ACTION_TAIL_PATTERN.search(
                passage[asserted_candidate_match.end():]
            )
        )
        party_actor_subject = bool(
            SUMMARY_PARTY_ACTOR_ACTION_PATTERN.search(passage)
        )
        elysee_outcome = bool(
            ELYSEE_2027_OUTCOME_PATTERN.search(passage)
        )
        if not (
            passage_campaign_matches
            or passage_integrity
            or asserted_candidate_relationship
            or elysee_outcome
            or (
                headline_election_integrity
                and passage_presidential_anchors
            )
        ):
            continue
        if (
            not passage_presidential_anchors
            and campaign_agenda_term_matches(
                passage,
                NON_PRESIDENTIAL_ELECTION_TERMS,
            )
        ):
            continue
        historical_years = {
            match.group(1)
            for match in HISTORICAL_PRESIDENTIAL_YEAR_PATTERN.finditer(
                passage
            )
        }
        if historical_years and "2027" not in historical_years:
            continue

        local_headline_parties = [
            party
            for party in headline_party_matches
            if normalized_alias_matches(passage, party)
        ]
        local_party_matches = campaign_agenda_term_matches(
            passage,
            PARTY_CONTEXT_TERMS,
        )
        local_candidate = any(
            normalized_alias_matches(passage, alias)
            for alias in candidate_aliases
        )
        actor_evidence = set(local_headline_parties)
        if local_candidate and (
            candidate_in_headline or local_headline_parties
        ):
            actor_evidence.add("candidate_in_summary")
        if (
            candidate_in_headline
            and asserted_candidate_relationship
            and (
                headline_election_integrity
                or headline_supports_summary_relationship
                or asserted_candidate_subject
            )
        ):
            actor_evidence.add("headline_candidate_race_relationship")
        if (
            candidate_in_headline
            and SUMMARY_ANAPHORIC_ACTOR_PATTERN.search(passage)
            and SUMMARY_ELECTORAL_CAMPAIGN_PATTERN.search(passage)
        ):
            actor_evidence.add("headline_candidate_race_relationship")
        if candidate_in_headline and party_actor_subject:
            actor_evidence.add("headline_party_actor_relationship")
        if (
            len(matched_candidates) >= 2
            and COLLECTIVE_PRESIDENTIAL_CANDIDATE_PATTERN.search(passage)
            and not SPECULATIVE_CANDIDACY_PATTERN.search(passage)
        ):
            actor_evidence.add("collective_headline_actors")

        presidential_anchors = set(passage_presidential_anchors)
        if elysee_outcome:
            presidential_anchors.add("elysee_2027_outcome")
        if PRESIDENTIAL_CANDIDACY_PATTERN.search(passage):
            presidential_anchors.add("presidential_candidacy")

        candidacy_matches = campaign_agenda_term_matches(
            passage,
            (
                "candidat",
                "candidats",
                "candidate",
                "candidates",
                "candidature",
                "candidatures",
            ),
        )
        if (
            local_candidate
            and candidacy_matches
            and presidential_anchors
            and SUMMARY_ANAPHORIC_ACTOR_PATTERN.search(passage)
            and not SPECULATIVE_CANDIDACY_PATTERN.search(passage)
        ):
            actor_evidence.add("bounded_summary_candidate_relationship")
        high_specificity_matches = campaign_agenda_term_matches(
            passage,
            SUMMARY_HIGH_SPECIFICITY_SELECTION_TERMS,
        )
        candidate_selection = bool(
            SUMMARY_CANDIDATE_SELECTION_PATTERN.search(passage)
        ) or bool(
            campaign_agenda_term_matches(
                passage,
                ("designation", "nomination"),
            )
            and candidacy_matches
        )
        party_leader_candidacy = bool(
            candidate_in_headline
            and local_party_matches
            and SUMMARY_PARTY_LEADER_CANDIDACY_PATTERN.search(passage)
            and presidential_anchors
        )
        withdrawal = bool(SUMMARY_WITHDRAWAL_PATTERN.search(passage))
        electoral_support = classify_structured_electoral_support(
            passage,
            matched_candidates,
        )["matched_terms"]

        headline_candidate_reference = bool(
            SUMMARY_HEADLINE_CANDIDATE_REFERENCE_PATTERN.search(passage)
        )
        if candidate_in_headline and headline_candidate_reference and (
            presidential_anchors
            or high_specificity_matches
            or candidate_selection
            or party_leader_candidacy
            or withdrawal
        ):
            actor_evidence.add("candidate_in_headline")

        passage_evidence: set[str] = set()
        if actor_evidence and (
            high_specificity_matches
            or candidate_selection
            or (
                electoral_support
                and presidential_anchors
            )
        ):
            passage_evidence.update(high_specificity_matches)
            if candidate_selection:
                passage_evidence.add("candidate_selection")
            passage_evidence.update(electoral_support)
            passage_evidence.update(candidacy_matches)

        if party_leader_candidacy:
            passage_evidence.update({
                "candidature",
                "party_leader_candidacy",
                *local_party_matches,
            })

        if (
            actor_evidence
            and candidacy_matches
            and presidential_anchors
            and not SPECULATIVE_CANDIDACY_PATTERN.search(passage)
            and (
                asserted_candidate_subject
                or headline_candidate_reference
                or SUMMARY_ELECTORAL_CAMPAIGN_PATTERN.search(passage)
                or party_leader_candidacy
                or withdrawal
            )
        ):
            passage_evidence.update(candidacy_matches)
            passage_evidence.update(presidential_anchors)

        if (
            presidential_anchors
            and headline_election_integrity
        ):
            passage_evidence.update(presidential_anchors)
            passage_evidence.add("election_integrity")

        if actor_evidence and passage_integrity and presidential_anchors:
            passage_evidence.update(presidential_anchors)
            passage_evidence.add("election_integrity")

        if actor_evidence and elysee_outcome:
            passage_evidence.add("elysee_2027_outcome")

        if (
            actor_evidence
            and ELECTED_PRESIDENT_POSITIONING_PATTERN.search(passage)
            and PROGRAMMATIC_POSITIONING_PATTERN.search(passage)
        ):
            passage_evidence.update({
                "elected_president_positioning",
                *presidential_anchors,
            })

        generic_campaign_matches = sorted(
            set(passage_campaign_matches)
            & {"campagne", "meeting", "rassemblement"}
        )
        if actor_evidence and presidential_anchors:
            locally_electoral_campaign = [
                term
                for term in generic_campaign_matches
                if term != "campagne"
                or SUMMARY_ELECTORAL_CAMPAIGN_PATTERN.search(passage)
            ]
            passage_evidence.update(locally_electoral_campaign)
            if locally_electoral_campaign:
                passage_evidence.update(presidential_anchors)

        if actor_evidence and withdrawal and presidential_anchors:
            passage_evidence.update(
                term
                for term in passage_campaign_matches
                if term in {
                    "candidature",
                    "investiture",
                    "primaire",
                    "renonce",
                    "retrait",
                    "retire",
                    "se retire",
                }
            )
            passage_evidence.add("campaign_withdrawal")

        if passage_evidence:
            qualifying_evidence.update(actor_evidence)
            qualifying_evidence.update(passage_evidence)

    return sorted(qualifying_evidence)


def headline_campaign_context_evidence(
    headline: str,
    headline_party_matches: list[str],
    candidate_in_headline: bool = False,
) -> list[str]:
    """Return high-specificity France 2027 evidence from a headline."""

    campaign_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_CAMPAIGN_TERMS,
    )
    evidence: set[str] = set()

    if RACE_YEAR_CAMPAIGN_PATTERN.search(headline):
        race_year_terms = set(campaign_matches)
        polling_relationship = bool(
            race_year_terms & {"sondage", "sondages", "intentions de vote"}
        )
        presidential_relationship = bool(
            current_presidential_matches(headline)
            or PRESIDENTIAL_CANDIDACY_PATTERN.search(headline)
            or ELECTION_INTEGRITY_HEADLINE_PATTERN.search(headline)
        )
        actor_relationship = bool(
            candidate_in_headline or headline_party_matches
        )
        if (
            polling_relationship
            or presidential_relationship
            or (actor_relationship and race_year_terms)
        ):
            evidence.update(campaign_matches)
            evidence.add("race_year_relationship")

    if PRESIDENTIAL_CANDIDACY_PATTERN.search(headline):
        evidence.update(
            term
            for term in campaign_matches
            if term in {"candidat", "candidate", "candidature"}
        )
        evidence.add("presidential_candidacy")

    if PRESIDENTIAL_PROGRAMME_PATTERN.search(headline):
        evidence.add("presidential_programme")

    elected_positioning = ELECTED_PRESIDENT_POSITIONING_PATTERN.search(
        headline
    )
    if elected_positioning and (
        DIRECT_PRESIDENTIAL_OFFICE_POSITIONING_PATTERN.search(headline)
        or PROGRAMMATIC_POSITIONING_PATTERN.search(headline)
    ):
        evidence.add("elected_president_positioning")

    if ELYSEE_2027_OUTCOME_PATTERN.search(headline):
        evidence.add("elysee_2027_outcome")

    if PRE_PRESIDENTIAL_ACTIVITY_PATTERN.search(headline):
        evidence.add("pre_presidential_activity")

    if (
        candidate_in_headline
        and EXPLICIT_CAMPAIGN_ACTIVITY_PATTERN.search(headline)
    ):
        evidence.add("explicit_campaign_activity")

    if (
        candidate_in_headline
        and IMPLICIT_2027_POSITIONING_PATTERN.search(headline)
    ):
        evidence.add("implicit_2027_positioning")

    if CAMPAIGN_POLLING_RELATIONSHIP_PATTERN.search(headline):
        evidence.add("campaign_polling_relationship")

    if CANDIDACY_RACE_CONSEQUENCE_PATTERN.search(headline):
        evidence.add("candidacy_race_consequence")

    integrity_evidence = election_integrity_race_evidence(headline)
    evidence.update(integrity_evidence)
    if (
        candidate_in_headline
        and ELECTION_INTEGRITY_HEADLINE_PATTERN.search(headline)
        and re.search(r"\b2027\b", headline)
    ):
        evidence.update({"election_integrity", "race_year_relationship"})

    if RACE_QUALIFIED_LEGAL_ELIGIBILITY_PATTERN.search(headline):
        evidence.add("legal_eligibility_consequence")

    selection_matches = sorted(
        set(campaign_matches)
        & {"primaire", "investiture", "designation", "vote des adherents"}
    )
    if (
        selection_matches
        and headline_party_matches
        and not PARTY_LEADERSHIP_ELECTION_PATTERN.search(headline)
    ):
        evidence.update(selection_matches)

    return sorted(evidence)


def election_integrity_race_evidence(
    normalized_text: str,
) -> list[str]:
    """Return bounded French presidential-election integrity evidence."""

    text = normalize(normalized_text)
    if not (
        ELECTION_INTEGRITY_HEADLINE_PATTERN.search(text)
        or SUMMARY_ELECTION_INTEGRITY_PATTERN.search(text)
        or FRENCH_ELECTION_INTEGRITY_PATTERN.search(text)
    ):
        return []

    presidential_matches = current_presidential_matches(text)
    has_race_year_relationship = bool(
        re.search(r"\b2027\b", text)
        and re.search(
            r"\b(?:candidat|candidate|candidats|candidates|"
            r"election|scrutin|campagne)\b",
            text,
        )
    )
    has_french_election_relationship = bool(
        FRENCH_ELECTION_INTEGRITY_PATTERN.search(text)
    )
    if not (
        presidential_matches
        or has_race_year_relationship
        or has_french_election_relationship
    ):
        return []

    evidence = {"election_integrity"}
    evidence.update(presidential_matches)
    if has_race_year_relationship:
        evidence.add("race_year_relationship")
    if has_french_election_relationship:
        evidence.add("french_election_relationship")
    return sorted(evidence)


def bounded_current_french_race_context(
    headline_value: Any,
    summary_value: Any,
) -> bool:
    """Return a bounded local anchor for the current French race."""

    normalized_headline = normalize(headline_value)
    combined = normalize(
        " ".join(
            part
            for part in (
                str(headline_value or ""),
                str(summary_value or ""),
            )
            if part
        )
    )
    return bool(
        EXPLICIT_FRENCH_RACE_HEADLINE_PATTERN.search(normalized_headline)
        or PRESIDENTIAL_CANDIDACY_PATTERN.search(normalized_headline)
        or RACE_YEAR_CAMPAIGN_PATTERN.search(normalized_headline)
        or CURRENT_PRESIDENTIAL_TIMING_PATTERN.search(combined)
        or (
            ELECTION_INTEGRITY_HEADLINE_PATTERN.search(normalized_headline)
            and current_presidential_matches(combined)
        )
        or (
            PRESIDENTIAL_CAMPAIGN_FINANCE_PATTERN.search(combined)
            and current_presidential_matches(normalized_headline)
        )
        or (
            FRENCH_RACE_INSTITUTION_PATTERN.search(normalized_headline)
            and (
                current_presidential_matches(normalized_headline)
                or election_integrity_race_evidence(combined)
            )
        )
        or (
            election_integrity_race_evidence(combined)
            and (
                re.search(r"\b2027\b", combined)
                or CURRENT_PRESIDENTIAL_TIMING_PATTERN.search(combined)
            )
        )
    )


def legal_race_qualification_evidence(
    headline: str,
    combined_text: str,
) -> list[str]:
    """Return independent race evidence for a headline legal event."""

    normalized_headline = normalize(headline)
    normalized_combined = normalize(combined_text)
    evidence: set[str] = set()

    if RACE_QUALIFIED_LEGAL_ELIGIBILITY_PATTERN.search(
        normalized_combined
    ):
        evidence.add("legal_eligibility_consequence")
    if PRESIDENTIAL_CAMPAIGN_FINANCE_PATTERN.search(normalized_combined):
        evidence.add("presidential_campaign_finance")

    headline_presidential = current_presidential_matches(
        normalized_headline
    )
    if not LEGAL_TEMPORAL_PRESIDENTIAL_FRAME_PATTERN.search(
        normalized_headline
    ):
        evidence.update(headline_presidential)

    integrity_evidence = election_integrity_race_evidence(
        normalized_combined
    )
    if integrity_evidence:
        evidence.update(integrity_evidence)

    if SUMMARY_ELECTORAL_CAMPAIGN_PATTERN.search(normalized_combined):
        evidence.add("presidential_campaign_relationship")

    return sorted(evidence)


def classify_relevant_news(
    headline_value: Any,
    summary_value: Any,
    matched_candidates: list[str],
    candidate_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Classify broad but genuine France 2027 article relevance.

    The headline establishes the article subject. A summary may confirm
    presidential context, but it cannot convert routine government,
    ordinary legislation, lifestyle coverage, or a historical election
    into current-race news.
    """
    headline = normalize(headline_value)
    summary = normalize(summary_value)
    bounded_french_race_context = bounded_current_french_race_context(
        headline_value,
        summary_value,
    )
    # Generic presidential language is not sufficient: the article must
    # also contain a deterministic French-race anchor. A current-timing
    # election-integrity relationship is itself such an anchor; foreign
    # election subjects are still rejected below.
    if (
        unanchored_presidential_context(
            headline_value,
            summary_value,
            matched_candidates,
        )
        and not bounded_french_race_context
    ):
        return None
    if (
        HISTORICAL_RETROSPECTIVE_HEADLINE_PATTERN.search(headline)
        and "2027" not in headline
    ):
        return None
    if (
        FOREIGN_ELECTION_SUBJECT_PATTERN.search(headline)
        and not EXPLICIT_FRENCH_RACE_HEADLINE_PATTERN.search(headline)
    ):
        return None
    headline_historical_years = {
        match.group(1)
        for match in HISTORICAL_PRESIDENTIAL_YEAR_PATTERN.finditer(
            headline
        )
    }
    if headline_historical_years and "2027" not in headline_historical_years:
        return None
    if (
        HISTORICAL_RETROSPECTIVE_SUBJECT_PATTERN.search(summary)
        and not current_presidential_matches(headline)
    ):
        return None
    if candidate_matches is None:
        candidate_matches = match_news_candidates(
            headline,
            summary,
            matched_candidates,
        )

    if (
        ORDINARY_LEGAL_HEADLINE_PATTERN.search(headline)
        and LEGAL_TEMPORAL_PRESIDENTIAL_FRAME_PATTERN.search(headline)
        and not RACE_QUALIFIED_LEGAL_ELIGIBILITY_PATTERN.search(headline)
        and not ELECTION_INTEGRITY_HEADLINE_PATTERN.search(headline)
        and not PRESIDENTIAL_CAMPAIGN_FINANCE_PATTERN.search(headline)
        and not SUMMARY_ELECTORAL_CAMPAIGN_PATTERN.search(summary)
    ):
        return None

    candidate_in_headline = candidate_has_match_location(
        candidate_matches,
        "headline",
    )
    headline_party_matches = campaign_agenda_term_matches(
        headline,
        PARTY_CONTEXT_TERMS,
    )
    combined_party_matches = campaign_agenda_term_matches(
        " ".join(part for part in (headline, summary) if part),
        PARTY_CONTEXT_TERMS,
    )
    headline_campaign_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_CAMPAIGN_TERMS,
    )
    headline_campaign_evidence = headline_campaign_context_evidence(
        headline,
        headline_party_matches,
        candidate_in_headline,
    )
    summary_campaign_matches = campaign_agenda_term_matches(
        summary,
        tuple(dict.fromkeys((
            *RELEVANT_CAMPAIGN_TERMS,
            *SUMMARY_CAMPAIGN_EXTRA_TERMS,
        ))),
    )
    combined_campaign_matches = sorted(set([
        *headline_campaign_matches,
        *summary_campaign_matches,
    ]))
    headline_electoral_support = classify_structured_electoral_support(
        headline,
        matched_candidates,
    )
    headline_support_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_HEADLINE_SUPPORT_TERMS,
    )
    headline_election_integrity = bool(
        ELECTION_INTEGRITY_HEADLINE_PATTERN.search(headline)
    )
    headline_presidential_matches = current_presidential_matches(headline)
    summary_presidential_matches = current_presidential_matches(summary)
    summary_collective_candidate_relationship = bool(
        len(matched_candidates) >= 2
        and COLLECTIVE_PRESIDENTIAL_CANDIDATE_PATTERN.search(summary)
        and not SPECULATIVE_CANDIDACY_PATTERN.search(summary)
    )
    other_election_matches = campaign_agenda_term_matches(
        headline,
        NON_PRESIDENTIAL_ELECTION_TERMS,
    )
    routine_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_ROUTINE_EXCLUSION_TERMS,
    )
    if re.search(r"\b(?:ex|ancien)\s+premier\s+ministre\b", headline):
        routine_matches = [
            term
            for term in routine_matches
            if term not in {"ministre", "premier ministre"}
        ]
    lifestyle_matches = campaign_agenda_term_matches(
        headline,
        RELEVANT_LIFESTYLE_EXCLUSION_TERMS,
    )
    if re.search(r"\bcahiers?\s+de\s+vacances\b", headline):
        lifestyle_matches = [
            term for term in lifestyle_matches if term != "vacances"
        ]
    if re.search(r"\bmode\s+operatoire\b", headline):
        lifestyle_matches = [
            term for term in lifestyle_matches if term != "mode"
        ]
    if candidate_in_headline and PRESIDENTIAL_FIELD_PATTERN.search(headline):
        lifestyle_matches = []

    # Headline subject exclusions are authoritative. A summary cannot
    # rescue lifestyle coverage or another type of election.
    if lifestyle_matches and not (
        headline_presidential_matches
        and re.search(r"\b2027\b", headline)
    ):
        return None
    if other_election_matches and not headline_presidential_matches:
        return None

    # An ordinary support destination cannot be rescued by ambiguous campaign
    # vocabulary or by presidential context appearing later in the headline.
    # Independent concrete campaign terms remain available to the normal
    # relevance branches below.
    ambiguous_support_context_terms = {
        "alliance",
        "campagne",
        "candidat",
        "candidate",
        "coalition",
    }
    if (
        headline_electoral_support["has_support_language"]
        and not headline_electoral_support["matched_terms"]
        and set(combined_campaign_matches).issubset(
            ambiguous_support_context_terms
        )
    ):
        return None

    # A current presidential frame in the headline is sufficient, even
    # for analysis or commentary. Historical 2002/2007/2012 retrospectives
    # fail current_presidential_matches().
    if headline_presidential_matches:
        presidential_evidence = set(headline_presidential_matches)
        if election_integrity_race_evidence(headline):
            presidential_evidence.add("election_integrity")
        return {
            "reason": "presidential_context",
            "matched_terms": sorted(presidential_evidence),
        }

    bounded_summary_evidence = summary_campaign_context_evidence(
        summary_value,
        headline_party_matches,
        matched_candidates,
        candidate_matches,
        headline_election_integrity,
        bool(headline_support_matches),
    )
    if not bounded_summary_evidence and summary_presidential_matches:
        headline_support_set = set(headline_support_matches)
        bounded_party_selection = bool(
            SUMMARY_CANDIDATE_SELECTION_PATTERN.search(summary)
            and "primaire" in summary_campaign_matches
            and (
                headline_party_matches
                or {"parti", "calendrier"}.issubset(
                    headline_support_set
                )
            )
        )
        bounded_race_year_actor = bool(
            candidate_in_headline
            and "2027" in headline_support_set
        )
        if bounded_party_selection or bounded_race_year_actor:
            bounded_summary_evidence = sorted(set([
                *summary_presidential_matches,
                *headline_party_matches,
                *(
                    ["candidate_selection", "primaire"]
                    if bounded_party_selection
                    else ["race_year_relationship"]
                ),
            ]))

    # Routine government and ordinary legislative headlines remain out
    # unless the headline itself explicitly frames them around the race.
    if (
        routine_matches
        and not headline_campaign_evidence
        and not headline_election_integrity
    ):
        return None

    if (
        ORDINARY_LEGAL_HEADLINE_PATTERN.search(headline)
        and not RACE_QUALIFIED_LEGAL_ELIGIBILITY_PATTERN.search(headline)
        and not headline_election_integrity
        and not PRESIDENTIAL_CAMPAIGN_FINANCE_PATTERN.search(headline)
        and not SUMMARY_ELECTORAL_CAMPAIGN_PATTERN.search(summary)
        and not headline_campaign_evidence
    ):
        return None

    # Structured electoral support is sufficient campaign evidence. A
    # candidate name elsewhere in the headline cannot convert an ordinary
    # support destination into an endorsement.
    headline_race_relationship = bool(
        headline_presidential_matches
        or headline_campaign_evidence
    )
    if (
        headline_electoral_support["matched_terms"]
        and headline_race_relationship
    ):
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": sorted(
                set([
                    *headline_electoral_support["matched_terms"],
                    *combined_party_matches,
                ])
            ),
        }

    # A race term explicitly bound to 2027 is independent electoral
    # evidence; the year alone remains insufficient. This covers polling,
    # candidacy and campaign relationships whose headline need not repeat
    # the word "presidential". Structured endorsements above keep their
    # more specific evidence provenance.
    if "race_year_relationship" in headline_campaign_evidence:
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": headline_campaign_evidence,
        }

    # Candidacy for the Élysée or the presidency of the Republic is already
    # office-specific. It does not depend on a monitored-name match.
    if "presidential_candidacy" in headline_campaign_evidence:
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": headline_campaign_evidence,
        }

    # Counterfactual policy explicitly tied to taking presidential office is
    # electoral positioning, unlike an ordinary policy statement by the same
    # monitored politician.
    if candidate_in_headline and headline_campaign_evidence:
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": sorted(set([
                *headline_campaign_evidence,
                "candidate_in_headline",
            ])),
        }

    if (
        headline_election_integrity
        and "election_integrity" in headline_campaign_evidence
    ):
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": headline_campaign_evidence,
        }

    # Campaign evidence in the headline remains sufficient when the article
    # subject is a monitored candidate or named political formation. Evidence
    # provenance stays confined to that headline.
    if headline_campaign_evidence and headline_party_matches:
        actor_evidence = list(headline_party_matches)
        return {
            "reason": "campaign_or_selection_context",
            "matched_terms": sorted(set([
                *headline_campaign_evidence,
                *actor_evidence,
            ])),
        }

    # Summary-only vocabulary must form qualifying evidence inside one raw,
    # bounded passage. An attempted but unqualified campaign interpretation
    # cannot fall through and relabel the same article as candidate coverage.
    if (summary_campaign_matches or summary_presidential_matches) and (
        candidate_in_headline
        or headline_party_matches
        or headline_support_matches
        or headline_election_integrity
        or headline_electoral_support["matched_terms"]
        or summary_collective_candidate_relationship
    ):
        summary_evidence = bounded_summary_evidence
        if not summary_evidence:
            return None
        return {
            "reason": (
                "summary_confirmed_presidential_context"
                if summary_presidential_matches
                else "campaign_or_selection_context"
            ),
            "matched_terms": summary_evidence,
        }

    # Candidate identity establishes linkage, not France 2027 relevance.
    # Profiles, interviews, commentary, office activity, policy positions,
    # and legal coverage therefore fall through unless an independent branch
    # above found deterministic presidential-race evidence.
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
    *,
    explicit_election: bool = False,
    matched_candidates: list[str] | None = None,
) -> dict[str, Any] | None:
    """Classify a supported campaign theme or return no topic.

    Topic Coverage is not a second copy of Relevant News. Articles without
    evidence for one of the reviewed themes remain in Relevant News but are
    omitted from the thematic agenda.
    """

    headline = normalize(normalized_headline)
    electoral_support = classify_structured_electoral_support(
        headline,
        matched_candidates,
    )
    scored_topics: list[
        tuple[int, int, dict[str, Any], list[str]]
    ] = []

    for position, topic in enumerate(
        CAMPAIGN_AGENDA_TOPICS
    ):
        matches = campaign_agenda_term_matches(
            headline,
            topic["terms"],
        )
        if topic["id"] == "candidacies_endorsements":
            matches = sorted(set([
                *matches,
                *electoral_support["matched_terms"],
            ]))

        if not explicit_election:
            matches = [
                term
                for term in matches
                if term
                not in CAMPAIGN_AGENDA_CONTEXT_REQUIRED_TERMS
            ]

        if matches:
            scored_topics.append(
                (
                    len(matches),
                    -position,
                    topic,
                    matches,
                )
            )

    if not scored_topics:
        return None

    _score, _position, topic, matches = max(
        scored_topics,
        key=lambda item: (
            item[0],
            item[1],
        ),
    )

    return {
        "id": topic["id"],
        "label": topic["label"],
        "matched_terms": matches,
    }




def classify_policy_agenda(
    headline: str,
    summary: str = "",
) -> list[dict[str, Any]]:
    """Return zero or more deterministic substantive policy labels.

    Policy Agenda is intentionally multi-label. A single accepted
    presidential-coverage record may legitimately concern several policy
    domains. The classifier therefore returns every supported root issue
    rather than forcing a mutually exclusive winner.
    """

    normalized_text = normalize(
        f"{headline or ''} {summary or ''}"
    )

    classifications: list[dict[str, Any]] = []

    for topic in POLICY_AGENDA_TOPICS:
        matched_terms = sorted(
            set(
                campaign_agenda_term_matches(
                    normalized_text,
                    topic["terms"],
                )
            )
        )

        # Retained RSS summaries occasionally append publisher names.
        # Publisher branding must never become substantive policy evidence.
        for boilerplate in POLICY_AGENDA_SUMMARY_BOILERPLATE_TERMS:
            if boilerplate in normalized_text:
                if (
                    boilerplate == "france 3 regions"
                    and "regions" in matched_terms
                ):
                    matched_terms.remove("regions")

                if (
                    boilerplate == "public senat"
                    and "senat" in matched_terms
                ):
                    matched_terms.remove("senat")

        # "Universités d'été" are political gatherings, not university
        # or education-policy coverage.
        if any(
            context in normalized_text
            for context in POLICY_AGENDA_POLITICAL_UNIVERSITY_CONTEXT
        ):
            matched_terms = [
                term
                for term in matched_terms
                if term not in {
                    "universite",
                    "universites",
                }
            ]

        # A politician's or foreign leader's personal health is not
        # healthcare-policy evidence.
        if topic["id"] == "health_education_public_services":
            if (
                "sante" in matched_terms
                and any(
                    context in normalized_text
                    for context in POLICY_AGENDA_HEALTH_PERSONAL_CONTEXT
                )
                and not any(
                    policy_term in normalized_text
                    for policy_term in (
                        "hopital",
                        "hopitaux",
                        "medecin",
                        "medecins",
                        "soins",
                        "deserts medicaux",
                        "ehpad",
                    )
                )
            ):
                matched_terms.remove("sante")

        # Generic health/education vocabulary only counts when the
        # surrounding text actually establishes a policy question.
        #
        # Examples intentionally excluded:
        # - fake news about a candidate's personal health
        # - "l'école, rempart de la démocratie"
        #
        # Specific service/system vocabulary remains directly classifiable.
        if topic["id"] == "health_education_public_services":
            if (
                "sante" in matched_terms
                and not any(
                    context in normalized_text
                    for context in POLICY_AGENDA_HEALTH_POLICY_CONTEXT
                )
            ):
                matched_terms.remove("sante")

            generic_education_terms = {
                "ecole",
                "education",
            }

            if (
                generic_education_terms.intersection(
                    matched_terms
                )
                and not any(
                    context in normalized_text
                    for context in POLICY_AGENDA_EDUCATION_POLICY_CONTEXT
                )
            ):
                matched_terms = [
                    term
                    for term in matched_terms
                    if term
                    not in generic_education_terms
                ]

        # sécurité civile / wildfire prevention belongs outside the
        # crime-police-justice root unless independent security evidence exists.
        if topic["id"] == "security_justice":
            if (
                "securite" in matched_terms
                and any(
                    context in normalized_text
                    for context in POLICY_AGENDA_SECURITY_CIVIL_CONTEXT
                )
                and not any(
                    policy_term in normalized_text
                    for policy_term in (
                        "police",
                        "gendarmerie",
                        "delinquance",
                        "criminalite",
                        "prison",
                        "prisons",
                        "terrorisme",
                        "narcotrafic",
                        "trafic de drogue",
                    )
                )
            ):
                matched_terms.remove("securite")

        if not matched_terms:
            continue

        matched_subtopics: list[str] = []

        for subtopic_id, terms in topic[
            "subtopics"
        ].items():
            if set(
                matched_terms
            ).intersection(
                terms
            ):
                matched_subtopics.append(
                    subtopic_id
                )

        classifications.append(
            {
                "id": topic["id"],
                "label": topic["label"],
                "matched_terms": matched_terms,
                "subtopics": sorted(
                    matched_subtopics
                ),
            }
        )

    return classifications

def classify_notable_development(
    normalized_text: str,
    matched_candidates: list[str],
    source: dict[str, Any],
    normalized_headline: str | None = None,
    candidate_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return only concrete developments tied to the presidential race.

    The full RSS text may provide context, but a politics-section source is not
    itself evidence that an ordinary law, ministerial decision, appointment,
    or another election is a presidential-race development.
    """

    del source  # source scope is metadata, not a substitute for race context

    headline_text = normalized_headline or normalized_text
    if candidate_matches is None:
        candidate_matches = match_news_candidates(
            headline_text,
            "",
            matched_candidates,
        )
    electoral_support = classify_structured_electoral_support(
        headline_text,
        matched_candidates,
    )
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
        if topic["id"] == "candidacies_endorsements":
            strict_matches = sorted(set([
                *strict_matches,
                *electoral_support["matched_terms"],
            ]))
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
    has_election_context = (
        bool(electoral_support["matched_terms"])
        or any(
            term in normalized_text
            for term in ELECTION_CONTEXT_TERMS
        )
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
    has_candidate_in_headline = candidate_has_match_location(
        candidate_matches,
        "headline",
    )

    result = {
        "id": topic_id,
        "label": topic["label"],
        "matched_terms": strict_matches,
    }

    if topic_id == "legal_eligibility":
        # A legal action involving a monitored figure is not presidential
        # news by itself. The text must independently establish an eligibility,
        # campaign-finance, election-integrity, or other race consequence.
        legal_race_evidence = legal_race_qualification_evidence(
            headline_text,
            normalized_text,
        )
        if not has_candidate_in_headline or not legal_race_evidence:
            return None
        result["matched_terms"] = sorted(set([
            *strict_matches,
            *legal_race_evidence,
        ]))
        return result

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


def campaign_agenda_support_sort_key(
    item: dict[str, Any],
) -> tuple[float, str, str, str]:
    """Sort topic evidence by recency with stable tie-breakers."""

    published = parse_feed_datetime(item.get("published_at"))
    timestamp = (
        published.timestamp()
        if published is not None
        else float("-inf")
    )

    return (
        -timestamp,
        str(item.get("publisher") or "").casefold(),
        str(item.get("headline") or "").casefold(),
        str(item.get("id") or ""),
    )


def campaign_agenda_evolution_anchor(
    relevant_news: list[dict[str, Any]],
    generated_at: datetime | None,
) -> datetime:
    """Return a deterministic UTC anchor for Agenda evolution."""

    if generated_at is not None:
        if (
            generated_at.tzinfo is None
            or generated_at.utcoffset() is None
        ):
            raise ValueError(
                "campaign agenda generated_at must be timezone-aware"
            )

        return generated_at.astimezone(timezone.utc)

    published = [
        parsed
        for item in relevant_news
        if (
            parsed := parse_feed_datetime(
                item.get("published_at")
            )
        )
        is not None
    ]

    if published:
        return max(published).astimezone(timezone.utc)

    # Deterministic fallback for empty synthetic/test inputs.
    return datetime(
        1970,
        1,
        CAMPAIGN_AGENDA_EVOLUTION_DAYS,
        tzinfo=timezone.utc,
    )


def build_campaign_agenda_evolution(
    topic_items: dict[str, list[dict[str, Any]]],
    topic_labels: dict[str, str],
    generated_at: datetime,
) -> dict[str, Any]:
    """Build the calendar-day analytical projection for Agenda."""

    anchor = generated_at.astimezone(timezone.utc)
    period_end = anchor.date()
    period_start = period_end - timedelta(
        days=CAMPAIGN_AGENDA_EVOLUTION_DAYS - 1
    )

    calendar_days = [
        period_start + timedelta(days=offset)
        for offset in range(
            CAMPAIGN_AGENDA_EVOLUTION_DAYS
        )
    ]

    latest_end = period_end - timedelta(days=1)
    latest_start = latest_end - timedelta(
        days=CAMPAIGN_AGENDA_COMPARISON_DAYS - 1
    )
    previous_end = latest_start - timedelta(days=1)
    previous_start = previous_end - timedelta(
        days=CAMPAIGN_AGENDA_COMPARISON_DAYS - 1
    )

    evolution_topics: list[dict[str, Any]] = []

    for topic_id, items in topic_items.items():
        period_items = [
            item
            for item in items
            if (
                period_start.isoformat()
                <= item["published_at"][:10]
                <= period_end.isoformat()
            )
        ]

        items_by_date: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for item in period_items:
            day = item["published_at"][:10]
            items_by_date.setdefault(day, []).append(
                item
            )

        daily_activity: list[dict[str, Any]] = []

        for current_date in calendar_days:
            date_key = current_date.isoformat()
            day_items = items_by_date.get(
                date_key,
                [],
            )

            day_publishers = {
                item["publisher"]
                for item in day_items
            }

            daily_activity.append(
                {
                    "date": date_key,
                    "item_count": len(day_items),
                    "source_day_count": len(
                        day_publishers
                    ),
                }
            )

        publishers = {
            item["publisher"]
            for item in period_items
        }

        matched_term_counts: dict[str, int] = {}

        for item in period_items:
            # One accepted record contributes at most once
            # to any individual matched term.
            for term in sorted(
                set(item.get("matched_terms", []))
            ):
                matched_term_counts[term] = (
                    matched_term_counts.get(
                        term,
                        0,
                    )
                    + 1
                )

        matched_terms = [
            {
                "term": term,
                "item_count": count,
            }
            for term, count in sorted(
                matched_term_counts.items(),
                key=lambda pair: (
                    -pair[1],
                    pair[0],
                ),
            )
        ]

        source_day_count = sum(
            day["source_day_count"]
            for day in daily_activity
        )

        active_day_count = sum(
            day["item_count"] > 0
            for day in daily_activity
        )

        evolution_topics.append(
            {
                "id": topic_id,
                "label": topic_labels[
                    topic_id
                ],
                "item_count": len(period_items),
                "publisher_count": len(
                    publishers
                ),
                "source_day_count": (
                    source_day_count
                ),
                "active_day_count": (
                    active_day_count
                ),
                "display_eligible": (
                    source_day_count
                    >= CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
                ),
                "daily_activity": (
                    daily_activity
                ),
                "matched_term_counts": (
                    matched_terms
                ),
            }
        )

    evolution_topics.sort(
        key=lambda topic: (
            -topic["display_eligible"],
            -topic["source_day_count"],
            -topic["item_count"],
            topic["label"],
        )
    )

    return {
        "period_days": (
            CAMPAIGN_AGENDA_EVOLUTION_DAYS
        ),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_end_partial": True,
        "comparison_days": (
            CAMPAIGN_AGENDA_COMPARISON_DAYS
        ),
        "latest_start": latest_start.isoformat(),
        "latest_end": latest_end.isoformat(),
        "previous_start": (
            previous_start.isoformat()
        ),
        "previous_end": previous_end.isoformat(),
        "topics": evolution_topics,
    }


def build_campaign_agenda(
    relevant_news: list[dict[str, Any]],
    window_days: int,
    notable_developments: (
        list[dict[str, Any]] | None
    ) = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    topic_items: dict[
        str,
        list[dict[str, Any]],
    ] = {}
    topic_labels: dict[str, str] = {}

    notable_by_id = {
        str(item.get("id") or ""): item
        for item in (
            notable_developments or []
        )
        if str(item.get("id") or "")
    }

    unclassified_item_count = 0

    for item in relevant_news:
        item_id = str(item.get("id") or "")
        development = (
            item
            if item.get("development_category")
            else notable_by_id.get(item_id)
        )

        if (
            isinstance(development, dict)
            and development.get(
                "development_category"
            )
        ):
            classification = {
                "id": development[
                    "development_category"
                ],
                "label": (
                    development.get(
                        "development_label"
                    )
                    or development[
                        "development_category"
                    ]
                ),
                "matched_terms": list(
                    development.get(
                        "matched_terms",
                        [],
                    )
                ),
            }
        else:
            classification = classify_campaign_agenda(
                normalize(item["headline"]),
                explicit_election=bool(
                    item.get("explicit_election")
                ),
                matched_candidates=item.get("candidates", []),
            )

        if classification is None:
            unclassified_item_count += 1
            continue

        topic_id = classification["id"]
        topic_labels[topic_id] = (
            classification["label"]
        )

        topic_items.setdefault(
            topic_id,
            [],
        ).append(
            {
                "id": item["id"],
                "publisher": item["publisher"],
                "published_at": item[
                    "published_at"
                ],
                "headline": item["headline"],
                "url": item["url"],
                "candidates": item["candidates"],
                "matched_terms": (
                    classification[
                        "matched_terms"
                    ]
                ),
            }
        )

    evolution_anchor = (
        campaign_agenda_evolution_anchor(
            relevant_news,
            generated_at,
        )
    )

    topics: list[dict[str, Any]] = []

    for topic_id, items in topic_items.items():
        items.sort(
            key=campaign_agenda_support_sort_key
        )

        publishers = sorted(
            {
                item["publisher"]
                for item in items
            }
        )
        active_days = sorted(
            {
                item["published_at"][:10]
                for item in items
            }
        )
        source_days = {
            (
                item["publisher"],
                item["published_at"][:10],
            )
            for item in items
        }
        supporting_items = items[
            :CAMPAIGN_AGENDA_SUPPORT_LIMIT
        ]

        topics.append(
            {
                "id": topic_id,
                "label": topic_labels[
                    topic_id
                ],
                "item_count": len(items),
                "publisher_count": len(
                    publishers
                ),
                "publisher_names": publishers,
                "source_day_count": len(
                    source_days
                ),
                "active_day_count": len(
                    active_days
                ),
                "display_eligible": (
                    len(source_days)
                    >= CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
                ),
                "supporting_item_count": len(
                    supporting_items
                ),
                "omitted_item_count": (
                    len(items)
                    - len(supporting_items)
                ),
                "supporting_items": (
                    supporting_items
                ),
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

    classified_item_count = sum(
        topic["item_count"]
        for topic in topics
    )

    evolution = build_campaign_agenda_evolution(
        topic_items,
        topic_labels,
        evolution_anchor,
    )

    return {
        "window_days": window_days,
        "input_item_count": len(
            relevant_news
        ),
        "classified_item_count": (
            classified_item_count
        ),
        "unclassified_item_count": (
            unclassified_item_count
        ),
        "method": (
            "accepted_relevant_news_by_campaign_theme"
        ),
        "display_min_source_days": (
            CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        ),
        "evolution": evolution,
        "topics": topics,
    }






def build_policy_analysis_input(
    relevant_news: list[dict[str, Any]],
    inventory_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return accepted public news enriched with retained summaries.

    The public relevant_news contract intentionally omits RSS summaries.
    Policy classification nevertheless benefits from substantive context,
    so summaries are reattached only inside the analytical pipeline.
    """

    summaries_by_id = {
        str(entry.get("id") or ""): str(
            entry.get("summary") or ""
        )
        for entry in inventory_entries
        if isinstance(entry, dict)
        and str(entry.get("id") or "")
    }

    enriched: list[dict[str, Any]] = []

    for item in relevant_news:
        analytical_item = dict(item)
        analytical_item["summary"] = (
            summaries_by_id.get(
                str(item.get("id") or ""),
                "",
            )
        )
        enriched.append(analytical_item)

    return enriched

def policy_agenda_evolution_anchor(
    relevant_news: list[dict[str, Any]],
    generated_at: datetime | None,
) -> datetime:
    """Return deterministic UTC anchor for Policy Agenda evolution."""

    if generated_at is not None:
        if (
            generated_at.tzinfo is None
            or generated_at.utcoffset() is None
        ):
            raise ValueError(
                "policy agenda generated_at must be timezone-aware"
            )

        return generated_at.astimezone(
            timezone.utc
        )

    published = [
        parsed
        for item in relevant_news
        if (
            parsed := parse_feed_datetime(
                item.get("published_at")
            )
        )
        is not None
    ]

    if published:
        return max(published).astimezone(
            timezone.utc
        )

    return datetime(
        1970,
        1,
        POLICY_AGENDA_EVOLUTION_DAYS,
        tzinfo=timezone.utc,
    )


def build_policy_agenda_evolution(
    topic_items: dict[str, list[dict[str, Any]]],
    topic_labels: dict[str, str],
    relevant_news: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    """Build 30-day issue recurrence and complete-week incidence."""

    anchor = generated_at.astimezone(
        timezone.utc
    )
    period_end = anchor.date()
    period_start = period_end - timedelta(
        days=POLICY_AGENDA_EVOLUTION_DAYS - 1
    )

    calendar_days = [
        period_start + timedelta(days=offset)
        for offset in range(
            POLICY_AGENDA_EVOLUTION_DAYS
        )
    ]

    latest_end = period_end - timedelta(
        days=1
    )
    latest_start = latest_end - timedelta(
        days=POLICY_AGENDA_COMPARISON_DAYS - 1
    )
    previous_end = latest_start - timedelta(
        days=1
    )
    previous_start = previous_end - timedelta(
        days=POLICY_AGENDA_COMPARISON_DAYS - 1
    )

    accepted_source_days_by_date: dict[
        str,
        set[tuple[str, str]],
    ] = {}

    for item in relevant_news:
        published_at = str(
            item.get("published_at") or ""
        )
        if len(published_at) < 10:
            continue

        date_key = published_at[:10]

        if not (
            period_start.isoformat()
            <= date_key
            <= period_end.isoformat()
        ):
            continue

        publisher = str(
            item.get("publisher") or ""
        )
        if not publisher:
            continue

        accepted_source_days_by_date.setdefault(
            date_key,
            set(),
        ).add(
            (publisher, date_key)
        )

    accepted_daily_activity = []

    for current_date in calendar_days:
        date_key = current_date.isoformat()
        accepted_daily_activity.append(
            {
                "date": date_key,
                "source_day_count": len(
                    accepted_source_days_by_date.get(
                        date_key,
                        set(),
                    )
                ),
            }
        )

    def accepted_source_days_between(
        start_date,
        end_date,
    ) -> set[tuple[str, str]]:
        result: set[tuple[str, str]] = set()

        for date_key, source_days in (
            accepted_source_days_by_date.items()
        ):
            if (
                start_date.isoformat()
                <= date_key
                <= end_date.isoformat()
            ):
                result.update(source_days)

        return result

    latest_denominator = (
        accepted_source_days_between(
            latest_start,
            latest_end,
        )
    )
    previous_denominator = (
        accepted_source_days_between(
            previous_start,
            previous_end,
        )
    )

    evolution_topics: list[
        dict[str, Any]
    ] = []

    for topic_id, items in topic_items.items():
        period_items = [
            item
            for item in items
            if (
                period_start.isoformat()
                <= item["published_at"][:10]
                <= period_end.isoformat()
            )
        ]

        items_by_date: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for item in period_items:
            date_key = item[
                "published_at"
            ][:10]
            items_by_date.setdefault(
                date_key,
                [],
            ).append(item)

        daily_activity = []

        for current_date in calendar_days:
            date_key = current_date.isoformat()
            day_items = items_by_date.get(
                date_key,
                [],
            )

            topic_source_days = {
                (
                    item["publisher"],
                    date_key,
                )
                for item in day_items
            }

            accepted_count = len(
                accepted_source_days_by_date.get(
                    date_key,
                    set(),
                )
            )
            topic_count = len(
                topic_source_days
            )

            daily_activity.append(
                {
                    "date": date_key,
                    "item_count": len(
                        day_items
                    ),
                    "source_day_count": (
                        topic_count
                    ),
                    "accepted_source_day_count": (
                        accepted_count
                    ),
                    "incidence": (
                        round(
                            topic_count
                            / accepted_count,
                            6,
                        )
                        if accepted_count
                        else 0.0
                    ),
                }
            )

        publishers = {
            item["publisher"]
            for item in period_items
        }

        source_days = {
            (
                item["publisher"],
                item["published_at"][:10],
            )
            for item in period_items
        }

        active_days = {
            item["published_at"][:10]
            for item in period_items
        }

        matched_term_counts: dict[
            str,
            int,
        ] = {}

        for item in period_items:
            for term in sorted(
                set(
                    item.get(
                        "matched_terms",
                        [],
                    )
                )
            ):
                matched_term_counts[term] = (
                    matched_term_counts.get(
                        term,
                        0,
                    )
                    + 1
                )

        latest_topic_source_days = {
            (
                item["publisher"],
                item["published_at"][:10],
            )
            for item in period_items
            if (
                latest_start.isoformat()
                <= item["published_at"][:10]
                <= latest_end.isoformat()
            )
        }

        previous_topic_source_days = {
            (
                item["publisher"],
                item["published_at"][:10],
            )
            for item in period_items
            if (
                previous_start.isoformat()
                <= item["published_at"][:10]
                <= previous_end.isoformat()
            )
        }

        latest_incidence = (
            len(latest_topic_source_days)
            / len(latest_denominator)
            if latest_denominator
            else 0.0
        )

        previous_incidence = (
            len(previous_topic_source_days)
            / len(previous_denominator)
            if previous_denominator
            else 0.0
        )

        evolution_topics.append(
            {
                "id": topic_id,
                "label": topic_labels[
                    topic_id
                ],
                "item_count": len(
                    period_items
                ),
                "publisher_count": len(
                    publishers
                ),
                "source_day_count": len(
                    source_days
                ),
                "active_day_count": len(
                    active_days
                ),
                "display_eligible": (
                    len(source_days)
                    >= POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS
                ),
                "latest_source_day_count": len(
                    latest_topic_source_days
                ),
                "previous_source_day_count": len(
                    previous_topic_source_days
                ),
                "latest_incidence": round(
                    latest_incidence,
                    6,
                ),
                "previous_incidence": round(
                    previous_incidence,
                    6,
                ),
                "incidence_change_pp": round(
                    (
                        latest_incidence
                        - previous_incidence
                    )
                    * 100,
                    3,
                ),
                "daily_activity": (
                    daily_activity
                ),
                "matched_term_counts": [
                    {
                        "term": term,
                        "item_count": count,
                    }
                    for term, count in sorted(
                        matched_term_counts.items(),
                        key=lambda pair: (
                            -pair[1],
                            pair[0],
                        ),
                    )
                ],
            }
        )

    evolution_topics.sort(
        key=lambda topic: (
            -topic["display_eligible"],
            -topic["source_day_count"],
            -topic["item_count"],
            topic["label"],
        )
    )

    return {
        "period_days": (
            POLICY_AGENDA_EVOLUTION_DAYS
        ),
        "period_start": (
            period_start.isoformat()
        ),
        "period_end": (
            period_end.isoformat()
        ),
        "period_end_partial": True,
        "comparison_days": (
            POLICY_AGENDA_COMPARISON_DAYS
        ),
        "latest_start": (
            latest_start.isoformat()
        ),
        "latest_end": (
            latest_end.isoformat()
        ),
        "previous_start": (
            previous_start.isoformat()
        ),
        "previous_end": (
            previous_end.isoformat()
        ),
        "accepted_daily_activity": (
            accepted_daily_activity
        ),
        "topics": evolution_topics,
    }


def build_policy_agenda(
    relevant_news: list[dict[str, Any]],
    window_days: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build deterministic multi-label substantive Policy Agenda."""

    topic_items: dict[
        str,
        list[dict[str, Any]],
    ] = {}
    topic_labels: dict[str, str] = {}

    classified_item_ids: set[str] = set()
    label_assignment_count = 0

    for item in relevant_news:
        classifications = (
            classify_policy_agenda(
                str(
                    item.get("headline")
                    or ""
                ),
                str(
                    item.get("summary")
                    or ""
                ),
            )
        )

        if not classifications:
            continue

        item_id = str(
            item.get("id") or ""
        )

        classified_item_ids.add(
            item_id
        )
        label_assignment_count += len(
            classifications
        )

        for classification in classifications:
            topic_id = classification[
                "id"
            ]
            topic_labels[topic_id] = (
                classification["label"]
            )

            topic_items.setdefault(
                topic_id,
                [],
            ).append(
                {
                    "id": item["id"],
                    "publisher": item[
                        "publisher"
                    ],
                    "published_at": item[
                        "published_at"
                    ],
                    "headline": item[
                        "headline"
                    ],
                    "url": item["url"],
                    "candidates": list(
                        item.get(
                            "candidates",
                            [],
                        )
                    ),
                    "matched_terms": list(
                        classification[
                            "matched_terms"
                        ]
                    ),
                    "subtopics": list(
                        classification[
                            "subtopics"
                        ]
                    ),
                }
            )

    topics: list[dict[str, Any]] = []

    for topic_id, items in topic_items.items():
        items.sort(
            key=campaign_agenda_support_sort_key
        )

        publishers = sorted(
            {
                item["publisher"]
                for item in items
            }
        )

        active_days = {
            item["published_at"][:10]
            for item in items
        }

        source_days = {
            (
                item["publisher"],
                item["published_at"][:10],
            )
            for item in items
        }

        subtopic_counts: dict[
            str,
            int,
        ] = {}

        candidate_counts: dict[
            str,
            int,
        ] = {}

        for item in items:
            for subtopic in set(
                item.get(
                    "subtopics",
                    [],
                )
            ):
                subtopic_counts[subtopic] = (
                    subtopic_counts.get(
                        subtopic,
                        0,
                    )
                    + 1
                )

            for candidate in set(
                item.get(
                    "candidates",
                    [],
                )
            ):
                candidate_name = str(
                    candidate
                ).strip()

                if not candidate_name:
                    continue

                candidate_counts[
                    candidate_name
                ] = (
                    candidate_counts.get(
                        candidate_name,
                        0,
                    )
                    + 1
                )

        supporting_items = items[
            :POLICY_AGENDA_SUPPORT_LIMIT
        ]

        topics.append(
            {
                "id": topic_id,
                "label": topic_labels[
                    topic_id
                ],
                "item_count": len(items),
                "publisher_count": len(
                    publishers
                ),
                "publisher_names": (
                    publishers
                ),
                "source_day_count": len(
                    source_days
                ),
                "active_day_count": len(
                    active_days
                ),
                "display_eligible": (
                    len(source_days)
                    >= POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS
                ),
                "subtopic_counts": [
                    {
                        "id": subtopic,
                        "item_count": count,
                    }
                    for subtopic, count in sorted(
                        subtopic_counts.items(),
                        key=lambda pair: (
                            -pair[1],
                            pair[0],
                        ),
                    )
                ],
                "candidate_counts": [
                    {
                        "candidate": candidate,
                        "item_count": count,
                    }
                    for candidate, count in sorted(
                        candidate_counts.items(),
                        key=lambda pair: (
                            -pair[1],
                            pair[0].casefold(),
                        ),
                    )
                ],
                "supporting_item_count": len(
                    supporting_items
                ),
                "omitted_item_count": (
                    len(items)
                    - len(supporting_items)
                ),
                "supporting_items": (
                    supporting_items
                ),
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

    evolution_anchor = (
        policy_agenda_evolution_anchor(
            relevant_news,
            generated_at,
        )
    )

    evolution = (
        build_policy_agenda_evolution(
            topic_items,
            topic_labels,
            relevant_news,
            evolution_anchor,
        )
    )

    input_item_count = len(
        relevant_news
    )
    classified_item_count = len(
        classified_item_ids
    )

    return {
        "window_days": window_days,
        "input_item_count": (
            input_item_count
        ),
        "classified_item_count": (
            classified_item_count
        ),
        "unclassified_item_count": (
            input_item_count
            - classified_item_count
        ),
        "label_assignment_count": (
            label_assignment_count
        ),
        "method": (
            "accepted_relevant_news_by_policy_issue_multilabel"
        ),
        "display_min_source_days": (
            POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        ),
        "evolution": evolution,
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
    candidates: list[str],
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
    schema_version = payload.get("schema_version")
    if schema_version not in {
        LEGACY_INVENTORY_SCHEMA_VERSION,
        INVENTORY_SCHEMA_VERSION,
    }:
        raise RuntimeError("Unsupported news inventory schema")
    if not isinstance(payload.get("items"), list):
        raise RuntimeError("News inventory items must be a list")

    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    migrated_items: list[dict[str, Any]] = []

    for stored_item in payload["items"]:
        expected_fields = (
            LEGACY_INVENTORY_ITEM_FIELDS
            if schema_version == LEGACY_INVENTORY_SCHEMA_VERSION
            else INVENTORY_ITEM_FIELDS
        )
        if (
            not isinstance(stored_item, dict)
            or set(stored_item) != expected_fields
        ):
            raise RuntimeError(
                "News inventory item has unexpected fields"
            )
        item = dict(stored_item)
        if schema_version == LEGACY_INVENTORY_SCHEMA_VERSION:
            candidate_matches = match_news_candidates(
                item.get("headline"),
                item.get("summary"),
                candidates,
            )
            item["candidate_matches"] = candidate_matches
            item["candidate_names"] = candidate_names_from_matches(
                candidate_matches
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
        validate_candidate_match_contract(
            candidate_names,
            item.get("candidate_matches"),
            "News inventory item",
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
        if schema_version == LEGACY_INVENTORY_SCHEMA_VERSION:
            relevance = classify_relevant_news(
                item.get("headline"),
                item.get("summary"),
                candidate_names,
                item["candidate_matches"],
            )
            item["relevance_reason"] = (
                relevance["reason"] if relevance is not None else None
            )
            item["relevance_terms"] = (
                relevance["matched_terms"] if relevance is not None else []
            )
        key = inventory_identity(item)
        if key in seen_keys:
            raise RuntimeError(
                "News inventory contains duplicate article identities"
            )
        seen_ids.add(item["id"])
        seen_keys.add(key)

        migrated_items.append(item)

    if schema_version == INVENTORY_SCHEMA_VERSION:
        return payload

    return {
        **payload,
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "items": migrated_items,
    }


def inventory_item_from_entry(
    entry: dict[str, Any],
    first_seen_at: str,
    last_seen_at: str,
) -> dict[str, Any]:
    canonical = canonical_url(
        entry.get("canonical_url") or entry.get("url")
    )
    identity = inventory_identity(entry)
    candidate_matches = [
        {
            "candidate": match["candidate"],
            "matched_aliases": list(match["matched_aliases"]),
            "locations": list(match["locations"]),
        }
        for match in entry.get("candidate_matches", [])
    ]
    candidate_names = candidate_names_from_matches(candidate_matches)
    validate_candidate_match_contract(
        candidate_names,
        candidate_matches,
        "News inventory entry",
    )

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
        "candidate_names": candidate_names,
        "candidate_matches": candidate_matches,
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
        "candidate_matches": [
            {
                key: list(value) if isinstance(value, list) else value
                for key, value in match.items()
            }
            for match in item["candidate_matches"]
        ],
        "candidate_names": candidate_names_from_matches(item["candidate_matches"]),
        "relevance_reason": item["relevance_reason"],
        "relevance_terms": list(item["relevance_terms"]),
    }


def revalidate_retained_inventory_scope(
    item: dict[str, Any],
) -> dict[str, Any]:
    """Refresh retained relevance while preserving factual provenance."""

    refreshed = dict(item)
    relevance = classify_relevant_news(
        refreshed.get("headline"),
        refreshed.get("summary"),
        refreshed.get("candidate_names"),
        refreshed.get("candidate_matches"),
    )
    refreshed["relevance_reason"] = (
        relevance["reason"] if relevance is not None else None
    )
    refreshed["relevance_terms"] = (
        relevance["matched_terms"] if relevance is not None else []
    )

    return refreshed

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

    for stored_item in existing.get("items", []):
        item = revalidate_retained_inventory_scope(stored_item)
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


def classify_candidate_coverage_scope(
    *,
    is_election_news: bool,
    relevance: dict[str, Any] | None,
    development: dict[str, Any] | None,
) -> str:
    """Explain why a candidate-linked record contributes to visibility.

    ``election`` is reserved for a current presidential-race headline.
    ``campaign`` covers other deterministically established race context or
    concrete campaign developments. ``general`` records political visibility
    without claiming that the article concerns the presidential campaign.
    """

    if is_election_news:
        return "election"
    if relevance is not None or development is not None:
        return "campaign"
    return "general"


def public_item(
    entry: dict[str, Any],
    candidate_matches: list[dict[str, Any]],
    explicit_election: bool,
) -> dict[str, Any]:
    public_candidate_matches = [
        {
            "candidate": match["candidate"],
            "matched_aliases": list(match["matched_aliases"]),
            "locations": list(match["locations"]),
        }
        for match in candidate_matches
    ]
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
        "candidates": candidate_names_from_matches(public_candidate_matches),
        "candidate_matches": public_candidate_matches,
    }


def public_relevant_item(
    entry: dict[str, Any],
    candidate_matches: list[dict[str, Any]],
    explicit_election: bool,
    classification: dict[str, Any],
) -> dict[str, Any]:
    item = public_item(entry, candidate_matches, explicit_election)
    item.update(
        {
            "relevance_reason": classification["reason"],
            "relevance_terms": classification["matched_terms"],
        }
    )
    return item


def public_notable_item(
    entry: dict[str, Any],
    candidate_matches: list[dict[str, Any]],
    classification: dict[str, Any],
) -> dict[str, Any]:
    item = public_item(entry, candidate_matches, False)
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


def round_candidate_visibility_ratio(value: float) -> float:
    return math.floor(value * 1000 + 0.5) / 1000


def candidate_visibility_gate(
    *,
    current_record_count: int,
    prior_record_count: int,
    current_publisher_count: int,
    prior_publisher_count: int,
    common_publisher_count: int,
    publisher_overlap_ratio: float,
    record_count_ratio: float | None,
) -> tuple[str, str]:
    thresholds = CANDIDATE_VISIBILITY_THRESHOLDS
    if (
        current_record_count < thresholds["minimum_period_records"]
        or prior_record_count < thresholds["minimum_period_records"]
        or current_publisher_count
        < thresholds["minimum_period_publishers"]
        or prior_publisher_count
        < thresholds["minimum_period_publishers"]
        or common_publisher_count
        < thresholds["minimum_common_publishers"]
    ):
        return "not_comparable", "insufficient_data"

    if (
        publisher_overlap_ratio
        < thresholds["minimum_publisher_overlap_ratio"]
        or record_count_ratio is None
        or record_count_ratio
        > thresholds["maximum_record_count_ratio"]
    ):
        return "not_comparable", "publisher_panel_changed"

    return "comparable", "comparable"


def candidate_story_tokens(
    headline: Any,
    candidate: str,
) -> frozenset[str]:
    """Return significant normalized terms for conservative clustering."""

    candidate_tokens = set(normalize(candidate).split())
    return frozenset(
        token
        for token in normalize(headline).split()
        if (
            len(token) >= 3
            and not token.isdigit()
            and token not in candidate_tokens
            and token not in STORY_CLUSTER_STOPWORDS
        )
    )


def candidate_story_similarity(
    left: frozenset[str],
    right: frozenset[str],
) -> float:
    """Measure headline overlap without semantic or embedding inference."""

    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    shared_count = len(left & right)
    if shared_count < STORY_CLUSTER_MIN_SHARED_TOKENS:
        return 0.0

    union_count = len(left | right)
    if not union_count:
        return 0.0

    return shared_count / union_count


def build_candidate_story_clusters(
    records: list[dict[str, Any]],
    candidate: str,
) -> list[dict[str, Any]]:
    """Group near-duplicate story frames using deterministic components."""

    if not records:
        return []

    token_sets = [
        candidate_story_tokens(item.get("headline"), candidate)
        for item in records
    ]
    neighbours: list[set[int]] = [
        set()
        for _item in records
    ]

    for left_index in range(len(records)):
        for right_index in range(left_index + 1, len(records)):
            similarity = candidate_story_similarity(
                token_sets[left_index],
                token_sets[right_index],
            )
            if similarity >= STORY_CLUSTER_MIN_JACCARD:
                neighbours[left_index].add(right_index)
                neighbours[right_index].add(left_index)

    components: list[list[int]] = []
    unseen = set(range(len(records)))

    while unseen:
        seed = min(unseen)
        stack = [seed]
        component: list[int] = []
        unseen.remove(seed)

        while stack:
            index = stack.pop()
            component.append(index)
            for neighbour in sorted(neighbours[index], reverse=True):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)

        components.append(sorted(component))

    clusters: list[dict[str, Any]] = []

    for component in components:
        component_records = [
            records[index]
            for index in component
        ]
        ordered_records = sorted(
            component_records,
            key=lambda item: (
                -(
                    parse_feed_datetime(item.get("published_at"))
                    or datetime.min.replace(tzinfo=timezone.utc)
                ).timestamp(),
                clean_text(item.get("headline")).casefold(),
                str(item.get("id") or ""),
            ),
        )

        item_ids = [
            str(item.get("id") or "").strip()
            for item in ordered_records
            if str(item.get("id") or "").strip()
        ]
        publishers = {
            str(item.get("publisher") or "").strip()
            for item in component_records
            if str(item.get("publisher") or "").strip()
        }
        active_dates = {
            published.date().isoformat()
            for item in component_records
            if (
                published := parse_feed_datetime(
                    item.get("published_at")
                )
            ) is not None
        }
        cluster_signature = "|".join(sorted(item_ids))
        cluster_id = hashlib.sha256(
            f"{candidate}|{cluster_signature}".encode("utf-8")
        ).hexdigest()[:12]

        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": clean_text(
                    ordered_records[0].get("headline")
                ),
                "record_count": len(component_records),
                "share": round_candidate_visibility_ratio(
                    len(component_records) / len(records)
                ),
                "publisher_count": len(publishers),
                "active_day_count": len(active_dates),
                "item_ids": item_ids,
            }
        )

    clusters.sort(
        key=lambda cluster: (
            -cluster["record_count"],
            -cluster["publisher_count"],
            -cluster["active_day_count"],
            cluster["label"].casefold(),
            cluster["cluster_id"],
        )
    )
    return clusters


def build_candidate_visibility_metrics(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate candidate visibility without inferring sentiment or support."""

    accumulators: dict[str, dict[str, Any]] = {}

    for item in records:
        published = parse_feed_datetime(item.get("published_at"))
        published_date = (
            published.date().isoformat()
            if published is not None
            else None
        )
        publisher = str(item.get("publisher") or "").strip()

        for match in item.get("candidate_matches", []):
            candidate = str(match.get("candidate") or "").strip()
            if not candidate:
                continue

            coverage_scope = item.get("coverage_scope")
            if coverage_scope not in CANDIDATE_COVERAGE_SCOPES:
                raise RuntimeError(
                    "candidate visibility record has invalid coverage_scope"
                )

            accumulator = accumulators.setdefault(
                candidate,
                {
                    "record_count": 0,
                    "records": [],
                    "publisher_names": set(),
                    "publisher_counts": {},
                    "active_dates": set(),
                    "headline_match_count": 0,
                    "summary_only_match_count": 0,
                    "scope_counts": {
                        scope: 0
                        for scope in CANDIDATE_COVERAGE_SCOPES
                    },
                },
            )

            accumulator["record_count"] += 1
            accumulator["records"].append(item)

            if publisher:
                accumulator["publisher_names"].add(publisher)
                accumulator["publisher_counts"][publisher] = (
                    accumulator["publisher_counts"].get(publisher, 0)
                    + 1
                )
            if published_date:
                accumulator["active_dates"].add(published_date)

            locations = set(match.get("locations", []))
            if "headline" in locations:
                accumulator["headline_match_count"] += 1
            elif "summary" in locations:
                accumulator["summary_only_match_count"] += 1

            accumulator["scope_counts"][coverage_scope] += 1

    period_record_count = len(records)
    metrics: list[dict[str, Any]] = []

    for candidate, accumulator in accumulators.items():
        record_count = accumulator["record_count"]
        publisher_names = sorted(accumulator["publisher_names"])
        scope_counts = {
            scope: accumulator["scope_counts"][scope]
            for scope in CANDIDATE_COVERAGE_SCOPES
        }
        scope_shares = {
            scope: round_candidate_visibility_ratio(
                scope_counts[scope] / record_count
                if record_count
                else 0.0
            )
            for scope in CANDIDATE_COVERAGE_SCOPES
        }
        story_clusters = build_candidate_story_clusters(
            accumulator["records"],
            candidate,
        )
        publisher_ranking = sorted(
            accumulator["publisher_counts"].items(),
            key=lambda item: (
                -item[1],
                item[0].casefold(),
            ),
        )
        if publisher_ranking:
            leading_publisher, leading_publisher_count = (
                publisher_ranking[0]
            )
        else:
            leading_publisher = None
            leading_publisher_count = 0

        leading_story_count = (
            story_clusters[0]["record_count"]
            if story_clusters
            else 0
        )

        metrics.append(
            {
                "candidate": candidate,
                "record_count": record_count,
                "share": round_candidate_visibility_ratio(
                    record_count / period_record_count
                    if period_record_count
                    else 0.0
                ),
                "publisher_count": len(publisher_names),
                "publisher_names": publisher_names,
                "active_day_count": len(accumulator["active_dates"]),
                "headline_match_count": accumulator[
                    "headline_match_count"
                ],
                "summary_only_match_count": accumulator[
                    "summary_only_match_count"
                ],
                "scope_counts": scope_counts,
                "scope_shares": scope_shares,
                "story_cluster_count": len(story_clusters),
                "story_clusters": story_clusters,
                "concentration": {
                    "leading_publisher": leading_publisher,
                    "leading_publisher_record_count": (
                        leading_publisher_count
                    ),
                    "leading_publisher_share": (
                        round_candidate_visibility_ratio(
                            leading_publisher_count / record_count
                            if record_count
                            else 0.0
                        )
                    ),
                    "leading_story_record_count": leading_story_count,
                    "leading_story_share": (
                        round_candidate_visibility_ratio(
                            leading_story_count / record_count
                            if record_count
                            else 0.0
                        )
                    ),
                },
            }
        )

    metrics.sort(
        key=lambda metric: (
            -metric["record_count"],
            metric["candidate"].casefold(),
        )
    )
    return metrics


def build_candidate_visibility(
    candidate_watch: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    """Build race visibility and general political visibility separately."""

    anchor = generated_at.astimezone(timezone.utc).date()
    current_start = anchor - timedelta(days=6)
    prior_end = current_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=6)

    primary_records: list[dict[str, Any]] = []
    general_records: list[dict[str, Any]] = []

    for item in candidate_watch:
        coverage_scope = item.get("coverage_scope")

        if coverage_scope not in CANDIDATE_COVERAGE_SCOPES:
            raise RuntimeError(
                "candidate visibility record has invalid coverage_scope"
            )

        if coverage_scope in CANDIDATE_VISIBILITY_PRIMARY_SCOPES:
            primary_records.append(item)
        elif coverage_scope == CANDIDATE_VISIBILITY_SECONDARY_SCOPE:
            general_records.append(item)

    def period(
        source_records: list[dict[str, Any]],
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        records = []

        for item in source_records:
            published = parse_feed_datetime(
                item.get("published_at")
            )

            if (
                published is not None
                and start_date <= published.date() <= end_date
            ):
                records.append(item)

        publishers = sorted(
            {
                str(item.get("publisher") or "").strip()
                for item in records
                if str(item.get("publisher") or "").strip()
            }
        )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "record_count": len(records),
            "publisher_count": len(publishers),
            "publisher_names": publishers,
            "candidate_metrics": (
                build_candidate_visibility_metrics(records)
            ),
        }

    current_period = period(
        primary_records,
        current_start,
        anchor,
    )
    prior_period = period(
        primary_records,
        prior_start,
        prior_end,
    )
    general_current_period = period(
        general_records,
        current_start,
        anchor,
    )
    general_prior_period = period(
        general_records,
        prior_start,
        prior_end,
    )

    current_publishers = set(
        current_period["publisher_names"]
    )
    prior_publishers = set(
        prior_period["publisher_names"]
    )
    common_publisher_count = len(
        current_publishers & prior_publishers
    )
    publisher_union_count = len(
        current_publishers | prior_publishers
    )
    publisher_overlap_ratio = (
        round_candidate_visibility_ratio(
            common_publisher_count / publisher_union_count
            if publisher_union_count
            else 0.0
        )
    )

    current_record_count = current_period["record_count"]
    prior_record_count = prior_period["record_count"]

    record_count_ratio = (
        round_candidate_visibility_ratio(
            max(current_record_count, prior_record_count)
            / min(current_record_count, prior_record_count)
        )
        if current_record_count and prior_record_count
        else None
    )

    status, reason = candidate_visibility_gate(
        current_record_count=current_record_count,
        prior_record_count=prior_record_count,
        current_publisher_count=current_period[
            "publisher_count"
        ],
        prior_publisher_count=prior_period[
            "publisher_count"
        ],
        common_publisher_count=common_publisher_count,
        publisher_overlap_ratio=publisher_overlap_ratio,
        record_count_ratio=record_count_ratio,
    )

    return {
        "method": CANDIDATE_VISIBILITY_METHOD,
        "primary_scopes": list(
            CANDIDATE_VISIBILITY_PRIMARY_SCOPES
        ),
        "secondary_scope": (
            CANDIDATE_VISIBILITY_SECONDARY_SCOPE
        ),
        "current_period": current_period,
        "prior_period": prior_period,
        "general_current_period": general_current_period,
        "general_prior_period": general_prior_period,
        "comparison_quality": {
            "status": status,
            "reason": reason,
            "current_record_count": current_record_count,
            "prior_record_count": prior_record_count,
            "current_publisher_count": current_period[
                "publisher_count"
            ],
            "prior_publisher_count": prior_period[
                "publisher_count"
            ],
            "common_publisher_count": (
                common_publisher_count
            ),
            "publisher_union_count": (
                publisher_union_count
            ),
            "publisher_overlap_ratio": (
                publisher_overlap_ratio
            ),
            "record_count_ratio": record_count_ratio,
            "thresholds": dict(
                CANDIDATE_VISIBILITY_THRESHOLDS
            ),
        },
    }


def validate_candidate_visibility(
    candidate_visibility: Any,
    candidate_watch: list[dict[str, Any]],
    generated_at: datetime,
) -> None:
    top_level_keys = {
        "method",
        "primary_scopes",
        "secondary_scope",
        "current_period",
        "prior_period",
        "general_current_period",
        "general_prior_period",
        "comparison_quality",
    }
    if (
        not isinstance(candidate_visibility, dict)
        or set(candidate_visibility) != top_level_keys
    ):
        raise RuntimeError("candidate_visibility has unexpected fields")
    if candidate_visibility["method"] != CANDIDATE_VISIBILITY_METHOD:
        raise RuntimeError("candidate_visibility method is invalid")

    if (
        candidate_visibility["primary_scopes"]
        != list(CANDIDATE_VISIBILITY_PRIMARY_SCOPES)
        or candidate_visibility["secondary_scope"]
        != CANDIDATE_VISIBILITY_SECONDARY_SCOPE
    ):
        raise RuntimeError(
            "candidate_visibility scope contract is invalid"
        )

    period_keys = {
        "start_date",
        "end_date",
        "record_count",
        "publisher_count",
        "publisher_names",
        "candidate_metrics",
    }
    parsed_periods: dict[str, tuple[date, date]] = {}

    period_names = (
        "current_period",
        "prior_period",
        "general_current_period",
        "general_prior_period",
    )

    for period_name in period_names:
        period = candidate_visibility.get(period_name)
        if not isinstance(period, dict) or set(period) != period_keys:
            raise RuntimeError(
                f"candidate_visibility {period_name} has unexpected fields"
            )
        try:
            start_date = date.fromisoformat(period["start_date"])
            end_date = date.fromisoformat(period["end_date"])
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"candidate_visibility {period_name} dates are invalid"
            ) from error
        if (
            period["start_date"] != start_date.isoformat()
            or period["end_date"] != end_date.isoformat()
            or start_date > end_date
            or (end_date - start_date).days != 6
        ):
            raise RuntimeError(
                f"candidate_visibility {period_name} dates are invalid"
            )
        parsed_periods[period_name] = (start_date, end_date)

        for field in ("record_count", "publisher_count"):
            if type(period[field]) is not int or period[field] < 0:
                raise RuntimeError(
                    f"candidate_visibility {period_name} counts are invalid"
                )

        publisher_names = period["publisher_names"]
        if (
            not isinstance(publisher_names, list)
            or any(
                not isinstance(name, str)
                or not name.strip()
                or name != name.strip()
                for name in publisher_names
            )
            or publisher_names != sorted(publisher_names)
            or len(publisher_names) != len(set(publisher_names))
            or period["publisher_count"] != len(publisher_names)
        ):
            raise RuntimeError(
                f"candidate_visibility {period_name} publishers are invalid"
            )

        candidate_metrics = period["candidate_metrics"]
        metric_keys = {
            "candidate",
            "record_count",
            "share",
            "publisher_count",
            "publisher_names",
            "active_day_count",
            "headline_match_count",
            "summary_only_match_count",
            "scope_counts",
            "scope_shares",
            "story_cluster_count",
            "story_clusters",
            "concentration",
        }
        if not isinstance(candidate_metrics, list):
            raise RuntimeError(
                f"candidate_visibility {period_name} metrics are invalid"
            )

        metric_candidates: list[str] = []
        expected_metric_order: list[tuple[int, str]] = []

        for metric in candidate_metrics:
            if not isinstance(metric, dict) or set(metric) != metric_keys:
                raise RuntimeError(
                    f"candidate_visibility {period_name} metric "
                    "has unexpected fields"
                )

            candidate = metric["candidate"]
            if (
                not isinstance(candidate, str)
                or not candidate.strip()
                or candidate != candidate.strip()
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} candidate is invalid"
                )

            metric_candidates.append(candidate)
            expected_metric_order.append(
                (-metric["record_count"], candidate.casefold())
            )

            count_fields = (
                "record_count",
                "publisher_count",
                "active_day_count",
                "headline_match_count",
                "summary_only_match_count",
            )
            if any(
                type(metric[field]) is not int or metric[field] < 0
                for field in count_fields
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} metric counts "
                    "are invalid"
                )

            if metric["record_count"] <= 0:
                raise RuntimeError(
                    f"candidate_visibility {period_name} metric "
                    "record count is invalid"
                )

            share = metric["share"]
            if (
                isinstance(share, bool)
                or not isinstance(share, (int, float))
                or not math.isfinite(share)
                or not 0 <= share <= 1
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} share is invalid"
                )

            expected_share = round_candidate_visibility_ratio(
                metric["record_count"] / period["record_count"]
                if period["record_count"]
                else 0.0
            )
            if share != expected_share:
                raise RuntimeError(
                    f"candidate_visibility {period_name} share "
                    "is inconsistent"
                )

            metric_publishers = metric["publisher_names"]
            if (
                not isinstance(metric_publishers, list)
                or any(
                    not isinstance(name, str)
                    or not name.strip()
                    or name != name.strip()
                    for name in metric_publishers
                )
                or metric_publishers != sorted(metric_publishers)
                or len(metric_publishers)
                != len(set(metric_publishers))
                or metric["publisher_count"]
                != len(metric_publishers)
                or metric["publisher_count"]
                > metric["record_count"]
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} metric "
                    "publishers are invalid"
                )

            if (
                metric["active_day_count"] > 7
                or metric["active_day_count"] > metric["record_count"]
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} active days "
                    "are invalid"
                )

            if (
                metric["headline_match_count"]
                + metric["summary_only_match_count"]
                != metric["record_count"]
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} match "
                    "provenance is inconsistent"
                )

            scope_counts = metric["scope_counts"]
            scope_shares = metric["scope_shares"]
            if (
                not isinstance(scope_counts, dict)
                or set(scope_counts) != set(CANDIDATE_COVERAGE_SCOPES)
                or any(
                    type(scope_counts[scope]) is not int
                    or scope_counts[scope] < 0
                    for scope in CANDIDATE_COVERAGE_SCOPES
                )
                or sum(scope_counts.values()) != metric["record_count"]
                or not isinstance(scope_shares, dict)
                or set(scope_shares) != set(CANDIDATE_COVERAGE_SCOPES)
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} scope "
                    "composition is invalid"
                )

            for scope in CANDIDATE_COVERAGE_SCOPES:
                scope_share = scope_shares[scope]
                expected_scope_share = round_candidate_visibility_ratio(
                    scope_counts[scope] / metric["record_count"]
                )
                if (
                    isinstance(scope_share, bool)
                    or not isinstance(scope_share, (int, float))
                    or not math.isfinite(scope_share)
                    or not 0 <= scope_share <= 1
                    or scope_share != expected_scope_share
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} scope "
                        "share is invalid"
                    )

            story_clusters = metric["story_clusters"]
            if (
                type(metric["story_cluster_count"]) is not int
                or metric["story_cluster_count"] < 0
                or not isinstance(story_clusters, list)
                or metric["story_cluster_count"] != len(story_clusters)
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} story "
                    "clusters are invalid"
                )

            cluster_keys = {
                "cluster_id",
                "label",
                "record_count",
                "share",
                "publisher_count",
                "active_day_count",
                "item_ids",
            }
            cluster_ids: set[str] = set()
            clustered_item_ids: list[str] = []
            cluster_record_total = 0
            cluster_order: list[
                tuple[int, int, int, str, str]
            ] = []

            for cluster in story_clusters:
                if (
                    not isinstance(cluster, dict)
                    or set(cluster) != cluster_keys
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} story "
                        "cluster has unexpected fields"
                    )

                cluster_id = cluster["cluster_id"]
                label = cluster["label"]
                if (
                    not isinstance(cluster_id, str)
                    or not cluster_id.strip()
                    or cluster_id in cluster_ids
                    or not isinstance(label, str)
                    or not label.strip()
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} story "
                        "cluster identity is invalid"
                    )
                cluster_ids.add(cluster_id)

                for field in (
                    "record_count",
                    "publisher_count",
                    "active_day_count",
                ):
                    if (
                        type(cluster[field]) is not int
                        or cluster[field] <= 0
                    ):
                        raise RuntimeError(
                            f"candidate_visibility {period_name} story "
                            "cluster counts are invalid"
                        )

                if (
                    cluster["publisher_count"]
                    > cluster["record_count"]
                    or cluster["active_day_count"] > 7
                    or cluster["active_day_count"]
                    > cluster["record_count"]
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} story "
                        "cluster breadth is invalid"
                    )

                item_ids = cluster["item_ids"]
                if (
                    not isinstance(item_ids, list)
                    or len(item_ids) != cluster["record_count"]
                    or any(
                        not isinstance(item_id, str)
                        or not item_id.strip()
                        for item_id in item_ids
                    )
                    or len(item_ids) != len(set(item_ids))
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} story "
                        "cluster evidence is invalid"
                    )

                cluster_share = cluster["share"]
                expected_cluster_share = (
                    round_candidate_visibility_ratio(
                        cluster["record_count"]
                        / metric["record_count"]
                    )
                )
                if (
                    isinstance(cluster_share, bool)
                    or not isinstance(cluster_share, (int, float))
                    or not math.isfinite(cluster_share)
                    or cluster_share != expected_cluster_share
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} story "
                        "cluster share is invalid"
                    )

                clustered_item_ids.extend(item_ids)
                cluster_record_total += cluster["record_count"]
                cluster_order.append(
                    (
                        -cluster["record_count"],
                        -cluster["publisher_count"],
                        -cluster["active_day_count"],
                        label.casefold(),
                        cluster_id,
                    )
                )

            if (
                cluster_record_total != metric["record_count"]
                or len(clustered_item_ids)
                != len(set(clustered_item_ids))
                or cluster_order != sorted(cluster_order)
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} story "
                    "cluster coverage is invalid"
                )

            concentration = metric["concentration"]
            concentration_keys = {
                "leading_publisher",
                "leading_publisher_record_count",
                "leading_publisher_share",
                "leading_story_record_count",
                "leading_story_share",
            }
            if (
                not isinstance(concentration, dict)
                or set(concentration) != concentration_keys
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} "
                    "concentration is invalid"
                )

            leading_publisher = concentration["leading_publisher"]
            if (
                leading_publisher is not None
                and (
                    not isinstance(leading_publisher, str)
                    or not leading_publisher.strip()
                )
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} leading "
                    "publisher is invalid"
                )

            for field in (
                "leading_publisher_record_count",
                "leading_story_record_count",
            ):
                if (
                    type(concentration[field]) is not int
                    or concentration[field] < 0
                    or concentration[field] > metric["record_count"]
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} "
                        "concentration counts are invalid"
                    )

            for count_field, share_field in (
                (
                    "leading_publisher_record_count",
                    "leading_publisher_share",
                ),
                (
                    "leading_story_record_count",
                    "leading_story_share",
                ),
            ):
                share = concentration[share_field]
                expected_share = round_candidate_visibility_ratio(
                    concentration[count_field] / metric["record_count"]
                )
                if (
                    isinstance(share, bool)
                    or not isinstance(share, (int, float))
                    or not math.isfinite(share)
                    or share != expected_share
                ):
                    raise RuntimeError(
                        f"candidate_visibility {period_name} "
                        "concentration share is invalid"
                    )

            expected_leading_story_count = (
                story_clusters[0]["record_count"]
                if story_clusters
                else 0
            )
            if (
                concentration["leading_story_record_count"]
                != expected_leading_story_count
                or (
                    concentration["leading_publisher_record_count"] == 0
                    and leading_publisher is not None
                )
                or (
                    concentration["leading_publisher_record_count"] > 0
                    and leading_publisher is None
                )
            ):
                raise RuntimeError(
                    f"candidate_visibility {period_name} "
                    "concentration is inconsistent"
                )

        if (
            len(metric_candidates) != len(set(metric_candidates))
            or expected_metric_order != sorted(expected_metric_order)
        ):
            raise RuntimeError(
                f"candidate_visibility {period_name} metric ordering "
                "is invalid"
            )

    current_start, current_end = parsed_periods[
        "current_period"
    ]
    prior_start, prior_end = parsed_periods[
        "prior_period"
    ]
    general_current_start, general_current_end = (
        parsed_periods["general_current_period"]
    )
    general_prior_start, general_prior_end = (
        parsed_periods["general_prior_period"]
    )

    expected_current_end = (
        generated_at.astimezone(timezone.utc).date()
    )

    if (
        current_end != expected_current_end
        or current_start != current_end - timedelta(days=6)
        or prior_end != current_start - timedelta(days=1)
        or prior_start != prior_end - timedelta(days=6)
        or (
            general_current_start,
            general_current_end,
        )
        != (
            current_start,
            current_end,
        )
        or (
            general_prior_start,
            general_prior_end,
        )
        != (
            prior_start,
            prior_end,
        )
    ):
        raise RuntimeError(
            "candidate_visibility periods are invalid"
        )

    quality_keys = {
        "status",
        "reason",
        "current_record_count",
        "prior_record_count",
        "current_publisher_count",
        "prior_publisher_count",
        "common_publisher_count",
        "publisher_union_count",
        "publisher_overlap_ratio",
        "record_count_ratio",
        "thresholds",
    }
    quality = candidate_visibility.get("comparison_quality")
    if not isinstance(quality, dict) or set(quality) != quality_keys:
        raise RuntimeError(
            "candidate_visibility comparison_quality has unexpected fields"
        )
    thresholds = quality.get("thresholds")
    if (
        not isinstance(thresholds, dict)
        or set(thresholds) != set(CANDIDATE_VISIBILITY_THRESHOLDS)
        or any(
            type(thresholds[field]) is not type(expected)
            or thresholds[field] != expected
            for field, expected in (
                CANDIDATE_VISIBILITY_THRESHOLDS.items()
            )
        )
    ):
        raise RuntimeError(
            "candidate_visibility comparison thresholds are invalid"
        )

    count_fields = (
        "current_record_count",
        "prior_record_count",
        "current_publisher_count",
        "prior_publisher_count",
        "common_publisher_count",
        "publisher_union_count",
    )
    if any(
        type(quality.get(field)) is not int or quality[field] < 0
        for field in count_fields
    ):
        raise RuntimeError(
            "candidate_visibility comparison counts are invalid"
        )

    current_period = candidate_visibility["current_period"]
    prior_period = candidate_visibility["prior_period"]
    expected_counts = {
        "current_record_count": current_period["record_count"],
        "prior_record_count": prior_period["record_count"],
        "current_publisher_count": current_period["publisher_count"],
        "prior_publisher_count": prior_period["publisher_count"],
    }
    if any(
        quality[field] != expected
        for field, expected in expected_counts.items()
    ):
        raise RuntimeError(
            "candidate_visibility comparison counts are inconsistent"
        )

    current_publishers = set(current_period["publisher_names"])
    prior_publishers = set(prior_period["publisher_names"])
    expected_common = len(current_publishers & prior_publishers)
    expected_union = len(current_publishers | prior_publishers)
    if (
        quality["common_publisher_count"] > current_period[
            "publisher_count"
        ]
        or quality["common_publisher_count"] > prior_period[
            "publisher_count"
        ]
        or quality["common_publisher_count"] != expected_common
        or quality["publisher_union_count"] != expected_union
    ):
        raise RuntimeError(
            "candidate_visibility publisher counts are inconsistent"
        )

    overlap_ratio = quality.get("publisher_overlap_ratio")
    if (
        isinstance(overlap_ratio, bool)
        or not isinstance(overlap_ratio, (int, float))
        or not math.isfinite(overlap_ratio)
        or not 0 <= overlap_ratio <= 1
    ):
        raise RuntimeError(
            "candidate_visibility publisher overlap ratio is invalid"
        )
    expected_overlap = round_candidate_visibility_ratio(
        expected_common / expected_union if expected_union else 0.0
    )
    if overlap_ratio != expected_overlap:
        raise RuntimeError(
            "candidate_visibility publisher overlap ratio is inconsistent"
        )

    record_ratio = quality.get("record_count_ratio")
    current_record_count = current_period["record_count"]
    prior_record_count = prior_period["record_count"]
    expected_record_ratio = (
        round_candidate_visibility_ratio(
            max(current_record_count, prior_record_count)
            / min(current_record_count, prior_record_count)
        )
        if current_record_count and prior_record_count
        else None
    )
    if record_ratio is not None and (
        isinstance(record_ratio, bool)
        or not isinstance(record_ratio, (int, float))
        or not math.isfinite(record_ratio)
        or record_ratio < 1
    ):
        raise RuntimeError(
            "candidate_visibility record count ratio is invalid"
        )
    if record_ratio != expected_record_ratio:
        raise RuntimeError(
            "candidate_visibility record count ratio is inconsistent"
        )

    expected_visibility = build_candidate_visibility(
        candidate_watch,
        generated_at,
    )

    for period_name in period_names:
        expected_period = expected_visibility[period_name]
        if candidate_visibility[period_name] != expected_period:
            raise RuntimeError(
                f"candidate_visibility {period_name} does not match "
                "candidate_watch"
            )

    expected_status, expected_reason = candidate_visibility_gate(
        current_record_count=current_record_count,
        prior_record_count=prior_record_count,
        current_publisher_count=current_period["publisher_count"],
        prior_publisher_count=prior_period["publisher_count"],
        common_publisher_count=expected_common,
        publisher_overlap_ratio=overlap_ratio,
        record_count_ratio=record_ratio,
    )
    if (
        quality.get("status") != expected_status
        or quality.get("reason") != expected_reason
    ):
        raise RuntimeError(
            "candidate_visibility comparison status is inconsistent"
        )


def validate_campaign_agenda_topic(
    topic: Any,
    seen_topic_ids: set[str],
) -> None:
    required = {
        "id",
        "label",
        "item_count",
        "publisher_count",
        "publisher_names",
        "source_day_count",
        "active_day_count",
        "display_eligible",
        "supporting_item_count",
        "omitted_item_count",
        "supporting_items",
    }

    if not isinstance(topic, dict) or set(topic) != required:
        raise RuntimeError(
            "campaign_agenda topic has unexpected fields"
        )

    topic_id = topic["id"]
    if (
        not isinstance(topic_id, str)
        or not topic_id.strip()
        or topic_id in seen_topic_ids
    ):
        raise RuntimeError(
            "campaign_agenda contains duplicate or invalid topic ids"
        )

    if (
        not isinstance(topic["label"], str)
        or not topic["label"].strip()
    ):
        raise RuntimeError(
            "campaign_agenda topic label is invalid"
        )

    count_fields = (
        "item_count",
        "publisher_count",
        "source_day_count",
        "active_day_count",
        "supporting_item_count",
        "omitted_item_count",
    )
    if any(
        type(topic[field]) is not int
        or topic[field] < 0
        for field in count_fields
    ):
        raise RuntimeError(
            "campaign_agenda topic counts are invalid"
        )

    supporting_items = topic["supporting_items"]
    if not isinstance(supporting_items, list):
        raise RuntimeError(
            "campaign_agenda supporting_items is not a list"
        )

    expected_supporting_count = min(
        topic["item_count"],
        CAMPAIGN_AGENDA_SUPPORT_LIMIT,
    )

    if (
        topic["supporting_item_count"]
        != len(supporting_items)
        or topic["supporting_item_count"]
        != expected_supporting_count
        or topic["omitted_item_count"]
        != topic["item_count"] - len(supporting_items)
    ):
        raise RuntimeError(
            "campaign_agenda supporting item count is invalid"
        )

    item_keys = {
        "id",
        "publisher",
        "published_at",
        "headline",
        "url",
        "candidates",
        "matched_terms",
    }
    item_ids: list[str] = []

    for item in supporting_items:
        if (
            not isinstance(item, dict)
            or set(item) != item_keys
        ):
            raise RuntimeError(
                "campaign_agenda supporting item "
                "has unexpected fields"
            )

        item_id = item["id"]
        if (
            not isinstance(item_id, str)
            or not item_id.strip()
        ):
            raise RuntimeError(
                "campaign_agenda supporting item id is invalid"
            )

        item_ids.append(item_id)

        if (
            not isinstance(item["publisher"], str)
            or not item["publisher"].strip()
            or not isinstance(item["headline"], str)
            or not item["headline"].strip()
            or parse_feed_datetime(
                item["published_at"]
            ) is None
            or not str(item["url"]).startswith(
                ("http://", "https://")
            )
        ):
            raise RuntimeError(
                "campaign_agenda supporting item is invalid"
            )

        for field in ("candidates", "matched_terms"):
            values = item[field]

            if (
                not isinstance(values, list)
                or any(
                    not isinstance(value, str)
                    or not value.strip()
                    for value in values
                )
                or len(values) != len(set(values))
            ):
                raise RuntimeError(
                    "campaign_agenda supporting item "
                    "provenance is invalid"
                )

    if len(item_ids) != len(set(item_ids)):
        raise RuntimeError(
            "campaign_agenda supporting items "
            "contain duplicate ids"
        )

    ordering = [
        campaign_agenda_support_sort_key(item)
        for item in supporting_items
    ]
    if ordering != sorted(ordering):
        raise RuntimeError(
            "campaign_agenda supporting item order is invalid"
        )

    publisher_names = topic["publisher_names"]
    if (
        not isinstance(publisher_names, list)
        or any(
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            for name in publisher_names
        )
        or publisher_names != sorted(publisher_names)
        or len(publisher_names)
        != len(set(publisher_names))
        or topic["publisher_count"]
        != len(publisher_names)
    ):
        raise RuntimeError(
            "campaign_agenda publisher evidence is invalid"
        )

    if (
        type(topic["display_eligible"]) is not bool
        or topic["display_eligible"]
        != (
            topic["source_day_count"]
            >= CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        )
    ):
        raise RuntimeError(
            "campaign_agenda display eligibility is invalid"
        )

    seen_topic_ids.add(topic_id)


def validate_campaign_agenda_evolution(
    evolution: Any,
    agenda_topics: list[dict[str, Any]],
) -> None:
    required = {
        "period_days",
        "period_start",
        "period_end",
        "period_end_partial",
        "comparison_days",
        "latest_start",
        "latest_end",
        "previous_start",
        "previous_end",
        "topics",
    }

    if (
        not isinstance(evolution, dict)
        or set(evolution) != required
    ):
        raise RuntimeError(
            "campaign_agenda evolution has unexpected fields"
        )

    if (
        type(evolution["period_days"]) is not int
        or evolution["period_days"]
        != CAMPAIGN_AGENDA_EVOLUTION_DAYS
        or type(evolution["comparison_days"])
        is not int
        or evolution["comparison_days"]
        != CAMPAIGN_AGENDA_COMPARISON_DAYS
        or type(evolution["period_end_partial"])
        is not bool
    ):
        raise RuntimeError(
            "campaign_agenda evolution window is invalid"
        )

    try:
        period_start = date.fromisoformat(
            evolution["period_start"]
        )
        period_end = date.fromisoformat(
            evolution["period_end"]
        )
        latest_start = date.fromisoformat(
            evolution["latest_start"]
        )
        latest_end = date.fromisoformat(
            evolution["latest_end"]
        )
        previous_start = date.fromisoformat(
            evolution["previous_start"]
        )
        previous_end = date.fromisoformat(
            evolution["previous_end"]
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "campaign_agenda evolution dates are invalid"
        ) from error

    if (
        period_start
        != period_end
        - timedelta(
            days=CAMPAIGN_AGENDA_EVOLUTION_DAYS - 1
        )
        or latest_end
        != period_end - timedelta(days=1)
        or latest_start
        != latest_end
        - timedelta(
            days=CAMPAIGN_AGENDA_COMPARISON_DAYS - 1
        )
        or previous_end
        != latest_start - timedelta(days=1)
        or previous_start
        != previous_end
        - timedelta(
            days=CAMPAIGN_AGENDA_COMPARISON_DAYS - 1
        )
    ):
        raise RuntimeError(
            "campaign_agenda evolution date windows are inconsistent"
        )

    evolution_topics = evolution["topics"]

    if not isinstance(evolution_topics, list):
        raise RuntimeError(
            "campaign_agenda evolution topics is not a list"
        )

    agenda_ids = {
        topic["id"]
        for topic in agenda_topics
    }

    evolution_ids: set[str] = set()

    expected_dates = [
        (
            period_start
            + timedelta(days=offset)
        ).isoformat()
        for offset in range(
            CAMPAIGN_AGENDA_EVOLUTION_DAYS
        )
    ]

    ordering: list[
        tuple[bool, int, int, str]
    ] = []

    for topic in evolution_topics:
        topic_required = {
            "id",
            "label",
            "item_count",
            "publisher_count",
            "source_day_count",
            "active_day_count",
            "display_eligible",
            "daily_activity",
            "matched_term_counts",
        }

        if (
            not isinstance(topic, dict)
            or set(topic) != topic_required
        ):
            raise RuntimeError(
                "campaign_agenda evolution topic has unexpected fields"
            )

        topic_id = topic["id"]

        if (
            not isinstance(topic_id, str)
            or not topic_id.strip()
            or topic_id in evolution_ids
        ):
            raise RuntimeError(
                "campaign_agenda evolution topic id is invalid"
            )

        evolution_ids.add(topic_id)

        if (
            not isinstance(topic["label"], str)
            or not topic["label"].strip()
        ):
            raise RuntimeError(
                "campaign_agenda evolution topic label is invalid"
            )

        for field in (
            "item_count",
            "publisher_count",
            "source_day_count",
            "active_day_count",
        ):
            if (
                type(topic[field]) is not int
                or topic[field] < 0
            ):
                raise RuntimeError(
                    "campaign_agenda evolution topic counts are invalid"
                )

        if (
            topic["publisher_count"]
            > topic["item_count"]
            or topic["source_day_count"]
            > topic["item_count"]
            or topic["active_day_count"]
            > CAMPAIGN_AGENDA_EVOLUTION_DAYS
        ):
            raise RuntimeError(
                "campaign_agenda evolution topic counts are inconsistent"
            )

        if (
            type(topic["display_eligible"])
            is not bool
            or topic["display_eligible"]
            != (
                topic["source_day_count"]
                >= CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
            )
        ):
            raise RuntimeError(
                "campaign_agenda evolution eligibility is invalid"
            )

        daily_activity = topic[
            "daily_activity"
        ]

        if (
            not isinstance(daily_activity, list)
            or len(daily_activity)
            != CAMPAIGN_AGENDA_EVOLUTION_DAYS
        ):
            raise RuntimeError(
                "campaign_agenda evolution daily activity is invalid"
            )

        actual_dates: list[str] = []

        for day in daily_activity:
            if (
                not isinstance(day, dict)
                or set(day)
                != {
                    "date",
                    "item_count",
                    "source_day_count",
                }
                or not isinstance(
                    day["date"],
                    str,
                )
                or type(day["item_count"])
                is not int
                or day["item_count"] < 0
                or type(day["source_day_count"])
                is not int
                or day["source_day_count"] < 0
                or day["source_day_count"]
                > day["item_count"]
            ):
                raise RuntimeError(
                    "campaign_agenda evolution daily value is invalid"
                )

            actual_dates.append(day["date"])

        if actual_dates != expected_dates:
            raise RuntimeError(
                "campaign_agenda evolution daily dates are invalid"
            )

        if (
            sum(
                day["item_count"]
                for day in daily_activity
            )
            != topic["item_count"]
            or sum(
                day["source_day_count"]
                for day in daily_activity
            )
            != topic["source_day_count"]
            or sum(
                day["item_count"] > 0
                for day in daily_activity
            )
            != topic["active_day_count"]
        ):
            raise RuntimeError(
                "campaign_agenda evolution daily totals are inconsistent"
            )

        matched_terms = topic[
            "matched_term_counts"
        ]

        if not isinstance(matched_terms, list):
            raise RuntimeError(
                "campaign_agenda evolution matched terms are invalid"
            )

        term_names: list[str] = []
        term_order: list[
            tuple[int, str]
        ] = []

        for matched in matched_terms:
            if (
                not isinstance(matched, dict)
                or set(matched)
                != {"term", "item_count"}
                or not isinstance(
                    matched["term"],
                    str,
                )
                or not matched["term"].strip()
                or type(
                    matched["item_count"]
                )
                is not int
                or matched["item_count"] < 1
                or matched["item_count"]
                > topic["item_count"]
            ):
                raise RuntimeError(
                    "campaign_agenda evolution matched term is invalid"
                )

            term_names.append(
                matched["term"]
            )
            term_order.append(
                (
                    -matched["item_count"],
                    matched["term"],
                )
            )

        if (
            len(term_names)
            != len(set(term_names))
            or term_order != sorted(term_order)
        ):
            raise RuntimeError(
                "campaign_agenda evolution matched term ordering is invalid"
            )

        ordering.append(
            (
                not topic["display_eligible"],
                -topic["source_day_count"],
                -topic["item_count"],
                topic["label"],
            )
        )

    if evolution_ids != agenda_ids:
        raise RuntimeError(
            "campaign_agenda evolution topics do not match agenda topics"
        )

    if ordering != sorted(ordering):
        raise RuntimeError(
            "campaign_agenda evolution topic order is invalid"
        )


def validate_campaign_agenda(
    campaign_agenda: Any,
    relevant_news: Any,
) -> None:
    required = {
        "window_days",
        "input_item_count",
        "classified_item_count",
        "unclassified_item_count",
        "method",
        "display_min_source_days",
        "evolution",
        "topics",
    }

    if (
        not isinstance(campaign_agenda, dict)
        or set(campaign_agenda) != required
    ):
        raise RuntimeError(
            "campaign_agenda has unexpected fields"
        )

    if not isinstance(relevant_news, list):
        raise RuntimeError(
            "campaign_agenda relevant_news input "
            "is invalid"
        )

    if (
        campaign_agenda["method"]
        != "accepted_relevant_news_by_campaign_theme"
    ):
        raise RuntimeError(
            "campaign_agenda method is invalid"
        )

    for field in (
        "window_days",
        "input_item_count",
        "classified_item_count",
        "unclassified_item_count",
        "display_min_source_days",
    ):
        if (
            type(campaign_agenda[field])
            is not int
            or campaign_agenda[field] < 0
        ):
            raise RuntimeError(
                "campaign_agenda counts are invalid"
            )

    if (
        campaign_agenda[
            "display_min_source_days"
        ]
        != CAMPAIGN_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        or campaign_agenda["window_days"] < 1
        or campaign_agenda["input_item_count"]
        != len(relevant_news)
        or (
            campaign_agenda[
                "classified_item_count"
            ]
            + campaign_agenda[
                "unclassified_item_count"
            ]
            != campaign_agenda[
                "input_item_count"
            ]
        )
    ):
        raise RuntimeError(
            "campaign_agenda coverage counts "
            "are inconsistent"
        )

    agenda_topics = campaign_agenda["topics"]

    if not isinstance(agenda_topics, list):
        raise RuntimeError(
            "campaign_agenda topics is not a list"
        )

    agenda_ids: set[str] = set()
    supporting_ids: set[str] = set()

    for topic in agenda_topics:
        validate_campaign_agenda_topic(
            topic,
            agenda_ids,
        )

        if topic["id"] == "other_campaign":
            raise RuntimeError(
                "campaign_agenda contains an "
                "unsupported catch-all topic"
            )

        for item in topic["supporting_items"]:
            item_id = item["id"]

            if item_id in supporting_ids:
                raise RuntimeError(
                    "campaign_agenda evidence is "
                    "assigned to multiple topics"
                )

            supporting_ids.add(item_id)

    validate_campaign_agenda_evolution(
        campaign_agenda["evolution"],
        agenda_topics,
    )

    if (
        sum(
            topic["item_count"]
            for topic in agenda_topics
        )
        != campaign_agenda[
            "classified_item_count"
        ]
    ):
        raise RuntimeError(
            "campaign_agenda classified count "
            "is inconsistent"
        )

    relevant_ids = {
        str(item.get("id") or "")
        for item in relevant_news
        if isinstance(item, dict)
        and str(item.get("id") or "")
    }

    if not supporting_ids.issubset(
        relevant_ids
    ):
        raise RuntimeError(
            "campaign_agenda evidence is not "
            "a subset of relevant_news"
        )




def validate_policy_agenda_topic(
    topic: Any,
    seen_topic_ids: set[str],
) -> set[str]:
    """Validate one multi-label Policy Agenda root."""

    taxonomy = {
        item["id"]: item
        for item in POLICY_AGENDA_TOPICS
    }

    required = {
        "id",
        "label",
        "item_count",
        "publisher_count",
        "publisher_names",
        "source_day_count",
        "active_day_count",
        "display_eligible",
        "subtopic_counts",
        "candidate_counts",
        "supporting_item_count",
        "omitted_item_count",
        "supporting_items",
    }

    if (
        not isinstance(topic, dict)
        or set(topic) != required
    ):
        raise RuntimeError(
            "policy_agenda topic has unexpected fields"
        )

    topic_id = topic["id"]

    if (
        not isinstance(topic_id, str)
        or topic_id not in taxonomy
        or topic_id in seen_topic_ids
    ):
        raise RuntimeError(
            "policy_agenda topic id is invalid"
        )

    definition = taxonomy[topic_id]

    if topic["label"] != definition["label"]:
        raise RuntimeError(
            "policy_agenda topic label is invalid"
        )

    count_fields = (
        "item_count",
        "publisher_count",
        "source_day_count",
        "active_day_count",
        "supporting_item_count",
        "omitted_item_count",
    )

    if any(
        type(topic[field]) is not int
        or topic[field] < 0
        for field in count_fields
    ):
        raise RuntimeError(
            "policy_agenda topic counts are invalid"
        )

    if (
        topic["publisher_count"]
        > topic["item_count"]
        or topic["source_day_count"]
        > topic["item_count"]
        or topic["active_day_count"]
        > topic["source_day_count"]
    ):
        raise RuntimeError(
            "policy_agenda topic counts are inconsistent"
        )

    if (
        type(topic["display_eligible"]) is not bool
        or topic["display_eligible"]
        != (
            topic["source_day_count"]
            >= POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        )
    ):
        raise RuntimeError(
            "policy_agenda display eligibility is invalid"
        )

    publisher_names = topic["publisher_names"]

    if (
        not isinstance(publisher_names, list)
        or any(
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            for name in publisher_names
        )
        or publisher_names != sorted(
            publisher_names
        )
        or len(publisher_names)
        != len(set(publisher_names))
        or topic["publisher_count"]
        != len(publisher_names)
    ):
        raise RuntimeError(
            "policy_agenda publisher evidence is invalid"
        )

    subtopic_definitions = set(
        definition["subtopics"]
    )
    subtopic_counts = topic[
        "subtopic_counts"
    ]

    if not isinstance(subtopic_counts, list):
        raise RuntimeError(
            "policy_agenda subtopic counts are invalid"
        )

    subtopic_ids: list[str] = []
    subtopic_order = []

    for item in subtopic_counts:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"id", "item_count"}
            or item["id"]
            not in subtopic_definitions
            or type(item["item_count"])
            is not int
            or item["item_count"] < 1
            or item["item_count"]
            > topic["item_count"]
        ):
            raise RuntimeError(
                "policy_agenda subtopic count is invalid"
            )

        subtopic_ids.append(item["id"])
        subtopic_order.append(
            (
                -item["item_count"],
                item["id"],
            )
        )

    if (
        len(subtopic_ids)
        != len(set(subtopic_ids))
        or subtopic_order
        != sorted(subtopic_order)
    ):
        raise RuntimeError(
            "policy_agenda subtopic ordering is invalid"
        )

    candidate_counts = topic[
        "candidate_counts"
    ]

    if not isinstance(candidate_counts, list):
        raise RuntimeError(
            "policy_agenda candidate counts are invalid"
        )

    candidate_names: list[str] = []
    candidate_order = []

    for item in candidate_counts:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"candidate", "item_count"}
            or not isinstance(
                item["candidate"],
                str,
            )
            or not item["candidate"].strip()
            or item["candidate"]
            != item["candidate"].strip()
            or type(item["item_count"])
            is not int
            or item["item_count"] < 1
            or item["item_count"]
            > topic["item_count"]
        ):
            raise RuntimeError(
                "policy_agenda candidate count is invalid"
            )

        candidate_names.append(
            item["candidate"]
        )
        candidate_order.append(
            (
                -item["item_count"],
                item["candidate"].casefold(),
            )
        )

    if (
        len(candidate_names)
        != len(set(candidate_names))
        or candidate_order
        != sorted(candidate_order)
    ):
        raise RuntimeError(
            "policy_agenda candidate ordering is invalid"
        )

    supporting_items = topic[
        "supporting_items"
    ]

    if not isinstance(supporting_items, list):
        raise RuntimeError(
            "policy_agenda supporting_items is invalid"
        )

    expected_support_count = min(
        topic["item_count"],
        POLICY_AGENDA_SUPPORT_LIMIT,
    )

    if (
        topic["supporting_item_count"]
        != len(supporting_items)
        or topic["supporting_item_count"]
        != expected_support_count
        or topic["omitted_item_count"]
        != (
            topic["item_count"]
            - len(supporting_items)
        )
    ):
        raise RuntimeError(
            "policy_agenda supporting item count is invalid"
        )

    allowed_terms = set(
        definition["terms"]
    )
    support_ids: list[str] = []

    expected_item_keys = {
        "id",
        "publisher",
        "published_at",
        "headline",
        "url",
        "candidates",
        "matched_terms",
        "subtopics",
    }

    for item in supporting_items:
        if (
            not isinstance(item, dict)
            or set(item)
            != expected_item_keys
        ):
            raise RuntimeError(
                "policy_agenda supporting item has unexpected fields"
            )

        item_id = item["id"]

        if (
            not isinstance(item_id, str)
            or not item_id.strip()
            or not isinstance(
                item["publisher"],
                str,
            )
            or not item["publisher"].strip()
            or not isinstance(
                item["headline"],
                str,
            )
            or not item["headline"].strip()
            or parse_feed_datetime(
                item["published_at"]
            )
            is None
            or not isinstance(
                item["url"],
                str,
            )
            or not item["url"].startswith(
                ("http://", "https://")
            )
        ):
            raise RuntimeError(
                "policy_agenda supporting item is invalid"
            )

        support_ids.append(item_id)

        candidates = item["candidates"]

        if (
            not isinstance(candidates, list)
            or any(
                not isinstance(candidate, str)
                or not candidate.strip()
                for candidate in candidates
            )
            or len(candidates)
            != len(set(candidates))
        ):
            raise RuntimeError(
                "policy_agenda candidate provenance is invalid"
            )

        matched_terms = item[
            "matched_terms"
        ]

        if (
            not isinstance(matched_terms, list)
            or not matched_terms
            or matched_terms
            != sorted(set(matched_terms))
            or any(
                term not in allowed_terms
                for term in matched_terms
            )
        ):
            raise RuntimeError(
                "policy_agenda matched term provenance is invalid"
            )

        subtopics = item["subtopics"]

        if (
            not isinstance(subtopics, list)
            or subtopics
            != sorted(set(subtopics))
            or any(
                subtopic
                not in subtopic_definitions
                for subtopic in subtopics
            )
        ):
            raise RuntimeError(
                "policy_agenda subtopic provenance is invalid"
            )

    if (
        len(support_ids)
        != len(set(support_ids))
    ):
        raise RuntimeError(
            "policy_agenda supporting items contain duplicate ids"
        )

    ordering = [
        campaign_agenda_support_sort_key(
            item
        )
        for item in supporting_items
    ]

    if ordering != sorted(ordering):
        raise RuntimeError(
            "policy_agenda supporting item order is invalid"
        )

    seen_topic_ids.add(topic_id)

    return set(support_ids)


def validate_policy_agenda_evolution(
    evolution: Any,
    agenda_topics: list[dict[str, Any]],
    relevant_news: list[dict[str, Any]],
) -> None:
    """Validate exact 30D recurrence and 7D incidence math."""

    taxonomy = {
        item["id"]: item
        for item in POLICY_AGENDA_TOPICS
    }

    required = {
        "period_days",
        "period_start",
        "period_end",
        "period_end_partial",
        "comparison_days",
        "latest_start",
        "latest_end",
        "previous_start",
        "previous_end",
        "accepted_daily_activity",
        "topics",
    }

    if (
        not isinstance(evolution, dict)
        or set(evolution) != required
    ):
        raise RuntimeError(
            "policy_agenda evolution has unexpected fields"
        )

    if (
        evolution["period_days"]
        != POLICY_AGENDA_EVOLUTION_DAYS
        or evolution["comparison_days"]
        != POLICY_AGENDA_COMPARISON_DAYS
        or type(
            evolution["period_end_partial"]
        )
        is not bool
        or not evolution[
            "period_end_partial"
        ]
    ):
        raise RuntimeError(
            "policy_agenda evolution window is invalid"
        )

    try:
        period_start = date.fromisoformat(
            evolution["period_start"]
        )
        period_end = date.fromisoformat(
            evolution["period_end"]
        )
        latest_start = date.fromisoformat(
            evolution["latest_start"]
        )
        latest_end = date.fromisoformat(
            evolution["latest_end"]
        )
        previous_start = date.fromisoformat(
            evolution["previous_start"]
        )
        previous_end = date.fromisoformat(
            evolution["previous_end"]
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "policy_agenda evolution dates are invalid"
        ) from error

    if (
        period_start
        != period_end
        - timedelta(
            days=POLICY_AGENDA_EVOLUTION_DAYS - 1
        )
        or latest_end
        != period_end - timedelta(days=1)
        or latest_start
        != latest_end
        - timedelta(
            days=POLICY_AGENDA_COMPARISON_DAYS - 1
        )
        or previous_end
        != latest_start - timedelta(days=1)
        or previous_start
        != previous_end
        - timedelta(
            days=POLICY_AGENDA_COMPARISON_DAYS - 1
        )
    ):
        raise RuntimeError(
            "policy_agenda evolution date windows are inconsistent"
        )

    expected_dates = [
        (
            period_start
            + timedelta(days=offset)
        ).isoformat()
        for offset in range(
            POLICY_AGENDA_EVOLUTION_DAYS
        )
    ]

    accepted_expected: dict[
        str,
        set[tuple[str, str]],
    ] = {
        date_key: set()
        for date_key in expected_dates
    }

    for item in relevant_news:
        if not isinstance(item, dict):
            continue

        published_at = str(
            item.get("published_at") or ""
        )
        publisher = str(
            item.get("publisher") or ""
        )

        if (
            len(published_at) < 10
            or not publisher
        ):
            continue

        date_key = published_at[:10]

        if date_key in accepted_expected:
            accepted_expected[
                date_key
            ].add(
                (publisher, date_key)
            )

    accepted_daily = evolution[
        "accepted_daily_activity"
    ]

    if (
        not isinstance(accepted_daily, list)
        or len(accepted_daily)
        != POLICY_AGENDA_EVOLUTION_DAYS
    ):
        raise RuntimeError(
            "policy_agenda accepted daily activity is invalid"
        )

    accepted_by_date: dict[str, int] = {}

    for expected_date, day in zip(
        expected_dates,
        accepted_daily,
    ):
        if (
            not isinstance(day, dict)
            or set(day)
            != {
                "date",
                "source_day_count",
            }
            or day["date"]
            != expected_date
            or type(
                day["source_day_count"]
            )
            is not int
            or day["source_day_count"] < 0
            or day["source_day_count"]
            != len(
                accepted_expected[
                    expected_date
                ]
            )
        ):
            raise RuntimeError(
                "policy_agenda accepted daily parity is invalid"
            )

        accepted_by_date[
            expected_date
        ] = day["source_day_count"]

    evolution_topics = evolution[
        "topics"
    ]

    if not isinstance(
        evolution_topics,
        list,
    ):
        raise RuntimeError(
            "policy_agenda evolution topics is invalid"
        )

    agenda_ids = {
        topic["id"]
        for topic in agenda_topics
    }
    evolution_ids: set[str] = set()
    ordering = []

    for topic in evolution_topics:
        required_topic = {
            "id",
            "label",
            "item_count",
            "publisher_count",
            "source_day_count",
            "active_day_count",
            "display_eligible",
            "latest_source_day_count",
            "previous_source_day_count",
            "latest_incidence",
            "previous_incidence",
            "incidence_change_pp",
            "daily_activity",
            "matched_term_counts",
        }

        if (
            not isinstance(topic, dict)
            or set(topic)
            != required_topic
        ):
            raise RuntimeError(
                "policy_agenda evolution topic has unexpected fields"
            )

        topic_id = topic["id"]

        if (
            topic_id not in taxonomy
            or topic_id in evolution_ids
            or topic["label"]
            != taxonomy[topic_id][
                "label"
            ]
        ):
            raise RuntimeError(
                "policy_agenda evolution topic identity is invalid"
            )

        evolution_ids.add(topic_id)

        for field in (
            "item_count",
            "publisher_count",
            "source_day_count",
            "active_day_count",
            "latest_source_day_count",
            "previous_source_day_count",
        ):
            if (
                type(topic[field]) is not int
                or topic[field] < 0
            ):
                raise RuntimeError(
                    "policy_agenda evolution counts are invalid"
                )

        if (
            topic["publisher_count"]
            > topic["item_count"]
            or topic["source_day_count"]
            > topic["item_count"]
            or topic["active_day_count"]
            > topic["source_day_count"]
        ):
            raise RuntimeError(
                "policy_agenda evolution counts are inconsistent"
            )

        if (
            type(
                topic["display_eligible"]
            )
            is not bool
            or topic["display_eligible"]
            != (
                topic["source_day_count"]
                >= POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS
            )
        ):
            raise RuntimeError(
                "policy_agenda evolution eligibility is invalid"
            )

        for field in (
            "latest_incidence",
            "previous_incidence",
            "incidence_change_pp",
        ):
            if (
                isinstance(
                    topic[field],
                    bool,
                )
                or not isinstance(
                    topic[field],
                    (int, float),
                )
                or not math.isfinite(
                    topic[field]
                )
            ):
                raise RuntimeError(
                    "policy_agenda incidence metric is invalid"
                )

        if (
            not 0
            <= topic["latest_incidence"]
            <= 1
            or not 0
            <= topic["previous_incidence"]
            <= 1
            or not -100
            <= topic["incidence_change_pp"]
            <= 100
        ):
            raise RuntimeError(
                "policy_agenda incidence range is invalid"
            )

        daily_activity = topic[
            "daily_activity"
        ]

        if (
            not isinstance(
                daily_activity,
                list,
            )
            or len(daily_activity)
            != POLICY_AGENDA_EVOLUTION_DAYS
        ):
            raise RuntimeError(
                "policy_agenda daily activity is invalid"
            )

        item_total = 0
        source_day_total = 0
        active_day_total = 0
        latest_topic_total = 0
        previous_topic_total = 0

        for expected_date, day in zip(
            expected_dates,
            daily_activity,
        ):
            if (
                not isinstance(day, dict)
                or set(day)
                != {
                    "date",
                    "item_count",
                    "source_day_count",
                    "accepted_source_day_count",
                    "incidence",
                }
                or day["date"]
                != expected_date
                or type(
                    day["item_count"]
                )
                is not int
                or day["item_count"] < 0
                or type(
                    day["source_day_count"]
                )
                is not int
                or day["source_day_count"] < 0
                or type(
                    day[
                        "accepted_source_day_count"
                    ]
                )
                is not int
                or day[
                    "accepted_source_day_count"
                ] < 0
                or day["source_day_count"]
                > day["item_count"]
                or day["source_day_count"]
                > day[
                    "accepted_source_day_count"
                ]
            ):
                raise RuntimeError(
                    "policy_agenda daily value is invalid"
                )

            accepted_count = (
                accepted_by_date[
                    expected_date
                ]
            )

            if (
                day[
                    "accepted_source_day_count"
                ]
                != accepted_count
            ):
                raise RuntimeError(
                    "policy_agenda daily denominator parity is invalid"
                )

            expected_incidence = (
                round(
                    day[
                        "source_day_count"
                    ]
                    / accepted_count,
                    6,
                )
                if accepted_count
                else 0.0
            )

            if (
                isinstance(
                    day["incidence"],
                    bool,
                )
                or not isinstance(
                    day["incidence"],
                    (int, float),
                )
                or day["incidence"]
                != expected_incidence
            ):
                raise RuntimeError(
                    "policy_agenda daily incidence is invalid"
                )

            item_total += day[
                "item_count"
            ]
            source_day_total += day[
                "source_day_count"
            ]
            active_day_total += (
                day["item_count"] > 0
            )

            current_date = date.fromisoformat(
                expected_date
            )

            if (
                latest_start
                <= current_date
                <= latest_end
            ):
                latest_topic_total += day[
                    "source_day_count"
                ]

            if (
                previous_start
                <= current_date
                <= previous_end
            ):
                previous_topic_total += day[
                    "source_day_count"
                ]

        if (
            item_total
            != topic["item_count"]
            or source_day_total
            != topic["source_day_count"]
            or active_day_total
            != topic["active_day_count"]
        ):
            raise RuntimeError(
                "policy_agenda evolution daily totals are inconsistent"
            )

        latest_denominator = sum(
            count
            for date_key, count
            in accepted_by_date.items()
            if (
                latest_start.isoformat()
                <= date_key
                <= latest_end.isoformat()
            )
        )

        previous_denominator = sum(
            count
            for date_key, count
            in accepted_by_date.items()
            if (
                previous_start.isoformat()
                <= date_key
                <= previous_end.isoformat()
            )
        )

        latest_ratio = (
            latest_topic_total
            / latest_denominator
            if latest_denominator
            else 0.0
        )
        previous_ratio = (
            previous_topic_total
            / previous_denominator
            if previous_denominator
            else 0.0
        )

        if (
            topic[
                "latest_source_day_count"
            ]
            != latest_topic_total
            or topic[
                "previous_source_day_count"
            ]
            != previous_topic_total
            or topic["latest_incidence"]
            != round(
                latest_ratio,
                6,
            )
            or topic[
                "previous_incidence"
            ]
            != round(
                previous_ratio,
                6,
            )
            or topic[
                "incidence_change_pp"
            ]
            != round(
                (
                    latest_ratio
                    - previous_ratio
                )
                * 100,
                3,
            )
        ):
            raise RuntimeError(
                "policy_agenda comparison incidence is inconsistent"
            )

        matched_terms = topic[
            "matched_term_counts"
        ]
        allowed_terms = set(
            taxonomy[topic_id][
                "terms"
            ]
        )

        if not isinstance(
            matched_terms,
            list,
        ):
            raise RuntimeError(
                "policy_agenda matched term counts are invalid"
            )

        names = []
        matched_order = []

        for item in matched_terms:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"term", "item_count"}
                or item["term"]
                not in allowed_terms
                or type(
                    item["item_count"]
                )
                is not int
                or item["item_count"] < 1
                or item["item_count"]
                > topic["item_count"]
            ):
                raise RuntimeError(
                    "policy_agenda matched term count is invalid"
                )

            names.append(item["term"])
            matched_order.append(
                (
                    -item["item_count"],
                    item["term"],
                )
            )

        if (
            len(names)
            != len(set(names))
            or matched_order
            != sorted(matched_order)
        ):
            raise RuntimeError(
                "policy_agenda matched term ordering is invalid"
            )

        ordering.append(
            (
                not topic[
                    "display_eligible"
                ],
                -topic[
                    "source_day_count"
                ],
                -topic["item_count"],
                topic["label"],
            )
        )

    if evolution_ids != agenda_ids:
        raise RuntimeError(
            "policy_agenda evolution topics do not match agenda topics"
        )

    if ordering != sorted(ordering):
        raise RuntimeError(
            "policy_agenda evolution topic order is invalid"
        )


def validate_policy_agenda(
    policy_agenda: Any,
    relevant_news: Any,
) -> None:
    """Validate the multi-label Policy Agenda public contract."""

    required = {
        "window_days",
        "input_item_count",
        "classified_item_count",
        "unclassified_item_count",
        "label_assignment_count",
        "method",
        "display_min_source_days",
        "evolution",
        "topics",
    }

    if (
        not isinstance(
            policy_agenda,
            dict,
        )
        or set(policy_agenda)
        != required
    ):
        raise RuntimeError(
            "policy_agenda has unexpected fields"
        )

    if not isinstance(
        relevant_news,
        list,
    ):
        raise RuntimeError(
            "policy_agenda relevant_news input is invalid"
        )

    if (
        policy_agenda["method"]
        != "accepted_relevant_news_by_policy_issue_multilabel"
    ):
        raise RuntimeError(
            "policy_agenda method is invalid"
        )

    for field in (
        "window_days",
        "input_item_count",
        "classified_item_count",
        "unclassified_item_count",
        "label_assignment_count",
        "display_min_source_days",
    ):
        if (
            type(
                policy_agenda[field]
            )
            is not int
            or policy_agenda[field] < 0
        ):
            raise RuntimeError(
                "policy_agenda counts are invalid"
            )

    if (
        policy_agenda[
            "window_days"
        ] < 1
        or policy_agenda[
            "display_min_source_days"
        ]
        != POLICY_AGENDA_DISPLAY_MIN_SOURCE_DAYS
        or policy_agenda[
            "input_item_count"
        ]
        != len(relevant_news)
        or (
            policy_agenda[
                "classified_item_count"
            ]
            + policy_agenda[
                "unclassified_item_count"
            ]
        )
        != policy_agenda[
            "input_item_count"
        ]
        or policy_agenda[
            "classified_item_count"
        ]
        > policy_agenda[
            "input_item_count"
        ]
        or policy_agenda[
            "label_assignment_count"
        ]
        < policy_agenda[
            "classified_item_count"
        ]
    ):
        raise RuntimeError(
            "policy_agenda coverage counts are inconsistent"
        )

    topics = policy_agenda[
        "topics"
    ]

    if (
        not isinstance(topics, list)
        or len(topics)
        > len(POLICY_AGENDA_TOPICS)
    ):
        raise RuntimeError(
            "policy_agenda topics is invalid"
        )

    seen_topic_ids: set[str] = set()
    supporting_ids: set[str] = set()
    topic_order = []

    for topic in topics:
        supporting_ids.update(
            validate_policy_agenda_topic(
                topic,
                seen_topic_ids,
            )
        )

        topic_order.append(
            (
                not topic[
                    "display_eligible"
                ],
                -topic[
                    "source_day_count"
                ],
                -topic["item_count"],
                topic["label"],
            )
        )

    if topic_order != sorted(topic_order):
        raise RuntimeError(
            "policy_agenda topic order is invalid"
        )

    if (
        sum(
            topic["item_count"]
            for topic in topics
        )
        != policy_agenda[
            "label_assignment_count"
        ]
    ):
        raise RuntimeError(
            "policy_agenda label assignment count is inconsistent"
        )

    if (
        policy_agenda[
            "classified_item_count"
        ] == 0
        and policy_agenda[
            "label_assignment_count"
        ] != 0
    ):
        raise RuntimeError(
            "policy_agenda empty classification is inconsistent"
        )

    relevant_ids = {
        str(item.get("id") or "")
        for item in relevant_news
        if isinstance(item, dict)
        and str(item.get("id") or "")
    }

    if not supporting_ids.issubset(
        relevant_ids
    ):
        raise RuntimeError(
            "policy_agenda evidence is not a subset of relevant_news"
        )

    validate_policy_agenda_evolution(
        policy_agenda["evolution"],
        topics,
        relevant_news,
    )

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
    validate_candidate_visibility(
        payload.get("candidate_visibility"),
        candidate_watch,
        generated_at,
    )
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

    campaign_agenda = payload.get(
        "campaign_agenda"
    )

    validate_campaign_agenda(
        campaign_agenda,
        relevant_news,
    )

    policy_agenda = payload.get(
        "policy_agenda"
    )

    validate_policy_agenda(
        policy_agenda,
        relevant_news,
    )

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
                "candidate_matches",
            }
            if list_name == "candidate_watch":
                required.add("coverage_scope")

            if set(item) != required:
                raise RuntimeError(
                    f"{list_name} item has unexpected fields"
                )

            if not item["headline"] or not item["publisher"]:
                raise RuntimeError(
                    f"{list_name} contains an empty headline or publisher"
                )
            validate_candidate_match_contract(
                item.get("candidates"),
                item.get("candidate_matches"),
                f"{list_name} item",
            )

            if list_name == "candidate_watch":
                coverage_scope = item.get("coverage_scope")
                if coverage_scope not in CANDIDATE_COVERAGE_SCOPES:
                    raise RuntimeError(
                        "candidate_watch contains an invalid coverage_scope"
                    )
                if (
                    (coverage_scope == "election")
                    != bool(item["explicit_election"])
                ):
                    raise RuntimeError(
                        "candidate_watch election scope is inconsistent"
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
            "candidate_matches",
            "relevance_reason",
            "relevance_terms",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError("relevant_news item has unexpected fields")
        validate_candidate_match_contract(
            item.get("candidates"),
            item.get("candidate_matches"),
            "relevant_news item",
        )
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
            "candidate_matches",
            "development_category",
            "development_label",
            "matched_terms",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError("notable_developments item has unexpected fields")
        validate_candidate_match_contract(
            item.get("candidates"),
            item.get("candidate_matches"),
            "notable_developments item",
        )
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
    candidacy_status_path: Path | str = CANDIDACY_STATUS_SOURCE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    elif generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    else:
        generated_at = generated_at.astimezone(timezone.utc)

    window_start = generated_at - timedelta(days=window_days)
    candidacy_payload = load_candidate_candidacy_status(candidacy_status_path)
    candidate_roster = candidate_roster_metadata(candidacy_payload)
    candidates = candidate_roster["names"]
    candidate_set = set(candidates)
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
        entry["candidate_matches"] = match_news_candidates(
            normalized_headline,
            normalized_summary,
            candidates,
        )
        entry["candidate_names"] = candidate_names_from_matches(
            entry["candidate_matches"]
        )
        relevance = classify_relevant_news(
            entry["headline"],
            entry.get("summary") or "",
            entry["candidate_names"],
            entry["candidate_matches"],
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
        candidates,
    )

    excluded_urls = load_news_exclusions()
    existing_inventory, all_entries = apply_news_exclusions(
        existing_inventory,
        all_entries,
        excluded_urls,
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
        candidate_matches = [
            match
            for match in entry.get("candidate_matches", [])
            if match.get("candidate") in candidate_set
        ]
        matched_candidates = candidate_names_from_matches(
            candidate_matches
        )
        normalized_headline = normalize(entry["headline"])
        normalized_summary = normalize(entry.get("summary") or "")

        # Retained inventory provenance cannot bypass current scope rules.
        # The record remains in the raw rolling inventory for continuity,
        # but an unanchored foreign presidential story enters no public lane.
        if (
            unanchored_presidential_context(
                normalized_headline,
                normalized_summary,
                matched_candidates,
            )
            and not bounded_current_french_race_context(
                normalized_headline,
                normalized_summary,
            )
        ):
            continue

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
            candidate_matches,
        )

        relevance = None
        if entry.get("relevance_reason"):
            relevance = {
                "reason": entry["relevance_reason"],
                "matched_terms": list(entry.get("relevance_terms", [])),
            }
        else:
            relevance = classify_relevant_news(
                entry["headline"],
                entry.get("summary") or "",
                matched_candidates,
                candidate_matches,
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
            candidate_matches,
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
                    candidate_matches,
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
                    candidate_matches,
                    is_election_news,
                    relevance,
                )
            )

        if matched_candidates:
            candidate_item = dict(base_item)
            candidate_item["coverage_scope"] = (
                classify_candidate_coverage_scope(
                    is_election_news=is_election_news,
                    relevance=relevance,
                    development=development,
                )
            )
            candidate_watch.append(candidate_item)

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
        notable_developments,
        generated_at,
    )

    policy_relevant_news = (
        build_policy_analysis_input(
            relevant_news,
            list(deduplicated.values()),
        )
    )

    policy_agenda = build_policy_agenda(
        policy_relevant_news,
        window_days,
        generated_at,
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
        "candidate_roster": candidate_roster,
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
        "policy_agenda": policy_agenda,
        "candidate_visibility": build_candidate_visibility(
            candidate_watch,
            generated_at,
        ),
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
        "--candidacy-status",
        type=Path,
        default=Path(CANDIDACY_STATUS_SOURCE),
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
        candidacy_status_path=arguments.candidacy_status,
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
