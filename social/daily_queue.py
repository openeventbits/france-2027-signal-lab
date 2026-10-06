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
    published_at: str | None = None
    buffer_post_id: str | None = None


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
    if target["key"].startswith(weekly_flagship.PRODUCT_TYPE + ":"):
        if not flagship_revision or not isinstance(buffer_post_id, str) or not buffer_post_id.strip():
            raise ValueError("flagship publication requires a verified revision and successful Buffer receipt")
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

    if flagship_revision is not None:
        planner.setdefault(weekly_flagship.STATE_KEY, {})[post.key] = {
            "product_id": post.key, "revision": flagship_revision,
            "published_at": target["published_at"], "buffer_post_id": buffer_post_id,
        }

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

    post = resolve_slot_post(item, now=now, state=state)
    if post is None:
        return 0

    print(f"queue_item={item['id']}")

    print(
        post.text
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

    text = post.text.strip()

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
                post.text
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
