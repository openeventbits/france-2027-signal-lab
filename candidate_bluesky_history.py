"""Durable bluesky observations; no historical API backfill or presentation."""
from candidate_history import (HistoryError, require, instant, iso, number, validate_history,
                               roll_points, delta, RETENTION_DAYS)
from candidate_bluesky import validate_candidate_bluesky, validate_mapping, valid_did


def identities(mapping, candidate_ids=None):
    validate_mapping(mapping, candidate_ids)
    return {r["candidate_id"]: (r["did"],) for r in mapping["accounts"]}


def numeric(row):
    return row["status"] == "observed" and row["followers_count"] is not None


def validate_candidate_bluesky_history(payload, *, mapping=None, candidate_ids=None, snapshot=None):
    index = identities(mapping, candidate_ids) if mapping is not None else None
    validate_history(payload, provider="bluesky", identity_fields=("did",),
                     value_field="followers_count", candidate_ids=candidate_ids, identities=index)
    for row in payload["candidates"]:
        value = row["did"]
        require(value is None or bool(valid_did(value)), "invalid bluesky identity")
    if snapshot is not None:
        validate_candidate_bluesky(snapshot, mapping=mapping, candidate_ids=candidate_ids)
        require(instant(payload["observed_at"]) == instant(snapshot["observed_at"]), "history snapshot timestamp mismatch")
        rows = {r["candidate_id"]: r for r in payload["candidates"]}
        for row in snapshot["candidates"]:
            if numeric(row):
                points = rows[row["candidate_id"]]["points"]
                require(bool(points) and instant(points[-1]["observed_at"]) == instant(snapshot["observed_at"])
                        and points[-1]["followers_count"] == row["followers_count"], "history lacks current observation")


def build_history(snapshot, mapping, candidate_ids, previous=None):
    validate_candidate_bluesky(snapshot, mapping=mapping, candidate_ids=candidate_ids)
    index = identities(mapping, candidate_ids)
    anchor = instant(snapshot["observed_at"])
    old = {}
    if previous is not None:
        validate_candidate_bluesky_history(previous)
        require({r["candidate_id"] for r in previous["candidates"]} <= set(candidate_ids),
                "registry removed a historical candidate; explicit review required")
        require(instant(previous["observed_at"]) <= anchor, "snapshot observation moved backwards")
        old = {r["candidate_id"]: r for r in previous["candidates"]}
    rows = []
    for row in sorted(snapshot["candidates"], key=lambda r: r["candidate_id"]):
        cid = row["candidate_id"]
        identity = index.get(cid, (None,))[0]
        prior = old.get(cid)
        require(not prior or prior["did"] is None or prior["did"] == identity,
                "bluesky identity changed; explicit history review required")
        additions = []
        if numeric(row):
            require(row["did"] == identity, "snapshot identity mismatch")
            additions = [{"observed_at": iso(anchor), "followers_count": number(row["followers_count"])}]
        points = roll_points(prior["points"] if prior else [], additions, anchor=anchor, value_field="followers_count")
        rows.append({"candidate_id": cid, "did": identity, "points": points})
    payload = {"schema_version": "1.0", "provider": "bluesky", "retention_days": RETENTION_DAYS,
               "observed_at": iso(anchor), "candidates": rows}
    validate_candidate_bluesky_history(payload, mapping=mapping, candidate_ids=candidate_ids, snapshot=snapshot)
    return payload


def derive_delta(row, days):
    return delta(row["points"], "followers_count", days)
