"""Twelve exact Commission reviews and two numeric Batch 2 admissions.

This later live-fetch review leaves frozen extraction and ordinary coverage
matching independent. It never rounds a bounded score, infers a candidate
identity, rewrites a historical event, or authorizes a survey by a weak anchor.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from commission_notice_coverage import (
    coverage_summary, is_relevant_notice, unresolved_coverage,
    validate_notice_coverage, matches_reviewed_yougov_identity_variant,
)
from fetch_polls import normalize, validate_second_round_event
from poll_contract import FIRST_ROUND, validate_poll_events
from poll_migration import candidate_identity, pollster_identity


REGISTRY = Path(__file__).with_name("fr27_commission_coverage_batch2.json")
# Canonical JSON protects facts, complete objects, literal bounds and both
# original Cluster17 representations, independently of formatting or EOLs.
REVIEW_SHA256 = "2c88cd583370e40f1ff23ddbedb9ec79135e12c721f183e89491bfbd2099ea5d"
NOTICE_IDS = frozenset("commission:" + n for n in (
    "10323", "10305", "10277", "10273", "10270", "10264", "10263",
    "10260", "10251", "10250", "10242", "10205",
))


def load_batch2_review(path: Path = REGISTRY) -> dict:
    review = json.loads(Path(path).read_text(encoding="utf-8"))
    encoded = json.dumps(
        review, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != REVIEW_SHA256:
        raise ValueError("Batch 2 evidence changed; explicit review required")
    records = review["notice_reviews"]
    if (len(records) != 12
            or {r["notice_identity"]["notice_id"] for r in records} != NOTICE_IDS):
        raise ValueError("Batch 2 notice identity collection is incomplete")
    seen = set()
    for record in records:
        for event in record["published_events"]:
            if event["event_id"] in seen:
                raise ValueError("Batch 2 published evidence has duplicate identities")
            seen.add(event["event_id"])
            if event["round"] == FIRST_ROUND:
                validate_poll_events([event])
            else:
                validate_second_round_event(event)
    admissions = review["admissions"]
    if len(admissions) != 2 or len({d["decision_id"] for d in admissions}) != 2:
        raise ValueError("Batch 2 requires exactly two reviewed admissions")
    for decision in admissions:
        event = decision["canonical_event"]
        validate_poll_events([event])
        if (decision["previous_event"] is not None
                or event["reviewed_correction_id"] != decision["decision_id"]
                or event["reviewed_notice_id"] != decision["notice_id"]
                or event["event_id"] not in seen):
            raise ValueError("Batch 2 admission identity or lineage changed")
    return review


def _notice_matches(notice: dict, identity: dict) -> bool:
    return (
        all(notice.get(field) == value
            for field, value in identity.items() if field != "resolved_urls")
        and notice.get("resolved_url") in identity["resolved_urls"]
    ) or matches_reviewed_yougov_identity_variant(notice, identity)


def _notice(registry: dict, notice_id: str) -> dict | None:
    matches = [n for n in registry["notices"] if n["notice_id"] == notice_id]
    if len(matches) > 1:
        raise ValueError("Batch 2 duplicate reviewed notice identity")
    return matches[0] if matches else None


def _configuration(event: dict) -> tuple:
    # This anchor can only reject duplicates, never select an admission.
    return (
        pollster_identity(event["pollster"]),
        event["fieldwork_start"], event["fieldwork_end"],
        tuple(sorted(candidate_identity(c["name"]) for c in event["candidates"])),
    )


def admit_batch2_configurations(events: list[dict], registry: dict) -> tuple[list[dict], dict]:
    """Append two complete official tables once; preserve every prior object.

    Called only after successful live French reconciliation and its extraction
    guards. Discovery cannot undo a retained official admission. An alternative
    ID or changed canonical object requires a new review instead of a merge.
    """
    review = load_batch2_review()
    identity = next(r["notice_identity"] for r in review["notice_reviews"]
                    if r["notice_identity"]["notice_id"] == "commission:10260")
    actual = _notice(registry, identity["notice_id"])
    if actual is None or not _notice_matches(actual, identity):
        raise ValueError("Batch 2 admission notice evidence changed or missing")
    validate_poll_events(events)
    result = copy.deepcopy(events)
    report = {"admitted": 0, "already_applied": 0, "decision_ids": []}
    for decision in review["admissions"]:
        canonical = decision["canonical_event"]
        matches = [e for e in result if e["event_id"] == canonical["event_id"]]
        anchor = _configuration(canonical)
        conflicts = [e for e in result
                     if (pollster_identity(e["pollster"]), e["fieldwork_start"], e["fieldwork_end"]) == anchor[:3]
                     and _configuration(e) == anchor]
        if matches:
            if matches != [canonical] or conflicts != matches:
                raise ValueError("Batch 2 admission facts changed or identity collision")
            report["already_applied"] += 1
        else:
            if conflicts:
                raise ValueError("Batch 2 admission configuration identity collision")
            result.append(copy.deepcopy(canonical))
            report["admitted"] += 1
        report["decision_ids"].append(decision["decision_id"])
    # Same order as the existing French integration boundary, so the first
    # admission and all subsequent retained-history runs serialize identically.
    result.sort(key=lambda event: (
        -int(event["fieldwork_end"].replace("-", "")),
        -int(event["fieldwork_start"].replace("-", "")),
        normalize(event["pollster"]), event["scenario_key"], event["event_id"],
    ))
    validate_poll_events(result)
    return result, report


def reconcile_batch2_notice_coverage(registry: dict, events: list[dict]) -> dict:
    """Replace coverage only for the twelve exact reviewed source records.

    Full first-round AND runoff collections, including all provenance and
    legacy sample representations, must equal the reviewed snapshots. Paired
    Cluster17 tables are explicitly evidenced; there is no rounding tolerance.
    An unresolved decision cannot become resolved merely by matching a subset.
    """
    review = load_batch2_review()
    for record in review["notice_reviews"]:
        identity = record["notice_identity"]
        notice = _notice(registry, identity["notice_id"])
        if notice is None:
            continue
        if not is_relevant_notice(notice):
            raise ValueError("Batch 2 reviewed notice relevance changed")
        metadata = record["verified_metadata"]
        actual = [e for e in events
                  if pollster_identity(e["pollster"]) == pollster_identity(metadata["institute"])
                  and e["fieldwork_start"] == metadata["fieldwork_start"]
                  and e["fieldwork_end"] == metadata["fieldwork_end"]]
        complete = sorted(actual, key=lambda e: e["event_id"]) == record["published_events"]
        if not _notice_matches(notice, identity):
            coverage = unresolved_coverage("reviewed_notice_identity_mismatch")
        elif not complete:
            coverage = unresolved_coverage("reviewed_notice_incomplete_or_changed_configurations")
        elif record["outcome"] == "unresolved":
            coverage = unresolved_coverage(record["unresolved_method"])
        else:
            coverage = {
                "state": "reconciled",
                "matched_event_ids": [e["event_id"] for e in record["published_events"]],
                "method": "reviewed_notice_complete_configurations_batch2",
            }
        notice["coverage"] = coverage
        validate_notice_coverage(notice)
    return coverage_summary(registry)
