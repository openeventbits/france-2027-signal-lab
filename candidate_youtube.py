"""YouTube-only snapshot contract. Platform reach/activity, never electoral support."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "1.0"
STALE_AFTER_HOURS = 48
RECENT_WINDOW_DAYS = 7
MAX_SAFE_INTEGER = 2**53 - 1
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
ROW_KEYS = {
    "candidate_id", "status", "channel_id", "channel_title", "channel_url",
    "subscriber_count", "hidden_subscriber_count", "channel_view_count",
    "public_video_count", "uploads_playlist_id", "latest_upload_at",
    "uploads_last_7d", "recent_window_complete", "recent_video_metrics_complete", "recent_videos",
}
VIDEO_KEYS = {"video_id", "title", "published_at", "view_count", "video_url"}
STATES = {"observed", "unavailable_no_channel", "unavailable_channel_missing"}


class CandidateYouTubeError(ValueError):
    """Collection cannot be trusted; retain the prior valid artifact."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateYouTubeError(message)


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def timestamp(value: Any) -> datetime:
    require(isinstance(value, str) and bool(re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)", value)),
        "timestamp must be UTC ISO text")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CandidateYouTubeError("invalid timestamp") from None


def count(value: Any) -> int:
    """Reject unsafe consumer precision instead of rounding or replacing with zero."""
    require(isinstance(value, str) and bool(re.fullmatch(r"[0-9]{1,16}", value)),
            "count must be an unsigned decimal string")
    parsed = int(value)
    require(parsed <= MAX_SAFE_INTEGER, "count exceeds JSON safe integer precision")
    return parsed


