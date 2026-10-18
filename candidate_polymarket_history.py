"""YES-token price history, with explicit CLOB versus FR27 snapshot provenance."""
from candidate_history import (require, instant, iso, number, validate_history,
                               roll_points, delta, RETENTION_DAYS)
from candidate_polymarket import validate_candidate_polymarket, validate_mapping


def identities(mapping, candidate_ids=None):
    validate_mapping(mapping, candidate_ids)
    return {r["candidate_id"]: (r["market_id"], r["outcome_id"]) for r in mapping["markets"]}


def validate_candidate_polymarket_history(payload, *, mapping=None, candidate_ids=None, snapshot=None):
    index = identities(mapping, candidate_ids) if mapping is not None else None
    validate_history(payload, provider="polymarket", identity_fields=("market_id", "yes_token_id"),
                     value_field="implied_probability", candidate_ids=candidate_ids,
                     identities=index, probability=True)
    for row in payload["candidates"]:
        for key in ("market_id", "yes_token_id"):
            require(row[key] is None or row[key].isascii() and row[key].isdecimal(), "invalid market/token ID")
    if snapshot is not None:
        validate_candidate_polymarket(snapshot, mapping=mapping, candidate_ids=candidate_ids)
        require(instant(payload["observed_at"]) == instant(snapshot["observed_at"]), "history snapshot timestamp mismatch")
        rows = {r["candidate_id"]: r for r in payload["candidates"]}
        for row in snapshot["candidates"]:
            if row["status"] == "observed":
                points = rows[row["candidate_id"]]["points"]
                require(bool(points) and instant(points[-1]["observed_at"]) == instant(snapshot["observed_at"])
                        and points[-1]["source"] == "fr27_snapshot"
                        and points[-1]["implied_probability"] == row["implied_probability"],
                        "history lacks authoritative current snapshot")


def build_history(snapshot, mapping, candidate_ids, previous=None, *, source_points=None, checked=None):
    validate_candidate_polymarket(snapshot, mapping=mapping, candidate_ids=candidate_ids)
    index = identities(mapping, candidate_ids)
    source_points, checked = source_points or {}, checked or {}
    require(set(source_points) <= set(index) and set(checked) <= set(index), "unreviewed source history candidate")
    anchor = instant(snapshot["observed_at"])
    old = {}
    if previous is not None:
        validate_candidate_polymarket_history(previous)
        require({r["candidate_id"] for r in previous["candidates"]} <= set(candidate_ids),
                "registry removed a historical candidate; explicit review required")
        require(instant(previous["observed_at"]) <= anchor, "snapshot observation moved backwards")
        old = {r["candidate_id"]: r for r in previous["candidates"]}
    rows = []
    for row in sorted(snapshot["candidates"], key=lambda r: r["candidate_id"]):
        cid = row["candidate_id"]
        identity = index.get(cid, (None, None))
        prior = old.get(cid)
        require(not prior or prior["yes_token_id"] is None
                or (prior["market_id"], prior["yes_token_id"]) == identity,
                "Polymarket identity changed; explicit history review required")
        additions = list(source_points.get(cid, []))
        require(all(p.get("source") == "clob_prices_history" for p in additions), "invalid source history provenance")
        if row["status"] == "observed":
            require((row["market_id"], row["outcome_id"]) == identity, "snapshot YES-token mismatch")
            additions.append({"observed_at": iso(anchor), "implied_probability": number(row["implied_probability"], probability=True),
                              "source": "fr27_snapshot"})
        points = roll_points(prior["points"] if prior else [], additions, anchor=anchor,
                             value_field="implied_probability", probability=True)
        source_candidates = list(source_points.get(cid, []))
        if prior and prior["latest_source_point"] is not None:
            source_candidates.append(prior["latest_source_point"])
        latest_sources = roll_points([], source_candidates, anchor=anchor,
                                     value_field="implied_probability", probability=True)
        latest_source = latest_sources[-1] if latest_sources else None
        watermark = checked.get(cid, prior["source_checked_through"] if prior else None)
        if prior and prior["source_checked_through"] and watermark:
            require(instant(watermark) >= instant(prior["source_checked_through"]), "source history watermark regressed")
        rows.append({"candidate_id": cid, "market_id": identity[0], "yes_token_id": identity[1],
                     "source_checked_through": watermark, "latest_source_point": latest_source, "points": points})
    payload = {"schema_version": "1.0", "provider": "polymarket", "retention_days": RETENTION_DAYS,
               "observed_at": iso(anchor), "candidates": rows}
    validate_candidate_polymarket_history(payload, mapping=mapping, candidate_ids=candidate_ids, snapshot=snapshot)
    return payload


def derive_delta(row, days):
    return delta(row["points"], "implied_probability", days, probability=True)
