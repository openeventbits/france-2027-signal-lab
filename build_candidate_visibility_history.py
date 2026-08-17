from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    validate_candidate_candidacy_status,
)
from candidate_visibility_history_contract import (
    CAMPAIGN_LANE,
    EXPECTED_DAYS,
    GENERAL_LANE,
    GENERAL_SCOPE,
    METHODOLOGY_CANDIDATE_LINKAGE,
    METHODOLOGY_METRIC,
    METHODOLOGY_SOURCE,
    NOT_MEASURES,
    PRIMARY_SCOPES,
    SCHEMA_VERSION,
    CandidateVisibilityHistoryContractError,
    serialize_candidate_visibility_history,
    validate_candidate_visibility_history,
)
from fetch_news_wire import (
    round_candidate_visibility_ratio,
    validate_output,
)


DEFAULT_NEWS_PATH = "news_wire.json"
DEFAULT_CANDIDACY_PATH = "candidate_candidacy_status.json"
DEFAULT_OUTPUT_PATH = "candidate_visibility_history.json"

MINIMUM_SOURCE_WINDOW_DAYS = 30


class CandidateVisibilityHistoryBuildError(ValueError):
    """Raised when visibility history cannot be derived safely."""


def _fail(message: str) -> None:
    raise CandidateVisibilityHistoryBuildError(message)


