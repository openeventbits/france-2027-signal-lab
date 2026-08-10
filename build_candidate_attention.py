from __future__ import annotations

import argparse
import json
import math
import os
import socket
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from candidate_candidacy_status import load_candidate_candidacy_status

from candidate_attention_contract import (
    EXPECTED_CANDIDATE_COUNT,
    EXPECTED_DAYS,
    METHODOLOGY_INTERPRETATION,
    METHODOLOGY_LABEL,
    METHODOLOGY_NOT_MEASURES,
    METHODOLOGY_REDIRECT_LIMITATION,
    METHODOLOGY_WEEKLY_COMPARISON,
    SCHEMA_VERSION,
    SOURCE_ACCESS,
    SOURCE_AGENT,
    SOURCE_API,
    SOURCE_GRANULARITY,
    SOURCE_METRIC,
    SOURCE_PROJECT,
    serialize_candidate_attention,
    validate_wikimedia_candidate_articles,
)


LOW_BASE_7D_VIEWS = 3000

SUSTAINED_CHANGE_MIN_PCT = 5.0

EVENT_AMPLIFIED_RAW_MIN_PCT = 10.0
EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT = 15.0
EVENT_AMPLIFIED_RETAINED_RATIO_MAX = 0.40
EVENT_AMPLIFIED_PEAK_SHARE_MIN = 0.35


class CandidateAttentionBuildError(ValueError):
    """Raised when Candidate Attention cannot be built safely."""


def _fail(message: str) -> None:
    raise CandidateAttentionBuildError(message)


def parse_calendar_date(value: str, field: str) -> date:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{field} must be non-empty trimmed text")

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CandidateAttentionBuildError(
            f"{field} must be a valid calendar date"
        ) from error


def normalize_generated_at(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail("generated_at must be non-empty trimmed text")

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise CandidateAttentionBuildError(
            "generated_at must be a valid UTC ISO-8601 timestamp"
        ) from error

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
    ):
        _fail("generated_at must use UTC")

    return (
        parsed.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def percentage_change(
    current: int,
    previous: int,
) -> float | None:
    if previous == 0:
        return None

    return round(
        ((current - previous) / previous) * 100.0,
        1,
    )


def expected_dates(
    data_as_of: date,
) -> list[str]:
    start = data_as_of - timedelta(days=EXPECTED_DAYS - 1)

    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(EXPECTED_DAYS)
    ]


def validate_daily_series(
    daily_series: Any,
    *,
    data_as_of: date,
) -> list[dict[str, Any]]:
    if not isinstance(daily_series, list):
        _fail("daily_series must be a list")

    if len(daily_series) != EXPECTED_DAYS:
        _fail(
            f"daily_series must contain exactly {EXPECTED_DAYS} observations"
        )

    required_dates = expected_dates(data_as_of)
    validated: list[dict[str, Any]] = []

    for index, raw_observation in enumerate(daily_series):
        field = f"daily_series[{index}]"

        if (
            not isinstance(raw_observation, dict)
            or set(raw_observation) != {"date", "views"}
        ):
            _fail(f"{field} has unexpected fields")

        observed_date = raw_observation["date"]

        if (
            not isinstance(observed_date, str)
            or observed_date != required_dates[index]
        ):
            _fail(
                "daily_series must contain the exact ascending "
                "90-day date sequence with no gaps or duplicates"
            )

        views = raw_observation["views"]

        if (
            not isinstance(views, int)
            or isinstance(views, bool)
            or views < 0
        ):
            _fail(f"{field}.views must be a non-negative integer")

        validated.append(
            {
                "date": observed_date,
                "views": views,
            }
        )

    return validated


