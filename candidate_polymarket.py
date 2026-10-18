"""Narrow Polymarket publication contract; independent of polling/attention."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
EVENT_ID = "79987"
EVENT_SLUG = "next-french-presidential-election"
API_URL = f"https://gamma-api.polymarket.com/events/slug/{EVENT_SLUG}"
SOURCE_URL = f"https://polymarket.com/event/{EVENT_SLUG}"
STALE_AFTER_HOURS = 48
ROW_KEYS = {"candidate_id", "status", "implied_probability", "market_id", "market_slug",
            "outcome_id", "outcome_name", "source_updated_at", "source_url"}
STATES = {"observed", "unavailable_no_market", "unavailable_missing_market",
          "unavailable_market_inactive", "unavailable_price"}


class CandidatePolymarketError(ValueError):
    """A source or publication cannot be trusted; retain the previous artifact."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidatePolymarketError(message)


def timestamp(value: Any) -> datetime:
    require(isinstance(value, str), "timestamp must be UTC text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidatePolymarketError("invalid timestamp") from error
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
            "timestamp must use UTC")
    return parsed


def probability(value: Any) -> float | int | None:
    if value is None:
        return None
    require(type(value) in (float, int) and 0 <= value <= 1 and math.isfinite(value),
            "probability must be a finite number in [0, 1] or null")
    return value


def validate_mapping(mapping: Any, candidate_ids: set[str] | None = None) -> None:
    require(isinstance(mapping, dict) and set(mapping) == {"event_id", "event_slug", "markets"},
            "invalid mapping fields")
    require(mapping["event_id"] == EVENT_ID and mapping["event_slug"] == EVENT_SLUG,
            "unexpected configured event")
    require(isinstance(mapping["markets"], list) and bool(mapping["markets"]), "empty mapping")
    ids, markets, tokens = set(), set(), set()
    for row in mapping["markets"]:
        require(isinstance(row, dict) and set(row) == {
            "candidate_id", "market_id", "market_slug", "outcome_id", "outcome_name", "group_item_title"
        }, "invalid mapping row")
        require(all(isinstance(v, str) and v.strip() == v and v for v in row.values()),
                "mapping identifiers must be non-empty text")
        require(row["outcome_name"] == "Yes", "only reviewed YES outcomes are supported")
        require(row["market_id"].isdecimal() and row["outcome_id"].isdecimal(), "invalid stable identifier")
        require(row["market_slug"].startswith("will-") and "/" not in row["market_slug"], "invalid market slug")
        require(row["candidate_id"] not in ids and row["market_id"] not in markets
                and row["outcome_id"] not in tokens, "duplicate mapping")
        if candidate_ids is not None:
            require(row["candidate_id"] in candidate_ids, "mapping candidate outside canonical registry")
        ids.add(row["candidate_id"])
        markets.add(row["market_id"])
        tokens.add(row["outcome_id"])


