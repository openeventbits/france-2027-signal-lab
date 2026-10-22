"""Three exact 10205 ballot-option supersessions, independent of Batch 2.

Original predecessor objects and their earlier lineage remain frozen in the
hash-pinned review. Weak wave/lineup anchors can reject drift, never select a
correction. No source row can authorize a new or different successor.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from poll_contract import FIRST_ROUND, validate_poll_events
from poll_migration import exact_factual_key, factual_key_from_dict, pollster_identity

REGISTRY = Path(__file__).with_name("fr27_commission_10205_composite_review.json")
REVIEW_SHA256 = "63984973841b138a1c13ab88460e988e49cdf2acb32f0bdb7d28c477c34ed168"
REVIEWED_REVISION = 240570516


def _object_json(value) -> str:
    # Python equality conflates True, 1 and 1.0. Historical snapshots require
    # exact JSON objects, including their numeric representation and types.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_composite_review(path: Path = REGISTRY) -> dict:
    review = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(
        review, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if digest != REVIEW_SHA256:
        raise ValueError("10205 composite review changed; explicit review required")
    old_ids, new_ids = set(), set()
    for decision in review["decisions"]:
        old, new = decision["previous_event"], decision["canonical_event"]
        validate_poll_events([old, new])
        if (old["event_id"] in old_ids or new["event_id"] in new_ids
                or new["supersedes_event_id"] != old["event_id"]
                or old["event_id"] == new["event_id"]):
            raise ValueError("10205 composite lineage collision")
        old_ids.add(old["event_id"])
        new_ids.add(new["event_id"])
    if len(old_ids) != 3 or old_ids & new_ids:
        raise ValueError("10205 composite review must cover exactly three events")
    return review


def _wave(event: dict) -> tuple:
    return (pollster_identity(event["pollster"]), event["fieldwork_start"],
            event["fieldwork_end"], event["round"])


def _anchor(key) -> tuple:
    return (key.pollster_identity, key.fieldwork_start, key.fieldwork_end,
            key.round, tuple(name for name, _ in key.candidates))


@dataclass
class CompositeResult:
    events: list[dict]
    handled: dict = field(default_factory=dict)
    canonical_ids: list[str] = field(default_factory=list)
    superseded_ids: list[str] = field(default_factory=list)
    covered_persistence_ids: list[str] = field(default_factory=list)
    report: dict = field(default_factory=lambda: {"applied": 0, "already_applied": 0})


def reconcile_composite_rn(
    rows: list[dict], revision: int, previous: list[dict], *,
    retain_published_history: bool = False,
) -> CompositeResult:
    result = CompositeResult(copy.deepcopy(previous))
    published = any(e.get("reviewed_correction_id", "").startswith("FR27-10205-C")
                    for e in previous)
    # Earlier frozen replays remain independent. A published correction survives
    # earlier Wikipedia snapshots; reverting its predecessor is never allowed.
    if not retain_published_history or (revision < REVIEWED_REVISION and not published):
        return result
    validate_poll_events(previous)
    review = load_composite_review()
    decisions = review["decisions"]
    wave = _wave(decisions[0]["previous_event"])
    by_id = {e["event_id"]: e for e in result.events}
    if len(by_id) != len(result.events):
        raise ValueError("10205 duplicate prior event ID")
    allowed_ids = {d[k]["event_id"] for d in decisions
                   for k in ("previous_event", "canonical_event")}
    if any(_wave(e) == wave and e["event_id"] not in allowed_ids for e in result.events):
        raise ValueError("10205 incompatible or duplicate prior configuration")
    source_wave = [row for row in rows if _wave(row) == wave]
    consumed = set()
    for decision in decisions:
        old, new = decision["previous_event"], decision["canonical_event"]
        old_id, new_id = old["event_id"], new["event_id"]
        if old_id in by_id and new_id in by_id:
            raise ValueError("10205 predecessor and successor are both active")
        current = by_id.get(new_id, by_id.get(old_id))
        if _object_json(current) == _object_json(new):
            result.report["already_applied"] += 1
        elif _object_json(current) == _object_json(old):
            result.events[result.events.index(current)] = copy.deepcopy(new)
            result.superseded_ids.append(old_id)
            result.report["applied"] += 1
        else:
            raise ValueError("10205 predecessor/successor missing or altered")
        variants = [(factual_key_from_dict(v["factual_key"], "10205 source key"),
                     v["source_url"]) for v in decision["source_variants"]]
        anchors = {_anchor(key) for key, _url in variants}
        matches = []
        for row in source_wave:
            key = exact_factual_key(row, sample_scope=row.get("sample_scope", "reported"))
            if _anchor(key) not in anchors:
                continue
            if (key, row["source_url"]) not in variants:
                raise ValueError("10205 reviewed source facts/provenance changed")
            matches.append(row)
        if len(matches) > 1:
            raise ValueError("10205 duplicate source configuration")
        for row in matches:
            locator = row["source_locator"]
            if locator in consumed:
                raise ValueError("10205 duplicate source locator")
            consumed.add(locator)
            result.handled[locator] = exact_factual_key(
                new, sample_scope=new.get("sample_scope", "reported"))
        result.canonical_ids.append(new_id)
        result.covered_persistence_ids.append(old_id)
    if len(consumed) != len(source_wave):
        raise ValueError("10205 unreviewed source configuration")
    validate_poll_events(result.events)
    return result


def reconcile_composite_notice_coverage(registry: dict, events: list[dict]) -> dict:
    """A separate exact identity decision supersedes only 10205's old outcome."""
    from commission_notice_coverage import (
        coverage_summary, is_relevant_notice, unresolved_coverage, validate_notice_coverage,
    )
    review = load_composite_review()
    matches = [n for n in registry["notices"] if n["notice_id"] == "commission:10205"]
    if len(matches) > 1:
        raise ValueError("10205 duplicate notice identity")
    if not matches:
        return coverage_summary(registry)
    notice = matches[0]
    if not is_relevant_notice(notice):
        raise ValueError("10205 reviewed notice relevance changed")
    identities = review["notice_identity_review"]["accepted_identities"]
    exact_notice = any(
        all(notice.get(k) == v for k, v in identity.items() if k != "resolved_urls")
        and notice.get("resolved_url") in identity["resolved_urls"]
        for identity in identities
    )
    expected = sorted((d["canonical_event"] for d in review["decisions"]),
                      key=lambda e: e["event_id"])
    actual = sorted((e for e in events if _wave(e) == _wave(expected[0])),
                    key=lambda e: e["event_id"])
    confirmed = notice.get("classification") == "eligible" or (
        notice.get("classification") == "unsupported"
        and notice.get("classification_reason") == (
            "document confirms 2027 presidential voting intentions, but no "
            "existing notice parser supports this listing"
        )
    )
    if not confirmed:
        notice["coverage"] = unresolved_coverage("reviewed_10205_document_not_confirmed")
    elif not exact_notice:
        notice["coverage"] = unresolved_coverage("reviewed_10205_notice_identity_mismatch")
    elif _object_json(actual) != _object_json(expected):
        notice["coverage"] = unresolved_coverage("reviewed_10205_incomplete_or_changed_configurations")
    else:
        notice["coverage"] = {
            "state": "reconciled", "method": "reviewed_10205_complete_composite_configurations",
            "matched_event_ids": [e["event_id"] for e in expected],
        }
    validate_notice_coverage(notice)
    return coverage_summary(registry)


