#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import signal_engine
import social_publish


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RECENT_CHANGES = ROOT / "recent_changes.json"
DEFAULT_CAMPAIGN_EVENTS = ROOT / "campaign_events.json"

FR_SLOTS_WITH_ROUNDUP = (
    "08:45",
    "10:15",
    "12:15",
    "14:30",
    "16:45",
    "18:30",
    "20:15",
    "21:30",
)

FR_SLOTS_NO_ROUNDUP = (
    "10:15",
    "12:15",
    "14:30",
    "16:45",
    "18:30",
    "20:15",
    "21:30",
    "22:15",
)

EN_SLOTS = (
    "11:30",
    "19:30",
)

CORE_FAMILIES = (
    "candidate_visibility",
    "issues",
    "agenda",
)

PLANNER_STATE_SCHEMA_VERSION = 1

HORIZON_COOLDOWN_DAYS = {
    "daily": 1,
    "weekly": 7,
    "four_week": 14,
}

ENTITY_COOLDOWN_DAYS = 2


@dataclass(frozen=True)
class PlannedPost:
    locale: str
    slot: str
    lane: str
    key: str
    text: str
    score: float | None = None


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(value, dict):
        raise ValueError(
            f"{path} must contain an object"
        )

    return value


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    text = value.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(timezone.utc)


