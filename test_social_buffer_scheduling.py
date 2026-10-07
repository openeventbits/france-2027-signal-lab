"""Buffer owns the clock for frozen FR27 core posts."""

import contextlib
import copy
import io
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(
    0,
    str(
        ROOT / "social"
    ),
)

import daily_queue as queue
import social_publish


class BufferScheduledCoreTests(
    unittest.TestCase
):
    day = "2026-10-07"

    def setUp(self):
        activation = patch.dict(os.environ, {"FR27_BUFFER_SCHEDULING_ENABLED": "true"})
        activation.start()
        self.addCleanup(activation.stop)

    def at(
        self,
        clock: str,
    ) -> datetime:
        return datetime.fromisoformat(
            f"{self.day}T{clock}:00+02:00"
        )

    def state_with_items(
        self,
        items,
    ):
        state = (
            social_publish
            .build_bootstrap_state(
                {
                    "items": []
                },
                {
                    "campaign_events": []
                },
                now=self.at(
                    "07:00"
                ),
            )
        )

        payload = {
            "schema_version": 1,
            "date": self.day,
            "created_at":
                "2026-10-07T05:00:00Z",
            "items": [],
        }

        for index, raw in enumerate(
            items
        ):
            payload[
                "items"
            ].append(
                {
                    "id":
                        raw.get(
                            "id",
                            f"{self.day}:fr:"
                            f"{raw['slot']}:"
                            f"fixture-{index}",
                        ),
                    "locale":
                        raw.get(
                            "locale",
                            "fr",
                        ),
                    "slot":
                        raw["slot"],
                    "lane":
                        raw.get(
                            "lane",
                            "newsroom",
                        ),
                    "key":
                        raw.get(
                            "key",
                            f"fixture-{index}",
                        ),
                    "text":
                        raw.get(
                            "text",
                            (
                                "Frozen signal\n\n"
                                "https://france2027.app/"
                            ),
                        ),
                    "score": None,
                    "status":
                        raw.get(
                            "status",
                            "pending",
                        ),
                    "scheduled_at":
                        raw.get(
                            "scheduled_at"
                        ),
                    "scheduled_for":
                        raw.get(
                            "scheduled_for"
                        ),
                    "published_at":
                        raw.get(
                            "published_at"
                        ),
                    "buffer_post_id":
                        raw.get(
                            "buffer_post_id"
                        ),
                    "delivery_status":
                        raw.get(
                            "delivery_status"
                        ),
                    "error_at":
                        raw.get(
                            "error_at"
                        ),
                }
            )

        queue.attach_queue(
            state,
            payload,
        )

        return state

    def items(
        self,
        state,
    ):
        return (
            state["planner"]
            ["daily_queue"]
            ["items"]
        )

    def test_buffer_custom_scheduled_payload(
        self,
    ):
        client = (
            social_publish.BufferClient(
                "token",
                "org",
                "channel",
            )
        )

        due_at = self.at(
            "10:15"
        )

        with patch.object(
            client,
            "graphql",
            return_value={
                "createPost": {
                    "post": {
                        "id": "buffer-1",
                        "status": "scheduled",
                        "dueAt":
                            "2026-10-07T08:15:00Z",
                    }
                }
            },
        ) as graphql:
            result = (
                client
                .create_scheduled_post(
                    "Bonjour",
                    due_at=due_at,
                )
            )

        self.assertEqual(
            result["id"],
            "buffer-1",
        )

        variables = (
            graphql
            .call_args
            .args[1]
        )

        payload = variables[
            "input"
        ]

        self.assertEqual(
            payload["mode"],
            "customScheduled",
        )

        self.assertEqual(
            payload["schedulingType"],
            "automatic",
        )

        self.assertEqual(
            payload["dueAt"],
            "2026-10-07T08:15:00Z",
        )

    def test_frozen_selection_excludes_late_bound(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                    "lane": "newsroom",
                    "key":
                        "issues_movers_daily:fixture",
                },
                {
                    "slot": "08:45",
                    "lane": "today_events",
                    "key":
                        "today-events:2026-10-07",
                },
                {
                    "slot": "16:45",
                    "lane": "candidate_slot",
                    "key":
                        "candidate_media_pulse_current:"
                        "slot:2026-10-07:fr",
                    "text": "",
                },
                {
                    "slot": "18:30",
                    "lane": "radar_slot",
                    "key":
                        "radar_media_publishers_current:"
                        "slot:2026-10-07:fr",
                    "text": "",
                },
                {
                    "slot": "09:30",
                    "lane":
                        "weekly_flagship_slot",
                    "key":
                        "weekly_flagship:"
                        "slot:2026-10-07:fr",
                    "text": "",
                },
            ]
        )

        selected = (
            queue
            .buffer_schedulable_items(
                queue.queue_from_state(
                    state
                ),
                now=self.at(
                    "08:00"
                ),
            )
        )

        self.assertEqual(
            [
                item["slot"]
                for item in selected
            ],
            [
                "08:45",
                "10:15",
            ],
        )

    def test_mark_scheduled_is_not_publication(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                }
            ]
        )

        item = self.items(
            state
        )[0]

        queue.mark_item_scheduled(
            state=state,
            item=item,
            scheduled_at=self.at(
                "08:00"
            ),
            scheduled_for=self.at(
                "10:15"
            ),
            buffer_post_id="buffer-1",
        )

        item = self.items(
            state
        )[0]

        self.assertEqual(
            item["status"],
            "scheduled",
        )

        self.assertIsNone(
            item["published_at"]
        )

        self.assertEqual(
            item["buffer_post_id"],
            "buffer-1",
        )

        self.assertEqual(
            item["scheduled_for"],
            "2026-10-07T08:15:00Z",
        )

    def test_scheduled_item_is_not_exact_slot_candidate(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                    "status": "scheduled",
                    "scheduled_at":
                        "2026-10-07T06:00:00Z",
                    "scheduled_for":
                        "2026-10-07T08:15:00Z",
                    "buffer_post_id":
                        "buffer-1",
                    "delivery_status":
                        "scheduled",
                }
            ]
        )

        self.assertIsNone(
            queue.pending_item_for_slot(
                queue.queue_from_state(
                    state
                ),
                slot="10:15",
            )
        )

        self.assertIsNone(
            queue.fallback_item(
                queue.queue_from_state(
                    state
                ),
                now=self.at(
                    "10:30"
                ),
            )
        )

    def test_schedule_frozen_dry_run_never_calls_buffer(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                }
            ]
        )

        args = (
            queue
            .build_parser()
            .parse_args(
                [
                    "schedule-frozen",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--now",
                    self.at(
                        "08:00"
                    ).isoformat(),
                    "--dry-run",
                ]
            )
        )

        before = copy.deepcopy(
            state
        )

        output = io.StringIO()

        with (
            patch.object(
                queue,
                "_load_json",
                return_value=state,
            ),
            patch.object(
                queue,
                "save_state",
            ) as save,
            patch.object(
                social_publish
                .BufferClient,
                "from_env",
            ) as factory,
            contextlib.redirect_stdout(
                output
            ),
        ):
            result = args.func(
                args
            )

        self.assertEqual(
            result,
            0,
        )

        self.assertIn(
            "PUBLICATION=SCHEDULE_PREVIEW",
            output.getvalue(),
        )

        factory.assert_not_called()
        save.assert_not_called()

        self.assertEqual(
            state,
            before,
        )

    def test_schedule_frozen_live_marks_buffer_scheduled(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                }
            ]
        )

        client = Mock()
        client.recent_posts.return_value = []
        client.create_scheduled_post.return_value = {
            "id": "buffer-1",
            "status": "scheduled",
            "dueAt":
                "2026-10-07T08:15:00Z",
        }

        args = (
            queue
            .build_parser()
            .parse_args(
                [
                    "schedule-frozen",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--now",
                    self.at(
                        "08:00"
                    ).isoformat(),
                ]
            )
        )

        with (
            patch.object(
                queue,
                "_load_json",
                return_value=state,
            ),
            patch.object(
                queue,
                "save_state",
            ) as save,
            patch.object(
                social_publish
                .BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(
                io.StringIO()
            ),
        ):
            result = args.func(
                args
            )

        self.assertEqual(
            result,
            0,
        )

        client.create_scheduled_post.assert_called_once()

        item = self.items(
            state
        )[0]

        self.assertEqual(
            item["status"],
            "scheduled",
        )

        self.assertEqual(
            item["buffer_post_id"],
            "buffer-1",
        )

        self.assertIsNone(
            item["published_at"]
        )

        save.assert_called_once()

    def test_schedule_recovery_does_not_duplicate_buffer_post(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                }
            ]
        )

        item = self.items(
            state
        )[0]

        client = Mock()

        client.recent_posts.return_value = [
            {
                "id": "existing-1",
                "text": item["text"],
                "status": "scheduled",
                "dueAt":
                    "2026-10-07T08:15:00Z",
            }
        ]

        args = (
            queue
            .build_parser()
            .parse_args(
                [
                    "schedule-frozen",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--now",
                    self.at(
                        "08:00"
                    ).isoformat(),
                ]
            )
        )

        with (
            patch.object(
                queue,
                "_load_json",
                return_value=state,
            ),
            patch.object(
                queue,
                "save_state",
            ),
            patch.object(
                social_publish
                .BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(
                io.StringIO()
            ),
        ):
            self.assertEqual(
                args.func(
                    args
                ),
                0,
            )

        client.create_scheduled_post.assert_not_called()

        self.assertEqual(
            self.items(
                state
            )[0]["buffer_post_id"],
            "existing-1",
        )

    def test_reconcile_sent_confirms_publication(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                }
            ]
        )

        item = self.items(
            state
        )[0]

        queue.mark_item_scheduled(
            state=state,
            item=item,
            scheduled_at=self.at(
                "08:00"
            ),
            scheduled_for=self.at(
                "10:15"
            ),
            buffer_post_id="buffer-1",
        )

        client = Mock()

        client.get_post.return_value = {
            "id": "buffer-1",
            "text": item["text"],
            "status": "sent",
            "dueAt": "2026-10-07T08:15:00Z",
        }

        args = (
            queue
            .build_parser()
            .parse_args(
                [
                    "reconcile-buffer",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--now",
                    self.at(
                        "10:30"
                    ).isoformat(),
                ]
            )
        )

        with (
            patch.object(
                queue,
                "_load_json",
                return_value=state,
            ),
            patch.object(
                queue,
                "save_state",
            ) as save,
            patch.object(
                social_publish
                .BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(
                io.StringIO()
            ),
        ):
            self.assertEqual(
                args.func(
                    args
                ),
                0,
            )

        item = self.items(
            state
        )[0]

        self.assertEqual(
            item["status"],
            "published",
        )

        self.assertEqual(
            item["delivery_status"],
            "sent",
        )

        self.assertEqual(
            item["published_at"],
            "2026-10-07T08:15:00Z",
        )

        save.assert_called_once()

    def test_reconcile_error_is_explicit_failure(
        self,
    ):
        state = self.state_with_items(
            [
                {
                    "slot": "10:15",
                }
            ]
        )

        item = self.items(
            state
        )[0]

        queue.mark_item_scheduled(
            state=state,
            item=item,
            scheduled_at=self.at(
                "08:00"
            ),
            scheduled_for=self.at(
                "10:15"
            ),
            buffer_post_id="buffer-1",
        )

        client = Mock()

        client.get_post.return_value = {
            "id": "buffer-1",
            "text": item["text"],
            "status": "error",
            "dueAt": "2026-10-07T08:15:00Z",
        }

        args = (
            queue
            .build_parser()
            .parse_args(
                [
                    "reconcile-buffer",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--now",
                    self.at(
                        "10:30"
                    ).isoformat(),
                ]
            )
        )

        with (
            patch.object(
                queue,
                "_load_json",
                return_value=state,
            ),
            patch.object(
                queue,
                "save_state",
            ) as save,
            patch.object(
                social_publish
                .BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(
                io.StringIO()
            ),
        ):
            self.assertEqual(
                args.func(
                    args
                ),
                0,
            )

        item = self.items(
            state
        )[0]

        self.assertEqual(
            item["status"],
            "error",
        )

        self.assertEqual(
            item["delivery_status"],
            "error",
        )

        self.assertIsNotNone(
            item["error_at"]
        )

        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
