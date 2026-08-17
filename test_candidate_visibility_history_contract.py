from __future__ import annotations

import json
import unittest
from datetime import date, timedelta

from candidate_visibility_history_contract import (
    CAMPAIGN_LANE,
    EXPECTED_DAYS,
    GENERAL_LANE,
    CandidateVisibilityHistoryContractError,
    round_visibility_ratio,
    serialize_candidate_visibility_history,
    validate_candidate_visibility_history,
)
from fetch_news_wire import (
    round_candidate_visibility_ratio,
)


def fixture_payload():
    start = date(2026, 7, 19)

    dates = [
        (
            start + timedelta(days=offset)
        ).isoformat()
        for offset in range(EXPECTED_DAYS)
    ]

    campaign_denominators = [
        {
            "date": current_date,
            "record_count": 2,
            "publisher_count": 2,
        }
        for current_date in dates
    ]

    general_denominators = [
        {
            "date": current_date,
            "record_count": (
                0 if index == 0 else 1
            ),
            "publisher_count": (
                0 if index == 0 else 1
            ),
        }
        for index, current_date in enumerate(
            dates
        )
    ]

    alice_campaign = [
        {
            "date": current_date,
            "record_count": 1,
            "share": 0.5,
            "publisher_count": 1,
        }
        for current_date in dates
    ]

    bob_campaign = [
        {
            "date": current_date,
            "record_count": 0,
            "share": 0.0,
            "publisher_count": 0,
        }
        for current_date in dates
    ]

    alice_general = [
        {
            "date": current_date,
            "record_count": 0,
            "share": (
                None if index == 0 else 0.0
            ),
            "publisher_count": 0,
        }
        for index, current_date in enumerate(
            dates
        )
    ]

    bob_general = [
        {
            "date": current_date,
            "record_count": (
                0 if index == 0 else 1
            ),
            "share": (
                None if index == 0 else 1.0
            ),
            "publisher_count": (
                0 if index == 0 else 1
            ),
        }
        for index, current_date in enumerate(
            dates
        )
    ]

    return {
        "schema_version": "1.0",
        "period": {
            "start_date": dates[0],
            "end_date": dates[-1],
            "days": 29,
            "data_as_of": dates[-1],
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "methodology": {
            "source": (
                "news_wire.json:"
                "candidate_watch"
            ),
            "primary_scopes": [
                "election",
                "campaign",
            ],
            "general_scope": "general",
            "metric": (
                "candidate_share_of_lane_records"
            ),
            "candidate_linkage": (
                "published_candidate_matches"
            ),
            "not_measures": [
                "sentiment",
                "approval",
                "electoral support",
                "voting intention",
            ],
        },
        "lanes": {
            CAMPAIGN_LANE: {
                "daily_denominators": (
                    campaign_denominators
                )
            },
            GENERAL_LANE: {
                "daily_denominators": (
                    general_denominators
                )
            },
        },
        "candidates": [
            {
                "candidate_id": "alice",
                "candidate_name": "Alice",
                CAMPAIGN_LANE: {
                    "daily_series": (
                        alice_campaign
                    )
                },
                GENERAL_LANE: {
                    "daily_series": (
                        alice_general
                    )
                },
            },
            {
                "candidate_id": "bob",
                "candidate_name": "Bob",
                CAMPAIGN_LANE: {
                    "daily_series": (
                        bob_campaign
                    )
                },
                GENERAL_LANE: {
                    "daily_series": (
                        bob_general
                    )
                },
            },
        ],
    }


class CandidateVisibilityHistoryContractTests(
    unittest.TestCase
):
    def mutation(self):
        return json.loads(
            json.dumps(fixture_payload())
        )

    def test_valid_payload_and_serialization(self):
        payload = fixture_payload()

        validate_candidate_visibility_history(
            payload
        )

        serialized = (
            serialize_candidate_visibility_history(
                payload
            )
        )

        self.assertTrue(
            serialized.endswith(b"\n")
        )

        reparsed = json.loads(
            serialized.decode("utf-8")
        )

        self.assertEqual(
            reparsed,
            payload,
        )

        self.assertNotIn(
            "generated_at",
            reparsed,
        )

    def test_rounding_matches_existing_visibility_semantics(self):
        for value in (
            0,
            1 / 7,
            1 / 3,
            0.5,
            2 / 3,
            0.9994,
            1,
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    round_visibility_ratio(
                        value
                    ),
                    round_candidate_visibility_ratio(
                        value
                    ),
                )

    def test_generated_at_is_rejected(self):
        payload = self.mutation()
        payload["generated_at"] = (
            "2026-08-17T10:51:58Z"
        )

        with self.assertRaisesRegex(
            CandidateVisibilityHistoryContractError,
            "exact keys",
        ):
            validate_candidate_visibility_history(
                payload
            )

    def test_daily_gap_is_rejected(self):
        payload = self.mutation()

        payload["lanes"][
            CAMPAIGN_LANE
        ]["daily_denominators"][7][
            "date"
        ] = "2026-08-30"

        with self.assertRaisesRegex(
            CandidateVisibilityHistoryContractError,
            "exact ascending 29-day sequence",
        ):
            validate_candidate_visibility_history(
                payload
            )

    def test_zero_denominator_requires_null_share(self):
        payload = self.mutation()

        payload["candidates"][0][
            GENERAL_LANE
        ]["daily_series"][0][
            "share"
        ] = 0.0

        with self.assertRaisesRegex(
            CandidateVisibilityHistoryContractError,
            "share must be null",
        ):
            validate_candidate_visibility_history(
                payload
            )

    def test_nonzero_denominator_preserves_real_zero(self):
        payload = fixture_payload()

        zero_point = payload[
            "candidates"
        ][1][CAMPAIGN_LANE][
            "daily_series"
        ][0]

        self.assertEqual(
            zero_point["record_count"],
            0,
        )
        self.assertEqual(
            zero_point["share"],
            0.0,
        )

        validate_candidate_visibility_history(
            payload
        )

    def test_inconsistent_share_is_rejected(self):
        payload = self.mutation()

        payload["candidates"][0][
            CAMPAIGN_LANE
        ]["daily_series"][0][
            "share"
        ] = 0.4

        with self.assertRaisesRegex(
            CandidateVisibilityHistoryContractError,
            "share is inconsistent",
        ):
            validate_candidate_visibility_history(
                payload
            )

    def test_candidate_order_is_deterministic(self):
        payload = self.mutation()

        payload["candidates"].reverse()

        with self.assertRaisesRegex(
            CandidateVisibilityHistoryContractError,
            "deterministically ordered",
        ):
            validate_candidate_visibility_history(
                payload
            )

    def test_expected_candidate_parity_is_exact(self):
        payload = fixture_payload()

        expected = [
            {
                "candidate_id": "alice",
                "candidate_name": "Alice",
            },
            {
                "candidate_id": "bob",
                "candidate_name": "Bob",
            },
        ]

        validate_candidate_visibility_history(
            payload,
            expected_candidates=expected,
        )

        expected[1][
            "candidate_name"
        ] = "Bob Changed"

        with self.assertRaisesRegex(
            CandidateVisibilityHistoryContractError,
            "controlled candidacy universe",
        ):
            validate_candidate_visibility_history(
                payload,
                expected_candidates=expected,
            )


if __name__ == "__main__":
    unittest.main()