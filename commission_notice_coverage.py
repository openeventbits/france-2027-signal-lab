"""Reconcile relevant Commission notices to published FR27 poll waves."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from poll_contract import FIRST_ROUND, normalize_identity


COVERAGE_STATES = {"parsed", "reconciled", "unresolved"}
RELEVANT_CLASSIFICATIONS = {"eligible", "unsupported"}
BAROMETER_NOTICE_IDS = frozenset({"commission:10327", "commission:10284"})
BAROMETER_REVIEW = Path(__file__).with_name("fr27_commission_barometer_review.json")
BAROMETER_REVIEW_SHA256 = "f22afa82eb0bf8ecefae56e382d804a30715c71346b00ea445b0d6d1d61fe439"


class CommissionCoverageError(ValueError):
    """Raised when Commission coverage metadata is invalid."""


def is_relevant_notice(notice: dict[str, Any]) -> bool:
    """Return whether the existing classification treats a notice as relevant."""
    return notice.get("classification") in RELEVANT_CLASSIFICATIONS


def unresolved_coverage(reason: str) -> dict[str, Any]:
    return {
        "state": "unresolved",
        "matched_event_ids": [],
        "method": reason,
    }


def synchronize_notice_coverage(notice: dict[str, Any]) -> None:
    """Add a safe default for relevant notices and remove states from others."""
    if is_relevant_notice(notice):
        notice.setdefault(
            "coverage",
            unresolved_coverage("not_yet_reconciled"),
        )
    else:
        notice.pop("coverage", None)


def _iso_date(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CommissionCoverageError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise CommissionCoverageError(f"{field} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise CommissionCoverageError(f"{field} must use YYYY-MM-DD")
    return value


def _survey_metadata(notice: dict[str, Any]) -> dict[str, Any]:
    metadata = notice.get("survey_metadata")
    if isinstance(metadata, dict):
        return metadata
    return notice


def validate_notice_coverage(
    notice: dict[str, Any],
    *,
    allow_missing_legacy_coverage: bool = False,
) -> None:
    """Validate optional source metadata and derived coverage for one notice."""
    notice_id = str(notice.get("notice_id", "notice"))
    metadata = notice.get("survey_metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise CommissionCoverageError(
                f"{notice_id}.survey_metadata must be an object"
            )
        allowed = {
            "pollster",
            "fieldwork_start",
            "fieldwork_end",
            "sample_size",
            "publication_date",
            "commissioner",
        }
        unexpected = set(metadata) - allowed
        if unexpected:
            raise CommissionCoverageError(
                f"{notice_id}.survey_metadata has unexpected fields: "
                f"{sorted(unexpected)}"
            )
        for field in ("pollster", "commissioner"):
            value = metadata.get(field)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise CommissionCoverageError(
                    f"{notice_id}.survey_metadata.{field} must be text or null"
                )
        start = metadata.get("fieldwork_start")
        end = metadata.get("fieldwork_end")
        if (start is None) != (end is None):
            raise CommissionCoverageError(
                f"{notice_id}.survey_metadata fieldwork dates must be paired"
            )
        if start is not None:
            normalized_start = _iso_date(
                start,
                field=f"{notice_id}.survey_metadata.fieldwork_start",
            )
            normalized_end = _iso_date(
                end,
                field=f"{notice_id}.survey_metadata.fieldwork_end",
            )
            if normalized_start > normalized_end:
                raise CommissionCoverageError(
                    f"{notice_id}.survey_metadata fieldwork dates are reversed"
                )
        publication_date = metadata.get("publication_date")
        if publication_date is not None:
            _iso_date(
                publication_date,
                field=f"{notice_id}.survey_metadata.publication_date",
            )
        sample_size = metadata.get("sample_size")
        if sample_size is not None and (
            isinstance(sample_size, bool)
            or not isinstance(sample_size, int)
            or sample_size < 1
        ):
            raise CommissionCoverageError(
                f"{notice_id}.survey_metadata.sample_size must be positive"
            )

    if not is_relevant_notice(notice):
        if "coverage" in notice:
            raise CommissionCoverageError(
                f"{notice_id} is not relevant and must not have coverage state"
            )
        return
    if "coverage" not in notice and allow_missing_legacy_coverage:
        return
    coverage = notice.get("coverage")
    if not isinstance(coverage, dict):
        raise CommissionCoverageError(
            f"{notice_id} relevant notice lacks coverage state"
        )
    if set(coverage) != {"state", "matched_event_ids", "method"}:
        raise CommissionCoverageError(
            f"{notice_id}.coverage has an unexpected contract"
        )
    state = coverage.get("state")
    if state not in COVERAGE_STATES:
        raise CommissionCoverageError(
            f"{notice_id}.coverage.state is invalid"
        )
    method = coverage.get("method")
    if not isinstance(method, str) or not method.strip():
        raise CommissionCoverageError(
            f"{notice_id}.coverage.method must be text"
        )
    event_ids = coverage.get("matched_event_ids")
    if not isinstance(event_ids, list) or any(
        not isinstance(event_id, str)
        or not re.fullmatch(r"[0-9a-f]{64}", event_id)
        for event_id in event_ids
    ):
        raise CommissionCoverageError(
            f"{notice_id}.coverage.matched_event_ids is invalid"
        )
    if event_ids != sorted(set(event_ids)):
        raise CommissionCoverageError(
            f"{notice_id}.coverage.matched_event_ids is not deterministic"
        )
    if state == "unresolved" and event_ids:
        raise CommissionCoverageError(
            f"{notice_id} unresolved coverage must not match events"
        )
    if state != "unresolved" and not event_ids:
        raise CommissionCoverageError(
            f"{notice_id} {state} coverage must match events"
        )


def _event_wave_identity(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(event.get("source_url", "")).strip(),
        event.get("sample_size"),
        normalize_identity(str(event.get("commissioner", ""))),
        event.get("publication_date"),
    )


def _representative_event_ids(events: Iterable[dict[str, Any]]) -> list[str]:
    """Retain one stable event id as minimal wave-level reconciliation evidence."""
    return [min({event["event_id"] for event in events})]


CORROBORATING_WAVE_ATTRIBUTES = (
    ("sample_size", 1),
    ("commissioner", 2),
    ("publication_date", 3),
)


def _corroborate_waves(
    waves: dict[tuple[Any, ...], list[dict[str, Any]]],
    metadata: dict[str, Any],
) -> list[tuple[Any, ...]]:
    original = list(waves)
    if len(original) < 2:
        return original

    constraints: list[set[tuple[Any, ...]]] = []
    for attribute, key_index in CORROBORATING_WAVE_ATTRIBUTES:
        expected = metadata.get(attribute)
        if attribute == "commissioner":
            expected = normalize_identity(str(expected or ""))
        if expected in (None, ""):
            continue
        matching = {key for key in original if key[key_index] == expected}
        if matching:
            constraints.append(matching)

    if not constraints:
        return original
    survivors = set(original).intersection(*constraints)
    return [key for key in original if key in survivors]


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _reviewed_barometer_coverage(
    notice: dict[str, Any], events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Use exact reviewed evidence for two formerly excluded notices only.

    Generic wave matching cannot clear either notice. The pinned full-object
    digest protects all ten 10284 configurations, including identities, samples
    and provenance. The literal-score conflict in 10327 remains unresolved.
    This changes coverage only; it cannot mutate or admit polling events.
    """
    review = json.loads(BAROMETER_REVIEW.read_text(encoding="utf-8"))
    if (_canonical_sha256(review) != BAROMETER_REVIEW_SHA256
            or len(review["notices"]) != 2
            or {r["notice_id"] for r in review["notices"]} != BAROMETER_NOTICE_IDS):
        raise CommissionCoverageError("barometer evidence changed; explicit review required")
    record = next(r for r in review["notices"] if r["notice_id"] == notice["notice_id"])
    identity = record["notice_identity"]
    confirmed_without_parser = (
        notice.get("classification") == "unsupported"
        and notice.get("classification_reason") == (
            "document confirms 2027 presidential voting intentions, but no "
            "existing notice parser supports this listing"
        )
    )
    if notice.get("classification") != "eligible" and not confirmed_without_parser:
        return unresolved_coverage("reviewed_barometer_document_not_confirmed")
    if (any(notice.get(k) != value for k, value in identity.items() if k != "resolved_urls")
            or notice.get("resolved_url") not in identity["resolved_urls"]):
        return unresolved_coverage("reviewed_barometer_notice_identity_mismatch")
    if record["outcome"] == "unresolved":
        return unresolved_coverage(record["unresolved_method"])
    # These exact dates and rounds come from the reviewed original PDF, not
    # from a permissive listing or a one-event wave inference.
    published = sorted((e for e in events
        if normalize_identity(str(e.get("pollster", ""))) == normalize_identity(identity["institute"])
        and e.get("fieldwork_start") == record["fieldwork_start"]
        and e.get("fieldwork_end") == record["fieldwork_end"]
        and e.get("round") in identity["confirmed_rounds"]), key=lambda e: e["event_id"])
    if _canonical_sha256(published) != record["published_collection_sha256"]:
        return unresolved_coverage("reviewed_barometer_incomplete_or_changed_configurations")
    return {"state": "reconciled", "matched_event_ids": record["published_event_ids"].copy(),
            "method": "reviewed_barometer_complete_configurations"}


