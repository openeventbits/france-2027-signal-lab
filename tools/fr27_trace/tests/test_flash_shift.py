from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from candidate_attention_contract import (
    METHODOLOGY_INTERPRETATION,
    METHODOLOGY_LABEL,
    METHODOLOGY_NOT_MEASURES,
    METHODOLOGY_REDIRECT_LIMITATION,
    METHODOLOGY_WEEKLY_COMPARISON,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TRACE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = TRACE_ROOT / "fixtures" / "flash_shift_candidate_v1.json"
sys.path.insert(0, str(REPOSITORY_ROOT))


def setUpModule() -> None:
    global FlashShiftError, TraceRenderModel, build_draft_trace
    global extract_live_flash_shift, flash_module, frozen_interpretation_flag
    global percentage_change, select_flash_shift, validate_flash_shift_evidence
    global validate_trace
    import tools.fr27_trace.flash_shift as module
    from tools.fr27_trace import build_draft_trace as draft_builder
    from tools.fr27_trace import validate_trace as trace_validator
    from tools.fr27_trace.flash_shift import (
        FlashShiftError as selection_error,
        extract_live_flash_shift as live_extractor,
        frozen_interpretation_flag as classifier,
        percentage_change as change_calculator,
        select_flash_shift as selector,
        validate_flash_shift_evidence as evidence_validator,
    )
    from tools.fr27_trace.render import TraceRenderModel as render_model

    FlashShiftError = selection_error
    TraceRenderModel = render_model
    build_draft_trace = draft_builder
    extract_live_flash_shift = live_extractor
    flash_module = module
    frozen_interpretation_flag = classifier
    percentage_change = change_calculator
    select_flash_shift = selector
    validate_flash_shift_evidence = evidence_validator
    validate_trace = trace_validator


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def series_from_windows(
    previous: list[int],
    latest: list[int],
    *,
    start: date = date(2026, 6, 3),
    prefix_value: int = 100,
) -> list[dict]:
    views = [prefix_value] * 76 + previous + latest
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "views": value}
        for index, value in enumerate(views)
    ]


def metric_values(series: list[dict]) -> dict:
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
        "latest_7_peak_share": (
            None if latest_total == 0 else round(latest_peak["views"] / latest_total, 4)
        ),
        "change_7_peak_removed_pct": percentage_change(
            latest_total - latest_peak["views"],
            previous_total - previous_peak["views"],
        ),
        "period_peak_date": period_peak["date"],
        "period_peak_views": period_peak["views"],
    }


def observed_candidate(
    candidate_id: str,
    candidate_name: str,
    series: list[dict],
    *,
    flag: str | None = None,
) -> dict:
    metrics = metric_values(series)
    classifier_metrics = {
        "latest_7_views": metrics["latest_7_views"],
        "change_7_pct": metrics["change_7_pct"],
        "latest_7_peak_share": metrics["latest_7_peak_share"],
        "change_7_peak_removed_pct": metrics["change_7_peak_removed_pct"],
    }
    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate_name,
        "evidence_state": "observed",
        "wikipedia_article": {
            "page_id": 1001,
            "title": candidate_name,
            "url": "https://fr.wikipedia.org/wiki/Synthetic_Candidate",
        },
        **metrics,
        "interpretation_flag": flag or frozen_interpretation_flag(classifier_metrics),
        "daily_series": series,
    }


def unavailable_candidate(candidate_id: str = "synthetic-unavailable") -> dict:
    metric_names = (
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
    )
    return {
        "candidate_id": candidate_id,
        "candidate_name": "Synthetic Unavailable",
        "evidence_state": "unavailable_no_personal_article",
        "wikipedia_article": None,
        **{name: None for name in metric_names},
        "interpretation_flag": None,
        "daily_series": [],
    }


