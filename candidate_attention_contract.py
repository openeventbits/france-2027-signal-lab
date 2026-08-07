from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0"
REGISTRY_SCHEMA_VERSION = "1.0"
EXPECTED_CANDIDATE_COUNT = 20
EXPECTED_DAYS = 90

SOURCE_PROJECT = "fr.wikipedia.org"
SOURCE_API = "Wikimedia Analytics API"
SOURCE_METRIC = "pageviews"
SOURCE_ACCESS = "all-access"
SOURCE_AGENT = "user"
SOURCE_GRANULARITY = "daily"

METHODOLOGY_LABEL = "Wikipedia Attention"
METHODOLOGY_INTERPRETATION = (
    "French Wikipedia pageviews measure article-reading attention."
)
METHODOLOGY_NOT_MEASURES = (
    "unique individuals",
    "sentiment",
    "approval",
    "electoral support",
    "voting intention",
)
METHODOLOGY_WEEKLY_COMPARISON = (
    "Latest seven complete UTC days versus the preceding seven complete UTC days."
)
METHODOLOGY_REDIRECT_LIMITATION = (
    "Redirect traffic may not always be fully attributed to the canonical article."
)

ALLOWED_INTERPRETATION_FLAGS = frozenset(
    {
        "sustained_rise",
        "sustained_decline",
        "event_amplified",
        "stable",
        "low_base",
    }
)


class CandidateAttentionContractError(ValueError):
    """Raised when a Candidate Attention artifact violates its contract."""


def _fail(message: str) -> None:
    raise CandidateAttentionContractError(message)


