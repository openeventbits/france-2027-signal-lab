#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import daily_plan
import signal_engine
import social_publish


ROOT = Path(__file__).resolve().parents[1]

def _configure_utf8_stdio() -> None:
    """
    Make CLI output portable on Windows consoles whose
    default Python text encoding is cp1252.

    This affects terminal output only. It does not alter
    queue text, JSON serialization, or X post content.
    """
    for stream_name in (
        "stdout",
        "stderr",
    ):
        stream = getattr(
            sys,
            stream_name,
            None,
        )

        reconfigure = getattr(
            stream,
            "reconfigure",
            None,
        )

        if callable(reconfigure):
            reconfigure(
                encoding="utf-8",
                errors="replace",
            )


QUEUE_SCHEMA_VERSION = 1

FR27_BASE_URL = "https://france2027.app"
ROUTE_REGISTRY_PATH = ROOT / "route_registry.json"

CORE_FR_MAX = 5
CORE_EN_MAX = 2
CORE_QUANTITATIVE_MAX = 4


@dataclass
class QueueItem:
    id: str
    locale: str
    slot: str
    lane: str
    key: str
    text: str
    score: float | None
    status: str = "pending"
    published_at: str | None = None
    buffer_post_id: str | None = None


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(value, dict):
        raise ValueError(
            f"{path} must contain an object"
        )

    return value