def window_peak(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    if not observations:
        _fail("cannot calculate a peak from an empty window")

    # Observations are ascending. Python max() returns the first item
    # that reaches the maximum, so equal peaks resolve to the earliest
    # date deterministically.
    return max(
        observations,
        key=lambda observation: observation["views"],
    )


def calculate_candidate_metrics(
    daily_series: list[dict[str, Any]],
    *,
    data_as_of: date,
) -> dict[str, Any]:
    series = validate_daily_series(
        daily_series,
        data_as_of=data_as_of,
    )

    latest_7 = series[-7:]
    previous_7 = series[-14:-7]

    latest_28 = series[-28:]
    previous_28 = series[-56:-28]

    latest_7_views = sum(
        observation["views"]
        for observation in latest_7
    )
    previous_7_views = sum(
        observation["views"]
        for observation in previous_7
    )

    latest_28_views = sum(
        observation["views"]
        for observation in latest_28
    )
    previous_28_views = sum(
        observation["views"]
        for observation in previous_28
    )

    latest_7_peak = window_peak(latest_7)
    previous_7_peak = window_peak(previous_7)
    period_peak = window_peak(series)

    latest_without_peak = (
        latest_7_views
        - latest_7_peak["views"]
    )
    previous_without_peak = (
        previous_7_views
        - previous_7_peak["views"]
    )

    latest_7_peak_share = (
        None
        if latest_7_views == 0
        else round(
            latest_7_peak["views"]
            / latest_7_views,
            4,
        )
    )

    return {
        "latest_7_views": latest_7_views,
        "previous_7_views": previous_7_views,
        "change_7_pct": percentage_change(
            latest_7_views,
            previous_7_views,
        ),
        "latest_28_views": latest_28_views,
        "previous_28_views": previous_28_views,
        "change_28_pct": percentage_change(
            latest_28_views,
            previous_28_views,
        ),
        "latest_7_peak_date": latest_7_peak["date"],
        "latest_7_peak_views": latest_7_peak["views"],
        "latest_7_peak_share": latest_7_peak_share,
        "change_7_peak_removed_pct": percentage_change(
            latest_without_peak,
            previous_without_peak,
        ),
        "period_peak_date": period_peak["date"],
        "period_peak_views": period_peak["views"],
    }


def interpretation_flag(
    metrics: dict[str, Any],
) -> str:
    latest_7_views = metrics["latest_7_views"]
    raw_change = metrics["change_7_pct"]
    peak_removed_change = metrics[
        "change_7_peak_removed_pct"
    ]
    peak_share = metrics["latest_7_peak_share"]

    if latest_7_views < LOW_BASE_7D_VIEWS:
        return "low_base"

    if raw_change is None or peak_removed_change is None:
        return "stable"

    raw_abs = abs(raw_change)
    adjusted_abs = abs(peak_removed_change)

    opposite_or_removed = (
        raw_change != 0
        and (
            peak_removed_change == 0
            or (
                raw_change > 0
                and peak_removed_change < 0
            )
            or (
                raw_change < 0
                and peak_removed_change > 0
            )
        )
    )

    difference = abs(
        raw_change - peak_removed_change
    )

    retained_ratio = (
        adjusted_abs / raw_abs
        if raw_abs > 0
        else 1.0
    )

    event_amplified = (
        raw_abs >= EVENT_AMPLIFIED_RAW_MIN_PCT
        and (
            opposite_or_removed
            or (
                difference
                >= EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT
                and retained_ratio
                <= EVENT_AMPLIFIED_RETAINED_RATIO_MAX
            )
            or (
                peak_share is not None
                and peak_share
                >= EVENT_AMPLIFIED_PEAK_SHARE_MIN
                and adjusted_abs
                < SUSTAINED_CHANGE_MIN_PCT
            )
        )
    )

    if event_amplified:
        return "event_amplified"

    if (
        raw_change >= SUSTAINED_CHANGE_MIN_PCT
        and peak_removed_change
        >= SUSTAINED_CHANGE_MIN_PCT
    ):
        return "sustained_rise"

    if (
        raw_change <= -SUSTAINED_CHANGE_MIN_PCT
        and peak_removed_change
        <= -SUSTAINED_CHANGE_MIN_PCT
    ):
        return "sustained_decline"

    return "stable"


def build_candidate_record(
    candidate: dict[str, Any],
    mapping: dict[str, Any],
    daily_series: list[dict[str, Any]],
    *,
    data_as_of: date,
) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]

    if mapping["candidate_id"] != candidate_id:
        _fail(
            f"Wikimedia mapping ID mismatch for {candidate_id}"
        )

    if mapping["candidate_name"] != candidate["candidate_name"]:
        _fail(
            f"Wikimedia mapping name mismatch for {candidate_id}"
        )

    series = validate_daily_series(
        daily_series,
        data_as_of=data_as_of,
    )

    metrics = calculate_candidate_metrics(
        series,
        data_as_of=data_as_of,
    )

    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate["candidate_name"],
        "canonical_article": mapping["canonical_article"],
        "article_url": mapping["article_url"],
        **metrics,
        "interpretation_flag": interpretation_flag(metrics),
        "daily_series": series,
    }