def validate_count(value: Any, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    require(type(value) is int and 0 <= value <= MAX_SAFE_INTEGER, "invalid published count")


def validate_mapping(mapping: Any, candidate_ids: set[str] | None = None) -> None:
    require(isinstance(mapping, dict) and set(mapping) == {"schema_version", "channels"}
            and mapping["schema_version"] == SCHEMA_VERSION
            and isinstance(mapping["channels"], list), "invalid channel mapping")
    candidates, channels = set(), set()
    for row in mapping["channels"]:
        require(isinstance(row, dict) and set(row) == {"candidate_id", "channel_id", "verification_url"},
                "invalid mapping row")
        require(all(text(v) for v in row.values()), "mapping fields must be non-empty text")
        require(bool(CHANNEL_ID.fullmatch(row["channel_id"])), "invalid stable channel ID")
        require(row["candidate_id"] not in candidates and row["channel_id"] not in channels,
                "duplicate candidate or channel mapping")
        verification = urlsplit(row["verification_url"])
        require(verification.scheme == "https" and bool(verification.hostname)
                and not verification.username and not verification.password
                and not verification.query and not verification.fragment,
                "invalid first-party verification URL")
        if candidate_ids is not None:
            require(row["candidate_id"] in candidate_ids, "mapping candidate outside registry")
        candidates.add(row["candidate_id"])
        channels.add(row["channel_id"])


def empty_record(candidate_id: str, config: dict | None = None) -> dict:
    row = dict.fromkeys(sorted(ROW_KEYS))
    row.update(candidate_id=candidate_id, status="unavailable_no_channel")
    if config:
        row.update(status="unavailable_channel_missing", channel_id=config["channel_id"],
                   channel_url=f'https://www.youtube.com/channel/{config["channel_id"]}')
    return row


def validate_candidate_youtube(payload: Any, *, mapping: Any = None,
                               candidate_ids: set[str] | None = None) -> None:
    require(isinstance(payload, dict) and set(payload) == {
        "schema_version", "provider", "generated_at", "observed_at", "stale_after_hours",
        "recent_window_days", "candidates"}, "invalid YouTube publication fields")
    require(payload["schema_version"] == SCHEMA_VERSION and payload["provider"] == "youtube",
            "unsupported YouTube publication")
    observed = timestamp(payload["observed_at"])
    require(timestamp(payload["generated_at"]) == observed, "generation/observation mismatch")
    require(type(payload["stale_after_hours"]) is int and payload["stale_after_hours"] == STALE_AFTER_HOURS
            and type(payload["recent_window_days"]) is int
            and payload["recent_window_days"] == RECENT_WINDOW_DAYS, "invalid observation policy")
    if mapping is not None:
        validate_mapping(mapping, candidate_ids)
    configs = {r["candidate_id"]: r for r in mapping["channels"]} if mapping is not None else {}
    rows = payload["candidates"]
    require(isinstance(rows, list) and bool(rows), "empty candidate publication")
    seen, channels = set(), set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == ROW_KEYS, "invalid candidate row fields")
        cid = row["candidate_id"]
        require(text(cid) and cid not in seen, "invalid/duplicate candidate")
        seen.add(cid)
        require(isinstance(row["status"], str) and row["status"] in STATES, "invalid candidate state")
        if row["status"] == "unavailable_no_channel":
            require(row == empty_record(cid) and cid not in configs, "unmapped evidence must be null")
            continue
        require(text(row["channel_id"]) and bool(CHANNEL_ID.fullmatch(row["channel_id"]))
                and row["channel_id"] not in channels, "invalid/duplicate published channel")
        channels.add(row["channel_id"])
        require(row["channel_url"] == f'https://www.youtube.com/channel/{row["channel_id"]}',
                "invalid channel link")
        if mapping is not None:
            require(cid in configs and row["channel_id"] == configs[cid]["channel_id"], "unreviewed channel")
        if row["status"] == "unavailable_channel_missing":
            require(row == empty_record(cid, {"channel_id": row["channel_id"]}),
                    "missing channel cannot carry metrics")
            continue
        require(text(row["channel_title"]) and isinstance(row["uploads_playlist_id"], str)
                and bool(re.fullmatch(r"UU[A-Za-z0-9_-]{22}", row["uploads_playlist_id"])),
                "observed channel lacks title/uploads")
        require(type(row["hidden_subscriber_count"]) is bool, "invalid subscriber visibility")
        if row["hidden_subscriber_count"]:
            require(row["subscriber_count"] is None, "hidden subscribers must remain unavailable")
        else:
            validate_count(row["subscriber_count"])
        for key in ("channel_view_count", "public_video_count"):
            validate_count(row[key])
        require(type(row["recent_window_complete"]) is bool
                and type(row["recent_video_metrics_complete"]) is bool, "invalid completeness")
        videos = row["recent_videos"]
        require(isinstance(videos, list), "recent videos must be a list")
        video_ids = set()
        for video in videos:
            require(isinstance(video, dict) and set(video) == VIDEO_KEYS, "invalid recent video")
            vid = video["video_id"]
            require(text(vid) and bool(VIDEO_ID.fullmatch(vid)) and vid not in video_ids,
                    "invalid/duplicate video ID")
            video_ids.add(vid)
            require(text(video["title"]), "missing video title")
            published = timestamp(video["published_at"])
            require(observed - timedelta(days=RECENT_WINDOW_DAYS) <= published <= observed,
                    "video outside recent window")
            validate_count(video["view_count"], nullable=True)
            require(video["video_url"] == f"https://www.youtube.com/watch?v={vid}", "invalid video link")
        require(videos == sorted(videos, key=lambda v: (-timestamp(v["published_at"]).timestamp(), v["video_id"])),
                "recent videos must be deterministically ordered")
        require(row["recent_video_metrics_complete"] == all(v["view_count"] is not None for v in videos),
                "video metric completeness mismatch")
        if row["recent_window_complete"]:
            validate_count(row["uploads_last_7d"])
            require(row["uploads_last_7d"] == len(videos), "upload count mismatch")
            if row["latest_upload_at"] is not None:
                latest = timestamp(row["latest_upload_at"])
                require(latest <= observed, "future latest upload")
                require(not videos or latest == timestamp(videos[0]["published_at"]), "latest upload mismatch")
                require(bool(videos) or latest < observed - timedelta(days=RECENT_WINDOW_DAYS),
                        "recent latest upload absent from complete window")
            else:
                require(not videos, "missing latest upload")
        else:
            require(row["uploads_last_7d"] is None and row["latest_upload_at"] is None,
                    "incomplete window cannot claim exact count/latest")
    require([r["candidate_id"] for r in rows] == sorted(seen), "candidate rows must be sorted")
    require(set(configs) <= seen, "mapping absent from artifact")
    if candidate_ids is not None:
        require(seen == candidate_ids, "candidate universe differs from registry")


def candidate_projection(payload: dict, candidate_id: str) -> dict:
    row = next((r for r in payload["candidates"] if r["candidate_id"] == candidate_id), None)
    require(row is not None, "candidate missing from YouTube snapshot")
    return {**row, **{k: payload[k] for k in ("provider", "observed_at", "stale_after_hours", "recent_window_days")}}


def validate_candidate_youtube_projection(row: Any, candidate_id: str) -> None:
    require(isinstance(row, dict) and set(row) == ROW_KEYS | {
        "provider", "observed_at", "stale_after_hours", "recent_window_days"}, "invalid YouTube projection")
    require(row["candidate_id"] == candidate_id, "projection candidate mismatch")
    validate_candidate_youtube({"schema_version": SCHEMA_VERSION, "generated_at": row["observed_at"],
        **{k: row[k] for k in ("provider", "observed_at", "stale_after_hours", "recent_window_days")},
        "candidates": [{k: row[k] for k in ROW_KEYS}]}, candidate_ids={candidate_id})
