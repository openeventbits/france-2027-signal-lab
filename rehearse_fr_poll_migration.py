"""Migration-aware parser and reconciliation for the FR27 French source.

The strict rehearsal entry point reproduces the frozen audited footprint.  The
production-capable helper also accepts structurally valid post-audit rows while
requiring explicit reviewed reconciliation for every historical ambiguity.
This module never writes polling data; callers choose their own output paths.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lxml import html as lxml_html

from fetch_polls import (
    MEDIAWIKI_API_URL as PRODUCTION_MEDIAWIKI_API_URL,
    SECOND_ROUND,
    SOURCE_PAGE as PRODUCTION_SOURCE_PAGE,
    SOURCE_URL as PRODUCTION_SOURCE_URL,
    USER_AGENT,
    validate_second_round_event,
)
from poll_contract import (
    FIRST_ROUND,
    apply_completeness_contract,
    make_event_id,
    make_scenario_key,
    normalize_identity,
    validate_poll_events,
)
from poll_migration import (
    FRENCH_FIXTURE,
    POST_AUDIT_HOLLANDE_LE_PEN_HEADING,
    candidate_identity,
    exact_factual_key,
    factual_key_from_dict,
    load_mediawiki_fixture,
    load_migration_registry,
    parse_french_frozen_fixture,
    pollster_identity,
    review_anchor,
    validate_migration_registry,
)


ROOT = Path(__file__).parent
PRE_CUTOVER_FIRST_ROUND = (
    ROOT / "test_fixtures/fr27_polling/pre_cutover_first_round_203.json"
)
PRE_CUTOVER_SECOND_ROUND = (
    ROOT / "test_fixtures/fr27_polling/pre_cutover_second_round_38.json"
)
FRENCH_REVISION = 238906992
REVIEWED_POST_AUDIT_FRENCH_REVISION = 239248634
REVIEWED_POST_AUDIT_FRENCH_FIXTURE = (
    ROOT
    / "test_fixtures/fr27_polling/fr_mediawiki_239248634.json"
)
SECOND_ROUND_EVIDENCE_RECONCILIATION = (
    ROOT / "fr27_poll_second_round_evidence_reconciliation.json"
)
SECOND_ROUND_EVIDENCE_REVISION = 239587014
REVIEWED_FAIL_CLOSED_SOURCE_REFRESHES = {
    (
        "opinionway",
        "2024-09-11",
        "2024-09-12",
        1009,
        "https://www.challenges.fr/politique/"
        "presidentielle-2027-le-sondage-confidentiel-qui-a-de-quoi-inquieter-"
        "attal-et-melenchon_905503",
        "censored_score",
    ): (
        "https://www.commission-des-sondages.fr/notices/files/notices/2024/"
        "septembre/9889a-pres-iv-opinionway-challenges-18-septembre.pdf"
    ),
}
REVIEWED_ACCEPTED_SOURCE_REFRESHES = {
    (
        "cluster17",
        "2026-08-31",
        "2026-09-01",
        1711,
        "https://www.lepoint.fr/politique/"
        "jean-luc-melenchon-aux-portes-du-second-tour-selon-un-sondage-"
        "cluster-17-pour-le-point-37HISKBJDRBZZFYP2EYB7PDIXA/",
        "https://www.commission-des-sondages.fr/notices/files/notices/2026/"
        "septembre/10251-pres-iv-cluster-17-le-point-5-septembre.pdf",
    ),
}
FRENCH_PAGE = "Liste de sondages sur l'élection présidentielle française de 2027"
FRENCH_API_URL = "https://fr.wikipedia.org/w/api.php"
PHASE4_PRODUCTION_MODIFICATION_FILES = (
    "fetch_polls.py",
    ".github/workflows/update-polls.yml",
)
PHASE4_SUPPORTING_TEST_FILES = (
    "test_fetch_polls.py",
    "test_poll_migration.py",
)
PHASE4_PROTECTED_LOGIC_SHA256 = {
    "poll_contract.py": "ba1c4e39db699293c859aa0740f57d4ba20dcd5b75bf31fb88f6f93c9af0a629",
    "commission_notice_discovery.py": "c3c4b448630bc5bcb5b319e9c798807a31bf7b900be615501eef2c35a113c879",
    "commission_notice_coverage.py": "0f467cccb64cb9bfc73ce58f4b874cf6d145233c8bad6736c8bd603a9b19c1b4",
}
PRODUCTION_ENGLISH_SOURCE = {
    "page_url": (
        "https://en.wikipedia.org/wiki/"
        "Opinion_polling_for_the_2027_French_presidential_election"
    ),
    "api_url": "https://en.wikipedia.org/w/api.php",
    "page": "Opinion_polling_for_the_2027_French_presidential_election",
}
EVENT_ID_CONTRACT_PROBES = {
    FIRST_ROUND: "ef29af8391fc51e049324a56e953a4fa2bd0436abf49d0ac38f67fb3897c0aed",
    SECOND_ROUND: "9908b42ab34235bc0b6456e96b237e9f00b9a58fa47ab1821d2a37ed5f019091",
}


class RehearsalError(ValueError):
    """Raised when a migration rehearsal cannot prove audited continuity."""


class SourceDriftError(RehearsalError):
    """Raised when live French source content exceeds the audited footprint."""


@dataclass(frozen=True)
class RehearsalResult:
    first_round_events: list[dict[str, Any]]
    second_round_events: list[dict[str, Any]]
    report: dict[str, Any]


def phase4a_cutover_contract() -> dict[str, Any]:
    """Prove the explicit French scheduled-source cutover boundary.

    The parser default remains English while the scheduled workflow explicitly
    opts into the French source. The hashes intentionally cover logic that the
    cutover must not change.
    """

    actual_source = {
        "page_url": PRODUCTION_SOURCE_URL,
        "api_url": PRODUCTION_MEDIAWIKI_API_URL,
        "page": PRODUCTION_SOURCE_PAGE,
    }
    if actual_source != PRODUCTION_ENGLISH_SOURCE:
        raise RehearsalError(
            "default polling source configuration changed"
        )
    workflow = (ROOT / ".github/workflows/update-polls.yml").read_text(
        encoding="utf-8"
    )
    required_workflow_markers = (
        "python fetch_polls.py",
        "--wikipedia-source french",
        "--previous-first-round polls.json",
        "--previous-second-round second_round_polls.json",
        "--second-round-output /tmp/second_round_polls.json",
    )
    if not all(marker in workflow for marker in required_workflow_markers):
        raise RehearsalError("current polling workflow contract changed")
    forbidden_phase4a_markers = (
        "fr.wikipedia.org",
        "rehearse_fr_poll_migration",
    )
    if any(marker in workflow for marker in forbidden_phase4a_markers):
        raise RehearsalError("scheduled workflow bypasses the explicit French source selector")

    protected_hashes: dict[str, str] = {}
    for relative, expected in PHASE4_PROTECTED_LOGIC_SHA256.items():
        content = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            raise RehearsalError(f"protected cutover logic changed: {relative}")
        protected_hashes[relative] = actual

    probe_material = {
        FIRST_ROUND: make_event_id(
            "Harris Interactive",
            "2026-08-18",
            "2026-08-19",
            "First round — audit probe",
            "https://example.test/source",
        ),
        SECOND_ROUND: make_event_id(
            "Harris Interactive",
            "2026-08-18",
            "2026-08-19",
            "Second round — audit probe",
            "https://example.test/source",
            round_name=SECOND_ROUND,
        ),
    }
    if probe_material != EVENT_ID_CONTRACT_PROBES:
        raise RehearsalError("make_event_id contract changed")

    return {
        "phase": "cutover",
        "production_source": "french_wikipedia_scheduled",
        "production_source_configuration": actual_source,
        "phase4_production_modification_files": list(
            PHASE4_PRODUCTION_MODIFICATION_FILES
        ),
        "phase4_supporting_test_files": list(PHASE4_SUPPORTING_TEST_FILES),
        "phase4_protected_logic_files": list(PHASE4_PROTECTED_LOGIC_SHA256),
        "protected_logic_sha256": protected_hashes,
        "make_event_id_probes": probe_material,
        "audited_cutover_counts": {
            "retained_first_round_ids": 203,
            "retained_second_round_ids": 38,
            "new_first_round": 29,
            "new_second_round": 12,
            "reconciled_first_round": 232,
            "reconciled_second_round": 50,
        },
    }


def fetch_live_french_parse() -> dict[str, Any]:
    """Fetch one current French MediaWiki parse response for rehearsal only."""

    query = urlencode(
        {
            "action": "parse",
            "format": "json",
            "formatversion": "2",
            "page": FRENCH_PAGE,
            "prop": "text|revid|tocdata",
            "redirects": "1",
        }
    )
    request = Request(
        f"{FRENCH_API_URL}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or "error" in payload:
        raise SourceDriftError(f"French MediaWiki API error: {payload!r}")
    parsed = payload.get("parse")
    if not isinstance(parsed, dict):
        raise SourceDriftError("French MediaWiki response lacks parse data")
    if not isinstance(parsed.get("revid"), int):
        raise SourceDriftError("French MediaWiki response lacks a revision ID")
    if not isinstance(parsed.get("text"), str):
        raise SourceDriftError("French MediaWiki response lacks rendered HTML")
    tocdata = parsed.get("tocdata")
    if not isinstance(tocdata, dict) or not isinstance(tocdata.get("sections"), list):
        raise SourceDriftError("French MediaWiki response lacks section metadata")
    return parsed


def _relevant_heading_fingerprint(parsed: dict[str, Any]) -> tuple[tuple[int, str], ...]:
    sections = parsed["tocdata"]["sections"]
    normalized = [
        (
            int(section.get("tocLevel", 0)),
            normalize_identity(str(section.get("line", ""))),
        )
        for section in sections
    ]
    first_heading = "sondages concernant le premier tour"
    try:
        start = next(index for index, (_level, line) in enumerate(normalized) if line == first_heading)
    except StopIteration as error:
        raise SourceDriftError(
            "French source lacks the audited first/second-round section boundary"
        ) from error
    top_level_sections = [
        index
        for index, (level, _line) in enumerate(normalized[start:], start=start)
        if level == 1
    ]
    if len(top_level_sections) < 3:
        raise SourceDriftError(
            "French source lacks the audited first/second-round section boundary"
        )
    return tuple(normalized[start : top_level_sections[2]])


def _record_signature(record: dict[str, Any]) -> tuple[str, str]:
    key = exact_factual_key(record, sample_scope="reported")
    return (
        json.dumps(key.to_dict(), ensure_ascii=False, sort_keys=True),
        record["source_url"],
    )


def _source_footprint(parsed: dict[str, Any]) -> dict[str, Any]:
    try:
        records = parse_french_frozen_fixture(parsed)
    except (TypeError, ValueError) as error:
        raise SourceDriftError(f"French table structure is not auditable: {error}") from error
    accepted: dict[str, tuple[str, str]] = {}
    for round_name in (FIRST_ROUND, SECOND_ROUND):
        for record in records[round_name]:
            locator = record["source_locator"]
            if locator in accepted:
                raise SourceDriftError(f"duplicate French source locator: {locator}")
            accepted[locator] = _record_signature(record)
    rejected = tuple(
        sorted(
            (record["source_locator"], record["reason_code"])
            for record in records["rejected"]
        )
    )
    return {
        "records": records,
        "headings": _relevant_heading_fingerprint(parsed),
        "accepted": accepted,
        "rejected": rejected,
    }


def _assert_audited_source_footprint(parsed: dict[str, Any]) -> dict[str, Any]:
    revision = parsed.get("revid")
    if not isinstance(revision, int) or revision < FRENCH_REVISION:
        raise SourceDriftError(
            f"French source revision {revision!r} predates audited revision {FRENCH_REVISION}"
        )
    audited = _source_footprint(
        load_mediawiki_fixture(FRENCH_FIXTURE, FRENCH_REVISION)
    )
    incoming = _source_footprint(parsed)
    drift: list[str] = []
    if incoming["headings"] != audited["headings"]:
        drift.append("relevant heading hierarchy changed")
    audited_locators = set(audited["accepted"])
    incoming_locators = set(incoming["accepted"])
    missing = sorted(audited_locators - incoming_locators)
    added = sorted(incoming_locators - audited_locators)
    if missing:
        drift.append(f"audited rows missing: {missing}")
    if added:
        drift.append(f"unaudited rows present: {added}")
    changed = sorted(
        locator
        for locator in audited_locators & incoming_locators
        if audited["accepted"][locator] != incoming["accepted"][locator]
    )
    if changed:
        drift.append(f"audited row facts or source URLs changed: {changed}")
    if incoming["rejected"] != audited["rejected"]:
        drift.append(
            "fail-closed rows changed: "
            f"expected {audited['rejected']}, got {incoming['rejected']}"
        )
    if drift:
        raise SourceDriftError("; ".join(drift))
    return incoming["records"]


def _assert_production_source_structure(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate dynamic table structure through the substantive French parser."""

    revision = parsed.get("revid")
    if not isinstance(revision, int) or revision < FRENCH_REVISION:
        raise SourceDriftError(
            f"French source revision {revision!r} predates audited revision {FRENCH_REVISION}"
        )
    try:
        return parse_french_frozen_fixture(parsed)
    except (TypeError, ValueError) as error:
        raise SourceDriftError(
            f"French polling structural validation failed: {error}"
        ) from error