def _require_trimmed_text(
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


def _utc_datetime(
    value: Any,
    field: str,
) -> datetime:
    text = _require_trimmed_text(
        value,
        field,
    )

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise CandidateVisibilityHistoryBuildError(
            f"{field} must be a valid UTC ISO-8601 timestamp"
        ) from error

    if (
        parsed.tzinfo is None
        or parsed.utcoffset()
        != timezone.utc.utcoffset(parsed)
    ):
        _fail(f"{field} must use UTC")

    return parsed.astimezone(timezone.utc)


def _history_dates(
    generated_at: datetime,
) -> tuple[date, date, list[str]]:
    anchor = generated_at.astimezone(
        timezone.utc
    ).date()

    end_date = anchor - timedelta(days=1)
    start_date = end_date - timedelta(
        days=EXPECTED_DAYS - 1
    )

    dates = [
        (
            start_date + timedelta(days=offset)
        ).isoformat()
        for offset in range(EXPECTED_DAYS)
    ]

    return start_date, end_date, dates


def _candidate_identity_index(
    candidates: list[dict[str, Any]],
) -> dict[str, str]:
    identity_to_id: dict[str, str] = {}

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            _fail(
                f"candidates[{index}] must be an object"
            )

        candidate_id = _require_trimmed_text(
            candidate.get("candidate_id"),
            f"candidates[{index}].candidate_id",
        )

        candidate_name = _require_trimmed_text(
            candidate.get("candidate_name"),
            f"candidates[{index}].candidate_name",
        )

        identities = [
            candidate_name,
            *candidate.get("previous_names", []),
        ]

        for identity in identities:
            identity_name = _require_trimmed_text(
                identity,
                (
                    f"candidates[{index}] "
                    "published identity"
                ),
            )

            previous_owner = identity_to_id.get(
                identity_name
            )

            if (
                previous_owner is not None
                and previous_owner != candidate_id
            ):
                _fail(
                    "candidate identity collision between "
                    f"{previous_owner!r} and {candidate_id!r}: "
                    f"{identity_name!r}"
                )

            identity_to_id[
                identity_name
            ] = candidate_id

    return identity_to_id


def _new_day_accumulator() -> dict[str, Any]:
    return {
        "record_count": 0,
        "publishers": set(),
        "candidate_counts": {},
        "candidate_publishers": {},
    }


def _daily_accumulators(
    dates: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        CAMPAIGN_LANE: {
            current_date: _new_day_accumulator()
            for current_date in dates
        },
        GENERAL_LANE: {
            current_date: _new_day_accumulator()
            for current_date in dates
        },
    }


def _resolve_candidate_matches(
    item: dict[str, Any],
    *,
    item_index: int,
    identity_index: dict[str, str],
) -> list[str]:
    matches = item.get("candidate_matches")

    if (
        not isinstance(matches, list)
        or not matches
    ):
        _fail(
            f"candidate_watch[{item_index}]."
            "candidate_matches must be a non-empty array"
        )

    candidate_ids: list[str] = []
    seen_ids: set[str] = set()

    for match_index, match in enumerate(matches):
        if not isinstance(match, dict):
            _fail(
                f"candidate_watch[{item_index}]."
                f"candidate_matches[{match_index}] "
                "must be an object"
            )

        candidate_name = _require_trimmed_text(
            match.get("candidate"),
            (
                f"candidate_watch[{item_index}]."
                f"candidate_matches[{match_index}]."
                "candidate"
            ),
        )

        candidate_id = identity_index.get(
            candidate_name
        )

        if candidate_id is None:
            _fail(
                "candidate_watch references an identity "
                "outside the controlled candidacy registry: "
                f"{candidate_name!r}"
            )

        if candidate_id in seen_ids:
            _fail(
                "candidate_watch record resolves the same "
                "candidate more than once: "
                f"{candidate_name!r}"
            )

        seen_ids.add(candidate_id)
        candidate_ids.append(candidate_id)

    return candidate_ids


def build_candidate_visibility_history(
    *,
    candidate_watch: list[dict[str, Any]],
    generated_at: str,
    window_days: int,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build 29 complete UTC days from published candidate matches only."""

    if not isinstance(candidate_watch, list):
        _fail("candidate_watch must be an array")

    if (
        type(window_days) is not int
        or window_days < MINIMUM_SOURCE_WINDOW_DAYS
    ):
        _fail(
            "source window must retain at least "
            f"{MINIMUM_SOURCE_WINDOW_DAYS} days"
        )

    if (
        not isinstance(candidates, list)
        or not candidates
    ):
        _fail("candidates must be a non-empty array")

    generated = _utc_datetime(
        generated_at,
        "news.generated_at",
    )

    start_date, end_date, dates = (
        _history_dates(generated)
    )

    date_set = set(dates)

    identity_index = _candidate_identity_index(
        candidates
    )

    candidate_ids = [
        candidate["candidate_id"]
        for candidate in candidates
    ]

    accumulators = _daily_accumulators(
        dates
    )

    for item_index, item in enumerate(
        candidate_watch
    ):
        if not isinstance(item, dict):
            _fail(
                f"candidate_watch[{item_index}] "
                "must be an object"
            )

        scope = item.get("coverage_scope")

        if scope not in {
            *PRIMARY_SCOPES,
            GENERAL_SCOPE,
        }:
            _fail(
                f"candidate_watch[{item_index}]."
                "coverage_scope is invalid"
            )

        published = _utc_datetime(
            item.get("published_at"),
            (
                f"candidate_watch[{item_index}]."
                "published_at"
            ),
        )

        published_date = (
            published.date().isoformat()
        )

        candidate_match_ids = (
            _resolve_candidate_matches(
                item,
                item_index=item_index,
                identity_index=identity_index,
            )
        )

        publisher = _require_trimmed_text(
            item.get("publisher"),
            (
                f"candidate_watch[{item_index}]."
                "publisher"
            ),
        )

        # The retained source includes the current UTC day
        # and may include a partial leading day. Neither is
        # part of the complete-day history artifact.
        if published_date not in date_set:
            continue

        lane_name = (
            CAMPAIGN_LANE
            if scope in PRIMARY_SCOPES
            else GENERAL_LANE
        )

        day = accumulators[
            lane_name
        ][published_date]

        # One candidate-linked record contributes exactly
        # once to the lane denominator regardless of how
        # many candidates it links to.
        day["record_count"] += 1
        day["publishers"].add(publisher)

        # The same record contributes once to every
        # published candidate match.
        for candidate_id in candidate_match_ids:
            day["candidate_counts"][
                candidate_id
            ] = (
                day["candidate_counts"].get(
                    candidate_id,
                    0,
                )
                + 1
            )

            day[
                "candidate_publishers"
            ].setdefault(
                candidate_id,
                set(),
            ).add(publisher)

    lanes: dict[str, Any] = {}

    for lane_name in (
        CAMPAIGN_LANE,
        GENERAL_LANE,
    ):
        lanes[lane_name] = {
            "daily_denominators": [
                {
                    "date": current_date,
                    "record_count": (
                        accumulators[
                            lane_name
                        ][current_date][
                            "record_count"
                        ]
                    ),
                    "publisher_count": len(
                        accumulators[
                            lane_name
                        ][current_date][
                            "publishers"
                        ]
                    ),
                }
                for current_date in dates
            ]
        }

    candidate_rows: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_id = candidate[
            "candidate_id"
        ]
        candidate_name = candidate[
            "candidate_name"
        ]

        row: dict[str, Any] = {
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
        }

        for lane_name in (
            CAMPAIGN_LANE,
            GENERAL_LANE,
        ):
            daily_series: list[
                dict[str, Any]
            ] = []

            for current_date in dates:
                day = accumulators[
                    lane_name
                ][current_date]

                denominator = day[
                    "record_count"
                ]

                record_count = day[
                    "candidate_counts"
                ].get(
                    candidate_id,
                    0,
                )

                publisher_count = len(
                    day[
                        "candidate_publishers"
                    ].get(
                        candidate_id,
                        set(),
                    )
                )

                share = (
                    None
                    if denominator == 0
                    else round_candidate_visibility_ratio(
                        record_count
                        / denominator
                    )
                )

                daily_series.append(
                    {
                        "date": current_date,
                        "record_count": (
                            record_count
                        ),
                        "share": share,
                        "publisher_count": (
                            publisher_count
                        ),
                    }
                )

            row[lane_name] = {
                "daily_series": daily_series
            }

        candidate_rows.append(row)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": EXPECTED_DAYS,
            "data_as_of": end_date.isoformat(),
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "methodology": {
            "source": METHODOLOGY_SOURCE,
            "primary_scopes": list(
                PRIMARY_SCOPES
            ),
            "general_scope": GENERAL_SCOPE,
            "metric": METHODOLOGY_METRIC,
            "candidate_linkage": (
                METHODOLOGY_CANDIDATE_LINKAGE
            ),
            "not_measures": list(
                NOT_MEASURES
            ),
        },
        "lanes": lanes,
        "candidates": candidate_rows,
    }

    validate_candidate_visibility_history(
        payload,
        expected_candidates=candidates,
    )

    return payload


def build_from_payloads(
    news_payload: dict[str, Any],
    candidacy_payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate current repository inputs and derive the history artifact."""

    try:
        validate_output(news_payload)
    except RuntimeError as error:
        raise CandidateVisibilityHistoryBuildError(
            f"news_wire.json is invalid: {error}"
        ) from error

    try:
        validate_candidate_candidacy_status(
            candidacy_payload
        )
    except CandidateCandidacyStatusError as error:
        raise CandidateVisibilityHistoryBuildError(
            "candidate_candidacy_status.json "
            f"is invalid: {error}"
        ) from error

    generated_at = news_payload.get(
        "generated_at"
    )
    window_days = news_payload.get(
        "window_days"
    )
    candidate_watch = news_payload.get(
        "candidate_watch"
    )

    payload = build_candidate_visibility_history(
        candidate_watch=candidate_watch,
        generated_at=generated_at,
        window_days=window_days,
        candidates=candidacy_payload[
            "candidates"
        ],
    )

    validate_candidate_visibility_history(
        payload,
        expected_candidates=candidacy_payload[
            "candidates"
        ],
    )

    return payload


def load_json(
    path: Path | str,
) -> Any:
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)


def atomic_write_bytes(
    path: Path | str,
    content: bytes,
) -> None:
    target = Path(path)

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic Candidate Visibility "
            "History from retained News Wire evidence."
        )
    )

    parser.add_argument(
        "--news",
        default=DEFAULT_NEWS_PATH,
        help=(
            "validated News Wire input "
            f"(default: {DEFAULT_NEWS_PATH})"
        ),
    )

    parser.add_argument(
        "--candidacy-status",
        default=DEFAULT_CANDIDACY_PATH,
        help=(
            "controlled candidacy registry "
            f"(default: {DEFAULT_CANDIDACY_PATH})"
        ),
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "output artifact "
            f"(default: {DEFAULT_OUTPUT_PATH})"
        ),
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "build and validate entirely in memory "
            "without writing the output file"
        ),
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    arguments = _parser().parse_args(
        argv
    )

    try:
        news_payload = load_json(
            arguments.news
        )
        candidacy_payload = load_json(
            arguments.candidacy_status
        )

        payload = build_from_payloads(
            news_payload,
            candidacy_payload,
        )

        content = (
            serialize_candidate_visibility_history(
                payload,
                expected_candidates=(
                    candidacy_payload[
                        "candidates"
                    ]
                ),
            )
        )

        if not arguments.check:
            atomic_write_bytes(
                arguments.output,
                content,
            )

    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            "candidate visibility history error: "
            f"{error}"
        )
        return 1

    action = (
        "validated"
        if arguments.check
        else "wrote"
    )

    print(
        f"{action} "
        f"{arguments.output} "
        f"({payload['period']['start_date']} "
        f"through {payload['period']['end_date']}; "
        f"{len(payload['candidates'])} candidates)"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())