def attention_payload(candidates: list[dict]) -> dict:
    observed_count = sum(row["evidence_state"] == "observed" for row in candidates)
    unavailable_count = len(candidates) - observed_count
    observed = next((row for row in candidates if row["evidence_state"] == "observed"), None)
    if observed is None:
        start = date(2026, 6, 3)
        end = date(2026, 8, 31)
    else:
        start = date.fromisoformat(observed["daily_series"][0]["date"])
        end = date.fromisoformat(observed["daily_series"][-1]["date"])
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
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": 90,
            "data_as_of": end.isoformat(),
        },
        "candidate_universe": {
            "source": "candidate_candidacy_status.json",
            "source_revision_id": 1,
            "source_revision_timestamp": "2026-09-01T08:00:00Z",
            "status_as_of": "2026-09-01",
            "rule": "active_monitoring_field",
            "count": len(candidates),
            "article_eligible_count": observed_count,
            "unavailable_no_personal_article_count": unavailable_count,
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
            "candidate_count": len(candidates),
            "observed_candidate_count": observed_count,
            "unavailable_candidate_count": unavailable_count,
            "expected_days_per_observed_candidate": 90,
            "missing_dates": 0,
            "duplicate_dates": 0,
        },
        "candidates": candidates,
    }


def payload_for(
    previous: list[int],
    latest: list[int],
    *,
    candidate_id: str = "synthetic-candidate-alpha",
    candidate_name: str = "Synthetic Candidate Alpha",
    start: date = date(2026, 6, 3),
    prefix_value: int = 100,
) -> dict:
    series = series_from_windows(previous, latest, start=start, prefix_value=prefix_value)
    return attention_payload([observed_candidate(candidate_id, candidate_name, series)])


EVENT_PREVIOUS = [1000] * 7
EVENT_LATEST = [600, 600, 600, 5000, 600, 600, 600]


class FlashShiftClassifierParityTests(unittest.TestCase):
    def test_threshold_constants_match_production(self) -> None:
        from build_candidate_attention import (
            EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT,
            EVENT_AMPLIFIED_PEAK_SHARE_MIN,
            EVENT_AMPLIFIED_RAW_MIN_PCT,
            EVENT_AMPLIFIED_RETAINED_RATIO_MAX,
            LOW_BASE_7D_VIEWS,
            SUSTAINED_CHANGE_MIN_PCT,
        )

        self.assertEqual(
            (3000, 5.0, 10.0, 15.0, 0.40, 0.35),
            (
                LOW_BASE_7D_VIEWS,
                SUSTAINED_CHANGE_MIN_PCT,
                EVENT_AMPLIFIED_RAW_MIN_PCT,
                EVENT_AMPLIFIED_DIFFERENCE_MIN_PCT,
                EVENT_AMPLIFIED_RETAINED_RATIO_MAX,
                EVENT_AMPLIFIED_PEAK_SHARE_MIN,
            ),
        )

    def test_table_driven_parity_with_current_production_classifier(self) -> None:
        from build_candidate_attention import interpretation_flag as production_flag

        cases = {
            "event_amplified": (10000, 22.9, -40.0, 0.5814),
            "sustained_rise": (7700, 10.0, 10.0, 0.1429),
            "sustained_decline": (6300, -10.0, -10.0, 0.1429),
            "stable": (7000, 0.0, 0.0, 0.1429),
            "low_base": (2800, -20.0, -20.0, 0.1429),
        }
        for expected, values in cases.items():
            with self.subTest(expected=expected):
                latest, raw, adjusted, peak_share = values
                metrics = {
                    "latest_7_views": latest,
                    "change_7_pct": raw,
                    "change_7_peak_removed_pct": adjusted,
                    "latest_7_peak_share": peak_share,
                }
                self.assertEqual(expected, frozen_interpretation_flag(metrics))
                self.assertEqual(production_flag(metrics), frozen_interpretation_flag(metrics))

    def test_precedence_and_exact_boundaries(self) -> None:
        cases = (
            ("low_base", 2999, 100.0, 100.0, 0.1),
            ("stable", 3000, 4.9, 4.9, 0.2),
            ("sustained_rise", 3000, 5.0, 5.0, 0.2),
            ("sustained_decline", 3000, -5.0, -5.0, 0.2),
            ("event_amplified", 10000, 10.0, -1.0, 0.2),
            ("event_amplified", 10000, 20.0, 5.0, 0.2),
            ("event_amplified", 10000, 25.0, 10.0, 0.2),
            ("event_amplified", 10000, 10.0, 4.9, 0.35),
        )
        for expected, latest, raw, adjusted, peak_share in cases:
            with self.subTest(expected=expected, raw=raw, adjusted=adjusted):
                self.assertEqual(
                    expected,
                    frozen_interpretation_flag(
                        {
                            "latest_7_views": latest,
                            "change_7_pct": raw,
                            "change_7_peak_removed_pct": adjusted,
                            "latest_7_peak_share": peak_share,
                        }
                    ),
                )

    def test_unavailable_comparison_and_percentage_zero_denominator(self) -> None:
        self.assertIsNone(percentage_change(10, 0))
        self.assertEqual(
            "stable",
            frozen_interpretation_flag(
                {
                    "latest_7_views": 5000,
                    "change_7_pct": None,
                    "change_7_peak_removed_pct": None,
                    "latest_7_peak_share": 0.2,
                }
            ),
        )
        self.assertEqual(
            "low_base",
            frozen_interpretation_flag(
                {
                    "latest_7_views": 0,
                    "change_7_pct": None,
                    "change_7_peak_removed_pct": None,
                    "latest_7_peak_share": None,
                }
            ),
        )