def _read_corpora(
    first_path: Path,
    second_path: Path,
    *,
    label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))
    second = second_payload.get("events") if isinstance(second_payload, dict) else None
    if not isinstance(first, list) or not isinstance(second, list):
        raise RehearsalError(f"{label} polling corpora are malformed")
    validate_poll_events(first)
    for event in second:
        validate_second_round_event(event)
    return first, second


def _read_current_corpora() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _read_corpora(
        ROOT / "polls.json",
        ROOT / "second_round_polls.json",
        label="current",
    )


def _read_pre_cutover_corpora() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _read_corpora(
        PRE_CUTOVER_FIRST_ROUND,
        PRE_CUTOVER_SECOND_ROUND,
        label="frozen pre-cutover",
    )


def _display_pollster(identity: str, reported: str) -> str:
    if identity == "ifop-hexagone":
        return "Ifop/Hexagone"
    if identity == "harris-interactive":
        return "Harris Interactive"
    if pollster_identity(reported) != identity:
        raise RehearsalError(
            f"no reviewed display mapping from {reported!r} to pollster {identity!r}"
        )
    return reported


def _score_number(value: str) -> int | float:
    number = Decimal(value)
    return int(number) if number == number.to_integral_value() else float(number)


def _addition_candidates(
    source_record: dict[str, Any], factual_key: dict[str, Any]
) -> list[dict[str, Any]]:
    source_names = {
        candidate_identity(candidate["name"]): candidate["name"]
        for candidate in source_record["candidates"]
    }
    key_ids = {candidate["candidate_id"] for candidate in factual_key["candidates"]}
    if set(source_names) != key_ids:
        raise RehearsalError(
            f"{source_record['source_locator']} candidate identities contradict registry"
        )
    return [
        {
            "name": source_names[candidate["candidate_id"]],
            "score": _score_number(candidate["score"]),
        }
        for candidate in factual_key["candidates"]
    ]


def _make_first_addition(
    source_record: dict[str, Any], registry_record: dict[str, Any]
) -> dict[str, Any]:
    key = factual_key_from_dict(
        registry_record["factual_key"],
        f"addition {registry_record['source_locator']}",
    ).to_dict()
    candidates = _addition_candidates(source_record, key)
    pollster = _display_pollster(key["pollster_identity"], source_record["pollster"])
    hypothesis = "French rehearsal — " + ", ".join(
        candidate["name"] for candidate in candidates
    )
    event = apply_completeness_contract(
        {
            "event_id": make_event_id(
                pollster,
                key["fieldwork_start"],
                key["fieldwork_end"],
                hypothesis,
                registry_record["source_url"],
            ),
            "pollster": pollster,
            "commissioner": None,
            "publication_date": None,
            "fieldwork_start": key["fieldwork_start"],
            "fieldwork_end": key["fieldwork_end"],
            "sample_size": key["sample_size"],
            "sample_scope": key["sample_scope"],
            "round": FIRST_ROUND,
            "hypothesis": hypothesis,
            "scenario_key": make_scenario_key(
                [candidate["name"] for candidate in candidates]
            ),
            "source_url": registry_record["source_url"],
            "candidates": candidates,
            "migration_source_locator": source_record["source_locator"],
            "rehearsal_only": True,
        }
    )
    validate_poll_events([event])
    return event


