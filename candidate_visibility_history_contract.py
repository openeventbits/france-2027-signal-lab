from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import Any


SCHEMA_VERSION = "1.0"
EXPECTED_DAYS = 29

CAMPAIGN_LANE = "campaign_attention"
GENERAL_LANE = "general_visibility"

PRIMARY_SCOPES = ("election", "campaign")
GENERAL_SCOPE = "general"

METHODOLOGY_SOURCE = "news_wire.json:candidate_watch"
METHODOLOGY_METRIC = "candidate_share_of_lane_records"
METHODOLOGY_CANDIDATE_LINKAGE = "published_candidate_matches"

NOT_MEASURES = (
    "sentiment",
    "approval",
    "electoral support",
    "voting intention",
)


class CandidateVisibilityHistoryContractError(ValueError):
    """Raised when Candidate Visibility History violates its public contract."""


def _fail(message: str) -> None:
    raise CandidateVisibilityHistoryContractError(message)


def _require_object(
    value: Any,
    field: str,
    *,
    keys: set[str] | None = None,
) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{field} must be an object")

    if keys is not None and set(value) != keys:
        missing = sorted(keys - set(value))
        unexpected = sorted(set(value) - keys)
        _fail(
            f"{field} must have exact keys; "
            f"missing={missing}, unexpected={unexpected}"
        )

    return value


def _require_list(
    value: Any,
    field: str,
) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{field} must be an array")
    return value


def _require_text(
    value: Any,
    field: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        _fail(f"{field} must be non-empty trimmed text")
    return value


def _require_non_negative_integer(
    value: Any,
    field: str,
) -> int:
    if (
        type(value) is not int
        or value < 0
    ):
        _fail(f"{field} must be a non-negative integer")
    return value


def _require_calendar_date(
    value: Any,
    field: str,
) -> date:
    text = _require_text(value, field)

    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise CandidateVisibilityHistoryContractError(
            f"{field} must be a valid canonical YYYY-MM-DD date"
        ) from error

    if parsed.isoformat() != text:
        _fail(f"{field} must be a canonical YYYY-MM-DD date")

    return parsed


def round_visibility_ratio(value: float) -> float:
    """Return the locked three-decimal FR27 visibility ratio."""

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        _fail("visibility ratio input must be finite and non-negative")

    return math.floor(float(value) * 1000 + 0.5) / 1000


def _expected_dates(
    start_date: date,
) -> list[str]:
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(EXPECTED_DAYS)
    ]


def _validate_period(
    value: Any,
) -> list[str]:
    period = _require_object(
        value,
        "period",
        keys={
            "start_date",
            "end_date",
            "days",
            "data_as_of",
            "day_boundary",
            "current_utc_day_excluded",
        },
    )

    start_date = _require_calendar_date(
        period["start_date"],
        "period.start_date",
    )
    end_date = _require_calendar_date(
        period["end_date"],
        "period.end_date",
    )
    data_as_of = _require_calendar_date(
        period["data_as_of"],
        "period.data_as_of",
    )

    if period["days"] != EXPECTED_DAYS:
        _fail(
            f"period.days must equal {EXPECTED_DAYS}"
        )

    if (
        end_date
        != start_date + timedelta(days=EXPECTED_DAYS - 1)
    ):
        _fail(
            "period must span exactly 29 complete UTC calendar days"
        )

    if data_as_of != end_date:
        _fail("period.data_as_of must equal period.end_date")

    if period["day_boundary"] != "UTC":
        _fail("period.day_boundary must equal UTC")

    if period["current_utc_day_excluded"] is not True:
        _fail(
            "period.current_utc_day_excluded must be true"
        )

    return _expected_dates(start_date)


def _validate_methodology(
    value: Any,
) -> None:
    methodology = _require_object(
        value,
        "methodology",
        keys={
            "source",
            "primary_scopes",
            "general_scope",
            "metric",
            "candidate_linkage",
            "not_measures",
        },
    )

    if methodology["source"] != METHODOLOGY_SOURCE:
        _fail(
            "methodology.source does not match the locked source"
        )

    if methodology["primary_scopes"] != list(PRIMARY_SCOPES):
        _fail(
            "methodology.primary_scopes must equal "
            "['election', 'campaign']"
        )

    if methodology["general_scope"] != GENERAL_SCOPE:
        _fail("methodology.general_scope must equal general")

    if methodology["metric"] != METHODOLOGY_METRIC:
        _fail("methodology.metric is invalid")

    if (
        methodology["candidate_linkage"]
        != METHODOLOGY_CANDIDATE_LINKAGE
    ):
        _fail("methodology.candidate_linkage is invalid")

    if methodology["not_measures"] != list(NOT_MEASURES):
        _fail("methodology.not_measures is invalid")


