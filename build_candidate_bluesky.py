"""Collect reviewed Bluesky DIDs using the official unauthenticated public AppView."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from build_candidate_signals import atomic_write, load_json
from candidate_candidacy_status import load_candidate_candidacy_status
from candidate_bluesky import (
    CandidateBlueskyError, SCHEMA_VERSION, STALE_AFTER_HOURS, count, empty_record,
    require, timestamp, valid_did, valid_handle, validate_candidate_bluesky, validate_mapping,
)

API_ROOT = "https://public.api.bsky.app/xrpc/"
PROFILES = "app.bsky.actor.getProfiles"
RESOLVE = "com.atproto.identity.resolveHandle"
PAGE_SIZE = 25
MAX_BYTES = 2 * 1024 * 1024
MAX_ATTEMPTS = 3
TIMEOUT = 20
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


class BlueskyClient:
    def __init__(self, *, opener=urlopen, sleep=time.sleep):
        self.opener, self.sleep = opener, sleep
        self.requests = {PROFILES: 0, RESOLVE: 0}

    def get(self, endpoint, **params):
        require(endpoint in self.requests, "unsupported Bluesky endpoint")
        for attempt in range(MAX_ATTEMPTS):
            delay = 2**attempt
            try:
                request = Request(API_ROOT + endpoint + "?" + urlencode(sorted(params.items()), doseq=True),
                    headers={"User-Agent": "FR27-Signal-Lab/1.0 (+https://france2027.app/)",
                             "Accept": "application/json"})
                self.requests[endpoint] += 1
                with self.opener(request, timeout=TIMEOUT) as response:
                    require(response.status == 200, "unexpected Bluesky HTTP response")
                    raw = response.read(MAX_BYTES + 1)
                require(len(raw) <= MAX_BYTES, "Bluesky response exceeds byte limit")
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise CandidateBlueskyError("malformed Bluesky JSON") from None
                require(isinstance(payload, dict) and "error" not in payload, "unexpected Bluesky response schema")
                return payload
            except HTTPError as error:
                code = error.code
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                error.close()
                if code not in RETRYABLE or attempt == MAX_ATTEMPTS - 1:
                    raise CandidateBlueskyError(f"Bluesky HTTP failure: {code}") from None
                if retry_after.isdecimal():
                    delay = min(int(retry_after), 30)
            except (URLError, TimeoutError, OSError):
                if attempt == MAX_ATTEMPTS - 1:
                    raise CandidateBlueskyError("Bluesky network failure after three attempts") from None
            self.sleep(delay)


def public_web_opt_out(profile, observed_at):
    """Honor account/profile labels, including expiration and explicit negation."""
    labels = profile.get("labels", [])
    require(isinstance(labels, list), "invalid profile labels")
    latest = {}
    did = profile["did"]
    for label in labels:
        require(isinstance(label, dict) and isinstance(label.get("val"), str)
                and valid_did(label.get("src")) and isinstance(label.get("uri"), str),
                "malformed profile label")
        require(type(label.get("neg", False)) is bool, "malformed label negation")
        created = timestamp(label.get("cts"))
        expiry = timestamp(label["exp"]) if "exp" in label else None
        if label["val"] != "!no-unauthenticated":
            continue
        require(label["uri"] in {did, f"at://{did}/app.bsky.actor.profile/self"},
                "opt-out label targets another identity")
        require(created <= observed_at, "future opt-out label")
        key = (label["src"], label["uri"])
        value = (created, label.get("neg", False), expiry)
        if key in latest:
            require(latest[key][0] != created or latest[key] == value, "conflicting opt-out labels")
        if key not in latest or latest[key][0] < created:
            latest[key] = value
    return any(not neg and (expiry is None or expiry > observed_at)
               for _, neg, expiry in latest.values())


def parse_profiles(payload, requested, observed_at):
    require(isinstance(payload, dict) and isinstance(payload.get("profiles"), list)
            and len(payload["profiles"]) <= PAGE_SIZE, "invalid profiles response")
    profiles = {}
    for profile in payload["profiles"]:
        require(isinstance(profile, dict), "invalid profile")
        did = profile.get("did")
        require(valid_did(did) and did in requested and did not in profiles,
                "wrong/duplicate returned DID")
        # Check opt-out before reading or retaining any profile metrics/content.
        if public_web_opt_out(profile, timestamp(observed_at)):
            profiles[did] = {"status": "unavailable_public_web_opt_out"}
            continue
        require(valid_handle(profile.get("handle")), "invalid observed handle")
        display = profile.get("displayName")
        require(display is None or (isinstance(display, str) and len(display) <= 640), "invalid display name")
        profiles[did] = dict(status="observed", handle=profile["handle"], display_name=display,
            profile_url=f"https://bsky.app/profile/{did}",
            followers_count=count(profile.get("followersCount")),
            follows_count=count(profile.get("followsCount")), posts_count=count(profile.get("postsCount")))
    return profiles


def build_candidate_bluesky(client, mapping, candidate_ids, observed_at):
    validate_mapping(mapping, candidate_ids)
    observed_at = timestamp(observed_at).isoformat().replace("+00:00", "Z")
    configs = {row["candidate_id"]: row for row in mapping["accounts"]}
    dids = sorted(row["did"] for row in mapping["accounts"])
    profiles = {}
    for offset in range(0, len(dids), PAGE_SIZE):
        batch = dids[offset:offset + PAGE_SIZE]
        profiles.update(parse_profiles(client.get(PROFILES, actors=batch), set(batch), observed_at))
    # Missing batch entries and HTTP account-not-found are collection failures,
    # never fabricated unavailable rows replacing the last successful snapshot.
    require(set(profiles) == set(dids), "mapped account missing/inaccessible; retaining prior snapshot")
    for did in dids:
        profile = profiles[did]
        if profile["status"] == "observed":
            resolved = client.get(RESOLVE, handle=profile["handle"])
            require(isinstance(resolved, dict) and resolved.get("did") == did,
                    "observed handle resolves to a different DID")
    rows = []
    for cid in sorted(candidate_ids):
        config = configs.get(cid)
        row = empty_record(cid, config)
        if config:
            row.update(profiles[config["did"]])
        rows.append(row)
    payload = dict(schema_version=SCHEMA_VERSION, provider="bluesky", generated_at=observed_at,
                   observed_at=observed_at, stale_after_hours=STALE_AFTER_HOURS, candidates=rows)
    validate_candidate_bluesky(payload, mapping=mapping, candidate_ids=candidate_ids)
    return payload


def collect(output="candidate_bluesky.json", *, mapping_path="bluesky_candidate_accounts.json",
            registry_path="candidate_candidacy_status.json", client=None, observed_at=None):
    registry = load_candidate_candidacy_status(registry_path)
    ids = {row["candidate_id"] for row in registry["candidates"]}
    mapping = load_json(mapping_path)
    validate_mapping(mapping, ids)
    client = client or BlueskyClient()
    observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = build_candidate_bluesky(client, mapping, ids, observed_at)
    atomic_write(output, (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return payload, client.requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="candidate_bluesky.json")
    args = parser.parse_args()
    try:
        payload, requests = collect(args.output)
    except (ValueError, OSError, TypeError, KeyError):
        print(json.dumps({"provider": "bluesky", "status": "failed",
                          "error": "collection failed; prior artifact retained"}))
        return 1
    print(json.dumps({"provider": "bluesky", "status": "published", "observed_at": payload["observed_at"],
        "observed": sum(row["status"] == "observed" for row in payload["candidates"]), "requests": requests}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
