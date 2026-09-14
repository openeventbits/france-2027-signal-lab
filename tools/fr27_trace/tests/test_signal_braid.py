from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess

import pytest

from candidate_agenda_history_contract import (
    CAMPAIGN_TAXONOMY,
    METHODOLOGY as AGENDA_METHODOLOGY,
    POLICY_TAXONOMY,
)
from candidate_attention_contract import (
    METHODOLOGY_INTERPRETATION,
    METHODOLOGY_LABEL,
    METHODOLOGY_NOT_MEASURES,
    METHODOLOGY_REDIRECT_LIMITATION,
    METHODOLOGY_WEEKLY_COMPARISON,
)
from candidate_visibility_history_contract import (
    METHODOLOGY_CANDIDATE_LINKAGE,
    METHODOLOGY_METRIC,
    METHODOLOGY_SOURCE,
    NOT_MEASURES,
    PRIMARY_SCOPES,
    round_visibility_ratio,
)

TRACE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TRACE_ROOT.parents[1]
FIXTURE = TRACE_ROOT / "fixtures" / "signal_braid_candidate_v1.json"
COVERAGE_FIXTURE = TRACE_ROOT / "fixtures" / "coverage_anatomy_candidate_v1.json"

CANDIDATE_ID = "synthetic-candidate-alpha"
CANDIDATE_NAME = "Synthetic Candidate Alpha"
WINDOW_START = date(2026, 8, 4)
WINDOW_END = date(2026, 8, 31)

MEDIA_COUNTS = [
    0, 1, 0, 2, 1, 0, 1, 2, 0, 1, 0, 1, 2, 0,
    10, 12, 14, 16, 18, 15, 15,
    30, 10, 20, 5, 15, 10, 10,
]
WIKIPEDIA_VIEWS = [800] * 14 + [1000] * 7 + [600, 600, 600, 5000, 600, 600, 600]


def setUpModule() -> None:
    global FLASH_FINDINGS, SUPPRESSION_INSUFFICIENT_COVERAGE
    global SUPPRESSION_NO_COMMON_WINDOW, SUPPRESSION_NO_QUALIFYING_SIGNAL
    global RenderModelError, SignalBraidError, TraceRenderModel, build_draft_trace
    global frozen_interpretation_flag, live_smoke_summary, percentage_change
    global select_signal_braid, validate_signal_braid_evidence, validate_trace

    from tools.fr27_trace import build_draft_trace as draft_builder
    from tools.fr27_trace import validate_trace as trace_validator
    from tools.fr27_trace.flash_shift import (
        frozen_interpretation_flag as classifier,
        percentage_change as change_calculator,
    )
    from tools.fr27_trace.render import (
        RenderModelError as render_error,
        TraceRenderModel as render_model,
    )
    from tools.fr27_trace.signal_braid import (
        FLASH_FINDINGS as finding_map,
        SUPPRESSION_INSUFFICIENT_COVERAGE as insufficient_code,
        SUPPRESSION_NO_COMMON_WINDOW as no_window_code,
        SUPPRESSION_NO_QUALIFYING_SIGNAL as no_signal_code,
        SignalBraidError as selection_error,
        live_smoke_summary as smoke_summary,
        select_signal_braid as selector,
        validate_signal_braid_evidence as evidence_validator,
    )

    FLASH_FINDINGS = finding_map
    SUPPRESSION_INSUFFICIENT_COVERAGE = insufficient_code
    SUPPRESSION_NO_COMMON_WINDOW = no_window_code
    SUPPRESSION_NO_QUALIFYING_SIGNAL = no_signal_code
    SignalBraidError = selection_error
    RenderModelError = render_error
    TraceRenderModel = render_model
    build_draft_trace = draft_builder
    frozen_interpretation_flag = classifier
    live_smoke_summary = smoke_summary
    percentage_change = change_calculator
    select_signal_braid = selector
    validate_signal_braid_evidence = evidence_validator
    validate_trace = trace_validator


