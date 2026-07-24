"""Build the static dashboard publication manifest.

The manifest records publication time separately from lane-local generation,
check, and evidence timestamps.  It is intentionally dependency-free so the
data workflows can run it after their existing validation steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"
OUTPUT_NAME = "publication_manifest.json"
TIMESTAMP_STATUSES = {"known", "unknown", "missing", "invalid"}
LANE_FILES = {
    "claims": ("claims_under_scrutiny.json",),
    "news": ("news_wire.json",),
    "polls": ("polls.json",),
    "recent_changes": ("recent_changes.json",),
    "runoff": (
        "second_round_polls.json",
        "closest_tested_runoff.json",
    ),
}
SOURCE_NETWORK_FIELDS = (
    "approved_publisher_domains",
    "configured_media_publishers",
    "configured_routes_or_feeds",
    "routes_due_in_run",
    "successful_due_routes",
    "contributing_publishers_in_retained_period",
    "publishers_represented_in_accepted_election_news",
)


class ManifestError(ValueError):
    """Raised when the manifest itself cannot satisfy its contract."""


def _utc_timestamp(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a UTC ISO-8601 timestamp")

    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError(
            f"{field} must be a UTC ISO-8601 timestamp"
        ) from error

    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ManifestError(f"{field} must include a UTC offset")

    normalized = parsed.astimezone(timezone.utc).isoformat()
    return normalized.replace("+00:00", "Z")


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_source(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "sha256": None,
        "payload": None,
        "error": None,
    }
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        result["error"] = f"{path.name} is missing"
        return result
    except OSError as error:
        result["error"] = f"{path.name} could not be read: {error}"
        return result

    result["available"] = True
    result["sha256"] = _sha256(content)
    try:
        result["payload"] = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        result["error"] = f"{path.name} is malformed JSON: {error}"
    return result


def _schema_version(payload: Any) -> Any:
    if isinstance(payload, dict):
        return payload.get("schema_version")
    return None


def _parse_evidence_value(value: Any) -> tuple[datetime, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        if "T" not in candidate:
            parsed = datetime.strptime(candidate, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            return parsed, parsed.date().isoformat()

        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        parsed = parsed.astimezone(timezone.utc)
        return parsed, parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _maximum_evidence(
    values: Iterable[Any],
) -> tuple[str | None, int]:
    valid: list[tuple[datetime, str]] = []
    invalid_count = 0
    for value in values:
        parsed = _parse_evidence_value(value)
        if parsed is None:
            invalid_count += 1
        else:
            valid.append(parsed)
    if not valid:
        return None, invalid_count
    return max(valid, key=lambda item: item[0])[1], invalid_count


def _timestamp_fields(
    lane_name: str,
    payload: Any,
    warnings: list[str],
) -> tuple[dict[str, str], str]:
    if lane_name == "polls":
        return {}, "unknown"
    if not isinstance(payload, dict):
        return {}, "invalid"

    field_map = (
        (("generated_at", "generated_at"),)
        if lane_name != "recent_changes"
        else (
            ("generated_at", "generated_at"),
            ("last_successful_check_at", "last_success_at"),
        )
    )
    timestamps: dict[str, str] = {}
    invalid = False
    supplied = False
    for source_field, manifest_field in field_map:
        value = payload.get(source_field)
        if value is None:
            continue
        supplied = True
        try:
            timestamps[manifest_field] = _utc_timestamp(
                value,
                field=f"{lane_name}.{manifest_field}",
            )
        except ManifestError:
            invalid = True
            warnings.append(
                f"{lane_name}: {source_field} is not a valid UTC timestamp"
            )

    if invalid:
        return timestamps, "invalid"
    if timestamps:
        return timestamps, "known"
    return timestamps, "unknown" if not supplied else "invalid"


def _structurally_valid(lane_name: str, sources: list[dict[str, Any]]) -> bool:
    if any(source["payload"] is None for source in sources):
        return False

    payload = sources[0]["payload"]
    if lane_name == "polls":
        return isinstance(payload, list) and all(
            isinstance(item, dict) for item in payload
        )
    if not isinstance(payload, dict):
        return False
    if lane_name == "runoff":
        related = sources[1]["payload"]
        return (
            isinstance(payload.get("events"), list)
            and all(isinstance(item, dict) for item in payload["events"])
            and isinstance(related, dict)
        )
    required_list = {
        "news": "election_news",
        "claims": "reviews",
        "recent_changes": "items",
    }[lane_name]
    return isinstance(payload.get(required_list), list) and all(
        isinstance(item, dict) for item in payload[required_list]
    )


def _evidence_values(lane_name: str, payload: Any) -> list[Any]:
    if lane_name == "polls":
        return [item.get("fieldwork_end") for item in payload]
    if lane_name == "runoff":
        return [
            item.get("fieldwork_end")
            for item in payload.get("events", [])
        ]
    if lane_name == "claims":
        return [
            item.get("review_date")
            for item in payload.get("reviews", [])
        ]
    if lane_name == "recent_changes":
        return [
            item.get("trusted_change_at")
            for item in payload.get("items", [])
        ]
    if lane_name == "news":
        values: list[Any] = []
        for list_name in (
            "election_news",
            "notable_developments",
            "relevant_news",
            "candidate_watch",
        ):
            items = payload.get(list_name, [])
            if isinstance(items, list):
                values.extend(
                    item.get("published_at")
                    for item in items
                    if isinstance(item, dict)
                )
        return values
    raise AssertionError(f"unsupported lane: {lane_name}")


def _build_lane(
    root: Path,
    lane_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    file_names = LANE_FILES[lane_name]
    sources = [_read_source(root / file_name) for file_name in file_names]
    lane_warnings = [
        source["error"] for source in sources if source["error"] is not None
    ]
    available = all(source["available"] for source in sources)
    valid = available and _structurally_valid(lane_name, sources)
    if available and not valid and not lane_warnings:
        lane_warnings.append(
            f"{lane_name}: payload does not match the expected lane structure"
        )

    primary = sources[0]
    lane: dict[str, Any] = {
        "file": file_names[0],
        "available": available,
        "valid": valid,
        "sha256": primary["sha256"],
        "schema_version": _schema_version(primary["payload"]),
        "data_as_of": None,
        "timestamp_status": (
            "missing"
            if not available
            else "invalid"
            if not valid
            else "unknown"
        ),
        "warnings": lane_warnings,
    }
    if len(file_names) > 1:
        lane["related_files"] = [
            {
                "file": file_name,
                "available": source["available"],
                "sha256": source["sha256"],
            }
            for file_name, source in zip(file_names[1:], sources[1:])
        ]

    if valid:
        timestamp_fields, timestamp_status = _timestamp_fields(
            lane_name,
            primary["payload"],
            lane_warnings,
        )
        lane.update(timestamp_fields)
        lane["timestamp_status"] = timestamp_status
        lane["data_as_of"], invalid_count = _maximum_evidence(
            _evidence_values(lane_name, primary["payload"])
        )
        if invalid_count:
            lane_warnings.append(
                f"{lane_name}: ignored {invalid_count} invalid or missing "
                "evidence timestamp"
                + ("" if invalid_count == 1 else "s")
            )
        if lane["data_as_of"] is None:
            lane_warnings.append(
                f"{lane_name}: no valid lane-local evidence date is available"
            )

    return lane, sources


def _non_negative_integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _source_network(news_payload: Any) -> dict[str, int | None]:
    metrics = {field: None for field in SOURCE_NETWORK_FIELDS}
    if not isinstance(news_payload, dict):
        return metrics

    discovery = news_payload.get("discovery")
    coverage = news_payload.get("feed_coverage")
    if not isinstance(discovery, dict):
        discovery = {}
    if not isinstance(coverage, dict):
        coverage = {}

    metrics.update(
        {
            "approved_publisher_domains": _non_negative_integer(
                discovery.get("approved_publisher_domains")
            ),
            "configured_media_publishers": _non_negative_integer(
                coverage.get("configured_media_publishers")
            ),
            "configured_routes_or_feeds": _non_negative_integer(
                coverage.get("configured_feeds")
            ),
            "routes_due_in_run": _non_negative_integer(
                coverage.get("feeds_due_this_run")
            ),
            "successful_due_routes": _non_negative_integer(
                coverage.get("feeds_successful_this_run")
            ),
            "contributing_publishers_in_retained_period": (
                _non_negative_integer(
                    coverage.get("contributing_publishers_30d")
                )
            ),
        }
    )

    election_news = news_payload.get("election_news")
    if isinstance(election_news, list):
        publishers = {
            item["publisher"].strip()
            for item in election_news
            if isinstance(item, dict)
            and isinstance(item.get("publisher"), str)
            and item["publisher"].strip()
        }
        metrics[
            "publishers_represented_in_accepted_election_news"
        ] = len(publishers)
    return metrics


def _snapshot_id(
    lane_sources: dict[str, list[dict[str, Any]]],
) -> str:
    content_hashes = {
        lane_name: [
            {
                "file": file_name,
                "sha256": source["sha256"],
            }
            for file_name, source in zip(
                LANE_FILES[lane_name],
                lane_sources[lane_name],
            )
        ]
        for lane_name in sorted(lane_sources)
    }
    serialized = json.dumps(
        content_hashes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_manifest(
    root: Path | str = ".",
    *,
    published_at: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    normalized_published_at = _utc_timestamp(
        published_at or _now_utc(),
        field="published_at",
    )
    lanes: dict[str, dict[str, Any]] = {}
    lane_sources: dict[str, list[dict[str, Any]]] = {}
    for lane_name in sorted(LANE_FILES):
        lane, sources = _build_lane(root_path, lane_name)
        lanes[lane_name] = lane
        lane_sources[lane_name] = sources

    warnings = [
        warning
        for lane_name in sorted(lanes)
        for warning in lanes[lane_name]["warnings"]
    ]
    news_payload = (
        lane_sources["news"][0]["payload"]
        if lanes["news"]["valid"]
        else None
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": _snapshot_id(lane_sources),
        "published_at": normalized_published_at,
        "lanes": lanes,
        "source_network": _source_network(news_payload),
        "warnings": warnings,
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("schema_version must equal 1.0")
    snapshot_id = manifest.get("snapshot_id")
    if (
        not isinstance(snapshot_id, str)
        or len(snapshot_id) != 64
        or any(character not in "0123456789abcdef" for character in snapshot_id)
    ):
        raise ManifestError("snapshot_id must be a full lowercase SHA-256")
    _utc_timestamp(manifest.get("published_at"), field="published_at")

    lanes = manifest.get("lanes")
    if not isinstance(lanes, dict) or set(lanes) != set(LANE_FILES):
        raise ManifestError("manifest lanes do not match the version 1 contract")
    for lane_name, lane in lanes.items():
        if not isinstance(lane, dict):
            raise ManifestError(f"{lane_name} lane must be an object")
        for field in (
            "file",
            "available",
            "valid",
            "sha256",
            "schema_version",
            "data_as_of",
            "timestamp_status",
            "warnings",
        ):
            if field not in lane:
                raise ManifestError(f"{lane_name} lane is missing {field}")
        if lane["timestamp_status"] not in TIMESTAMP_STATUSES:
            raise ManifestError(
                f"{lane_name} has an invalid timestamp_status"
            )
        if not isinstance(lane["warnings"], list):
            raise ManifestError(f"{lane_name} warnings must be an array")

    network = manifest.get("source_network")
    if not isinstance(network, dict) or set(network) != set(
        SOURCE_NETWORK_FIELDS
    ):
        raise ManifestError("source_network does not match the version 1 contract")
    if any(
        value is not None
        and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        )
        for value in network.values()
    ):
        raise ManifestError(
            "source_network metrics must be non-negative integers or null"
        )
    if not isinstance(manifest.get("warnings"), list):
        raise ManifestError("warnings must be an array")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build publication_manifest.json version 1"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="build and validate in memory without writing the manifest",
    )
    parser.add_argument(
        "--published-at",
        help="coherent snapshot publication time as a UTC ISO-8601 timestamp",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        manifest = build_manifest(
            Path.cwd(),
            published_at=arguments.published_at,
        )
        if not arguments.check:
            atomic_write_json(Path.cwd() / OUTPUT_NAME, manifest)
    except ManifestError as error:
        print(f"publication manifest error: {error}")
        return 1

    action = "validated" if arguments.check else "wrote"
    print(
        f"{action} {OUTPUT_NAME} "
        f"(snapshot {manifest['snapshot_id']})"
    )
    for warning in manifest["warnings"]:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
