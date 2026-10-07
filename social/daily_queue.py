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
import newsroom_products
import candidate_media_pulse
import radar_media
import weekly_flagship
import queue_metadata
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
MAX_CORE_LATENESS_MINUTES = 60
MIN_BUFFER_SCHEDULE_LEAD_MINUTES = 10

FR27_BASE_URL = "https://france2027.app"
ROUTE_REGISTRY_PATH = ROOT / "route_registry.json"

CORE_FR_MAX = 6
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
    scheduled_at: str | None = None
    scheduled_for: str | None = None
    published_at: str | None = None
    buffer_post_id: str | None = None
    delivery_status: str | None = None
    error_at: str | None = None


@dataclass(frozen=True)
class CoreSlotTimeliness:
    target: datetime
    lateness_minutes: float

    @property
    def eligible(self) -> bool:
        return 0 <= self.lateness_minutes <= MAX_CORE_LATENESS_MINUTES

    @property
    def reason(self) -> str:
        if self.lateness_minutes < 0:
            return "NOT_YET_DUE"
        return "ELIGIBLE" if self.eligible else "EXPIRED"


def core_slot_timeliness(*, queue_date: str, slot: str, now: datetime) -> CoreSlotTimeliness:
    """Canonical inclusive live window for exact slots and heartbeat recovery."""
    slot_time = datetime.strptime(slot, "%H:%M").time()
    if slot != slot_time.strftime("%H:%M"):
        raise ValueError("core queue slot must use HH:MM")
    target = datetime.combine(datetime.strptime(queue_date, "%Y-%m-%d").date(),
                              slot_time, tzinfo=social_publish.PARIS)
    lateness = (now.astimezone(timezone.utc) - target.astimezone(timezone.utc)).total_seconds() / 60
    return CoreSlotTimeliness(target=target, lateness_minutes=lateness)


