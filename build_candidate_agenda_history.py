"""Build persistent daily Candidate Agenda History from published News Wire evidence."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from candidate_agenda_history_contract import (
    CAMPAIGN_TAXONOMY,
    DAY_BOUNDARY,
    METHODOLOGY,
    POLICY_MIN_NONZERO_TOPICS,
    POLICY_TAXONOMY,
    SCHEMA_VERSION,
    CandidateAgendaHistoryContractError,
    serialize_candidate_agenda_history,
    validate_candidate_agenda_history,
)
from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    validate_candidate_candidacy_status,
)
from candidate_identity import CandidateIdentityError, normalized_candidate_key
from fetch_news_wire import (
    classify_campaign_agenda,
    classify_policy_agenda,
    normalize,
    validate_output as validate_news_wire,
)


RECOMPUTABLE_CALENDAR_DAYS = 30


class CandidateAgendaHistoryBuildError(ValueError):
    """Raised when safe Candidate Agenda History construction is impossible."""


def _utc_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CandidateAgendaHistoryBuildError(
            f"{field} must be a UTC ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidateAgendaHistoryBuildError(
            f"{field} must be a UTC ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CandidateAgendaHistoryBuildError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _empty_counts(taxonomy: tuple[tuple[str, str], ...]) -> dict[str, int]:
    return {topic_id: 0 for topic_id, _label in taxonomy}


def _empty_day(current_date: date) -> dict[str, Any]:
    return {
        "date": current_date.isoformat(),
        "policy_counts": _empty_counts(POLICY_TAXONOMY),
        "campaign_counts": _empty_counts(CAMPAIGN_TAXONOMY),
    }


def _candidate_identity_index(
    candidates: list[dict[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        names = [candidate["candidate_name"], *candidate.get("previous_names", [])]
        for name in names:
            try:
                key = normalized_candidate_key(name)
            except CandidateIdentityError as error:
                raise CandidateAgendaHistoryBuildError(
                    f"candidate registry contains an invalid identity: {error}"
                ) from error
            prior = result.get(key)
            if prior is not None and prior != candidate_id:
                raise CandidateAgendaHistoryBuildError(
                    f"controlled candidate identity {name!r} maps to multiple stable IDs"
                )
            result[key] = candidate_id
    return result


def _linked_candidate_ids(
    item: dict[str, Any], identity_index: dict[str, str]
) -> list[str]:
    matches = item.get("candidate_matches")
    if not isinstance(matches, list):
        raise CandidateAgendaHistoryBuildError(
            "relevant_news candidate_matches must be an array"
        )
    result: list[str] = []
    seen: set[str] = set()
    for match in matches:
        name = match.get("candidate") if isinstance(match, dict) else None
        try:
            key = normalized_candidate_key(name)
        except (CandidateIdentityError, TypeError) as error:
            raise CandidateAgendaHistoryBuildError(
                "relevant_news contains an invalid published candidate identity"
            ) from error
        candidate_id = identity_index.get(key)
        if candidate_id is None:
            raise CandidateAgendaHistoryBuildError(
                f"relevant_news references uncontrolled candidate identity {name!r}"
            )
        if candidate_id not in seen:
            seen.add(candidate_id)
            result.append(candidate_id)
    return result


def _recompute_days(
    *,
    relevant_news: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    recomputable_start: date,
    data_as_of: date,
) -> dict[str, dict[str, dict[str, Any]]]:
    buckets = {
        candidate["candidate_id"]: {
            current_date.isoformat(): _empty_day(current_date)
            for current_date in _dates(recomputable_start, data_as_of)
        }
        for candidate in candidates
    }
    identity_index = _candidate_identity_index(candidates)
    policy_ids = {topic_id for topic_id, _label in POLICY_TAXONOMY}
    campaign_ids = {topic_id for topic_id, _label in CAMPAIGN_TAXONOMY}

    for index, item in enumerate(relevant_news):
        if not isinstance(item, dict):
            raise CandidateAgendaHistoryBuildError(
                f"relevant_news[{index}] must be an object"
            )
        published_at = _utc_datetime(
            item.get("published_at"), field=f"relevant_news[{index}].published_at"
        )
        published_date = published_at.date()
        if published_date < recomputable_start or published_date > data_as_of:
            continue

        linked_ids = _linked_candidate_ids(item, identity_index)
        if not linked_ids:
            continue
        headline = item.get("headline")
        if not isinstance(headline, str):
            raise CandidateAgendaHistoryBuildError(
                f"relevant_news[{index}].headline must be a string"
            )
        summary = item.get("summary", "")
        if not isinstance(summary, str):
            raise CandidateAgendaHistoryBuildError(
                f"relevant_news[{index}].summary must be a string when supplied"
            )
        policy_classifications = classify_policy_agenda(headline, summary)
        policy_topics = [classification.get("id") for classification in policy_classifications]
        if len(policy_topics) != len(set(policy_topics)) or any(
            topic_id not in policy_ids for topic_id in policy_topics
        ):
            raise CandidateAgendaHistoryBuildError(
                "classify_policy_agenda returned a non-canonical topic"
            )
        matched_names = item.get("candidates")
        if not isinstance(matched_names, list) or any(
            not isinstance(name, str) for name in matched_names
        ):
            raise CandidateAgendaHistoryBuildError(
                f"relevant_news[{index}].candidates must be an array of strings"
            )
        campaign_classification = classify_campaign_agenda(
            normalize(headline),
            explicit_election=bool(item.get("explicit_election")),
            matched_candidates=matched_names,
        )
        campaign_topic = (
            campaign_classification.get("id")
            if campaign_classification is not None
            else None
        )
        if campaign_topic is not None and campaign_topic not in campaign_ids:
            raise CandidateAgendaHistoryBuildError(
                "classify_campaign_agenda returned a non-canonical topic"
            )

        day_key = published_date.isoformat()
        for candidate_id in linked_ids:
            day = buckets[candidate_id][day_key]
            for topic_id in policy_topics:
                day["policy_counts"][topic_id] += 1
            if campaign_topic is not None:
                day["campaign_counts"][campaign_topic] += 1
    return buckets


def _cumulative_profile(
    *, tracking_start: date, data_as_of: date, daily_series: list[dict[str, Any]]
) -> dict[str, Any]:
    policy_totals = _empty_counts(POLICY_TAXONOMY)
    campaign_totals = _empty_counts(CAMPAIGN_TAXONOMY)
    for day in daily_series:
        for topic_id in policy_totals:
            policy_totals[topic_id] += day["policy_counts"][topic_id]
        for topic_id in campaign_totals:
            campaign_totals[topic_id] += day["campaign_counts"][topic_id]
    profile_mode = (
        "policy"
        if sum(count > 0 for count in policy_totals.values())
        >= POLICY_MIN_NONZERO_TOPICS
        else "campaign"
    )
    taxonomy = POLICY_TAXONOMY if profile_mode == "policy" else CAMPAIGN_TAXONOMY
    totals = policy_totals if profile_mode == "policy" else campaign_totals
    association_count = sum(totals.values())
    return {
        "profile_mode": profile_mode,
        "period_start": tracking_start.isoformat(),
        "period_end": data_as_of.isoformat(),
        "day_count": (data_as_of - tracking_start).days + 1,
        "association_count": association_count,
        "topics": [
            {
                "id": topic_id,
                "label": label,
                "count": totals[topic_id],
                "share": (
                    round(totals[topic_id] / association_count, 6)
                    if association_count
                    else 0.0
                ),
            }
            for topic_id, label in taxonomy
        ],
    }


def build_candidate_agenda_history(
    *,
    relevant_news: list[dict[str, Any]],
    generated_at: str,
    window_days: int,
    candidates: list[dict[str, Any]],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a merged artifact from current evidence and optional settled state."""

    if type(window_days) is not int or window_days < 30:
        raise CandidateAgendaHistoryBuildError(
            "news window_days must provide at least 30 UTC calendar days"
        )
    generated_day = _utc_datetime(generated_at, field="news.generated_at").date()
    data_as_of = generated_day
    recomputable_start = data_as_of - timedelta(
        days=RECOMPUTABLE_CALENDAR_DAYS - 1
    )

    previous_by_id: dict[str, dict[str, Any]] = {}
    if previous is None:
        global_start = recomputable_start
    else:
        try:
            validate_candidate_agenda_history(previous)
            global_start = date.fromisoformat(
                previous["tracking"]["start_date"]
            )
        except CandidateAgendaHistoryContractError as error:
            raise CandidateAgendaHistoryBuildError(
                f"previous Candidate Agenda History is invalid: {error}"
            ) from error
        previous_data_as_of = date.fromisoformat(
            previous["tracking"]["data_as_of"]
        )
        if previous_data_as_of > data_as_of:
            raise CandidateAgendaHistoryBuildError(
                "previous data_as_of is later than the current build data_as_of"
            )
        previous_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in previous["candidates"]
        }

    rebuilt = _recompute_days(
        relevant_news=relevant_news,
        candidates=candidates,
        recomputable_start=recomputable_start,
        data_as_of=data_as_of,
    )
    output_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        prior = previous_by_id.get(candidate_id)
        if previous is None:
            candidate_start = global_start
        elif prior is None:
            candidate_start = max(global_start, recomputable_start)
        else:
            candidate_start = date.fromisoformat(prior["tracking_start"])

        preserved: dict[str, dict[str, Any]] = {}
        if prior is not None:
            preserved = {
                row["date"]: row
                for row in prior["daily_series"]
                if date.fromisoformat(row["date"]) < recomputable_start
            }
        merged: list[dict[str, Any]] = []
        for current_date in _dates(candidate_start, data_as_of):
            day_key = current_date.isoformat()
            if current_date < recomputable_start:
                row = preserved.get(day_key)
                if row is None:
                    raise CandidateAgendaHistoryBuildError(
                        f"missing settled historical day {day_key} for {candidate_id}"
                    )
            else:
                row = rebuilt[candidate_id][day_key]
            merged.append(row)

        output_candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": candidate["candidate_name"],
                "tracking_start": candidate_start.isoformat(),
                "daily_series": merged,
                "cumulative_profile": _cumulative_profile(
                    tracking_start=candidate_start,
                    data_as_of=data_as_of,
                    daily_series=merged,
                ),
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "tracking": {
            "start_date": global_start.isoformat(),
            "data_as_of": data_as_of.isoformat(),
            "day_boundary": DAY_BOUNDARY,
            "current_utc_day_excluded": False,
        },
        "methodology": dict(METHODOLOGY),
        "taxonomies": {
            "policy": [
                {"id": topic_id, "label": label}
                for topic_id, label in POLICY_TAXONOMY
            ],
            "campaign": [
                {"id": topic_id, "label": label}
                for topic_id, label in CAMPAIGN_TAXONOMY
            ],
        },
        "candidates": output_candidates,
    }
    try:
        validate_candidate_agenda_history(payload, expected_candidates=candidates)
    except CandidateAgendaHistoryContractError as error:
        raise CandidateAgendaHistoryBuildError(
            f"built Candidate Agenda History is invalid: {error}"
        ) from error
    return payload


