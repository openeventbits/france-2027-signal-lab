"""Frozen-source migration contract for the FR27 French polling cutover.

This module is intentionally not wired into the production polling fetch.  It
provides the reviewed, source-independent reconciliation key, strict migration
registry validation, frozen MediaWiki fixture parsing, and second-round
continuity helpers needed before the live source is changed.
"""

from __future__ import annotations

import copy
import io
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import pandas as pd
from lxml import html as lxml_html

from fetch_polls import (
    SECOND_ROUND,
    canonical_candidate_name,
    canonical_pollster_name,
    cell_link,
    cell_text,
    candidate_name,
    parse_fieldwork,
    parse_sample_size,
    parse_score,
    parse_wikipedia_first_round_html,
    validate_second_round_event,
)
from poll_contract import FIRST_ROUND, normalize_identity


DEFAULT_MIGRATION_REGISTRY = Path(__file__).with_name(
    "fr27_poll_migration_registry.json"
)
FROZEN_FIXTURE_DIRECTORY = Path(__file__).with_name("test_fixtures") / "fr27_polling"
ENGLISH_FIXTURE = FROZEN_FIXTURE_DIRECTORY / "en_mediawiki_1371070883.json"
FRENCH_FIXTURE = FROZEN_FIXTURE_DIRECTORY / "fr_mediawiki_238906992.json"

AUDITED_FRENCH_RUNOFF_HEADINGS = (
    "hypothese attal le pen",
    "hypothese glucksmann le pen",
    "hypothese melenchon le pen",
    "hypothese philippe le pen",
    "hypothese retailleau le pen",
    "hypothese ruffin le pen",
    "hypothese attal bardella",
    "hypothese glucksmann bardella",
    "hypothese melenchon bardella",
    "hypothese philippe bardella",
    "hypothese retailleau bardella",
)
POST_AUDIT_HOLLANDE_LE_PEN_HEADING = "hypothese hollande le pen"
POST_AUDIT_HOLLANDE_LE_PEN_LOCATOR = "FR-POST-HOLLANDE-LE-PEN"

ALLOWED_ROUNDS = {FIRST_ROUND, SECOND_ROUND}
ALLOWED_SAMPLE_SCOPES = {
    "adult_population",
    "matchup_respondents",
    "registered_voters",
    "reported",
    "survey_respondents",
}
ALLOWED_TREATMENTS = {
    "add_new",
    "preserve_historical",
    "retain_id_reviewed_correction",
    "retain_id_source_refresh",
    "skip_fail_closed",
}

GENERIC_CANDIDATE_MARKERS = {
    "autre",
    "autres",
    "candidat",
    "candidat eelv",
    "candidat ens",
    "candidat epr",
    "candidat lr",
    "candidat ps dvg",
    "candidat ps pp",
    "candidat rn",
}
AMBIGUOUS_CANDIDATE_LABELS = {
    "bardella le pen",
    "bardella ou le pen",
}

MIGRATION_CANDIDATE_NAMES = (
    "Anne Hidalgo",
    "Bernard Cazeneuve",
    "Bruno Le Maire",
    "Bruno Retailleau",
    "Carole Delga",
    "Cyril Hanouna",
    "David Lisnard",
    "Dominique de Villepin",
    "Emmanuel Macron",
    "Fabien Roussel",
    "François Bayrou",
    "François Hollande",
    "François Ruffin",
    "Gabriel Attal",
    "Gérald Darmanin",
    "Jean Castex",
    "Jean Lassalle",
    "Jean-Luc Mélenchon",
    "Jordan Bardella",
    "Laurent Wauquiez",
    "Marine Le Pen",
    "Marine Tondelier",
    "Michel Barnier",
    "Michel-Édouard Leclerc",
    "Nathalie Arthaud",
    "Nicolas Dupont-Aignan",
    "Olivier Faure",
    "Philippe Poutou",
    "Philippe de Villiers",
    "Patrick Sébastien",
    "Raphaël Glucksmann",
    "Sandrine Rousseau",
    "Sarah Knafo",
    "Sébastien Lecornu",
    "Teddy Riner",
    "Xavier Bertrand",
    "Yaël Braun-Pivet",
    "Yannick Jadot",
    "Édouard Philippe",
    "Élisabeth Borne",
    "Éric Zemmour",
    "Valérie Pécresse",
)