@dataclass(frozen=True)
class ResolvedRadarPost(daily_plan.PlannedPost):
    radar_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResolvedFlagshipPost(daily_plan.PlannedPost):
    flagship_revision: str | None = None


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
    key = str(raw.get("key") or "")
    if key.startswith(weekly_flagship.PRODUCT_TYPE + ":"):
        parts = key.split(":")
        if (len(parts) != 4 or parts[3] != "fr" or raw.get("locale") != "fr"
                or raw.get("slot") != weekly_flagship.SLOT or raw.get("lane") != "weekly_flagship_slot"
                or raw.get("text") != "" or raw.get("score") is not None):
            raise ValueError("weekly flagship instruction must not contain frozen text or a score")
        monday = datetime.fromisoformat(parts[2]).date() + timedelta(days=1)
        if key != weekly_flagship.slot_instruction(monday).product_id:
            raise ValueError("invalid weekly flagship calendar-week identity")
        return ""
    if key.startswith(radar_media.PRODUCT_TYPE + ":"):
        parts = key.split(":")
        if (len(parts) != 4 or parts[1] != "slot" or parts[3] != "fr"
                or raw.get("locale") != "fr" or raw.get("slot") != radar_media.SLOT
                or raw.get("lane") != "radar_slot" or raw.get("text") != ""):
            raise ValueError("Radar slot instruction must not contain frozen text")
        return ""
    if key.startswith(candidate_media_pulse.PRODUCT_TYPE + ":"):
        parts = key.split(":")
        if (
            len(parts) != 4 or parts[3] != "fr"
            or raw.get("locale") != "fr"
            or raw.get("slot") != candidate_media_pulse.SLOT
        ):
            raise ValueError("invalid current candidate Media Pulse queue identity")
        if parts[1] == "slot":
            if raw.get("lane") != "candidate_slot" or raw.get("text") != "":
                raise ValueError("candidate slot instruction must not contain frozen text")
            return ""
        if raw.get("lane") != "newsroom":
            raise ValueError("invalid current candidate Media Pulse queue lane")
        canonical = candidate_media_pulse.canonical_candidate_url(
            {"routes": list(_route_registry_entries())}, parts[1],
        )
        text = raw["text"]
        if candidate_media_pulse.URL_RE.findall(text) != [canonical]:
            raise ValueError("candidate queue requires its exact canonical FR detail URL")
        if candidate_media_pulse.weighted_x_length(text) > 280:
            raise ValueError("candidate queue post exceeds X weighted limit")
        return text

    text = str(
        raw.get("text") or ""
    ).strip()

    if raw.get("lane") == "newsroom":
        # Only Issues/Agenda products use the Premium newsroom ceiling.
        # Other products keep the generic compact-post contract.
        limit = (
            newsroom_products.MAX_X_WEIGHTED_LENGTH
            if key.startswith((
                "issues_movers_", "issues_dominance_",
                "agenda_movers_", "agenda_dominance_",
            ))
            else social_publish.MAX_X_WEIGHTED_LENGTH
        )
        if (
            social_publish
            ._weighted_x_length(
                text
            )
            > limit
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
        if str(raw.get("key") or "").startswith(weekly_flagship.PRODUCT_TYPE + ":"):
            if raw["key"] != weekly_flagship.slot_instruction(datetime.fromisoformat(queue_date).date()).product_id:
                raise ValueError("flagship queue date must match its Monday publication date")
        if str(raw.get("key") or "").startswith(radar_media.PRODUCT_TYPE + ":"):
            parts = raw["key"].split(":")
            if len(parts) != 4 or parts[2] != queue_date:
                raise ValueError("Radar queue date must match its Paris date")
        if str(raw.get("key") or "").startswith(candidate_media_pulse.PRODUCT_TYPE + ":"):
            parts = raw["key"].split(":")
            if len(parts) != 4 or parts[2] != queue_date:
                raise ValueError("candidate queue period must match its Paris date")
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

        record = asdict(item)
        metadata = raw.get("metadata")
        if metadata is not None:
            record.update(queue_metadata.validate(metadata))
        else:
            existing_metadata = queue_metadata.from_item(raw)
            if existing_metadata is not None:
                record.update(existing_metadata)
        items.append(record)

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
            "scheduled",
            "published",
            "error",
        }:
            raise ValueError(
                "unsupported queue status"
            )

        for optional_field in (
            "scheduled_at",
            "scheduled_for",
            "published_at",
            "buffer_post_id",
            "delivery_status",
            "error_at",
        ):
            optional_value = item.get(
                optional_field
            )

            if (
                optional_value is not None
                and not isinstance(
                    optional_value,
                    str,
                )
            ):
                raise ValueError(
                    "daily queue item "
                    f"{optional_field} must "
                    "be a string or null"
                )

        if item["id"] in ids:
            raise ValueError(
                "duplicate queue item id"
            )

        ids.add(item["id"])
        queue_metadata.from_item(item)

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
        issue_payload=(
            _load_json(daily_plan.DEFAULT_ISSUE_HISTORY)
        ),
        agenda_payload=(
            _load_json(daily_plan.DEFAULT_AGENDA_HISTORY)
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

    if current is not None:
        unresolved_delivery = [
            item
            for item in current["items"]
            if item["status"] in {
                "scheduled",
                "error",
            }
        ]

        if unresolved_delivery:
            details = ", ".join(
                f"{item['id']}={item['status']}"
                for item in unresolved_delivery
            )

            raise ValueError(
                "cannot replace prior daily queue "
                "with unresolved Buffer deliveries: "
                + details
            )

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


def is_late_bound_item(
    item: dict[str, Any],
) -> bool:
    """Products that must still be resolved close to publication time."""
    lane = str(
        item.get("lane") or ""
    )

    key = str(
        item.get("key") or ""
    )

    if lane in {
        "candidate_slot",
        "radar_slot",
        "weekly_flagship_slot",
    }:
        return True

    return key.startswith(
        (
            candidate_media_pulse.PRODUCT_TYPE + ":",
            radar_media.PRODUCT_TYPE + ":",
            weekly_flagship.PRODUCT_TYPE + ":",
        )
    )


def queue_item_target(
    queue: dict[str, Any],
    item: dict[str, Any],
) -> datetime:
    slot_time = datetime.strptime(
        item["slot"],
        "%H:%M",
    ).time()

    queue_day = datetime.strptime(
        queue["date"],
        "%Y-%m-%d",
    ).date()

    return datetime.combine(
        queue_day,
        slot_time,
        tzinfo=social_publish.PARIS,
    )


def buffer_schedulable_items(
    queue: dict[str, Any],
    *,
    now: datetime,
    min_lead_minutes: int = MIN_BUFFER_SCHEDULE_LEAD_MINUTES,
    target_slot: str | None = None,
) -> list[dict[str, Any]]:
    """Frozen pending posts Buffer can safely own the clock for."""
    queue = validate_queue(
        queue
    )

    if target_slot is not None:
        slot_time = datetime.strptime(
            target_slot,
            "%H:%M",
        ).time()

        if target_slot != slot_time.strftime("%H:%M"):
            raise ValueError(
                "target Buffer slot must use HH:MM"
            )

    paris_now = now.astimezone(
        social_publish.PARIS
    )

    if (
        queue["date"]
        != paris_now.date().isoformat()
    ):
        return []

    selected: list[
        tuple[
            datetime,
            str,
            dict[str, Any],
        ]
    ] = []

    for item in queue["items"]:
        if item["status"] != "pending":
            continue

        if (
            target_slot is not None
            and item["slot"] != target_slot
        ):
            continue

        if is_late_bound_item(
            item
        ):
            continue

        if not str(
            item.get("text") or ""
        ).strip():
            continue

        target = queue_item_target(
            queue,
            item,
        )

        lead_minutes = (
            target.astimezone(timezone.utc)
            - now.astimezone(timezone.utc)
        ).total_seconds() / 60

        if (
            lead_minutes
            < max(
                0,
                min_lead_minutes,
            )
        ):
            continue

        selected.append(
            (
                target,
                item["id"],
                item,
            )
        )

    selected.sort(
        key=lambda row: (
            row[0],
            row[1],
        )
    )

    return [
        row[2]
        for row in selected
    ]


def _buffer_due_at(
    value: Any,
) -> datetime | None:
    text = str(
        value or ""
    ).strip()

    if not text:
        return None

    try:
        return _parse_now(
            text
        )
    except ValueError:
        return None


def _matching_buffer_post(
    posts: list[dict[str, Any]],
    *,
    item: dict[str, Any],
    target: datetime,
) -> dict[str, Any] | None:
    text = str(
        item.get("text") or ""
    ).strip()

    target_utc = target.astimezone(
        timezone.utc
    )

    for post in posts:
        if (
            str(
                post.get("text") or ""
            ).strip()
            != text
        ):
            continue

        if str(
            post.get("status") or ""
        ) not in {
            "scheduled",
            "sending",
            "sent",
        }:
            continue

        due_at = _buffer_due_at(
            post.get("dueAt")
        )

        if due_at is None:
            continue

        delta_seconds = abs(
            (
                due_at
                - target_utc
            ).total_seconds()
        )

        if delta_seconds <= 60:
            return post

    return None


def _target_item(
    *,
    state: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
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
            for row in queue["items"]
            if row["id"]
            == item["id"]
        ),
        None,
    )

    if target is None:
        raise ValueError(
            "queue item disappeared"
        )

    return target