def _parse_now(
    value: str | None,
) -> datetime:
    if not value:
        return datetime.now(
            timezone.utc
        )

    text = value.strip()

    if text.endswith("Z"):
        text = (
            text[:-1]
            + "+00:00"
        )

    parsed = datetime.fromisoformat(
        text
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _paris_date(
    now: datetime,
) -> str:
    return (
        now
        .astimezone(
            social_publish.PARIS
        )
        .date()
        .isoformat()
    )


def _queue_item_id(
    *,
    queue_date: str,
    locale: str,
    slot: str,
    key: str,
) -> str:
    return (
        f"{queue_date}:"
        f"{locale}:"
        f"{slot}:"
        f"{key}"
    )



@lru_cache(maxsize=1)
def _route_registry_entries(
) -> tuple[dict[str, Any], ...]:
    payload = _load_json(
        ROUTE_REGISTRY_PATH
    )

    routes = payload.get(
        "routes"
    )

    if not isinstance(
        routes,
        list,
    ):
        raise ValueError(
            "route_registry.json "
            "requires routes list"
        )

    return tuple(
        route
        for route in routes
        if isinstance(
            route,
            dict,
        )
    )


def _canonical_route_url(
    *,
    family: str,
    kind: str,
    entity_id: str,
    locale: str,
) -> str:
    matches = [
        route
        for route
        in _route_registry_entries()
        if (
            route.get("family")
            == family
            and route.get("kind")
            == kind
            and route.get("entity_id")
            == entity_id
            and route.get("language")
            == locale
        )
    ]

    if len(matches) != 1:
        raise ValueError(
            "expected exactly one "
            "canonical route for "
            f"{family}/"
            f"{kind}/"
            f"{entity_id}/"
            f"{locale}; "
            f"found {len(matches)}"
        )

    canonical = matches[0].get(
        "canonical_url"
    )

    if not isinstance(
        canonical,
        str,
    ) or not canonical:
        raise ValueError(
            "canonical route has no "
            "canonical_url"
        )

    if not canonical.startswith(
        FR27_BASE_URL + "/"
    ):
        raise ValueError(
            "canonical route is outside "
            "FR27 domain: "
            + canonical
        )

    return canonical


def quantitative_internal_url(
    raw: dict[str, Any],
) -> str:
    if (
        raw.get("lane")
        != "quantitative"
    ):
        return ""

    key = str(
        raw.get("key") or ""
    )

    parts = key.split(":")

    if (
        len(parts) != 5
        or parts[0]
        not in {
            "quant",
            "en-quant",
        }
    ):
        raise ValueError(
            "invalid quantitative "
            "queue key: "
            + key
        )

    family = parts[1]
    entity_id = parts[3]

    locale = str(
        raw.get("locale") or ""
    )

    if locale not in {
        "fr",
        "en",
    }:
        raise ValueError(
            "unsupported quantitative "
            "locale: "
            + locale
        )

    if family == "candidate_visibility":
        return _canonical_route_url(
            family="candidates",
            kind="candidate-detail",
            entity_id=entity_id,
            locale=locale,
        )

    if family == "issues":
        return _canonical_route_url(
            family="issues",
            kind="issue-detail",
            entity_id=entity_id,
            locale=locale,
        )

    if family == "agenda":
        return _canonical_route_url(
            family="agenda",
            kind="agenda-detail",
            entity_id=entity_id,
            locale=locale,
        )

    raise ValueError(
        "unsupported quantitative "
        "family: "
        + family
    )


def core_post_text(
    raw: dict[str, Any],
) -> str:
    text = str(
        raw.get("text") or ""
    ).strip()

    if raw.get("lane") == "newsroom":
        if (
            social_publish
            ._weighted_x_length(
                text
            )
            > social_publish.MAX_X_WEIGHTED_LENGTH
        ):
            raise ValueError(
                "newsroom queue post exceeds "
                "X weighted limit"
            )

        if (
            "https://france2027.app/"
            not in text
        ):
            raise ValueError(
                "newsroom queue post requires "
                "an FR27 destination URL"
            )

        return text

    if raw.get("lane") != "quantitative":
        return text

    url = quantitative_internal_url(
        raw
    )

    result = (
        social_publish._fit_with_url(
            text,
            url,
        )
    )

    if (
        social_publish
        ._weighted_x_length(
            result
        )
        > social_publish.MAX_X_WEIGHTED_LENGTH
    ):
        raise ValueError(
            "core quantitative post "
            "exceeds X weighted limit"
        )

    return result


def new_queue(
    *,
    queue_date: str,
    created_at: datetime,
    posts: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    items = []

    for raw in posts:
        item = QueueItem(
            id=_queue_item_id(
                queue_date=queue_date,
                locale=raw["locale"],
                slot=raw["slot"],
                key=raw["key"],
            ),
            locale=raw["locale"],
            slot=raw["slot"],
            lane=raw["lane"],
            key=raw["key"],
            text=core_post_text(raw),
            score=raw.get("score"),
        )

        items.append(
            asdict(item)
        )

    items.sort(
        key=lambda item: (
            item["slot"],
            item["locale"],
            item["id"],
        )
    )

    return {
        "schema_version":
            QUEUE_SCHEMA_VERSION,

        "date":
            queue_date,

        "created_at":
            created_at
            .astimezone(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            ),

        "items":
            items,
    }


def validate_queue(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "daily queue must be an object"
        )

    if (
        value.get(
            "schema_version"
        )
        != QUEUE_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported daily queue schema"
        )

    queue_date = value.get("date")

    if not isinstance(
        queue_date,
        str,
    ) or not queue_date:
        raise ValueError(
            "daily queue requires date"
        )

    items = value.get("items")

    if not isinstance(
        items,
        list,
    ):
        raise ValueError(
            "daily queue requires items"
        )

    ids: set[str] = set()

    for item in items:
        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                "daily queue item must "
                "be an object"
            )

        for field in (
            "id",
            "locale",
            "slot",
            "lane",
            "key",
            "text",
            "status",
        ):
            if not isinstance(
                item.get(field),
                str,
            ):
                raise ValueError(
                    "daily queue item "
                    f"requires {field}"
                )

        if item["status"] not in {
            "pending",
            "published",
        }:
            raise ValueError(
                "unsupported queue status"
            )

        if item["id"] in ids:
            raise ValueError(
                "duplicate queue item id"
            )

        ids.add(item["id"])

    return value


def planner_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    return (
        daily_plan
        .planner_state_from_social_state(
            state
        )
    )


def queue_from_state(
    state: dict[str, Any],
) -> dict[str, Any] | None:
    planner = planner_from_state(
        state
    )

    value = planner.get(
        "daily_queue"
    )

    if value is None:
        return None

    return validate_queue(
        value
    )


def attach_queue(
    state: dict[str, Any],
    queue: dict[str, Any],
) -> None:
    planner = planner_from_state(
        state
    )

    planner["daily_queue"] = (
        validate_queue(queue)
    )


def save_state(
    path: Path,
    state: dict[str, Any],
) -> None:
    daily_plan.save_social_state(
        path,
        state,
    )


def build_core_plan(
    *,
    state: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    return daily_plan.build_plan(
        candidate_payload=(
            signal_engine._load_json(
                signal_engine
                .DEFAULT_CANDIDATE_HISTORY
            )
        ),
        issue_payload=(
            signal_engine._load_json(
                signal_engine
                .DEFAULT_ISSUE_HISTORY
            )
        ),
        agenda_payload=(
            signal_engine._load_json(
                signal_engine
                .DEFAULT_AGENDA_HISTORY
            )
        ),
        recent_changes=_load_json(
            ROOT / "recent_changes.json"
        ),
        campaign_events=_load_json(
            ROOT / "campaign_events.json"
        ),
        now=now,
        max_fr=CORE_FR_MAX,
        max_en=CORE_EN_MAX,
        max_quantitative=(
            CORE_QUANTITATIVE_MAX
        ),
        # Dynamic developments are NOT part
        # of the immutable morning queue.
        max_updates=0,
        lookback_hours=24,
        social_state=state,
    )


def build_queue(
    *,
    state: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    queue_date = _paris_date(
        now
    )

    current = queue_from_state(
        state
    )

    # Idempotent same-day queue build.
    if (
        current is not None
        and current["date"]
        == queue_date
    ):
        return current

    plan = build_core_plan(
        state=state,
        now=now,
    )

    posts = [
        *plan.get(
            "fr_posts",
            []
        ),
        *plan.get(
            "en_posts",
            []
        ),
    ]

    queue = new_queue(
        queue_date=queue_date,
        created_at=now,
        posts=posts,
    )

    attach_queue(
        state,
        queue,
    )

    return queue


def pending_item_for_slot(
    queue: dict[str, Any],
    *,
    slot: str,
) -> dict[str, Any] | None:
    queue = validate_queue(
        queue
    )

    matches = [
        item
        for item
        in queue["items"]
        if (
            item["slot"] == slot
            and item["status"]
            == "pending"
        )
    ]

    if not matches:
        return None

    if len(matches) > 1:
        raise ValueError(
            f"multiple pending posts "
            f"for slot {slot}"
        )

    return matches[0]


def planned_post_from_item(
    item: dict[str, Any],
) -> daily_plan.PlannedPost:
    return daily_plan.PlannedPost(
        locale=item["locale"],
        slot=item["slot"],
        lane=item["lane"],
        key=item["key"],
        text=item["text"],
        score=item.get("score"),
    )


def mark_item_published(
    *,
    state: dict[str, Any],
    item: dict[str, Any],
    published_at: datetime,
    buffer_post_id: str,
) -> None:
    queue = queue_from_state(
        state
    )

    if queue is None:
        raise ValueError(
            "social state has no daily queue"
        )

    target = next(
        (
            row
            for row
            in queue["items"]
            if row["id"]
            == item["id"]
        ),
        None,
    )

    if target is None:
        raise ValueError(
            "queue item disappeared"
        )

    if (
        target["status"]
        == "published"
    ):
        return

    post = planned_post_from_item(
        target
    )

    planner = planner_from_state(
        state
    )

    daily_plan.mark_post_published(
        planner,
        post,
        published_at=published_at,
    )

    target["status"] = "published"

    target["published_at"] = (
        published_at
        .astimezone(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )

    target["buffer_post_id"] = (
        buffer_post_id
    )

    state["updated_at"] = (
        published_at
        .astimezone(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def queue_counts(
    queue: dict[str, Any],
) -> dict[str, int]:
    items = queue["items"]

    return {
        "total": len(items),

        "fr": sum(
            item["locale"] == "fr"
            for item in items
        ),

        "en": sum(
            item["locale"] == "en"
            for item in items
        ),

        "pending": sum(
            item["status"] == "pending"
            for item in items
        ),

        "published": sum(
            item["status"]
            == "published"
            for item in items
        ),
    }


def print_queue(
    queue: dict[str, Any],
) -> None:
    counts = queue_counts(
        queue
    )

    print(
        "queue_date="
        + queue["date"]
    )

    for key, value in (
        counts.items()
    ):
        print(
            f"{key}={value}"
        )

    print()

    for index, item in enumerate(
        queue["items"],
        start=1,
    ):
        print(
            f"{index}. "
            f"{item['slot']} "
            f"{item['locale']} "
            f"{item['lane']} "
            f"status={item['status']}"
        )

        print(
            item["text"]
        )

        print("---")


def run_build(
    args: argparse.Namespace,
) -> int:
    now = _parse_now(
        args.now
    )

    state_path = Path(
        args.state
    )

    output_path = Path(
        args.state_output
    )

    state = _load_json(
        state_path
    )

    social_publish._validate_state(
        state
    )

    queue = build_queue(
        state=state,
        now=now,
    )

    save_state(
        output_path,
        state,
    )

    if args.queue_output:
        queue_path = Path(
            args.queue_output
        )

        queue_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        queue_path.write_text(
            json.dumps(
                queue,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print_queue(queue)

    print(
        "state_output="
        + str(
            output_path.resolve()
        )
    )

    return 0


def run_slot(
    args: argparse.Namespace,
) -> int:
    now = _parse_now(
        args.now
    )

    state = _load_json(
        Path(args.state)
    )

    social_publish._validate_state(
        state
    )

    queue = queue_from_state(
        state
    )

    if queue is None:
        raise ValueError(
            "no daily queue in state"
        )

    today = _paris_date(
        now
    )

    if queue["date"] != today:
        print(
            "queue is not for today; "
            "skipping"
        )

        return 0

    item = pending_item_for_slot(
        queue,
        slot=args.slot,
    )

    if item is None:
        print(
            f"no pending item for "
            f"slot={args.slot}"
        )

        return 0

    print(
        f"queue_item={item['id']}"
    )

    print(
        item["text"]
    )

    if args.dry_run:
        print(
            "dry_run=true"
        )

        return 0

    client = (
        social_publish
        .BufferClient
        .from_env()
    )

    recent_texts = (
        client.recent_post_texts(
            since=(
                now
                - timedelta(
                    days=3
                )
            )
        )
    )

    text = item["text"].strip()

    if text in recent_texts:
        post_id = (
            "buffer-existing"
        )

        print(
            "already present in "
            "Buffer; resolving state"
        )

    else:
        post_id = (
            client.create_post(
                item["text"]
            )
        )

        print(
            "published queue item: "
            + post_id
        )

    mark_item_published(
        state=state,
        item=item,
        published_at=now,
        buffer_post_id=post_id,
    )

    save_state(
        Path(args.state_output),
        state,
    )

    print(
        "state_output="
        + str(
            Path(
                args.state_output
            ).resolve()
        )
    )

    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "FR27 immutable daily "
            "core X queue"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    build = sub.add_parser(
        "build"
    )

    build.add_argument(
        "--state",
        required=True,
    )

    build.add_argument(
        "--state-output",
        required=True,
    )

    build.add_argument(
        "--queue-output",
    )

    build.add_argument(
        "--now",
    )

    build.set_defaults(
        func=run_build
    )

    slot = sub.add_parser(
        "slot"
    )

    slot.add_argument(
        "--state",
        required=True,
    )

    slot.add_argument(
        "--state-output",
        required=True,
    )

    slot.add_argument(
        "--slot",
        required=True,
    )

    slot.add_argument(
        "--now",
    )

    slot.add_argument(
        "--dry-run",
        action="store_true",
    )

    slot.set_defaults(
        func=run_slot
    )

    return parser


def main() -> int:
    _configure_utf8_stdio()

    args = (
        build_parser()
        .parse_args()
    )

    return int(
        args.func(args)
    )


if __name__ == "__main__":
    raise SystemExit(main())
