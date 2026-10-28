"""Reviewed election scope, independent of immutable polling observations.

Unlisted observations are not_yet_reviewed. Only an exact authenticated entry
can exclude a scenario; dates, names, URLs and scenario keys never classify it.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "poll_election_scope.json"
RETROSPECTIVE = "retrospective_2022_revote"
UNREVIEWED = "not_yet_reviewed"
SCOPES = {RETROSPECTIVE, "presidential_2027_scenario", UNREVIEWED}


class PollScopeError(ValueError):
    pass


def object_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PollScopeError(f"Duplicate scope registry key: {key}")
        result[key] = value
    return result


def load_scope_registry(path=REGISTRY_PATH):
    value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return _validate_registry_schema(value)


def _validate_registry_schema(value):
    if (not isinstance(value, dict) or value.get("schema_version") != "1.0"
            or not isinstance(value.get("events"), dict) or not value["events"]):
        raise PollScopeError("Invalid election scope registry")
    for identifier, record in value["events"].items():
        if not re.fullmatch(r"[a-f0-9]{64}", identifier) or not isinstance(record, dict):
            raise PollScopeError("Invalid scope event identity")
        required = {"scope", "event_sha256", "evidence_url", "evidence_locator", "review_date", "rationale"}
        if set(record) != required or record.get("scope") not in SCOPES:
            raise PollScopeError(f"Invalid scope entry: {identifier}")
        if not re.fullmatch(r"[a-f0-9]{64}", str(record["event_sha256"])):
            raise PollScopeError("Invalid scope observation digest")
        if not isinstance(record["evidence_url"], str):
            raise PollScopeError("Invalid scope evidence URL")
        url = urlsplit(record["evidence_url"])
        if url.scheme != "https" or not url.netloc or url.username or url.password:
            raise PollScopeError("Invalid scope evidence URL")
        try:
            reviewed = date.fromisoformat(record["review_date"])
        except (TypeError, ValueError) as error:
            raise PollScopeError("Invalid scope review date") from error
        if reviewed.isoformat() != record["review_date"]:
            raise PollScopeError("Non-canonical scope review date")
        locator = record["evidence_locator"]
        if (not isinstance(record["rationale"], str) or not record["rationale"].strip()
                or not isinstance(locator, dict) or set(locator) != {"fr", "en"}
                or any(not isinstance(text, str) or not text.strip() for text in locator.values())):
            raise PollScopeError("Missing scope evidence reference")
    return value


def validate_scope_registry(registry, polls, *, require_all=True):
    """Production boundary: every reviewed ID must occur once, unchanged."""
    _validate_registry_schema(registry)
    if not isinstance(polls, list) or any(not isinstance(event, dict) for event in polls):
        raise PollScopeError("Scope validation requires a corpus of observation objects")
    by_id = {}
    for event in polls:
        identifier = event.get("event_id")
        if identifier in by_id:
            raise PollScopeError(f"Duplicate corpus event: {identifier}")
        by_id[identifier] = event
    for identifier, record in registry["events"].items():
        event = by_id.get(identifier)
        if event is None:
            if not require_all:
                continue
            raise PollScopeError(f"Unknown reviewed scope event: {identifier}")
        if event.get("round") != "first_round" or object_digest(event) != record["event_sha256"]:
            raise PollScopeError(f"Reviewed scope observation changed: {identifier}")
    return registry


@lru_cache(maxsize=1)
def _registry():
    return validate_scope_registry(load_scope_registry(),
                                   json.loads((ROOT / "polls.json").read_text(encoding="utf-8")))


def scope_record(event):
    record = _registry()["events"].get(event.get("event_id"))
    if record and object_digest(event) != record["event_sha256"]:
        raise PollScopeError(f"Reviewed scope observation changed: {event.get('event_id')}")
    return copy.deepcopy(record) if record else {"scope": UNREVIEWED}


def default_2027_eligible(event):
    return scope_record(event)["scope"] != RETROSPECTIVE


def browser_script():
    """Publish only the reviewed IDs, scopes and exact original observations.

    Full-object comparisons in the browser also reject source/score/ID drift.
    JSON numbers have the same semantics as the raw polling payload.
    """
    polls = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
    registry = validate_scope_registry(load_scope_registry(), polls)
    records = {event["event_id"]: {"scope": registry["events"][event["event_id"]]["scope"], "event": event}
               for event in polls if event["event_id"] in registry["events"]}
    template = (ROOT / "poll_scope_runtime.js").read_text(encoding="utf-8")
    return template.replace("/* REVIEWED_ELECTION_SCOPE */", json.dumps(
        records, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = browser_script()
    target = ROOT / "assets" / "poll-scope.js"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            raise PollScopeError("Election scope browser projection is stale")
    else:
        target.write_text(expected, encoding="utf-8", newline="\n")
    print("Validated reviewed election scope and browser projection")


if __name__ == "__main__":
    main()
