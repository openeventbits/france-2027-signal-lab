import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SOCIAL = Path(__file__).parent / "social"

if str(SOCIAL) not in sys.path:
    sys.path.insert(
        0,
        str(SOCIAL),
    )

MODULE_PATH = SOCIAL / "daily_plan.py"

SPEC = importlib.util.spec_from_file_location(
    "fr27_daily_plan",
    MODULE_PATH,
)

MODULE = importlib.util.module_from_spec(
    SPEC
)

sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DailyPlanTests(unittest.TestCase):
    def _signal(
        self,
        *,
        family,
        entity,
        horizon,
        score,
    ):
        return MODULE.signal_engine.Signal(
            family=family,
            horizon=horizon,
            entity_id=entity,
            label_fr=entity,
            label_en=entity,
            current_percent=20.0,
            prior_percent=10.0,
            delta_pp=10.0,
            current_numerator=20,
            prior_numerator=10,
            current_denominator=100,
            prior_denominator=100,
            current_start="2026-10-01",
            current_end="2026-10-07",
            prior_start="2026-09-24",
            prior_end="2026-09-30",
            score=score,
        )

    def test_quantitative_selection_guarantees_family_mix(self):
        values = [
            self._signal(
                family="candidate_visibility",
                entity="candidate-a",
                horizon="weekly",
                score=20,
            ),
            self._signal(
                family="candidate_visibility",
                entity="candidate-b",
                horizon="daily",
                score=19,
            ),
            self._signal(
                family="issues",
                entity="issue-a",
                horizon="weekly",
                score=8,
            ),
            self._signal(
                family="agenda",
                entity="agenda-a",
                horizon="weekly",
                score=7,
            ),
        ]

        selected = (
            MODULE.select_quantitative(
                values,
                limit=4,
            )
        )

        families = [
            value.family
            for value in selected
        ]

        self.assertIn(
            "candidate_visibility",
            families,
        )

        self.assertIn(
            "issues",
            families,
        )

        self.assertIn(
            "agenda",
            families,
        )

        self.assertLessEqual(
            families.count(
                "candidate_visibility"
            ),
            2,
        )

    def test_english_quantitative_uses_distinct_families(self):
        values = [
            self._signal(
                family="candidate_visibility",
                entity="candidate-a",
                horizon="weekly",
                score=20,
            ),
            self._signal(
                family="candidate_visibility",
                entity="candidate-b",
                horizon="daily",
                score=19,
            ),
            self._signal(
                family="issues",
                entity="issue-a",
                horizon="weekly",
                score=8,
            ),
        ]

        selected = (
            MODULE
            .select_english_quantitative(
                values,
                limit=2,
            )
        )

        self.assertEqual(
            len(selected),
            2,
        )

        self.assertNotEqual(
            selected[0].family,
            selected[1].family,
        )

    def test_today_event_ids_use_paris_date(self):
        payload = {
            "campaign_events": [
                {
                    "event_id": "today",
                    "scheduled_start": (
                        "2026-10-05T19:00:00+02:00"
                    ),
                },
                {
                    "event_id": "tomorrow",
                    "scheduled_start": (
                        "2026-10-06T10:00:00+02:00"
                    ),
                },
            ]
        }

        values = MODULE._today_event_ids(
            payload,
            now=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            values,
            {"today"},
        )

    def test_fr_plan_never_exceeds_cap(self):
        quantitative = [
            self._signal(
                family="candidate_visibility",
                entity=f"candidate-{index}",
                horizon="weekly",
                score=20 - index,
            )
            for index in range(4)
        ]

        posts = MODULE._build_fr_posts(
            roundup="Roundup",
            quantitative=quantitative,
            updates=[],
            max_posts=3,
            now=datetime(
                2026,
                10,
                5,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            len(posts),
            3,
        )


    def test_weekly_lane_has_seven_day_cooldown(self):
        signal = self._signal(
            family="issues",
            entity="work",
            horizon="weekly",
            score=10,
        )

        state = MODULE.new_planner_state()

        post = MODULE.PlannedPost(
            locale="fr",
            slot="10:15",
            lane="quantitative",
            key=(
                "quant:issues:weekly:"
                "work:2026-10-04"
            ),
            text="test",
            score=10,
        )

        MODULE.mark_post_published(
            state,
            post,
            published_at=datetime(
                2026,
                10,
                5,
                10,
                tzinfo=timezone.utc,
            ),
        )

        tomorrow_signal = (
            MODULE.signal_engine.Signal(
                **{
                    **signal.__dict__,
                    "current_end":
                        "2026-10-05",
                }
            )
        )

        self.assertFalse(
            MODULE.signal_available(
                tomorrow_signal,
                state=state,
                locale="fr",
                now=datetime(
                    2026,
                    10,
                    6,
                    10,
                    tzinfo=timezone.utc,
                ),
            )
        )

        self.assertTrue(
            MODULE.signal_available(
                tomorrow_signal,
                state=state,
                locale="fr",
                now=datetime(
                    2026,
                    10,
                    12,
                    10,
                    tzinfo=timezone.utc,
                ),
            )
        )

    def test_same_entity_cross_horizon_has_two_day_cooldown(self):
        state = MODULE.new_planner_state()

        post = MODULE.PlannedPost(
            locale="fr",
            slot="10:15",
            lane="quantitative",
            key=(
                "quant:"
                "candidate_visibility:"
                "weekly:"
                "candidate-a:"
                "2026-10-04"
            ),
            text="test",
            score=10,
        )

        MODULE.mark_post_published(
            state,
            post,
            published_at=datetime(
                2026,
                10,
                5,
                10,
                tzinfo=timezone.utc,
            ),
        )

        daily = self._signal(
            family=(
                "candidate_visibility"
            ),
            entity="candidate-a",
            horizon="daily",
            score=20,
        )

        self.assertFalse(
            MODULE.signal_available(
                daily,
                state=state,
                locale="fr",
                now=datetime(
                    2026,
                    10,
                    6,
                    10,
                    tzinfo=timezone.utc,
                ),
            )
        )

    def test_roundup_is_once_per_paris_date(self):
        state = MODULE.new_planner_state()

        post = MODULE.PlannedPost(
            locale="fr",
            slot="08:45",
            lane="today_events",
            key="today-events:2026-10-05",
            text="roundup",
        )

        now = datetime(
            2026,
            10,
            5,
            8,
            tzinfo=timezone.utc,
        )

        self.assertTrue(
            MODULE.roundup_available(
                state=state,
                now=now,
            )
        )

        MODULE.mark_post_published(
            state,
            post,
            published_at=now,
        )

        self.assertFalse(
            MODULE.roundup_available(
                state=state,
                now=now,
            )
        )

    def test_daily_update_diversity_caps_candidate(self):
        first = MODULE.social_publish.SocialCandidate(
            key="a",
            kind="recent_change",
            observed_at=datetime(
                2026,
                10,
                5,
                10,
                tzinfo=timezone.utc,
            ),
            text="A",
            source_url="https://example.test/a",
        )

        second = MODULE.social_publish.SocialCandidate(
            key="b",
            kind="recent_change",
            observed_at=datetime(
                2026,
                10,
                5,
                9,
                tzinfo=timezone.utc,
            ),
            text="B",
            source_url="https://example.test/b",
        )

        third = MODULE.social_publish.SocialCandidate(
            key="c",
            kind="recent_change",
            observed_at=datetime(
                2026,
                10,
                5,
                8,
                tzinfo=timezone.utc,
            ),
            text="C",
            source_url="https://example.test/c",
        )

        payload = {
            "items": [
                {
                    "id": "a",
                    "candidate_ids": [
                        "edouard-philippe"
                    ],
                },
                {
                    "id": "b",
                    "candidate_ids": [
                        "edouard-philippe"
                    ],
                },
                {
                    "id": "c",
                    "candidate_ids": [
                        "other-candidate"
                    ],
                },
            ]
        }

        selected = MODULE.diversify_updates(
            [
                first,
                second,
                third,
            ],
            payload,
            limit=3,
            per_candidate_limit=1,
        )

        self.assertEqual(
            [
                item.key
                for item in selected
            ],
            ["a", "c"],
        )


    def test_quantitative_freshness_uses_previous_utc_day(self):
        signal = self._signal(
            family="issues",
            entity="work",
            horizon="weekly",
            score=10,
        )

        fresh = MODULE.signal_engine.Signal(
            **{
                **signal.__dict__,
                "current_end":
                    "2026-10-04",
            }
        )

        stale = MODULE.signal_engine.Signal(
            **{
                **signal.__dict__,
                "current_end":
                    "2026-10-03",
            }
        )

        now = datetime(
            2026,
            10,
            5,
            6,
            tzinfo=timezone.utc,
        )

        self.assertTrue(
            MODULE.signal_is_fresh(
                fresh,
                now=now,
            )
        )

        self.assertFalse(
            MODULE.signal_is_fresh(
                stale,
                now=now,
            )
        )

    def test_yesterdays_signal_becomes_stale_next_day(self):
        signal = self._signal(
            family="agenda",
            entity="strategy",
            horizon="weekly",
            score=10,
        )

        signal = (
            MODULE.signal_engine.Signal(
                **{
                    **signal.__dict__,
                    "current_end":
                        "2026-10-04",
                }
            )
        )

        self.assertTrue(
            MODULE.signal_is_fresh(
                signal,
                now=datetime(
                    2026,
                    10,
                    5,
                    6,
                    tzinfo=timezone.utc,
                ),
            )
        )

        self.assertFalse(
            MODULE.signal_is_fresh(
                signal,
                now=datetime(
                    2026,
                    10,
                    6,
                    6,
                    tzinfo=timezone.utc,
                ),
            )
        )


    def test_planner_reads_nested_unified_social_state(self):
        social_state = (
            MODULE.social_publish
            .build_bootstrap_state(
                {
                    "items": [
                        {
                            "id":
                                "change-a"
                        }
                    ]
                },
                {
                    "campaign_events": [
                        {
                            "event_id":
                                "event-a"
                        }
                    ]
                },
                now=datetime(
                    2026,
                    10,
                    5,
                    6,
                    tzinfo=timezone.utc,
                ),
            )
        )

        planner_state = (
            MODULE
            .planner_state_from_social_state(
                social_state
            )
        )

        self.assertIs(
            planner_state,
            social_state["planner"],
        )

        self.assertEqual(
            planner_state[
                "published_quantitative"
            ],
            [],
        )

    def test_attach_planner_preserves_seen_registries(self):
        social_state = {
            "schema_version": 1,
            "initialized_at":
                "2026-10-01T00:00:00Z",
            "updated_at":
                "2026-10-01T00:00:00Z",
            "seen": {
                "recent_changes": [
                    "change-a"
                ],
                "campaign_events": [
                    "event-a"
                ],
            },
        }

        planner_state = (
            MODULE.new_planner_state()
        )

        MODULE.attach_planner_state(
            social_state,
            planner_state,
        )

        self.assertEqual(
            social_state["seen"][
                "recent_changes"
            ],
            ["change-a"],
        )

        self.assertEqual(
            social_state["seen"][
                "campaign_events"
            ],
            ["event-a"],
        )

        self.assertEqual(
            social_state["planner"],
            planner_state,
        )


    def test_new_planner_state_has_dynamic_ledger(self):
        state = MODULE.new_planner_state()

        self.assertEqual(
            state["dynamic_updates"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
