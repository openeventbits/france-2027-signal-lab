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
EXCLUSION_FIELDS = {
    "source_locator", "source_revisions", "source_url", "factual_key",
    "review_reason",
}


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
        if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
            raise ValueError("post-audit first-round correction fields are malformed")
        revisions = _provenance(record, "incoming_source_revisions")
        historical = record["historical_source_revision"]
        if type(historical) is not int or not 238906992 < historical < min(revisions):
            raise ValueError("correction historical revision is malformed")
        locator = record["source_locator"]
        if locator in locators:
            raise ValueError("duplicate correction source locator")
        locators.add(locator)
        old, incoming, canonical = (
            factual_key_from_dict(record[field], field)
            for field in ("old_factual_key", "incoming_factual_key", "canonical_factual_key")
        )
        if any(key.round != FIRST_ROUND for key in (old, incoming, canonical)):
            raise ValueError("correction factual keys must be first-round")
        if incoming in incoming_keys:
            raise ValueError("duplicate correction incoming factual key")
        incoming_keys.add(incoming)
        for field, seen in (("previous_event_id", previous_ids), ("canonical_event_id", canonical_ids)):
            value = record[field]
            if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValueError("correction event ID is malformed")
            if value in seen:
                raise ValueError("ambiguous correction event target")
            seen.add(value)
        for key in (incoming, canonical):
            if (key.pollster_identity, key.fieldwork_start, key.fieldwork_end) != (
                old.pollster_identity, old.fieldwork_start, old.fieldwork_end
            ):
                raise ValueError("correction changes pollster or fieldwork")
        if old.candidates != incoming.candidates:
            raise ValueError("reviewed source refresh changes non-sample facts")
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
        if action == "correct_retained_sample":
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


def load_corrections(path: Path | str = REGISTRY) -> dict:
    return validate_corrections(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class CorrectionResult:
    events: list[dict]
    handled: dict[str, object]
    excluded: set[str]
    report: dict


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
        "canonical_event_ids": [], "superseded_event_ids": [], "excluded_source_rows": 0,
    }
    rows_by_locator = {row["source_locator"]: row for row in rows}
    if len(rows_by_locator) != len(rows):
        raise ValueError("duplicate incoming first-round locator")
    # Require an exact decision for every row in a registered correction wave,
    # including rows moved away from their reviewed locator or mutated facts.
    wave_keys = {
        (record["old_factual_key"]["pollster_identity"],
         record["old_factual_key"]["fieldwork_start"],
         record["old_factual_key"]["fieldwork_end"])
        for record in registry["corrections"]
    }
    from poll_migration import pollster_identity
    wave_rows = {
        row["source_locator"] for row in rows
        if (pollster_identity(row["pollster"]), row["fieldwork_start"], row["fieldwork_end"])
        in wave_keys
    }
    for record in registry["corrections"]:
        locator = record["source_locator"]
        key = record["old_factual_key"]
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
            record["old_factual_key"] if revision == record["historical_source_revision"]
            else record["incoming_factual_key"]
        )
        if (
            (revision < min(record["incoming_source_revisions"])
             and revision != record["historical_source_revision"])
            or row is None or row["source_url"] != record["source_url"]
            or exact_factual_key(row, sample_scope=row.get("sample_scope", "reported"))
            != factual_key_from_dict(expected, "reviewed incoming first-round key")
        ):
            raise ValueError("reviewed first-round correction source scope/facts changed")
        old_id, canonical_id = record["previous_event_id"], record["canonical_event_id"]
        old, canonical = events.get(old_id), events.get(canonical_id)
        if old_id != canonical_id and old is not None and canonical is not None:
            raise ValueError("first-round supersession contains both event identities")
        current = old if old is not None else canonical
        if current is None:
            raise ValueError("reviewed first-round correction is missing its retained event")
        current_key = exact_factual_key(current, sample_scope=current.get("sample_scope", "reported"))
        canonical_key = factual_key_from_dict(record["canonical_factual_key"], "canonical first-round key")
        old_key = factual_key_from_dict(record["old_factual_key"], "old first-round key")
        if (
            current["source_url"] != record["source_url"]
            or current_key not in {old_key, canonical_key}
            or (current_key == old_key and (current["event_id"] != old_id
                or current["hypothesis"] != record["previous_hypothesis"]))
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
    if wave_rows != set(handled):
        raise ValueError("unregistered row in reviewed first-round correction wave")
    for record in registry["excluded_source_rows"]:
        if revision < min(record["source_revisions"]):
            continue
        key = factual_key_from_dict(record["factual_key"], "excluded source factual key")
        excluded_anchor = (
            key.pollster_identity, key.fieldwork_start, key.fieldwork_end,
            tuple(name for name, _ in key.candidates),
        )
        matches = []
        for row in rows:
            anchor = review_anchor(row)
            if (
                row["source_url"] == record["source_url"]
                or row["source_locator"] == record["source_locator"]
                or (anchor.pollster_identity, anchor.fieldwork_start, anchor.fieldwork_end,
                    anchor.candidate_ids) == excluded_anchor
            ):
                # A weak anchor can only reject changed withheld evidence; it
                # never authorizes either a correction or a new source event.
                matches.append(row)
        for row in matches:
            if (
                row["source_locator"] != record["source_locator"]
                or row["source_url"] != record["source_url"]
                or exact_factual_key(row, sample_scope=row.get("sample_scope", "reported"))
                != factual_key_from_dict(record["factual_key"], "excluded source factual key")
            ):
                raise ValueError("withheld first-round source representation changed")
            excluded.add(row["source_locator"])
    report["excluded_source_rows"] = len(excluded)
    report["canonical_event_ids"].sort()
    report["superseded_event_ids"].sort()
    return CorrectionResult(list(events.values()), handled, excluded, report)
