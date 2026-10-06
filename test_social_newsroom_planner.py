import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOCIAL = ROOT / "social"

if str(SOCIAL) not in sys.path:
    sys.path.insert(
        0,
        str(SOCIAL),
    )

import daily_plan
import daily_queue
import signal_engine


class NewsroomPlannerTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.issue_payload = json.loads(
            (
                ROOT
                / "issue_coverage_history.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        cls.agenda_payload = json.loads(
            (
                ROOT
                / "agenda_coverage_history.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        cls.candidate_payload = (
            signal_engine._load_json(
                signal_engine
                .DEFAULT_CANDIDATE_HISTORY
            )
        )

        cls.monday = datetime(
            2026,
            10,
            5,
            10,
            tzinfo=timezone.utc,
        )

    def _plan(
        self,
        *,
        max_fr=5,
        max_en=2,
    ):
        return daily_plan.build_plan(
            candidate_payload=(
                self.candidate_payload
            ),
            issue_payload=(
                self.issue_payload
            ),
            agenda_payload=(
                self.agenda_payload
            ),
            recent_changes={
                "items": [],
            },
            campaign_events={
                "campaign_events": [],
            },
            now=self.monday,
            max_fr=max_fr,
            max_en=max_en,
            max_quantitative=4,
            max_updates=0,
            lookback_hours=24,
            planner_state=(
                daily_plan
                .new_planner_state()
            ),
        )

    def test_monday_uses_complete_week_overlay(
        self,
    ):
        self.assertEqual(
            daily_plan.newsroom_window_mode(
                self.monday
            ),
            "complete_week",
        )

        products = (
            daily_plan
            .newsroom_products
            .build_newsroom_products(
                issue_payload=(
                    self.issue_payload
                ),
                agenda_payload=(
                    self.agenda_payload
                ),
                locale="fr",
            )
        )

        eligible = (
            daily_plan
            ._eligible_newsroom_products(
                products,
                now=self.monday,
            )
        )

        self.assertTrue(
            eligible
        )

        self.assertEqual(
            {
                product.window_mode
                for product in eligible
            },
            {
                "complete_week",
            },
        )

    def test_dominance_families_rotate_without_cross_metric_ranking(
        self,
    ):
        from datetime import timedelta

        first = (
            daily_plan
            .dominance_family_for_date(
                self.monday
            )
        )

        second = (
            daily_plan
            .dominance_family_for_date(
                self.monday
                + timedelta(days=1)
            )
        )

        next_week = (
            daily_plan
            .dominance_family_for_date(
                self.monday
                + timedelta(days=7)
            )
        )

        self.assertIn(
            first,
            {
                "issues",
                "agenda",
            },
        )

        self.assertNotEqual(
            first,
            second,
        )

        # Seven days changes ordinal parity,
        # so weekly Monday dominance alternates too.
        self.assertNotEqual(
            first,
            next_week,
        )

    def test_fr_slots_are_fixed_newsroom_slots(
        self,
    ):
        plan = self._plan()

        posts = plan[
            "fr_posts"
        ]

        self.assertEqual(
            [
                post["slot"]
                for post in posts
            ],
            [
                "09:30",
                "16:45",
                "18:30",
            ],
        )

        self.assertEqual(
            [
                post["lane"]
                for post in posts
            ],
            [
                "weekly_flagship_slot",
                "candidate_slot",
                "radar_slot",
            ],
        )

        self.assertIn(
            "weekly_flagship_fr:",
            posts[0]["key"],
        )

        self.assertEqual(posts[0]["text"], "")

    def test_candidate_slot_uses_current_dossier_media_pulse(
        self,
    ):
        plan = self._plan()

        self.assertIn(
            "16:45",
            {
                post["slot"]
                for post in plan[
                    "fr_posts"
                ]
            },
        )

        self.assertEqual(
            plan["rules"][
                "candidate_visibility_slot"
            ],
            "candidate_media_pulse_current",
        )

    def test_english_uses_two_distinct_mover_families(
        self,
    ):
        plan = self._plan()

        posts = plan[
            "en_posts"
        ]

        self.assertEqual(
            [
                post["slot"]
                for post in posts
            ],
            [
                "11:30",
                "19:30",
            ],
        )

        self.assertTrue(
            all(
                post["lane"]
                == "newsroom"
                for post in posts
            )
        )

        keys = [
            post["key"]
            for post in posts
        ]

        self.assertTrue(
            all(
                "_movers_complete_week"
                in key
                for key in keys
            )
        )

        self.assertTrue(
            any(
                key.startswith(
                    "issues_"
                )
                for key in keys
            )
        )

        self.assertTrue(
            any(
                key.startswith(
                    "agenda_"
                )
                for key in keys
            )
        )

    def test_newsroom_queue_preserves_exact_text(
        self,
    ):
        plan = self._plan()

        source = plan[
            "en_posts"
        ][0]

        queue = daily_queue.new_queue(
            queue_date="2026-10-05",
            created_at=self.monday,
            posts=[
                source,
            ],
        )

        self.assertEqual(
            queue["items"][0][
                "text"
            ],
            source["text"],
        )

        self.assertIn(
            "https://france2027.app/",
            queue["items"][0][
                "text"
            ],
        )

        self.assertLessEqual(
            daily_queue
            .social_publish
            ._weighted_x_length(
                queue["items"][0][
                    "text"
                ]
            ),
            280,
        )

    def test_fr_cap_is_respected(
        self,
    ):
        plan = self._plan(
            max_fr=2,
        )

        self.assertEqual(
            len(
                plan["fr_posts"]
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