def _make_second_addition(
    source_record: dict[str, Any], registry_record: dict[str, Any]
) -> dict[str, Any]:
    key = factual_key_from_dict(
        registry_record["factual_key"],
        f"addition {registry_record['source_locator']}",
    ).to_dict()
    candidates = _addition_candidates(source_record, key)
    pollster = _display_pollster(key["pollster_identity"], source_record["pollster"])
    hypothesis = "Second round — " + " vs ".join(
        candidate["name"] for candidate in candidates
    )
    event = {
        "event_id": make_event_id(
            pollster,
            key["fieldwork_start"],
            key["fieldwork_end"],
            hypothesis,
            registry_record["source_url"],
            round_name=SECOND_ROUND,
        ),
        "round": SECOND_ROUND,
        "pollster": pollster,
        "commissioner": None,
        "publication_date": None,
        "fieldwork_start": key["fieldwork_start"],
        "fieldwork_end": key["fieldwork_end"],
        "sample_size": key["sample_size"],
        "sample_scope": key["sample_scope"],
        "hypothesis": hypothesis,
        "matchup_key": make_scenario_key(
            [candidate["name"] for candidate in candidates],
            round_name=SECOND_ROUND,
        ),
        "candidates": candidates,
        "margin": abs(candidates[0]["score"] - candidates[1]["score"]),
        "source_url": registry_record["source_url"],
        "source_scope": "current_tested",
        "quality_flags": [],
        "migration_source_locator": source_record["source_locator"],
        "rehearsal_only": True,
    }
    validate_second_round_event(event)
    return event


def _make_normal_first_event(source_record: dict[str, Any]) -> dict[str, Any]:
    candidates = copy.deepcopy(source_record["candidates"])
    hypothesis = "French source — " + ", ".join(
        candidate["name"] for candidate in candidates
    )
    event = apply_completeness_contract(
        {
            "event_id": make_event_id(
                source_record["pollster"],
                source_record["fieldwork_start"],
                source_record["fieldwork_end"],
                hypothesis,
                source_record["source_url"],
            ),
            "pollster": source_record["pollster"],
            "commissioner": None,
            "publication_date": None,
            "fieldwork_start": source_record["fieldwork_start"],
            "fieldwork_end": source_record["fieldwork_end"],
            "sample_size": source_record["sample_size"],
            "sample_scope": "reported",
            "round": FIRST_ROUND,
            "hypothesis": hypothesis,
            "scenario_key": make_scenario_key(
                [candidate["name"] for candidate in candidates]
            ),
            "source_url": source_record["source_url"],
            "candidates": candidates,
            "migration_source_locator": source_record["source_locator"],
        }
    )
    validate_poll_events([event])
    return event


def _make_normal_second_event(source_record: dict[str, Any]) -> dict[str, Any]:
    candidates = copy.deepcopy(source_record["candidates"])
    hypothesis = "Second round — " + " vs ".join(
        candidate["name"] for candidate in candidates
    )
    event = {
        "event_id": make_event_id(
            source_record["pollster"],
            source_record["fieldwork_start"],
            source_record["fieldwork_end"],
            hypothesis,
            source_record["source_url"],
            round_name=SECOND_ROUND,
        ),
        "round": SECOND_ROUND,
        "pollster": source_record["pollster"],
        "commissioner": None,
        "publication_date": None,
        "fieldwork_start": source_record["fieldwork_start"],
        "fieldwork_end": source_record["fieldwork_end"],
        "sample_size": source_record["sample_size"],
        "sample_scope": "reported",
        "hypothesis": hypothesis,
        "matchup_key": make_scenario_key(
            [candidate["name"] for candidate in candidates],
            round_name=SECOND_ROUND,
        ),
        "candidates": candidates,
        "margin": abs(candidates[0]["score"] - candidates[1]["score"]),
        "source_url": source_record["source_url"],
        "source_page_url": (
            "https://fr.wikipedia.org/wiki/"
            "Liste_de_sondages_sur_l%27%C3%A9lection_pr%C3%A9sidentielle_"
            "fran%C3%A7aise_de_2027"
        ),
        "source_section": "French production migration",
        "source_section_path": ["Sondages concernant le second tour"],
        "source_scope": "current_tested",
        "quality_flags": [],
        "migration_source_locator": source_record["source_locator"],
    }
    validate_second_round_event(event)
    return event


