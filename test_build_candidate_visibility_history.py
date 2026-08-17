from __future__ import annotations

import json
import random
import unittest

from build_candidate_visibility_history import (
    CandidateVisibilityHistoryBuildError,
    build_candidate_visibility_history,
)
from candidate_visibility_history_contract import (
    CAMPAIGN_LANE,
    GENERAL_LANE,
    serialize_candidate_visibility_history,
)


GENERATED_AT = (
    "2026-08-17T10:51:58.096270Z"
)


def candidates():
    return [
        {
            "candidate_id": "alice",
            "candidate_name": "Alice",
            "previous_names": [
                "Alice Ancienne"
            ],
        },
        {
            "candidate_id": "bob",
            "candidate_name": "Bob",
            "previous_names": [],
        },
        {
            "candidate_id": "zero",
            "candidate_name": "Zero Candidate",
            "previous_names": [],
        },
    ]


def watch_item(
    *,
    published_date,
    scope,
    names,
    publisher,
    suffix,
):
    return {
        "id": f"item-{suffix}",
        "publisher": publisher,
        "published_at": (
            f"{published_date}T12:00:00Z"
        ),
        "headline": f"Headline {suffix}",
        "url": (
            "https://example.test/"
            f"{suffix}"
        ),
        "explicit_election": (
            scope == "election"
        ),
        "candidates": list(names),
        "candidate_matches": [
            {
                "candidate": name,
                "matched_aliases": [name],
                "locations": [
                    "headline"
                ],
            }
            for name in names
        ],
        "coverage_scope": scope,
    }


def point(
    payload,
    candidate_id,
    lane_name,
    current_date,
):
    candidate = next(
        row
        for row in payload["candidates"]
        if row["candidate_id"] == candidate_id
    )

    return next(
        observation
        for observation in candidate[
            lane_name
        ]["daily_series"]
        if observation["date"] == current_date
    )


def denominator(
    payload,
    lane_name,
    current_date,
):
    return next(
        observation
        for observation in payload[
            "lanes"
        ][lane_name][
            "daily_denominators"
        ]
        if observation["date"] == current_date
    )