def reconcile_commission_notices(
    registry: dict[str, Any],
    events: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Derive one conservative coverage state for every relevant notice.

    Direct Commission provenance is recognized only through ``official_notice_id``.
    External-source reconciliation requires exact pollster, exact fieldwork window,
    and a compatible first-round event. Optional metadata only disambiguates
    multiple otherwise-plausible published waves.
    """
    published = list(events)
    for notice in registry.get("notices", []):
        synchronize_notice_coverage(notice)
        if not is_relevant_notice(notice):
            continue

        notice_id = notice["notice_id"]
        if notice_id in BAROMETER_NOTICE_IDS:
            notice["coverage"] = _reviewed_barometer_coverage(notice, published)
            validate_notice_coverage(notice)
            continue
        direct = [
            event
            for event in published
            if event.get("official_notice_id") == notice_id
        ]
        if direct:
            notice["coverage"] = {
                "state": "parsed",
                "matched_event_ids": _representative_event_ids(direct),
                "method": "official_notice_id",
            }
            continue

        metadata = _survey_metadata(notice)
        pollster = metadata.get("pollster") or notice.get("institute")
        start = metadata.get("fieldwork_start")
        end = metadata.get("fieldwork_end")
        if not pollster or not start or not end:
            notice["coverage"] = unresolved_coverage(
                "missing_structured_metadata"
            )
            continue
        if FIRST_ROUND not in notice.get("confirmed_rounds", []):
            notice["coverage"] = unresolved_coverage(
                "no_compatible_published_round"
            )
            continue

        plausible = [
            event
            for event in published
            if event.get("round") == FIRST_ROUND
            and normalize_identity(str(event.get("pollster", "")))
            == normalize_identity(str(pollster))
            and event.get("fieldwork_start") == start
            and event.get("fieldwork_end") == end
        ]
        if not plausible:
            notice["coverage"] = unresolved_coverage(
                "no_exact_published_wave"
            )
            continue

        waves: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for event in plausible:
            waves[_event_wave_identity(event)].append(event)
        survivors = _corroborate_waves(waves, metadata)
        if len(survivors) != 1:
            notice["coverage"] = unresolved_coverage(
                "ambiguous_published_waves"
            )
            continue

        matched = waves[survivors[0]]
        notice["coverage"] = {
            "state": "reconciled",
            "matched_event_ids": _representative_event_ids(matched),
            "method": "exact_pollster_fieldwork_round",
        }

    summary = coverage_summary(registry)
    for notice in registry.get("notices", []):
        validate_notice_coverage(notice)
    return summary


def coverage_summary(registry: dict[str, Any]) -> dict[str, Any]:
    relevant = [
        notice
        for notice in registry.get("notices", [])
        if is_relevant_notice(notice)
    ]
    counts = {
        state: sum(
            _interpreted_coverage_state(notice) == state
            for notice in relevant
        )
        for state in ("parsed", "reconciled", "unresolved")
    }
    return {
        "relevant": len(relevant),
        **counts,
        "unresolved_notice_ids": [
            notice["notice_id"]
            for notice in relevant
            if _interpreted_coverage_state(notice) == "unresolved"
        ],
    }


def _interpreted_coverage_state(notice: dict[str, Any]) -> Any:
    """Treat only missing legacy coverage as conservatively unresolved."""
    if "coverage" not in notice:
        return "unresolved"
    coverage = notice.get("coverage")
    return coverage.get("state") if isinstance(coverage, dict) else None


def coverage_warnings(registry: dict[str, Any]) -> list[str]:
    """Return production warnings only for unresolved relevant notices."""
    return [
        "poll coverage: unresolved relevant Commission notice "
        f"{notice['notice_id']} ({notice.get('title', 'untitled')})"
        for notice in registry.get("notices", [])
        if is_relevant_notice(notice)
        and _interpreted_coverage_state(notice) == "unresolved"
    ]