def _current_exact_index(
    events: list[dict[str, Any]], round_name: str
) -> dict[Any, list[dict[str, Any]]]:
    index: dict[Any, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("round") != round_name:
            raise RehearsalError(f"current {round_name} corpus contains another round")
        try:
            key = exact_factual_key(event, sample_scope="reported")
        except ValueError:
            # Audited unnamed historical scenarios survive only through their
            # explicit persistence obligations, never through inferred identity.
            continue
        index.setdefault(key, []).append(event)
    return index


def rehearse_migration(
    parsed: dict[str, Any],
    *,
    current_first: list[dict[str, Any]] | None = None,
    current_second: list[dict[str, Any]] | None = None,
    registry: dict[str, Any] | None = None,
) -> RehearsalResult:
    """Reconcile one French parse entirely in memory or fail closed."""

    source_records = _assert_audited_source_footprint(parsed)
    migration_registry = registry or load_migration_registry()
    validate_migration_registry(migration_registry)
    if current_first is None or current_second is None:
        loaded_first, loaded_second = _read_current_corpora()
        current_first = loaded_first if current_first is None else current_first
        current_second = loaded_second if current_second is None else current_second
    validate_poll_events(current_first)
    for event in current_second:
        validate_second_round_event(event)
    if (len(current_first), len(current_second)) != (203, 38):
        raise RehearsalError(
            "current corpus counts contradict audited continuity: "
            f"{len(current_first)} first, {len(current_second)} second"
        )

    mappings = {
        record["incoming_source_locator"]: record
        for section in (
            "source_only_identity_migrations",
            "reviewed_reconciliations",
        )
        for record in migration_registry[section]
        if record.get("incoming_source_revision", FRENCH_REVISION)
        == parsed["revid"]
    }
    additions = {
        record["source_locator"]: record
        for round_name in (FIRST_ROUND, SECOND_ROUND)
        for record in migration_registry["french_additions"][round_name]
    }
    identity_skips = {
        record["source_locator"] for record in migration_registry["identity_skips"]
    }
    persistence_ids = {
        round_name: {
            record["event_id"]
            for record in migration_registry["persistence_obligations"][round_name]
        }
        for round_name in (FIRST_ROUND, SECOND_ROUND)
    }
    current_by_round = {
        FIRST_ROUND: current_first,
        SECOND_ROUND: current_second,
    }
    current_ids = {
        round_name: {event["event_id"] for event in events}
        for round_name, events in current_by_round.items()
    }
    exact_indexes = {
        round_name: _current_exact_index(events, round_name)
        for round_name, events in current_by_round.items()
    }
    represented_ids = {
        FIRST_ROUND: set(persistence_ids[FIRST_ROUND]),
        SECOND_ROUND: set(persistence_ids[SECOND_ROUND]),
    }
    exact_common = {FIRST_ROUND: 0, SECOND_ROUND: 0}
    mapped_counts = {
        "source_only": {FIRST_ROUND: 0, SECOND_ROUND: 0},
        "reviewed": {FIRST_ROUND: 0, SECOND_ROUND: 0},
    }
    new_events = {FIRST_ROUND: [], SECOND_ROUND: []}
    canonical_keys: set[Any] = set()

    for round_name in (FIRST_ROUND, SECOND_ROUND):
        for source_record in source_records[round_name]:
            locator = source_record["source_locator"]
            if locator in identity_skips:
                continue
            if locator in mappings:
                record = mappings[locator]
                incoming = exact_factual_key(source_record, sample_scope="reported")
                expected_incoming = factual_key_from_dict(
                    record["incoming_factual_key"], f"mapping {locator} incoming"
                )
                if incoming != expected_incoming:
                    raise SourceDriftError(
                        f"{locator} no longer matches its reviewed incoming factual key"
                    )
                canonical = factual_key_from_dict(
                    record["canonical_factual_key"], f"mapping {locator} canonical"
                )
                if canonical in canonical_keys:
                    raise RehearsalError(f"duplicate canonical factual identity: {locator}")
                canonical_keys.add(canonical)
                retained_id = record["retained_event_id"]
                if retained_id not in current_ids[round_name]:
                    raise RehearsalError(f"{locator} retained event ID is absent")
                represented_ids[round_name].add(retained_id)
                category = (
                    "reviewed"
                    if record["treatment"] == "retain_id_reviewed_correction"
                    else "source_only"
                )
                mapped_counts[category][round_name] += 1
                continue
            if locator in additions:
                record = additions[locator]
                key = factual_key_from_dict(
                    record["factual_key"], f"addition {locator}"
                )
                if key in canonical_keys:
                    raise RehearsalError(f"duplicate canonical factual identity: {locator}")
                canonical_keys.add(key)
                maker = (
                    _make_first_addition
                    if round_name == FIRST_ROUND
                    else _make_second_addition
                )
                new_events[round_name].append(maker(source_record, record))
                continue

            key = exact_factual_key(source_record, sample_scope="reported")
            matches = [
                event
                for event in exact_indexes[round_name].get(key, [])
                if event["source_url"] == source_record["source_url"]
            ]
            if len(matches) != 1:
                raise RehearsalError(
                    f"{locator} is unclassified and has {len(matches)} exact current matches"
                )
            if key in canonical_keys:
                raise RehearsalError(f"duplicate canonical factual identity: {locator}")
            canonical_keys.add(key)
            represented_ids[round_name].add(matches[0]["event_id"])
            exact_common[round_name] += 1

    for round_name in (FIRST_ROUND, SECOND_ROUND):
        unexplained = current_ids[round_name] - represented_ids[round_name]
        if unexplained:
            raise RehearsalError(
                f"unexplained historical losses in {round_name}: {sorted(unexplained)}"
            )
    if (exact_common[FIRST_ROUND], exact_common[SECOND_ROUND]) != (10, 10):
        raise RehearsalError(f"exact-common accounting drifted: {exact_common}")
    if (len(new_events[FIRST_ROUND]), len(new_events[SECOND_ROUND])) != (29, 12):
        raise RehearsalError("French addition counts contradict the audited registry")

    reconciled_first = [
        *copy.deepcopy(current_first),
        *copy.deepcopy(new_events[FIRST_ROUND]),
    ]
    reconciled_second = [
        *copy.deepcopy(current_second),
        *copy.deepcopy(new_events[SECOND_ROUND]),
    ]
    validate_poll_events(reconciled_first)
    for event in reconciled_second:
        validate_second_round_event(event)
    for round_name, events in (
        (FIRST_ROUND, reconciled_first),
        (SECOND_ROUND, reconciled_second),
    ):
        event_ids = [event["event_id"] for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise RehearsalError(f"duplicate reconciled {round_name} event IDs")
    if (len(reconciled_first), len(reconciled_second)) != (232, 50):
        raise RehearsalError("reconciled corpus totals contradict the audit")

    august_runoffs = {
        tuple(sorted((candidate["name"], candidate["score"]) for candidate in event["candidates"]))
        for event in new_events[SECOND_ROUND]
        if event["fieldwork_start"] == "2026-08-18"
        and event["fieldwork_end"] == "2026-08-19"
    }
    required_august = {
        tuple(sorted((("Gabriel Attal", 43), ("Marine Le Pen", 57)))),
        tuple(sorted((("Jean-Luc Mélenchon", 32), ("Marine Le Pen", 68)))),
        tuple(sorted((("Édouard Philippe", 45), ("Marine Le Pen", 55)))),
    }
    if not required_august <= august_runoffs:
        raise RehearsalError("August Harris runoff gate is incomplete or changed")

    report = {
        "status": "passed",
        "source_revision": parsed["revid"],
        "audited_source_revision": FRENCH_REVISION,
        "parsed": {
            "first_round": len(source_records[FIRST_ROUND]),
            "second_round": len(source_records[SECOND_ROUND]),
        },
        "reconciled": {
            "first_round": len(reconciled_first),
            "second_round": len(reconciled_second),
        },
        "retained_ids": {
            "first_round": len(current_ids[FIRST_ROUND]),
            "second_round": len(current_ids[SECOND_ROUND]),
        },
        "new_additions": {
            "first_round": len(new_events[FIRST_ROUND]),
            "second_round": len(new_events[SECOND_ROUND]),
        },
        "source_only_migrations": {
            "first_round": mapped_counts["source_only"][FIRST_ROUND],
            "second_round": mapped_counts["source_only"][SECOND_ROUND],
        },
        "reviewed_reconciliations": {
            "first_round": mapped_counts["reviewed"][FIRST_ROUND],
            "second_round": mapped_counts["reviewed"][SECOND_ROUND],
        },
        "exact_common": {
            "first_round": exact_common[FIRST_ROUND],
            "second_round": exact_common[SECOND_ROUND],
        },
        "skips": {
            "fail_closed_rows": len(source_records["rejected"]),
            "ambiguous_identity_rows": len(identity_skips),
        },
        "unexplained_historical_losses": 0,
        "unresolved_accepted_ambiguities": 0,
        "duplicate_canonical_factual_identities": 0,
        "source_structure_drift": [],
        "august_harris_18_19_runoffs_verified": 3,
    }
    return RehearsalResult(reconciled_first, reconciled_second, report)


def _rejected_row_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        pollster_identity(record["pollster"]),
        record["fieldwork_start"],
        record["fieldwork_end"],
        record["sample_size"],
        record["source_url"],
        record["reason_code"],
    )


def _reviewed_rejected_row_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    signature = _rejected_row_signature(record)
    for reviewed, refreshed_source in REVIEWED_FAIL_CLOSED_SOURCE_REFRESHES.items():
        refreshed = reviewed[:4] + (refreshed_source, reviewed[5])
        if signature == refreshed:
            return reviewed
    return signature


def _factual_key_label(key: Any) -> str:
    candidates = ",".join(candidate_id for candidate_id, _score in key.candidates)
    return (
        f"{key.round}:{key.pollster_identity}:"
        f"{key.fieldwork_start}..{key.fieldwork_end}:"
        f"n={key.sample_size}:[{candidates}]"
    )


def _is_reviewed_accepted_source_refresh(
    key: Any, reviewed_source: str, incoming_source: str
) -> bool:
    return (
        key.pollster_identity,
        key.fieldwork_start,
        key.fieldwork_end,
        key.sample_size,
        reviewed_source,
        incoming_source,
    ) in REVIEWED_ACCEPTED_SOURCE_REFRESHES


def _load_second_round_evidence_reconciliation() -> dict[str, Any]:
    """Load the bounded reviewed second-round evidence successor contract."""

    try:
        payload = json.loads(
            SECOND_ROUND_EVIDENCE_RECONCILIATION.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        raise RehearsalError(
            "second-round evidence reconciliation cannot be loaded"
        ) from error

    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "source_revision",
        "second_round_reconciliations",
    }:
        raise RehearsalError(
            "second-round evidence reconciliation top level is malformed"
        )

    if payload.get("schema_version") != "1.0":
        raise RehearsalError(
            "second-round evidence reconciliation schema is unsupported"
        )

    source = payload.get("source_revision")
    expected_fixture = (
        "test_fixtures/fr27_polling/"
        f"fr_mediawiki_{SECOND_ROUND_EVIDENCE_REVISION}.json"
    )

    if (
        not isinstance(source, dict)
        or set(source) != {
            "revision_id",
            "page_url",
            "fixture",
            "fixture_sha256",
        }
        or source.get("revision_id") != SECOND_ROUND_EVIDENCE_REVISION
        or source.get("fixture") != expected_fixture
    ):
        raise RehearsalError(
            "second-round evidence source revision is malformed"
        )

    fixture_sha256 = source.get("fixture_sha256")
    if (
        not isinstance(fixture_sha256, str)
        or len(fixture_sha256) != 64
        or any(character not in "0123456789abcdef" for character in fixture_sha256)
    ):
        raise RehearsalError(
            "second-round evidence fixture SHA-256 is malformed"
        )

    fixture_path = ROOT / expected_fixture
    try:
        actual_fixture_sha256 = hashlib.sha256(
            fixture_path.read_bytes()
        ).hexdigest()
    except OSError as error:
        raise RehearsalError(
            "second-round evidence fixture cannot be read"
        ) from error

    if actual_fixture_sha256 != fixture_sha256:
        raise RehearsalError(
            "second-round evidence fixture SHA-256 changed"
        )

    records = payload.get("second_round_reconciliations")
    if not isinstance(records, list) or len(records) != 10:
        raise RehearsalError(
            "second-round evidence reconciliation must contain exactly ten records"
        )

    allowed_actions = {
        "retain_existing",
        "correct_retained_sample",
        "supersede_event",
    }
    expected_action_counts = {
        "retain_existing": 4,
        "correct_retained_sample": 5,
        "supersede_event": 1,
    }

    action_counts = {
        action: 0
        for action in allowed_actions
    }
    seen_locators: set[str] = set()
    seen_previous_ids: set[str] = set()
    seen_reviewed_keys: set[Any] = set()
    seen_incoming_keys: set[Any] = set()
    seen_canonical_keys: set[Any] = set()

    for index, record in enumerate(records):
        context = (
            "second_round_reconciliations"
            f"[{index}]"
        )

        if not isinstance(record, dict):
            raise RehearsalError(f"{context} must be an object")

        action = record.get("action")
        required = {
            "source_locator",
            "previous_event_id",
            "action",
            "reviewed_factual_key",
            "previous_event_factual_key",
            "incoming_factual_key",
            "canonical_factual_key",
            "incoming_source_url",
            "evidence_urls",
            "review_reason",
        }

        if action == "supersede_event":
            required.add("replacement_event_id")

        if set(record) != required:
            raise RehearsalError(f"{context} fields are malformed")

        if action not in allowed_actions:
            raise RehearsalError(f"{context}.action is unsupported")

        action_counts[action] += 1

        locator = record["source_locator"]
        if (
            not isinstance(locator, str)
            or not locator.startswith("FR-R")
            or locator in seen_locators
        ):
            raise RehearsalError(
                f"{context}.source_locator is malformed or duplicated"
            )
        seen_locators.add(locator)

        previous_id = record["previous_event_id"]
        if (
            not isinstance(previous_id, str)
            or len(previous_id) != 64
            or any(
                character not in "0123456789abcdef"
                for character in previous_id
            )
            or previous_id in seen_previous_ids
        ):
            raise RehearsalError(
                f"{context}.previous_event_id is malformed or duplicated"
            )
        seen_previous_ids.add(previous_id)

        keys = {}
        for field in (
            "reviewed_factual_key",
            "previous_event_factual_key",
            "incoming_factual_key",
            "canonical_factual_key",
        ):
            try:
                key = factual_key_from_dict(
                    record[field],
                    f"{context}.{field}",
                )
            except ValueError as error:
                raise RehearsalError(
                    f"{context}.{field} is malformed"
                ) from error

            if key.round != SECOND_ROUND:
                raise RehearsalError(
                    f"{context}.{field} is not second round"
                )

            keys[field] = key

        reviewed_key = keys["reviewed_factual_key"]
        incoming_key = keys["incoming_factual_key"]
        canonical_key = keys["canonical_factual_key"]
        previous_key = keys["previous_event_factual_key"]

        if reviewed_key in seen_reviewed_keys:
            raise RehearsalError(
                "duplicate reviewed second-round successor key"
            )
        if incoming_key in seen_incoming_keys:
            raise RehearsalError(
                "duplicate incoming second-round successor key"
            )
        if canonical_key in seen_canonical_keys:
            raise RehearsalError(
                "duplicate canonical second-round successor key"
            )

        seen_reviewed_keys.add(reviewed_key)
        seen_incoming_keys.add(incoming_key)
        seen_canonical_keys.add(canonical_key)

        incoming_source_url = record["incoming_source_url"]
        if (
            not isinstance(incoming_source_url, str)
            or not incoming_source_url.startswith(("http://", "https://"))
        ):
            raise RehearsalError(
                f"{context}.incoming_source_url is malformed"
            )

        evidence_urls = record["evidence_urls"]
        if (
            not isinstance(evidence_urls, list)
            or not evidence_urls
            or not all(
                isinstance(url, str)
                and url.startswith(("http://", "https://"))
                for url in evidence_urls
            )
        ):
            raise RehearsalError(
                f"{context}.evidence_urls is malformed"
            )

        if (
            not isinstance(record["review_reason"], str)
            or not record["review_reason"].strip()
        ):
            raise RehearsalError(
                f"{context}.review_reason is malformed"
            )

        if action == "retain_existing":
            if previous_key != canonical_key:
                raise RehearsalError(
                    f"{context} retain_existing must preserve canonical facts"
                )

        elif action == "correct_retained_sample":
            stable_fields = (
                "pollster_identity",
                "fieldwork_start",
                "fieldwork_end",
                "candidates",
            )
            if any(
                getattr(previous_key, field)
                != getattr(canonical_key, field)
                for field in stable_fields
            ):
                raise RehearsalError(
                    f"{context} sample correction changes non-sample facts"
                )

            if canonical_key.sample_scope != "matchup_respondents":
                raise RehearsalError(
                    f"{context} sample correction lacks matchup respondent scope"
                )

        elif action == "supersede_event":
            replacement_id = record["replacement_event_id"]

            if (
                not isinstance(replacement_id, str)
                or len(replacement_id) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in replacement_id
                )
                or replacement_id == previous_id
            ):
                raise RehearsalError(
                    f"{context}.replacement_event_id is malformed"
                )

            if canonical_key != incoming_key:
                raise RehearsalError(
                    f"{context} supersession canonical key must equal incoming"
                )

    if action_counts != expected_action_counts:
        raise RehearsalError(
            "second-round evidence reconciliation action counts changed"
        )

    return payload


