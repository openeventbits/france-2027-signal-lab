from __future__ import annotations

import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from candidate_attention_contract import (
    CandidateAttentionContractError,
    METHODOLOGY_INTERPRETATION,
    METHODOLOGY_LABEL,
    METHODOLOGY_NOT_MEASURES,
    METHODOLOGY_REDIRECT_LIMITATION,
    METHODOLOGY_WEEKLY_COMPARISON,
    serialize_candidate_attention,
    validate_candidate_attention,
    validate_wikimedia_candidate_articles,
)


ROOT = Path(__file__).resolve().parent

CANDIDACY = json.loads(
    (ROOT / "candidate_candidacy_status.json").read_text(
        encoding="utf-8"
    )
)

REGISTRY = json.loads(
    (ROOT / "wikimedia_candidate_articles.json").read_text(
        encoding="utf-8"
    )
)

CANDIDACY_BY_ID = {
    record["candidate_id"]: record
    for record in CANDIDACY["candidates"]
}
REGISTRY_BY_ID = {
    record["candidate_id"]: record
    for record in REGISTRY["candidates"]
}
CONTROLLED_CANDIDATES = [
    CANDIDACY_BY_ID[record["candidate_id"]]
    for record in REGISTRY["candidates"]
]


def percentage_change(current, previous):
    if previous == 0:
        return None
    return round(
        ((current - previous) / previous) * 100.0,
        1,
    )


def candidate_payload(
    candidate,
    *,
    start=date(2026, 5, 9),
    views=None,
    flag="stable",
):
    if views is None:
        views = [10] * 90

    dates = [
        start + timedelta(days=offset)
        for offset in range(90)
    ]

    series = [
        {
            "date": day.isoformat(),
            "views": value,
        }
        for day, value in zip(dates, views)
    ]

    latest_7 = series[-7:]
    previous_7 = series[-14:-7]
    latest_28 = series[-28:]
    previous_28 = series[-56:-28]

    latest_7_views = sum(day["views"] for day in latest_7)
    previous_7_views = sum(day["views"] for day in previous_7)
    latest_28_views = sum(day["views"] for day in latest_28)
    previous_28_views = sum(day["views"] for day in previous_28)

    # Ascending series + max() means earliest date wins ties.
    latest_peak = max(
        latest_7,
        key=lambda observation: observation["views"],
    )
    previous_peak = max(
        previous_7,
        key=lambda observation: observation["views"],
    )
    period_peak = max(
        series,
        key=lambda observation: observation["views"],
    )

    current_without_peak = (
        latest_7_views - latest_peak["views"]
    )
    previous_without_peak = (
        previous_7_views - previous_peak["views"]
    )

    mapping = REGISTRY_BY_ID[candidate["candidate_id"]]

    return {
        "candidate_id": candidate["candidate_id"],
        "candidate_name": candidate["candidate_name"],
        "canonical_article": mapping["canonical_article"],
        "article_url": mapping["article_url"],
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
        "latest_7_peak_date": latest_peak["date"],
        "latest_7_peak_views": latest_peak["views"],
        "latest_7_peak_share": (
            None
            if latest_7_views == 0
            else round(
                latest_peak["views"] / latest_7_views,
                4,
            )
        ),
        "change_7_peak_removed_pct": percentage_change(
            current_without_peak,
            previous_without_peak,
        ),
        "period_peak_date": period_peak["date"],
        "period_peak_views": period_peak["views"],
        "interpretation_flag": flag,
        "daily_series": series,
    }


def valid_payload(*, views=None, flag="stable"):
    start = date(2026, 5, 9)
    end = start + timedelta(days=89)

    return {
        "schema_version": "1.0",
        "generated_at": "2026-08-07T04:42:05Z",
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
            "status_as_of": CANDIDACY["status_as_of"],
            "count": 20,
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
            "candidate_count": 20,
            "expected_days_per_candidate": 90,
            "missing_dates": 0,
            "duplicate_dates": 0,
        },
        "candidates": [
            candidate_payload(
                candidate,
                start=start,
                views=views,
                flag=flag,
            )
            for candidate in CONTROLLED_CANDIDATES
        ],
    }


class WikimediaCandidateRegistryContractTests(unittest.TestCase):
    def test_controlled_registry_is_valid(self):
        validate_wikimedia_candidate_articles(
            REGISTRY,
            expected_candidates=CONTROLLED_CANDIDATES,
        )

    def test_registry_contains_exactly_twenty_candidates(self):
        self.assertEqual(REGISTRY["candidate_count"], 20)
        self.assertEqual(len(REGISTRY["candidates"]), 20)

    def test_duplicate_candidate_is_rejected(self):
        payload = copy.deepcopy(REGISTRY)
        payload["candidates"][1]["candidate_id"] = (
            payload["candidates"][0]["candidate_id"]
        )

        with self.assertRaises(CandidateAttentionContractError):
            validate_wikimedia_candidate_articles(payload)

    def test_unknown_candidate_breaks_controlled_parity(self):
        payload = copy.deepcopy(REGISTRY)
        payload["candidates"][0]["candidate_id"] = "unknown-candidate"

        with self.assertRaises(CandidateAttentionContractError):
            validate_wikimedia_candidate_articles(
                payload,
                expected_candidates=CONTROLLED_CANDIDATES,
            )

    def test_olivier_faure_disambiguation_is_locked(self):
        payload = copy.deepcopy(REGISTRY)
        olivier = next(
            record
            for record in payload["candidates"]
            if record["candidate_id"] == "olivier-faure"
        )
        olivier["canonical_article"] = "Olivier Faure"

        with self.assertRaises(CandidateAttentionContractError):
            validate_wikimedia_candidate_articles(payload)

    def test_visibility_authority_is_rejected_as_extra_schema(self):
        payload = copy.deepcopy(REGISTRY)
        payload["candidates"][0]["display_tier"] = "main"

        with self.assertRaises(CandidateAttentionContractError):
            validate_wikimedia_candidate_articles(payload)


