"""Collect reviewed official YouTube channels; validate fully before atomic publication."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from build_candidate_signals import atomic_write, load_json
from candidate_candidacy_status import load_candidate_candidacy_status
from candidate_youtube import (
    CandidateYouTubeError, RECENT_WINDOW_DAYS, SCHEMA_VERSION, STALE_AFTER_HOURS,
    VIDEO_ID, candidate_projection, count, empty_record, require, text, timestamp,
    validate_candidate_youtube, validate_mapping,
)

API_ROOT = "https://www.googleapis.com/youtube/v3/"
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 20
PAGE_SIZE = 50
MAX_ATTEMPTS = 3
TIMEOUT = 20
RETRYABLE = {408, 425, 429, 500, 502, 503, 504}
FIELDS = {
    "channels": "items(id,snippet/title,contentDetails/relatedPlaylists/uploads,statistics(subscriberCount,hiddenSubscriberCount,viewCount,videoCount))",
    "playlistItems": "nextPageToken,items(snippet(title,videoOwnerChannelId),contentDetails(videoId,videoPublishedAt))",
    "videos": "items(id,snippet/channelId,statistics/viewCount)",
}
PARTS = {"channels": "snippet,contentDetails,statistics", "playlistItems": "snippet,contentDetails",
         "videos": "snippet,statistics"}


class YouTubeClient:
    def __init__(self, *, opener=urlopen, sleep=time.sleep):
        # Production credentials have a single source. Tests patch the environment.
        self._key = os.environ.get("YOUTUBE_API_KEY", "")
        require(bool(self._key.strip()), "YOUTUBE_API_KEY is missing")
        self.opener, self.sleep = opener, sleep
        self.requests = {endpoint: 0 for endpoint in PARTS}

    def assert_secret_absent(self, value):
        serialized = json.dumps(value, ensure_ascii=True, allow_nan=False)
        require(all(secret not in serialized for secret in (self._key, quote(self._key, safe=""))),
                "credential contamination; refusing publication")

    def get(self, endpoint, **params):
        require(endpoint in PARTS, "unsupported YouTube endpoint")
        params.update(part=PARTS[endpoint], fields=FIELDS[endpoint], key=self._key)
        for attempt in range(MAX_ATTEMPTS):
            delay = 2**attempt
            try:
                request = Request(API_ROOT + endpoint + "?" + urlencode(sorted(params.items())),
                                  headers={"User-Agent": "FR27-Signal-Lab/1.0 (+https://france2027.app/)",
                                           "Accept": "application/json"})
                self.requests[endpoint] += 1
                with self.opener(request, timeout=TIMEOUT) as response:
                    require(response.status == 200, "unexpected HTTP response")
                    raw = response.read(MAX_BYTES + 1)
                require(len(raw) <= MAX_BYTES, "YouTube response exceeds byte limit")
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise CandidateYouTubeError("malformed YouTube JSON") from None
                self.assert_secret_absent(payload)
                require(isinstance(payload, dict) and isinstance(payload.get("items"), list)
                        and "error" not in payload, "unexpected YouTube response schema")
                return payload
            except HTTPError as error:
                code = error.code
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                error.close()
                if code not in RETRYABLE or attempt == MAX_ATTEMPTS - 1:
                    # Never propagate URL, response body, reason, or chained exceptions.
                    raise CandidateYouTubeError(f"YouTube HTTP failure: {code}") from None
                if retry_after.isdecimal():
                    delay = min(int(retry_after), 30)
            except (URLError, TimeoutError, OSError):
                if attempt == MAX_ATTEMPTS - 1:
                    raise CandidateYouTubeError("YouTube network failure after three attempts") from None
            self.sleep(delay)


def batches(values):
    values = sorted(set(values))
    for offset in range(0, len(values), PAGE_SIZE):
        yield values[offset:offset + PAGE_SIZE]


def parse_channels(payload, requested):
    require(isinstance(payload, dict) and isinstance(payload.get("items"), list), "invalid channels response")
    result = {}
    for channel in payload["items"]:
        require(isinstance(channel, dict), "invalid channel resource")
        cid = channel.get("id")
        require(isinstance(cid, str) and cid in requested and cid not in result, "wrong/duplicate returned channel ID")
        snippet, details, stats = (channel.get(k) for k in ("snippet", "contentDetails", "statistics"))
        require(isinstance(snippet, dict) and text(snippet.get("title")), "missing channel title")
        require(isinstance(details, dict) and isinstance(details.get("relatedPlaylists"), dict)
                and text(details["relatedPlaylists"].get("uploads")), "missing uploads playlist")
        require(isinstance(stats, dict) and type(stats.get("hiddenSubscriberCount")) is bool,
                "invalid channel statistics")
        hidden = stats["hiddenSubscriberCount"]
        # A hidden count may be omitted; if supplied it must still be well formed.
        if "subscriberCount" in stats:
            count(stats["subscriberCount"])
        subscribers = None if hidden else count(stats.get("subscriberCount"))
        result[cid] = dict(channel_title=snippet["title"], uploads_playlist_id=details["relatedPlaylists"]["uploads"],
                           subscriber_count=subscribers, hidden_subscriber_count=hidden,
                           channel_view_count=count(stats.get("viewCount")), public_video_count=count(stats.get("videoCount")))
    return result


def collect_uploads(client, playlist_id, channel_id, observed_at, *, max_pages=MAX_PAGES):
    require(type(max_pages) is int and 1 <= max_pages <= MAX_PAGES, "invalid pagination bound")
    observed = timestamp(observed_at)
    boundary = observed - timedelta(days=RECENT_WINDOW_DAYS)
    videos, all_ids, tokens, dates = {}, set(), set(), []
    token, unknown_dates = None, False
    for _ in range(max_pages):
        params = dict(playlistId=playlist_id, maxResults=PAGE_SIZE)
        if token:
            params["pageToken"] = token
        payload = client.get("playlistItems", **params)
        require(isinstance(payload, dict) and isinstance(payload.get("items"), list)
                and len(payload["items"]) <= PAGE_SIZE, "invalid uploads response")
        for item in payload["items"]:
            require(isinstance(item, dict) and isinstance(item.get("contentDetails"), dict)
                    and isinstance(item.get("snippet"), dict), "invalid upload item")
            details, snippet = item["contentDetails"], item["snippet"]
            vid = details.get("videoId")
            require(text(vid) and bool(VIDEO_ID.fullmatch(vid)) and vid not in all_ids,
                    "invalid/duplicate upload video ID")
            all_ids.add(vid)
            if details.get("videoPublishedAt") is None:
                # Private/deleted items can lack a publication date; do not invent one.
                unknown_dates = True
                continue
            published = timestamp(details["videoPublishedAt"])
            if published > observed:  # Scheduled future publication is outside the observation window.
                continue
            require(snippet.get("videoOwnerChannelId") == channel_id, "upload owner differs from mapped channel")
            require(text(snippet.get("title")), "missing upload title")
            dates.append(published)
            if published >= boundary:
                videos[vid] = dict(video_id=vid, title=snippet["title"],
                    published_at=published.isoformat().replace("+00:00", "Z"), view_count=None,
                    video_url=f"https://www.youtube.com/watch?v={vid}")
        token = payload.get("nextPageToken")
        if token is None:
            complete = not unknown_dates
            break
        require(text(token) and len(token) <= 2048 and token not in tokens, "invalid/repeated pagination token")
        tokens.add(token)
    else:
        complete = False
    ordered = sorted(videos.values(), key=lambda v: (-timestamp(v["published_at"]).timestamp(), v["video_id"]))
    latest = max(dates).isoformat().replace("+00:00", "Z") if complete and dates else None
    return ordered, complete, latest


def parse_video_statistics(payload, requested, owners):
    require(isinstance(payload, dict) and isinstance(payload.get("items"), list), "invalid videos response")
    result = {}
    for video in payload["items"]:
        require(isinstance(video, dict), "invalid video resource")
        vid = video.get("id")
        require(isinstance(vid, str) and vid in requested and vid not in result, "wrong/duplicate video ID")
        require(isinstance(video.get("snippet"), dict)
                and video["snippet"].get("channelId") == owners[vid], "video owner mismatch")
        stats = video.get("statistics")
        require(stats is None or isinstance(stats, dict), "invalid video statistics")
        result[vid] = count(stats["viewCount"]) if stats is not None and "viewCount" in stats else None
    return result


def build_candidate_youtube(client, mapping, candidate_ids, observed_at):
    validate_mapping(mapping, candidate_ids)
    observed_at = timestamp(observed_at).isoformat().replace("+00:00", "Z")
    configs = {r["candidate_id"]: r for r in mapping["channels"]}
    channels = {}
    for batch in batches(r["channel_id"] for r in mapping["channels"]):
        channels.update(parse_channels(client.get("channels", id=",".join(batch), maxResults=PAGE_SIZE), set(batch)))
    # A missing mapped channel fails the whole collection. The explicit missing
    # state is supported by the contract, but never used to mask API collection errors.
    require(len(channels) == len(configs), "mapped channel missing/inaccessible; retaining prior snapshot")
    rows, owners = [], {}
    for cid in sorted(candidate_ids):
        config = configs.get(cid)
        row = empty_record(cid, config)
        if config:
            channel_id = config["channel_id"]
            row.update(channels[channel_id], status="observed")
            videos, complete, latest = collect_uploads(client, row["uploads_playlist_id"], channel_id, observed_at)
            row.update(recent_videos=videos, recent_window_complete=complete,
                       uploads_last_7d=len(videos) if complete else None, latest_upload_at=latest)
            owners.update({video["video_id"]: channel_id for video in videos})
        rows.append(row)
    metrics = {}
    for batch in batches(owners):
        metrics.update(parse_video_statistics(client.get("videos", id=",".join(batch)), set(batch), owners))
    for row in rows:
        if row["status"] == "observed":
            for video in row["recent_videos"]:
                video["view_count"] = metrics.get(video["video_id"])
            row["recent_video_metrics_complete"] = all(v["view_count"] is not None for v in row["recent_videos"])
    payload = dict(schema_version=SCHEMA_VERSION, provider="youtube", generated_at=observed_at,
                   observed_at=observed_at, stale_after_hours=STALE_AFTER_HOURS,
                   recent_window_days=RECENT_WINDOW_DAYS, candidates=rows)
    validate_candidate_youtube(payload, mapping=mapping, candidate_ids=candidate_ids)
    client.assert_secret_absent(payload)
    return payload


def collect(output="candidate_youtube.json", *, mapping_path="youtube_candidate_channels.json",
            registry_path="candidate_candidacy_status.json", client=None, observed_at=None):
    registry = load_candidate_candidacy_status(registry_path)
    ids = {r["candidate_id"] for r in registry["candidates"]}
    mapping = load_json(mapping_path)
    validate_mapping(mapping, ids)
    client = client or YouTubeClient()
    # Reference instant at collection start: later requests are a bounded snapshot,
    # not a claim of simultaneous platform measurements.
    observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = build_candidate_youtube(client, mapping, ids, observed_at)
    atomic_write(output, (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return payload, client.requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="candidate_youtube.json")
    args = parser.parse_args()
    try:
        payload, requests = collect(args.output)
    except (ValueError, OSError, TypeError, KeyError):
        # Neither platform strings nor transport exception details reach logs.
        print(json.dumps({"provider": "youtube", "status": "failed", "error": "collection failed; prior artifact retained"}))
        return 1
    print(json.dumps({"provider": "youtube", "status": "published", "observed_at": payload["observed_at"],
                      "observed": sum(r["status"] == "observed" for r in payload["candidates"]), "requests": requests}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