class CandidateVisibilityHistoryBuildTests(
    unittest.TestCase
):
    def build(self, items):
        return build_candidate_visibility_history(
            candidate_watch=items,
            generated_at=GENERATED_AT,
            window_days=30,
            candidates=candidates(),
        )

    def test_period_is_29_complete_utc_days(self):
        payload = self.build([])

        self.assertEqual(
            payload["period"],
            {
                "start_date": "2026-07-19",
                "end_date": "2026-08-16",
                "days": 29,
                "data_as_of": "2026-08-16",
                "day_boundary": "UTC",
                "current_utc_day_excluded": True,
            },
        )

    def test_multi_candidate_record_has_one_denominator(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Alice", "Bob"],
                    publisher="Publisher A",
                    suffix="multi",
                )
            ]
        )

        day = denominator(
            payload,
            CAMPAIGN_LANE,
            "2026-08-16",
        )

        self.assertEqual(
            day["record_count"],
            1,
        )

        self.assertEqual(
            point(
                payload,
                "alice",
                CAMPAIGN_LANE,
                "2026-08-16",
            )["record_count"],
            1,
        )

        self.assertEqual(
            point(
                payload,
                "bob",
                CAMPAIGN_LANE,
                "2026-08-16",
            )["record_count"],
            1,
        )

    def test_primary_and_general_denominators_are_separate(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Publisher A",
                    suffix="campaign",
                ),
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="election",
                    names=["Alice"],
                    publisher="Publisher B",
                    suffix="election",
                ),
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="general",
                    names=["Bob"],
                    publisher="Publisher C",
                    suffix="general",
                ),
            ]
        )

        primary = denominator(
            payload,
            CAMPAIGN_LANE,
            "2026-08-16",
        )
        general = denominator(
            payload,
            GENERAL_LANE,
            "2026-08-16",
        )

        self.assertEqual(
            primary["record_count"],
            2,
        )
        self.assertEqual(
            primary["publisher_count"],
            2,
        )
        self.assertEqual(
            general["record_count"],
            1,
        )
        self.assertEqual(
            general["publisher_count"],
            1,
        )

        alice = point(
            payload,
            "alice",
            CAMPAIGN_LANE,
            "2026-08-16",
        )

        self.assertEqual(
            alice["record_count"],
            2,
        )
        self.assertEqual(
            alice["share"],
            1.0,
        )

        bob_general = point(
            payload,
            "bob",
            GENERAL_LANE,
            "2026-08-16",
        )

        self.assertEqual(
            bob_general["record_count"],
            1,
        )
        self.assertEqual(
            bob_general["share"],
            1.0,
        )

    def test_real_zero_and_null_are_distinct(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Publisher A",
                    suffix="one",
                )
            ]
        )

        observed_zero = point(
            payload,
            "zero",
            CAMPAIGN_LANE,
            "2026-08-16",
        )

        unavailable_day = point(
            payload,
            "zero",
            GENERAL_LANE,
            "2026-08-16",
        )

        self.assertEqual(
            observed_zero["record_count"],
            0,
        )
        self.assertEqual(
            observed_zero["share"],
            0.0,
        )

        self.assertEqual(
            unavailable_day["record_count"],
            0,
        )
        self.assertIsNone(
            unavailable_day["share"]
        )

    def test_current_utc_day_and_partial_leading_day_are_excluded(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-17"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Current Day",
                    suffix="current",
                ),
                watch_item(
                    published_date=(
                        "2026-07-18"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Partial Day",
                    suffix="partial",
                ),
                watch_item(
                    published_date=(
                        "2026-07-19"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Complete Day",
                    suffix="complete",
                ),
            ]
        )

        total = sum(
            item["record_count"]
            for item in payload[
                "lanes"
            ][CAMPAIGN_LANE][
                "daily_denominators"
            ]
        )

        self.assertEqual(
            total,
            1,
        )

        self.assertEqual(
            point(
                payload,
                "alice",
                CAMPAIGN_LANE,
                "2026-07-19",
            )["record_count"],
            1,
        )

    def test_previous_name_resolves_published_identity(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=[
                        "Alice Ancienne"
                    ],
                    publisher="Publisher A",
                    suffix="prior-name",
                )
            ]
        )

        self.assertEqual(
            point(
                payload,
                "alice",
                CAMPAIGN_LANE,
                "2026-08-16",
            )["record_count"],
            1,
        )

        self.assertEqual(
            payload["candidates"][0][
                "candidate_name"
            ],
            "Alice",
        )

    def test_unknown_published_match_is_rejected(self):
        with self.assertRaisesRegex(
            CandidateVisibilityHistoryBuildError,
            "outside the controlled candidacy registry",
        ):
            self.build(
                [
                    watch_item(
                        published_date=(
                            "2026-08-16"
                        ),
                        scope="campaign",
                        names=[
                            "Unknown Person"
                        ],
                        publisher=(
                            "Publisher A"
                        ),
                        suffix="unknown",
                    )
                ]
            )

    def test_complete_candidate_universe_keeps_zero_history_rows(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Publisher A",
                    suffix="alice",
                )
            ]
        )

        self.assertEqual(
            [
                row["candidate_id"]
                for row in payload[
                    "candidates"
                ]
            ],
            [
                "alice",
                "bob",
                "zero",
            ],
        )

        zero = next(
            row
            for row in payload[
                "candidates"
            ]
            if row["candidate_id"] == "zero"
        )

        self.assertTrue(
            all(
                item[
                    "record_count"
                ] == 0
                for item in zero[
                    CAMPAIGN_LANE
                ]["daily_series"]
            )
        )

    def test_three_decimal_rounding_matches_current_visibility(self):
        payload = self.build(
            [
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Alice"],
                    publisher="Publisher A",
                    suffix="a",
                ),
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Bob"],
                    publisher="Publisher B",
                    suffix="b",
                ),
                watch_item(
                    published_date=(
                        "2026-08-16"
                    ),
                    scope="campaign",
                    names=["Bob"],
                    publisher="Publisher C",
                    suffix="c",
                ),
            ]
        )

        self.assertEqual(
            point(
                payload,
                "alice",
                CAMPAIGN_LANE,
                "2026-08-16",
            )["share"],
            0.333,
        )

        self.assertEqual(
            point(
                payload,
                "bob",
                CAMPAIGN_LANE,
                "2026-08-16",
            )["share"],
            0.667,
        )

    def test_input_order_does_not_change_serialized_output(self):
        items = [
            watch_item(
                published_date=(
                    "2026-08-16"
                ),
                scope="campaign",
                names=["Alice", "Bob"],
                publisher="Publisher A",
                suffix="a",
            ),
            watch_item(
                published_date=(
                    "2026-08-15"
                ),
                scope="general",
                names=["Bob"],
                publisher="Publisher B",
                suffix="b",
            ),
            watch_item(
                published_date=(
                    "2026-08-14"
                ),
                scope="election",
                names=["Alice"],
                publisher="Publisher C",
                suffix="c",
            ),
        ]

        first = self.build(items)

        shuffled = json.loads(
            json.dumps(items)
        )

        random.Random(
            2027
        ).shuffle(shuffled)

        second = self.build(
            shuffled
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            serialize_candidate_visibility_history(
                first,
                expected_candidates=candidates(),
            ),
            serialize_candidate_visibility_history(
                second,
                expected_candidates=candidates(),
            ),
        )

    def test_retention_shorter_than_30_days_is_rejected(self):
        with self.assertRaisesRegex(
            CandidateVisibilityHistoryBuildError,
            "at least 30 days",
        ):
            build_candidate_visibility_history(
                candidate_watch=[],
                generated_at=GENERATED_AT,
                window_days=29,
                candidates=candidates(),
            )

    def test_current_day_only_change_does_not_change_serialized_history(self):
        import json
        from copy import deepcopy
        from pathlib import Path

        from build_candidate_visibility_history import (
            build_from_payloads,
        )
        from candidate_visibility_history_contract import (
            serialize_candidate_visibility_history,
        )
        from fetch_news_wire import (
            build_candidate_visibility,
            parse_feed_datetime,
        )

        root = Path(__file__).resolve().parent

        news = json.loads(
            (root / "news_wire.json").read_text(
                encoding="utf-8"
            )
        )

        registry = json.loads(
            (
                root
                / "candidate_candidacy_status.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        baseline_payload = build_from_payloads(
            news,
            registry,
        )

        baseline_bytes = (
            serialize_candidate_visibility_history(
                baseline_payload,
                expected_candidates=registry[
                    "candidates"
                ],
            )
        )

        changed_news = deepcopy(news)

        generated_at = changed_news.get(
            "generated_at"
        )

        self.assertIsInstance(
            generated_at,
            str,
        )

        self.assertGreaterEqual(
            len(generated_at),
            10,
        )

        current_utc_date = (
            generated_at[:10]
        )

        candidate_watch = (
            changed_news.get(
                "candidate_watch"
            )
        )

        self.assertIsInstance(
            candidate_watch,
            list,
        )

        source_record = next(
            (
                record
                for record in candidate_watch
                if (
                    isinstance(record, dict)
                    and isinstance(
                        record.get(
                            "candidate_matches"
                        ),
                        list,
                    )
                    and record.get(
                        "candidate_matches"
                    )
                    and isinstance(
                        record.get(
                            "published_at"
                        ),
                        str,
                    )
                )
            ),
            None,
        )

        self.assertIsNotNone(
            source_record,
        )

        current_day_record = deepcopy(
            source_record
        )

        current_day_record[
            "published_at"
        ] = (
            f"{current_utc_date}"
            "T12:00:00Z"
        )

        # Avoid accidentally depending on source-record identity.
        if isinstance(
            current_day_record.get("id"),
            str,
        ):
            current_day_record["id"] = (
                current_day_record["id"]
                + "-current-day-invariance"
            )

        candidate_watch.append(
            current_day_record
        )

        counts = changed_news.get(
            "counts"
        )

        self.assertIsInstance(
            counts,
            dict,
        )

        counts[
            "candidate_watch"
        ] = len(
            candidate_watch
        )

        parsed_generated_at = (
            parse_feed_datetime(
                changed_news[
                    "generated_at"
                ]
            )
        )

        self.assertIsNotNone(
            parsed_generated_at,
        )

        changed_news[
            "candidate_visibility"
        ] = build_candidate_visibility(
            candidate_watch,
            parsed_generated_at,
        )

        changed_payload = build_from_payloads(
            changed_news,
            registry,
        )

        changed_bytes = (
            serialize_candidate_visibility_history(
                changed_payload,
                expected_candidates=registry[
                    "candidates"
                ],
            )
        )

        self.assertEqual(
            baseline_payload[
                "period"
            ],
            changed_payload[
                "period"
            ],
        )

        self.assertEqual(
            baseline_bytes,
            changed_bytes,
        )



if __name__ == "__main__":
    unittest.main()