class CandidateAttentionArtifactContractTests(unittest.TestCase):
    def test_complete_artifact_is_valid(self):
        validate_candidate_attention(
            valid_payload(),
            expected_candidates=CONTROLLED_CANDIDATES,
        )

    def test_candidate_identity_order_must_match_controlled_universe(self):
        payload = valid_payload()
        payload["candidates"][0], payload["candidates"][1] = (
            payload["candidates"][1],
            payload["candidates"][0],
        )

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(
                payload,
                expected_candidates=CONTROLLED_CANDIDATES,
            )

    def test_exactly_ninety_daily_observations_are_required(self):
        payload = valid_payload()
        payload["candidates"][0]["daily_series"].pop(0)

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_missing_date_is_rejected(self):
        payload = valid_payload()
        payload["candidates"][0]["daily_series"][10]["date"] = (
            "2026-05-25"
        )

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_duplicate_date_is_rejected(self):
        payload = valid_payload()
        series = payload["candidates"][0]["daily_series"]
        series[11]["date"] = series[10]["date"]

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_negative_views_are_rejected(self):
        payload = valid_payload()
        payload["candidates"][0]["daily_series"][0]["views"] = -1

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_genuine_zero_series_is_valid_and_division_by_zero_is_null(self):
        payload = valid_payload(
            views=[0] * 90,
            flag="low_base",
        )

        first = payload["candidates"][0]

        self.assertEqual(first["latest_7_views"], 0)
        self.assertEqual(first["previous_7_views"], 0)
        self.assertIsNone(first["change_7_pct"])
        self.assertIsNone(first["change_28_pct"])
        self.assertIsNone(first["latest_7_peak_share"])
        self.assertIsNone(
            first["change_7_peak_removed_pct"]
        )

        validate_candidate_attention(
            payload,
            expected_candidates=CONTROLLED_CANDIDATES,
        )

    def test_zero_denominator_must_not_emit_infinity_or_zero_change(self):
        payload = valid_payload(
            views=[0] * 90,
            flag="low_base",
        )
        payload["candidates"][0]["change_7_pct"] = 0.0

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_weekly_metric_mismatch_is_rejected(self):
        payload = valid_payload()
        payload["candidates"][0]["latest_7_views"] += 1

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_28_day_metric_mismatch_is_rejected(self):
        payload = valid_payload()
        payload["candidates"][0]["change_28_pct"] = 15.0

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_peak_ties_resolve_to_earliest_date(self):
        payload = valid_payload()
        candidate = payload["candidates"][0]

        expected_latest_peak_date = (
            candidate["daily_series"][-7]["date"]
        )
        expected_period_peak_date = (
            candidate["daily_series"][0]["date"]
        )

        self.assertEqual(
            candidate["latest_7_peak_date"],
            expected_latest_peak_date,
        )
        self.assertEqual(
            candidate["period_peak_date"],
            expected_period_peak_date,
        )

        validate_candidate_attention(payload)

    def test_peak_removed_metric_mismatch_is_rejected(self):
        payload = valid_payload()
        payload["candidates"][0][
            "change_7_peak_removed_pct"
        ] = 12.3

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_unknown_interpretation_flag_is_rejected(self):
        payload = valid_payload()
        payload["candidates"][0]["interpretation_flag"] = (
            "popularity_rising"
        )

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_methodology_explicitly_rejects_support_interpretation(self):
        payload = valid_payload()
        self.assertIn(
            "electoral support",
            payload["methodology"]["not_measures"],
        )
        self.assertIn(
            "voting intention",
            payload["methodology"]["not_measures"],
        )
        self.assertEqual(
            payload["methodology"]["label"],
            "Wikipedia Attention",
        )
        validate_candidate_attention(payload)

    def test_data_as_of_must_equal_final_complete_observation(self):
        payload = valid_payload()
        payload["period"]["data_as_of"] = "2026-08-05"

        with self.assertRaises(CandidateAttentionContractError):
            validate_candidate_attention(payload)

    def test_generated_at_and_data_as_of_are_distinct_concepts(self):
        payload = valid_payload()

        self.assertEqual(
            payload["period"]["data_as_of"],
            "2026-08-06",
        )
        self.assertEqual(
            payload["generated_at"],
            "2026-08-07T04:42:05Z",
        )

        validate_candidate_attention(payload)

    def test_semantic_serialization_is_deterministic(self):
        payload = valid_payload()

        first = serialize_candidate_attention(
            payload,
            expected_candidates=CONTROLLED_CANDIDATES,
        )
        second = serialize_candidate_attention(
            copy.deepcopy(payload),
            expected_candidates=CONTROLLED_CANDIDATES,
        )

        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertIn(
            "Raphaël Glucksmann".encode("utf-8"),
            first,
        )


if __name__ == "__main__":
    unittest.main()