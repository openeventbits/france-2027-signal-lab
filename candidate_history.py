"""Low-level UTC retention/validation helpers for three separate provider histories.

No cross-provider values, normalization, scoring or presentation belongs here.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from build_candidate_signals import atomic_write, load_json

RETENTION_DAYS = 90
MAX_SAFE_INTEGER = 2**53 - 1


class HistoryError(ValueError):
    """Untrusted history: preserve the prior artifact and block publication."""


def require(condition, message):
    if not condition:
        raise HistoryError(message)


def instant(value):
    require(isinstance(value, str) and bool(re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)", value)),
        "invalid UTC timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise HistoryError("invalid UTC timestamp") from error


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def number(value, *, probability=False):
    if probability:
        require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                "probability must be finite and within [0, 1]")
    else:
        require(type(value) is int and 0 <= value <= MAX_SAFE_INTEGER,
                "count must be a non-negative safe integer")
    return value


def validate_history(payload, *, provider, identity_fields, value_field,
                     candidate_ids=None, identities=None, probability=False):
    require(isinstance(payload, dict) and set(payload) == {
        "schema_version", "provider", "retention_days", "observed_at", "candidates"},
        "unexpected history envelope")
    require(payload["schema_version"] == "1.0" and payload["provider"] == provider,
            "unexpected history provider/schema")
    require(type(payload["retention_days"]) is int and payload["retention_days"] == RETENTION_DAYS,
            "unexpected retention")
    anchor = instant(payload["observed_at"])
    cutoff = anchor.date() - timedelta(days=RETENTION_DAYS - 1)
    rows = payload["candidates"]
    require(isinstance(rows, list), "history candidates must be an array")
    ids, seen_identities = [], set()
    for row in rows:
        keys = {"candidate_id", "points", *identity_fields}
        if probability:
            keys.update({"source_checked_through", "latest_source_point"})
        require(isinstance(row, dict) and set(row) == keys, "unexpected history row")
        cid = row["candidate_id"]
        require(isinstance(cid, str) and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cid)),
                "invalid candidate ID")
        ids.append(cid)
        identity = tuple(row[k] for k in identity_fields)
        require(all(v is None for v in identity) or all(isinstance(v, str) and v.strip() == v and v for v in identity),
                "partial/invalid history identity")
        if identity[0] is not None:
            require(identity not in seen_identities, "duplicate provider identity")
            seen_identities.add(identity)
        if identities is not None:
            require(identity == identities.get(cid, (None,) * len(identity_fields)), "history mapping identity mismatch")
        points = row["points"]
        require(isinstance(points, list) and len(points) <= RETENTION_DAYS, "invalid/bloated points")
        require(identity[0] is not None or not points, "unmapped identity has points")
        days = []
        for point in points:
            require(isinstance(point, dict) and set(point) == {"observed_at", value_field, *(('source',) if probability else ())},
                    "unexpected history point")
            observed = instant(point["observed_at"])
            require(cutoff <= observed.date() <= anchor.date() and observed <= anchor,
                    "point outside retention/observation window")
            number(point[value_field], probability=probability)
            if probability:
                require(point["source"] in {"clob_prices_history", "fr27_snapshot"}, "unknown price provenance")
            days.append(observed.date())
        require(days == sorted(set(days)), "points must have unique ordered UTC dates")
        if probability and row["latest_source_point"] is not None:
            source = row["latest_source_point"]
            require(isinstance(source, dict) and set(source) == {"observed_at", value_field, "source"}
                    and source["source"] == "clob_prices_history", "invalid latest source point")
            source_time = instant(source["observed_at"])
            require(identity[0] is not None and cutoff <= source_time.date() and source_time <= anchor,
                    "latest source point outside retained observation window")
            number(source[value_field], probability=True)
        if probability and row["source_checked_through"] is not None:
            require(identity[0] is not None and instant(row["source_checked_through"]) <= anchor,
                    "invalid source history watermark")
    require(ids == sorted(set(ids)), "duplicate/unordered candidate IDs")
    if candidate_ids is not None:
        require(set(ids) == set(candidate_ids), "history registry coverage mismatch")


def roll_points(points, additions, *, anchor, value_field, probability=False):
    """Latest successful observation per UTC day, without fabricating empty days."""
    latest = {}
    for point in [*points, *additions]:
        observed = instant(point["observed_at"])
        number(point[value_field], probability=probability)
        require(observed <= anchor, "future history point")
        day = observed.date()
        if day < anchor.date() - timedelta(days=RETENTION_DAYS - 1):
            continue
        previous = latest.get(day)
        if previous and instant(previous["observed_at"]) == observed:
            if probability and previous.get("source") != point.get("source"):
                # CLOB and Gamma are distinct price observations, even at the same second.
                if previous.get("source") == "fr27_snapshot":
                    continue
                if point.get("source") == "fr27_snapshot":
                    latest[day] = dict(point, observed_at=iso(observed))
                    continue
            require(previous[value_field] == point[value_field], "conflicting values at identical timestamp")
            if previous.get("source") == "fr27_snapshot":
                continue
        if previous is None or instant(previous["observed_at"]) <= observed:
            latest[day] = dict(point, observed_at=iso(observed))
    return [latest[day] for day in sorted(latest)]


def delta(points, value_field, days, *, probability=False):
    require(days in (7, 30), "only 7/30-day anchors are defined")
    if not points:
        return None
    times = [instant(p["observed_at"]) for p in points]
    require(times == sorted(set(times)), "delta requires ordered observations")
    for point in points:
        number(point[value_field], probability=probability)
    boundary = times[-1] - timedelta(days=days)
    baselines = [p for p, t in zip(points[:-1], times[:-1]) if t <= boundary]
    if not baselines:
        return None
    change = Decimal(str(points[-1][value_field])) - Decimal(str(baselines[-1][value_field]))
    return float(change * 100) if probability else int(change)


def encode(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def update_file(output, snapshot_path, mapping_path, registry_path, build, validate, *, check=False):
    from pathlib import Path
    from candidate_candidacy_status import load_candidate_candidacy_status
    snapshot, mapping = load_json(snapshot_path), load_json(mapping_path)
    ids = {r["candidate_id"] for r in load_candidate_candidacy_status(registry_path)["candidates"]}
    previous = load_json(output) if Path(output).exists() else None
    if check:
        require(previous is not None, "history is missing")
        validate(previous, mapping=mapping, candidate_ids=ids, snapshot=snapshot)
        return previous
    payload = build(snapshot, mapping, ids, previous)
    # Build/validation completes before the existing fsync + os.replace helper is called.
    atomic_write(output, encode(payload))
    return payload
