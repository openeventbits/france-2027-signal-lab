import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SOCIAL = (
    Path(__file__).parent
    / "social"
)

if str(SOCIAL) not in sys.path:
    sys.path.insert(
        0,
        str(SOCIAL),
    )

SPEC = (
    importlib.util
    .spec_from_file_location(
        "fr27_daily_queue",
        SOCIAL / "daily_queue.py",
    )
)

MODULE = (
    importlib.util
    .module_from_spec(
        SPEC
    )
)

sys.modules[SPEC.name] = MODULE

SPEC.loader.exec_module(
    MODULE
)


class DailyQueueTests(
    unittest.TestCase
):
    def _state(self):
        return (
            MODULE.social_publish
            .build_bootstrap_state(
                {
                    "items": [
                        {
                            "id":
                                "existing-change"
                        }
                    ]
                },
                {
                    "campaign_events": [
                        {
                            "event_id":
                                "existing-event"
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

    def test_queue_is_idempotent_for_same_day(self):
        state = self._state()

        original = (
            MODULE.build_core_plan
        )

        calls = []

        def fake_plan(
            *,
            state,
            now,
        ):
            calls.append(now)

            return {
                "fr_posts": [
                    {
                        "locale": "fr",
                        "slot": "08:45",
                        "lane":
                            "today_events",
                        "key":
                            "today-events:"
                            "2026-10-05",
                        "text":
                            "Roundup",
                        "score": None,
                    }
                ],
                "en_posts": [],
            }

        MODULE.build_core_plan = (
            fake_plan
        )

        try:
            first = MODULE.build_queue(
                state=state,
                now=datetime(
                    2026,
                    10,
                    5,
                    6,
                    tzinfo=timezone.utc,
                ),
            )

            second = MODULE.build_queue(
                state=state,
                now=datetime(
                    2026,
                    10,
                    5,
                    12,
                    tzinfo=timezone.utc,
                ),
            )

        finally:
            MODULE.build_core_plan = (
                original
            )

        self.assertIs(
            first,
            second,
        )

        self.assertEqual(
            len(calls),
            1,
        )

    def test_queue_contains_locale_and_slot(self):
        queue = MODULE.new_queue(
            queue_date="2026-10-05",
            created_at=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
            posts=[
                {
                    "locale": "fr",
                    "slot": "10:15",
                    "lane":
                        "quantitative",
                    "key":
                        "quant:issues:"
                        "weekly:work_purchasing_power_pensions:"
                        "2026-10-04",
                    "text": "FR",
                    "score": 1.0,
                },
                {
                    "locale": "en",
                    "slot": "11:30",
                    "lane":
                        "quantitative",
                    "key":
                        "en-quant:agenda:"
                        "weekly:selection_strategy:"
                        "2026-10-04",
                    "text": "EN",
                    "score": 2.0,
                },
            ],
        )

        self.assertEqual(
            queue["items"][0][
                "slot"
            ],
            "10:15",
        )

        self.assertEqual(
            queue["items"][1][
                "locale"
            ],
            "en",
        )

    def test_mark_publish_updates_queue_and_cooldown_state(self):
        state = self._state()

        queue = MODULE.new_queue(
            queue_date="2026-10-05",
            created_at=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
            posts=[
                {
                    "locale": "fr",
                    "slot": "10:15",
                    "lane":
                        "quantitative",
                    "key":
                        "quant:issues:"
                        "weekly:work_purchasing_power_pensions:"
                        "2026-10-04",
                    "text": "test",
                    "score": 1.0,
                }
            ],
        )

        MODULE.attach_queue(
            state,
            queue,
        )

        item = (
            MODULE
            .pending_item_for_slot(
                queue,
                slot="10:15",
            )
        )

        MODULE.mark_item_published(
            state=state,
            item=item,
            published_at=datetime(
                2026,
                10,
                5,
                10,
                tzinfo=timezone.utc,
            ),
            buffer_post_id="123",
        )

        self.assertEqual(
            item["status"],
            "published",
        )

        self.assertEqual(
            item["buffer_post_id"],
            "123",
        )

        planner = (
            MODULE.planner_from_state(
                state
            )
        )

        self.assertEqual(
            len(
                planner[
                    "published_quantitative"
                ]
            ),
            1,
        )

    def test_pending_slot_is_unique(self):
        queue = MODULE.new_queue(
            queue_date="2026-10-05",
            created_at=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
            posts=[
                {
                    "locale": "fr",
                    "slot": "08:45",
                    "lane":
                        "today_events",
                    "key":
                        "today-events:"
                        "2026-10-05",
                    "text": "Roundup",
                    "score": None,
                }
            ],
        )

        item = (
            MODULE
            .pending_item_for_slot(
                queue,
                slot="08:45",
            )
        )

        self.assertIsNotNone(
            item
        )

        missing = (
            MODULE
            .pending_item_for_slot(
                queue,
                slot="12:15",
            )
        )

        self.assertIsNone(
            missing
        )


    def test_candidate_internal_urls_are_bilingual(self):
        fr = {
            "locale": "fr",
            "lane": "quantitative",
            "key": (
                "quant:"
                "candidate_visibility:"
                "weekly:"
                "edouard-philippe:"
                "2026-10-04"
            ),
        }

        en = {
            **fr,
            "locale": "en",
            "key": (
                "en-quant:"
                "candidate_visibility:"
                "weekly:"
                "edouard-philippe:"
                "2026-10-04"
            ),
        }

        self.assertEqual(
            MODULE.quantitative_internal_url(
                fr
            ),
            (
                "https://france2027.app/"
                "candidates/"
                "edouard-philippe/"
            ),
        )

        self.assertEqual(
            MODULE.quantitative_internal_url(
                en
            ),
            (
                "https://france2027.app/"
                "en/candidates/"
                "edouard-philippe/"
            ),
        )

    def test_issue_internal_urls_are_bilingual(self):
        fr = {
            "locale": "fr",
            "lane": "quantitative",
            "key": (
                "quant:issues:weekly:"
                "work_purchasing_power_pensions:"
                "2026-10-04"
            ),
        }

        en = {
            **fr,
            "locale": "en",
            "key": (
                "en-quant:issues:weekly:"
                "work_purchasing_power_pensions:"
                "2026-10-04"
            ),
        }

        self.assertEqual(
            MODULE.quantitative_internal_url(
                fr
            ),
            (
                "https://france2027.app/"
                "enjeux/"
                "travail-pouvoir-achat-retraites/"
            ),
        )

        self.assertEqual(
            MODULE.quantitative_internal_url(
                en
            ),
            (
                "https://france2027.app/"
                "en/issues/"
                "work-purchasing-power-pensions/"
            ),
        )

    def test_agenda_internal_urls_are_bilingual(self):
        fr = {
            "locale": "fr",
            "lane": "quantitative",
            "key": (
                "quant:agenda:weekly:"
                "selection_strategy:"
                "2026-10-04"
            ),
        }

        en = {
            **fr,
            "locale": "en",
            "key": (
                "en-quant:agenda:weekly:"
                "selection_strategy:"
                "2026-10-04"
            ),
        }

        self.assertEqual(
            MODULE.quantitative_internal_url(
                fr
            ),
            (
                "https://france2027.app/"
                "agenda/"
                "primaires-strategies-partisanes/"
            ),
        )

        self.assertEqual(
            MODULE.quantitative_internal_url(
                en
            ),
            (
                "https://france2027.app/"
                "en/agenda/"
                "primaries-party-strategy/"
            ),
        )

    def test_quantitative_queue_post_gets_internal_link_within_x_limit(self):
        queue = MODULE.new_queue(
            queue_date="2026-10-05",
            created_at=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
            posts=[
                {
                    "locale": "fr",
                    "slot": "10:15",
                    "lane":
                        "quantitative",
                    "key": (
                        "quant:"
                        "candidate_visibility:"
                        "weekly:"
                        "edouard-philippe:"
                        "2026-10-04"
                    ),
                    "text": (
                        "VISIBILITÉ CANDIDATS · "
                        "7 JOURS\n\n"
                        "Édouard Philippe : "
                        "61/281 articles."
                    ),
                    "score": 10.0,
                }
            ],
        )

        text = queue[
            "items"
        ][0]["text"]

        self.assertIn(
            (
                "https://france2027.app/"
                "candidates/"
                "edouard-philippe/"
            ),
            text,
        )

        self.assertLessEqual(
            MODULE.social_publish
            ._weighted_x_length(
                text
            ),
            280,
        )


if __name__ == "__main__":
    unittest.main()
