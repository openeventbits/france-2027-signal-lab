"""Bluesky-only public-account evidence; never an electoral or synthetic score."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "1.0"
STALE_AFTER_HOURS = 48
MAX_SAFE_INTEGER = 2**53 - 1
DID = re.compile(r"(?:did:plc:[a-z2-7]{24}|did:web:[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)")
HANDLE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
ROW_KEYS = {"candidate_id", "status", "did", "handle", "display_name", "profile_url",
            "followers_count", "follows_count", "posts_count"}
STATES = {"observed", "unavailable_no_account", "unavailable_account_missing",
          "unavailable_public_web_opt_out"}


class CandidateBlueskyError(ValueError):
    """Untrusted collection or contract: retain the prior valid artifact."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateBlueskyError(message)


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def valid_did(value: Any) -> bool:
    # Only reviewed AT Protocol DID methods; unsupported forms need explicit review.
    return isinstance(value, str) and len(value) <= 2048 and bool(DID.fullmatch(value))


def valid_handle(value: Any) -> bool:
    return (isinstance(value, str) and len(value) <= 253 and bool(HANDLE.fullmatch(value))
            and value.rsplit(".", 1)[-1] not in {
                "alt", "arpa", "example", "internal", "invalid", "local", "localhost", "onion"})


def timestamp(value: Any) -> datetime:
    require(isinstance(value, str) and bool(re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)", value)),
        "timestamp must be UTC ISO text")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CandidateBlueskyError("invalid timestamp") from None


def count(value: Any) -> int:
    require(type(value) is int and 0 <= value <= MAX_SAFE_INTEGER,
            "count must be a non-negative JSON safe integer")
    return value


def validate_mapping(mapping: Any, candidate_ids: set[str] | None = None) -> None:
    require(isinstance(mapping, dict) and set(mapping) == {"schema_version", "accounts"}
            and mapping["schema_version"] == SCHEMA_VERSION
            and isinstance(mapping["accounts"], list), "invalid Bluesky mapping")
    candidates, dids, handles = set(), set(), set()
    for row in mapping["accounts"]:
        require(isinstance(row, dict) and set(row) == {
            "candidate_id", "did", "reviewed_handle", "verification_url", "account_url"},
            "invalid mapping row")
        require(all(text(value) for value in row.values()), "mapping fields must be non-empty text")
        require(valid_did(row["did"]) and valid_handle(row["reviewed_handle"]), "invalid mapped identity")
        require(row["candidate_id"] not in candidates and row["did"] not in dids
                and row["reviewed_handle"] not in handles, "duplicate candidate, DID or handle mapping")
        source = urlsplit(row["verification_url"])
        require(source.scheme == "https" and bool(source.hostname) and not source.username
                and not source.password and not source.query and not source.fragment,
                "invalid first-party verification URL")
        require(row["account_url"] in {
            f'https://bsky.app/profile/{row["reviewed_handle"]}',
            f'https://bsky.app/profile/{row["did"]}'}, "account URL must identify the reviewed account")
        if candidate_ids is not None:
            require(row["candidate_id"] in candidate_ids, "mapping candidate outside canonical registry")
        candidates.add(row["candidate_id"])
        dids.add(row["did"])
        handles.add(row["reviewed_handle"])


def empty_record(candidate_id: str, config: dict | None = None, *,
                 status: str | None = None) -> dict:
    row = dict.fromkeys(sorted(ROW_KEYS))
    row.update(candidate_id=candidate_id, status="unavailable_no_account")
    if config:
        row.update(did=config["did"], status=status or "unavailable_account_missing")
    return row


def validate_candidate_bluesky(payload: Any, *, mapping: Any = None,
                               candidate_ids: set[str] | None = None) -> None:
    require(isinstance(payload, dict) and set(payload) == {
        "schema_version", "provider", "generated_at", "observed_at", "stale_after_hours", "candidates"},
        "invalid Bluesky publication fields")
    require(payload["schema_version"] == SCHEMA_VERSION and payload["provider"] == "bluesky",
            "unsupported Bluesky publication")
    observed = timestamp(payload["observed_at"])
    require(timestamp(payload["generated_at"]) == observed, "generation/observation mismatch")
    require(type(payload["stale_after_hours"]) is int and payload["stale_after_hours"] == STALE_AFTER_HOURS,
            "invalid freshness policy")
    if mapping is not None:
        validate_mapping(mapping, candidate_ids)
    configs = {row["candidate_id"]: row for row in mapping["accounts"]} if mapping is not None else {}
    rows = payload["candidates"]
    require(isinstance(rows, list) and bool(rows), "empty candidate publication")
    seen, dids = set(), set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == ROW_KEYS, "invalid candidate fields")
        cid = row["candidate_id"]
        require(text(cid) and cid not in seen, "invalid/duplicate candidate")
        seen.add(cid)
        require(isinstance(row["status"], str) and row["status"] in STATES, "invalid candidate status")
        if row["status"] == "unavailable_no_account":
            require(row == empty_record(cid) and cid not in configs, "unmapped evidence must be null")
            continue
        require(valid_did(row["did"]) and row["did"] not in dids, "invalid/duplicate published DID")
        dids.add(row["did"])
        if mapping is not None:
            require(cid in configs and row["did"] == configs[cid]["did"], "unreviewed DID")
        if row["status"] != "observed":
            require(row == empty_record(cid, {"did": row["did"]}, status=row["status"]),
                    "unavailable account must suppress profile fields and metrics")
            continue
        require(valid_handle(row["handle"]), "invalid observed handle")
        require(row["display_name"] is None or
                (isinstance(row["display_name"], str) and len(row["display_name"]) <= 640),
                "invalid display name")
        require(row["profile_url"] == f'https://bsky.app/profile/{row["did"]}', "invalid stable profile URL")
        for key in ("followers_count", "follows_count", "posts_count"):
            count(row[key])
    require([row["candidate_id"] for row in rows] == sorted(seen), "candidate rows must be sorted")
    require(set(configs) <= seen, "mapping absent from snapshot")
    if candidate_ids is not None:
        require(seen == candidate_ids, "candidate universe differs from canonical registry")


def candidate_projection(payload: dict, candidate_id: str) -> dict:
    row = next((row for row in payload["candidates"] if row["candidate_id"] == candidate_id), None)
    require(row is not None, "candidate missing from Bluesky snapshot")
    return {**row, **{key: payload[key] for key in ("provider", "observed_at", "stale_after_hours")}}


def validate_candidate_bluesky_projection(row: Any, candidate_id: str) -> None:
    require(isinstance(row, dict) and set(row) == ROW_KEYS | {
        "provider", "observed_at", "stale_after_hours"}, "invalid Bluesky projection")
    require(row["candidate_id"] == candidate_id, "projection candidate mismatch")
    validate_candidate_bluesky({"schema_version": SCHEMA_VERSION, "generated_at": row["observed_at"],
        **{key: row[key] for key in ("provider", "observed_at", "stale_after_hours")},
        "candidates": [{key: row[key] for key in ROW_KEYS}]}, candidate_ids={candidate_id})
