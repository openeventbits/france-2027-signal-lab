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
FRENCH_PAGE = "Liste de sondages sur l'élection présidentielle française de 2027"
FRENCH_API_URL = "https://fr.wikipedia.org/w/api.php"
POST_AUDIT_HOLLANDE_LE_PEN_TOC_ENTRY = (
    3,
    POST_AUDIT_HOLLANDE_LE_PEN_HEADING,
)
POST_AUDIT_HOLLANDE_LE_PEN_TABLE_SCHEMA = (
    (
        ("sondeur", "3", "1"),
        ("dates", "3", "1"),
        ("echantillon", "3", "1"),
        ("", "1", "1"),
        ("", "1", "1"),
    ),
    (
        ("hollande ps", "1", "1"),
        ("le pen rn", "1", "1"),
    ),
)

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


def _semantic_header_text(cell: object) -> str:
    semantic_cell = copy.deepcopy(cell)
    for reference in semantic_cell.xpath(
        ".//sup[contains(concat(' ', normalize-space(@class), ' '), ' reference ')]"
    ):
        reference.getparent().remove(reference)
    return normalize_identity(semantic_cell.text_content())


def _table_schema_fingerprint(
    parsed: dict[str, Any], *, relevant_table_count: int
) -> tuple[Any, ...]:
    """Describe audited table headers while deliberately ignoring body rows."""

    document = lxml_html.fromstring(parsed["text"])
    tables = document.xpath("//table")
    if len(tables) < relevant_table_count:
        raise SourceDriftError(
            f"French source exposes {len(tables)} tables; "
            f"reviewed parser requires {relevant_table_count}"
        )
    schemas: list[tuple[Any, ...]] = []
    for table_index, table in enumerate(tables[:relevant_table_count]):
        header_rows: list[tuple[Any, ...]] = []
        for row in table.xpath("./thead/tr | ./tbody/tr | ./tr"):
            if row.xpath("./td"):
                break
            cells = row.xpath("./th")
            if not cells:
                continue
            header_rows.append(
                tuple(
                    (
                        _semantic_header_text(cell),
                        cell.get("rowspan", "1"),
                        cell.get("colspan", "1"),
                    )
                    for cell in cells
                )
            )
        if not header_rows:
            raise SourceDriftError(
                f"French table {table_index} lacks an auditable header"
            )
        schemas.append(tuple(header_rows))
    return tuple(schemas)


def _assert_production_source_structure(parsed: dict[str, Any]) -> dict[str, Any]:
    """Allow new body rows but reject unreviewed heading/table schema drift."""

    revision = parsed.get("revid")
    if not isinstance(revision, int) or revision < FRENCH_REVISION:
        raise SourceDriftError(
            f"French source revision {revision!r} predates audited revision {FRENCH_REVISION}"
        )
    audited = load_mediawiki_fixture(FRENCH_FIXTURE, FRENCH_REVISION)
    audited_headings = _relevant_heading_fingerprint(audited)
    ruffin_index = audited_headings.index((3, "hypothese ruffin le pen"))
    reviewed_headings = (
        audited_headings[: ruffin_index + 1]
        + (POST_AUDIT_HOLLANDE_LE_PEN_TOC_ENTRY,)
        + audited_headings[ruffin_index + 1 :]
    )
    incoming_headings = _relevant_heading_fingerprint(parsed)
    if incoming_headings not in {audited_headings, reviewed_headings}:
        raise SourceDriftError("relevant heading hierarchy changed")
    audited_schema = _table_schema_fingerprint(audited, relevant_table_count=17)
    if incoming_headings == audited_headings:
        expected_schema = audited_schema
    else:
        expected_schema = (
            audited_schema[:12]
            + (POST_AUDIT_HOLLANDE_LE_PEN_TABLE_SCHEMA,)
            + audited_schema[12:]
        )
    if _table_schema_fingerprint(
        parsed, relevant_table_count=len(expected_schema)
    ) != expected_schema:
        raise SourceDriftError("French polling table/header schema changed")
    try:
        return parse_french_frozen_fixture(parsed)
    except (TypeError, ValueError) as error:
        raise SourceDriftError(f"French table structure is not auditable: {error}") from error


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
        _rejected_row_signature(record) for record in audited["rejected"]
    }
    incoming_rejected = {
        _rejected_row_signature(record) for record in source_records["rejected"]
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
    ambiguous_skips = 0
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

            if raw_key in mapping_by_incoming:
                record = mapping_by_incoming[raw_key]
                canonical = factual_key_from_dict(
                    record["canonical_factual_key"], "mapping canonical factual key"
                )
                if canonical in classified_canonical_keys:
                    raise RehearsalError("duplicate canonical factual identity")
                classified_canonical_keys.add(canonical)
                retained_id = record["retained_event_id"]
                if retained_id not in previous_ids[round_name]:
                    raise RehearsalError(
                        "reviewed mapping references an absent retained event ID"
                    )
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
        if not original_ids <= set(ids):
            raise RehearsalError(f"{round_name} historical event ID loss")

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