def _classify_second_round_evidence_lifecycle(
    previous_second: list[dict[str, Any]],
    payload: dict[str, Any],
) -> str:
    """Classify the persisted corpus against the bounded ten-record contract."""

    current_by_id = {
        event["event_id"]: event
        for event in previous_second
    }

    pre_transition = 0
    applied = 0

    for record in payload["second_round_reconciliations"]:
        action = record["action"]
        previous_id = record["previous_event_id"]

        previous_key = factual_key_from_dict(
            record["previous_event_factual_key"],
            "second-round lifecycle previous factual key",
        )
        canonical_key = factual_key_from_dict(
            record["canonical_factual_key"],
            "second-round lifecycle canonical factual key",
        )

        if action == "retain_existing":
            event = current_by_id.get(previous_id)
            if event is None:
                raise RehearsalError(
                    "second-round evidence retained event is absent"
                )

            event_key = exact_factual_key(
                event,
                sample_scope=event.get(
                    "sample_scope",
                    "reported",
                ),
            )
            if event_key != canonical_key:
                raise RehearsalError(
                    "second-round evidence retained event facts changed"
                )
            continue

        if action == "correct_retained_sample":
            event = current_by_id.get(previous_id)
            if event is None:
                raise RehearsalError(
                    "second-round evidence corrected event is absent"
                )

            event_key = exact_factual_key(
                event,
                sample_scope=event.get(
                    "sample_scope",
                    "reported",
                ),
            )

            if event_key == previous_key:
                pre_transition += 1
            elif event_key == canonical_key:
                applied += 1
            else:
                raise RehearsalError(
                    "second-round evidence corrected event facts changed"
                )
            continue

        if action == "supersede_event":
            replacement_id = record["replacement_event_id"]
            old_event = current_by_id.get(previous_id)
            replacement = current_by_id.get(replacement_id)

            if old_event is not None and replacement is not None:
                raise RehearsalError(
                    "second-round evidence supersession contains both "
                    "old and replacement event IDs"
                )

            if old_event is not None:
                old_key = exact_factual_key(
                    old_event,
                    sample_scope=old_event.get(
                        "sample_scope",
                        "reported",
                    ),
                )
                if old_key != previous_key:
                    raise RehearsalError(
                        "second-round evidence superseded event facts changed"
                    )
                pre_transition += 1
                continue

            if replacement is None:
                raise RehearsalError(
                    "reviewed mapping supersession replacement is absent"
                )

            replacement_key = exact_factual_key(
                replacement,
                sample_scope=replacement.get(
                    "sample_scope",
                    "reported",
                ),
            )
            if replacement_key != canonical_key:
                raise RehearsalError(
                    "reviewed mapping supersession replacement facts changed"
                )

            if (
                replacement["source_url"]
                != record["incoming_source_url"]
                or replacement.get("migration_source_locator")
                != record["source_locator"]
            ):
                raise RehearsalError(
                    "second-round evidence replacement provenance changed"
                )

            applied += 1
            continue

        raise RehearsalError(
            "unsupported second-round evidence lifecycle action"
        )

    if pre_transition and applied:
        raise RehearsalError(
            "mixed second-round evidence lifecycle state"
        )

    if pre_transition == 6:
        return "pre_evidence"

    if applied == 6:
        return "applied"

    raise RehearsalError(
        "second-round evidence lifecycle state is incomplete"
    )