def build_candidate_attention_payload(
    *,
    candidacy_payload: dict[str, Any],
    registry_payload: dict[str, Any],
    observations_by_candidate: dict[
        str,
        list[dict[str, Any]]
    ],
    generated_at: str,
    data_as_of: str,
) -> dict[str, Any]:
    if not isinstance(candidacy_payload, dict):
        _fail("candidacy_payload must be an object")

    controlled_candidates = candidacy_payload.get(
        "candidates"
    )

    if (
        not isinstance(controlled_candidates, list)
        or len(controlled_candidates)
        != EXPECTED_CANDIDATE_COUNT
    ):
        _fail(
            "controlled candidacy universe must contain "
            f"exactly {EXPECTED_CANDIDATE_COUNT} candidates"
        )

    status_as_of = candidacy_payload.get(
        "status_as_of"
    )

    if not isinstance(status_as_of, str):
        _fail(
            "candidate candidacy status_as_of is missing"
        )

    parse_calendar_date(
        status_as_of,
        "candidate_candidacy_status.status_as_of",
    )

    validate_wikimedia_candidate_articles(
        registry_payload,
        expected_candidates=controlled_candidates,
    )

    registry_by_id = {
        record["candidate_id"]: record
        for record in registry_payload["candidates"]
    }

    candidate_ids = [
        candidate["candidate_id"]
        for candidate in controlled_candidates
    ]

    if set(observations_by_candidate) != set(candidate_ids):
        missing = sorted(
            set(candidate_ids)
            - set(observations_by_candidate)
        )
        extra = sorted(
            set(observations_by_candidate)
            - set(candidate_ids)
        )

        _fail(
            "observation universe does not match controlled "
            f"candidate universe; missing={missing}; extra={extra}"
        )

    end_date = parse_calendar_date(
        data_as_of,
        "data_as_of",
    )
    start_date = (
        end_date
        - timedelta(days=EXPECTED_DAYS - 1)
    )

    normalized_generated_at = normalize_generated_at(
        generated_at
    )

    records = [
        build_candidate_record(
            candidate,
            registry_by_id[candidate["candidate_id"]],
            observations_by_candidate[
                candidate["candidate_id"]
            ],
            data_as_of=end_date,
        )
        for candidate in controlled_candidates
    ]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": normalized_generated_at,
        "source": {
            "project": SOURCE_PROJECT,
            "api": SOURCE_API,
            "metric": SOURCE_METRIC,
            "access": SOURCE_ACCESS,
            "agent": SOURCE_AGENT,
            "granularity": SOURCE_GRANULARITY,
        },
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": EXPECTED_DAYS,
            "data_as_of": end_date.isoformat(),
        },
        "candidate_universe": {
            "source": "candidate_candidacy_status.json",
            "status_as_of": status_as_of,
            "count": EXPECTED_CANDIDATE_COUNT,
        },
        "methodology": {
            "label": METHODOLOGY_LABEL,
            "interpretation": METHODOLOGY_INTERPRETATION,
            "not_measures": list(
                METHODOLOGY_NOT_MEASURES
            ),
            "weekly_comparison": (
                METHODOLOGY_WEEKLY_COMPARISON
            ),
            "redirect_limitation": (
                METHODOLOGY_REDIRECT_LIMITATION
            ),
        },
        "validation": {
            "status": "pass",
            "candidate_count": EXPECTED_CANDIDATE_COUNT,
            "expected_days_per_candidate": EXPECTED_DAYS,
            "missing_dates": 0,
            "duplicate_dates": 0,
        },
        "candidates": records,
    }

    # The serializer also performs complete contract validation.
    serialize_candidate_attention(
        payload,
        expected_candidates=controlled_candidates,
    )

    return payload


