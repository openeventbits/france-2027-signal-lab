"""Deterministic persistent health state for news collection routes."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
FAILURE_THRESHOLD = 3
ROLLING_ATTEMPT_LIMIT = 24
ROUTE_TYPES = {"direct", "shared_discovery", "publisher_site"}
STATUSES = {
    "healthy",
    "healthy_zero_yield",
    "transient_failure",
    "repeated_failure",
    "not_due",
    "never_attempted",
    "disabled",
    "removed",
}

ROUTE_FIELDS = {
    "route_id",
    "route_type",
    "publisher",
    "domain",
    "configured",
    "enabled",
    "schedule_class",
    "schedule_slot",
    "due_this_run",
    "status",
    "last_attempt_at",
    "last_success_at",
    "last_failure_at",
    "consecutive_failures",
    "latest_http_status",
    "latest_failure_category",
    "latest_latency_ms",
    "parsed_item_count",
    "accepted_inventory_count",
    "accepted_election_news_count",
    "rolling_attempt_count",
    "rolling_success_count",
    "rolling_parsed_items",
    "rolling_accepted_items",
    "rolling_election_news_items",
    "updated_at",
    "attempt_history",
}
OPTIONAL_ROUTE_FIELDS = {
    "etag",
    "last_modified",
    "validator_url",
    "latest_attempt_count",
    "latest_not_modified",
    "response_bytes",
}

ATTEMPT_HISTORY_FIELDS = {
    "attempted_at",
    "success",
    "http_status",
    "failure_category",
    "latency_ms",
    "parsed_item_count",
    "accepted_inventory_count",
    "accepted_election_news_count",
}

CURRENT_RUN_FIELDS = {
    "run_at",
    "configured_routes",
    "due_routes",
    "attempted_routes",
    "successful_routes",
    "failed_routes",
    "zero_parsed_routes",
    "accepted_inventory_routes",
    "accepted_election_news_routes",
    "newly_repeated_failure_routes",
    "recovered_routes",
}


class SourceHealthError(ValueError):
    """Raised when source-health state cannot satisfy its contract."""


def utc_timestamp(value: datetime | str, *, field: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError as error:
            raise SourceHealthError(
                f"{field} must be a UTC ISO-8601 timestamp"
            ) from error
    else:
        raise SourceHealthError(
            f"{field} must be a UTC ISO-8601 timestamp"
        )

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceHealthError(f"{field} must include a UTC offset")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _is_non_negative_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _optional_non_negative_integer(value: Any) -> bool:
    return value is None or _is_non_negative_integer(value)


def _optional_timestamp(value: Any, *, field: str) -> None:
    if value is not None:
        utc_timestamp(value, field=field)


def validate_source_health(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SourceHealthError("source health must be a JSON object")
    if set(payload) != {
        "schema_version",
        "generated_at",
        "failure_threshold",
        "rolling_attempt_limit",
        "routes",
        "current_run",
    }:
        raise SourceHealthError("source health has unexpected top-level fields")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise SourceHealthError(
            f"source health schema_version must equal {SCHEMA_VERSION}"
        )
    utc_timestamp(payload["generated_at"], field="generated_at")
    if payload["failure_threshold"] != FAILURE_THRESHOLD:
        raise SourceHealthError("source health failure_threshold is unsupported")
    if payload["rolling_attempt_limit"] != ROLLING_ATTEMPT_LIMIT:
        raise SourceHealthError(
            "source health rolling_attempt_limit is unsupported"
        )

    routes = payload["routes"]
    if not isinstance(routes, list):
        raise SourceHealthError("source health routes must be an array")
    route_ids: list[str] = []
    for route in routes:
        if (
            not isinstance(route, dict)
            or not ROUTE_FIELDS.issubset(route)
            or not set(route).issubset(ROUTE_FIELDS | OPTIONAL_ROUTE_FIELDS)
        ):
            raise SourceHealthError(
                "source health route has unexpected fields"
            )
        route_id = route["route_id"]
        if not isinstance(route_id, str) or not route_id.strip():
            raise SourceHealthError("source health route_id is invalid")
        route_ids.append(route_id)
        if route["route_type"] not in ROUTE_TYPES:
            raise SourceHealthError(
                f"{route_id}: route_type is unsupported"
            )
        for field in ("publisher", "domain"):
            value = route[field]
            if value is not None and not isinstance(value, str):
                raise SourceHealthError(f"{route_id}: {field} is invalid")
        if not _optional_non_negative_integer(route["schedule_slot"]):
            raise SourceHealthError(
                f"{route_id}: schedule_slot is invalid"
            )
        if not isinstance(route["schedule_class"], str) or not route[
            "schedule_class"
        ].strip():
            raise SourceHealthError(
                f"{route_id}: schedule_class is invalid"
            )
        for field in ("configured", "enabled", "due_this_run"):
            if type(route[field]) is not bool:
                raise SourceHealthError(f"{route_id}: {field} is invalid")
        if route["status"] not in STATUSES:
            raise SourceHealthError(f"{route_id}: status is unsupported")
        for field in (
            "last_attempt_at",
            "last_success_at",
            "last_failure_at",
            "updated_at",
        ):
            _optional_timestamp(
                route[field],
                field=f"{route_id}.{field}",
            )
        if route["updated_at"] is None:
            raise SourceHealthError(f"{route_id}: updated_at is required")
        for field in (
            "consecutive_failures",
            "parsed_item_count",
            "accepted_inventory_count",
            "accepted_election_news_count",
            "rolling_attempt_count",
            "rolling_success_count",
            "rolling_parsed_items",
            "rolling_accepted_items",
            "rolling_election_news_items",
        ):
            if not _is_non_negative_integer(route[field]):
                raise SourceHealthError(f"{route_id}: {field} is invalid")
        for field in (
            "latest_http_status",
            "latest_latency_ms",
        ):
            if not _optional_non_negative_integer(route[field]):
                raise SourceHealthError(f"{route_id}: {field} is invalid")
        if (
            route["latest_failure_category"] is not None
            and (
                not isinstance(route["latest_failure_category"], str)
                or not route["latest_failure_category"].strip()
            )
        ):
            raise SourceHealthError(
                f"{route_id}: latest_failure_category is invalid"
            )
        for field in ("etag", "last_modified", "validator_url"):
            if field not in route:
                continue
            value = route[field]
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise SourceHealthError(f"{route_id}: {field} is invalid")
        for field in ("latest_attempt_count", "response_bytes"):
            if field in route and not _optional_non_negative_integer(
                route[field]
            ):
                raise SourceHealthError(f"{route_id}: {field} is invalid")
        if (
            "latest_not_modified" in route
            and type(route["latest_not_modified"]) is not bool
        ):
            raise SourceHealthError(
                f"{route_id}: latest_not_modified is invalid"
            )
        if route.get("latest_not_modified"):
            if (
                route["latest_http_status"] != 304
                or route["consecutive_failures"] != 0
                or route["parsed_item_count"] != 0
                or route.get("response_bytes") != 0
            ):
                raise SourceHealthError(
                    f"{route_id}: not-modified diagnostics are inconsistent"
                )

        history = route["attempt_history"]
        if (
            not isinstance(history, list)
            or len(history) > ROLLING_ATTEMPT_LIMIT
        ):
            raise SourceHealthError(
                f"{route_id}: attempt_history is invalid"
            )
        for attempt in history:
            if (
                not isinstance(attempt, dict)
                or set(attempt) != ATTEMPT_HISTORY_FIELDS
            ):
                raise SourceHealthError(
                    f"{route_id}: attempt history has unexpected fields"
                )
            utc_timestamp(
                attempt["attempted_at"],
                field=f"{route_id}.attempted_at",
            )
            if type(attempt["success"]) is not bool:
                raise SourceHealthError(
                    f"{route_id}: attempt success is invalid"
                )
            for field in (
                "http_status",
                "latency_ms",
            ):
                if not _optional_non_negative_integer(attempt[field]):
                    raise SourceHealthError(
                        f"{route_id}: attempt {field} is invalid"
                    )
            if (
                attempt["failure_category"] is not None
                and (
                    not isinstance(attempt["failure_category"], str)
                    or not attempt["failure_category"].strip()
                )
            ):
                raise SourceHealthError(
                    f"{route_id}: attempt failure_category is invalid"
                )
            for field in (
                "parsed_item_count",
                "accepted_inventory_count",
                "accepted_election_news_count",
            ):
                if not _is_non_negative_integer(attempt[field]):
                    raise SourceHealthError(
                        f"{route_id}: attempt {field} is invalid"
                    )

        expected_rolling = {
            "rolling_attempt_count": len(history),
            "rolling_success_count": sum(
                attempt["success"] for attempt in history
            ),
            "rolling_parsed_items": sum(
                attempt["parsed_item_count"] for attempt in history
            ),
            "rolling_accepted_items": sum(
                attempt["accepted_inventory_count"] for attempt in history
            ),
            "rolling_election_news_items": sum(
                attempt["accepted_election_news_count"]
                for attempt in history
            ),
        }
        for field, expected in expected_rolling.items():
            if route[field] != expected:
                raise SourceHealthError(
                    f"{route_id}: {field} does not match attempt_history"
                )
        if route["rolling_success_count"] > route["rolling_attempt_count"]:
            raise SourceHealthError(
                f"{route_id}: rolling success count is inconsistent"
            )

    if route_ids != sorted(route_ids):
        raise SourceHealthError("source health routes are not sorted")
    if len(route_ids) != len(set(route_ids)):
        raise SourceHealthError("source health route_ids are not unique")

    current_run = payload["current_run"]
    if (
        not isinstance(current_run, dict)
        or set(current_run) != CURRENT_RUN_FIELDS
    ):
        raise SourceHealthError(
            "source health current_run has unexpected fields"
        )
    utc_timestamp(current_run["run_at"], field="current_run.run_at")
    for field in (
        "configured_routes",
        "due_routes",
        "attempted_routes",
        "successful_routes",
        "failed_routes",
        "zero_parsed_routes",
        "accepted_inventory_routes",
        "accepted_election_news_routes",
    ):
        if not _is_non_negative_integer(current_run[field]):
            raise SourceHealthError(f"current_run.{field} is invalid")
    for field in (
        "newly_repeated_failure_routes",
        "recovered_routes",
    ):
        values = current_run[field]
        if (
            not isinstance(values, list)
            or values != sorted(values)
            or len(values) != len(set(values))
            or any(
                not isinstance(value, str) or not value.strip()
                for value in values
            )
        ):
            raise SourceHealthError(f"current_run.{field} is invalid")
    if (
        current_run["successful_routes"] + current_run["failed_routes"]
        != current_run["attempted_routes"]
    ):
        raise SourceHealthError(
            "current_run success/failure counts are inconsistent"
        )


def load_source_health(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise SourceHealthError(
            f"could not read previous source health {path}: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SourceHealthError(
            f"previous source health {path} is malformed JSON: {error}"
        ) from error
    validate_source_health(payload)
    return payload


def _validate_route_configuration(route: Any) -> None:
    required = {
        "route_id",
        "route_type",
        "publisher",
        "domain",
        "enabled",
        "schedule_class",
        "schedule_slot",
        "due_this_run",
    }
    if not isinstance(route, dict) or set(route) != required:
        raise SourceHealthError(
            "route configuration has unexpected fields"
        )
    if (
        not isinstance(route["route_id"], str)
        or not route["route_id"].strip()
    ):
        raise SourceHealthError("route configuration route_id is invalid")
    if route["route_type"] not in ROUTE_TYPES:
        raise SourceHealthError(
            f"{route['route_id']}: route configuration type is unsupported"
        )
    for field in ("enabled", "due_this_run"):
        if type(route[field]) is not bool:
            raise SourceHealthError(
                f"{route['route_id']}: {field} must be boolean"
            )
    if route["due_this_run"] and not route["enabled"]:
        raise SourceHealthError(
            f"{route['route_id']}: disabled route cannot be due"
        )


def _validate_attempt(attempt: Any) -> None:
    required = {
        "route_id",
        "success",
        "not_modified",
        "http_status",
        "failure_category",
        "latency_ms",
        "attempts",
        "response_bytes",
        "etag",
        "last_modified",
        "request_url",
        "parsed_item_count",
        "accepted_inventory_count",
        "accepted_election_news_count",
    }
    if not isinstance(attempt, dict) or set(attempt) != required:
        raise SourceHealthError("route attempt has unexpected fields")
    route_id = attempt["route_id"]
    if not isinstance(route_id, str) or not route_id.strip():
        raise SourceHealthError("route attempt route_id is invalid")
    if type(attempt["success"]) is not bool:
        raise SourceHealthError(f"{route_id}: attempt success is invalid")
    if type(attempt["not_modified"]) is not bool:
        raise SourceHealthError(
            f"{route_id}: attempt not_modified is invalid"
        )
    for field in ("http_status", "latency_ms"):
        if not _optional_non_negative_integer(attempt[field]):
            raise SourceHealthError(f"{route_id}: attempt {field} is invalid")
    if (
        attempt["failure_category"] is not None
        and (
            not isinstance(attempt["failure_category"], str)
            or not attempt["failure_category"].strip()
        )
    ):
        raise SourceHealthError(
            f"{route_id}: attempt failure_category is invalid"
        )
    for field in (
        "parsed_item_count",
        "accepted_inventory_count",
        "accepted_election_news_count",
    ):
        if not _is_non_negative_integer(attempt[field]):
            raise SourceHealthError(f"{route_id}: attempt {field} is invalid")
    if attempt["success"] and attempt["failure_category"] is not None:
        raise SourceHealthError(
            f"{route_id}: successful attempt cannot have failure category"
        )
    if not attempt["success"] and attempt["failure_category"] is None:
        raise SourceHealthError(
            f"{route_id}: failed attempt requires failure category"
        )
    if (
        not _is_non_negative_integer(attempt["attempts"])
        or not 1 <= attempt["attempts"] <= 3
    ):
        raise SourceHealthError(f"{route_id}: attempt count is invalid")
    if not _is_non_negative_integer(attempt["response_bytes"]):
        raise SourceHealthError(
            f"{route_id}: attempt response_bytes is invalid"
        )
    for field in ("etag", "last_modified"):
        value = attempt[field]
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            raise SourceHealthError(
                f"{route_id}: attempt {field} is invalid"
            )
    if (
        attempt["request_url"] is not None
        and (
            not isinstance(attempt["request_url"], str)
            or not attempt["request_url"].strip()
        )
    ):
        raise SourceHealthError(
            f"{route_id}: attempt request_url is invalid"
        )
    if attempt["not_modified"] and (
        not attempt["success"]
        or attempt["http_status"] != 304
        or attempt["response_bytes"] != 0
        or attempt["parsed_item_count"] != 0
    ):
        raise SourceHealthError(
            f"{route_id}: attempt not_modified is inconsistent"
        )


def _normalized_attempt(attempt: Any) -> dict[str, Any]:
    if not isinstance(attempt, dict):
        raise SourceHealthError("route attempt has unexpected fields")
    normalized = deepcopy(attempt)
    normalized.setdefault("not_modified", False)
    normalized.setdefault("attempts", 1)
    normalized.setdefault("response_bytes", 0)
    normalized.setdefault("etag", None)
    normalized.setdefault("last_modified", None)
    normalized.setdefault("request_url", None)
    return normalized


def _new_route(
    configuration: dict[str, Any],
    run_at: str,
) -> dict[str, Any]:
    enabled = configuration["enabled"]
    return {
        "route_id": configuration["route_id"],
        "route_type": configuration["route_type"],
        "publisher": configuration["publisher"],
        "domain": configuration["domain"],
        "configured": True,
        "enabled": enabled,
        "schedule_class": configuration["schedule_class"],
        "schedule_slot": configuration["schedule_slot"],
        "due_this_run": configuration["due_this_run"],
        "status": "never_attempted" if enabled else "disabled",
        "last_attempt_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "consecutive_failures": 0,
        "latest_http_status": None,
        "latest_failure_category": None,
        "latest_latency_ms": None,
        "latest_attempt_count": None,
        "latest_not_modified": False,
        "response_bytes": None,
        "etag": None,
        "last_modified": None,
        "validator_url": None,
        "parsed_item_count": 0,
        "accepted_inventory_count": 0,
        "accepted_election_news_count": 0,
        "rolling_attempt_count": 0,
        "rolling_success_count": 0,
        "rolling_parsed_items": 0,
        "rolling_accepted_items": 0,
        "rolling_election_news_items": 0,
        "updated_at": run_at,
        "attempt_history": [],
    }


def _apply_rolling_counts(route: dict[str, Any]) -> None:
    history = route["attempt_history"]
    route["rolling_attempt_count"] = len(history)
    route["rolling_success_count"] = sum(
        attempt["success"] for attempt in history
    )
    route["rolling_parsed_items"] = sum(
        attempt["parsed_item_count"] for attempt in history
    )
    route["rolling_accepted_items"] = sum(
        attempt["accepted_inventory_count"] for attempt in history
    )
    route["rolling_election_news_items"] = sum(
        attempt["accepted_election_news_count"] for attempt in history
    )


def update_source_health(
    previous: dict[str, Any] | None,
    route_configurations: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    run_at: datetime | str,
) -> dict[str, Any]:
    if previous is not None:
        validate_source_health(previous)
    normalized_run_at = utc_timestamp(run_at, field="run_at")

    configured_by_id: dict[str, dict[str, Any]] = {}
    for configuration in route_configurations:
        _validate_route_configuration(configuration)
        route_id = configuration["route_id"]
        if route_id in configured_by_id:
            raise SourceHealthError(
                f"duplicate route configuration: {route_id}"
            )
        configured_by_id[route_id] = deepcopy(configuration)

    attempts_by_id: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        normalized_attempt = _normalized_attempt(attempt)
        _validate_attempt(normalized_attempt)
        route_id = normalized_attempt["route_id"]
        if route_id in attempts_by_id:
            raise SourceHealthError(f"duplicate route attempt: {route_id}")
        attempts_by_id[route_id] = normalized_attempt

    expected_attempt_ids = {
        route_id
        for route_id, configuration in configured_by_id.items()
        if configuration["enabled"] and configuration["due_this_run"]
    }
    if set(attempts_by_id) != expected_attempt_ids:
        missing = sorted(expected_attempt_ids - set(attempts_by_id))
        unexpected = sorted(set(attempts_by_id) - expected_attempt_ids)
        raise SourceHealthError(
            "route attempts do not match due enabled routes "
            f"(missing={missing}, unexpected={unexpected})"
        )

    previous_by_id = {
        route["route_id"]: route
        for route in (previous or {}).get("routes", [])
    }
    routes: list[dict[str, Any]] = []
    newly_repeated: list[str] = []
    recovered: list[str] = []

    for route_id in sorted(configured_by_id):
        configuration = configured_by_id[route_id]
        old = previous_by_id.get(route_id)
        route = (
            deepcopy(old)
            if old is not None
            else _new_route(configuration, normalized_run_at)
        )
        route.update(
            {
                "route_type": configuration["route_type"],
                "publisher": configuration["publisher"],
                "domain": configuration["domain"],
                "configured": True,
                "enabled": configuration["enabled"],
                "schedule_class": configuration["schedule_class"],
                "schedule_slot": configuration["schedule_slot"],
                "due_this_run": configuration["due_this_run"],
                "updated_at": normalized_run_at,
            }
        )

        if not configuration["enabled"]:
            route["status"] = "disabled"
            route["due_this_run"] = False
            routes.append(route)
            continue
        if not configuration["due_this_run"]:
            route["status"] = (
                "never_attempted"
                if route["last_attempt_at"] is None
                else "not_due"
            )
            routes.append(route)
            continue

        attempt = attempts_by_id[route_id]
        prior_failures = route["consecutive_failures"]
        route.update(
            {
                "last_attempt_at": normalized_run_at,
                "latest_http_status": attempt["http_status"],
                "latest_failure_category": attempt["failure_category"],
                "latest_latency_ms": attempt["latency_ms"],
                "latest_attempt_count": attempt["attempts"],
                "latest_not_modified": attempt["not_modified"],
                "response_bytes": attempt["response_bytes"],
                "parsed_item_count": attempt["parsed_item_count"],
                "accepted_inventory_count": attempt[
                    "accepted_inventory_count"
                ],
                "accepted_election_news_count": attempt[
                    "accepted_election_news_count"
                ],
            }
        )
        history_entry = {
            key: attempt[key]
            for key in ATTEMPT_HISTORY_FIELDS
            if key != "attempted_at"
        }
        history_entry["attempted_at"] = normalized_run_at
        route["attempt_history"] = (
            route["attempt_history"] + [history_entry]
        )[-ROLLING_ATTEMPT_LIMIT:]
        _apply_rolling_counts(route)

        if attempt["success"]:
            if attempt["request_url"] is not None:
                same_validator_url = (
                    route.get("validator_url") == attempt["request_url"]
                )
                preserve_omitted = (
                    attempt["not_modified"] and same_validator_url
                )
                if preserve_omitted:
                    if attempt["etag"] is not None:
                        route["etag"] = attempt["etag"]
                    if attempt["last_modified"] is not None:
                        route["last_modified"] = attempt["last_modified"]
                else:
                    route["etag"] = attempt["etag"]
                    route["last_modified"] = attempt["last_modified"]
                route["validator_url"] = (
                    attempt["request_url"]
                    if route.get("etag") is not None
                    or route.get("last_modified") is not None
                    else None
                )
            route["last_success_at"] = normalized_run_at
            route["consecutive_failures"] = 0
            route["status"] = (
                "healthy_zero_yield"
                if attempt["parsed_item_count"] == 0
                else "healthy"
            )
            if prior_failures > 0:
                recovered.append(route_id)
        else:
            route["last_failure_at"] = normalized_run_at
            route["consecutive_failures"] = prior_failures + 1
            route["status"] = (
                "repeated_failure"
                if route["consecutive_failures"] >= FAILURE_THRESHOLD
                else "transient_failure"
            )
            if (
                prior_failures < FAILURE_THRESHOLD
                and route["consecutive_failures"] >= FAILURE_THRESHOLD
            ):
                newly_repeated.append(route_id)
        routes.append(route)

    for route_id in sorted(set(previous_by_id) - set(configured_by_id)):
        route = deepcopy(previous_by_id[route_id])
        route.update(
            {
                "configured": False,
                "enabled": False,
                "due_this_run": False,
                "status": "removed",
                "updated_at": normalized_run_at,
            }
        )
        routes.append(route)

    routes.sort(key=lambda route: route["route_id"])
    successful_attempts = [
        attempt for attempt in attempts if attempt["success"]
    ]
    failed_attempts = [
        attempt for attempt in attempts if not attempt["success"]
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": normalized_run_at,
        "failure_threshold": FAILURE_THRESHOLD,
        "rolling_attempt_limit": ROLLING_ATTEMPT_LIMIT,
        "routes": routes,
        "current_run": {
            "run_at": normalized_run_at,
            "configured_routes": len(configured_by_id),
            "due_routes": len(expected_attempt_ids),
            "attempted_routes": len(attempts),
            "successful_routes": len(successful_attempts),
            "failed_routes": len(failed_attempts),
            "zero_parsed_routes": sum(
                attempt["success"] and attempt["parsed_item_count"] == 0
                for attempt in attempts
            ),
            "accepted_inventory_routes": sum(
                attempt["success"]
                and attempt["accepted_inventory_count"] > 0
                for attempt in attempts
            ),
            "accepted_election_news_routes": sum(
                attempt["success"]
                and attempt["accepted_election_news_count"] > 0
                for attempt in attempts
            ),
            "newly_repeated_failure_routes": sorted(newly_repeated),
            "recovered_routes": sorted(recovered),
        },
    }
    validate_source_health(payload)
    return payload


def source_health_aggregate(payload: dict[str, Any]) -> dict[str, int]:
    validate_source_health(payload)
    current_run = payload["current_run"]
    configured_routes = [
        route for route in payload["routes"] if route["configured"]
    ]
    return {
        "configured_routes": current_run["configured_routes"],
        "attempted_routes": current_run["attempted_routes"],
        "successful_routes": current_run["successful_routes"],
        "failed_routes": current_run["failed_routes"],
        "repeated_failure_routes": sum(
            route["enabled"]
            and route["consecutive_failures"] >= FAILURE_THRESHOLD
            for route in configured_routes
        ),
        "healthy_zero_yield_routes": sum(
            route["enabled"]
            and route["last_success_at"] is not None
            and route["parsed_item_count"] == 0
            and route["consecutive_failures"] == 0
            for route in configured_routes
        ),
        "recovered_routes": len(current_run["recovered_routes"]),
    }


def substantive_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Return health semantics with timestamps and schedule-only state removed."""
    validate_source_health(payload)
    route_fields = (
        "route_id",
        "route_type",
        "publisher",
        "domain",
        "configured",
        "enabled",
        "schedule_class",
        "schedule_slot",
        "consecutive_failures",
        "latest_http_status",
        "latest_failure_category",
        "parsed_item_count",
        "accepted_inventory_count",
        "accepted_election_news_count",
        "rolling_attempt_count",
        "rolling_success_count",
        "rolling_parsed_items",
        "rolling_accepted_items",
        "rolling_election_news_items",
        "etag",
        "last_modified",
        "validator_url",
        "latest_attempt_count",
        "latest_not_modified",
        "response_bytes",
    )
    return {
        "schema_version": payload["schema_version"],
        "failure_threshold": payload["failure_threshold"],
        "rolling_attempt_limit": payload["rolling_attempt_limit"],
        "routes": [
            {field: route.get(field) for field in route_fields}
            for route in payload["routes"]
        ],
        "current_run": {
            field: payload["current_run"][field]
            for field in (
                "configured_routes",
                "attempted_routes",
                "successful_routes",
                "failed_routes",
                "zero_parsed_routes",
                "accepted_inventory_routes",
                "accepted_election_news_routes",
                "newly_repeated_failure_routes",
                "recovered_routes",
            )
        },
    }


def has_substantive_change(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    return substantive_projection(previous) != substantive_projection(current)


def write_source_health_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    validate_source_health(payload)
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
            json.dump(payload, handle, ensure_ascii=False, indent=2)
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