def _assert_reviewed_post_audit_semantics(
    parsed: dict[str, Any],
    source_records: dict[str, Any],
    previous_by_round: dict[str, list[dict[str, Any]]],
    migration_registry: dict[str, Any],
) -> None:
    """Keep reviewed facts/provenance strict while allowing new source rows."""

    if parsed["revid"] < REVIEWED_POST_AUDIT_FRENCH_REVISION:
        return
    reviewed = parse_french_frozen_fixture(
        load_mediawiki_fixture(
            REVIEWED_POST_AUDIT_FRENCH_FIXTURE,
            REVIEWED_POST_AUDIT_FRENCH_REVISION,
        )
    )
    reviewed_replacements: dict[tuple[str, Any], dict[str, Any]] = {}
    for record in migration_registry["reviewed_reconciliations"]:
        if record.get("materialize_absent_canonical") is not True:
            continue
        old_key = factual_key_from_dict(
            record["old_factual_key"], "reviewed reconciliation old factual key"
        )
        canonical_key = factual_key_from_dict(
            record["canonical_factual_key"],
            "reviewed reconciliation canonical factual key",
        )
        if old_key != canonical_key:
            continue
        reviewed_replacements[(canonical_key.round, canonical_key)] = record

    second_round_successors_by_reviewed: dict[Any, dict[str, Any]] = {}
    if parsed["revid"] >= SECOND_ROUND_EVIDENCE_REVISION:
        successor_payload = _load_second_round_evidence_reconciliation()
        for record in successor_payload["second_round_reconciliations"]:
            reviewed_key = factual_key_from_dict(
                record["reviewed_factual_key"],
                "second-round successor reviewed factual key",
            )
            if reviewed_key in second_round_successors_by_reviewed:
                raise RehearsalError(
                    "duplicate reviewed second-round successor factual identity"
                )
            second_round_successors_by_reviewed[reviewed_key] = record

    drift: list[str] = []
    for round_name in (FIRST_ROUND, SECOND_ROUND):
        previous_keys: set[Any] = set()
        for event in previous_by_round[round_name]:
            try:
                previous_keys.add(
                    exact_factual_key(
                        event,
                        sample_scope=event.get("sample_scope", "reported"),
                    )
                )
            except ValueError:
                # Non-French legacy candidates cannot match a reviewed French
                # source row and are irrelevant to this provenance comparison.
                continue
        reviewed_by_key = {
            exact_factual_key(record, sample_scope="reported"): record
            for record in reviewed[round_name]
        }
        incoming_by_key = {
            exact_factual_key(record, sample_scope="reported"): record
            for record in source_records[round_name]
        }
        missing = []
        for reviewed_key in set(reviewed_by_key) - set(incoming_by_key):
            replacement = reviewed_replacements.get((round_name, reviewed_key))
            if replacement is not None:
                incoming_key = factual_key_from_dict(
                    replacement["incoming_factual_key"],
                    "reviewed reconciliation incoming factual key",
                )
                incoming = incoming_by_key.get(incoming_key)
                if (
                    incoming is None
                    or incoming["source_url"]
                    != replacement["incoming_source_url"]
                ):
                    missing.append(reviewed_key)
                continue

            successor = (
                second_round_successors_by_reviewed.get(reviewed_key)
                if round_name == SECOND_ROUND
                else None
            )
            if successor is not None:
                incoming_key = factual_key_from_dict(
                    successor["incoming_factual_key"],
                    "second-round successor incoming factual key",
                )
                incoming = incoming_by_key.get(incoming_key)
                if (
                    incoming is None
                    or incoming["source_url"]
                    != successor["incoming_source_url"]
                ):
                    missing.append(reviewed_key)
                continue

            missing.append(reviewed_key)
        missing.sort()
        if missing:
            drift.append(
                f"reviewed {round_name} factual identities missing or changed: "
                + ", ".join(_factual_key_label(key) for key in missing)
            )
        changed_sources = sorted(
            key
            for key in set(reviewed_by_key) & set(incoming_by_key)
            if key not in previous_keys
            if reviewed_by_key[key]["source_url"]
            != incoming_by_key[key]["source_url"]
            if not _is_reviewed_accepted_source_refresh(
                key,
                reviewed_by_key[key]["source_url"],
                incoming_by_key[key]["source_url"],
            )
        )
        if changed_sources:
            drift.append(
                f"reviewed {round_name} provenance changed: "
                + ", ".join(_factual_key_label(key) for key in changed_sources)
            )

    reviewed_rejected = {
        _reviewed_rejected_row_signature(record) for record in reviewed["rejected"]
    }
    incoming_rejected = {
        _reviewed_rejected_row_signature(record)
        for record in source_records["rejected"]
    }
    missing_rejected = sorted(reviewed_rejected - incoming_rejected)
    if missing_rejected:
        drift.append(
            "reviewed fail-closed row identity/provenance changed: "
            + ", ".join(
                f"{pollster}:{start}..{end}:n={sample}:{reason}"
                for pollster, start, end, sample, _source, reason in missing_rejected
            )
        )
    if drift:
        raise SourceDriftError(
            "French polling semantic/evidence drift: " + "; ".join(drift)
        )


