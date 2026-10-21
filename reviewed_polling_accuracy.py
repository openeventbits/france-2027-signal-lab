"""Nine bounded Batch 1 decisions backed by the original October reports.

This supplements, rather than widens, the older first-round expansion and
ten-record runoff reconciliation contracts. Exact complete prior/canonical
objects authorize mutations; discovery anchors can only reject drift. The
official admissions do not depend on Wikipedia carrying the missing rows.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from fetch_polls import SECOND_ROUND, validate_second_round_event
from poll_contract import FIRST_ROUND, normalize_identity, validate_poll_events
from poll_migration import exact_factual_key, factual_key_from_dict, pollster_identity


REGISTRY = Path(__file__).with_name("fr27_polling_accuracy_batch1.json")
REVIEWED_SOURCE_REVISION = 240562307
# Canonical JSON digest: JSON formatting/EOL changes do not alter this review.
# Changing any authorized fact, predecessor, source variant or evidence requires
# a new explicit review, rather than a more permissive matching rule.
REVIEW_SHA256 = "ecce41bfd0ff61dc30fd8003c8fea2ae5fc43e21743922f735b2b3eda4db207b"


def load_batch1_review(path: Path = REGISTRY) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != REVIEW_SHA256:
        raise ValueError("Batch 1 reviewed decisions changed; explicit review required")
    if payload["reviewed_source_revision"] != REVIEWED_SOURCE_REVISION:
        raise ValueError("Batch 1 reviewed revision changed")
    ids, old_ids = set(), set()
    for record in payload["decisions"]:
        event, old = record["canonical_event"], record["previous_event"]
        validate = validate_poll_events if event["round"] == FIRST_ROUND else lambda es: [validate_second_round_event(e) for e in es]
        validate([event])
        if event["event_id"] in ids:
            raise ValueError("Batch 1 canonical identity collision")
        ids.add(event["event_id"])
        if old is not None:
            validate([old])
            if old["event_id"] in old_ids:
                raise ValueError("Batch 1 predecessor identity collision")
            old_ids.add(old["event_id"])
        if record["action"] == "supersede_runoff_metadata" and (
            event["supersedes_event_id"] != old["event_id"]
            or event["event_id"] == old["event_id"]
            or event["matchup_key"] != old["matchup_key"]
        ):
            raise ValueError("Batch 1 runoff supersession lineage is invalid")
        for variant in record["source_variants"]:
            factual_key_from_dict(variant["factual_key"], "Batch 1 source variant")
    return payload


@dataclass
class AccuracyResult:
    first_round: list[dict]
    second_round: list[dict]
    handled: dict[tuple[str, str], object]
    report: dict


def _anchor(key):
    # A weak anchor never selects an outcome. It only detects conflicting rows
    # for one of the nine exact, individually reviewed configurations.
    return (key.round, key.pollster_identity, key.fieldwork_start,
            key.fieldwork_end, tuple(name for name, _ in key.candidates))


def reconcile_batch1_accuracy(
    rows: dict, revision: int, first: list[dict], second: list[dict], *,
    retain_published_history: bool = False,
) -> AccuracyResult:
    report = {"applied": 0, "already_applied": 0, "admitted": 0,
              "canonical_first_round_ids": [], "superseded_second_round_ids": [],
              "decision_ids": []}
    result = AccuracyResult(copy.deepcopy(first), copy.deepcopy(second), {}, report)
    # Earlier frozen replays remain byte-for-byte independent. Once a reviewed
    # outcome is published, an older discovery snapshot cannot undo it either.
    published = any(e.get("reviewed_correction_id", "").startswith("FR27-B1-")
                    for e in first + second)
    if not retain_published_history or (revision < REVIEWED_SOURCE_REVISION and not published):
        return result
    registry = load_batch1_review()
    events = {FIRST_ROUND: result.first_round, SECOND_ROUND: result.second_round}
    for record in registry["decisions"]:
        canonical, old = record["canonical_event"], record["previous_event"]
        round_name, event_id = canonical["round"], canonical["event_id"]
        current = events[round_name]
        by_id = {e["event_id"]: e for e in current}
        if len(by_id) != len(current):
            raise ValueError("Batch 1 duplicate prior event ID")
        old_id = old["event_id"] if old is not None else None
        if old_id != event_id and old_id in by_id and event_id in by_id:
            raise ValueError("Batch 1 contains both predecessor and successor")
        retained = by_id.get(event_id, by_id.get(old_id))
        if retained == canonical:
            report["already_applied"] += 1
        elif old is not None:
            if retained != old:
                raise ValueError("Batch 1 prior event facts/provenance changed or missing")
            current.remove(retained)
            current.append(copy.deepcopy(canonical))
            report["applied"] += 1
            if old_id != event_id:
                report["superseded_second_round_ids"].append(old_id)
        else:
            if retained is not None:
                raise ValueError("Batch 1 admission canonical object changed")
            current.append(copy.deepcopy(canonical))
            report["admitted"] += 1

        canonical_key = exact_factual_key(canonical)
        # A different ID with the same poll/date/lineup would create a duplicate,
        # even if a URL, candidate order, score or sample change hid it from an
        # exact-key index. Fail closed instead of merging it by inference.
        canonical_anchor = _anchor(canonical_key)
        for other in current:
            if (pollster_identity(other["pollster"]), other["fieldwork_start"], other["fieldwork_end"]) != (
                canonical_key.pollster_identity, canonical_key.fieldwork_start, canonical_key.fieldwork_end
            ):
                continue
            if other["event_id"] != event_id and _anchor(exact_factual_key(other, sample_scope=other.get("sample_scope", "reported"))) == canonical_anchor:
                raise ValueError("Batch 1 configuration identity collision")

        variants = [
            (factual_key_from_dict(v["factual_key"], "Batch 1 source key"), v["source_url"])
            for v in record["source_variants"]
        ]
        anchors = {_anchor(key) for key, _ in variants}
        matches = []
        for row in rows[round_name]:
            key = exact_factual_key(row, sample_scope=row.get("sample_scope", "reported"))
            if _anchor(key) not in anchors:
                continue
            if (key, row["source_url"]) not in variants:
                raise ValueError("Batch 1 reviewed source facts/provenance changed")
            matches.append(row)
        if len(matches) > 1:
            raise ValueError("Batch 1 duplicate source representations")
        for row in matches:
            result.handled[round_name, row["source_locator"]] = canonical_key
        if round_name == FIRST_ROUND:
            report["canonical_first_round_ids"].append(event_id)
        report["decision_ids"].append(record["decision_id"])
    validate_poll_events(result.first_round)
    for event in result.second_round:
        validate_second_round_event(event)
    for field in ("canonical_first_round_ids", "superseded_second_round_ids", "decision_ids"):
        report[field].sort()
    return result


def reconcile_batch1_notice_coverage(registry: dict, events: list[dict]) -> dict:
    """Reconcile only notice 10324 against its complete exact reviewed survey.

    Called after ordinary coverage; this neither changes general wave matching
    nor claims that the notice has an automatic parser. Historical snapshots
    without a Batch 1 Elabe outcome retain their original coverage behavior.
    """
    from commission_notice_coverage import (
        coverage_summary, is_relevant_notice, unresolved_coverage,
        validate_notice_coverage,
    )

    if not any(e.get("reviewed_correction_id") in {"FR27-B1-A", "FR27-B1-B"}
               for e in events):
        return coverage_summary(registry)
    review = load_batch1_review()["notice_coverage_reviews"][0]
    identity = review["notice_identity"]
    for notice in registry["notices"]:
        if notice["notice_id"] != identity["notice_id"] or not is_relevant_notice(notice):
            continue
        metadata = notice.get("survey_metadata", {})
        exact_notice = (
            all(notice.get(field) == identity[field] for field in (
                "notice_id", "content_sha256", "institute", "listed_date",
            ))
            and notice.get("resolved_url") in identity["resolved_urls"]
            and FIRST_ROUND in notice.get("confirmed_rounds", [])
            and all(metadata.get(field) == identity[field]
                    for field in ("fieldwork_start", "fieldwork_end"))
        )
        published = [e for e in events if e.get("round") == FIRST_ROUND
                     and normalize_identity(e.get("pollster", "")) == normalize_identity(identity["institute"])
                     and e.get("fieldwork_start") == identity["fieldwork_start"]
                     and e.get("fieldwork_end") == identity["fieldwork_end"]]
        expected = review["configurations"]
        # Complete objects include source provenance and the historically
        # retained sample representations. A weak wave match cannot authorize
        # an equivalence or hide an extra, missing, or duplicate configuration.
        complete = (len(published) == len(expected)
                    and sorted(published, key=lambda e: e["event_id"]) == expected)
        if exact_notice and complete:
            notice["coverage"] = {
                "state": "reconciled",
                "matched_event_ids": [e["event_id"] for e in expected],
                "method": "reviewed_notice_complete_configurations",
            }
        else:
            notice["coverage"] = unresolved_coverage(
                "reviewed_notice_identity_mismatch" if not exact_notice
                else "reviewed_notice_incomplete_or_changed_configurations"
            )
        validate_notice_coverage(notice)
    return coverage_summary(registry)