def build_from_payloads(
    news: Any,
    candidacy_status: Any,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate source artifacts, then build without network access."""

    try:
        validate_news_wire(news)
    except (KeyError, RuntimeError, TypeError, ValueError) as error:
        raise CandidateAgendaHistoryBuildError(f"news source is invalid: {error}") from error
    try:
        validate_candidate_candidacy_status(candidacy_status)
    except CandidateCandidacyStatusError as error:
        raise CandidateAgendaHistoryBuildError(
            f"candidate registry is invalid: {error}"
        ) from error
    return build_candidate_agenda_history(
        relevant_news=news["relevant_news"],
        generated_at=news["generated_at"],
        window_days=news["window_days"],
        candidates=candidacy_status["candidates"],
        previous=previous,
    )


def load_json(path: Path, *, field: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateAgendaHistoryBuildError(
            f"could not read {field} from {path}: {error}"
        ) from error


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build persistent candidate_agenda_history.json"
    )
    parser.add_argument("--news", type=Path, default=Path("news_wire.json"))
    parser.add_argument(
        "--candidacy-status",
        type=Path,
        default=Path("candidate_candidacy_status.json"),
    )
    parser.add_argument("--previous", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("candidate_agenda_history.json")
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate a complete build without replacing the output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        news = load_json(args.news, field="News Wire")
        registry = load_json(args.candidacy_status, field="candidate registry")
        previous = (
            load_json(args.previous, field="previous Candidate Agenda History")
            if args.previous is not None
            else None
        )
        payload = build_from_payloads(news, registry, previous)
        content = serialize_candidate_agenda_history(payload)
        if not args.check:
            atomic_write_bytes(args.output, content)
    except CandidateAgendaHistoryBuildError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