def reconcile_french_production_source(
    parsed: dict[str, Any],
    previous_first: list[dict[str, Any]],
    previous_second: list[dict[str, Any]],
    *,
    registry: dict[str, Any] | None = None,
) -> RehearsalResult:
    """Apply the one-time audit baseline, then admit new valid French rows.

    Exact factual identities may retain a prior event.  Review anchors are
    consulted only to reject near matches that require an explicit registry
    decision; they never select or merge an event.
    """

    source_records = _assert_production_source_structure(parsed)
    migration_registry = registry or load_migration_registry()
    validate_migration_registry(migration_registry)
    validate_poll_events(previous_first)
    for event in previous_second:
        validate_second_round_event(event)
    previous_by_round = {
        FIRST_ROUND: previous_first,
        SECOND_ROUND: previous_second,
    }
    _assert_reviewed_post_audit_semantics(
        parsed,
        source_records,
        previous_by_round,
        migration_registry,
    )
    previous_ids = {
        round_name: {event["event_id"] for event in events}
        for round_name, events in previous_by_round.items()
    }
    if any(
        len(previous_ids[round_name]) != len(previous_by_round[round_name])
        for round_name in (FIRST_ROUND, SECOND_ROUND)
    ):
        raise RehearsalError("previous polling corpus contains duplicate event IDs")

    for round_name in (FIRST_ROUND, SECOND_ROUND):
        required = {
            record["event_id"]
            for record in migration_registry["persistence_obligations"][round_name]
        }
        if not required <= previous_ids[round_name]:
            raise RehearsalError(
                f"{round_name} persistence obligation is missing from prior corpus"
            )

    audited = parse_french_frozen_fixture(
        load_mediawiki_fixture(FRENCH_FIXTURE, FRENCH_REVISION)
    )
    audited_by_locator = {
        record["source_locator"]: record
        for round_name in (FIRST_ROUND, SECOND_ROUND)
        for record in audited[round_name]
    }
    reviewed_post_audit = parse_french_frozen_fixture(
        load_mediawiki_fixture(
            REVIEWED_POST_AUDIT_FRENCH_FIXTURE,
            REVIEWED_POST_AUDIT_FRENCH_REVISION,
        )
    )
    reviewed_post_audit_by_key = {
        round_name: {
            exact_factual_key(record, sample_scope="reported"): record
            for record in reviewed_post_audit[round_name]
        }
        for round_name in (FIRST_ROUND, SECOND_ROUND)
    }
    mapping_by_incoming: dict[Any, dict[str, Any]] = {}
    for section in (
        "source_only_identity_migrations",
        "reviewed_reconciliations",
    ):
        for record in migration_registry[section]:
            key = factual_key_from_dict(
                record["incoming_factual_key"],
                f"{section} incoming factual key",
            )
            if key in mapping_by_incoming:
                raise RehearsalError("ambiguous registry incoming factual identity")
            mapping_by_incoming[key] = record

    successor_payload = _load_second_round_evidence_reconciliation()
    second_round_evidence_state = (
        _classify_second_round_evidence_lifecycle(
            previous_second,
            successor_payload,
        )
    )

    second_round_successors_by_incoming: dict[Any, dict[str, Any]] = {}
    second_round_successors_by_reviewed: dict[Any, dict[str, Any]] = {}

    for record in successor_payload["second_round_reconciliations"]:
        reviewed_key = factual_key_from_dict(
            record["reviewed_factual_key"],
            "second-round successor reviewed factual key",
        )
        if reviewed_key in second_round_successors_by_reviewed:
            raise RehearsalError(
                "duplicate reviewed second-round successor factual identity"
            )
        second_round_successors_by_reviewed[reviewed_key] = record

        if parsed["revid"] >= SECOND_ROUND_EVIDENCE_REVISION:
            incoming_key = factual_key_from_dict(
                record["incoming_factual_key"],
                "second-round successor incoming factual key",
            )
            if incoming_key in second_round_successors_by_incoming:
                raise RehearsalError(
                    "duplicate incoming second-round successor factual identity"
                )
            second_round_successors_by_incoming[incoming_key] = record

    audited_second_round_by_key: dict[Any, dict[str, Any]] = {}
    for audited_record in audited[SECOND_ROUND]:
        audited_key = exact_factual_key(
            audited_record,
            sample_scope="reported",
        )
        if audited_key not in second_round_successors_by_reviewed:
            continue
        if audited_key in audited_second_round_by_key:
            raise RehearsalError(
                "duplicate audited reviewed second-round factual identity"
            )
        audited_second_round_by_key[audited_key] = audited_record

    if (
        set(audited_second_round_by_key)
        != set(second_round_successors_by_reviewed)
    ):
        raise RehearsalError(
            "second-round evidence reviewed keys do not match "
            "the audited historical fixture"
        )

    historical_second_round_evidence_replay = False

    if (
        parsed["revid"] < SECOND_ROUND_EVIDENCE_REVISION
        and second_round_evidence_state == "applied"
    ):
        reviewed_rows_seen: set[Any] = set()

        for source_record in source_records[SECOND_ROUND]:
            reviewed_key = exact_factual_key(
                source_record,
                sample_scope="reported",
            )

            if reviewed_key not in second_round_successors_by_reviewed:
                continue

            if reviewed_key in reviewed_rows_seen:
                raise SourceDriftError(
                    "historical second-round evidence row is duplicated"
                )

            trusted = audited_second_round_by_key[reviewed_key]

            if (
                source_record["source_url"] != trusted["source_url"]
                or source_record["source_locator"]
                != trusted["source_locator"]
            ):
                raise SourceDriftError(
                    "historical second-round evidence provenance changed"
                )

            reviewed_rows_seen.add(reviewed_key)

        expected_reviewed_rows = set(
            second_round_successors_by_reviewed
        )

        if reviewed_rows_seen != expected_reviewed_rows:
            raise SourceDriftError(
                "historical second-round evidence replay is incomplete"
            )

        historical_second_round_evidence_replay = True

    addition_by_audited_key: dict[Any, dict[str, Any]] = {}
    for round_name in (FIRST_ROUND, SECOND_ROUND):
        for record in migration_registry["french_additions"][round_name]:
            audited_record = audited_by_locator[record["source_locator"]]
            raw_key = exact_factual_key(audited_record, sample_scope="reported")
            if raw_key in addition_by_audited_key:
                raise RehearsalError("ambiguous audited addition factual identity")
            addition_by_audited_key[raw_key] = record

    identity_skip_keys = {
        exact_factual_key(
            audited_by_locator[record["source_locator"]],
            sample_scope="reported",
        )
        for record in migration_registry["identity_skips"]
    }
    audited_rejected = {
        _reviewed_rejected_row_signature(record) for record in audited["rejected"]
    }
    incoming_rejected = {
        _reviewed_rejected_row_signature(record)
        for record in source_records["rejected"]
    }
    missing_rejections = audited_rejected - incoming_rejected
    if missing_rejections:
        raise SourceDriftError(
            "an audited fail-closed French row disappeared or changed identity"
        )

    exact_indexes = {
        round_name: _current_exact_index(events, round_name)
        for round_name, events in previous_by_round.items()
    }
    known_anchors: set[Any] = set()
    for record in audited_by_locator.values():
        try:
            known_anchors.add(review_anchor(record))
        except ValueError:
            pass
    for events in previous_by_round.values():
        for event in events:
            try:
                known_anchors.add(review_anchor(event))
            except ValueError:
                pass

    reconciled = {
        FIRST_ROUND: copy.deepcopy(previous_first),
        SECOND_ROUND: copy.deepcopy(previous_second),
    }
    mapped = {
        "source_only": {FIRST_ROUND: 0, SECOND_ROUND: 0},
        "reviewed": {FIRST_ROUND: 0, SECOND_ROUND: 0},
    }
    exact_retained = {FIRST_ROUND: 0, SECOND_ROUND: 0}
    audited_additions_present = {FIRST_ROUND: 0, SECOND_ROUND: 0}
    audited_additions_introduced = {FIRST_ROUND: 0, SECOND_ROUND: 0}
    normal_additions = {FIRST_ROUND: 0, SECOND_ROUND: 0}
    reviewed_canonical_introduced = {FIRST_ROUND: 0, SECOND_ROUND: 0}
    ambiguous_skips = 0
    second_round_evidence_actions = {
        "retain_existing": 0,
        "correct_retained_sample": 0,
        "supersede_event": 0,
    }
    second_round_evidence_already_applied = {
        "retain_existing": 0,
        "correct_retained_sample": 0,
        "supersede_event": 0,
    }
    superseded_second_round_event_ids: set[str] = set()
    classified_canonical_keys: set[Any] = set()
    source_keys: set[Any] = set()

    for round_name in (FIRST_ROUND, SECOND_ROUND):
        for source_record in source_records[round_name]:
            raw_key = exact_factual_key(source_record, sample_scope="reported")
            if raw_key in source_keys:
                raise SourceDriftError("French source contains a duplicate factual row")
            source_keys.add(raw_key)
            if raw_key in identity_skip_keys:
                ambiguous_skips += 1
                continue

            if (
                round_name == SECOND_ROUND
                and historical_second_round_evidence_replay
                and raw_key in second_round_successors_by_reviewed
            ):
                record = second_round_successors_by_reviewed[raw_key]

                canonical = factual_key_from_dict(
                    record["canonical_factual_key"],
                    "historical second-round replay canonical factual key",
                )

                if canonical in classified_canonical_keys:
                    raise RehearsalError(
                        "duplicate canonical factual identity"
                    )

                classified_canonical_keys.add(canonical)
                second_round_evidence_already_applied[
                    record["action"]
                ] += 1
                continue

            if (
                round_name == SECOND_ROUND
                and raw_key in second_round_successors_by_incoming
            ):
                record = second_round_successors_by_incoming[raw_key]

                if (
                    parsed["revid"] == SECOND_ROUND_EVIDENCE_REVISION
                    and source_record["source_locator"]
                    != record["source_locator"]
                ):
                    raise SourceDriftError(
                        "reviewed second-round successor locator changed "
                        "inside the audited revision"
                    )

                if (
                    source_record["source_url"]
                    != record["incoming_source_url"]
                ):
                    raise SourceDriftError(
                        f"{source_record['source_locator']} reviewed "
                        "second-round successor provenance changed"
                    )

                previous_key = factual_key_from_dict(
                    record["previous_event_factual_key"],
                    "second-round successor previous factual key",
                )
                canonical = factual_key_from_dict(
                    record["canonical_factual_key"],
                    "second-round successor canonical factual key",
                )

                if canonical in classified_canonical_keys:
                    raise RehearsalError(
                        "duplicate canonical factual identity"
                    )
                classified_canonical_keys.add(canonical)

                previous_id = record["previous_event_id"]
                action = record["action"]

                current_by_id = {
                    event["event_id"]: event
                    for event in reconciled[SECOND_ROUND]
                }

                if action == "retain_existing":
                    retained = current_by_id.get(previous_id)
                    if retained is None:
                        raise RehearsalError(
                            "reviewed second-round retained event is absent"
                        )

                    retained_key = exact_factual_key(
                        retained,
                        sample_scope=retained.get(
                            "sample_scope",
                            "reported",
                        ),
                    )
                    if retained_key not in {previous_key, canonical}:
                        raise RehearsalError(
                            "reviewed second-round retained event facts changed"
                        )

                elif action == "correct_retained_sample":
                    retained = current_by_id.get(previous_id)
                    if retained is None:
                        raise RehearsalError(
                            "reviewed second-round sample correction "
                            "references an absent event"
                        )

                    retained_key = exact_factual_key(
                        retained,
                        sample_scope=retained.get(
                            "sample_scope",
                            "reported",
                        ),
                    )
                    if retained_key not in {previous_key, canonical}:
                        raise RehearsalError(
                            "reviewed second-round sample correction "
                            "starts from unexpected facts"
                        )

                    retained["sample_size"] = canonical.sample_size
                    retained["sample_scope"] = canonical.sample_scope

                    corrected_key = exact_factual_key(
                        retained,
                        sample_scope=retained["sample_scope"],
                    )
                    if corrected_key != canonical:
                        raise RehearsalError(
                            "reviewed second-round sample correction "
                            "did not produce canonical facts"
                        )

                    validate_second_round_event(retained)

                elif action == "supersede_event":
                    replacement_id = record["replacement_event_id"]
                    old_event = current_by_id.get(previous_id)
                    replacement = current_by_id.get(replacement_id)

                    if old_event is not None and replacement is not None:
                        raise RehearsalError(
                            "reviewed second-round supersession contains "
                            "both old and replacement event IDs"
                        )

                    if old_event is not None:
                        old_key = exact_factual_key(
                            old_event,
                            sample_scope=old_event.get(
                                "sample_scope",
                                "reported",
                            ),
                        )
                        if old_key != previous_key:
                            raise RehearsalError(
                                "reviewed second-round supersession starts "
                                "from unexpected facts"
                            )

                        replacement = _make_normal_second_event(
                            source_record
                        )

                        if replacement["event_id"] != replacement_id:
                            raise RehearsalError(
                                "reviewed second-round replacement event ID changed"
                            )

                        replacement_key = exact_factual_key(
                            replacement,
                            sample_scope=replacement.get(
                                "sample_scope",
                                "reported",
                            ),
                        )
                        if replacement_key != canonical:
                            raise RehearsalError(
                                "reviewed second-round replacement facts changed"
                            )

                        reconciled[SECOND_ROUND] = [
                            event
                            for event in reconciled[SECOND_ROUND]
                            if event["event_id"] != previous_id
                        ]
                        reconciled[SECOND_ROUND].append(replacement)

                        previous_ids[SECOND_ROUND].discard(previous_id)
                        previous_ids[SECOND_ROUND].add(replacement_id)
                        superseded_second_round_event_ids.add(previous_id)

                    elif replacement is not None:
                        replacement_key = exact_factual_key(
                            replacement,
                            sample_scope=replacement.get(
                                "sample_scope",
                                "reported",
                            ),
                        )
                        if replacement_key != canonical:
                            raise RehearsalError(
                                "reviewed second-round replacement "
                                "event facts changed"
                            )

                    else:
                        raise RehearsalError(
                            "reviewed second-round supersession has "
                            "neither old nor replacement event"
                        )

                else:
                    raise RehearsalError(
                        "unsupported second-round evidence action"
                    )

                second_round_evidence_actions[action] += 1
                continue

            if raw_key in mapping_by_incoming:
                record = mapping_by_incoming[raw_key]
                if (
                    "incoming_source_revision" in record
                    and source_record["source_url"]
                    != record["incoming_source_url"]
                ):
                    raise SourceDriftError(
                        f"{source_record['source_locator']} reviewed mapping provenance changed"
                    )
                canonical = factual_key_from_dict(
                    record["canonical_factual_key"], "mapping canonical factual key"
                )
                if canonical in classified_canonical_keys:
                    raise RehearsalError("duplicate canonical factual identity")
                classified_canonical_keys.add(canonical)
                retained_id = record["retained_event_id"]
                if retained_id not in previous_ids[round_name]:
                    old_key = factual_key_from_dict(
                        record["old_factual_key"], "mapping old factual key"
                    )
                    reviewed_source = reviewed_post_audit_by_key[round_name].get(
                        canonical
                    )
                    if (
                        round_name != FIRST_ROUND
                        or record["treatment"]
                        != "retain_id_reviewed_correction"
                        or record.get("materialize_absent_canonical") is not True
                        or old_key != canonical
                        or reviewed_source is None
                    ):
                        raise RehearsalError(
                            "reviewed mapping references an absent retained event ID"
                        )
                    canonical_source = copy.deepcopy(reviewed_source)
                    canonical_source["source_locator"] = source_record[
                        "source_locator"
                    ]
                    if (
                        exact_factual_key(
                            canonical_source, sample_scope="reported"
                        )
                        != canonical
                    ):
                        raise RehearsalError(
                            "reviewed post-audit canonical factual identity changed"
                        )
                    event = _make_normal_first_event(canonical_source)
                    if event["event_id"] != retained_id:
                        raise RehearsalError(
                            "reviewed post-audit canonical event ID changed"
                        )
                    reconciled[round_name].append(event)
                    previous_ids[round_name].add(retained_id)
                    reviewed_canonical_introduced[round_name] += 1
                category = (
                    "reviewed"
                    if record["treatment"] == "retain_id_reviewed_correction"
                    else "source_only"
                )
                mapped[category][round_name] += 1
                continue

            if raw_key in addition_by_audited_key:
                record = addition_by_audited_key[raw_key]
                canonical = factual_key_from_dict(
                    record["factual_key"], "addition canonical factual key"
                )
                if canonical in classified_canonical_keys:
                    raise RehearsalError("duplicate canonical factual identity")
                classified_canonical_keys.add(canonical)
                maker = (
                    _make_first_addition
                    if round_name == FIRST_ROUND
                    else _make_second_addition
                )
                event = maker(source_record, record)
                audited_additions_present[round_name] += 1
                if event["event_id"] not in previous_ids[round_name]:
                    reconciled[round_name].append(event)
                    previous_ids[round_name].add(event["event_id"])
                    audited_additions_introduced[round_name] += 1
                continue

            exact_matches = exact_indexes[round_name].get(raw_key, [])
            if len(exact_matches) > 1:
                raise RehearsalError("exact factual identity maps to multiple prior events")
            if len(exact_matches) == 1:
                if raw_key in classified_canonical_keys:
                    raise RehearsalError("duplicate canonical factual identity")
                classified_canonical_keys.add(raw_key)
                exact_retained[round_name] += 1
                continue

            anchor = review_anchor(source_record)
            if anchor in known_anchors:
                raise RehearsalError(
                    "unregistered French row shares a review anchor; explicit mapping required"
                )
            maker = (
                _make_normal_first_event
                if round_name == FIRST_ROUND
                else _make_normal_second_event
            )
            event = maker(source_record)
            if raw_key in classified_canonical_keys:
                raise RehearsalError("duplicate canonical factual identity")
            classified_canonical_keys.add(raw_key)
            if event["event_id"] in previous_ids[round_name]:
                raise RehearsalError("new French event unexpectedly duplicates a prior ID")
            reconciled[round_name].append(event)
            previous_ids[round_name].add(event["event_id"])
            normal_additions[round_name] += 1

    first_events = sorted(
        reconciled[FIRST_ROUND],
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize_identity(event["pollster"]),
            event["scenario_key"],
            event["event_id"],
        ),
    )
    second_events = sorted(
        reconciled[SECOND_ROUND],
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize_identity(event["pollster"]),
            event["matchup_key"],
            event["event_id"],
        ),
    )
    validate_poll_events(first_events)
    for event in second_events:
        validate_second_round_event(event)
    for round_name, events, original in (
        (FIRST_ROUND, first_events, previous_first),
        (SECOND_ROUND, second_events, previous_second),
    ):
        ids = [event["event_id"] for event in events]
        if len(ids) != len(set(ids)):
            raise RehearsalError(f"duplicate {round_name} event IDs after reconciliation")
        original_ids = {event["event_id"] for event in original}
        missing_original_ids = original_ids - set(ids)

        if round_name == SECOND_ROUND:
            missing_original_ids -= superseded_second_round_event_ids

        if missing_original_ids:
            raise RehearsalError(
                f"{round_name} historical event ID loss"
            )

    exact_second = [
        exact_factual_key(
            event, sample_scope=event.get("sample_scope", "reported")
        )
        for event in second_events
    ]
    if len(exact_second) != len(set(exact_second)):
        raise RehearsalError("duplicate exact runoff factual identities")

    report = {
        "status": "passed",
        "source_revision": parsed["revid"],
        "parsed": {
            FIRST_ROUND: len(source_records[FIRST_ROUND]),
            SECOND_ROUND: len(source_records[SECOND_ROUND]),
        },
        "retained_ids": {
            FIRST_ROUND: len(previous_first),
            SECOND_ROUND: len(previous_second),
        },
        "reconciled": {
            FIRST_ROUND: len(first_events),
            SECOND_ROUND: len(second_events),
        },
        "audited_additions_present": audited_additions_present,
        "audited_additions_introduced": audited_additions_introduced,
        "normal_post_audit_additions": normal_additions,
        "reviewed_canonical_introduced": reviewed_canonical_introduced,
        "second_round_evidence_reconciliations": (
            second_round_evidence_actions
        ),
        "second_round_evidence_already_applied": (
            second_round_evidence_already_applied
        ),
        "superseded_second_round_event_ids": sorted(
            superseded_second_round_event_ids
        ),
        "source_only_migrations": mapped["source_only"],
        "reviewed_reconciliations": mapped["reviewed"],
        "exact_retained": exact_retained,
        "skips": {
            "fail_closed_rows": len(source_records["rejected"]),
            "ambiguous_identity_rows": ambiguous_skips,
        },
        "unexplained_historical_losses": 0,
        "unresolved_accepted_ambiguities": 0,
        "duplicate_canonical_factual_identities": 0,
        "duplicate_runoff_factual_identities": 0,
        "source_structure_drift": [],
    }
    return RehearsalResult(first_events, second_events, report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only FR27 French-source cutover rehearsal."
    )
    parser.add_argument(
        "--frozen",
        action="store_true",
        help=(
            "use audited revision 238906992 and the frozen pre-cutover "
            "203/38 polling corpora"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.frozen:
            parsed = load_mediawiki_fixture(FRENCH_FIXTURE, FRENCH_REVISION)
            current_first, current_second = _read_pre_cutover_corpora()
            result = rehearse_migration(
                parsed,
                current_first=current_first,
                current_second=current_second,
            )
        else:
            parsed = fetch_live_french_parse()
            result = rehearse_migration(parsed)
    except RehearsalError as error:
        print(
            json.dumps(
                {
                    "status": "failed_closed",
                    "source_structure_drift": [str(error)],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(result.report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