def serialize_semantic_payload(
    payload: dict[str, Any],
) -> bytes:
    semantic = json.loads(
        json.dumps(
            payload,
            ensure_ascii=False,
        )
    )
    semantic["generated_at"] = (
        "<execution-time>"
    )

    return (
        json.dumps(
            semantic,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def atomic_write_bytes(
    path: Path | str,
    content: bytes,
) -> None:
    target = Path(path)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )

    temporary_path = Path(
        temporary_name
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            target,
        )

    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise

WIKIMEDIA_USER_AGENT = (
    "France2027SignalLab/0.3 "
    "(https://github.com/openeventbits/france-2027-signal-lab)"
)

WIKIMEDIA_TITLE_API = "https://fr.wikipedia.org/w/api.php"

WIKIMEDIA_PAGEVIEWS_BASE = (
    "https://wikimedia.org/api/rest_v1/"
    "metrics/pageviews/per-article"
)

DEFAULT_HTTP_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DEFAULT_REQUEST_DELAY_SECONDS = 0.30
PAGEVIEWS_404_RETRY_DELAYS = (1.0, 2.0)

MAX_HTTP_ATTEMPTS = 4
MAX_RETRY_AFTER_SECONDS = 30.0

RETRYABLE_HTTP_STATUSES = frozenset(
    {
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    }
)


class WikimediaFetchError(CandidateAttentionBuildError):
    """Bounded Wikimedia request failure."""

    def __init__(
        self,
        category: str,
        message: str,
        *,
        status: int | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(
            f"{category}: {message}"
        )
        self.category = category
        self.status = status
        self.attempts = attempts


class WikimediaPageviewsNotFoundError(WikimediaFetchError):
    """A Pageviews request returned HTTP 404."""


def _http_failure_category(
    status: int,
) -> str:
    if status == 429:
        return "rate_limited"

    if 400 <= status <= 499:
        return "http_4xx"

    if 500 <= status <= 599:
        return "http_5xx"

    return "invalid_response"


def _close_response(
    response: Any,
) -> None:
    close = getattr(
        response,
        "close",
        None,
    )

    if callable(close):
        try:
            close()
        except Exception:
            pass


def _retry_after_seconds(
    headers: Any,
    *,
    now: Callable[[], datetime],
) -> float | None:
    if headers is None:
        return None

    try:
        raw = headers.get(
            "Retry-After"
        )
    except (
        AttributeError,
        TypeError,
    ):
        return None

    if (
        not isinstance(raw, str)
        or not raw.strip()
    ):
        return None

    value = raw.strip()

    if (
        value.isascii()
        and value.isdecimal()
    ):
        return min(
            float(value),
            MAX_RETRY_AFTER_SECONDS,
        )

    try:
        retry_at = (
            parsedate_to_datetime(
                value
            )
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return None

    if retry_at.tzinfo is None:
        retry_at = (
            retry_at.replace(
                tzinfo=timezone.utc
            )
        )

    current = now()

    if current.tzinfo is None:
        current = current.replace(
            tzinfo=timezone.utc
        )

    delay = (
        retry_at.astimezone(
            timezone.utc
        )
        - current.astimezone(
            timezone.utc
        )
    ).total_seconds()

    return min(
        max(
            0.0,
            delay,
        ),
        MAX_RETRY_AFTER_SECONDS,
    )


def _retry_delay(
    attempt: int,
) -> float:
    return min(
        0.5
        * (
            2
            ** (
                attempt - 1
            )
        ),
        MAX_RETRY_AFTER_SECONDS,
    )


def fetch_json(
    url: str,
    *,
    timeout: int | float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    max_attempts: int = MAX_HTTP_ATTEMPTS,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = (
        lambda: datetime.now(
            timezone.utc
        )
    ),
) -> dict[str, Any]:
    if (
        not isinstance(url, str)
        or not url.startswith(
            "https://"
        )
    ):
        _fail(
            "Wikimedia request URL must use HTTPS"
        )

    if (
        not isinstance(
            max_attempts,
            int,
        )
        or isinstance(
            max_attempts,
            bool,
        )
        or max_attempts < 1
    ):
        _fail(
            "max_attempts must be a positive integer"
        )

    if (
        not isinstance(
            max_response_bytes,
            int,
        )
        or isinstance(
            max_response_bytes,
            bool,
        )
        or max_response_bytes < 1
    ):
        _fail(
            "max_response_bytes must be a positive integer"
        )

    request_headers = {
        "Accept": "application/json",
        "User-Agent": WIKIMEDIA_USER_AGENT,
    }

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        request = Request(
            url,
            headers=request_headers,
        )

        response = None

        try:
            response = opener(
                request,
                timeout=timeout,
            )

        except HTTPError as error:
            status = int(
                error.code
            )

            retry_after = (
                _retry_after_seconds(
                    error.headers,
                    now=now,
                )
            )

            _close_response(
                error
            )

            if (
                status
                in RETRYABLE_HTTP_STATUSES
                and attempt
                < max_attempts
            ):
                sleeper(
                    retry_after
                    if retry_after
                    is not None
                    else _retry_delay(
                        attempt
                    )
                )
                continue

            raise WikimediaFetchError(
                _http_failure_category(
                    status
                ),
                f"HTTP {status}",
                status=status,
                attempts=attempt,
            ) from error

        except (
            TimeoutError,
            socket.timeout,
        ) as error:
            if attempt < max_attempts:
                sleeper(
                    _retry_delay(
                        attempt
                    )
                )
                continue

            raise WikimediaFetchError(
                "timeout",
                str(error)
                or "request timed out",
                attempts=attempt,
            ) from error

        except URLError as error:
            category = (
                "timeout"
                if isinstance(
                    error.reason,
                    (
                        TimeoutError,
                        socket.timeout,
                    ),
                )
                else "network_error"
            )

            if attempt < max_attempts:
                sleeper(
                    _retry_delay(
                        attempt
                    )
                )
                continue

            raise WikimediaFetchError(
                category,
                str(
                    error.reason
                ),
                attempts=attempt,
            ) from error

        except OSError as error:
            if attempt < max_attempts:
                sleeper(
                    _retry_delay(
                        attempt
                    )
                )
                continue

            raise WikimediaFetchError(
                "network_error",
                str(error),
                attempts=attempt,
            ) from error

        try:
            status = getattr(
                response,
                "status",
                None,
            )

            if status is None:
                try:
                    status = (
                        response.getcode()
                    )
                except (
                    AttributeError,
                    TypeError,
                ):
                    status = None

            if status != 200:
                if (
                    isinstance(
                        status,
                        int,
                    )
                    and status
                    in RETRYABLE_HTTP_STATUSES
                    and attempt
                    < max_attempts
                ):
                    retry_after = (
                        _retry_after_seconds(
                            getattr(
                                response,
                                "headers",
                                None,
                            ),
                            now=now,
                        )
                    )

                    _close_response(
                        response
                    )
                    response = None

                    sleeper(
                        retry_after
                        if retry_after
                        is not None
                        else _retry_delay(
                            attempt
                        )
                    )
                    continue

                category = (
                    _http_failure_category(
                        status
                    )
                    if isinstance(
                        status,
                        int,
                    )
                    else "invalid_response"
                )

                raise WikimediaFetchError(
                    category,
                    (
                        f"HTTP {status}"
                        if status
                        is not None
                        else (
                            "response has no "
                            "valid HTTP status"
                        )
                    ),
                    status=(
                        status
                        if isinstance(
                            status,
                            int,
                        )
                        else None
                    ),
                    attempts=attempt,
                )

            headers_object = getattr(
                response,
                "headers",
                None,
            )

            content_length = None

            if (
                headers_object
                is not None
            ):
                try:
                    content_length = (
                        headers_object.get(
                            "Content-Length"
                        )
                    )
                except (
                    AttributeError,
                    TypeError,
                ):
                    content_length = None

            if (
                isinstance(
                    content_length,
                    str,
                )
                and content_length.isascii()
                and content_length.isdecimal()
                and int(
                    content_length
                )
                > max_response_bytes
            ):
                raise WikimediaFetchError(
                    "response_too_large",
                    (
                        "Content-Length exceeds "
                        f"{max_response_bytes} bytes"
                    ),
                    status=200,
                    attempts=attempt,
                )

            body = response.read(
                max_response_bytes
                + 1
            )

            if not isinstance(
                body,
                bytes,
            ):
                raise WikimediaFetchError(
                    "invalid_response",
                    (
                        "response read did "
                        "not return bytes"
                    ),
                    status=200,
                    attempts=attempt,
                )

            if (
                len(body)
                > max_response_bytes
            ):
                raise WikimediaFetchError(
                    "response_too_large",
                    (
                        "response exceeds "
                        f"{max_response_bytes} bytes"
                    ),
                    status=200,
                    attempts=attempt,
                )

        finally:
            if response is not None:
                _close_response(
                    response
                )

        try:
            payload = json.loads(
                body.decode(
                    "utf-8"
                )
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise WikimediaFetchError(
                "malformed_json",
                (
                    "response is not valid "
                    "UTF-8 JSON"
                ),
                status=200,
                attempts=attempt,
            ) from error

        if not isinstance(
            payload,
            dict,
        ):
            raise WikimediaFetchError(
                "invalid_response",
                (
                    "Wikimedia JSON response "
                    "must be an object"
                ),
                status=200,
                attempts=attempt,
            )

        return payload

    raise AssertionError(
        "bounded Wikimedia fetch loop exhausted unexpectedly"
    )


def resolve_wikipedia_title(
    title: str,
    *,
    fetcher: Callable[
        [str],
        dict[str, Any],
    ] = fetch_json,
) -> str:
    if (
        not isinstance(
            title,
            str,
        )
        or not title
        or title
        != title.strip()
    ):
        _fail(
            "Wikipedia title must be non-empty trimmed text"
        )

    query = urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "titles": title,
        }
    )

    payload = fetcher(
        f"{WIKIMEDIA_TITLE_API}?{query}"
    )

    query_payload = (
        payload.get(
            "query"
        )
    )

    if not isinstance(
        query_payload,
        dict,
    ):
        _fail(
            "Wikimedia title response has no query object"
        )

    pages = query_payload.get(
        "pages"
    )

    if (
        not isinstance(
            pages,
            list,
        )
        or len(pages) != 1
        or not isinstance(
            pages[0],
            dict,
        )
    ):
        _fail(
            "Wikimedia title response must contain exactly one page"
        )

    page = pages[0]

    if "missing" in page:
        _fail(
            "Wikipedia article does not exist: "
            f"{title}"
        )

    resolved = page.get(
        "title"
    )

    if (
        not isinstance(
            resolved,
            str,
        )
        or not resolved.strip()
    ):
        _fail(
            "Wikimedia title response has no canonical page title"
        )

    return resolved.strip()


def verify_article_mapping(
    mapping: dict[str, Any],
    *,
    fetcher: Callable[
        [str],
        dict[str, Any],
    ] = fetch_json,
) -> str:
    requested = mapping[
        "requested_article"
    ]

    canonical = mapping[
        "canonical_article"
    ]

    resolved_canonical = (
        resolve_wikipedia_title(
            canonical,
            fetcher=fetcher,
        )
    )

    if (
        resolved_canonical
        != canonical
    ):
        _fail(
            "controlled canonical title changed unexpectedly: "
            f"{canonical!r} resolved to "
            f"{resolved_canonical!r}"
        )

    # The requested/base title may deliberately differ from
    # the approved canonical title, as with Olivier Faure.
    # Verify that it still exists, but never rewrite the registry.
    if requested != canonical:
        resolve_wikipedia_title(
            requested,
            fetcher=fetcher,
        )

    return canonical


def _pageview_article_segment(
    title: str,
) -> str:
    return quote(
        title.replace(
            " ",
            "_",
        ),
        safe="()_-",
    )


def pageview_request_url(
    canonical_article: str,
    *,
    data_as_of: date,
) -> str:
    start = (
        data_as_of
        - timedelta(
            days=(
                EXPECTED_DAYS
                - 1
            )
        )
    )

    return (
        f"{WIKIMEDIA_PAGEVIEWS_BASE}/"
        f"{SOURCE_PROJECT}/"
        f"{SOURCE_ACCESS}/"
        f"{SOURCE_AGENT}/"
        f"{_pageview_article_segment(canonical_article)}/"
        f"{SOURCE_GRANULARITY}/"
        f"{start.strftime('%Y%m%d')}/"
        f"{data_as_of.strftime('%Y%m%d')}"
    )


def fetch_pageview_series(
    canonical_article: str,
    *,
    data_as_of: date,
    fetcher: Callable[
        [str],
        dict[str, Any],
    ] = fetch_json,
    sleeper: Callable[
        [float],
        None,
    ] = time.sleep,
) -> list[dict[str, Any]]:
    request_url = pageview_request_url(
        canonical_article,
        data_as_of=(
            data_as_of
        ),
    )

    total_attempts = (
        len(
            PAGEVIEWS_404_RETRY_DELAYS
        )
        + 1
    )

    for attempt in range(
        1,
        total_attempts + 1,
    ):
        try:
            payload = fetcher(
                request_url
            )
            break
        except WikimediaFetchError as error:
            if error.status != 404:
                raise

            if attempt == total_attempts:
                raise WikimediaPageviewsNotFoundError(
                    error.category,
                    "Pageviews HTTP 404",
                    status=error.status,
                    attempts=attempt,
                ) from error

            delay = (
                PAGEVIEWS_404_RETRY_DELAYS[
                    attempt - 1
                ]
            )

            print(
                "Pageviews HTTP 404; retrying same request "
                f"({attempt + 1}/{total_attempts}) after "
                f"{delay:g}s.",
                flush=True,
            )

            sleeper(
                delay
            )

    items = payload.get(
        "items"
    )

    if not isinstance(
        items,
        list,
    ):
        _fail(
            "Wikimedia pageview response has no items list"
        )

    records: dict[
        str,
        int,
    ] = {}

    for index, item in enumerate(
        items
    ):
        field = (
            f"Wikimedia items[{index}]"
        )

        if not isinstance(
            item,
            dict,
        ):
            _fail(
                f"{field} must be an object"
            )

        timestamp = item.get(
            "timestamp"
        )

        views = item.get(
            "views"
        )

        if (
            not isinstance(
                timestamp,
                str,
            )
            or len(
                timestamp
            ) != 10
            or not timestamp.endswith(
                "00"
            )
        ):
            _fail(
                f"{field}.timestamp is invalid"
            )

        try:
            observation_date = (
                datetime.strptime(
                    timestamp,
                    "%Y%m%d00",
                )
                .date()
                .isoformat()
            )
        except ValueError as error:
            raise CandidateAttentionBuildError(
                f"{field}.timestamp is invalid"
            ) from error

        if (
            not isinstance(
                views,
                int,
            )
            or isinstance(
                views,
                bool,
            )
            or views < 0
        ):
            _fail(
                f"{field}.views must be a non-negative integer"
            )

        if (
            observation_date
            in records
        ):
            _fail(
                "Wikimedia returned duplicate daily pageview dates"
            )

        records[
            observation_date
        ] = views

    required_dates = (
        expected_dates(
            data_as_of
        )
    )

    required_set = set(
        required_dates
    )

    missing = [
        observed_date
        for observed_date
        in required_dates
        if observed_date
        not in records
    ]

    extras = sorted(
        set(records)
        - required_set
    )

    if missing or extras:
        _fail(
            "Wikimedia daily pageview sequence is incomplete; "
            f"missing={missing}; extra={extras}"
        )

    return [
        {
            "date": observed_date,
            "views": records[
                observed_date
            ],
        }
        for observed_date
        in required_dates
    ]


def collect_wikimedia_observations(
    *,
    candidacy_payload: dict[str, Any],
    registry_payload: dict[str, Any],
    data_as_of: date,
    fetcher: Callable[
        [str],
        dict[str, Any],
    ] = fetch_json,
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
    sleeper: Callable[
        [float],
        None,
    ] = time.sleep,
) -> dict[
    str,
    list[dict[str, Any]],
]:
    if (
        not isinstance(
            delay_seconds,
            (int, float),
        )
        or isinstance(
            delay_seconds,
            bool,
        )
        or not math.isfinite(
            float(
                delay_seconds
            )
        )
        or delay_seconds < 0
    ):
        _fail(
            "delay_seconds must be a finite non-negative number"
        )

    controlled_candidates = (
        candidacy_payload.get(
            "candidates"
        )
    )

    if not isinstance(
        controlled_candidates,
        list,
    ):
        _fail(
            "candidacy payload has no candidates list"
        )

    validate_wikimedia_candidate_articles(
        registry_payload,
        expected_candidates=(
            controlled_candidates
        ),
    )

    mappings = {
        record[
            "candidate_id"
        ]: record
        for record
        in registry_payload[
            "candidates"
        ]
    }

    logical_request_count = 0

    def paced_fetch(
        url: str,
    ) -> dict[str, Any]:
        nonlocal logical_request_count

        if (
            logical_request_count
            > 0
            and delay_seconds
            > 0
        ):
            sleeper(
                float(
                    delay_seconds
                )
            )

        result = fetcher(
            url
        )

        logical_request_count += 1

        return result

    observations: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    # Deliberately sequential. No thread pool, async gather,
    # multiprocessing pool, or concurrent Wikimedia requests.
    candidate_count = len(
        controlled_candidates
    )

    for index, candidate in enumerate(
        controlled_candidates,
        start=1,
    ):
        candidate_id = candidate[
            "candidate_id"
        ]

        candidate_name = candidate[
            "candidate_name"
        ]

        mapping = mappings[
            candidate_id
        ]

        print(
            f"[{index:02d}/{candidate_count:02d}] "
            f"{candidate_name} ({candidate_id}) - verify",
            flush=True,
        )

        canonical = (
            verify_article_mapping(
                mapping,
                fetcher=(
                    paced_fetch
                ),
            )
        )

        print(
            f"[{index:02d}/{candidate_count:02d}] "
            f"{candidate_name} ({candidate_id}) - pageviews",
            flush=True,
        )

        observations[
            candidate_id
        ] = (
            fetch_pageview_series(
                canonical,
                data_as_of=(
                    data_as_of
                ),
                fetcher=(
                    paced_fetch
                ),
                sleeper=(
                    sleeper
                ),
            )
        )

    return observations


def _load_json_object(
    path: Path | str,
    *,
    label: str,
) -> dict[str, Any]:
    source = Path(
        path
    )

    try:
        payload = json.loads(
            source.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as error:
        raise CandidateAttentionBuildError(
            f"{label} file is missing: {source}"
        ) from error
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        OSError,
    ) as error:
        raise CandidateAttentionBuildError(
            f"{label} could not be loaded: {error}"
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        _fail(
            f"{label} must contain a JSON object"
        )

    return payload


def default_data_as_of(
    *,
    now: datetime | None = None,
) -> date:
    current = (
        now
        if now is not None
        else datetime.now(
            timezone.utc
        )
    )

    if current.tzinfo is None:
        current = (
            current.replace(
                tzinfo=timezone.utc
            )
        )

    return (
        current.astimezone(
            timezone.utc
        ).date()
        - timedelta(
            days=1
        )
    )


def default_generated_at(
    *,
    now: datetime | None = None,
) -> str:
    current = (
        now
        if now is not None
        else datetime.now(
            timezone.utc
        )
    )

    if current.tzinfo is None:
        current = (
            current.replace(
                tzinfo=timezone.utc
            )
        )

    return (
        current.astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def run_build(
    *,
    candidacy_path: Path | str = (
        "candidate_candidacy_status.json"
    ),
    registry_path: Path | str = (
        "wikimedia_candidate_articles.json"
    ),
    output_path: Path | str = (
        "candidate_attention.json"
    ),
    data_as_of: str | None = None,
    generated_at: str | None = None,
    fallback_days: int = 0,
    delay_seconds: float = (
        DEFAULT_REQUEST_DELAY_SECONDS
    ),
    fetcher: Callable[
        [str],
        dict[str, Any],
    ] = fetch_json,
    sleeper: Callable[
        [float],
        None,
    ] = time.sleep,
) -> dict[str, Any]:
    if (
        not isinstance(
            fallback_days,
            int,
        )
        or isinstance(
            fallback_days,
            bool,
        )
        or fallback_days not in (0, 1)
    ):
        _fail(
            "fallback_days must be 0 or 1"
        )

    try:
        candidacy_payload = (
            load_candidate_candidacy_status(
                candidacy_path
            )
        )
    except Exception as error:
        raise CandidateAttentionBuildError(
            "candidacy registry validation failed: "
            f"{error}"
        ) from error

    registry_payload = (
        _load_json_object(
            registry_path,
            label=(
                "Wikimedia article registry"
            ),
        )
    )

    validate_wikimedia_candidate_articles(
        registry_payload,
        expected_candidates=(
            candidacy_payload[
                "candidates"
            ]
        ),
    )

    end_date = (
        parse_calendar_date(
            data_as_of,
            "data_as_of",
        )
        if data_as_of
        is not None
        else default_data_as_of()
    )

    execution_time = (
        normalize_generated_at(
            generated_at
        )
        if generated_at
        is not None
        else default_generated_at()
    )

    resolved_date = end_date

    try:
        observations = (
            collect_wikimedia_observations(
                candidacy_payload=(
                    candidacy_payload
                ),
                registry_payload=(
                    registry_payload
                ),
                data_as_of=(
                    resolved_date
                ),
                fetcher=(
                    fetcher
                ),
                delay_seconds=(
                    delay_seconds
                ),
                sleeper=(
                    sleeper
                ),
            )
        )
    except WikimediaPageviewsNotFoundError:
        if fallback_days == 0:
            raise

        resolved_date = (
            end_date
            - timedelta(days=1)
        )

        print(
            "Preferred Pageviews date unavailable; "
            "retrying complete collection for "
            f"{resolved_date.isoformat()}.",
            flush=True,
        )

        observations = (
            collect_wikimedia_observations(
                candidacy_payload=(
                    candidacy_payload
                ),
                registry_payload=(
                    registry_payload
                ),
                data_as_of=(
                    resolved_date
                ),
                fetcher=(
                    fetcher
                ),
                delay_seconds=(
                    delay_seconds
                ),
                sleeper=(
                    sleeper
                ),
            )
        )

    payload = (
        build_candidate_attention_payload(
            candidacy_payload=(
                candidacy_payload
            ),
            registry_payload=(
                registry_payload
            ),
            observations_by_candidate=(
                observations
            ),
            generated_at=(
                execution_time
            ),
            data_as_of=(
                resolved_date.isoformat()
            ),
        )
    )

    # Complete contract validation occurs before output replacement.
    content = (
        serialize_candidate_attention(
            payload,
            expected_candidates=(
                candidacy_payload[
                    "candidates"
                ]
            ),
        )
    )

    atomic_write_bytes(
        output_path,
        content,
    )

    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build candidate_attention.json from "
            "French Wikipedia daily pageviews."
        )
    )

    parser.add_argument(
        "--candidacy-status",
        default=(
            "candidate_candidacy_status.json"
        ),
    )

    parser.add_argument(
        "--registry",
        default=(
            "wikimedia_candidate_articles.json"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "candidate_attention.json"
        ),
    )

    parser.add_argument(
        "--end-date",
        default=None,
        help=(
            "Final complete UTC observation "
            "date (YYYY-MM-DD). "
            "Defaults to yesterday UTC."
        ),
    )

    parser.add_argument(
        "--fallback-days",
        type=int,
        choices=(0, 1),
        default=0,
        help=(
            "On a Pageviews HTTP 404 only, retry the complete "
            "collection for one previous calendar day."
        ),
    )

    parser.add_argument(
        "--generated-at",
        default=None,
        help=(
            "Explicit UTC execution timestamp "
            "for reproducible runs."
        ),
    )

    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=(
            DEFAULT_REQUEST_DELAY_SECONDS
        ),
    )

    return parser


def main() -> int:
    args = (
        _parser().parse_args()
    )

    payload = run_build(
        candidacy_path=(
            args.candidacy_status
        ),
        registry_path=(
            args.registry
        ),
        output_path=(
            args.output
        ),
        data_as_of=(
            args.end_date
        ),
        generated_at=(
            args.generated_at
        ),
        fallback_days=(
            args.fallback_days
        ),
        delay_seconds=(
            args.delay_seconds
        ),
    )

    print(
        "Candidate Attention built:"
    )

    print(
        "  candidates:",
        payload[
            "candidate_universe"
        ]["count"],
    )

    print(
        "  period:",
        payload[
            "period"
        ]["start_date"],
        "to",
        payload[
            "period"
        ]["end_date"],
    )

    print(
        "  data_as_of:",
        payload[
            "period"
        ]["data_as_of"],
    )

    print(
        "  output:",
        args.output,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
