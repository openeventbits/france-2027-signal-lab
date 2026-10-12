"""Exact reviewed first-round corrections, separate from the cutover audit.

Neither review anchors nor numerical tolerances select a correction. Reviewed
revisions record provenance; later rows must match the exact locator, URL and
complete factual key, regardless of unrelated page edits.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from poll_contract import (
    FIRST_ROUND, apply_completeness_contract, make_event_id, make_scenario_key,
    validate_poll_events,
)
from poll_migration import exact_factual_key, factual_key_from_dict, review_anchor


REGISTRY = Path(__file__).with_name("fr27_post_audit_first_round_corrections.json")
RECORD_FIELDS = {
    "source_locator", "incoming_source_revisions", "historical_source_revision",
    "source_url", "previous_event_id", "canonical_event_id",
    "previous_hypothesis", "canonical_hypothesis", "old_factual_key",
    "incoming_factual_key", "canonical_factual_key", "canonical_candidates",
    "action", "evidence_urls", "review_reason", "official_page",
}
SOURCE_VARIANT_FIELDS = {"source_variants", "historical_incoming_factual_key"}
CONSOLIDATION_FIELDS = RECORD_FIELDS - {
    "previous_event_id", "previous_hypothesis", "old_factual_key",
    "historical_source_revision",
} | {"predecessors"}
PREDECESSOR_FIELDS = {
    "event_id", "hypothesis", "factual_key", "source_url", "source_revision",
    "source_locator", "review_reason", "evidence_urls", "official_page",
}
MAX_REVIEWED_PREDECESSORS = 8
EXCLUSION_FIELDS = {
    "source_locator", "source_revisions", "source_url", "factual_key",
    "review_reason",
}
ACCEPTANCE_FIELDS = RECORD_FIELDS - {
    "previous_event_id", "previous_hypothesis", "old_factual_key",
    "historical_source_revision",
} | {"historical_withheld_source"}


def _url(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("correction URL must be HTTP(S)")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
        raise ValueError("correction URL must be HTTP(S)")


def _revisions(value: object) -> list[int]:
    if (
        not isinstance(value, list) or not value
        or any(type(item) is not int or item <= 238906992 for item in value)
        or value != sorted(set(value))
    ):
        raise ValueError("correction revisions must be explicit sorted post-audit IDs")
    return value


def _provenance(record: dict, revisions_field: str) -> list[int]:
    if not isinstance(record["source_locator"], str) or not re.fullmatch(
        r"FR-T\d+R\d+", record["source_locator"]
    ):
        raise ValueError("correction source locator is malformed")
    _url(record["source_url"])
    if not isinstance(record["review_reason"], str) or not record["review_reason"].strip():
        raise ValueError("correction review reason must be non-empty")
    return _revisions(record[revisions_field])


def _predecessor_projection(record: dict, predecessor: dict) -> dict:
    """Validate shared contracts through the existing one-predecessor schema."""
    return {
        **{key: value for key, value in record.items() if key != "predecessors"},
        "action": "supersede_event",
        "previous_event_id": predecessor["event_id"],
        "previous_hypothesis": predecessor["hypothesis"],
        "old_factual_key": predecessor["factual_key"],
        "historical_source_revision": predecessor["source_revision"],
    }


def _validate_predecessors(record: dict) -> list[dict]:
    predecessors = record["predecessors"]
    if not isinstance(predecessors, list) or not 2 <= len(predecessors) <= MAX_REVIEWED_PREDECESSORS:
        raise ValueError("consolidation requires a bounded explicit predecessor collection")
    ids = set()
    canonical = factual_key_from_dict(record["canonical_factual_key"], "consolidation canonical key")
    for predecessor in predecessors:
        if not isinstance(predecessor, dict) or set(predecessor) != PREDECESSOR_FIELDS:
            raise ValueError("consolidation predecessor fields are malformed")
        if not isinstance(predecessor["event_id"], str) or not re.fullmatch(r"[a-f0-9]{64}", predecessor["event_id"]):
            raise ValueError("consolidation predecessor ID is malformed")
        if predecessor["event_id"] in ids:
            raise ValueError("duplicate consolidation predecessor ID")
        ids.add(predecessor["event_id"])
        _provenance({**predecessor, "source_revisions": [predecessor["source_revision"]]}, "source_revisions")
        old = factual_key_from_dict(predecessor["factual_key"], "consolidation predecessor key")
        if (
            (old.round, old.pollster_identity, old.fieldwork_start, old.fieldwork_end,
             old.sample_size, old.sample_scope)
            != (canonical.round, canonical.pollster_identity, canonical.fieldwork_start,
                canonical.fieldwork_end, canonical.sample_size, canonical.sample_scope)
            or not set(old.candidates) < set(canonical.candidates)
            or predecessor["source_url"] != record["source_url"]
            or predecessor["evidence_urls"] != record["evidence_urls"]
            or predecessor["official_page"] != record["official_page"]
        ):
            raise ValueError("consolidation predecessor contradicts reviewed canonical evidence")
        # Each exact ID, historical revision, hypothesis and factual key must
        # also satisfy every existing scalar supersession validation rule.
        validate_corrections({"schema_version": "1.0", "corrections": [
            _predecessor_projection(record, predecessor)
        ], "excluded_source_rows": []})
    return predecessors


def validate_corrections(payload: object) -> dict:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "corrections", "excluded_source_rows"}
        or payload["schema_version"] != "1.0"
        or not isinstance(payload["corrections"], list)
        or not isinstance(payload["excluded_source_rows"], list)
    ):
        raise ValueError("post-audit first-round correction schema is malformed")
    locators, incoming_keys, previous_ids, canonical_ids = set(), set(), set(), set()
    for record in payload["corrections"]:
        predecessors = []
        if isinstance(record, dict) and record.get("action") == "consolidate_events":
            if set(record) - {"source_variants"} != CONSOLIDATION_FIELDS:
                raise ValueError("consolidation correction fields are malformed")
            predecessors = _validate_predecessors(record)
            record = _predecessor_projection(record, predecessors[0])
        acceptance = isinstance(record, dict) and record.get("action") == "accept_reviewed_sample"
        if not isinstance(record, dict) or set(record) - SOURCE_VARIANT_FIELDS != (ACCEPTANCE_FIELDS if acceptance else RECORD_FIELDS):
            raise ValueError("post-audit first-round correction fields are malformed")
        revisions = _provenance(record, "incoming_source_revisions")
        if acceptance:
            historical = record["historical_withheld_source"]
            validate_corrections({
                "schema_version": "1.0", "corrections": [],
                "excluded_source_rows": [historical],
            })
            if (
                max(historical["source_revisions"]) >= min(revisions)
                or historical["source_url"] != record["source_url"]
                or historical["factual_key"] != record["incoming_factual_key"]
            ):
                raise ValueError("acceptance historical withholding contradicts reviewed source")
        else:
            historical = record["historical_source_revision"]
            if type(historical) is not int or not 238906992 < historical < min(revisions):
                raise ValueError("correction historical revision is malformed")
        locator = record["source_locator"]
        if locator in locators:
            raise ValueError("duplicate correction source locator")
        locators.add(locator)
        old, incoming, canonical = (
            factual_key_from_dict(record.get(field, record["incoming_factual_key"]), field)
            for field in ("old_factual_key", "incoming_factual_key", "canonical_factual_key")
        )
        if any(key.round != FIRST_ROUND for key in (old, incoming, canonical)):
            raise ValueError("correction factual keys must be first-round")
        if incoming in incoming_keys:
            raise ValueError("duplicate correction incoming factual key")
        incoming_keys.add(incoming)
        for field, seen in (("previous_event_id", previous_ids), ("canonical_event_id", canonical_ids)):
            if acceptance and field == "previous_event_id":
                continue
            value = record[field]
            if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValueError("correction event ID is malformed")
            if value in seen:
                raise ValueError("ambiguous correction event target")
            seen.add(value)
        for predecessor in predecessors[1:]:
            if predecessor["event_id"] in previous_ids:
                raise ValueError("ambiguous correction predecessor target")
            previous_ids.add(predecessor["event_id"])
        for key in (incoming, canonical):
            if (key.pollster_identity, key.fieldwork_start, key.fieldwork_end) != (
                old.pollster_identity, old.fieldwork_start, old.fieldwork_end
            ):
                raise ValueError("correction changes pollster or fieldwork")
        if old.candidates != incoming.candidates and not (
            record["action"] == "supersede_event" and incoming.candidates == canonical.candidates
        ):
            raise ValueError("reviewed source refresh changes non-sample facts")
        variants = record.get("source_variants", [])
        if not isinstance(variants, list):
            raise ValueError("correction source variants are malformed")
        variant_revisions = set()
        for variant in variants:
            if (not isinstance(variant, dict) or set(variant) != {"first_revision", "source_locator"}
                    or type(variant["first_revision"]) is not int
                    or variant["first_revision"] not in revisions
                    or variant["first_revision"] in variant_revisions
                    or not isinstance(variant["source_locator"], str)
                    or not re.fullmatch(r"FR-T\d+R\d+", variant["source_locator"])):
                raise ValueError("correction source variant provenance is malformed")
            variant_revisions.add(variant["first_revision"])
        if "historical_incoming_factual_key" in record:
            if acceptance:
                raise ValueError("acceptance cannot contain historical correction facts")
            historical_key = factual_key_from_dict(record["historical_incoming_factual_key"], "historical source key")
            if (historical_key.pollster_identity, historical_key.fieldwork_start, historical_key.fieldwork_end,
                    historical_key.sample_size, historical_key.sample_scope, historical_key.candidates) != (
                    old.pollster_identity, old.fieldwork_start, old.fieldwork_end,
                    old.sample_size, old.sample_scope, incoming.candidates):
                raise ValueError("historical source key changes reviewed facts")
        candidates = record["canonical_candidates"]
        if (
            not isinstance(candidates, list) or len(candidates) < 2
            or any(
                not isinstance(candidate, dict) or set(candidate) != {"name", "score"}
                or not isinstance(candidate["name"], str) or not candidate["name"].strip()
                for candidate in candidates
            )
        ):
            raise ValueError("canonical candidate fields are malformed")
        candidate_key = exact_factual_key({
            "round": FIRST_ROUND, "pollster": canonical.pollster_identity,
            "fieldwork_start": canonical.fieldwork_start,
            "fieldwork_end": canonical.fieldwork_end,
            "sample_size": canonical.sample_size, "sample_scope": canonical.sample_scope,
            "candidates": record["canonical_candidates"],
        })
        if candidate_key != canonical:
            raise ValueError("canonical candidates contradict canonical factual key")
        hypothesis = "French source — " + ", ".join(
            candidate["name"] for candidate in record["canonical_candidates"]
        )
        if record["canonical_hypothesis"] != hypothesis:
            raise ValueError("canonical hypothesis contradicts candidate lineup")
        for prefix, key in (("previous", old), ("canonical", canonical)):
            if acceptance and prefix == "previous":
                continue
            hypothesis = record[prefix + "_hypothesis"]
            if not isinstance(hypothesis, str) or not hypothesis.strip():
                raise ValueError("correction hypothesis is malformed")
            expected = make_event_id(
                key.pollster_identity, key.fieldwork_start, key.fieldwork_end,
                hypothesis, record["source_url"],
            )
            if record[prefix + "_event_id"] != expected:
                raise ValueError("correction event ID is not deterministic")
        action = record["action"]
        if acceptance:
            if incoming.candidates != canonical.candidates:
                raise ValueError("reviewed sample acceptance changes candidate facts")
        elif action == "correct_retained_sample":
            if (
                old.candidates != canonical.candidates
                or record["previous_event_id"] != record["canonical_event_id"]
                or record["previous_hypothesis"] != record["canonical_hypothesis"]
            ):
                raise ValueError("retained sample correction changes scenario identity")
        elif action == "supersede_event":
            if (
                {name for name, _ in old.candidates} == {name for name, _ in canonical.candidates}
                or record["previous_event_id"] == record["canonical_event_id"]
            ):
                raise ValueError("supersession must explicitly change candidate identity")
        else:
            raise ValueError("correction action is unsupported")
        if type(record["official_page"]) is not int or record["official_page"] <= 0:
            raise ValueError("correction official page is malformed")
        evidence = record["evidence_urls"]
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("correction evidence URLs must be non-empty")
        for url in evidence:
            _url(url)
    if (previous_ids & canonical_ids) != {
        record["previous_event_id"] for record in payload["corrections"]
        if record["action"] == "correct_retained_sample"
    }:
        raise ValueError("correction targets form an ambiguous identity chain")
    for record in payload["excluded_source_rows"]:
        if not isinstance(record, dict) or set(record) != EXCLUSION_FIELDS:
            raise ValueError("excluded source row fields are malformed")
        _provenance(record, "source_revisions")
        key = factual_key_from_dict(record["factual_key"], "excluded factual key")
        if key.round != FIRST_ROUND:
            raise ValueError("excluded source row must be first-round")
        if record["source_locator"] in locators or key in incoming_keys:
            raise ValueError("duplicate or ambiguous excluded source row")
        locators.add(record["source_locator"])
        incoming_keys.add(key)
    return payload


def _withheld_matches(rows: list[dict], record: dict) -> set[str]:
    key = factual_key_from_dict(record["factual_key"], "excluded source factual key")
    excluded_anchor = (
        key.pollster_identity, key.fieldwork_start, key.fieldwork_end,
        tuple(name for name, _ in key.candidates),
    )
    excluded = set()
    for row in rows:
        anchor = review_anchor(row)
        if (
            row["source_url"] == record["source_url"]
            or row["source_locator"] == record["source_locator"]
            or (anchor.pollster_identity, anchor.fieldwork_start, anchor.fieldwork_end,
                anchor.candidate_ids) == excluded_anchor
        ):
            # Weak anchors only reject changed evidence; they never authorize it.
            if (
                row["source_locator"] != record["source_locator"]
                or row["source_url"] != record["source_url"]
                or exact_factual_key(row, sample_scope=row.get("sample_scope", "reported")) != key
            ):
                raise ValueError("withheld first-round source representation changed")
            excluded.add(row["source_locator"])
    return excluded


def load_corrections(path: Path | str = REGISTRY) -> dict:
    return validate_corrections(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class CorrectionResult:
    events: list[dict]
    handled: dict[str, object]
    excluded: set[str]
    report: dict


def _consolidate_reviewed_events(record: dict, events: dict, report: dict) -> None:
    """Allow only the complete reviewed before-state or complete after-state."""
    predecessors = record["predecessors"]
    ids = sorted(predecessor["event_id"] for predecessor in predecessors)
    canonical_id = record["canonical_event_id"]
    canonical_key = factual_key_from_dict(record["canonical_factual_key"], "canonical consolidation key")
    present = [identity for identity in ids if identity in events]
    canonical = events.get(canonical_id)
    if canonical is not None:
        if present:
            raise ValueError("consolidation contains both event identities")
        if (
            exact_factual_key(canonical) != canonical_key
            or canonical["source_url"] != record["source_url"]
            or canonical["hypothesis"] != record["canonical_hypothesis"]
            or canonical.get("supersedes_event_ids") != ids
            or "supersedes_event_id" in canonical
        ):
            raise ValueError("consolidation canonical facts/provenance/continuity changed")
        report["already_applied"] += 1
    else:
        if present != ids:
            raise ValueError("reviewed consolidation is missing a predecessor or successor")
        for predecessor in predecessors:
            event = events[predecessor["event_id"]]
            if (
                exact_factual_key(event) != factual_key_from_dict(predecessor["factual_key"], "predecessor key")
                or event["hypothesis"] != predecessor["hypothesis"]
                or event["source_url"] != predecessor["source_url"]
                or event.get("migration_source_locator") != predecessor["source_locator"]
            ):
                raise ValueError("reviewed consolidation predecessor facts/provenance changed")
        corrected = copy.deepcopy(events[predecessors[0]["event_id"]])
        corrected.update({
            "event_id": canonical_id, "hypothesis": record["canonical_hypothesis"],
            "candidates": copy.deepcopy(record["canonical_candidates"]),
            "scenario_key": make_scenario_key(c["name"] for c in record["canonical_candidates"]),
            "supersedes_event_ids": ids,
        })
        corrected.pop("supersedes_event_id", None)
        apply_completeness_contract(corrected)
        validate_poll_events([corrected])
        if exact_factual_key(corrected) != canonical_key:
            raise ValueError("consolidation did not produce reviewed canonical facts")
        for identity in ids:
            del events[identity]
        events[canonical_id] = corrected
        report["superseded_event_ids"].extend(ids)
        report["consolidate_events"] += 1
    if any(identity in events for identity in ids) or canonical_id not in events:
        raise ValueError("consolidation did not replace every reviewed predecessor")


def _make_reviewed_source_event(source_record: dict) -> dict:
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


def reconcile_first_round_corrections(
    rows: list[dict], revision: int, previous: list[dict], *, registry: dict | None = None,
) -> CorrectionResult:
    registry = validate_corrections(registry) if registry is not None else load_corrections()
    validate_poll_events(previous)
    events = {event["event_id"]: copy.deepcopy(event) for event in previous}
    if len(events) != len(previous):
        raise ValueError("duplicate prior first-round event ID")
    handled, excluded = {}, set()
    report = {
        "correct_retained_sample": 0, "supersede_event": 0, "already_applied": 0,
        "accept_reviewed_sample": 0,
        "consolidate_events": 0,
        "canonical_event_ids": [], "superseded_event_ids": [], "excluded_source_rows": 0,
    }
    rows_by_locator = {row["source_locator"]: row for row in rows}
    if len(rows_by_locator) != len(rows):
        raise ValueError("duplicate incoming first-round locator")
    # Require an exact decision for every row in a registered correction wave,
    # including rows moved away from their reviewed locator or mutated facts.
    wave_keys = {
        (record["incoming_factual_key"]["pollster_identity"],
         record["incoming_factual_key"]["fieldwork_start"],
         record["incoming_factual_key"]["fieldwork_end"])
        for record in registry["corrections"]
    }
    from poll_migration import pollster_identity
    wave_rows = {
        row["source_locator"] for row in rows
        if (pollster_identity(row["pollster"]), row["fieldwork_start"], row["fieldwork_end"])
        in wave_keys
    }
    for record in registry["corrections"]:
        acceptance = record["action"] == "accept_reviewed_sample"
        consolidation = record["action"] == "consolidate_events"
        if acceptance and revision < min(record["incoming_source_revisions"]):
            historical = record["historical_withheld_source"]
            if revision >= min(historical["source_revisions"]):
                excluded.update(_withheld_matches(rows, historical))
            continue
        # Positions are reviewed provenance, never a fallback for changed facts.
        variants = [v for v in record.get("source_variants", []) if revision >= v["first_revision"]]
        locator = max(variants, key=lambda v: v["first_revision"])["source_locator"] if variants else record["source_locator"]
        key = record.get("old_factual_key", record["incoming_factual_key"])
        wave_present = any(
            (pollster_identity(row["pollster"]), row["fieldwork_start"], row["fieldwork_end"])
            == (key["pollster_identity"], key["fieldwork_start"], key["fieldwork_end"])
            for row in rows
        )
        if not wave_present:
            if revision >= min(record["incoming_source_revisions"]):
                raise ValueError("reviewed first-round correction wave is missing")
            continue
        row = rows_by_locator.get(locator)
        expected = (
            record.get("historical_incoming_factual_key", record.get("old_factual_key")) if revision == record.get("historical_source_revision")
            else record["incoming_factual_key"]
        )
        if (
            (revision < min(record["incoming_source_revisions"])
             and revision != record.get("historical_source_revision"))
            or row is None or row["source_url"] != record["source_url"]
            or exact_factual_key(row, sample_scope=row.get("sample_scope", "reported"))
            != factual_key_from_dict(expected, "reviewed incoming first-round key")
        ):
            raise ValueError("reviewed first-round correction source scope/facts changed")
        if acceptance and any(
            other is not row and other["source_url"] == record["source_url"]
            for other in rows
        ):
            raise ValueError("unregistered row in reviewed first-round acceptance source")
        canonical_id = record["canonical_event_id"]
        if consolidation:
            _consolidate_reviewed_events(record, events, report)
            report["canonical_event_ids"].append(canonical_id)
            handled[locator] = factual_key_from_dict(record["canonical_factual_key"], "canonical consolidation key")
            continue
        old_id = record.get("previous_event_id", canonical_id)
        old, canonical = events.get(old_id), events.get(canonical_id)
        if old_id != canonical_id and old is not None and canonical is not None:
            raise ValueError("first-round supersession contains both event identities")
        current = old if old is not None else canonical
        if current is None:
            if not acceptance:
                raise ValueError("reviewed first-round correction is missing its retained event")
            # Construct the source event only after exact reviewed
            # provenance/facts pass; canonical metadata is applied below.
            current = _make_reviewed_source_event(row)
        current_key = exact_factual_key(current, sample_scope=current.get("sample_scope", "reported"))
        canonical_key = factual_key_from_dict(record["canonical_factual_key"], "canonical first-round key")
        old_key = factual_key_from_dict(key, "old first-round key")
        if (
            current["source_url"] != record["source_url"]
            or current_key not in {old_key, canonical_key}
            or (current_key == old_key and (current["event_id"] != old_id
                or current["hypothesis"] != record.get("previous_hypothesis", record["canonical_hypothesis"])))
            or (current_key == canonical_key and (current["event_id"] != canonical_id
                or current["hypothesis"] != record["canonical_hypothesis"]))
        ):
            raise ValueError("reviewed first-round correction starts from unexpected facts")
        if current_key == canonical_key:
            if record["action"] == "supersede_event" and current.get("supersedes_event_id") != old_id:
                raise ValueError("first-round supersession continuity is missing")
            report["already_applied"] += 1
        else:
            corrected = copy.deepcopy(current)
            corrected.update({
                "event_id": canonical_id, "sample_size": canonical_key.sample_size,
                "sample_scope": canonical_key.sample_scope,
                "hypothesis": record["canonical_hypothesis"],
                "candidates": copy.deepcopy(record["canonical_candidates"]),
                "scenario_key": make_scenario_key(c["name"] for c in record["canonical_candidates"]),
            })
            if record["action"] == "supersede_event":
                corrected["supersedes_event_id"] = old_id
                del events[old_id]
                report["superseded_event_ids"].append(old_id)
            corrected = apply_completeness_contract(corrected)
            if exact_factual_key(corrected) != canonical_key:
                raise ValueError("first-round correction did not produce canonical facts")
            validate_poll_events([corrected])
            events[canonical_id] = corrected
            report[record["action"]] += 1
        report["canonical_event_ids"].append(canonical_id)
        handled[locator] = canonical_key
    if wave_rows != set(handled) | excluded:
        raise ValueError("unregistered row in reviewed first-round correction wave")
    for record in registry["excluded_source_rows"]:
        if revision < min(record["source_revisions"]):
            continue
        excluded.update(_withheld_matches(rows, record))
    report["excluded_source_rows"] = len(excluded)
    report["canonical_event_ids"].sort()
    report["superseded_event_ids"].sort()
    return CorrectionResult(list(events.values()), handled, excluded, report)