def _require_object(
    value: Any,
    field: str,
    *,
    keys: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{field} must be an object")
    if keys is not None and set(value) != keys:
        _fail(f"{field} has unexpected fields")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{field} must be a list")
    return value


def _require_text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        _fail(f"{field} must be non-empty trimmed text")
    return value


def _require_non_negative_integer(value: Any, field: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        _fail(f"{field} must be a non-negative integer")
    return value


def _require_number_or_none(value: Any, field: str) -> float | int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        _fail(f"{field} must be a finite number or null")
    return value


def _calendar_date(value: Any, field: str) -> date:
    text = _require_text(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise CandidateAttentionContractError(
            f"{field} must be a valid calendar date"
        ) from error


def _utc_timestamp(value: Any, field: str) -> datetime:
    text = _require_text(value, field)
    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise CandidateAttentionContractError(
            f"{field} must be a valid UTC ISO-8601 timestamp"
        ) from error

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
    ):
        _fail(f"{field} must use UTC")
    return parsed


def _valid_article_url(value: Any, field: str) -> str:
    text = _require_text(value, field)
    parsed = urlsplit(text)

    if (
        parsed.scheme != "https"
        or parsed.netloc != SOURCE_PROJECT
        or not parsed.path.startswith("/wiki/")
        or parsed.query
        or parsed.fragment
    ):
        _fail(f"{field} must be a canonical French Wikipedia article URL")

    return text


def _expected_dates(start_date: date, days: int) -> list[str]:
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(days)
    ]


def _percentage_change(
    current: int,
    previous: int,
) -> float | None:
    if previous == 0:
        return None
    return round(
        ((current - previous) / previous) * 100.0,
        1,
    )


def _same_number(
    actual: Any,
    expected: float | int | None,
    field: str,
) -> None:
    _require_number_or_none(actual, field)

    if expected is None:
        if actual is not None:
            _fail(f"{field} must be null when its denominator is zero")
        return

    if actual is None:
        _fail(f"{field} must not be null")

    if abs(float(actual) - float(expected)) > 1e-9:
        _fail(
            f"{field} is inconsistent: expected {expected}, got {actual}"
        )


def _window_peak(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    # The series is ascending. max() returns the first matching item,
    # therefore ties resolve to the earliest date deterministically.
    return max(
        observations,
        key=lambda observation: observation["views"],
    )


def validate_wikimedia_candidate_articles(
    payload: Any,
    *,
    expected_candidates: list[dict[str, Any]] | None = None,
) -> None:
    value = _require_object(
        payload,
        "registry",
        keys={
            "schema_version",
            "project",
            "reviewed_at",
            "candidate_count",
            "candidates",
        },
    )

    if value["schema_version"] != REGISTRY_SCHEMA_VERSION:
        _fail(
            "registry.schema_version must equal "
            f"{REGISTRY_SCHEMA_VERSION}"
        )

    if value["project"] != SOURCE_PROJECT:
        _fail("registry.project must equal fr.wikipedia.org")

    _calendar_date(value["reviewed_at"], "registry.reviewed_at")

    count = _require_non_negative_integer(
        value["candidate_count"],
        "registry.candidate_count",
    )
    if count != EXPECTED_CANDIDATE_COUNT:
        _fail(
            "registry.candidate_count must equal "
            f"{EXPECTED_CANDIDATE_COUNT}"
        )

    records = _require_list(
        value["candidates"],
        "registry.candidates",
    )
    if len(records) != EXPECTED_CANDIDATE_COUNT:
        _fail(
            "registry.candidates must contain exactly "
            f"{EXPECTED_CANDIDATE_COUNT} records"
        )

    seen_ids: set[str] = set()

    for index, raw_record in enumerate(records):
        field = f"registry.candidates[{index}]"
        record = _require_object(
            raw_record,
            field,
            keys={
                "candidate_id",
                "candidate_name",
                "requested_article",
                "canonical_article",
                "article_url",
                "project",
            },
        )

        candidate_id = _require_text(
            record["candidate_id"],
            f"{field}.candidate_id",
        )
        _require_text(
            record["candidate_name"],
            f"{field}.candidate_name",
        )
        _require_text(
            record["requested_article"],
            f"{field}.requested_article",
        )
        _require_text(
            record["canonical_article"],
            f"{field}.canonical_article",
        )
        _valid_article_url(
            record["article_url"],
            f"{field}.article_url",
        )

        if record["project"] != SOURCE_PROJECT:
            _fail(f"{field}.project must equal fr.wikipedia.org")

        if candidate_id in seen_ids:
            _fail("registry candidate IDs must be unique")
        seen_ids.add(candidate_id)

        if candidate_id == "olivier-faure":
            if (
                record["requested_article"] != "Olivier Faure"
                or record["canonical_article"]
                != "Olivier Faure (homme politique)"
            ):
                _fail(
                    "Olivier Faure disambiguation mapping is invalid"
                )

    if expected_candidates is not None:
        if len(expected_candidates) != EXPECTED_CANDIDATE_COUNT:
            _fail(
                "expected candidate universe must contain exactly "
                f"{EXPECTED_CANDIDATE_COUNT} candidates"
            )

        expected_order = [
            (
                candidate["candidate_id"],
                candidate["candidate_name"],
            )
            for candidate in expected_candidates
        ]

        actual_order = [
            (
                candidate["candidate_id"],
                candidate["candidate_name"],
            )
            for candidate in records
        ]

        if actual_order != expected_order:
            _fail(
                "registry candidate IDs/names/order do not match "
                "the controlled candidacy universe"
            )


def validate_candidate_attention(
    payload: Any,
    *,
    expected_candidates: list[dict[str, Any]] | None = None,
) -> None:
    value = _require_object(
        payload,
        "payload",
        keys={
            "schema_version",
            "generated_at",
            "source",
            "period",
            "candidate_universe",
            "methodology",
            "validation",
            "candidates",
        },
    )

    if value["schema_version"] != SCHEMA_VERSION:
        _fail(
            f"payload.schema_version must equal {SCHEMA_VERSION}"
        )

    _utc_timestamp(
        value["generated_at"],
        "payload.generated_at",
    )

    source = _require_object(
        value["source"],
        "payload.source",
        keys={
            "project",
            "api",
            "metric",
            "access",
            "agent",
            "granularity",
        },
    )

    expected_source = {
        "project": SOURCE_PROJECT,
        "api": SOURCE_API,
        "metric": SOURCE_METRIC,
        "access": SOURCE_ACCESS,
        "agent": SOURCE_AGENT,
        "granularity": SOURCE_GRANULARITY,
    }

    if source != expected_source:
        _fail("payload.source does not match the locked source contract")

    period = _require_object(
        value["period"],
        "payload.period",
        keys={
            "start_date",
            "end_date",
            "days",
            "data_as_of",
        },
    )

    start_date = _calendar_date(
        period["start_date"],
        "payload.period.start_date",
    )
    end_date = _calendar_date(
        period["end_date"],
        "payload.period.end_date",
    )

    if period["days"] != EXPECTED_DAYS:
        _fail(
            f"payload.period.days must equal {EXPECTED_DAYS}"
        )

    if end_date != start_date + timedelta(days=EXPECTED_DAYS - 1):
        _fail("payload.period must span exactly 90 complete UTC days")

    data_as_of = _calendar_date(
        period["data_as_of"],
        "payload.period.data_as_of",
    )
    if data_as_of != end_date:
        _fail(
            "payload.period.data_as_of must equal the final "
            "complete observation date"
        )

    universe = _require_object(
        value["candidate_universe"],
        "payload.candidate_universe",
        keys={
            "source",
            "status_as_of",
            "count",
        },
    )

    if universe["source"] != "candidate_candidacy_status.json":
        _fail(
            "payload.candidate_universe.source must equal "
            "candidate_candidacy_status.json"
        )

    _calendar_date(
        universe["status_as_of"],
        "payload.candidate_universe.status_as_of",
    )

    if universe["count"] != EXPECTED_CANDIDATE_COUNT:
        _fail(
            "payload.candidate_universe.count must equal "
            f"{EXPECTED_CANDIDATE_COUNT}"
        )

    methodology = _require_object(
        value["methodology"],
        "payload.methodology",
        keys={
            "label",
            "interpretation",
            "not_measures",
            "weekly_comparison",
            "redirect_limitation",
        },
    )

    if methodology["label"] != METHODOLOGY_LABEL:
        _fail("payload.methodology.label is invalid")

    if methodology["interpretation"] != METHODOLOGY_INTERPRETATION:
        _fail("payload.methodology.interpretation is invalid")

    if methodology["not_measures"] != list(METHODOLOGY_NOT_MEASURES):
        _fail("payload.methodology.not_measures is invalid")

    if (
        methodology["weekly_comparison"]
        != METHODOLOGY_WEEKLY_COMPARISON
    ):
        _fail("payload.methodology.weekly_comparison is invalid")

    if (
        methodology["redirect_limitation"]
        != METHODOLOGY_REDIRECT_LIMITATION
    ):
        _fail("payload.methodology.redirect_limitation is invalid")

    validation = _require_object(
        value["validation"],
        "payload.validation",
        keys={
            "status",
            "candidate_count",
            "expected_days_per_candidate",
            "missing_dates",
            "duplicate_dates",
        },
    )

    if validation["status"] != "pass":
        _fail("payload.validation.status must equal pass")

    for field, expected in (
        ("candidate_count", EXPECTED_CANDIDATE_COUNT),
        ("expected_days_per_candidate", EXPECTED_DAYS),
        ("missing_dates", 0),
        ("duplicate_dates", 0),
    ):
        actual = _require_non_negative_integer(
            validation[field],
            f"payload.validation.{field}",
        )
        if actual != expected:
            _fail(
                f"payload.validation.{field} must equal {expected}"
            )

    candidates = _require_list(
        value["candidates"],
        "payload.candidates",
    )

    if len(candidates) != EXPECTED_CANDIDATE_COUNT:
        _fail(
            "payload.candidates must contain exactly "
            f"{EXPECTED_CANDIDATE_COUNT} records"
        )

    expected_date_sequence = _expected_dates(
        start_date,
        EXPECTED_DAYS,
    )

    seen_ids: set[str] = set()
    actual_identity_order: list[tuple[str, str]] = []

    for index, raw_candidate in enumerate(candidates):
        field = f"payload.candidates[{index}]"

        candidate = _require_object(
            raw_candidate,
            field,
            keys={
                "candidate_id",
                "candidate_name",
                "canonical_article",
                "article_url",
                "latest_7_views",
                "previous_7_views",
                "change_7_pct",
                "latest_28_views",
                "previous_28_views",
                "change_28_pct",
                "latest_7_peak_date",
                "latest_7_peak_views",
                "latest_7_peak_share",
                "change_7_peak_removed_pct",
                "period_peak_date",
                "period_peak_views",
                "interpretation_flag",
                "daily_series",
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

        if candidate_id in seen_ids:
            _fail("payload candidate IDs must be unique")
        seen_ids.add(candidate_id)
        actual_identity_order.append(
            (candidate_id, candidate_name)
        )

        _require_text(
            candidate["canonical_article"],
            f"{field}.canonical_article",
        )
        _valid_article_url(
            candidate["article_url"],
            f"{field}.article_url",
        )

        if candidate["interpretation_flag"] not in ALLOWED_INTERPRETATION_FLAGS:
            _fail(
                f"{field}.interpretation_flag is not an allowed value"
            )

        daily_series = _require_list(
            candidate["daily_series"],
            f"{field}.daily_series",
        )

        if len(daily_series) != EXPECTED_DAYS:
            _fail(
                f"{field}.daily_series must contain exactly "
                f"{EXPECTED_DAYS} observations"
            )

        actual_dates: list[str] = []

        for day_index, raw_day in enumerate(daily_series):
            day_field = (
                f"{field}.daily_series[{day_index}]"
            )
            day = _require_object(
                raw_day,
                day_field,
                keys={"date", "views"},
            )
            observed_date = _calendar_date(
                day["date"],
                f"{day_field}.date",
            ).isoformat()
            _require_non_negative_integer(
                day["views"],
                f"{day_field}.views",
            )
            actual_dates.append(observed_date)

        if actual_dates != expected_date_sequence:
            _fail(
                f"{field}.daily_series must contain the exact "
                "ascending 90-day date sequence with no gaps "
                "or duplicates"
            )

        latest_7 = daily_series[-7:]
        previous_7 = daily_series[-14:-7]
        latest_28 = daily_series[-28:]
        previous_28 = daily_series[-56:-28]

        latest_7_views = sum(day["views"] for day in latest_7)
        previous_7_views = sum(day["views"] for day in previous_7)
        latest_28_views = sum(day["views"] for day in latest_28)
        previous_28_views = sum(day["views"] for day in previous_28)

        for metric_field, expected_value in (
            ("latest_7_views", latest_7_views),
            ("previous_7_views", previous_7_views),
            ("latest_28_views", latest_28_views),
            ("previous_28_views", previous_28_views),
        ):
            actual = _require_non_negative_integer(
                candidate[metric_field],
                f"{field}.{metric_field}",
            )
            if actual != expected_value:
                _fail(
                    f"{field}.{metric_field} is inconsistent "
                    "with daily_series"
                )

        _same_number(
            candidate["change_7_pct"],
            _percentage_change(
                latest_7_views,
                previous_7_views,
            ),
            f"{field}.change_7_pct",
        )

        _same_number(
            candidate["change_28_pct"],
            _percentage_change(
                latest_28_views,
                previous_28_views,
            ),
            f"{field}.change_28_pct",
        )

        latest_7_peak = _window_peak(latest_7)

        if (
            candidate["latest_7_peak_date"]
            != latest_7_peak["date"]
        ):
            _fail(
                f"{field}.latest_7_peak_date is inconsistent "
                "with daily_series"
            )

        if (
            candidate["latest_7_peak_views"]
            != latest_7_peak["views"]
        ):
            _fail(
                f"{field}.latest_7_peak_views is inconsistent "
                "with daily_series"
            )

        expected_peak_share = (
            None
            if latest_7_views == 0
            else round(
                latest_7_peak["views"] / latest_7_views,
                4,
            )
        )

        _same_number(
            candidate["latest_7_peak_share"],
            expected_peak_share,
            f"{field}.latest_7_peak_share",
        )

        previous_7_peak = _window_peak(previous_7)

        current_without_peak = (
            latest_7_views
            - latest_7_peak["views"]
        )
        previous_without_peak = (
            previous_7_views
            - previous_7_peak["views"]
        )

        _same_number(
            candidate["change_7_peak_removed_pct"],
            _percentage_change(
                current_without_peak,
                previous_without_peak,
            ),
            f"{field}.change_7_peak_removed_pct",
        )

        period_peak = _window_peak(daily_series)

        if candidate["period_peak_date"] != period_peak["date"]:
            _fail(
                f"{field}.period_peak_date is inconsistent "
                "with daily_series"
            )

        if candidate["period_peak_views"] != period_peak["views"]:
            _fail(
                f"{field}.period_peak_views is inconsistent "
                "with daily_series"
            )

    if expected_candidates is not None:
        if len(expected_candidates) != EXPECTED_CANDIDATE_COUNT:
            _fail(
                "expected candidate universe must contain exactly "
                f"{EXPECTED_CANDIDATE_COUNT} candidates"
            )

        expected_identity_order = [
            (
                candidate["candidate_id"],
                candidate["candidate_name"],
            )
            for candidate in expected_candidates
        ]

        if actual_identity_order != expected_identity_order:
            _fail(
                "payload candidate IDs/names/order do not match "
                "the controlled candidacy universe"
            )


def serialize_candidate_attention(
    payload: Any,
    *,
    expected_candidates: list[dict[str, Any]] | None = None,
) -> bytes:
    validate_candidate_attention(
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