def _validate_daily_denominators(
    value: Any,
    *,
    lane_name: str,
    required_dates: list[str],
) -> dict[str, dict[str, Any]]:
    lane = _require_object(
        value,
        f"lanes.{lane_name}",
        keys={"daily_denominators"},
    )

    observations = _require_list(
        lane["daily_denominators"],
        f"lanes.{lane_name}.daily_denominators",
    )

    if len(observations) != EXPECTED_DAYS:
        _fail(
            f"lanes.{lane_name}.daily_denominators must "
            f"contain exactly {EXPECTED_DAYS} observations"
        )

    indexed: dict[str, dict[str, Any]] = {}

    for index, raw in enumerate(observations):
        field = (
            f"lanes.{lane_name}."
            f"daily_denominators[{index}]"
        )

        observation = _require_object(
            raw,
            field,
            keys={
                "date",
                "record_count",
                "publisher_count",
            },
        )

        observed_date = _require_text(
            observation["date"],
            f"{field}.date",
        )

        if observed_date != required_dates[index]:
            _fail(
                f"lanes.{lane_name}.daily_denominators must "
                "contain the exact ascending 29-day sequence "
                "with no gaps or duplicates"
            )

        record_count = _require_non_negative_integer(
            observation["record_count"],
            f"{field}.record_count",
        )

        publisher_count = _require_non_negative_integer(
            observation["publisher_count"],
            f"{field}.publisher_count",
        )

        if publisher_count > record_count:
            _fail(
                f"{field}.publisher_count cannot exceed "
                "record_count"
            )

        indexed[observed_date] = observation

    return indexed


def _validate_candidate_series(
    value: Any,
    *,
    lane_name: str,
    required_dates: list[str],
    denominators: dict[str, dict[str, Any]],
) -> None:
    lane = _require_object(
        value,
        f"candidate.{lane_name}",
        keys={"daily_series"},
    )

    series = _require_list(
        lane["daily_series"],
        f"candidate.{lane_name}.daily_series",
    )

    if len(series) != EXPECTED_DAYS:
        _fail(
            f"candidate.{lane_name}.daily_series must "
            f"contain exactly {EXPECTED_DAYS} observations"
        )

    for index, raw in enumerate(series):
        field = (
            f"candidate.{lane_name}."
            f"daily_series[{index}]"
        )

        observation = _require_object(
            raw,
            field,
            keys={
                "date",
                "record_count",
                "share",
                "publisher_count",
            },
        )

        observed_date = _require_text(
            observation["date"],
            f"{field}.date",
        )

        if observed_date != required_dates[index]:
            _fail(
                f"candidate.{lane_name}.daily_series must "
                "contain the exact ascending 29-day sequence "
                "with no gaps or duplicates"
            )

        record_count = _require_non_negative_integer(
            observation["record_count"],
            f"{field}.record_count",
        )

        publisher_count = _require_non_negative_integer(
            observation["publisher_count"],
            f"{field}.publisher_count",
        )

        denominator = denominators[observed_date]
        denominator_count = denominator["record_count"]
        denominator_publishers = denominator[
            "publisher_count"
        ]

        if record_count > denominator_count:
            _fail(
                f"{field}.record_count cannot exceed "
                "its lane denominator"
            )

        if publisher_count > record_count:
            _fail(
                f"{field}.publisher_count cannot exceed "
                "candidate record_count"
            )

        if publisher_count > denominator_publishers:
            _fail(
                f"{field}.publisher_count cannot exceed "
                "its lane publisher denominator"
            )

        share = observation["share"]

        if denominator_count == 0:
            if (
                record_count != 0
                or publisher_count != 0
            ):
                _fail(
                    f"{field} counts must be zero when "
                    "the lane denominator is zero"
                )

            if share is not None:
                _fail(
                    f"{field}.share must be null when "
                    "the lane denominator is zero"
                )

            continue

        if (
            isinstance(share, bool)
            or not isinstance(share, (int, float))
            or not math.isfinite(float(share))
            or not 0 <= float(share) <= 1
        ):
            _fail(
                f"{field}.share must be a finite ratio "
                "between zero and one"
            )

        expected_share = round_visibility_ratio(
            record_count / denominator_count
        )

        if float(share) != expected_share:
            _fail(
                f"{field}.share is inconsistent; "
                f"expected {expected_share}, got {share}"
            )


