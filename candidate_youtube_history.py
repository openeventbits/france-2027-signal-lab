"""Durable youtube observations; no historical API backfill or presentation."""
from candidate_history import (HistoryError, require, instant, iso, number, validate_history,
                               roll_points, delta, RETENTION_DAYS)
from candidate_youtube import validate_candidate_youtube, validate_mapping, CHANNEL_ID


def identities(mapping, candidate_ids=None):
    validate_mapping(mapping, candidate_ids)
    return {r["candidate_id"]: (r["channel_id"],) for r in mapping["channels"]}


def numeric(row):
    return row["status"] == "observed" and not row["hidden_subscriber_count"] and row["subscriber_count"] is not None


def validate_candidate_youtube_history(payload, *, mapping=None, candidate_ids=None, snapshot=None):
    index = identities(mapping, candidate_ids) if mapping is not None else None
    validate_history(payload, provider="youtube", identity_fields=("channel_id",),
                     value_field="subscriber_count", candidate_ids=candidate_ids, identities=index)
    for row in payload["candidates"]:
        value = row["channel_id"]
        require(value is None or bool(CHANNEL_ID.fullmatch(value)), "invalid youtube identity")
    if snapshot is not None:
        validate_candidate_youtube(snapshot, mapping=mapping, candidate_ids=candidate_ids)
        require(instant(payload["observed_at"]) == instant(snapshot["observed_at"]), "history snapshot timestamp mismatch")
        rows = {r["candidate_id"]: r for r in payload["candidates"]}
        for row in snapshot["candidates"]:
            if numeric(row):
                points = rows[row["candidate_id"]]["points"]
                require(bool(points) and instant(points[-1]["observed_at"]) == instant(snapshot["observed_at"])
                        and points[-1]["subscriber_count"] == row["subscriber_count"], "history lacks current observation")


def build_history(snapshot, mapping, candidate_ids, previous=None):
    validate_candidate_youtube(snapshot, mapping=mapping, candidate_ids=candidate_ids)
    index = identities(mapping, candidate_ids)
    anchor = instant(snapshot["observed_at"])
    old = {}
    if previous is not None:
        validate_candidate_youtube_history(previous)
        require({r["candidate_id"] for r in previous["candidates"]} <= set(candidate_ids),
                "registry removed a historical candidate; explicit review required")
        require(instant(previous["observed_at"]) <= anchor, "snapshot observation moved backwards")
        old = {r["candidate_id"]: r for r in previous["candidates"]}
    rows = []
    for row in sorted(snapshot["candidates"], key=lambda r: r["candidate_id"]):
        cid = row["candidate_id"]
        identity = index.get(cid, (None,))[0]
        prior = old.get(cid)
        require(not prior or prior["channel_id"] is None or prior["channel_id"] == identity,
                "youtube identity changed; explicit history review required")
        additions = []
        if numeric(row):
            require(row["channel_id"] == identity, "snapshot identity mismatch")
            additions = [{"observed_at": iso(anchor), "subscriber_count": number(row["subscriber_count"])}]
        points = roll_points(prior["points"] if prior else [], additions, anchor=anchor, value_field="subscriber_count")
        rows.append({"candidate_id": cid, "channel_id": identity, "points": points})
    payload = {"schema_version": "1.0", "provider": "youtube", "retention_days": RETENTION_DAYS,
               "observed_at": iso(anchor), "candidates": rows}
    validate_candidate_youtube_history(payload, mapping=mapping, candidate_ids=candidate_ids, snapshot=snapshot)
    return payload


def derive_delta(row, days):
    return delta(row["points"], "subscriber_count", days)