def _empty_preview_state(
    now: datetime,
    *,
    lookback_hours: int,
) -> dict[str, Any]:
    initialized = (
        now - timedelta(
            hours=max(
                lookback_hours + 1,
                25,
            )
        )
    )

    return {
        "schema_version": 1,
        "initialized_at": (
            initialized
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "updated_at": (
            initialized
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "seen": {
            "recent_changes": [],
            "campaign_events": [],
        },
    }



def new_planner_state() -> dict[str, Any]:
    return {
        "schema_version": (
            PLANNER_STATE_SCHEMA_VERSION
        ),
        "published_quantitative": [],
        "roundup_dates": [],
        "dynamic_updates": [],
    }


def validate_planner_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    if (
        state.get("schema_version")
        != PLANNER_STATE_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported planner-state schema"
        )

    if not isinstance(
        state.get("published_quantitative"),
        list,
    ):
        raise ValueError(
            "planner state requires "
            "published_quantitative list"
        )

    if not isinstance(
        state.get("roundup_dates"),
        list,
    ):
        raise ValueError(
            "planner state requires "
            "roundup_dates list"
        )

    if "dynamic_updates" not in state:
        state["dynamic_updates"] = []

    if not isinstance(
        state.get("dynamic_updates"),
        list,
    ):
        raise ValueError(
            "planner state requires "
            "dynamic_updates list"
        )

    return state



def planner_state_from_social_state(
    social_state: dict[str, Any],
) -> dict[str, Any]:
    # social_publish._validate_state performs
    # the backward-compatible legacy upgrade
    # and validates the seen registries.
    social_publish._validate_state(
        social_state
    )

    value = social_state["planner"]

    return validate_planner_state(
        value
    )


def attach_planner_state(
    social_state: dict[str, Any],
    planner_state: dict[str, Any],
) -> dict[str, Any]:
    social_publish._validate_state(
        social_state
    )

    social_state["planner"] = (
        validate_planner_state(
            planner_state
        )
    )

    return social_state


def save_social_state(
    path: Path,
    state: dict[str, Any],
) -> None:
    social_publish._validate_state(
        state
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_planner_state(
    path: Path | None,
) -> dict[str, Any]:
    if path is None or not path.exists():
        return new_planner_state()

    value = _load_json(path)

    return validate_planner_state(
        value
    )


def _planner_date(
    now: datetime,
):
    return (
        now
        .astimezone(
            social_publish.PARIS
        )
        .date()
    )


def _published_row_date(
    row: dict[str, Any],
):
    value = str(
        row.get("published_at") or ""
    )

    if not value:
        return None

    try:
        parsed = _parse_now(value)
    except ValueError:
        return None

    return _planner_date(parsed)


def _signal_observation_id(
    signal: signal_engine.Signal,
) -> str:
    return (
        f"{signal.family}:"
        f"{signal.horizon}:"
        f"{signal.entity_id}:"
        f"{signal.current_end}"
    )



def expected_latest_complete_utc_day(
    now: datetime,
):
    return (
        now
        .astimezone(timezone.utc)
        .date()
        - timedelta(days=1)
    )


def signal_is_fresh(
    signal: signal_engine.Signal,
    *,
    now: datetime,
) -> bool:
    try:
        end_date = datetime.strptime(
            signal.current_end,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return False

    return (
        end_date
        == expected_latest_complete_utc_day(
            now
        )
    )


def signal_available(
    signal: signal_engine.Signal,
    *,
    state: dict[str, Any],
    locale: str,
    now: datetime,
) -> bool:
    state = validate_planner_state(
        state
    )

    today = _planner_date(now)

    observation_id = (
        _signal_observation_id(signal)
    )

    for row in state[
        "published_quantitative"
    ]:
        if (
            str(row.get("locale"))
            != locale
        ):
            continue

        published_date = (
            _published_row_date(row)
        )

        if published_date is None:
            continue

        age_days = (
            today - published_date
        ).days

        if age_days < 0:
            continue

        # Never post exactly the same
        # observation twice.
        if (
            str(
                row.get(
                    "observation_id"
                )
            )
            == observation_id
        ):
            return False

        # One lane has its own natural
        # publishing cadence.
        if (
            str(row.get("family"))
            == signal.family
            and str(
                row.get("horizon")
            )
            == signal.horizon
        ):
            cooldown = (
                HORIZON_COOLDOWN_DAYS[
                    signal.horizon
                ]
            )

            if age_days < cooldown:
                return False

        # Avoid replacing a weekly candidate
        # post tomorrow with a daily post about
        # exactly the same candidate.
        if (
            str(row.get("family"))
            == signal.family
            and str(
                row.get("entity_id")
            )
            == signal.entity_id
            and age_days
            < ENTITY_COOLDOWN_DAYS
        ):
            return False

    return True


def roundup_available(
    *,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    today = (
        _planner_date(now)
        .isoformat()
    )

    return today not in {
        str(value)
        for value
        in state["roundup_dates"]
    }


def mark_post_published(
    state: dict[str, Any],
    post: PlannedPost,
    *,
    published_at: datetime,
) -> None:
    state = validate_planner_state(
        state
    )

    if post.lane == "today_events":
        today = (
            _planner_date(
                published_at
            )
            .isoformat()
        )

        values = set(
            str(value)
            for value
            in state["roundup_dates"]
        )

        values.add(today)

        state["roundup_dates"] = (
            sorted(values)
        )

        return

    if post.lane != "quantitative":
        return

    parts = post.key.split(":")

    if len(parts) != 5:
        return

    if parts[0] not in {
        "quant",
        "en-quant",
    }:
        return

    family = parts[1]
    horizon = parts[2]
    entity_id = parts[3]
    current_end = parts[4]

    observation_id = (
        f"{family}:"
        f"{horizon}:"
        f"{entity_id}:"
        f"{current_end}"
    )

    rows = state[
        "published_quantitative"
    ]

    # Idempotent state update.
    for row in rows:
        if (
            row.get("locale")
            == post.locale
            and row.get(
                "observation_id"
            )
            == observation_id
        ):
            return

    rows.append(
        {
            "locale": post.locale,
            "family": family,
            "horizon": horizon,
            "entity_id": entity_id,
            "current_end": current_end,
            "observation_id": (
                observation_id
            ),
            "published_at": (
                published_at
                .astimezone(
                    timezone.utc
                )
                .isoformat()
                .replace(
                    "+00:00",
                    "Z",
                )
            ),
        }
    )


def mark_plan_published(
    state: dict[str, Any],
    plan: dict[str, Any],
    *,
    published_at: datetime,
) -> None:
    for raw in [
        *plan.get("fr_posts", []),
        *plan.get("en_posts", []),
    ]:
        post = PlannedPost(
            locale=raw["locale"],
            slot=raw["slot"],
            lane=raw["lane"],
            key=raw["key"],
            text=raw["text"],
            score=raw.get("score"),
        )

        mark_post_published(
            state,
            post,
            published_at=published_at,
        )


def _scheduled_event_date(
    item: dict[str, Any],
) -> str:
    value = str(
        item.get("scheduled_start") or ""
    ).strip()

    if len(value) < 10:
        return ""

    if len(value) == 10:
        return value

    text = value

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return value[:10]

    if parsed.tzinfo is None:
        return value[:10]

    return (
        parsed
        .astimezone(social_publish.PARIS)
        .date()
        .isoformat()
    )


def _today_event_ids(
    campaign_events: dict[str, Any],
    *,
    now: datetime,
) -> set[str]:
    today = (
        now
        .astimezone(social_publish.PARIS)
        .date()
        .isoformat()
    )

    values: set[str] = set()

    for item in (
        campaign_events.get(
            "campaign_events"
        )
        or []
    ):
        if not isinstance(item, dict):
            continue

        if (
            _scheduled_event_date(item)
            != today
        ):
            continue

        event_id = str(
            item.get("event_id") or ""
        )

        if event_id:
            values.add(event_id)

    return values


def select_quantitative(
    signals: list[signal_engine.Signal],
    *,
    limit: int = 4,
    planner_state: dict[str, Any] | None = None,
    locale: str = "fr",
    now: datetime | None = None,
) -> list[signal_engine.Signal]:
    if planner_state is None:
        planner_state = new_planner_state()

    if now is None:
        now = datetime.now(
            timezone.utc
        )

    available = [
        signal
        for signal in signals
        if signal_available(
            signal,
            state=planner_state,
            locale=locale,
            now=now,
        )
    ]

    ranked = sorted(
        available,
        key=lambda item: (
            -item.score,
            item.family,
            item.horizon,
            item.entity_id,
        ),
    )

    selected: list[
        signal_engine.Signal
    ] = []

    used_entities: set[
        tuple[str, str]
    ] = set()

    family_counts: dict[str, int] = {}

    # First guarantee one strong signal from
    # each available editorial family.
    for family in CORE_FAMILIES:
        winner = next(
            (
                item
                for item in ranked
                if item.family == family
                and (
                    item.family,
                    item.entity_id,
                )
                not in used_entities
            ),
            None,
        )

        if winner is None:
            continue

        selected.append(winner)

        used_entities.add(
            (
                winner.family,
                winner.entity_id,
            )
        )

        family_counts[winner.family] = 1

        if len(selected) >= limit:
            return selected

    # Then allow one flex slot. No family may
    # occupy more than two quantitative posts.
    for signal in ranked:
        entity_key = (
            signal.family,
            signal.entity_id,
        )

        if entity_key in used_entities:
            continue

        if family_counts.get(
            signal.family,
            0,
        ) >= 2:
            continue

        selected.append(signal)
        used_entities.add(entity_key)

        family_counts[signal.family] = (
            family_counts.get(
                signal.family,
                0,
            )
            + 1
        )

        if len(selected) >= limit:
            break

    return selected


def select_english_quantitative(
    signals: list[signal_engine.Signal],
    *,
    limit: int = 2,
    planner_state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[signal_engine.Signal]:
    if planner_state is None:
        planner_state = new_planner_state()

    if now is None:
        now = datetime.now(
            timezone.utc
        )

    available = [
        signal
        for signal in signals
        if signal_available(
            signal,
            state=planner_state,
            locale="en",
            now=now,
        )
    ]

    ranked = sorted(
        available,
        key=lambda item: (
            -item.score,
            item.family,
            item.horizon,
            item.entity_id,
        ),
    )

    selected: list[
        signal_engine.Signal
    ] = []

    used_families: set[str] = set()

    for signal in ranked:
        if signal.family in used_families:
            continue

        selected.append(signal)
        used_families.add(
            signal.family
        )

        if len(selected) >= limit:
            break

    return selected



def diversify_updates(
    values: list[Any],
    recent_changes: dict[str, Any],
    *,
    limit: int,
    per_candidate_limit: int = 1,
) -> list[Any]:
    candidate_map = {
        str(item.get("id")): {
            str(candidate_id)
            for candidate_id
            in (
                item.get(
                    "candidate_ids"
                )
                or []
            )
            if str(candidate_id)
        }
        for item
        in (
            recent_changes.get("items")
            or []
        )
        if item.get("id")
    }

    counts: dict[str, int] = {}
    selected: list[Any] = []

    for item in values:
        candidate_ids = (
            candidate_map.get(
                item.key,
                set(),
            )
            if item.kind
            == "recent_change"
            else set()
        )

        if candidate_ids:
            blocked = any(
                counts.get(
                    candidate_id,
                    0,
                )
                >= per_candidate_limit
                for candidate_id
                in candidate_ids
            )

            if blocked:
                continue

        selected.append(item)

        for candidate_id in (
            candidate_ids
        ):
            counts[candidate_id] = (
                counts.get(
                    candidate_id,
                    0,
                )
                + 1
            )

        if len(selected) >= limit:
            break

    return selected


def collect_fresh_updates(
    recent_changes: dict[str, Any],
    campaign_events: dict[str, Any],
    *,
    now: datetime,
    lookback_hours: int,
    limit: int,
    suppress_today_events: bool,
    social_state: dict[str, Any] | None = None,
) -> tuple[
    list[Any],
    str | None,
]:
    state = (
        social_state
        if social_state is not None
        else _empty_preview_state(
            now,
            lookback_hours=lookback_hours,
        )
    )

    try:
        values = (
            social_publish
            .collect_update_candidates(
                recent_changes,
                campaign_events,
                state,
                now=now,
                lookback_hours=(
                    lookback_hours
                ),
            )
        )
    except Exception as exc:
        # Preview should still show the
        # quantitative/editorial plan even if
        # external URL decoding fails locally.
        return [], (
            f"{type(exc).__name__}: {exc}"
        )

    if suppress_today_events:
        today_ids = _today_event_ids(
            campaign_events,
            now=now,
        )

        values = [
            item
            for item in values
            if not (
                item.kind
                == "campaign_event"
                and item.key in today_ids
            )
        ]

    values = sorted(
        values,
        key=lambda item: (
            item.observed_at,
            item.kind,
            item.key,
        ),
        reverse=True,
    )

    values = diversify_updates(
        values,
        recent_changes,
        limit=limit,
        per_candidate_limit=1,
    )

    return values, None


def _build_fr_posts(
    *,
    roundup: str,
    quantitative: list[
        signal_engine.Signal
    ],
    updates: list[Any],
    max_posts: int,
    now: datetime,
) -> list[PlannedPost]:
    roundup = roundup.strip()

    posts: list[PlannedPost] = []

    if roundup:
        posts.append(
            PlannedPost(
                locale="fr",
                slot=(
                    FR_SLOTS_WITH_ROUNDUP[0]
                ),
                lane="today_events",
                key=(
                    "today-events:"
                    + now
                    .astimezone(
                        social_publish.PARIS
                    )
                    .date()
                    .isoformat()
                ),
                text=roundup,
            )
        )

    candidates: list[
        tuple[str, str, str, float | None]
    ] = []

    max_length = max(
        len(quantitative),
        len(updates),
    )

    # Interleave data and developments rather
    # than posting four metrics consecutively.
    for index in range(max_length):
        if index < len(quantitative):
            signal = quantitative[index]

            candidates.append(
                (
                    "quantitative",
                    (
                        "quant:"
                        f"{signal.family}:"
                        f"{signal.horizon}:"
                        f"{signal.entity_id}:"
                        f"{signal.current_end}"
                    ),
                    signal_engine.render_fr(
                        signal
                    ),
                    signal.score,
                )
            )

        if index < len(updates):
            update = updates[index]

            candidates.append(
                (
                    update.kind,
                    (
                        "update:"
                        f"{update.kind}:"
                        f"{update.key}"
                    ),
                    update.text,
                    None,
                )
            )

    slots = (
        FR_SLOTS_WITH_ROUNDUP
        if roundup
        else FR_SLOTS_NO_ROUNDUP
    )

    for candidate in candidates:
        if len(posts) >= max_posts:
            break

        slot_index = len(posts)

        if slot_index >= len(slots):
            break

        lane, key, text, score = (
            candidate
        )

        posts.append(
            PlannedPost(
                locale="fr",
                slot=slots[slot_index],
                lane=lane,
                key=key,
                text=text,
                score=score,
            )
        )

    return posts


def _build_en_posts(
    signals: list[signal_engine.Signal],
    *,
    max_posts: int,
    planner_state: dict[str, Any],
    now: datetime,
) -> list[PlannedPost]:
    selected = (
        select_english_quantitative(
            signals,
            limit=min(
                max_posts,
                len(EN_SLOTS),
            ),
            planner_state=planner_state,
            now=now,
        )
    )

    return [
        PlannedPost(
            locale="en",
            slot=EN_SLOTS[index],
            lane="quantitative",
            key=(
                "en-quant:"
                f"{signal.family}:"
                f"{signal.horizon}:"
                f"{signal.entity_id}:"
                f"{signal.current_end}"
            ),
            text=signal_engine.render_en(
                signal
            ),
            score=signal.score,
        )
        for index, signal
        in enumerate(selected)
    ]


def build_plan(
    *,
    candidate_payload: dict[str, Any],
    issue_payload: dict[str, Any],
    agenda_payload: dict[str, Any],
    recent_changes: dict[str, Any],
    campaign_events: dict[str, Any],
    now: datetime,
    max_fr: int = 8,
    max_en: int = 2,
    max_quantitative: int = 4,
    max_updates: int = 3,
    lookback_hours: int = 24,
    planner_state: dict[str, Any] | None = None,
    social_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if planner_state is None:
        if social_state is not None:
            planner_state = (
                planner_state_from_social_state(
                    social_state
                )
            )
        else:
            planner_state = (
                new_planner_state()
            )

    planner_state = validate_planner_state(
        planner_state
    )

    all_signals = (
        signal_engine.build_all_signals(
            candidate_payload=(
                candidate_payload
            ),
            issue_payload=issue_payload,
            agenda_payload=agenda_payload,
        )
    )

    signals = [
        signal
        for signal in all_signals
        if signal_is_fresh(
            signal,
            now=now,
        )
    ]

    stale_signal_count = (
        len(all_signals)
        - len(signals)
    )

    quantitative = select_quantitative(
        signals,
        limit=max_quantitative,
        planner_state=planner_state,
        locale="fr",
        now=now,
    )

    roundup = (
        social_publish
        .render_today_events(
            campaign_events,
            now=now,
        )
    )

    if not roundup_available(
        state=planner_state,
        now=now,
    ):
        roundup = ""

    roundup_present = bool(
        roundup.strip()
    )

    updates, update_error = (
        collect_fresh_updates(
            recent_changes,
            campaign_events,
            now=now,
            lookback_hours=(
                lookback_hours
            ),
            limit=max_updates,
            suppress_today_events=(
                roundup_present
            ),
            social_state=social_state,
        )
    )

    fr_posts = _build_fr_posts(
        roundup=roundup,
        quantitative=quantitative,
        updates=updates,
        max_posts=max_fr,
        now=now,
    )

    en_posts = _build_en_posts(
        signals,
        max_posts=max_en,
        planner_state=planner_state,
        now=now,
    )

    return {
        "generated_at": (
            now.isoformat()
        ),
        "rules": {
            "fr_max": max_fr,
            "en_max": max_en,
            "quantitative_max": (
                max_quantitative
            ),
            "fresh_update_max": (
                max_updates
            ),
            "lookback_hours": (
                lookback_hours
            ),
            "quantitative_core": list(
                CORE_FAMILIES
            ),
            "today_event_individual_posts_suppressed_when_roundup_present": True,
        },
        "counts": {
            "eligible_quantitative_signals": len(
                signals
            ),
            "stale_quantitative_signals_suppressed": (
                stale_signal_count
            ),
            "selected_quantitative": len(
                quantitative
            ),
            "fresh_updates": len(
                updates
            ),
            "roundup_present": (
                roundup_present
            ),
            "fr_posts": len(fr_posts),
            "en_posts": len(en_posts),
        },
        "update_preview_error": (
            update_error
        ),
        "selected_quantitative": [
            asdict(item)
            for item in quantitative
        ],
        "fresh_updates": [
            {
                "key": item.key,
                "kind": item.kind,
                "observed_at": (
                    item.observed_at
                    .isoformat()
                ),
                "text": item.text,
            }
            for item in updates
        ],
        "fr_posts": [
            asdict(item)
            for item in fr_posts
        ],
        "en_posts": [
            asdict(item)
            for item in en_posts
        ],
    }


def _print_posts(
    title: str,
    posts: list[dict[str, Any]],
) -> None:
    print(title)

    if not posts:
        print("(none)")
        return

    for index, post in enumerate(
        posts,
        start=1,
    ):
        score = post.get("score")

        score_text = (
            ""
            if score is None
            else f" score={score:.3f}"
        )

        print(
            f"{index}. "
            f"{post['slot']} "
            f"lane={post['lane']}"
            f"{score_text}"
        )

        print(post["text"])
        print("---")


def run_preview(
    args: argparse.Namespace,
) -> int:
    now = _parse_now(args.now)

    social_state = None

    if args.social_state:
        social_state = _load_json(
            Path(args.social_state)
        )

        planner_state = (
            planner_state_from_social_state(
                social_state
            )
        )

    else:
        planner_state = load_planner_state(
            Path(args.planner_state)
            if args.planner_state
            else None
        )

    plan = build_plan(
        candidate_payload=(
            signal_engine._load_json(
                Path(
                    args.candidate_history
                )
            )
        ),
        issue_payload=(
            signal_engine._load_json(
                Path(
                    args.issue_history
                )
            )
        ),
        agenda_payload=(
            signal_engine._load_json(
                Path(
                    args.agenda_history
                )
            )
        ),
        recent_changes=_load_json(
            Path(args.recent_changes)
        ),
        campaign_events=_load_json(
            Path(args.campaign_events)
        ),
        now=now,
        max_fr=args.fr,
        max_en=args.en,
        max_quantitative=(
            args.quantitative
        ),
        max_updates=args.updates,
        lookback_hours=args.lookback_hours,
        planner_state=planner_state,
        social_state=social_state,
    )

    print(
        "=== DAILY PLAN SUMMARY ==="
    )

    for key, value in (
        plan["counts"].items()
    ):
        print(f"{key}={value}")

    if plan["update_preview_error"]:
        print(
            "update_preview_error="
            + plan[
                "update_preview_error"
            ]
        )

    print()
    _print_posts(
        "=== FR DAILY QUEUE ===",
        plan["fr_posts"],
    )

    print()
    _print_posts(
        "=== EN DAILY QUEUE ===",
        plan["en_posts"],
    )

    print()
    print(
        "=== QUANTITATIVE MIX ==="
    )

    for signal in (
        plan[
            "selected_quantitative"
        ]
    ):
        print(
            f"{signal['family']:22} "
            f"{signal['horizon']:10} "
            f"{signal['entity_id']:36} "
            f"score={signal['score']:.3f}"
        )

    if args.json_output:
        path = Path(args.json_output)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                plan,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print()
        print(
            f"json_output={path}"
        )

    return 0



def run_state_upgrade(
    args: argparse.Namespace,
) -> int:
    state = _load_json(
        Path(args.state)
    )

    before_has_planner = (
        isinstance(
            state.get("planner"),
            dict,
        )
    )

    planner_state = (
        planner_state_from_social_state(
            state
        )
    )

    attach_planner_state(
        state,
        planner_state,
    )

    save_social_state(
        Path(args.output),
        state,
    )

    print(
        "legacy_planner_present="
        + str(before_has_planner)
    )

    print(
        "planner_schema_version="
        + str(
            planner_state[
                "schema_version"
            ]
        )
    )

    print(
        "published_quantitative="
        + str(
            len(
                planner_state[
                    "published_quantitative"
                ]
            )
        )
    )

    print(
        "roundup_dates="
        + str(
            len(
                planner_state[
                    "roundup_dates"
                ]
            )
        )
    )

    print(
        "recent_changes_seen="
        + str(
            len(
                state["seen"][
                    "recent_changes"
                ]
            )
        )
    )

    print(
        "campaign_events_seen="
        + str(
            len(
                state["seen"][
                    "campaign_events"
                ]
            )
        )
    )

    print(
        "state_output="
        + str(
            Path(args.output)
            .resolve()
        )
    )

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic FR27 "
            "daily X publishing plan"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    preview = sub.add_parser(
        "preview"
    )

    preview.add_argument(
        "--candidate-history",
        default=str(
            signal_engine
            .DEFAULT_CANDIDATE_HISTORY
        ),
    )

    preview.add_argument(
        "--issue-history",
        default=str(
            signal_engine
            .DEFAULT_ISSUE_HISTORY
        ),
    )

    preview.add_argument(
        "--agenda-history",
        default=str(
            signal_engine
            .DEFAULT_AGENDA_HISTORY
        ),
    )

    preview.add_argument(
        "--recent-changes",
        default=str(
            DEFAULT_RECENT_CHANGES
        ),
    )

    preview.add_argument(
        "--campaign-events",
        default=str(
            DEFAULT_CAMPAIGN_EVENTS
        ),
    )

    preview.add_argument(
        "--fr",
        type=int,
        default=8,
    )

    preview.add_argument(
        "--en",
        type=int,
        default=2,
    )

    preview.add_argument(
        "--quantitative",
        type=int,
        default=4,
    )

    preview.add_argument(
        "--updates",
        type=int,
        default=3,
    )

    preview.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
    )

    preview.add_argument(
        "--now",
    )

    preview.add_argument(
        "--json-output",
    )

    preview.add_argument(
        "--planner-state",
    )

    preview.add_argument(
        "--social-state",
        help=(
            "Unified social/x/state.json "
            "containing seen registries and "
            "nested planner state"
        ),
    )

    preview.set_defaults(
        func=run_preview
    )

    upgrade = sub.add_parser(
        "state-upgrade",
        help=(
            "upgrade legacy social state "
            "to unified planner state "
            "without publishing"
        ),
    )

    upgrade.add_argument(
        "--state",
        required=True,
    )

    upgrade.add_argument(
        "--output",
        required=True,
    )

    upgrade.set_defaults(
        func=run_state_upgrade
    )

    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
