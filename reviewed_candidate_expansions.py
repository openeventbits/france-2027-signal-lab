"""Three exact, reviewed first-round candidate-list expansions.

This is deliberately separate from general source matching and the existing
post-audit wave correction registry. No inferred or tolerant matching.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from poll_contract import (
    FIRST_ROUND, apply_completeness_contract,
    make_event_id, make_scenario_key, validate_poll_events,
)
from poll_migration import exact_factual_key


REGISTRY = Path(__file__).with_name(
    "fr27_reviewed_candidate_expansions.json"
)
REVIEWED_REVISION = 240470913

# Notice 10324, methodology p1 and configuration 5 on p8, independently
# matches the original Elabe report (p2/p18). Keep that report URL for IDs.
_ELABE_SOURCE_REFRESH_REVISION = 240485523
_ELABE_REPORT_URL = (
    "https://elabe.fr/fichier-pdf/13329-les-francais-et-lelection-presidentielle-2027/"
)
_ELABE_NOTICE_URL = (
    "https://www.commission-des-sondages.fr/notices/files/notices/2026/"
    "octobre/10324-pres-iv-elabe-17-octobre.pdf"
)

# Immutable identity and single added-fact boundaries.
_EXPECTED = {
    "FR-T0R5": (
        "736b68938b1b45c3c9e3bf61b422c7ba0184f412092d971f955871a195a9a82e",
        "63aecb7f3bd59f50845e47dc628ed7d480330d1a028228561ad2cc6a3bb1afb0",
        "gabriel-attal", "4.5", 18,
    ),
    "FR-T2R10": (
        "ed26935dd3b45aadc1c1e142351b7c357d10f45e2a36219ba6309962b47a4092",
        "97585f1475829d9d8af92d50051dc40d3fc7e515c8c5bed45e8ce8c5c9f50085",
        "marine-tondelier", "5", 13,
    ),
    "FR-T2R11": (
        "3720d46369d9dc9629d3ce8d80bad3740c0b43845c3a8f7e77f2cc4620a7dd08",
        "18c3f04dfcd854092bfaddba00a48f75bb6c129f483507dc9f880a1065657210",
        "marine-tondelier", "4", 12,
    ),
}

_FIELDS = {
    "source_locator", "previous_event", "incoming_row",
    "canonical_event_id", "canonical_hypothesis",
    "added_candidate", "evidence_url", "evidence_page",
}


@dataclass
class ReviewExpansionResult:
    events: list[dict]
    canonical_event_ids: list[str]
    superseded_event_ids: list[str]
    covered_persistence_ids: list[str]
    applied: int
    already_applied: int


def _canonical_event(row: dict, old_id: str) -> dict:
    candidates = copy.deepcopy(row["candidates"])
    hypothesis = "French source — " + ", ".join(
        candidate["name"] for candidate in candidates
    )
    event = {
        "event_id": make_event_id(
            row["pollster"], row["fieldwork_start"],
            row["fieldwork_end"], hypothesis, row["source_url"],
        ),
        "pollster": row["pollster"],
        "commissioner": None,
        "publication_date": None,
        "fieldwork_start": row["fieldwork_start"],
        "fieldwork_end": row["fieldwork_end"],
        "sample_size": row["sample_size"],
        "sample_scope": "reported",
        "round": FIRST_ROUND,
        "hypothesis": hypothesis,
        "scenario_key": make_scenario_key(
            candidate["name"] for candidate in candidates
        ),
        "source_url": row["source_url"],
        "candidates": candidates,
        "migration_source_locator": row["source_locator"],
        "supersedes_event_id": old_id,
    }
    apply_completeness_contract(event)
    validate_poll_events([event])
    return event


def reconcile_reviewed_candidate_expansions(
    rows: list[dict],
    revision: int,
    previous: list[dict],
    *,
    registry_path: Path = REGISTRY,
) -> ReviewExpansionResult:
    payload = json.loads(
        Path(registry_path).read_text(encoding="utf-8")
    )
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "reviewed_revision", "expansions"}
        or payload["schema_version"] != "1.0"
        or type(payload["reviewed_revision"]) is not int
        or payload["reviewed_revision"] != REVIEWED_REVISION
        or not isinstance(payload["expansions"], list)
        or len(payload["expansions"]) != len(_EXPECTED)
    ):
        raise ValueError("Reviewed candidate expansion registry is malformed")

    records = {}
    for record in payload["expansions"]:
        if not isinstance(record, dict) or set(record) != _FIELDS:
            raise ValueError("Reviewed candidate expansion fields are malformed")
        locator = record["source_locator"]
        if locator not in _EXPECTED or locator in records:
            raise ValueError("Unregistered or duplicate expansion locator")
        records[locator] = record

    if set(records) != set(_EXPECTED):
        raise ValueError("Reviewed candidate expansion coverage is incomplete")

    # Earlier frozen fixtures must remain independent of this later review.
    if revision < REVIEWED_REVISION:
        return ReviewExpansionResult(
            copy.deepcopy(previous), [], [], [], 0, 0
        )

    source = {row["source_locator"]: row for row in rows}
    if len(source) != len(rows):
        raise ValueError("Duplicate incoming expansion source locator")

    events = {event["event_id"]: copy.deepcopy(event) for event in previous}
    if len(events) != len(previous):
        raise ValueError("Duplicate historical first-round event ID")

    canonical_ids = []
    superseded_ids = []
    covered_ids = []
    applied = 0
    already_applied = 0

    for locator, spec in _EXPECTED.items():
        old_id, new_id, candidate_id, score, page = spec
        record = records[locator]
        old = record["previous_event"]
        incoming = record["incoming_row"]

        if (
            old["event_id"] != old_id
            or record["canonical_event_id"] != new_id
            or record["added_candidate"] != {
                "candidate_id": candidate_id, "score": score
            }
            or record["evidence_page"] != page
            or record["evidence_url"] != incoming["source_url"]
            or incoming["source_locator"] != locator
        ):
            raise ValueError("Reviewed candidate expansion identity changed")

        current_row = source.get(locator)
        # This exact URL pair is evidence equivalence for this one expansion,
        # not a replacement source for canonical construction below. Every
        # other field, including sample scope and candidate order, must match.
        reviewed_source_refresh = (
            locator == "FR-T0R5"
            and revision >= _ELABE_SOURCE_REFRESH_REVISION
            and incoming["source_url"] == _ELABE_REPORT_URL
            and current_row == {**incoming, "source_url": _ELABE_NOTICE_URL}
        )
        if current_row != incoming and not reviewed_source_refresh:
            raise ValueError(
                "Reviewed candidate expansion source facts/provenance changed: "
                + locator
            )

        validate_poll_events([old])
        old_key = exact_factual_key(old, sample_scope="reported")
        incoming_key = exact_factual_key(
            incoming, sample_scope="reported"
        )

        old_wave = (
            old_key.pollster_identity,
            old_key.fieldwork_start,
            old_key.fieldwork_end,
            old_key.sample_size,
            old_key.sample_scope,
        )
        incoming_wave = (
            incoming_key.pollster_identity,
            incoming_key.fieldwork_start,
            incoming_key.fieldwork_end,
            incoming_key.sample_size,
            incoming_key.sample_scope,
        )

        old_facts = set(old_key.candidates)
        incoming_facts = set(incoming_key.candidates)

        if (
            old_wave != incoming_wave
            or not old_facts < incoming_facts
            or incoming_facts - old_facts != {(candidate_id, score)}
        ):
            raise ValueError(
                "Reviewed candidate expansion changes unapproved facts"
            )

        canonical = _canonical_event(incoming, old_id)

        if (
            canonical["event_id"] != new_id
            or canonical["hypothesis"] != record["canonical_hypothesis"]
            or canonical["reported_total"] != 100
            or canonical["completeness_status"] != "complete"
        ):
            raise ValueError("Reviewed candidate successor is not canonical")

        prior = events.get(old_id)
        successor = events.get(new_id)

        if prior is not None and successor is not None:
            raise ValueError(
                "Reviewed expansion contains both historical and successor IDs"
            )

        if prior is not None:
            if prior != old:
                raise ValueError(
                    "Reviewed expansion historical facts/provenance changed"
                )
            del events[old_id]
            events[new_id] = canonical
            superseded_ids.append(old_id)
            applied += 1
        elif successor is not None:
            if successor != canonical:
                raise ValueError(
                    "Reviewed expansion successor facts/provenance changed"
                )
            already_applied += 1
        else:
            raise ValueError(
                "Reviewed expansion has neither historical nor successor ID"
            )

        canonical_ids.append(new_id)
        # Only a fully validated historical/successor pair can satisfy
        # its historical persistence obligation.
        covered_ids.append(old_id)

    return ReviewExpansionResult(
        list(events.values()),
        sorted(canonical_ids),
        sorted(superseded_ids),
        sorted(covered_ids),
        applied,
        already_applied,
    )
