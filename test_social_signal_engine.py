import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "social" / "signal_engine.py"

SPEC = importlib.util.spec_from_file_location(
    "fr27_signal_engine",
    MODULE_PATH,
)

MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SignalEngineTests(unittest.TestCase):
    def test_window_dates(self):
        dates = [
            f"2026-10-{day:02d}"
            for day in range(1, 15)
        ]

        current, prior = MODULE._window_dates(
            dates,
            "weekly",
        )

        self.assertEqual(
            prior,
            [
                f"2026-10-{day:02d}"
                for day in range(1, 8)
            ],
        )

        self.assertEqual(
            current,
            [
                f"2026-10-{day:02d}"
                for day in range(8, 15)
            ],
        )

    def test_candidate_daily_signal(self):
        payload = {
            "lanes": {
                "campaign_attention": {
                    "daily_denominators": [
                        {
                            "date": "2026-10-01",
                            "record_count": 100,
                        },
                        {
                            "date": "2026-10-02",
                            "record_count": 100,
                        },
                    ]
                }
            },
            "candidates": [
                {
                    "candidate_id": "example",
                    "candidate_name": "Example Candidate",
                    "campaign_attention": {
                        "daily_series": [
                            {
                                "date": "2026-10-01",
                                "record_count": 10,
                            },
                            {
                                "date": "2026-10-02",
                                "record_count": 20,
                            },
                        ]
                    },
                }
            ],
        }

        signals = MODULE.candidate_signals(payload)

        self.assertEqual(len(signals), 1)

        signal = signals[0]

        self.assertEqual(signal.horizon, "daily")
        self.assertAlmostEqual(
            signal.current_percent,
            20.0,
        )
        self.assertAlmostEqual(
            signal.prior_percent,
            10.0,
        )
        self.assertAlmostEqual(
            signal.delta_pp,
            10.0,
        )

    def test_lane_winners_returns_one_per_lane(self):
        base = dict(
            label_fr="Test",
            label_en="Test",
            current_percent=10.0,
            prior_percent=5.0,
            delta_pp=5.0,
            current_numerator=10,
            prior_numerator=5,
            current_denominator=100,
            prior_denominator=100,
            current_start="2026-10-02",
            current_end="2026-10-02",
            prior_start="2026-10-01",
            prior_end="2026-10-01",
        )

        values = [
            MODULE.Signal(
                family="issues",
                horizon="daily",
                entity_id="a",
                score=5.0,
                **base,
            ),
            MODULE.Signal(
                family="issues",
                horizon="daily",
                entity_id="b",
                score=9.0,
                **base,
            ),
            MODULE.Signal(
                family="agenda",
                horizon="daily",
                entity_id="c",
                score=7.0,
                **base,
            ),
        ]

        winners = MODULE.lane_winners(values)

        self.assertEqual(len(winners), 2)

        ids = {signal.entity_id for signal in winners}

        self.assertEqual(ids, {"b", "c"})

    def test_rendered_posts_fit_basic_x_limit(self):
        signal = MODULE.Signal(
            family="candidate_visibility",
            horizon="weekly",
            entity_id="example",
            label_fr="Édouard Philippe",
            label_en="Édouard Philippe",
            current_percent=18.4,
            prior_percent=11.2,
            delta_pp=7.2,
            current_numerator=120,
            prior_numerator=80,
            current_denominator=650,
            prior_denominator=700,
            current_start="2026-09-28",
            current_end="2026-10-04",
            prior_start="2026-09-21",
            prior_end="2026-09-27",
            score=9.0,
        )

        fr = MODULE.render_fr(signal)
        en = MODULE.render_en(signal)

        self.assertLessEqual(len(fr), 280)
        self.assertLessEqual(len(en), 280)


    def test_agenda_uses_canonical_daily_array(self):
        payload = {
            "daily": [
                {
                    "date": "2026-10-01",
                    "total_classified_agenda_items": 20,
                },
                {
                    "date": "2026-10-02",
                    "total_classified_agenda_items": 20,
                },
            ],
            "topics": [
                {
                    "id": "example-topic",
                    "labels": {
                        "fr": "Sujet exemple",
                        "en": "Example topic",
                    },
                    "daily": [
                        {
                            "date": "2026-10-01",
                            "item_count": 2,
                        },
                        {
                            "date": "2026-10-02",
                            "item_count": 10,
                        },
                    ],
                }
            ],
        }

        signals = MODULE.agenda_signals(
            payload
        )

        self.assertEqual(
            len(signals),
            1,
        )

        signal = signals[0]

        self.assertEqual(
            signal.family,
            "agenda",
        )

        self.assertEqual(
            signal.horizon,
            "daily",
        )

        self.assertAlmostEqual(
            signal.prior_percent,
            10.0,
        )

        self.assertAlmostEqual(
            signal.current_percent,
            50.0,
        )

        self.assertAlmostEqual(
            signal.delta_pp,
            40.0,
        )

    def test_selection_does_not_repeat_entity_across_horizons(self):
        common = dict(
            family="issues",
            label_fr="Europe",
            label_en="Europe",
            current_percent=10.0,
            prior_percent=5.0,
            delta_pp=5.0,
            current_numerator=10,
            prior_numerator=5,
            current_denominator=100,
            prior_denominator=100,
            current_start="2026-10-02",
            current_end="2026-10-02",
            prior_start="2026-10-01",
            prior_end="2026-10-01",
        )

        values = [
            MODULE.Signal(
                entity_id="europe",
                horizon="daily",
                score=10.0,
                **common,
            ),
            MODULE.Signal(
                entity_id="europe",
                horizon="weekly",
                score=9.0,
                **common,
            ),
            MODULE.Signal(
                entity_id="economy",
                horizon="four_week",
                score=8.0,
                **{
                    **common,
                    "label_fr": "Économie",
                    "label_en": "Economy",
                },
            ),
        ]

        selected = MODULE.select_signals(
            values,
            limit=3,
        )

        self.assertEqual(
            [item.entity_id for item in selected],
            ["europe", "economy"],
        )

    def test_english_selection_prefers_distinct_families(self):
        base = dict(
            label_fr="Test",
            label_en="Test",
            current_percent=10.0,
            prior_percent=5.0,
            delta_pp=5.0,
            current_numerator=10,
            prior_numerator=5,
            current_denominator=100,
            prior_denominator=100,
            current_start="2026-10-02",
            current_end="2026-10-02",
            prior_start="2026-10-01",
            prior_end="2026-10-01",
        )

        values = [
            MODULE.Signal(
                family="candidate_visibility",
                entity_id="candidate-a",
                horizon="daily",
                score=10.0,
                **base,
            ),
            MODULE.Signal(
                family="candidate_visibility",
                entity_id="candidate-b",
                horizon="weekly",
                score=9.0,
                **base,
            ),
            MODULE.Signal(
                family="issues",
                entity_id="issue-a",
                horizon="daily",
                score=8.0,
                **base,
            ),
        ]

        selected = MODULE.select_signals(
            values,
            limit=2,
            distinct_families=True,
        )

        self.assertEqual(
            [item.family for item in selected],
            [
                "candidate_visibility",
                "issues",
            ],
        )


    def test_poll_race_agenda_lane_is_excluded_from_social(self):
        payload = {
            "daily": [
                {
                    "date": "2026-10-01",
                    "total_classified_agenda_items": 20,
                },
                {
                    "date": "2026-10-02",
                    "total_classified_agenda_items": 20,
                },
            ],
            "topics": [
                {
                    "id": "polls_race",
                    "labels": {
                        "fr": "Sondages et rapports de force",
                        "en": "Polling & race narratives",
                    },
                    "daily": [
                        {
                            "date": "2026-10-01",
                            "item_count": 1,
                        },
                        {
                            "date": "2026-10-02",
                            "item_count": 15,
                        },
                    ],
                }
            ],
        }

        self.assertEqual(
            MODULE.agenda_signals(payload),
            [],
        )

    def test_weak_daily_issue_signal_is_suppressed(self):
        payload = {
            "corpus": {
                "daily": [
                    {
                        "date": "2026-10-01",
                        "item_count": 100,
                    },
                    {
                        "date": "2026-10-02",
                        "item_count": 100,
                    },
                ]
            },
            "issues": [
                {
                    "id": "example",
                    "labels": {
                        "fr": "Exemple",
                        "en": "Example",
                    },
                    "daily": [
                        {
                            "date": "2026-10-01",
                            "item_count": 0,
                        },
                        {
                            "date": "2026-10-02",
                            "item_count": 4,
                        },
                    ],
                }
            ],
        }

        self.assertEqual(
            MODULE.issue_signals(payload),
            [],
        )

    def test_candidate_copy_contains_raw_counts(self):
        signal = MODULE.Signal(
            family="candidate_visibility",
            horizon="daily",
            entity_id="example",
            label_fr="Exemple",
            label_en="Example",
            current_percent=20.0,
            prior_percent=10.0,
            delta_pp=10.0,
            current_numerator=20,
            prior_numerator=10,
            current_denominator=100,
            prior_denominator=100,
            current_start="2026-10-02",
            current_end="2026-10-02",
            prior_start="2026-10-01",
            prior_end="2026-10-01",
            score=10.0,
        )

        fr = MODULE.render_fr(signal)
        en = MODULE.render_en(signal)

        self.assertIn("20/100", fr)
        self.assertIn("10/100", fr)

        self.assertIn("20/100", en)
        self.assertIn("10/100", en)


if __name__ == "__main__":
    unittest.main()
