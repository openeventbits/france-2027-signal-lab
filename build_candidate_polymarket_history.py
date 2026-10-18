"""Bounded official CLOB history backfill/incremental update; current snapshot is read-only."""
import argparse
import json
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from build_candidate_signals import atomic_write, load_json
from candidate_candidacy_status import load_candidate_candidacy_status
from candidate_history import HistoryError, require, instant, iso, number, encode, RETENTION_DAYS
from candidate_polymarket_history import build_history, validate_candidate_polymarket_history

API_URL = "https://clob.polymarket.com/prices-history"
FIDELITY_MINUTES = 1440
MAX_REQUEST_SECONDS = 7 * 86400
MAX_BYTES = 1024 * 1024
MAX_POINTS = 10000
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


def fetch_history(token, start, end, *, opener=urlopen, sleep=time.sleep, counters=None):
    require(isinstance(token, str) and token.isascii() and token.isdecimal(), "invalid pinned token")
    params = {"market": token, "startTs": start, "endTs": end, "fidelity": FIDELITY_MINUTES}
    request = Request(API_URL + "?" + urlencode(params), headers={"Accept": "application/json", "User-Agent": "FR27-Signal-Lab/1.0"})
    for attempt in range(3):
        if counters is not None:
            counters["request_count"] += 1
        try:
            with opener(request, timeout=20) as response:
                require(response.status == 200, "unexpected CLOB HTTP status")
                content = response.read(MAX_BYTES + 1)
            require(len(content) <= MAX_BYTES, "CLOB response exceeds size bound")
            return json.loads(content)
        except HTTPError as error:
            error.close()
            if error.code not in RETRYABLE or attempt == 2:
                raise HistoryError(f"CLOB HTTP failure: {error.code}") from error
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            delay = min(int(retry_after), 30) if retry_after.isascii() and retry_after.isdecimal() else 2**attempt
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            if attempt == 2:
                raise HistoryError("CLOB network failure after three attempts") from error
            delay = 2**attempt
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise HistoryError("malformed CLOB JSON") from error
        sleep(delay)


def parse_source(payload, start, end):
    require(isinstance(payload, dict) and set(payload) == {"history"}, "unexpected CLOB response schema")
    raw = payload["history"]
    require(isinstance(raw, list) and len(raw) <= MAX_POINTS, "invalid/oversized CLOB history")
    by_time = {}
    for point in raw:
        require(isinstance(point, dict) and set(point) == {"t", "p"}, "malformed CLOB point")
        t = point["t"]
        require(type(t) is int and 0 <= t <= 253402300799, "invalid CLOB epoch timestamp")
        price = number(point["p"], probability=True)
        if not start <= t <= end:
            continue
        require(t not in by_time or by_time[t] == price, "conflicting duplicate source timestamp")
        by_time[t] = price
    return [{"observed_at": iso(datetime.fromtimestamp(t, timezone.utc)), "implied_probability": by_time[t],
             "source": "clob_prices_history"} for t in sorted(by_time)]


def collect(output="candidate_polymarket_history.json", *, mode="append", snapshot_path="candidate_polymarket.json",
            mapping_path="polymarket_candidate_markets.json", registry_path="candidate_candidacy_status.json",
            fetch=None, check=False):
    require(mode in {"append", "backfill", "incremental"}, "invalid history mode")
    snapshot, mapping = load_json(snapshot_path), load_json(mapping_path)
    ids = {r["candidate_id"] for r in load_candidate_candidacy_status(registry_path)["candidates"]}
    previous = load_json(output) if Path(output).exists() else None
    if check:
        require(previous is not None, "history is missing")
        validate_candidate_polymarket_history(previous, mapping=mapping, candidate_ids=ids, snapshot=snapshot)
        return previous, {"request_count": 0}
    # Validate snapshots, prior history, registry and identity locks before any network request.
    seed = build_history(snapshot, mapping, ids, previous)
    anchor = instant(snapshot["observed_at"])
    cutoff = datetime.combine(anchor.date() - timedelta(days=RETENTION_DAYS - 1), datetime.min.time(), timezone.utc)
    source_points, checked = {}, {}
    report = {"request_count": 0, "mode": mode, "fidelity_minutes": FIDELITY_MINUTES, "candidates": []}
    if fetch is None:
        fetch = lambda token, start, end: fetch_history(token, start, end, counters=report)
    for row in seed["candidates"]:
        if mode == "append" or row["yes_token_id"] is None:
            continue
        start = cutoff
        prior_check = row["source_checked_through"]
        if mode == "incremental" and prior_check:
            if instant(prior_check) == anchor:
                continue
            start = max(cutoff, datetime.combine(instant(prior_check).date() - timedelta(days=1), datetime.min.time(), timezone.utc))
        start_ts, end_ts = int(start.timestamp()), int(anchor.timestamp())
        raw_points, windows, clipped = [], 0, 0
        cursor = start_ts
        try:
            while cursor < end_ts:
                window_end = min(cursor + MAX_REQUEST_SECONDS, end_ts)
                response = fetch(row["yes_token_id"], cursor, window_end)
                parse_source(response, cursor, window_end)
                clipped += sum(not cursor <= p["t"] <= window_end for p in response["history"])
                raw_points.extend(response["history"])
                windows += 1
                if window_end == end_ts:
                    break
                # One second of overlap prevents boundary loss with exclusive time filters.
                cursor = window_end - 1
            points = parse_source({"history": raw_points}, start_ts, end_ts)
        except (ValueError, OSError) as error:
            report["failed_candidate_id"] = row["candidate_id"]
            report["error"] = str(error)
            error.history_report = report
            raise
        cid = row["candidate_id"]
        source_points[cid], checked[cid] = points, iso(anchor)
        report["candidates"].append({"candidate_id": cid, "yes_token_id": row["yes_token_id"],
            "start_at": iso(start), "end_at": iso(anchor), "raw_points": len(raw_points), "request_windows": windows, "outside_chunk_samples": clipped,
            "clipped_outside_window_samples": sum(not start_ts <= p["t"] <= end_ts for p in raw_points),
            "source_daily_points": len({p["observed_at"][:10] for p in points}),
            "first_source_at": points[0]["observed_at"] if points else None,
            "last_source_at": points[-1]["observed_at"] if points else None})
    payload = build_history(snapshot, mapping, ids, previous, source_points=source_points, checked=checked)
    report["published_points"] = sum(len(r["points"]) for r in payload["candidates"])
    report["mapped_candidates"] = sum(r["yes_token_id"] is not None for r in payload["candidates"])
    atomic_write(output, encode(payload))
    return payload, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="candidate_polymarket_history.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--backfill", action="store_true")
    mode.add_argument("--incremental", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        _, report = collect(args.output, mode="backfill" if args.backfill else "incremental" if args.incremental else "append", check=args.check)
    except (ValueError, OSError) as error:
        print(json.dumps({"provider": "polymarket_history", "status": "failed", "error": str(error), "collection": getattr(error, "history_report", None)}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