def _identity_slug(value: str) -> str:
    normalized = normalize_identity(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if not slug:
        raise ValueError(f"identity cannot be normalized: {value!r}")
    return slug


_CANDIDATE_ALIASES: dict[str, str] = {}
for _full_name in MIGRATION_CANDIDATE_NAMES:
    _CANDIDATE_ALIASES[normalize_identity(_full_name)] = _full_name
    surname = _full_name.split()[-1]
    surname_key = normalize_identity(surname)
    if surname_key not in _CANDIDATE_ALIASES:
        _CANDIDATE_ALIASES[surname_key] = _full_name

_CANDIDATE_ALIASES.update(
    {
        normalize_identity("Attal"): "Gabriel Attal",
        normalize_identity("Bardella"): "Jordan Bardella",
        normalize_identity("Dupont Aignan"): "Nicolas Dupont-Aignan",
        normalize_identity("de Villepin"): "Dominique de Villepin",
        normalize_identity("de Villiers"): "Philippe de Villiers",
        normalize_identity("Glucksmann"): "Raphaël Glucksmann",
        normalize_identity("Le Pen"): "Marine Le Pen",
        normalize_identity("Leclerc"): "Michel-Édouard Leclerc",
        normalize_identity("Melenchon"): "Jean-Luc Mélenchon",
        normalize_identity("Philippe"): "Édouard Philippe",
        normalize_identity("Hanouna"): "Cyril Hanouna",
        normalize_identity("Riner"): "Teddy Riner",
        normalize_identity("Sébastien"): "Patrick Sébastien",
        normalize_identity("Retailleau"): "Bruno Retailleau",
        normalize_identity("Ruffin"): "François Ruffin",
        normalize_identity("Villepin"): "Dominique de Villepin",
    }
)


def reviewed_candidate_name(value: str) -> str:
    """Resolve only the finite, audited candidate-name set.

    Unlike the general production poll contract, migration reconciliation must
    not accept an unseen label merely because it is syntactically clean.
    """

    raw = candidate_name(value)
    key = normalize_identity(raw)
    if key in GENERIC_CANDIDATE_MARKERS or key in AMBIGUOUS_CANDIDATE_LABELS:
        raise ValueError(f"candidate is not uniquely identified: {value!r}")
    canonical = _CANDIDATE_ALIASES.get(key)
    if canonical is None:
        canonical = _CANDIDATE_ALIASES.get(
            normalize_identity(canonical_candidate_name(raw))
        )
    if canonical is None:
        raise ValueError(f"unreviewed candidate label: {value!r}")
    return canonical


def candidate_identity(value: str) -> str:
    return _identity_slug(reviewed_candidate_name(value))


def pollster_identity(value: str) -> str:
    cleaned = re.sub(r"\[[^]]*]", "", value).strip()
    normalized = normalize_identity(cleaned)
    reviewed = {
        "cluster 17": "cluster17",
        "cluster17": "cluster17",
        "harris": "harris-interactive",
        "harris interactive": "harris-interactive",
        "harris interactive toluna": "harris-interactive",
        "opinion way": "opinionway",
        "opinionway": "opinionway",
    }.get(normalized)
    return reviewed or _identity_slug(canonical_pollster_name(cleaned))


def _decimal_score(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError(f"score must be numeric: {value!r}")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"score must be an exact decimal: {value!r}") from error
    if not decimal.is_finite() or not Decimal("0") <= decimal <= Decimal("100"):
        raise ValueError(f"score is outside 0..100: {value!r}")
    rendered = format(decimal, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


@dataclass(frozen=True, order=True)
class FactualKey:
    round: str
    pollster_identity: str
    fieldwork_start: str
    fieldwork_end: str
    sample_size: int
    sample_scope: str
    candidates: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "pollster_identity": self.pollster_identity,
            "fieldwork_start": self.fieldwork_start,
            "fieldwork_end": self.fieldwork_end,
            "sample_size": self.sample_size,
            "sample_scope": self.sample_scope,
            "candidates": [
                {"candidate_id": candidate_id, "score": score}
                for candidate_id, score in self.candidates
            ],
        }


@dataclass(frozen=True, order=True)
class ReviewAnchor:
    round: str
    pollster_identity: str
    fieldwork_start: str
    fieldwork_end: str
    candidate_ids: tuple[str, ...]


def _valid_iso_date(value: object, context: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{context} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{context} must be a valid date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{context} must use canonical YYYY-MM-DD")
    return value


def exact_factual_key(
    event: dict[str, Any],
    *,
    sample_scope: str | None = None,
    reviewed_pollster: str | None = None,
) -> FactualKey:
    """Return the audited source-independent exact factual key.

    ``source_url`` is intentionally ignored.  Callers must explicitly provide
    sample scope when the event does not carry it; silently guessing the base
    would reintroduce the sample ambiguities found in the audit.
    """

    round_name = event.get("round")
    if round_name not in ALLOWED_ROUNDS:
        raise ValueError(f"unsupported polling round: {round_name!r}")
    start = _valid_iso_date(event.get("fieldwork_start"), "fieldwork_start")
    end = _valid_iso_date(event.get("fieldwork_end"), "fieldwork_end")
    if start > end:
        raise ValueError("fieldwork_start must not exceed fieldwork_end")
    size = event.get("sample_size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("sample_size must be a positive integer")
    scope = sample_scope if sample_scope is not None else event.get("sample_scope")
    if scope not in ALLOWED_SAMPLE_SCOPES:
        raise ValueError(f"unsupported or missing sample_scope: {scope!r}")
    candidates = event.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    expected_count = 2 if round_name == SECOND_ROUND else 3
    if len(candidates) < expected_count or (
        round_name == SECOND_ROUND and len(candidates) != 2
    ):
        raise ValueError("factual key has an invalid candidate count")

    normalized_candidates = sorted(
        (
            candidate_identity(str(candidate.get("name", ""))),
            _decimal_score(candidate.get("score")),
        )
        for candidate in candidates
        if isinstance(candidate, dict)
    )
    if len(normalized_candidates) != len(candidates):
        raise ValueError("candidate entries must be objects")
    candidate_ids = [item[0] for item in normalized_candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("factual key has duplicate candidate identities")
    reviewed_identity = (
        _identity_slug(reviewed_pollster)
        if reviewed_pollster is not None
        else pollster_identity(str(event.get("pollster", "")))
    )
    return FactualKey(
        round=round_name,
        pollster_identity=reviewed_identity,
        fieldwork_start=start,
        fieldwork_end=end,
        sample_size=size,
        sample_scope=scope,
        candidates=tuple(normalized_candidates),
    )


def review_anchor(
    event: dict[str, Any], *, reviewed_pollster: str | None = None
) -> ReviewAnchor:
    """Return a weak lookup anchor; this value is never an auto-merge key."""

    round_name = event.get("round")
    if round_name not in ALLOWED_ROUNDS:
        raise ValueError(f"unsupported polling round: {round_name!r}")
    start = _valid_iso_date(event.get("fieldwork_start"), "fieldwork_start")
    end = _valid_iso_date(event.get("fieldwork_end"), "fieldwork_end")
    candidates = event.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise ValueError("review anchor requires candidates")
    candidate_ids = tuple(
        sorted(candidate_identity(str(candidate.get("name", ""))) for candidate in candidates)
    )
    return ReviewAnchor(
        round=round_name,
        pollster_identity=(
            _identity_slug(reviewed_pollster)
            if reviewed_pollster is not None
            else pollster_identity(str(event.get("pollster", "")))
        ),
        fieldwork_start=start,
        fieldwork_end=end,
        candidate_ids=candidate_ids,
    )


def factual_key_from_dict(value: object, context: str) -> FactualKey:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    expected = {
        "round",
        "pollster_identity",
        "fieldwork_start",
        "fieldwork_end",
        "sample_size",
        "sample_scope",
        "candidates",
    }
    if set(value) != expected:
        raise ValueError(
            f"{context} fields must equal {sorted(expected)}; got {sorted(value)}"
        )
    pollster = value["pollster_identity"]
    if not isinstance(pollster, str) or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", pollster
    ):
        raise ValueError(f"{context}.pollster_identity is malformed")
    start = _valid_iso_date(value["fieldwork_start"], f"{context}.fieldwork_start")
    end = _valid_iso_date(value["fieldwork_end"], f"{context}.fieldwork_end")
    if start > end:
        raise ValueError(f"{context} has reversed fieldwork dates")
    size = value["sample_size"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError(f"{context}.sample_size must be a positive integer")
    scope = value["sample_scope"]
    if scope not in ALLOWED_SAMPLE_SCOPES:
        raise ValueError(f"{context}.sample_scope is unsupported")
    round_name = value["round"]
    if round_name not in ALLOWED_ROUNDS:
        raise ValueError(f"{context}.round is unsupported")
    raw_candidates = value["candidates"]
    if not isinstance(raw_candidates, list):
        raise ValueError(f"{context}.candidates must be a list")
    candidates: list[tuple[str, str]] = []
    for index, candidate in enumerate(raw_candidates):
        candidate_context = f"{context}.candidates[{index}]"
        if not isinstance(candidate, dict) or set(candidate) != {
            "candidate_id",
            "score",
        }:
            raise ValueError(f"{candidate_context} is malformed")
        candidate_id = candidate["candidate_id"]
        if not isinstance(candidate_id, str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate_id
        ):
            raise ValueError(f"{candidate_context}.candidate_id is malformed")
        score = candidate["score"]
        if not isinstance(score, str) or _decimal_score(score) != score:
            raise ValueError(f"{candidate_context}.score is not canonical")
        candidates.append((candidate_id, score))
    if candidates != sorted(candidates):
        raise ValueError(f"{context}.candidates must be deterministically sorted")
    if len({candidate_id for candidate_id, _ in candidates}) != len(candidates):
        raise ValueError(f"{context} has duplicate candidate identities")
    if round_name == SECOND_ROUND and len(candidates) != 2:
        raise ValueError(f"{context} second round must contain exactly two candidates")
    if round_name == FIRST_ROUND and len(candidates) < 3:
        raise ValueError(f"{context} first round must contain at least three candidates")
    return FactualKey(
        round=round_name,
        pollster_identity=pollster,
        fieldwork_start=start,
        fieldwork_end=end,
        sample_size=size,
        sample_scope=scope,
        candidates=tuple(candidates),
    )


def _http_url(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be an HTTP(S) URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{context} must be an HTTP(S) URL")
    return value


def _validate_source_revision(value: object, context: str) -> None:
    if not isinstance(value, dict) or set(value) != {
        "revision_id",
        "page_url",
        "fixture",
        "fixture_sha256",
    }:
        raise ValueError(f"{context} is malformed")
    if isinstance(value["revision_id"], bool) or not isinstance(value["revision_id"], int):
        raise ValueError(f"{context}.revision_id must be an integer")
    _http_url(value["page_url"], f"{context}.page_url")
    if not isinstance(value["fixture"], str) or not value["fixture"].strip():
        raise ValueError(f"{context}.fixture must be a non-empty path")
    if not isinstance(value["fixture_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["fixture_sha256"]
    ):
        raise ValueError(f"{context}.fixture_sha256 must be lowercase SHA-256")


def _validate_field_decisions(
    decisions: object,
    old_key: FactualKey,
    incoming_key: FactualKey,
    canonical_key: FactualKey,
    context: str,
) -> None:
    if not isinstance(decisions, dict) or not decisions:
        raise ValueError(f"{context} requires non-empty field_decisions")
    allowed = {
        "pollster_identity",
        "fieldwork_start",
        "fieldwork_end",
        "sample_size",
        "sample_scope",
        "candidates",
    }
    for field, decision in decisions.items():
        if field not in allowed:
            raise ValueError(f"{context}.{field} is unsupported")
        if not isinstance(decision, dict) or set(decision) != {
            "old",
            "incoming",
            "canonical",
        }:
            raise ValueError(f"{context}.{field} is malformed")
        old_value = getattr(old_key, field)
        incoming_value = getattr(incoming_key, field)
        canonical_value = getattr(canonical_key, field)
        normalized = {
            "old": old_value,
            "incoming": incoming_value,
            "canonical": canonical_value,
        }
        for side in ("old", "incoming", "canonical"):
            value = decision[side]
            if field == "candidates":
                value = tuple(
                    (item["candidate_id"], item["score"])
                    for item in value
                ) if isinstance(value, list) else value
            if value != normalized[side]:
                raise ValueError(
                    f"{context}.{field}.{side} contradicts its factual key"
                )
        if old_value == incoming_value == canonical_value:
            raise ValueError(f"{context}.{field} does not describe a disagreement")


def validate_migration_registry(payload: object) -> dict[str, Any]:
    """Validate the dedicated migration registry and fail closed on ambiguity."""

    if not isinstance(payload, dict):
        raise ValueError("migration registry must be an object")
    expected_top = {
        "schema_version",
        "source_revisions",
        "acceptance",
        "wave_scoped_pollster_aliases",
        "source_only_identity_migrations",
        "reviewed_reconciliations",
        "persistence_obligations",
        "french_additions",
        "fail_closed",
        "identity_skips",
    }
    if set(payload) != expected_top:
        raise ValueError(
            "migration registry top-level fields are malformed: "
            f"{sorted(set(payload) ^ expected_top)}"
        )
    if payload.get("schema_version") != "1.0":
        raise ValueError("migration registry schema_version must equal 1.0")
    revisions = payload.get("source_revisions")
    if not isinstance(revisions, dict) or set(revisions) != {"english", "french"}:
        raise ValueError("source_revisions must contain English and French")
    for language, revision in revisions.items():
        _validate_source_revision(revision, f"source_revisions.{language}")

    acceptance = payload.get("acceptance")
    required_acceptance = {
        "current_first_round_preserved": 203,
        "current_second_round_preserved": 38,
        "french_new_first_round": 29,
        "french_new_second_round": 12,
        "source_only_migrations": 102,
        "reviewed_reconciliation_mappings": 73,
        "unexplained_historical_losses": 0,
        "unresolved_accepted_identity_ambiguities": 0,
        "duplicate_canonical_factual_identities": 0,
        "fail_closed_french_rows": 8,
    }
    if acceptance != required_acceptance:
        raise ValueError("migration registry acceptance table is not the audited gate")

    aliases = payload.get("wave_scoped_pollster_aliases")
    if not isinstance(aliases, list):
        raise ValueError("wave_scoped_pollster_aliases must be a list")
    alias_scopes: set[tuple[Any, ...]] = set()
    for index, alias in enumerate(aliases):
        context = f"wave_scoped_pollster_aliases[{index}]"
        if not isinstance(alias, dict) or set(alias) != {
            "reported",
            "canonical_identity",
            "fieldwork_start",
            "fieldwork_end",
            "sample_size",
            "evidence_urls",
            "review_reason",
        }:
            raise ValueError(f"{context} is malformed")
        key = (
            normalize_identity(str(alias["reported"])),
            _valid_iso_date(alias["fieldwork_start"], f"{context}.fieldwork_start"),
            _valid_iso_date(alias["fieldwork_end"], f"{context}.fieldwork_end"),
            alias["sample_size"],
        )
        if key in alias_scopes:
            raise ValueError(f"duplicate wave-scoped pollster alias: {key}")
        alias_scopes.add(key)
        if not isinstance(alias["canonical_identity"], str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", alias["canonical_identity"]
        ):
            raise ValueError(f"{context}.canonical_identity is malformed")
        if isinstance(alias["sample_size"], bool) or not isinstance(alias["sample_size"], int) or alias["sample_size"] <= 0:
            raise ValueError(f"{context}.sample_size must be positive")
        _validate_evidence(alias, context)

    legacy_ids: set[str] = set()
    retained_by_locator: dict[str, str] = {}
    canonical_to_retained: dict[FactualKey, str] = {}
    mapping_locators: set[str] = set()
    for section_name, reviewed in (
        ("source_only_identity_migrations", False),
        ("reviewed_reconciliations", True),
    ):
        records = payload.get(section_name)
        if not isinstance(records, list):
            raise ValueError(f"{section_name} must be a list")
        for index, record in enumerate(records):
            context = f"{section_name}[{index}]"
            required = {
                "legacy_event_id",
                "retained_event_id",
                "incoming_source_locator",
                "treatment",
                "old_factual_key",
                "incoming_factual_key",
                "canonical_factual_key",
                "legacy_source_url",
                "incoming_source_url",
                "evidence_urls",
                "review_reason",
            }
            if reviewed:
                required.add("field_decisions")
            if not isinstance(record, dict) or set(record) != required:
                raise ValueError(f"{context} is malformed")
            legacy_id = record["legacy_event_id"]
            retained_id = record["retained_event_id"]
            for field, value in (
                ("legacy_event_id", legacy_id),
                ("retained_event_id", retained_id),
            ):
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                    raise ValueError(f"{context}.{field} must be a SHA-256 identity")
            if legacy_id in legacy_ids:
                raise ValueError(f"duplicate legacy event ID: {legacy_id}")
            legacy_ids.add(legacy_id)
            locator = record["incoming_source_locator"]
            if not isinstance(locator, str) or not re.fullmatch(
                r"FR-(?:T\d+R\d+|R\d+r\d+)", locator
            ):
                raise ValueError(f"{context}.incoming_source_locator is malformed")
            prior_retained = retained_by_locator.get(locator)
            if prior_retained is not None and prior_retained != retained_id:
                raise ValueError(
                    f"incoming mapping {locator} maps to multiple retained IDs"
                )
            if locator in mapping_locators:
                raise ValueError(f"ambiguous source locator: {locator}")
            mapping_locators.add(locator)
            retained_by_locator[locator] = retained_id
            treatment = record["treatment"]
            expected_treatment = (
                "retain_id_reviewed_correction"
                if reviewed
                else "retain_id_source_refresh"
            )
            if treatment not in ALLOWED_TREATMENTS or treatment != expected_treatment:
                raise ValueError(f"{context}.treatment is unsupported")
            old_key = factual_key_from_dict(record["old_factual_key"], f"{context}.old_factual_key")
            incoming_key = factual_key_from_dict(
                record["incoming_factual_key"], f"{context}.incoming_factual_key"
            )
            canonical_key = factual_key_from_dict(
                record["canonical_factual_key"], f"{context}.canonical_factual_key"
            )
            if reviewed:
                _validate_field_decisions(
                    record["field_decisions"],
                    old_key,
                    incoming_key,
                    canonical_key,
                    f"{context}.field_decisions",
                )
            elif not (old_key == incoming_key == canonical_key):
                raise ValueError(f"{context} source-only keys must be identical")
            if canonical_key in canonical_to_retained:
                raise ValueError("duplicate canonical mapping")
            canonical_to_retained[canonical_key] = retained_id
            _http_url(record["legacy_source_url"], f"{context}.legacy_source_url")
            _http_url(record["incoming_source_url"], f"{context}.incoming_source_url")
            _validate_evidence(record, context)

    persistence = payload.get("persistence_obligations")
    if not isinstance(persistence, dict) or set(persistence) != {
        "first_round",
        "second_round",
    }:
        raise ValueError("persistence_obligations is malformed")
    persistence_ids: set[str] = set()
    for round_name, expected_count in (("first_round", 44), ("second_round", 2)):
        records = persistence[round_name]
        if not isinstance(records, list) or len(records) != expected_count:
            raise ValueError(f"persistence_obligations.{round_name} has wrong count")
        for index, record in enumerate(records):
            context = f"persistence_obligations.{round_name}[{index}]"
            if not isinstance(record, dict) or set(record) != {
                "event_id",
                "treatment",
                "evidence_urls",
                "review_reason",
            }:
                raise ValueError(f"{context} is malformed")
            event_id = record["event_id"]
            if not isinstance(event_id, str) or not re.fullmatch(r"[0-9a-f]{64}", event_id):
                raise ValueError(f"{context}.event_id is malformed")
            if event_id in persistence_ids:
                raise ValueError(f"duplicate persistence event ID: {event_id}")
            persistence_ids.add(event_id)
            if record["treatment"] != "preserve_historical":
                raise ValueError(f"{context}.treatment is unsupported")
            _validate_evidence(record, context)

    addition_locators: set[str] = set()
    additions = payload.get("french_additions")
    if not isinstance(additions, dict) or set(additions) != {
        "first_round",
        "second_round",
    }:
        raise ValueError("french_additions is malformed")
    for round_name, expected_count in (("first_round", 29), ("second_round", 12)):
        records = additions[round_name]
        if not isinstance(records, list) or len(records) != expected_count:
            raise ValueError(f"french_additions.{round_name} has wrong count")
        for index, record in enumerate(records):
            context = f"french_additions.{round_name}[{index}]"
            if not isinstance(record, dict) or set(record) != {
                "source_locator",
                "treatment",
                "factual_key",
                "source_url",
                "evidence_urls",
                "review_reason",
            }:
                raise ValueError(f"{context} is malformed")
            locator = record["source_locator"]
            if not isinstance(locator, str) or not re.fullmatch(
                r"FR-(?:T\d+R\d+|R\d+r\d+)", locator
            ):
                raise ValueError(f"{context}.source_locator is malformed")
            if locator in addition_locators or locator in mapping_locators:
                raise ValueError(f"ambiguous source locator: {locator}")
            addition_locators.add(locator)
            if record["treatment"] != "add_new":
                raise ValueError(f"{context}.treatment is unsupported")
            key = factual_key_from_dict(record["factual_key"], f"{context}.factual_key")
            if key.round != round_name:
                raise ValueError(f"{context}.factual_key round contradicts section")
            if key in canonical_to_retained:
                raise ValueError(f"{context}.factual_key duplicates a canonical mapping")
            canonical_to_retained[key] = f"new:{locator}"
            _http_url(record["source_url"], f"{context}.source_url")
            _validate_evidence(record, context)

    fail_closed = payload.get("fail_closed")
    if not isinstance(fail_closed, list) or len(fail_closed) != 8:
        raise ValueError("fail_closed must contain the eight audited rows")
    fail_locators: set[str] = set()
    for index, record in enumerate(fail_closed):
        context = f"fail_closed[{index}]"
        if not isinstance(record, dict) or set(record) != {
            "source_locator",
            "reason_code",
            "treatment",
            "evidence_urls",
            "review_reason",
        }:
            raise ValueError(f"{context} is malformed")
        locator = record["source_locator"]
        if not isinstance(locator, str) or not re.fullmatch(r"FR-T\d+R\d+", locator):
            raise ValueError(f"{context}.source_locator is malformed")
        if locator in fail_locators or locator in mapping_locators or locator in addition_locators:
            raise ValueError(f"ambiguous source locator: {locator}")
        fail_locators.add(locator)
        if record["treatment"] != "skip_fail_closed":
            raise ValueError(f"{context}.treatment is unsupported")
        if record["reason_code"] not in {"censored_score", "unnamed_generic_candidate"}:
            raise ValueError(f"{context}.reason_code is unsupported")
        _validate_evidence(record, context)

    identity_skips = payload.get("identity_skips")
    if not isinstance(identity_skips, list) or len(identity_skips) != 3:
        raise ValueError("identity_skips must contain the three audited ambiguous rows")
    for index, record in enumerate(identity_skips):
        context = f"identity_skips[{index}]"
        if not isinstance(record, dict) or set(record) != {
            "source_locator",
            "reason_code",
            "treatment",
            "evidence_urls",
            "review_reason",
        }:
            raise ValueError(f"{context} is malformed")
        locator = record["source_locator"]
        if not isinstance(locator, str) or not re.fullmatch(r"FR-T\d+R\d+", locator):
            raise ValueError(f"{context}.source_locator is malformed")
        if locator in fail_locators or locator in mapping_locators or locator in addition_locators:
            raise ValueError(f"ambiguous source locator: {locator}")
        fail_locators.add(locator)
        if record["treatment"] != "skip_fail_closed":
            raise ValueError(f"{context}.treatment is unsupported")
        if record["reason_code"] != "ambiguous_candidate_identity":
            raise ValueError(f"{context}.reason_code is unsupported")
        _validate_evidence(record, context)

    if len(payload["source_only_identity_migrations"]) != 102:
        raise ValueError("source-only migration count must equal 102")
    if len(payload["reviewed_reconciliations"]) != 73:
        raise ValueError("reviewed reconciliation count must equal 73")
    return payload


def _validate_evidence(record: dict[str, Any], context: str) -> None:
    reason = record.get("review_reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{context}.review_reason must be non-empty")
    evidence = record.get("evidence_urls")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{context}.evidence_urls must be non-empty")
    for index, url in enumerate(evidence):
        _http_url(url, f"{context}.evidence_urls[{index}]")


@lru_cache(maxsize=None)
def load_migration_registry(
    path: Path | str = DEFAULT_MIGRATION_REGISTRY,
) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load migration registry {source}: {error}") from error
    return validate_migration_registry(payload)


def apply_wave_scoped_pollster_alias(
    pollster: str,
    fieldwork_start: str,
    fieldwork_end: str,
    sample_size: int,
    registry: dict[str, Any],
) -> str:
    matches = [
        alias
        for alias in registry["wave_scoped_pollster_aliases"]
        if normalize_identity(alias["reported"]) == normalize_identity(pollster)
        and alias["fieldwork_start"] == fieldwork_start
        and alias["fieldwork_end"] == fieldwork_end
        and alias["sample_size"] == sample_size
    ]
    if len(matches) > 1:
        raise ValueError("ambiguous wave-scoped pollster alias")
    if not matches:
        return pollster_identity(pollster)
    return matches[0]["canonical_identity"]


def load_mediawiki_fixture(path: Path | str, expected_revision: int) -> dict[str, Any]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    parsed = payload.get("parse") if isinstance(payload, dict) else None
    if not isinstance(parsed, dict):
        raise ValueError(f"frozen fixture {source} lacks parse data")
    if parsed.get("revid") != expected_revision:
        raise ValueError(
            f"frozen fixture {source} has revision {parsed.get('revid')}, "
            f"expected {expected_revision}"
        )
    if not isinstance(parsed.get("text"), str):
        raise ValueError(f"frozen fixture {source} lacks rendered HTML")
    tocdata = parsed.get("tocdata")
    if not isinstance(tocdata, dict) or not isinstance(tocdata.get("sections"), list):
        raise ValueError(f"frozen fixture {source} lacks tocdata sections")
    return parsed


FRENCH_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}


def parse_french_fieldwork(value: str, *, default_year: int | None) -> tuple[str, str]:
    raw = re.sub(r"\[[^]]*]", "", value)
    raw = raw.replace("–", "-").replace("—", "-").replace("−", "-")
    raw = re.sub(r"\b1er\b", "1", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+", " ", raw).strip().casefold()
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(character)
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else default_year
    if year is None:
        raise ValueError(f"French fieldwork date lacks a year: {value!r}")
    normalized = re.sub(r"\b20\d{2}\b", "", normalized).strip()
    normalized = re.sub(r"^(?:du|le)\s+", "", normalized)
    normalized = normalized.replace(" au ", " - ")
    month_tokens = "|".join(FRENCH_MONTHS)
    across = re.fullmatch(
        rf"(\d{{1,2}})\s+({month_tokens})\s*-\s*(\d{{1,2}})\s+({month_tokens})",
        normalized,
    )
    if across:
        start_day, start_month, end_day, end_month = across.groups()
        start = date(year, FRENCH_MONTHS[start_month], int(start_day))
        end = date(year, FRENCH_MONTHS[end_month], int(end_day))
        if end < start:
            end = end.replace(year=year + 1)
        return start.isoformat(), end.isoformat()
    same_month = re.fullmatch(
        rf"(\d{{1,2}})\s*-\s*(\d{{1,2}})\s+({month_tokens})",
        normalized,
    )
    if same_month:
        start_day, end_day, month = same_month.groups()
        start = date(year, FRENCH_MONTHS[month], int(start_day))
        end = date(year, FRENCH_MONTHS[month], int(end_day))
        return start.isoformat(), end.isoformat()
    single = re.fullmatch(rf"(\d{{1,2}})\s+({month_tokens})", normalized)
    if single:
        day, month = single.groups()
        parsed = date(year, FRENCH_MONTHS[month], int(day))
        return parsed.isoformat(), parsed.isoformat()
    raise ValueError(f"unparsed French fieldwork date: {value!r}")


def _parse_french_score(value: object) -> float | None:
    """Parse the numeric prefix used by French cells with candidate links."""

    raw = re.sub(r"\[[^]]*]", "", cell_text(value)).strip()
    if normalize_identity(raw) in {"", "nan"} or raw in {"-", "–", "—", "−"}:
        return None
    if re.match(r"^<\s*\d", raw):
        raise ValueError(f"censored score: {raw}")
    match = re.match(r"^(\d+(?:[.,]\d+)?)", raw)
    if not match:
        raise ValueError(f"ambiguous score: {raw}")
    return float(match.group(1).replace(",", "."))


def _header_value(column: object) -> tuple[str, str | None]:
    levels = column if isinstance(column, tuple) else (column,)
    for level in reversed(levels):
        text = cell_text(level)
        link = cell_link(level)
        if text and not text.startswith("Unnamed:"):
            return text, link
    return "", None


def _candidate_from_link(link: str | None) -> str | None:
    if not link or "/wiki/" not in link:
        return None
    title = unquote(link.split("/wiki/", 1)[1]).replace("_", " ")
    title = re.sub(r" \(.*\)$", "", title)
    try:
        return reviewed_candidate_name(title)
    except ValueError:
        return None


def _header_candidate(column: object) -> tuple[str | None, bool]:
    text, link = _header_value(column)
    cleaned = candidate_name(text)
    normalized = normalize_identity(cleaned)
    if normalized in {"autre", "autres"}:
        return None, False
    if normalized in GENERIC_CANDIDATE_MARKERS:
        return None, True
    linked = _candidate_from_link(link)
    if linked:
        return linked, False
    try:
        return reviewed_candidate_name(cleaned), False
    except ValueError:
        return None, True


def _row_candidate(value: object, header_name: str | None, generic: bool) -> str:
    raw = cell_text(value)
    linked = _candidate_from_link(cell_link(value))
    if linked:
        return linked
    if not generic and header_name:
        return header_name
    suffix = re.sub(r"^[<>]?\s*\d+(?:[.,]\d+)?\s*", "", raw).strip()
    if not suffix:
        raise ValueError("unnamed generic candidate")
    return reviewed_candidate_name(suffix)


def _table_default_year(table: object) -> int | None:
    headings = table.xpath("preceding::*[self::h2 or self::h3 or self::h4]")
    for heading in reversed(headings):
        match = re.search(r"\b(20\d{2})\b", heading.text_content())
        if match:
            return int(match.group(1))
        if normalize_identity(heading.text_content()) == "autres":
            return None
    return None


def _preceding_heading(table: object) -> str:
    headings = table.xpath("preceding::*[self::h2 or self::h3 or self::h4]")
    return normalize_identity(headings[-1].text_content()) if headings else ""


def _french_runoff_table_plan(tables: list[object]) -> list[tuple[str, object]]:
    """Select reviewed runoff families without tying legacy locators to positions."""

    reviewed_headings = set(AUDITED_FRENCH_RUNOFF_HEADINGS) | {
        POST_AUDIT_HOLLANDE_LE_PEN_HEADING
    }
    by_heading: dict[str, object] = {}
    for table in tables:
        heading = _preceding_heading(table)
        if heading not in reviewed_headings:
            continue
        if heading in by_heading:
            raise ValueError(f"French runoff family {heading!r} exposes multiple tables")
        by_heading[heading] = table

    missing = [
        heading for heading in AUDITED_FRENCH_RUNOFF_HEADINGS if heading not in by_heading
    ]
    if missing:
        raise ValueError(f"French source lacks audited runoff tables: {missing}")

    plan = [
        (f"FR-R{family_index}", by_heading[heading])
        for family_index, heading in enumerate(AUDITED_FRENCH_RUNOFF_HEADINGS, start=1)
    ]
    if POST_AUDIT_HOLLANDE_LE_PEN_HEADING in by_heading:
        plan.insert(
            6,
            (
                POST_AUDIT_HOLLANDE_LE_PEN_LOCATOR,
                by_heading[POST_AUDIT_HOLLANDE_LE_PEN_HEADING],
            ),
        )
    return plan


def _frozen_record(
    *,
    locator: str,
    round_name: str,
    pollster: str,
    start: str,
    end: str,
    sample_size: int,
    candidates: list[dict[str, Any]],
    source_url: str,
) -> dict[str, Any]:
    return {
        "source_locator": locator,
        "round": round_name,
        "pollster": canonical_pollster_name(
            re.sub(r"\[[^]]*]", "", pollster).strip()
        ),
        "fieldwork_start": start,
        "fieldwork_end": end,
        "sample_size": sample_size,
        "sample_scope": "reported",
        "candidates": candidates,
        "source_url": source_url,
    }


def parse_french_frozen_fixture(parsed: dict[str, Any]) -> dict[str, Any]:
    """Parse the two audited French table families from frozen rendered HTML."""

    document = lxml_html.fromstring(parsed["text"])
    tables = document.xpath("//table")
    first_round: list[dict[str, Any]] = []
    second_round: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for table_index, table in enumerate(tables[:6]):
        frame = pd.read_html(
            io.StringIO(lxml_html.tostring(table, encoding="unicode")),
            extract_links="all",
        )[0]
        if len(frame.columns) < 6:
            continue
        default_year = _table_default_year(table)
        candidate_columns = [
            (index, *_header_candidate(column))
            for index, column in enumerate(frame.columns[3:], start=3)
        ]
        for row_index, row in frame.iterrows():
            locator = f"FR-T{table_index}R{row_index}"
            pollster = cell_text(row.iloc[0])
            fieldwork = cell_text(row.iloc[1])
            sample_size = parse_sample_size(cell_text(row.iloc[2]))
            source_url = cell_link(row.iloc[0])
            if not pollster or not fieldwork or sample_size is None or not source_url:
                continue
            try:
                start, end = parse_french_fieldwork(fieldwork, default_year=default_year)
            except ValueError:
                continue
            candidates: list[dict[str, Any]] = []
            candidate_links: dict[str, str | None] = {}
            rejection: str | None = None
            for column_index, header_name, generic in candidate_columns:
                raw_score = cell_text(row.iloc[column_index])
                normalized_score = raw_score.replace(",", ".").strip()
                if normalize_identity(normalized_score) in {"", "nan"} or normalized_score in {"-", "–", "—"}:
                    continue
                if re.match(r"^<\s*\d", normalized_score):
                    rejection = "censored_score"
                    break
                try:
                    score = _parse_french_score(row.iloc[column_index])
                except ValueError:
                    rejection = "censored_score"
                    break
                if score is None:
                    continue
                try:
                    name = _row_candidate(row.iloc[column_index], header_name, generic)
                except ValueError:
                    rejection = "unnamed_generic_candidate"
                    break
                candidate_id = candidate_identity(name)
                rendered_score: int | float = (
                    int(score) if score.is_integer() else score
                )
                existing = next(
                    (
                        item
                        for item in candidates
                        if candidate_identity(item["name"]) == candidate_id
                    ),
                    None,
                )
                row_link = cell_link(row.iloc[column_index])
                if existing is not None:
                    if (
                        existing["score"] == rendered_score
                        and row_link
                        and candidate_links[candidate_id] == row_link
                    ):
                        # A body-cell colspan is expanded by pandas into the
                        # candidate columns it covers.  Count that explicit
                        # linked person once, not once per covered header.
                        continue
                    raise ValueError(f"{locator} has contradictory duplicate candidates")
                candidates.append({"name": name, "score": rendered_score})
                candidate_links[candidate_id] = row_link
            if rejection:
                rejected.append(
                    {
                        "source_locator": locator,
                        "reason_code": rejection,
                        "pollster": canonical_pollster_name(
                            re.sub(r"\[[^]]*]", "", pollster).strip()
                        ),
                        "fieldwork_start": start,
                        "fieldwork_end": end,
                        "sample_size": sample_size,
                        "source_url": urljoin("https://fr.wikipedia.org", source_url),
                    }
                )
                continue
            if len(candidates) < 3:
                continue
            first_round.append(
                _frozen_record(
                    locator=locator,
                    round_name=FIRST_ROUND,
                    pollster=pollster,
                    start=start,
                    end=end,
                    sample_size=sample_size,
                    candidates=candidates,
                    source_url=urljoin("https://fr.wikipedia.org", source_url),
                )
            )

    for family_locator, table in _french_runoff_table_plan(tables):
        frame = pd.read_html(
            io.StringIO(lxml_html.tostring(table, encoding="unicode")),
            extract_links="all",
        )[0]
        candidate_columns = [
            (index, *_header_candidate(column))
            for index, column in enumerate(frame.columns[3:], start=3)
        ]
        resolved_headers = [name for _, name, generic in candidate_columns if name and not generic]
        if len(candidate_columns) != 2 or len(resolved_headers) != 2:
            raise ValueError(
                f"French runoff table {family_locator} has ambiguous headers"
            )
        for row_index, row in frame.iterrows():
            locator = f"{family_locator}r{row_index}"
            pollster = cell_text(row.iloc[0])
            fieldwork = cell_text(row.iloc[1])
            sample_size = parse_sample_size(cell_text(row.iloc[2]))
            source_url = cell_link(row.iloc[0])
            if not pollster or not fieldwork or sample_size is None or not source_url:
                continue
            try:
                start, end = parse_french_fieldwork(fieldwork, default_year=None)
            except ValueError:
                continue
            candidates: list[dict[str, Any]] = []
            for column_index, header_name, generic in candidate_columns:
                if generic or not header_name:
                    raise ValueError(f"{locator} has an unnamed runoff candidate")
                score = _parse_french_score(row.iloc[column_index])
                if score is None:
                    raise ValueError(f"{locator} has a missing runoff score")
                candidates.append({"name": header_name, "score": int(score) if score.is_integer() else score})
            second_round.append(
                _frozen_record(
                    locator=locator,
                    round_name=SECOND_ROUND,
                    pollster=pollster,
                    start=start,
                    end=end,
                    sample_size=sample_size,
                    candidates=candidates,
                    source_url=urljoin("https://fr.wikipedia.org", source_url),
                )
            )

    return {
        "revision_id": parsed["revid"],
        "first_round": first_round,
        "second_round": second_round,
        "rejected": rejected,
    }


def parse_english_frozen_first_round(parsed: dict[str, Any]) -> tuple[list[dict], list[str]]:
    return parse_wikipedia_first_round_html(parsed["text"])


def parse_english_frozen_second_round(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the frozen English runoff tables without MediaWiki network calls."""

    document = lxml_html.fromstring(parsed["text"])
    events: list[dict[str, Any]] = []
    family_index = 0
    for table in document.xpath("//table"):
        headings = table.xpath("preceding::*[self::h2 or self::h3 or self::h4]")
        heading = headings[-1].text_content().strip() if headings else ""
        if not re.search(r"\s+vs\.?\s+", heading, flags=re.IGNORECASE):
            continue
        family_index += 1
        frame = pd.read_html(
            io.StringIO(lxml_html.tostring(table, encoding="unicode")),
            extract_links="all",
        )[0]
        if len(frame.columns) != 5:
            raise ValueError(f"English runoff table {family_index} has unexpected width")
        candidate_columns = [
            (index, *_header_candidate(column))
            for index, column in enumerate(frame.columns[3:], start=3)
        ]
        if any(generic or not name for _, name, generic in candidate_columns):
            heading_parts = re.split(
                r"\s+vs\.?\s+", heading, maxsplit=1, flags=re.IGNORECASE
            )
            if len(heading_parts) != 2:
                raise ValueError(
                    f"English runoff table {family_index} has ambiguous headers"
                )
            heading_candidates = [
                reviewed_candidate_name(part) for part in heading_parts
            ]
            candidate_columns = [
                (index, heading_candidates[offset], False)
                for offset, (index, _name, _generic) in enumerate(candidate_columns)
            ]
        for row_index, row in frame.iterrows():
            pollster = cell_text(row.iloc[0])
            fieldwork = cell_text(row.iloc[1])
            sample_size = parse_sample_size(cell_text(row.iloc[2]))
            source_url = cell_link(row.iloc[0])
            if normalize_identity(pollster) in {"2022 election", "election"}:
                continue
            if not pollster or not fieldwork or sample_size is None or not source_url:
                continue
            try:
                start, end = parse_fieldwork(fieldwork)
            except ValueError:
                continue
            candidates: list[dict[str, Any]] = []
            for column_index, name, _generic in candidate_columns:
                score = parse_score(cell_text(row.iloc[column_index]))
                if score is None:
                    raise ValueError(
                        f"EN-R{family_index}r{row_index} has a missing runoff score"
                    )
                candidates.append(
                    {
                        "name": name,
                        "score": int(score) if score.is_integer() else score,
                    }
                )
            events.append(
                _frozen_record(
                    locator=f"EN-R{family_index}r{row_index}",
                    round_name=SECOND_ROUND,
                    pollster=pollster,
                    start=start,
                    end=end,
                    sample_size=sample_size,
                    candidates=candidates,
                    source_url=urljoin("https://en.wikipedia.org", source_url),
                )
            )
    return events


def reconcile_runoff_continuity(
    current_events: list[dict[str, Any]],
    registry: dict[str, Any],
) -> dict[str, int]:
    """Return the reviewed future second-round persistence accounting.

    This helper deliberately does not construct replacement production IDs.
    Mapped incoming rows retain the existing validated event, historical rows
    remain present, and only the twelve explicit additions increase the count.
    """

    for event in current_events:
        validate_second_round_event(event)
    current_ids = {event["event_id"] for event in current_events}
    if len(current_ids) != len(current_events):
        raise ValueError("current second-round corpus has duplicate event IDs")
    reviewed = [
        record
        for record in registry["reviewed_reconciliations"]
        if record["old_factual_key"]["round"] == SECOND_ROUND
    ]
    source_only = [
        record
        for record in registry["source_only_identity_migrations"]
        if record["old_factual_key"]["round"] == SECOND_ROUND
    ]
    mapped_ids = {
        record["retained_event_id"] for record in [*reviewed, *source_only]
    }
    if not mapped_ids.issubset(current_ids):
        raise ValueError("runoff registry references a missing retained event ID")
    persistence_ids = {
        record["event_id"]
        for record in registry["persistence_obligations"]["second_round"]
    }
    if not persistence_ids.issubset(current_ids):
        raise ValueError("runoff persistence obligation is absent from current corpus")
    additions = registry["french_additions"]["second_round"]
    return {
        "current_preserved": len(current_ids),
        "reviewed_different_representations": len(reviewed),
        "source_only_reconciliations": len(source_only),
        "english_only_historical_preserved": len(persistence_ids),
        "french_new": len(additions),
        "expected_post_migration": len(current_ids) + len(additions),
    }


def merge_previous_second_round_events(
    fresh_events: list[dict[str, Any]],
    previous_events: list[dict[str, Any]],
    registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Internal persistence primitive for a future ``--previous-second-round``.

    Mapped legacy records remain authoritative until event identity is changed
    in a later phase.  This function is intentionally not connected to the CLI.
    """

    for event in [*fresh_events, *previous_events]:
        validate_second_round_event(event)
    validate_migration_registry(registry)
    previous_by_id = {event["event_id"]: event for event in previous_events}
    if len(previous_by_id) != len(previous_events):
        raise ValueError("previous second-round corpus has duplicate event IDs")

    locator_to_retained: dict[str, str] = {}
    for record in [
        *registry["source_only_identity_migrations"],
        *registry["reviewed_reconciliations"],
    ]:
        if record["canonical_factual_key"]["round"] != SECOND_ROUND:
            continue
        locator = record["incoming_source_locator"]
        retained_id = record["retained_event_id"]
        if retained_id not in previous_by_id:
            raise ValueError(
                "runoff registry references a retained event absent from "
                "the previous corpus"
            )
        locator_to_retained[locator] = retained_id

    merged_by_id: dict[str, dict[str, Any]] = {}
    reconciled = 0
    seen_locators: set[str] = set()
    for event in fresh_events:
        locator = event.get("migration_source_locator")
        if locator is not None:
            if not isinstance(locator, str) or not locator:
                raise ValueError("migration_source_locator must be non-empty text")
            if locator in seen_locators:
                raise ValueError(
                    f"duplicate fresh migration source locator: {locator}"
                )
            seen_locators.add(locator)
        retained_id = locator_to_retained.get(locator)
        if retained_id is not None:
            # The legacy event remains authoritative in Phase 1 because the
            # production event ID is still source-URL-sensitive.  A locator
            # can reconcile only when the reviewed registry names one retained
            # ID; the weaker review anchor is intentionally not consulted.
            reconciled += 1
            continue
        event_id = event["event_id"]
        if event_id in merged_by_id:
            raise ValueError(f"fresh second-round corpus duplicates {event_id}")
        merged_by_id[event_id] = copy.deepcopy(event)

    for event_id, event in previous_by_id.items():
        merged_by_id.setdefault(event_id, copy.deepcopy(event))
    events = sorted(
        merged_by_id.values(),
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize_identity(event["pollster"]),
            event["matchup_key"],
            event["event_id"],
        ),
    )
    for event in events:
        validate_second_round_event(event)
    return events, reconciled