def prepare_composite_history(
    parsed: dict, previous: list[dict], *, retain_published_history: bool = False,
) -> tuple[list[dict], dict | None]:
    """Validate successors before replaying earlier immutable migrations.

    Two predecessors are themselves canonical results of an earlier reviewed
    migration. Its exact historical contract still runs against the original
    objects. This finite compatibility view is never published: the caller
    reapplies all three checked successors after the historical guards pass.
    No arbitrary successor can masquerade as a historical predecessor.
    """
    published = any(e.get("reviewed_correction_id", "").startswith("FR27-10205-C")
                    for e in previous)
    if not retain_published_history or (parsed["revid"] < REVIEWED_REVISION and not published):
        return previous, None
    from poll_migration import parse_french_frozen_fixture

    rows = parse_french_frozen_fixture(parsed)[FIRST_ROUND]
    checked = reconcile_composite_rn(rows, parsed["revid"], previous,
                                    retain_published_history=True)
    predecessors = {d["canonical_event"]["event_id"]: d["previous_event"]
                    for d in load_composite_review()["decisions"]}
    view = [copy.deepcopy(predecessors.get(e["event_id"], e)) for e in checked.events]
    report = {**checked.report,
              "canonical_event_ids": sorted(checked.canonical_ids),
              "superseded_event_ids": sorted(checked.superseded_ids),
              "decision_id": "FR27-10205-COMPOSITE-RN"}
    return view, {"rows": rows, "report": report}


def finalize_composite_history(state: dict, events: list[dict]) -> list[dict]:
    # prepare_composite_history already validated the published successors and
    # exact source variants. Their review stays effective on older replays;
    # the internal predecessor view must never reactivate those old objects.
    return reconcile_composite_rn(state["rows"], REVIEWED_REVISION, events,
                                 retain_published_history=True).events