class FlashShiftExtractionTests(unittest.TestCase):
    def test_fixture_arithmetic_identity_and_classification(self) -> None:
        document = load_fixture()
        self.assertIsNone(validate_trace(document["trace"]))
        self.assertIsNone(validate_flash_shift_evidence(document["trace"]["evidence"]))
        metrics = document["trace"]["evidence"]["metrics"]
        self.assertEqual(7000, metrics["previous_7_views"]["value"])
        self.assertEqual(8600, metrics["latest_7_views"]["value"])
        self.assertEqual(22.9, metrics["change_7_pct"]["value"])
        self.assertEqual("2026-08-28", metrics["latest_7_peak_date"]["value"])
        self.assertEqual(5000, metrics["latest_7_peak_views"]["value"])
        self.assertEqual(0.5814, metrics["latest_7_peak_share"]["value"])
        self.assertEqual(-40, metrics["change_7_peak_removed_pct"]["value"])
        self.assertEqual(
            "event_amplified", document["trace"]["evidence"]["classification"]["value"]
        )

    def test_eligible_event_amplified_builds_candidate_trace(self) -> None:
        selection = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST), "synthetic-candidate-alpha"
        )
        self.assertTrue(selection.eligible)
        self.assertEqual("FLASH", selection.classification_label)
        self.assertEqual(
            {"start": "2026-08-18", "end": "2026-08-31"},
            selection.observation_window,
        )
        trace = selection.build_trace()
        self.assertEqual("candidate", trace["family"])
        self.assertEqual("flash_shift.v1", trace["detector_id"])
        self.assertEqual(["synthetic-candidate-alpha"], trace["primary_entity_ids"])

    def test_stable_low_base_and_unavailable_are_valid_suppressions(self) -> None:
        cases = (
            (payload_for([1000] * 7, [1000] * 7), "stable"),
            (payload_for([500] * 7, [400] * 7), "low_base"),
            (attention_payload([unavailable_candidate()]), "unavailable"),
        )
        ids = ("synthetic-candidate-alpha", "synthetic-candidate-alpha", "synthetic-unavailable")
        for (payload, reason), candidate_id in zip(cases, ids):
            with self.subTest(reason=reason):
                selection = select_flash_shift(payload, candidate_id)
                self.assertFalse(selection.eligible)
                self.assertEqual("suppressed", selection.status)
                self.assertEqual(reason, selection.suppression_reason)
                self.assertIsNone(selection.build_trace())

    def test_sustained_rise_and_decline_are_eligible(self) -> None:
        cases = (
            ([1000] * 7, [1100] * 7, "sustained_rise", "SHIFT · RISE"),
            ([1000] * 7, [900] * 7, "sustained_decline", "SHIFT · DECLINE"),
        )
        for previous, latest, flag, label in cases:
            with self.subTest(flag=flag):
                selection = select_flash_shift(
                    payload_for(previous, latest), "synthetic-candidate-alpha"
                )
                self.assertTrue(selection.eligible)
                self.assertEqual(flag, selection.interpretation_flag)
                self.assertEqual(label, selection.classification_label)

    def test_malformed_evidence_fails_instead_of_suppressing(self) -> None:
        payload = payload_for([1000] * 7, [1000] * 7)
        payload["candidates"][0]["latest_7_views"] += 1
        with self.assertRaisesRegex(FlashShiftError, "invalid candidate_attention"):
            select_flash_shift(payload, "synthetic-candidate-alpha")

    def test_production_contract_rejects_bad_length_continuity_bool_and_schema(self) -> None:
        cases = []
        wrong_length = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        wrong_length["candidates"][0]["daily_series"].pop()
        cases.append(wrong_length)
        discontinuous = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        discontinuous["candidates"][0]["daily_series"][-1]["date"] = "2026-08-29"
        cases.append(discontinuous)
        boolean_view = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        boolean_view["candidates"][0]["daily_series"][-1]["views"] = True
        cases.append(boolean_view)
        wrong_schema = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        wrong_schema["schema_version"] = "1.0"
        cases.append(wrong_schema)
        for index, payload in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(FlashShiftError):
                    select_flash_shift(payload, "synthetic-candidate-alpha")

    def test_authoritative_flag_must_match_frozen_classifier(self) -> None:
        payload = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        payload["candidates"][0]["interpretation_flag"] = "stable"
        with self.assertRaisesRegex(FlashShiftError, "frozen flash_shift.v1 classifier"):
            select_flash_shift(payload, "synthetic-candidate-alpha")

    def test_exact_candidate_id_is_required_without_fuzzy_or_fallback_selection(self) -> None:
        payload = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        for candidate_id in ("Synthetic Candidate Alpha", "synthetic-candidate", ""):
            with self.subTest(candidate_id=candidate_id):
                with self.assertRaises(FlashShiftError):
                    select_flash_shift(payload, candidate_id)

    def test_selected_evidence_is_narrow_and_excludes_production_extras(self) -> None:
        evidence = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST), "synthetic-candidate-alpha"
        ).evidence
        self.assertEqual(
            {"source", "classification", "previous_7", "latest_7", "metrics"},
            set(evidence),
        )
        serialized = json.dumps(evidence)
        for excluded in (
            "candidate_name",
            "generated_at",
            "latest_28_views",
            "previous_28_views",
            "change_28_pct",
            "period_peak_date",
            "period_peak_views",
            "wikipedia_article",
        ):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, serialized)

    def test_same_selected_evidence_produces_same_identity(self) -> None:
        first = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST), "synthetic-candidate-alpha"
        ).build_trace()
        second = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST), "synthetic-candidate-alpha"
        ).build_trace()
        self.assertEqual(first["trace_key"], second["trace_key"])

    def test_candidate_and_observation_window_changes_change_identity(self) -> None:
        first = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST), "synthetic-candidate-alpha"
        ).build_trace()
        candidate_changed = select_flash_shift(
            payload_for(
                EVENT_PREVIOUS,
                EVENT_LATEST,
                candidate_id="synthetic-candidate-beta",
                candidate_name="Synthetic Candidate Beta",
            ),
            "synthetic-candidate-beta",
        ).build_trace()
        window_changed = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST, start=date(2026, 6, 4)),
            "synthetic-candidate-alpha",
        ).build_trace()
        self.assertNotEqual(first["trace_key"], candidate_changed["trace_key"])
        self.assertNotEqual(first["trace_key"], window_changed["trace_key"])

    def test_daily_and_coherent_classifier_changes_change_identity(self) -> None:
        first = select_flash_shift(
            payload_for(EVENT_PREVIOUS, EVENT_LATEST), "synthetic-candidate-alpha"
        ).build_trace()
        changed_daily = select_flash_shift(
            payload_for(EVENT_PREVIOUS, [600, 600, 600, 5001, 600, 600, 600]),
            "synthetic-candidate-alpha",
        ).build_trace()
        changed_classifier = select_flash_shift(
            payload_for([1000] * 7, [1100] * 7), "synthetic-candidate-alpha"
        ).build_trace()
        self.assertNotEqual(first["trace_key"], changed_daily["trace_key"])
        self.assertNotEqual(first["trace_key"], changed_classifier["trace_key"])

    def test_presentation_language_and_copy_do_not_change_identity(self) -> None:
        first = load_fixture()
        second = deepcopy(first)
        second["presentation"].update(
            {
                "language": "fr",
                "finding": "COPIE DE PRÉSENTATION SYNTHÉTIQUE.",
                "qualifier": "Texte de rendu seulement.",
                "display_label": "CANDIDAT SYNTHÉTIQUE ALPHA",
            }
        )
        first_model = TraceRenderModel.from_document(first)
        second_model = TraceRenderModel.from_document(second)
        self.assertEqual(first_model.trace["trace_key"], second_model.trace["trace_key"])

    def test_generated_at_unrelated_candidate_and_first_76_days_do_not_change_identity(self) -> None:
        base_payload = payload_for(EVENT_PREVIOUS, EVENT_LATEST)
        generated_changed = deepcopy(base_payload)
        generated_changed["generated_at"] = "2026-09-02T09:00:00Z"

        unrelated_first = attention_payload(
            [deepcopy(base_payload["candidates"][0]), unavailable_candidate()]
        )
        unrelated_second = deepcopy(unrelated_first)
        unrelated_second["candidates"][1]["candidate_name"] = "Changed Elsewhere"

        first_76_changed = payload_for(
            EVENT_PREVIOUS, EVENT_LATEST, prefix_value=999
        )
        traces = [
            select_flash_shift(payload, "synthetic-candidate-alpha").build_trace()
            for payload in (
                base_payload,
                generated_changed,
                unrelated_first,
                unrelated_second,
                first_76_changed,
            )
        ]
        self.assertEqual(1, len({trace["trace_key"] for trace in traces}))

    def test_equal_peak_tie_uses_earliest_date(self) -> None:
        selection = select_flash_shift(
            payload_for([900] * 7, [1000] * 7), "synthetic-candidate-alpha"
        )
        self.assertEqual(
            "2026-08-25",
            selection.evidence["metrics"]["latest_7_peak_date"]["value"],
        )

    def test_zero_views_are_observed_not_missing(self) -> None:
        selection = select_flash_shift(
            payload_for([0] * 7, [0] * 7), "synthetic-candidate-alpha"
        )
        self.assertEqual("low_base", selection.interpretation_flag)
        first_day = selection.evidence["previous_7"]["daily_views"][0]["views"]
        self.assertEqual(
            {"availability": "observed", "unit": "pageviews", "value": 0},
            first_day,
        )
        self.assertEqual(
            "unavailable",
            selection.evidence["metrics"]["change_7_pct"]["availability"],
        )

    def test_live_adapter_opens_only_fixed_source_for_reading(self) -> None:
        source_file = io.StringIO(json.dumps(payload_for(EVENT_PREVIOUS, EVENT_LATEST)))
        fake_path = mock.Mock()
        fake_path.open.return_value = source_file
        with mock.patch.object(flash_module, "CANDIDATE_ATTENTION_PATH", fake_path):
            selection = extract_live_flash_shift("synthetic-candidate-alpha")
        self.assertTrue(selection.eligible)
        fake_path.open.assert_called_once_with(encoding="utf-8")

    def test_runtime_source_does_not_import_builder_or_offer_external_path(self) -> None:
        source = (TRACE_ROOT / "flash_shift.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("from build_candidate_attention", source)
        self.assertNotIn("import build_candidate_attention", source)
        for forbidden in ("urlopen", "requests", "subprocess", ".write_text(", ".write_bytes("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class FlashShiftRenderTests(unittest.TestCase):
    def test_render_payload_has_chronological_days_common_scale_and_boundary(self) -> None:
        payload = TraceRenderModel.from_document(load_fixture()).to_payload()
        field = payload["field"]
        self.assertEqual(14, len(field["days"]))
        self.assertEqual(
            [f"2026-08-{day:02d}" for day in range(18, 32)],
            [day["date"] for day in field["days"]],
        )
        self.assertEqual(["previous"] * 7 + ["latest"] * 7, [day["window"] for day in field["days"]])
        self.assertEqual(100, field["days"][10]["heightPercent"])
        self.assertEqual(20, field["days"][0]["heightPercent"])
        self.assertEqual(12, field["days"][7]["heightPercent"])

        css = (TRACE_ROOT / "render" / "shell.css").read_text(encoding="utf-8")
        self.assertIn(".flash-day:nth-child(8)", css)
        self.assertIn(".flash-day-latest .flash-bar", css)
        self.assertIn("var(--cyan)", css[css.index(".flash-day-latest .flash-bar"):])
        self.assertIn("var(--muted)", css[css.index(".flash-bar {"):css.index(".flash-day-latest")])

    def test_exact_summary_classification_and_footer_values(self) -> None:
        payload = TraceRenderModel.from_document(load_fixture()).to_payload()
        self.assertEqual("FLASH", payload["field"]["classificationLabel"])
        self.assertEqual(
            ["7,000", "8,600", "+22.9%", "-40.0%", "58.1%"],
            [item["value"] for item in payload["field"]["summary"]],
        )
        self.assertEqual("FR27 WIKIPEDIA ATTENTION", payload["sourceScope"])
        self.assertEqual("PAGEVIEWS ≠ SUPPORT OR SENTIMENT", payload["methodologicalBoundary"])

    def test_visual_uses_only_pageviews_for_scaled_bars_and_no_prohibited_claims(self) -> None:
        payload = TraceRenderModel.from_document(load_fixture()).to_payload()
        self.assertTrue(all(set(day) == {
            "date", "dateLabel", "views", "viewsLabel", "window", "heightPercent", "isPeak"
        } for day in payload["field"]["days"]))
        serialized = json.dumps(payload).lower()
        for forbidden in (
            "momentum",
            "popularity",
            "surge in support",
            "voter movement",
            "caused by",
            "reaction to",
            "composite score",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

        css = (TRACE_ROOT / "render" / "shell.css").read_text(encoding="utf-8")
        flash_css = css[css.index(".flash-field {"):css.index(".trace-footer {")]
        self.assertNotIn("var(--event-red)", flash_css)

    def test_flash_field_requires_matching_candidate_detector_and_valid_evidence(self) -> None:
        document = load_fixture()
        document["trace"]["detector_id"] = "another_detector.v1"
        with self.assertRaisesRegex(Exception, "invalid TRACE|flash_shift"):
            TraceRenderModel.from_document(document)

        malformed = load_fixture()
        evidence = deepcopy(malformed["trace"]["evidence"])
        evidence["latest_7"]["daily_views"][0]["views"]["value"] += 1
        source_trace = malformed["trace"]
        malformed["trace"] = build_draft_trace(
            family="candidate",
            detector_id="flash_shift.v1",
            primary_entity_ids=source_trace["primary_entity_ids"],
            observation_window=source_trace["observation_window"],
            evidence=evidence,
        )
        with self.assertRaisesRegex(Exception, "invalid Flash/Shift evidence"):
            TraceRenderModel.from_document(malformed)

    def test_shell_and_coverage_structures_remain_present(self) -> None:
        html = (TRACE_ROOT / "render" / "shell.html").read_text(encoding="utf-8")
        css = (TRACE_ROOT / "render" / "shell.css").read_text(encoding="utf-8")
        javascript = (TRACE_ROOT / "render" / "shell.js").read_text(encoding="utf-8")
        for frozen in (
            'class="trace-header"',
            'class="finding-region"',
            'class="coverage-field"',
            'class="trace-footer"',
            'class="brand-url">france2027.app',
        ):
            self.assertIn(frozen, html)
        self.assertIn("grid-template-columns: 45fr 35fr 20fr", css)
        self.assertIn('model.fieldType === "coverage_anatomy"', javascript)


if __name__ == "__main__":
    unittest.main()