def mark_item_scheduled(
    *,
    state: dict[str, Any],
    item: dict[str, Any],
    scheduled_at: datetime,
    scheduled_for: datetime,
    buffer_post_id: str,
    delivery_status: str = "scheduled",
) -> None:
    target = _target_item(
        state=state,
        item=item,
    )

    if target["status"] == "published":
        return

    if target["status"] not in {
        "pending",
        "scheduled",
    }:
        raise ValueError(
            "only pending/scheduled queue "
            "items can be scheduled"
        )

    target["status"] = "scheduled"

    target["scheduled_at"] = (
        scheduled_at
        .astimezone(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )

    target["scheduled_for"] = (
        scheduled_for
        .astimezone(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )

    target["buffer_post_id"] = (
        buffer_post_id
    )

    target["delivery_status"] = (
        delivery_status
    )

    target["published_at"] = None
    target["error_at"] = None

    state["updated_at"] = (
        target["scheduled_at"]
    )


def mark_item_delivery_error(
    *,
    state: dict[str, Any],
    item: dict[str, Any],
    observed_at: datetime,
) -> None:
    target = _target_item(
        state=state,
        item=item,
    )

    target["status"] = "error"
    target["delivery_status"] = "error"

    target["error_at"] = (
        observed_at
        .astimezone(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )

    state["updated_at"] = (
        target["error_at"]
    )


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
        metadata=queue_metadata.from_item(item),
    )


def resolve_slot_post(
    item: dict[str, Any], *, now: datetime, site_root: Path | None = None,
    state: dict[str, Any] | None = None,
) -> daily_plan.PlannedPost | None:
    """Resolve flagship, candidate and Radar instructions against current checkout files.

    Legacy Phase 4C candidate items are also refreshed, never replayed.
    Every other core post retains its exact morning key and text.
    """
    # A same-day immutable queue created by an older deployment must not
    # resurrect the Monday specialists replaced by the flagship.
    if (daily_plan._planner_date(now).weekday() == 0 and item.get("locale") == "fr"
            and item.get("slot") in daily_plan.MONDAY_SUPPRESSED_FR_SLOTS):
        print("monday_specialist_skipped=replaced by weekly flagship")
        return None
    if item["key"].startswith(weekly_flagship.PRODUCT_TYPE + ":") or item.get("lane") == "weekly_flagship_slot":
        try:
            expected = weekly_flagship.slot_instruction(daily_plan._planner_date(now)).product_id
            if (item["key"] != expected or item["locale"] != "fr" or item["slot"] != weekly_flagship.SLOT
                    or item.get("lane") != "weekly_flagship_slot" or item.get("text") != ""
                    or item.get("score") is not None or state is None):
                raise ValueError("invalid weekly flagship instruction")
            if expected in weekly_flagship.published_weeks(planner_from_state(state)):
                print("late_bound_flagship_skipped=completed week already published")
                return None
            product = weekly_flagship.load_product(root=site_root if site_root is not None else ROOT, now=now)
            if product.product_id != expected or not product.revision:
                raise ValueError("flagship must resolve the expected week from a verified revision")
            return ResolvedFlagshipPost(locale="fr", slot=weekly_flagship.SLOT, lane="newsroom",
                key=product.product_id, text=product.text, score=None, flagship_revision=product.revision,
                metadata=queue_metadata.flagship(daily_plan._planner_date(now), product))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
            print(f"late_bound_flagship_skipped={error}")
            return None
    if item["key"].startswith(radar_media.PRODUCT_TYPE + ":") or item.get("lane") == "radar_slot":
        try:
            expected = radar_media.slot_instruction(daily_plan._planner_date(now)).product_id
            if (item["key"] != expected or item["locale"] != "fr" or item["slot"] != radar_media.SLOT
                    or item.get("lane") != "radar_slot" or item.get("text") != ""):
                raise ValueError("invalid Radar slot instruction")
            if state is None:
                raise ValueError("Radar requires last successful publication state")
            product = radar_media.load_product(
                root=site_root if site_root is not None else ROOT, now=now,
                last_publication=planner_from_state(state).get(radar_media.STATE_KEY),
            )
            if product is None:
                print("late_bound_radar_skipped=unchanged meaningful payload")
                return None
            return ResolvedRadarPost(locale="fr", slot=radar_media.SLOT, lane="newsroom",
                                     key=product.product_id, text=product.text,
                                     radar_payload=product.payload, metadata=queue_metadata.radar(product))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
            print(f"late_bound_radar_skipped={error}")
            return None
    if not item["key"].startswith(candidate_media_pulse.PRODUCT_TYPE + ":"):
        if item.get("lane") == "candidate_slot":
            print("late_bound_candidate_skipped=invalid slot instruction")
            return None
        return planned_post_from_item(item)
    root = site_root if site_root is not None else ROOT
    try:
        parts = item["key"].split(":")
        if (len(parts) != 4 or parts[3] != "fr"
                or parts[2] != daily_plan._planner_date(now).isoformat()):
            raise ValueError("invalid candidate slot identity or date")
        if item["locale"] != "fr" or item["slot"] != candidate_media_pulse.SLOT:
            raise ValueError("invalid candidate slot locale or time")
        if parts[1] == "slot" and (item.get("lane") != "candidate_slot" or item.get("text") != ""):
            raise ValueError("candidate slot instruction must not contain frozen text")
        product = candidate_media_pulse.build_product(
            candidate_signals=candidate_media_pulse.load_json(root / "candidate_signals.json"),
            candidacy_registry=candidate_media_pulse.load_json(root / "candidate_candidacy_status.json"),
            route_registry=candidate_media_pulse.load_json(root / "route_registry.json"),
            planner_date=daily_plan._planner_date(now),
            site_root=root,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"late_bound_candidate_skipped={error}")
        return None
    if product is None:
        print("late_bound_candidate_skipped=stale period or no eligible reported evidence")
        return None
    return daily_plan.PlannedPost(
        locale=product.locale, slot=product.slot, lane="newsroom",
        key=product.product_id, text=product.text, score=product.score,
        metadata=queue_metadata.candidate(product),
    )


def mark_item_published(
    *,
    state: dict[str, Any],
    item: dict[str, Any],
    published_at: datetime,
    buffer_post_id: str,
    resolved_post: daily_plan.PlannedPost | None = None,
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

    radar_payload = getattr(resolved_post, "radar_payload", None)
    flagship_revision = getattr(resolved_post, "flagship_revision", None)
    flagship_receipt = None
    if target["key"].startswith(weekly_flagship.PRODUCT_TYPE + ":"):
        flagship_receipt = weekly_flagship.publication_receipt(
            product_id=target["key"], revision=flagship_revision,
            published_at=published_at, buffer_post_id=buffer_post_id)
        if resolved_post.key != target["key"]:
            raise ValueError("flagship publication week changed")
        weekly_flagship.published_weeks(planner_from_state(state))
    if target["key"].startswith(radar_media.PRODUCT_TYPE + ":") and radar_payload is None:
        raise ValueError("Radar publication requires its freshly resolved payload")
    if radar_payload is not None and (not isinstance(buffer_post_id, str) or not buffer_post_id.strip()):
        raise ValueError("Radar publication requires a successful Buffer receipt")
    resolved_metadata = (queue_metadata.validate(resolved_post.metadata)
                         if resolved_post is not None and resolved_post.metadata is not None else None)

    if resolved_post is not None:
        # Keep the stable slot ID; retain the actual successfully sent payload
        # for deduplication and the publication receipt.
        target.update(
            key=resolved_post.key, text=resolved_post.text,
            lane=resolved_post.lane, score=resolved_post.score,
        )
        if resolved_metadata is not None:
            target.update(resolved_metadata)

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

    if flagship_receipt is not None:
        weekly_flagship.record_receipt(planner, flagship_receipt)

    if radar_payload is not None:
        # This function is reached only after Buffer success (or an exact
        # existing-publication receipt). Never advance this state on resolution,
        # dry runs, unchanged skips or publication errors.
        planner[radar_media.STATE_KEY] = {
            "payload": radar_payload,
            "fingerprint": radar_media.fingerprint(radar_payload),
            "published_at": target["published_at"],
            "buffer_post_id": buffer_post_id,
        }

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

        "scheduled": sum(
            item["status"]
            == "scheduled"
            for item in items
        ),

        "published": sum(
            item["status"]
            == "published"
            for item in items
        ),

        "error": sum(
            item["status"]
            == "error"
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

    return execute_slot(args, state=state, now=now)


def execute_slot(
    args: argparse.Namespace, *, state: dict[str, Any], now: datetime,
) -> int:
    """The shared exact-slot and heartbeat executor; one publication at most."""
    queue = queue_from_state(
        state
    )

    if queue is None:
        raise ValueError(
            "no daily queue in state"
        )

    item = pending_item_for_slot(
        queue,
        slot=args.slot,
    )

    if item is None:
        print(
            f"no pending item for "
            f"slot={args.slot}"
        )
        print("PUBLICATION=NOOP")
        print("BUFFER_API_CALLED=false")

        return 0

    timing = core_slot_timeliness(queue_date=queue["date"], slot=item["slot"], now=now)
    print(f"slot={item['slot']} timeliness={timing.reason} "
          f"lateness_minutes={timing.lateness_minutes:g}")
    if not timing.eligible:
        if not args.dry_run:
            print(f"exact_slot=NOOP reason={timing.reason} "
                  f"lateness_minutes={timing.lateness_minutes:g}")
            print("PUBLICATION=SKIPPED")
            print(f"REASON=SLOT_{timing.reason}")
            print("BUFFER_API_CALLED=false")
            return 0
        preview_status = "STALE" if timing.reason == "EXPIRED" else timing.reason
        print(f"{preview_status} / WOULD_NOT_PUBLISH_LIVE "
              f"lateness_minutes={timing.lateness_minutes:g}")

    post = resolve_slot_post(item, now=now, state=state)
    if post is None:
        print("PUBLICATION=SKIPPED")
        print("REASON=PRODUCT_NOT_ELIGIBLE")
        print("BUFFER_API_CALLED=false")
        return 0

    print(f"queue_item={item['id']}")

    print(
        post.text
    )

    if args.dry_run:
        print(
            "dry_run=true"
        )
        print("PUBLICATION=PREVIEW")
        print("BUFFER_API_CALLED=false")

        return 0

    client = (
        social_publish
        .BufferClient
        .from_env()
    )

    recent_posts = (
        client.recent_posts(
            since=(
                now
                - timedelta(days=3)
            )
        )
    )

    text = post.text.strip()

    exact_delivery = _matching_buffer_post(
        recent_posts,
        item=item,
        target=timing.target,
    )

    publication_time = now

    if exact_delivery is not None:
        post_id = str(
            exact_delivery.get("id") or ""
        ).strip()

        delivery_status = str(
            exact_delivery.get("status") or ""
        ).strip()

        if delivery_status in {
            "scheduled",
            "sending",
        }:
            mark_item_scheduled(
                state=state,
                item=item,
                scheduled_at=now,
                scheduled_for=timing.target,
                buffer_post_id=post_id,
                delivery_status=delivery_status,
            )

            save_state(
                Path(args.state_output),
                state,
            )

            print("PUBLICATION=SCHEDULED_RECOVERED")
            print("BUFFER_API_CALLED=true")
            print("BUFFER_CREATE_CALLED=false")
            print("BUFFER_POST_ID=" + post_id)

            return 0

        if delivery_status == "sent":
            publication_time = (
                _buffer_due_at(
                    exact_delivery.get("dueAt")
                )
                or now
            )

            print("PUBLICATION=ALREADY_SENT")
            print("BUFFER_API_CALLED=true")
            print("BUFFER_CREATE_CALLED=false")

        else:
            raise RuntimeError(
                "unexpected Buffer status: "
                + delivery_status
            )

    else:
        exact_error = None

        for candidate in recent_posts:
            if (
                str(candidate.get("text") or "").strip()
                != text
            ):
                continue

            if (
                str(candidate.get("status") or "").strip()
                != "error"
            ):
                continue

            due_at = _buffer_due_at(
                candidate.get("dueAt")
            )

            if due_at is None:
                continue

            if abs(
                (
                    due_at
                    - timing.target.astimezone(
                        timezone.utc
                    )
                ).total_seconds()
            ) <= 60:
                exact_error = candidate
                break

        if exact_error is not None:
            post_id = str(
                exact_error.get("id") or ""
            ).strip()

            mark_item_delivery_error(
                state=state,
                item=item,
                observed_at=now,
            )

            target = _target_item(
                state=state,
                item=item,
            )

            target["buffer_post_id"] = post_id

            save_state(
                Path(args.state_output),
                state,
            )

            print("PUBLICATION=ERROR")
            print("BUFFER_API_CALLED=true")
            print("BUFFER_CREATE_CALLED=false")
            print("BUFFER_POST_ID=" + post_id)

            return 0

        sent_candidates = []

        live_window_start = (
            timing.target
            .astimezone(timezone.utc)
            - timedelta(minutes=5)
        )

        live_window_end = (
            now.astimezone(timezone.utc)
            + timedelta(minutes=5)
        )

        for candidate in recent_posts:
            if (
                str(
                    candidate.get("text")
                    or ""
                ).strip()
                != text
            ):
                continue

            if (
                str(
                    candidate.get("status")
                    or ""
                ).strip()
                != "sent"
            ):
                continue

            observed = (
                _buffer_due_at(
                    candidate.get("createdAt")
                )
                or _buffer_due_at(
                    candidate.get("dueAt")
                )
            )

            if (
                observed is not None
                and live_window_start
                <= observed
                <= live_window_end
            ):
                sent_candidates.append(
                    (
                        observed,
                        candidate,
                    )
                )

        if sent_candidates:
            sent_candidates.sort(
                key=lambda row: row[0],
                reverse=True,
            )

            publication_time, receipt = (
                sent_candidates[0]
            )

            post_id = str(
                receipt.get("id")
                or ""
            ).strip()

            print(
                "recovered existing Buffer "
                "sent shareNow delivery"
            )
            print("PUBLICATION=ALREADY_SENT")
            print("BUFFER_API_CALLED=true")
            print("BUFFER_CREATE_CALLED=false")
            print("BUFFER_POST_ID=" + post_id)

        else:
            post_id = client.create_post(
                post.text
            )

            publication_time = now

            print(
                "published queue item: "
                + post_id
            )
            print("PUBLICATION=SUBMITTED_NOW")
            print("BUFFER_API_CALLED=true")
            print("BUFFER_CREATE_CALLED=true")
            print("BUFFER_POST_ID=" + post_id)

    mark_item_published(
        state=state,
        item=item,
        published_at=publication_time,
        buffer_post_id=post_id,
        resolved_post=post,
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


def fallback_item(
    queue: dict[str, Any], *, now: datetime,
) -> dict[str, Any] | None:
    """Select the oldest pending slot within today's inclusive recovery window."""
    queue = validate_queue(queue)
    paris_now = now.astimezone(social_publish.PARIS)
    if queue["date"] != paris_now.date().isoformat():
        return None
    eligible = []
    for item in queue["items"]:
        if item["status"] != "pending":
            continue
        if not item["id"].startswith(queue["date"] + ":"):
            continue
        timing = core_slot_timeliness(queue_date=queue["date"], slot=item["slot"], now=now)
        if timing.eligible:
            eligible.append((timing.target, item["id"], item))
    return min(eligible, key=lambda row: (row[0], row[1]))[2] if eligible else None


def run_scheduler_tick(args: argparse.Namespace) -> int:
    now = _parse_now(args.now)
    state = _load_json(Path(args.state))
    social_publish._validate_state(state)
    queue = queue_from_state(state)
    queue_built = queue is None or queue["date"] != _paris_date(now)
    if queue_built:
        # The existing builder is idempotent and never bootstraps state.
        queue = build_queue(state=state, now=now)
        print("scheduler_queue_built=true")

    item = fallback_item(queue, now=now)
    if item is None:
        print("scheduler_tick=NOOP slot=NONE lateness_minutes=NONE")
        print("PUBLICATION=NOOP")
        print("BUFFER_API_CALLED=false")
        result = 0
    else:
        timing = core_slot_timeliness(queue_date=queue["date"], slot=item["slot"], now=now)
        print(f"scheduler_tick=SELECTED queue_item={item['id']} slot={item['slot']} "
              f"lateness_minutes={timing.lateness_minutes:g}")
        slot_args = argparse.Namespace(**vars(args), slot=item["slot"])
        # No separate Buffer or late-bound resolution logic. Exceptions propagate
        # without writing state, leaving the persisted item pending for retry.
        result = execute_slot(slot_args, state=state, now=now)

    if args.dry_run:
        print("scheduler_tick_dry_run=true")
    elif queue_built:
        # Persist a recovered queue even on NOOP/expected product skip. For an
        # existing queue the executor writes only after success/duplicate receipt.
        save_state(Path(args.state_output), state)
    return result


def run_schedule_frozen(
    args: argparse.Namespace,
) -> int:
    now = _parse_now(
        args.now
    )

    state = _load_json(
        Path(
            args.state
        )
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

    items = buffer_schedulable_items(
        queue,
        now=now,
        min_lead_minutes=(
            args.min_lead_minutes
        ),
        target_slot=args.slot,
    )

    print(
        "buffer_schedulable_count="
        + str(
            len(items)
        )
    )

    for item in items:
        target = queue_item_target(
            queue,
            item,
        )

        print(
            "BUFFER_SCHEDULE_PLAN "
            f"queue_item={item['id']} "
            f"slot={item['slot']} "
            "due_at="
            + target
            .astimezone(timezone.utc)
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )

    if args.dry_run:
        print(
            "BUFFER_CALLED=false"
        )

        print(
            "PUBLICATION=SCHEDULE_PREVIEW"
        )

        return 0

    if not items:
        print(
            "BUFFER_CALLED=false"
        )

        print(
            "PUBLICATION=NOOP"
        )

        return 0

    client = (
        social_publish
        .BufferClient
        .from_env()
    )

    recent_posts = (
        client.recent_posts(
            since=(
                now
                - timedelta(
                    days=3
                )
            )
        )
    )

    scheduled_count = 0
    recovered_count = 0

    for item in items:
        target = queue_item_target(
            queue,
            item,
        )

        existing = (
            _matching_buffer_post(
                recent_posts,
                item=item,
                target=target,
            )
        )

        if existing is not None:
            receipt = {
                "id": str(
                    existing.get(
                        "id"
                    )
                    or ""
                ),
                "status": str(
                    existing.get(
                        "status"
                    )
                    or "scheduled"
                ),
                "dueAt": str(
                    existing.get(
                        "dueAt"
                    )
                    or ""
                ),
            }

            recovered_count += 1

            print(
                "BUFFER_SCHEDULE_RECOVERED "
                f"queue_item={item['id']} "
                f"buffer_post_id={receipt['id']}"
            )
        else:
            receipt = (
                client
                .create_scheduled_post(
                    item["text"],
                    due_at=target,
                )
            )

        post_id = str(
            receipt.get("id")
            or ""
        ).strip()

        if not post_id:
            raise RuntimeError(
                "Buffer scheduling receipt "
                "has no post id"
            )

        delivery_status = str(
            receipt.get(
                "status"
            )
            or "scheduled"
        ).strip()

        if delivery_status not in {
            "scheduled",
            "sending",
            "sent",
        }:
            raise RuntimeError(
                "unexpected Buffer "
                "scheduled-post status: "
                + delivery_status
            )

        returned_due = _buffer_due_at(
            receipt.get(
                "dueAt"
            )
        )

        if returned_due is not None:
            delta_seconds = abs(
                (
                    returned_due
                    - target.astimezone(
                        timezone.utc
                    )
                ).total_seconds()
            )

            if delta_seconds > 60:
                raise RuntimeError(
                    "Buffer returned a dueAt "
                    "that does not match the "
                    "FR27 slot"
                )

        mark_item_scheduled(
            state=state,
            item=item,
            scheduled_at=now,
            scheduled_for=target,
            buffer_post_id=post_id,
            delivery_status=(
                delivery_status
            ),
        )

        recent_posts.append(
            {
                "id": post_id,
                "text": item["text"],
                "dueAt": (
                    target
                    .astimezone(
                        timezone.utc
                    )
                    .isoformat()
                    .replace(
                        "+00:00",
                        "Z",
                    )
                ),
                "status": (
                    delivery_status
                ),
            }
        )

        scheduled_count += 1

        print(
            "PUBLICATION=SCHEDULED "
            f"queue_item={item['id']} "
            f"buffer_post_id={post_id} "
            f"buffer_status={delivery_status}"
        )

    save_state(
        Path(
            args.state_output
        ),
        state,
    )

    print(
        f"BUFFER_SCHEDULED={scheduled_count}"
    )

    print(
        f"BUFFER_RECOVERED={recovered_count}"
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


def run_reconcile_buffer(
    args: argparse.Namespace,
) -> int:
    now = _parse_now(
        args.now
    )

    state = _load_json(
        Path(
            args.state
        )
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

    scheduled = [
        item
        for item
        in queue["items"]
        if item["status"]
        == "scheduled"
    ]

    print(
        "buffer_reconcile_count="
        + str(
            len(scheduled)
        )
    )

    if not scheduled:
        print(
            "PUBLICATION=NOOP"
        )

        return 0

    if args.dry_run:
        for item in scheduled:
            print(
                "BUFFER_RECONCILE_PREVIEW "
                f"queue_item={item['id']} "
                "buffer_post_id="
                + str(
                    item.get(
                        "buffer_post_id"
                    )
                    or ""
                )
            )

        print(
            "BUFFER_CALLED=false"
        )

        return 0

    client = (
        social_publish
        .BufferClient
        .from_env()
    )

    posts = client.recent_posts(
        since=(
            now
            - timedelta(
                days=3
            )
        )
    )

    by_id = {
        str(
            post.get("id")
            or ""
        ): post
        for post in posts
        if str(
            post.get("id")
            or ""
        )
    }

    confirmed = 0
    errors = 0
    pending_delivery = 0
    missing = 0
    mutated = False

    for item in scheduled:
        post_id = str(
            item.get(
                "buffer_post_id"
            )
            or ""
        ).strip()

        post = by_id.get(
            post_id
        )

        if post is None:
            missing += 1

            print(
                "BUFFER_RECONCILE_MISSING "
                f"queue_item={item['id']} "
                f"buffer_post_id={post_id}"
            )

            continue

        status = str(
            post.get(
                "status"
            )
            or ""
        ).strip()

        print(
            "BUFFER_RECONCILE "
            f"queue_item={item['id']} "
            f"buffer_post_id={post_id} "
            f"buffer_status={status}"
        )

        if status in {
            "scheduled",
            "sending",
        }:
            pending_delivery += 1

            target = _target_item(
                state=state,
                item=item,
            )

            if (
                target.get(
                    "delivery_status"
                )
                != status
            ):
                target[
                    "delivery_status"
                ] = status

                state[
                    "updated_at"
                ] = (
                    now
                    .astimezone(
                        timezone.utc
                    )
                    .isoformat()
                    .replace(
                        "+00:00",
                        "Z",
                    )
                )

                mutated = True

            continue

        if status == "sent":
            published_at = (
                _buffer_due_at(
                    post.get(
                        "dueAt"
                    )
                )
                or now
            )

            mark_item_published(
                state=state,
                item=item,
                published_at=(
                    published_at
                ),
                buffer_post_id=(
                    post_id
                ),
                resolved_post=(
                    planned_post_from_item(
                        item
                    )
                ),
            )

            target = _target_item(
                state=state,
                item=item,
            )

            target[
                "delivery_status"
            ] = "sent"

            confirmed += 1
            mutated = True

            print(
                "PUBLICATION=CONFIRMED "
                f"queue_item={item['id']}"
            )

            continue

        if status == "error":
            mark_item_delivery_error(
                state=state,
                item=item,
                observed_at=now,
            )

            errors += 1
            mutated = True

            print(
                "PUBLICATION=ERROR "
                f"queue_item={item['id']}"
            )

            continue

        raise RuntimeError(
            "unsupported Buffer delivery "
            f"status: {status}"
        )

    if mutated:
        save_state(
            Path(
                args.state_output
            ),
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

    print(
        f"BUFFER_CONFIRMED={confirmed}"
    )

    print(
        f"BUFFER_ERRORS={errors}"
    )

    print(
        "BUFFER_PENDING_DELIVERY="
        + str(
            pending_delivery
        )
    )

    print(
        f"BUFFER_MISSING={missing}"
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

    tick = sub.add_parser("scheduler-tick", help="Recover one missed core slot, at most 60 minutes late")
    tick.add_argument("--state", required=True)
    tick.add_argument("--state-output", required=True)
    tick.add_argument("--now")
    tick.add_argument("--dry-run", action="store_true")
    tick.set_defaults(func=run_scheduler_tick)

    schedule = sub.add_parser(
        "schedule-frozen",
        help=(
            "Schedule frozen core posts "
            "into Buffer at exact slots"
        ),
    )
    schedule.add_argument(
        "--state",
        required=True,
    )
    schedule.add_argument(
        "--state-output",
        required=True,
    )
    schedule.add_argument(
        "--now",
    )
    schedule.add_argument(
        "--slot",
    )
    schedule.add_argument(
        "--min-lead-minutes",
        type=int,
        default=(
            MIN_BUFFER_SCHEDULE_LEAD_MINUTES
        ),
    )
    schedule.add_argument(
        "--dry-run",
        action="store_true",
    )
    schedule.set_defaults(
        func=run_schedule_frozen
    )

    reconcile = sub.add_parser(
        "reconcile-buffer",
        help=(
            "Reconcile scheduled Buffer "
            "posts to sent/error state"
        ),
    )
    reconcile.add_argument(
        "--state",
        required=True,
    )
    reconcile.add_argument(
        "--state-output",
        required=True,
    )
    reconcile.add_argument(
        "--now",
    )
    reconcile.add_argument(
        "--dry-run",
        action="store_true",
    )
    reconcile.set_defaults(
        func=run_reconcile_buffer
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