def validate_candidate_polymarket(payload: Any, *, mapping: Any = None,
                                  candidate_ids: set[str] | None = None) -> None:
    require(isinstance(payload, dict) and set(payload) == {
        "schema_version", "provider", "event_id", "event_slug", "source_url", "generated_at",
        "observed_at", "source_updated_at", "stale_after_hours", "candidates", "ignored_markets"
    }, "invalid publication fields")
    require(payload["schema_version"] == SCHEMA_VERSION and payload["provider"] == "polymarket",
            "unsupported publication")
    require(payload["event_id"] == EVENT_ID and payload["event_slug"] == EVENT_SLUG
            and payload["source_url"] == SOURCE_URL, "unexpected published event")
    observed = timestamp(payload["observed_at"])
    require(timestamp(payload["generated_at"]) == observed, "generation/observation mismatch")
    require(payload["stale_after_hours"] == STALE_AFTER_HOURS, "invalid freshness policy")
    if payload["source_updated_at"] is not None:
        require(timestamp(payload["source_updated_at"]) <= observed, "future event timestamp")
    rows = payload["candidates"]
    require(isinstance(rows, list) and bool(rows), "empty candidate publication")
    seen, seen_markets = set(), set()
    if mapping is not None:
        validate_mapping(mapping, candidate_ids)
    by_candidate = {r["candidate_id"]: r for r in mapping["markets"]} if mapping else {}
    for row in rows:
        require(isinstance(row, dict) and set(row) == ROW_KEYS, "invalid candidate fields")
        cid = row["candidate_id"]
        require(isinstance(cid, str) and bool(cid) and cid not in seen, "invalid/duplicate candidate")
        seen.add(cid)
        require(isinstance(row["status"], str) and row["status"] in STATES, "invalid candidate status")
        probability(row["implied_probability"])
        require((row["status"] == "observed") == (row["implied_probability"] is not None),
                "unavailable must be null; observed must have a price")
        if row["status"] == "unavailable_no_market":
            require(all(row[k] is None for k in ROW_KEYS - {"candidate_id", "status"}),
                    "unmapped candidate must have null evidence")
            require(cid not in by_candidate, "configured candidate marked unmapped")
            continue
        require(all(isinstance(row[k], str) and row[k] for k in
                    ("market_id", "market_slug", "outcome_id", "outcome_name", "source_url")),
                "mapped candidate lacks identifiers")
        require(row["market_id"].isdecimal() and row["outcome_id"].isdecimal()
                and row["outcome_name"] == "Yes", "invalid published outcome")
        require(row["source_url"] == f'{SOURCE_URL}/{row["market_slug"]}', "invalid source link")
        require(row["market_id"] not in seen_markets, "duplicate published market")
        seen_markets.add(row["market_id"])
        if row["source_updated_at"] is not None:
            require(timestamp(row["source_updated_at"]) <= observed, "future market timestamp")
        if mapping is not None:
            require(cid in by_candidate and all(row[k] == by_candidate[cid][k] for k in
                    ("market_id", "market_slug", "outcome_id", "outcome_name")), "unreviewed mapping")
    require([r["candidate_id"] for r in rows] == sorted(seen), "candidates must be sorted")
    require(set(by_candidate) <= seen, "reviewed mappings absent from publication")
    if candidate_ids is not None:
        require(seen == candidate_ids, "candidate publication differs from registry")
    ignored = payload["ignored_markets"]
    require(isinstance(ignored, list), "ignored markets must be inspectable")
    ignored_ids = []
    for row in ignored:
        require(isinstance(row, dict) and set(row) == {"market_id", "name", "reason"}, "invalid ignored market")
        require(isinstance(row["market_id"], str) and row["market_id"].isdecimal()
                and isinstance(row["name"], str) and bool(row["name"])
                and row["reason"] == "unreviewed_market", "invalid ignored identity")
        require(row["market_id"] not in seen_markets, "mapped market also ignored")
        ignored_ids.append(row["market_id"])
    require(ignored_ids == sorted(set(ignored_ids)), "ignored markets must be sorted and unique")


def validate_candidate_polymarket_projection(row: Any, candidate_id: str) -> None:
    require(isinstance(row, dict) and set(row) == ROW_KEYS | {
        "provider", "event_id", "observed_at", "stale_after_hours"
    }, "invalid candidate projection fields")
    require(row["candidate_id"] == candidate_id, "projection candidate mismatch")
    validate_candidate_polymarket({
        "schema_version": SCHEMA_VERSION, "provider": row["provider"], "event_id": row["event_id"],
        "event_slug": EVENT_SLUG, "source_url": SOURCE_URL, "generated_at": row["observed_at"],
        "observed_at": row["observed_at"], "source_updated_at": None,
        "stale_after_hours": row["stale_after_hours"],
        "candidates": [{key: row[key] for key in ROW_KEYS}], "ignored_markets": [],
    }, candidate_ids={candidate_id})


def candidate_record(payload: dict, candidate_id: str) -> dict:
    """A new registry candidate absent from an older snapshot is unavailable."""
    for row in payload["candidates"]:
        if row["candidate_id"] == candidate_id:
            return row
    return {**dict.fromkeys(ROW_KEYS), "candidate_id": candidate_id, "status": "unavailable_no_market"}