def validate_candidate_visibility_history(
    payload: Any,
    *,
    expected_candidates: list[dict[str, Any]] | None = None,
) -> None:
    value = _require_object(
        payload,
        "payload",
        keys={
            "schema_version",
            "period",
            "methodology",
            "lanes",
            "candidates",
        },
    )

    if value["schema_version"] != SCHEMA_VERSION:
        _fail(
            f"payload.schema_version must equal {SCHEMA_VERSION}"
        )

    required_dates = _validate_period(
        value["period"]
    )

    _validate_methodology(
        value["methodology"]
    )

    lanes = _require_object(
        value["lanes"],
        "lanes",
        keys={
            CAMPAIGN_LANE,
            GENERAL_LANE,
        },
    )

    denominators = {
        CAMPAIGN_LANE: _validate_daily_denominators(
            lanes[CAMPAIGN_LANE],
            lane_name=CAMPAIGN_LANE,
            required_dates=required_dates,
        ),
        GENERAL_LANE: _validate_daily_denominators(
            lanes[GENERAL_LANE],
            lane_name=GENERAL_LANE,
            required_dates=required_dates,
        ),
    }

    candidates = _require_list(
        value["candidates"],
        "candidates",
    )

    if not candidates:
        _fail("candidates must be non-empty")

    candidate_ids: set[str] = set()
    candidate_names: set[str] = set()
    identities: list[tuple[str, str]] = []

    for index, raw_candidate in enumerate(candidates):
        field = f"candidates[{index}]"

        candidate = _require_object(
            raw_candidate,
            field,
            keys={
                "candidate_id",
                "candidate_name",
                CAMPAIGN_LANE,
                GENERAL_LANE,
            },
        )

        candidate_id = _require_text(
            candidate["candidate_id"],
            f"{field}.candidate_id",
        )
        candidate_name = _require_text(
            candidate["candidate_name"],
            f"{field}.candidate_name",
        )

        if candidate_id in candidate_ids:
            _fail("candidate IDs must be unique")

        if candidate_name in candidate_names:
            _fail("candidate names must be unique")

        candidate_ids.add(candidate_id)
        candidate_names.add(candidate_name)
        identities.append(
            (candidate_id, candidate_name)
        )

        _validate_candidate_series(
            candidate[CAMPAIGN_LANE],
            lane_name=CAMPAIGN_LANE,
            required_dates=required_dates,
            denominators=denominators[CAMPAIGN_LANE],
        )

        _validate_candidate_series(
            candidate[GENERAL_LANE],
            lane_name=GENERAL_LANE,
            required_dates=required_dates,
            denominators=denominators[GENERAL_LANE],
        )

    expected_order = sorted(
        identities,
        key=lambda item: (
            item[1].casefold(),
            item[0],
        ),
    )

    if identities != expected_order:
        _fail(
            "candidates must be deterministically ordered by "
            "candidate_name.casefold(), then candidate_id"
        )

    if expected_candidates is not None:
        expected_identities: list[
            tuple[str, str]
        ] = []

        for index, candidate in enumerate(
            expected_candidates
        ):
            if not isinstance(candidate, dict):
                _fail(
                    "expected_candidates entries must be objects"
                )

            candidate_id = _require_text(
                candidate.get("candidate_id"),
                (
                    f"expected_candidates[{index}]."
                    "candidate_id"
                ),
            )
            candidate_name = _require_text(
                candidate.get("candidate_name"),
                (
                    f"expected_candidates[{index}]."
                    "candidate_name"
                ),
            )

            expected_identities.append(
                (candidate_id, candidate_name)
            )

        if identities != expected_identities:
            _fail(
                "candidate identities/order do not match "
                "the controlled candidacy universe"
            )


def serialize_candidate_visibility_history(
    payload: dict[str, Any],
    *,
    expected_candidates: list[dict[str, Any]] | None = None,
) -> bytes:
    validate_candidate_visibility_history(
        payload,
        expected_candidates=expected_candidates,
    )

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")