"""Collect the pinned official Gamma event and atomically publish candidate evidence."""

from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from build_candidate_signals import atomic_write, load_json
from candidate_candidacy_status import load_candidate_candidacy_status
from candidate_polymarket import (
    API_URL, EVENT_ID, EVENT_SLUG, ROW_KEYS, SCHEMA_VERSION, SOURCE_URL,
    STALE_AFTER_HOURS, CandidatePolymarketError, probability, require,
    timestamp, validate_candidate_polymarket, validate_mapping,
)

USER_AGENT = "FR27-Signal-Lab/1.0 (+https://france2027.app/)"
MAX_BYTES = 5 * 1024 * 1024
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


def fetch_event(*, opener=urlopen, sleep=time.sleep):
    """20s timeout, bounded response, three attempts; failures never publish."""
    for attempt in range(3):
        try:
            request = Request(API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with opener(request, timeout=20) as response:
                require(response.status == 200, "unexpected HTTP response")
                raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, "response exceeds byte limit")
            return json.loads(raw)
        except HTTPError as error:
            error.close()
            if error.code not in RETRYABLE or attempt == 2:
                raise CandidatePolymarketError(f"HTTP failure: {error.code}") from error
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            delay = min(float(retry_after), 30) if retry_after.isdecimal() else 2 ** attempt
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            if attempt == 2:
                raise CandidatePolymarketError("network failure after three attempts") from error
            delay = 2 ** attempt
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise CandidatePolymarketError("malformed JSON response") from error
        sleep(delay)


def array(value, field):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as error:
            raise CandidatePolymarketError(f"malformed {field}") from error
    require(isinstance(value, list) and len(value) == 2, f"{field} must be a binary array")
    return value


def build_candidate_polymarket(event, mapping, candidate_ids, observed_at):
    validate_mapping(mapping, candidate_ids)
    observed = timestamp(observed_at)
    observed_at = observed.isoformat().replace("+00:00", "Z")
    require(isinstance(event, dict) and event.get("id") == EVENT_ID
            and event.get("slug") == EVENT_SLUG, "unexpected upstream event")
    require(event.get("active") is True and event.get("closed") is False
            and event.get("archived") is False, "event is not active")
    markets = event.get("markets")
    require(isinstance(markets, list) and bool(markets), "missing/empty upstream markets")
    by_id = {}
    for market in markets:
        require(isinstance(market, dict) and isinstance(market.get("id"), str)
                and market["id"].isdecimal(), "malformed market identity")
        require(market["id"] not in by_id, "duplicate upstream market")
        by_id[market["id"]] = market
    reviewed = {r["candidate_id"]: r for r in mapping["markets"]}
    mapped_market_ids = {r["market_id"] for r in mapping["markets"]}
    ignored = []
    for mid in sorted(set(by_id) - mapped_market_ids):
        name = by_id[mid].get("groupItemTitle")
        require(isinstance(name, str) and bool(name), "unreviewed market lacks inspectable name")
        ignored.append({"market_id": mid, "name": name, "reason": "unreviewed_market"})
    rows = []
    matched = 0
    for cid in sorted(candidate_ids):
        row = dict.fromkeys(ROW_KEYS)
        row.update(candidate_id=cid, status="unavailable_no_market")
        config = reviewed.get(cid)
        if config:
            for key in ("market_id", "market_slug", "outcome_id", "outcome_name"):
                row[key] = config[key]
            row["source_url"] = f'{SOURCE_URL}/{config["market_slug"]}'
            row["status"] = "unavailable_missing_market"
            market = by_id.get(config["market_id"])
            if market:
                matched += 1
                require(market.get("slug") == config["market_slug"] and
                        market.get("groupItemTitle") == config["group_item_title"],
                        "changed market identity or candidate label")
                require(market.get("version") == "v1", "unreviewed market protocol version")
                labels = array(market.get("outcomes"), "outcomes")
                tokens = array(market.get("clobTokenIds"), "clobTokenIds")
                require(labels == ["Yes", "No"] and tokens[0] == config["outcome_id"],
                        "changed outcome identity")
                row["source_updated_at"] = market.get("updatedAt")
                require(all(type(market.get(k)) is bool for k in
                            ("active", "closed", "archived", "acceptingOrders")), "invalid market status")
                row["status"] = "unavailable_market_inactive"
                raw_prices = market.get("outcomePrices")
                prices = array(raw_prices, "outcomePrices") if raw_prices is not None else [None, None]
                parsed = []
                for value in prices:
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError as error:
                            raise CandidatePolymarketError("non-numeric outcome price") from error
                    parsed.append(probability(value))
                if market["active"] and not market["closed"] and not market["archived"] and market["acceptingOrders"]:
                    row["status"] = "observed" if parsed[0] is not None else "unavailable_price"
                    row["implied_probability"] = parsed[0]
        rows.append({key: row[key] for key in sorted(ROW_KEYS)})
    require(matched > 0, "no reviewed markets found; refusing empty publication")
    payload = dict(schema_version=SCHEMA_VERSION, provider="polymarket", event_id=EVENT_ID,
                   event_slug=EVENT_SLUG, source_url=SOURCE_URL, generated_at=observed_at,
                   observed_at=observed_at, source_updated_at=event.get("updatedAt"),
                   stale_after_hours=STALE_AFTER_HOURS, candidates=rows, ignored_markets=ignored)
    validate_candidate_polymarket(payload, mapping=mapping, candidate_ids=candidate_ids)
    return payload


def collect(output="candidate_polymarket.json", *, mapping_path="polymarket_candidate_markets.json",
            registry_path="candidate_candidacy_status.json", fetch=fetch_event, observed_at=None):
    registry = load_candidate_candidacy_status(registry_path)
    mapping = load_json(mapping_path)
    candidate_ids = {r["candidate_id"] for r in registry["candidates"]}
    event = fetch()
    # Capture completion, never an invented source timestamp.
    observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = build_candidate_polymarket(event, mapping, candidate_ids, observed_at)
    atomic_write(output, (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="candidate_polymarket.json")
    args = parser.parse_args()
    try:
        payload = collect(args.output)
    except (ValueError, OSError) as error:
        print(json.dumps({"provider": "polymarket", "status": "failed", "error": str(error)}))
        return 1
    print(json.dumps({"provider": "polymarket", "status": "published", "observed_at": payload["observed_at"],
                      "observed": sum(r["status"] == "observed" for r in payload["candidates"]),
                      "ignored": len(payload["ignored_markets"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