def _dates(start: date, count: int) -> list[str]:
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _media_payload(counts: list[int] = MEDIA_COUNTS) -> dict:
    source_dates = _dates(WINDOW_START - timedelta(days=1), 29)
    source_counts = [0, *counts]
    campaign_denominators = []
    campaign_series = []
    general_denominators = []
    general_series = []
    for day, count in zip(source_dates, source_counts, strict=True):
        denominator = max(1, count + 1)
        campaign_denominators.append(
            {"date": day, "record_count": denominator, "publisher_count": denominator}
        )
        campaign_series.append(
            {
                "date": day,
                "record_count": count,
                "share": round_visibility_ratio(count / denominator),
                "publisher_count": min(count, 1),
            }
        )
        general_denominators.append(
            {"date": day, "record_count": 0, "publisher_count": 0}
        )
        general_series.append(
            {"date": day, "record_count": 0, "share": None, "publisher_count": 0}
        )
    return {
        "schema_version": "1.0",
        "period": {
            "start_date": source_dates[0],
            "end_date": source_dates[-1],
            "days": 29,
            "data_as_of": source_dates[-1],
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "methodology": {
            "source": METHODOLOGY_SOURCE,
            "primary_scopes": list(PRIMARY_SCOPES),
            "general_scope": "general",
            "metric": METHODOLOGY_METRIC,
            "candidate_linkage": METHODOLOGY_CANDIDATE_LINKAGE,
            "not_measures": list(NOT_MEASURES),
        },
        "lanes": {
            "campaign_attention": {"daily_denominators": campaign_denominators},
            "general_visibility": {"daily_denominators": general_denominators},
        },
        "candidates": [
            {
                "candidate_id": CANDIDATE_ID,
                "candidate_name": CANDIDATE_NAME,
                "campaign_attention": {"daily_series": campaign_series},
                "general_visibility": {"daily_series": general_series},
            }
        ],
    }


def _metric_values(series: list[dict]) -> dict:
    latest_7 = series[-7:]
    previous_7 = series[-14:-7]
    latest_28 = series[-28:]
    previous_28 = series[-56:-28]
    latest_total = sum(day["views"] for day in latest_7)
    previous_total = sum(day["views"] for day in previous_7)
    latest_28_total = sum(day["views"] for day in latest_28)
    previous_28_total = sum(day["views"] for day in previous_28)
    latest_peak = max(latest_7, key=lambda day: day["views"])
    previous_peak = max(previous_7, key=lambda day: day["views"])
    period_peak = max(series, key=lambda day: day["views"])
    return {
        "latest_7_views": latest_total,
        "previous_7_views": previous_total,
        "change_7_pct": percentage_change(latest_total, previous_total),
        "latest_28_views": latest_28_total,
        "previous_28_views": previous_28_total,
        "change_28_pct": percentage_change(latest_28_total, previous_28_total),
        "latest_7_peak_date": latest_peak["date"],
        "latest_7_peak_views": latest_peak["views"],
        "latest_7_peak_share": round(latest_peak["views"] / latest_total, 4),
        "change_7_peak_removed_pct": percentage_change(
            latest_total - latest_peak["views"],
            previous_total - previous_peak["views"],
        ),
        "period_peak_date": period_peak["date"],
        "period_peak_views": period_peak["views"],
    }


def _observed_attention_candidate(views: list[int]) -> dict:
    dates = _dates(WINDOW_END - timedelta(days=89), 90)
    full_views = [700] * 62 + views
    series = [
        {"date": day, "views": value}
        for day, value in zip(dates, full_views, strict=True)
    ]
    metrics = _metric_values(series)
    flag = frozen_interpretation_flag(
        {
            "latest_7_views": metrics["latest_7_views"],
            "change_7_pct": metrics["change_7_pct"],
            "latest_7_peak_share": metrics["latest_7_peak_share"],
            "change_7_peak_removed_pct": metrics["change_7_peak_removed_pct"],
        }
    )
    return {
        "candidate_id": CANDIDATE_ID,
        "candidate_name": CANDIDATE_NAME,
        "evidence_state": "observed",
        "wikipedia_article": {
            "page_id": 1001,
            "title": CANDIDATE_NAME,
            "url": "https://fr.wikipedia.org/wiki/Synthetic_Candidate_Alpha",
        },
        **metrics,
        "interpretation_flag": flag,
        "daily_series": series,
    }


def _unavailable_attention_candidate() -> dict:
    metrics = {
        key: None
        for key in (
            "latest_7_views", "previous_7_views", "change_7_pct",
            "latest_28_views", "previous_28_views", "change_28_pct",
            "latest_7_peak_date", "latest_7_peak_views", "latest_7_peak_share",
            "change_7_peak_removed_pct", "period_peak_date", "period_peak_views",
        )
    }
    return {
        "candidate_id": CANDIDATE_ID,
        "candidate_name": CANDIDATE_NAME,
        "evidence_state": "unavailable_no_personal_article",
        "wikipedia_article": None,
        **metrics,
        "interpretation_flag": None,
        "daily_series": [],
    }


def _attention_payload(
    *,
    views: list[int] = WIKIPEDIA_VIEWS,
    unavailable: bool = False,
) -> dict:
    candidate = (
        _unavailable_attention_candidate()
        if unavailable
        else _observed_attention_candidate(views)
    )
    observed_count = int(not unavailable)
    return {
        "schema_version": "1.1",
        "generated_at": "2026-09-01T09:00:00Z",
        "source": {
            "project": "fr.wikipedia.org",
            "api": "Wikimedia Analytics API",
            "metric": "pageviews",
            "access": "all-access",
            "agent": "user",
            "granularity": "daily",
        },
        "period": {
            "start_date": (WINDOW_END - timedelta(days=89)).isoformat(),
            "end_date": WINDOW_END.isoformat(),
            "days": 90,
            "data_as_of": WINDOW_END.isoformat(),
        },
        "candidate_universe": {
            "source": "candidate_candidacy_status.json",
            "source_revision_id": 1,
            "source_revision_timestamp": "2026-09-01T08:00:00Z",
            "status_as_of": "2026-09-01",
            "rule": "active_monitoring_field",
            "count": 1,
            "article_eligible_count": observed_count,
            "unavailable_no_personal_article_count": 1 - observed_count,
        },
        "methodology": {
            "label": METHODOLOGY_LABEL,
            "interpretation": METHODOLOGY_INTERPRETATION,
            "not_measures": list(METHODOLOGY_NOT_MEASURES),
            "weekly_comparison": METHODOLOGY_WEEKLY_COMPARISON,
            "redirect_limitation": METHODOLOGY_REDIRECT_LIMITATION,
        },
        "validation": {
            "status": "pass",
            "candidate_count": 1,
            "observed_candidate_count": observed_count,
            "unavailable_candidate_count": 1 - observed_count,
            "expected_days_per_observed_candidate": 90,
            "missing_dates": 0,
            "duplicate_dates": 0,
        },
        "candidates": [candidate],
    }


def _agenda_payload(*, tracking_start: date = date(2026, 8, 3)) -> dict:
    data_as_of = date(2026, 9, 1)
    policy_ids = [topic_id for topic_id, _label in POLICY_TAXONOMY]
    campaign_ids = [topic_id for topic_id, _label in CAMPAIGN_TAXONOMY]
    observations = {
        "2026-08-18": {"campaign": {"candidacies_endorsements": 2}},
        "2026-08-20": {"policy": {"immigration_identity_secularism": 1}},
        "2026-08-25": {"policy": {"work_purchasing_power_pensions": 2}},
        "2026-08-28": {
            "policy": {"security_justice": 1},
            "campaign": {"selection_strategy": 1},
        },
        "2026-08-31": {"policy": {"europe_defence_foreign_affairs": 1}},
    }
    series = []
    policy_totals = dict.fromkeys(policy_ids, 0)
    campaign_totals = dict.fromkeys(campaign_ids, 0)
    for day in _dates(tracking_start, (data_as_of - tracking_start).days + 1):
        policy_counts = dict.fromkeys(policy_ids, 0)
        campaign_counts = dict.fromkeys(campaign_ids, 0)
        selected = observations.get(day, {})
        policy_counts.update(selected.get("policy", {}))
        campaign_counts.update(selected.get("campaign", {}))
        for topic_id, count in policy_counts.items():
            policy_totals[topic_id] += count
        for topic_id, count in campaign_counts.items():
            campaign_totals[topic_id] += count
        series.append(
            {
                "date": day,
                "policy_counts": policy_counts,
                "campaign_counts": campaign_counts,
            }
        )
    use_policy = sum(value > 0 for value in policy_totals.values()) >= 3
    taxonomy = POLICY_TAXONOMY if use_policy else CAMPAIGN_TAXONOMY
    totals = policy_totals if use_policy else campaign_totals
    total = sum(totals.values())
    profile = {
        "profile_mode": "policy" if use_policy else "campaign",
        "period_start": tracking_start.isoformat(),
        "period_end": data_as_of.isoformat(),
        "day_count": len(series),
        "association_count": total,
        "topics": [
            {
                "id": topic_id,
                "label": label,
                "count": totals[topic_id],
                "share": round(totals[topic_id] / total, 6) if total else 0.0,
            }
            for topic_id, label in taxonomy
        ],
    }
    return {
        "schema_version": "1.0",
        "tracking": {
            "start_date": tracking_start.isoformat(),
            "data_as_of": data_as_of.isoformat(),
            "day_boundary": "UTC",
            "current_utc_day_excluded": False,
        },
        "methodology": deepcopy(AGENDA_METHODOLOGY),
        "taxonomies": {
            "policy": [{"id": key, "label": label} for key, label in POLICY_TAXONOMY],
            "campaign": [{"id": key, "label": label} for key, label in CAMPAIGN_TAXONOMY],
        },
        "candidates": [
            {
                "candidate_id": CANDIDATE_ID,
                "candidate_name": CANDIDATE_NAME,
                "tracking_start": tracking_start.isoformat(),
                "daily_series": series,
                "cumulative_profile": profile,
            }
        ],
    }


def _package(
    *,
    pollster: str = "Synthetic Polling",
    fieldwork_start: str = "2026-08-21",
    fieldwork_end: str = "2026-08-22",
    sample_size: int = 1000,
    hypothesis_count: int = 2,
) -> dict:
    key = json.dumps(
        [pollster, fieldwork_start, fieldwork_end, sample_size],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "package_key": key,
        "pollster": pollster,
        "fieldwork_start": fieldwork_start,
        "fieldwork_end": fieldwork_end,
        "sample_size": sample_size,
        "hypothesis_count": hypothesis_count,
        "hypotheses": [
            {"candidate_id": CANDIDATE_ID, "scenario": "A"},
            {"candidate_id": CANDIDATE_ID, "scenario": "B"},
        ],
        "candidate_score": 99.9,
        "source_urls": ["https://example.test/not-identity-material"],
    }


def _candidate_signals(*, packages: list[dict] | None = None) -> dict:
    if packages is None:
        packages = [_package()]
    return {
        "schema_version": "1.5",
        "generated_at": "2026-09-01T09:00:00Z",
        "candidates": [
            {
                "candidate_id": CANDIDATE_ID,
                "candidate_name": CANDIDATE_NAME,
                "poll_history": {
                    "evidence_state": "reported" if packages else "not_observed",
                    "observation_count": len(packages),
                    "period_start": (
                        min(package["fieldwork_start"] for package in packages)
                        if packages
                        else None
                    ),
                    "period_end": (
                        max(package["fieldwork_end"] for package in packages)
                        if packages
                        else None
                    ),
                    "observations": packages,
                },
            },
            {
                "candidate_id": "unrelated-candidate",
                "candidate_name": "Unrelated Candidate",
                    "poll_history": {
                        "evidence_state": "reported",
                        "observation_count": 1,
                        "period_start": "2026-08-21",
                        "period_end": "2026-08-22",
                        "observations": [
                        _package(pollster="Unrelated Pollster", hypothesis_count=7)
                    ],
                },
            },
        ],
    }


def _sources(
    *,
    views: list[int] = WIKIPEDIA_VIEWS,
    wikipedia_unavailable: bool = False,
    agenda_tracking_start: date = date(2026, 8, 3),
    packages: list[dict] | None = None,
) -> tuple[dict, dict, dict, dict]:
    return (
        _media_payload(),
        _attention_payload(views=views, unavailable=wikipedia_unavailable),
        _agenda_payload(tracking_start=agenda_tracking_start),
        _candidate_signals(packages=packages),
    )


def _select(*sources: dict, coverage_child: dict | None = None):
    return select_signal_braid(
        *sources,
        CANDIDATE_ID,
        controlled_candidates=[{"id": CANDIDATE_ID, "name": CANDIDATE_NAME}],
        coverage_child=coverage_child,
        current_utc_date=date(2026, 9, 1),
    )


def synthetic_document() -> dict:
    selection = _select(*_sources())
    trace = selection.build_trace()
    assert trace is not None
    return {
        "trace": trace,
        "presentation": {
            "language": "en",
            "display_label": CANDIDATE_NAME,
            "finding": FLASH_FINDINGS["event_amplified"],
            "qualifier": "Also tested in 1 accepted first-round poll package this window.",
            "source_scope": "FR27 CANDIDATE-LINKED NEWS · WIKIPEDIA · FIRST-ROUND POLL PACKAGES",
            "methodological_boundary": "SEPARATE LANES · NO COMBINED SCALE, SUPPORT MEASURE OR CAUSAL CLAIM",
            "observation_window_display": "04 AUG — 31 AUG 2026 · UTC",
            "renderer_version": "trace-shell.v1",
            "field_type": "signal_braid",
        },
    }


def live_shaped_agenda_document() -> dict:
    document = synthetic_document()
    original = document["trace"]
    evidence = deepcopy(original["evidence"])
    day = next(
        row for row in evidence["agenda"]["days"] if row["date"] == "2026-08-28"
    )
    day["value"]["policy_counts"][:4] = [1, 2, 3, 4]
    day["value"]["campaign_counts"][:4] = [4, 3, 2, 1]
    document["trace"] = build_draft_trace(
        family=original["family"],
        detector_id=original["detector_id"],
        primary_entity_ids=original["primary_entity_ids"],
        observation_window=original["observation_window"],
        evidence=evidence,
    )
    return document


class TestSignalBraidSelection:
    def test_primary_fixture_arithmetic_and_semantics(self) -> None:
        selection = _select(*_sources())
        assert selection.eligible
        assert selection.observation_window == {"start": "2026-08-04", "end": "2026-08-31"}
        evidence = selection.evidence
        assert evidence is not None
        assert len(evidence["media"]["series"]["value"]) == 28
        assert sum(row["record_count"]["value"] for row in evidence["media"]["series"]["value"]) == 211
        assert evidence["media"]["series"]["value"][0]["record_count"] == {
            "availability": "observed", "unit": "candidate_linked_records", "value": 0
        }
        assert sum(row["views"]["value"] for row in evidence["wikipedia"]["series"]["value"]) == 26800
        assert selection.flash_classification == "event_amplified"
        assert selection.finding == "WIKIPEDIA ATTENTION SHOWED A FLASH PATTERN."

    def test_calendar_is_exact_closed_28_complete_utc_days(self) -> None:
        selection = _select(*_sources())
        calendar = selection.evidence["calendar"]["value"]
        assert calendar == {
            "timezone": "UTC",
            "start": "2026-08-04",
            "end": "2026-08-31",
            "days": 28,
            "inclusive": True,
            "current_utc_day_excluded": True,
        }
        assert selection.evidence["agenda"]["days"][-1]["date"] == "2026-08-31"

    def test_wikipedia_raw_slice_and_flash_child_are_distinct(self) -> None:
        selection = _select(*_sources())
        evidence = selection.evidence
        assert [row["views"]["value"] for row in evidence["wikipedia"]["series"]["value"]] == WIKIPEDIA_VIEWS
        child = evidence["annotations"]["flash_shift"]["value"]
        assert child["detector_id"] == "flash_shift.v1"
        assert child["classification"] == "event_amplified"
        assert child["observation_window"] == {"start": "2026-08-18", "end": "2026-08-31"}
        assert set(child) == {"detector_id", "trace_key", "observation_window", "classification"}

    def test_wikipedia_unavailable_is_preserved_and_poll_can_qualify(self) -> None:
        selection = _select(*_sources(wikipedia_unavailable=True))
        assert selection.eligible
        assert selection.evidence["wikipedia"]["series"] == {
            "availability": "unavailable",
            "unit": "pageviews_daily",
            "reason": "unavailable_no_personal_article",
        }
        assert "flash_shift" not in selection.evidence["annotations"]
        assert selection.finding == "TESTED IN 1 FIRST-ROUND POLL PACKAGE THIS WINDOW."

    def test_agenda_taxonomies_zeros_and_tracking_start(self) -> None:
        selection = _select(*_sources())
        agenda = selection.evidence["agenda"]
        assert agenda["semantics"]["value"]["policy_topic_ids"] == [key for key, _ in POLICY_TAXONOMY]
        assert agenda["semantics"]["value"]["campaign_topic_ids"] == [key for key, _ in CAMPAIGN_TAXONOMY]
        first = agenda["days"][0]
        assert first["availability"] == "observed"
        assert set(first["value"]) == {"policy_counts", "campaign_counts"}
        assert all(count == 0 for count in first["value"]["policy_counts"])
        august_28 = next(row for row in agenda["days"] if row["date"] == "2026-08-28")
        assert august_28["value"]["policy_counts"][3] == 1
        assert august_28["value"]["campaign_counts"][1] == 1

    def test_agenda_pretracking_dates_are_not_observed_not_zero(self) -> None:
        selection = _select(
            *_sources(
                wikipedia_unavailable=True,
                agenda_tracking_start=date(2026, 8, 18),
            )
        )
        assert selection.status == "suppressed"
        assert selection.suppression_reason == SUPPRESSION_INSUFFICIENT_COVERAGE
        assert selection.evidence["agenda"]["days"][0] == {
            "date": "2026-08-04",
            "availability": "not_observed",
            "reason": "date_precedes_tracking_start",
        }

    def test_poll_hypotheses_are_one_package_interval_with_end_qualification(self) -> None:
        sources = _sources()
        assert len(sources[3]["candidates"][0]["poll_history"]["observations"][0]["hypotheses"]) == 2
        selection = _select(*sources)
        poll_tests = selection.evidence["poll_tests"]
        assert poll_tests["availability"] == "observed"
        assert len(poll_tests["value"]) == 1
        assert poll_tests["value"][0]["hypothesis_count"] == 2
        assert poll_tests["value"][0]["fieldwork_start"] == "2026-08-21"
        assert poll_tests["value"][0]["fieldwork_end"] == "2026-08-22"
        assert set(poll_tests["value"][0]) == {
            "package_key", "pollster", "fieldwork_start", "fieldwork_end",
            "sample_size", "hypothesis_count",
        }

    def test_poll_package_ending_outside_window_is_not_selected(self) -> None:
        outside = _package(fieldwork_start="2026-08-30", fieldwork_end="2026-09-01")
        selection = _select(*_sources(packages=[outside]))
        assert selection.eligible  # eligible Flash/Shift still qualifies
        assert selection.evidence["poll_tests"]["availability"] == "not_observed"

    def test_semantically_duplicate_poll_key_spellings_collapse_once(self) -> None:
        canonical = _package()
        alternate = deepcopy(canonical)
        alternate["package_key"] = json.dumps(
            [
                alternate["pollster"],
                alternate["fieldwork_start"],
                alternate["fieldwork_end"],
                alternate["sample_size"],
            ],
            ensure_ascii=False,
        )
        selection = _select(*_sources(packages=[canonical, alternate]))
        packages = selection.evidence["poll_tests"]["value"]
        assert len(packages) == 1
        assert packages[0]["package_key"] == canonical["package_key"]

    def test_conflicting_semantic_poll_duplicate_fails_closed(self) -> None:
        canonical = _package()
        conflict = deepcopy(canonical)
        conflict["package_key"] = json.dumps(
            [
                conflict["pollster"],
                conflict["fieldwork_start"],
                conflict["fieldwork_end"],
                conflict["sample_size"],
            ]
        )
        conflict["hypothesis_count"] = 3
        with pytest.raises(SignalBraidError, match="conflicting facts"):
            _select(*_sources(packages=[canonical, conflict]))

    def test_poll_boundaries_and_order_are_semantic_not_input_order(self) -> None:
        packages = [
            _package(
                pollster="Window end",
                fieldwork_start="2026-08-30",
                fieldwork_end="2026-08-31",
            ),
            _package(
                pollster="Window start",
                fieldwork_start="2026-08-01",
                fieldwork_end="2026-08-04",
            ),
            _package(
                pollster="Before window",
                fieldwork_start="2026-08-01",
                fieldwork_end="2026-08-03",
            ),
        ]
        first = _select(*_sources(packages=packages)).build_trace()
        second = _select(*_sources(packages=list(reversed(packages)))).build_trace()
        assert first["trace_key"] == second["trace_key"]
        selected = first["evidence"]["poll_tests"]["value"]
        assert [package["pollster"] for package in selected] == [
            "Window start",
            "Window end",
        ]

    def test_poll_history_period_must_match_observations(self) -> None:
        sources = list(_sources())
        sources[3]["candidates"][0]["poll_history"]["period_start"] = "2026-08-20"
        with pytest.raises(SignalBraidError, match="period does not match"):
            _select(*sources)

    def test_unknown_or_fuzzy_candidate_id_is_error(self) -> None:
        with pytest.raises(SignalBraidError, match="unknown canonical candidate id"):
            select_signal_braid(
                *_sources(),
                "synthetic-candidate",
                controlled_candidates=[{"id": CANDIDATE_ID, "name": CANDIDATE_NAME}],
            )

    def test_malformed_candidate_id_errors_before_suppression(self) -> None:
        with pytest.raises(SignalBraidError, match="canonical lowercase FR27 ID"):
            select_signal_braid(
                *_sources(),
                "Bad ID",
                controlled_candidates=[{"id": "Bad ID", "name": CANDIDATE_NAME}],
                current_utc_date=date(2026, 8, 31),
            )

    def test_current_utc_date_is_a_fail_closed_validation_boundary(self) -> None:
        yesterday = _select(*_sources())
        assert yesterday.observation_window["end"] == "2026-08-31"
        for current_day in (date(2026, 8, 31), date(2026, 8, 30)):
            with pytest.raises(SignalBraidError, match="precede the current UTC"):
                select_signal_braid(
                    *_sources(),
                    CANDIDATE_ID,
                    controlled_candidates=[{"id": CANDIDATE_ID, "name": CANDIDATE_NAME}],
                    current_utc_date=current_day,
                )
        selected_dates = [
            day["date"] for day in yesterday.evidence["agenda"]["days"]
        ]
        assert "2026-09-01" not in selected_dates

    def test_malformed_source_and_arithmetic_inconsistency_are_errors(self) -> None:
        sources = list(_sources())
        sources[0]["candidates"][0]["campaign_attention"]["daily_series"].pop()
        with pytest.raises(SignalBraidError, match="malformed production source"):
            _select(*sources)
        sources = list(_sources())
        sources[3]["candidates"][0]["poll_history"]["observation_count"] = 7
        with pytest.raises(SignalBraidError, match="observation_count is inconsistent"):
            _select(*sources)

    def test_all_three_suppression_codes(self) -> None:
        stable = [800] * 28
        no_trigger = _select(*_sources(views=stable, packages=[]))
        assert no_trigger.suppression_reason == SUPPRESSION_NO_QUALIFYING_SIGNAL

        insufficient = _select(
            *_sources(
                wikipedia_unavailable=True,
                agenda_tracking_start=date(2026, 8, 18),
            )
        )
        assert insufficient.suppression_reason == SUPPRESSION_INSUFFICIENT_COVERAGE

        sources = list(_sources())
        sources[2] = _agenda_payload(tracking_start=date(2026, 9, 1))
        no_window = _select(*sources)
        assert no_window.suppression_reason == SUPPRESSION_NO_COMMON_WINDOW
        assert no_window.evidence is None

    def test_stable_flash_is_suppressed_without_removing_wikipedia_lane(self) -> None:
        selection = _select(*_sources(views=[800] * 28))
        assert selection.eligible
        assert selection.flash_status == "suppressed"
        assert "flash_shift" not in selection.evidence["annotations"]
        assert selection.evidence["wikipedia"]["series"]["availability"] == "observed"
        assert selection.finding == "TESTED IN 1 FIRST-ROUND POLL PACKAGE THIS WINDOW."

    def test_no_new_cross_lane_metric_or_poll_score_enters_evidence(self) -> None:
        serialized = json.dumps(_select(*_sources()).evidence, sort_keys=True)
        for forbidden in (
            "candidate_score", "correlation", "momentum", "rank", "trend",
            "publisher_count", "general_visibility", "leading_topic",
        ):
            assert forbidden not in serialized


class TestSignalBraidIdentityAndChildren:
    def _coverage_document(self) -> dict:
        return json.loads(COVERAGE_FIXTURE.read_text(encoding="utf-8"))

    def test_compatible_coverage_child_attaches_as_narrow_reference(self) -> None:
        selection = _select(*_sources(), coverage_child=self._coverage_document())
        child = selection.evidence["annotations"]["coverage_anatomy"]["value"]
        assert selection.coverage_status == "compatible"
        assert set(child) == {"detector_id", "trace_key", "observation_window"}
        assert child["observation_window"] == {"start": "2026-08-18", "end": "2026-08-31"}

    def test_coverage_candidate_mismatch_is_error(self) -> None:
        document = self._coverage_document()
        trace = build_draft_trace(
            family="candidate",
            detector_id="coverage_anatomy.v1",
            primary_entity_ids=["different-candidate"],
            observation_window=document["trace"]["observation_window"],
            evidence=document["trace"]["evidence"],
        )
        with pytest.raises(SignalBraidError, match="candidate does not match"):
            _select(*_sources(), coverage_child=trace)

    def test_malformed_coverage_child_is_error_not_incompatible(self) -> None:
        malformed = {"trace": {"family": "candidate", "detector_id": "coverage_anatomy.v1"}}
        with pytest.raises(SignalBraidError, match="invalid Coverage Anatomy child"):
            _select(*_sources(), coverage_child=malformed)

    def test_valid_coverage_window_outside_parent_is_incompatible(self) -> None:
        document = self._coverage_document()
        evidence = deepcopy(document["trace"]["evidence"])
        evidence["prior_period"]["start"] = "2026-08-19"
        evidence["prior_period"]["end"] = "2026-08-25"
        evidence["current_period"]["start"] = "2026-08-26"
        evidence["current_period"]["end"] = "2026-09-01"
        trace = build_draft_trace(
            family="candidate",
            detector_id="coverage_anatomy.v1",
            primary_entity_ids=[CANDIDATE_ID],
            observation_window={"start": "2026-08-19", "end": "2026-09-01"},
            evidence=evidence,
        )
        selection = _select(*_sources(), coverage_child=trace)
        assert selection.coverage_status == "incompatible"
        assert "coverage_anatomy" not in selection.evidence["annotations"]

    def test_child_presentation_is_not_identity_material(self) -> None:
        child = self._coverage_document()
        changed = deepcopy(child)
        changed["presentation"]["finding"] = "COMPLETELY DIFFERENT PRESENTATION COPY."
        first = _select(*_sources(), coverage_child=child).build_trace()
        second = _select(*_sources(), coverage_child=changed).build_trace()
        assert first["trace_key"] == second["trace_key"]

    def test_selected_material_child_key_is_identity_material(self) -> None:
        child = self._coverage_document()
        evidence = deepcopy(child["trace"]["evidence"])
        current = evidence["current_period"]["candidate_metrics"]
        current["leading_publisher_record_count"]["value"] = 25
        current["leading_publisher_share"]["value"] = 0.25
        changed_trace = build_draft_trace(
            family="candidate",
            detector_id="coverage_anatomy.v1",
            primary_entity_ids=[CANDIDATE_ID],
            observation_window=child["trace"]["observation_window"],
            evidence=evidence,
        )
        first = _select(*_sources(), coverage_child=child).build_trace()
        second = _select(*_sources(), coverage_child=changed_trace).build_trace()
        assert child["trace"]["trace_key"] != changed_trace["trace_key"]
        assert first["trace_key"] != second["trace_key"]

    def test_unrelated_candidate_and_unused_payload_do_not_affect_identity(self) -> None:
        sources = list(_sources())
        first = _select(*sources).build_trace()
        changed = deepcopy(sources)
        changed[3]["generated_at"] = "2099-01-01T00:00:00Z"
        changed[3]["candidates"][1]["poll_history"]["observations"][0]["candidate_score"] = 0
        changed[3]["candidates"][0]["poll_history"]["observations"][0]["source_urls"] = ["https://changed.test"]
        second = _select(*changed).build_trace()
        assert first["trace_key"] == second["trace_key"]

    def test_unused_historical_dates_and_suppressed_child_metadata_do_not_affect_identity(self) -> None:
        sources = list(_sources(views=[800] * 28))
        first = _select(*sources).build_trace()
        changed = deepcopy(sources)
        changed[1]["generated_at"] = "2026-09-01T10:00:00Z"
        changed[1]["candidates"][0]["wikipedia_article"]["url"] = "https://fr.wikipedia.org/wiki/Changed"
        for row in changed[1]["candidates"][0]["daily_series"][:62]:
            row["views"] = 701
        candidate = changed[1]["candidates"][0]
        candidate.update(_metric_values(candidate["daily_series"]))
        candidate["interpretation_flag"] = frozen_interpretation_flag(
            {
                "latest_7_views": candidate["latest_7_views"],
                "change_7_pct": candidate["change_7_pct"],
                "latest_7_peak_share": candidate["latest_7_peak_share"],
                "change_7_peak_removed_pct": candidate["change_7_peak_removed_pct"],
            }
        )
        second = _select(*changed).build_trace()
        assert "flash_shift" not in first["evidence"]["annotations"]
        assert "flash_shift" not in second["evidence"]["annotations"]
        assert first["trace_key"] == second["trace_key"]

    def test_source_candidate_display_name_is_not_identity_material(self) -> None:
        sources = list(_sources())
        first = _select(*sources).build_trace()
        changed_name = "Alternate Display Name"
        for payload in sources:
            for candidate in payload["candidates"]:
                if candidate.get("candidate_id") == CANDIDATE_ID:
                    candidate["candidate_name"] = changed_name
        sources[1]["candidates"][0]["wikipedia_article"]["title"] = changed_name
        second_selection = select_signal_braid(
            *sources,
            CANDIDATE_ID,
            controlled_candidates=[{"id": CANDIDATE_ID, "name": changed_name}],
            current_utc_date=date(2026, 9, 1),
        )
        assert first["trace_key"] == second_selection.build_trace()["trace_key"]

    def test_material_parent_lane_change_changes_identity(self) -> None:
        first = _select(*_sources()).build_trace()
        sources = list(_sources())
        media_rows = sources[0]["candidates"][0]["campaign_attention"]["daily_series"]
        denominator_rows = sources[0]["lanes"]["campaign_attention"]["daily_denominators"]
        media_rows[1]["record_count"] = 1
        media_rows[1]["publisher_count"] = 1
        media_rows[1]["share"] = round_visibility_ratio(1 / denominator_rows[1]["record_count"])
        second = _select(*sources).build_trace()
        assert first["trace_key"] != second["trace_key"]

    def test_material_poll_hypothesis_count_changes_identity(self) -> None:
        first = _select(*_sources()).build_trace()
        changed_package = _package(hypothesis_count=3)
        second = _select(*_sources(packages=[changed_package])).build_trace()
        assert first["trace_key"] != second["trace_key"]

    def test_display_name_and_render_language_are_not_identity_material(self) -> None:
        document = synthetic_document()
        changed = deepcopy(document)
        changed["presentation"]["language"] = "fr"
        changed["presentation"]["display_label"] = "Candidat synthétique"
        assert document["trace"]["trace_key"] == changed["trace"]["trace_key"]
        assert TraceRenderModel.from_document(changed).trace["trace_key"] == document["trace"]["trace_key"]

    def test_frozen_synthetic_identity_is_preserved(self) -> None:
        assert synthetic_document()["trace"]["trace_key"] == (
            "trace_dcd4837fb3bb91b4165ed57770ce815d04ef6f15e6425536a13fdefa9168465c"
        )


class TestSignalBraidRenderer:
    def test_frozen_fixture_matches_selected_trace_and_validates(self) -> None:
        frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert frozen == synthetic_document()
        validate_trace(frozen["trace"])
        validate_signal_braid_evidence(
            frozen["trace"]["evidence"],
            observation_window=frozen["trace"]["observation_window"],
        )
        assert "coverage_anatomy" not in frozen["trace"]["evidence"]["annotations"]

    def test_renderer_has_exact_four_structural_lanes(self) -> None:
        payload = TraceRenderModel.from_document(synthetic_document()).to_payload()
        assert payload["fieldType"] == "signal_braid"
        assert set(payload["field"]) == {
            "componentLabel", "calendarLabel", "ticks", "media", "wikipedia",
            "agenda", "pollTests",
        }
        assert [payload["field"][key]["label"] for key in ("media", "wikipedia", "agenda", "pollTests")] == [
            "MEDIA", "WIKIPEDIA", "AGENDA / ISSUES", "POLL TESTS"
        ]

    def test_signal_braid_presentation_window_is_canonical_and_locked(self) -> None:
        document = synthetic_document()
        payload = TraceRenderModel.from_document(document).to_payload()
        assert payload["observationWindow"] == "04 AUG — 31 AUG 2026 · UTC"
        assert payload["field"]["calendarLabel"] == (
            "2026-08-04 — 2026-08-31 · UTC"
        )
        changed = deepcopy(document)
        changed["presentation"]["observation_window_display"] = (
            "01 JAN — 28 JAN 2099 · UTC"
        )
        with pytest.raises(RenderModelError, match="disagrees with canonical window"):
            TraceRenderModel.from_document(changed)

    def test_signal_braid_finding_and_qualifier_are_locked_presentation(self) -> None:
        document = synthetic_document()
        original_key = document["trace"]["trace_key"]
        for field, replacement in (
            ("finding", "MOMENTUM AND SUPPORT STRENGTHENED."),
            ("qualifier", "POPULARITY ROSE BECAUSE OF MEDIA COVERAGE."),
        ):
            changed = deepcopy(document)
            changed["presentation"][field] = replacement
            assert changed["trace"]["trace_key"] == original_key
            with pytest.raises(RenderModelError, match=field):
                TraceRenderModel.from_document(changed)

    def test_rehashed_parent_and_evidence_windows_cannot_disagree(self) -> None:
        document = synthetic_document()
        trace = document["trace"]
        document["trace"] = build_draft_trace(
            family=trace["family"],
            detector_id=trace["detector_id"],
            primary_entity_ids=trace["primary_entity_ids"],
            observation_window={"start": "2026-08-05", "end": "2026-09-01"},
            evidence=trace["evidence"],
        )
        with pytest.raises(RenderModelError, match="calendar disagrees"):
            TraceRenderModel.from_document(document)

    def test_quantitative_lanes_scale_locally(self) -> None:
        field = TraceRenderModel.from_document(synthetic_document()).to_payload()["field"]
        media_heights = [point["heightPercent"] for point in field["media"]["points"]]
        wiki_heights = [point["heightPercent"] for point in field["wikipedia"]["points"]]
        assert max(media_heights) == 100
        assert max(wiki_heights) == 100
        assert field["media"]["unitLabel"] != field["wikipedia"]["unitLabel"]

    def test_agenda_rendering_is_categorical_and_count_does_not_set_height(self) -> None:
        document = synthetic_document()
        field = TraceRenderModel.from_document(document).to_payload()["field"]
        row = next(
            row
            for row in field["agenda"]["rows"]
            if row.get("id") == "work_purchasing_power_pensions"
        )
        mark = next(mark for mark in row["marks"] if mark["date"] == "2026-08-25")
        assert row["code"] == "WORK"
        assert mark["active"] is True
        assert "heightPercent" not in row
        assert "count" not in mark

    def test_live_shaped_simultaneous_agenda_topics_use_distinct_fixed_rows(self) -> None:
        document = live_shaped_agenda_document()
        agenda = TraceRenderModel.from_document(document).to_payload()["field"]["agenda"]
        assert len(agenda["rows"]) == 16
        topic_rows = [row for row in agenda["rows"] if row["kind"] == "topic"]
        assert len(topic_rows) == 14
        active_rows = [
            row["id"]
            for row in topic_rows
            if next(mark for mark in row["marks"] if mark["date"] == "2026-08-28")["active"]
        ]
        assert len(active_rows) == 8
        assert len(set(active_rows)) == 8
        assert all("count" not in row and "heightPercent" not in row for row in topic_rows)

    def test_live_shaped_agenda_passes_headless_clipping_and_alignment_audit(self) -> None:
        payload = TraceRenderModel.from_document(
            live_shaped_agenda_document()
        ).to_payload()
        capture_path = TRACE_ROOT / "render" / "capture.cjs"
        playwright_path = TRACE_ROOT / "node_modules" / "playwright"
        render_root = TRACE_ROOT / "render"
        script = f"""
const fs = require('node:fs');
const path = require('node:path');
const {{ chromium }} = require({json.dumps(str(playwright_path))});
const {{ assertSignalBraidGeometry }} = require({json.dumps(str(capture_path))});
(async () => {{
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const model = JSON.parse(input);
  const root = {json.dumps(str(render_root))};
  const markup = fs.readFileSync(path.join(root, 'shell.html'), 'utf8');
  const styles = fs.readFileSync(path.join(root, 'shell.css'), 'utf8');
  const renderer = fs.readFileSync(path.join(root, 'shell.js'), 'utf8');
  const source = markup.replace('</head>', `<style>${{styles}}</style><script>${{renderer}}</script></head>`);
  const browser = await chromium.launch({{ headless: true }});
  try {{
    const page = await browser.newPage({{ viewport: {{ width: 1280, height: 720 }} }});
    await page.route('**/*', route => route.abort());
    await page.setContent(source, {{ waitUntil: 'load' }});
    await page.evaluate(value => window.renderTraceShell(value), model);
    await assertSignalBraidGeometry(page, model);
    console.log('geometry-ok');
  }} finally {{
    await browser.close();
  }}
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        assert "geometry-ok" in completed.stdout

    def test_agenda_display_label_change_does_not_change_trace_identity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tools.fr27_trace.render.model as render_model_module

        document = synthetic_document()
        trace_key = document["trace"]["trace_key"]
        before = TraceRenderModel.from_document(document).to_payload()["field"]
        monkeypatch.setitem(
            render_model_module._AGENDA_CODES,
            "work_purchasing_power_pensions",
            "WORK / PAY",
        )
        after = TraceRenderModel.from_document(document).to_payload()["field"]
        before_row = next(
            row for row in before["agenda"]["rows"]
            if row.get("id") == "work_purchasing_power_pensions"
        )
        after_row = next(
            row for row in after["agenda"]["rows"]
            if row.get("id") == "work_purchasing_power_pensions"
        )
        assert before_row["code"] == "WORK"
        assert after_row["code"] == "WORK / PAY"
        assert document["trace"]["trace_key"] == trace_key

    def test_poll_fieldwork_interval_and_endpoint_are_preserved(self) -> None:
        field = TraceRenderModel.from_document(synthetic_document()).to_payload()["field"]
        package = field["pollTests"]["packages"][0]
        assert package["fieldworkStart"] == "2026-08-21"
        assert package["fieldworkEnd"] == "2026-08-22"
        assert package["widthPercent"] > 0
        assert package["continuesLeft"] is False

    def test_poll_start_before_parent_is_clipped_with_continuation(self) -> None:
        sources = _sources(packages=[_package(fieldwork_start="2026-08-01", fieldwork_end="2026-08-04")])
        selection = _select(*sources)
        document = synthetic_document()
        document["trace"] = selection.build_trace()
        document["presentation"]["finding"] = selection.finding
        document["presentation"]["qualifier"] = selection.qualifier or None
        field = TraceRenderModel.from_document(document).to_payload()["field"]
        package = field["pollTests"]["packages"][0]
        assert package["leftPercent"] == 0
        assert package["continuesLeft"] is True
        assert package["fieldworkStart"] == "2026-08-01"

    def test_signal_field_uses_no_event_red_or_cross_lane_connector(self) -> None:
        css = (TRACE_ROOT / "render" / "shell.css").read_text(encoding="utf-8")
        signal_css = css.split(".signal-braid-field", 1)[1]
        javascript = (TRACE_ROOT / "render" / "shell.js").read_text(encoding="utf-8")
        assert "event-red" not in signal_css
        assert "causal-connector" not in javascript
        assert "candidate-color" not in signal_css


def test_live_edouard_philippe_smoke() -> None:
    summary = live_smoke_summary("edouard-philippe")
    assert summary["candidate_id"] == "edouard-philippe"
    assert summary["common_window"] == {"start": "2026-08-16", "end": "2026-09-12"}
    assert summary["status"] == "eligible"
    assert summary["flash_shift"] == {"status": "eligible", "classification": "sustained_decline"}
    assert summary["coverage_anatomy"] == "incompatible"
    assert summary["finding"] == "WIKIPEDIA ATTENTION SHOWED A SHIFT · DECLINE PATTERN."
    assert summary["media_28_day_total"] >= 0
    assert summary["wikipedia_28_day_total"] is None or summary["wikipedia_28_day_total"] >= 0
    assert summary["agenda_observed_day_count"] == 28
    assert summary["poll_package_count"] >= 1
