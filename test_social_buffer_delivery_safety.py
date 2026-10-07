import contextlib
import io
import copy
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))

import daily_queue as queue
import social_publish


class BufferDeliverySafetyTests(unittest.TestCase):

    def setUp(self):
        activation = patch.dict(os.environ, {"FR27_BUFFER_SCHEDULING_ENABLED": "true"})
        activation.start()
        self.addCleanup(activation.stop)

    def test_live_scheduled_delivery_requires_explicit_activation(self):
        for command in ("schedule-frozen", "reconcile-buffer"):
            for flag in (None, "false", "TRUE", "1"):
                with self.subTest(command=command, flag=flag):
                    item = {"slot": "10:15", "text": "Frozen"}
                    if command == "reconcile-buffer":
                        item.update(status="scheduled", buffer_post_id="buffer-1")
                    state = self.state_with_queue(items=[item])
                    before = copy.deepcopy(state)
                    args = queue.build_parser().parse_args([
                        command, "--state", "unused", "--state-output", "unused",
                        "--now", self.at("2026-10-07", "08:00").isoformat(),
                    ])
                    with (patch.dict(os.environ, {}, clear=True),
                          patch.object(queue, "_load_json", return_value=state),
                          patch.object(queue, "save_state") as save,
                          patch.object(social_publish.BufferClient, "from_env") as factory,
                          contextlib.redirect_stdout(io.StringIO())):
                        if flag is not None:
                            os.environ["FR27_BUFFER_SCHEDULING_ENABLED"] = flag
                        with self.assertRaisesRegex(ValueError, "explicitly true"):
                            args.func(args)
                        args.dry_run = True
                        self.assertEqual(args.func(args), 0)
                    factory.assert_not_called()
                    save.assert_not_called()
                    self.assertEqual(state, before)

    def test_build_queue_without_buffer_credentials_or_scheduling_activation(self):
        state = social_publish.build_bootstrap_state(
            {"items": []}, {"campaign_events": []}, now=self.at("2026-10-07", "08:00"))
        args = queue.build_parser().parse_args([
            "build", "--state", "unused", "--state-output", "unused",
            "--now", self.at("2026-10-07", "08:25").isoformat(),
        ])
        with (patch.dict(os.environ, {}, clear=True),
              patch.object(queue, "_load_json", return_value=state),
              patch.object(queue, "build_core_plan", return_value={"fr_posts": [], "en_posts": []}),
              patch.object(queue, "save_state") as save,
              patch.object(social_publish.BufferClient, "from_env") as factory,
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(args.func(args), 0)
        self.assertEqual(queue.queue_from_state(state)["date"], "2026-10-07")
        save.assert_called_once()
        factory.assert_not_called()

    def test_frozen_crash_window_error_is_not_rescheduled(self):
        state = self.state_with_queue(items=[{"slot": "10:15", "text": "Frozen"}])
        client = Mock()
        client.recent_posts.return_value = [{
            "id": "failed-1", "text": "Frozen", "status": "error",
            "dueAt": "2026-10-07T08:15:00Z",
        }]
        args = queue.build_parser().parse_args([
            "schedule-frozen", "--state", "unused", "--state-output", "unused",
            "--now", self.at("2026-10-07", "08:00").isoformat(),
        ])
        with (patch.object(queue, "_load_json", return_value=state),
              patch.object(queue, "save_state") as save,
              patch.object(social_publish.BufferClient, "from_env", return_value=client),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(args.func(args), 0)
        client.create_scheduled_post.assert_not_called()
        self.assertEqual(self.items(state)[0]["status"], "error")
        self.assertEqual(self.items(state)[0]["buffer_post_id"], "failed-1")
        save.assert_called_once()

    def test_share_now_inflight_receipt_prevents_duplicate_with_scheduling_disabled(self):
        for status in ("scheduled", "sending"):
            with self.subTest(status=status):
                state = self.state_with_queue(items=[{"slot": "10:15", "text": "Frozen"}])
                client = Mock()
                client.recent_posts.return_value = [{
                    "id": "inflight-1", "text": "Frozen", "status": status,
                    "createdAt": "2026-10-07T08:30:00Z", "dueAt": "",
                }]
                args = queue.build_parser().parse_args([
                    "slot", "--slot", "10:15", "--state", "unused", "--state-output", "unused",
                    "--now", self.at("2026-10-07", "10:30").isoformat(),
                ])
                with (patch.dict(os.environ, {"FR27_BUFFER_SCHEDULING_ENABLED": "false"}),
                      patch.object(queue, "_load_json", return_value=state),
                      patch.object(queue, "save_state") as save,
                      patch.object(social_publish.BufferClient, "from_env", return_value=client),
                      contextlib.redirect_stdout(io.StringIO())):
                    self.assertEqual(args.func(args), 0)
                client.create_post.assert_not_called()
                self.assertEqual(self.items(state)[0]["status"], "published")
                self.assertEqual(self.items(state)[0]["buffer_post_id"], "inflight-1")
                save.assert_called_once()

    def at(self, day, clock):
        return datetime.fromisoformat(
            f"{day}T{clock}:00+02:00"
        )

    def state_with_queue(
        self,
        day="2026-10-07",
        items=None,
    ):
        items = items or []

        state = social_publish.build_bootstrap_state(
            {"items": []},
            {"campaign_events": []},
            now=self.at(day, "07:00"),
        )

        payload = {
            "schema_version": 1,
            "date": day,
            "created_at": f"{day}T05:00:00Z",
            "items": [],
        }

        for i, raw in enumerate(items):
            payload["items"].append(
                {
                    "id": raw.get(
                        "id",
                        f"{day}:fr:{raw['slot']}:safety-{i}",
                    ),
                    "locale": raw.get("locale", "fr"),
                    "slot": raw["slot"],
                    "lane": raw.get("lane", "newsroom"),
                    "key": raw.get("key", f"safety-{i}"),
                    "text": raw.get("text", "Frozen signal"),
                    "score": None,
                    "status": raw.get("status", "pending"),
                    "scheduled_at": raw.get("scheduled_at"),
                    "scheduled_for": raw.get("scheduled_for"),
                    "published_at": raw.get("published_at"),
                    "buffer_post_id": raw.get("buffer_post_id"),
                    "delivery_status": raw.get("delivery_status"),
                    "error_at": raw.get("error_at"),
                }
            )

        queue.attach_queue(state, payload)
        return state

    def items(self, state):
        return state["planner"]["daily_queue"]["items"]

    def test_recent_posts_query_has_no_sort(self):
        client = social_publish.BufferClient(
            "token",
            "org",
            "channel",
        )

        with patch.object(
            client,
            "graphql",
            return_value={"posts": {"edges": []}},
        ) as graphql:
            client.recent_posts(
                since=datetime(
                    2026,
                    10,
                    7,
                    tzinfo=timezone.utc,
                )
            )

        self.assertNotIn(
            "sort:",
            graphql.call_args.args[0],
        )

    def test_slot_selector(self):
        state = self.state_with_queue(
            items=[
                {"slot": "10:15", "text": "A"},
                {
                    "slot": "11:30",
                    "locale": "en",
                    "text": "B",
                },
            ]
        )

        selected = queue.buffer_schedulable_items(
            queue.queue_from_state(state),
            now=self.at(
                "2026-10-07",
                "08:00",
            ),
            target_slot="11:30",
        )

        self.assertEqual(
            [x["slot"] for x in selected],
            ["11:30"],
        )

    def test_rollover_blocks_scheduled(self):
        state = self.state_with_queue(
            day="2026-10-06",
            items=[
                {
                    "slot": "19:30",
                    "status": "scheduled",
                    "scheduled_at":
                        "2026-10-06T08:00:00Z",
                    "scheduled_for":
                        "2026-10-06T17:30:00Z",
                    "buffer_post_id": "buf-1",
                    "delivery_status": "scheduled",
                }
            ],
        )

        with self.assertRaisesRegex(
            ValueError,
            "unresolved Buffer deliveries",
        ):
            queue.build_queue(
                state=state,
                now=self.at(
                    "2026-10-07",
                    "08:25",
                ),
            )

    def test_exact_scheduled_not_published(self):
        state = self.state_with_queue(
            items=[
                {
                    "slot": "10:15",
                    "text": "Exact signal",
                }
            ]
        )

        client = Mock()

        client.recent_posts.return_value = [
            {
                "id": "buf-scheduled",
                "text": "Exact signal",
                "status": "scheduled",
                "createdAt":
                    "2026-10-07T06:00:00Z",
                "dueAt":
                    "2026-10-07T08:15:00Z",
            }
        ]

        args = (
            queue.build_parser()
            .parse_args(
                [
                    "slot",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--slot",
                    "10:15",
                    "--now",
                    self.at(
                        "2026-10-07",
                        "10:15",
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
                social_publish.BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            args.func(args)

        item = self.items(state)[0]

        self.assertEqual(
            item["status"],
            "scheduled",
        )

        self.assertIsNone(
            item["published_at"]
        )

        client.create_post.assert_not_called()

    def test_exact_sent_confirms_publication(self):
        state = self.state_with_queue(
            items=[
                {
                    "slot": "10:15",
                    "text": "Sent signal",
                }
            ]
        )

        client = Mock()

        client.recent_posts.return_value = [
            {
                "id": "buf-sent",
                "text": "Sent signal",
                "status": "sent",
                "createdAt":
                    "2026-10-07T06:00:00Z",
                "dueAt":
                    "2026-10-07T08:15:00Z",
            }
        ]

        args = (
            queue.build_parser()
            .parse_args(
                [
                    "slot",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--slot",
                    "10:15",
                    "--now",
                    self.at(
                        "2026-10-07",
                        "10:20",
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
                social_publish.BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            args.func(args)

        item = self.items(state)[0]

        self.assertEqual(
            item["status"],
            "published",
        )

        self.assertEqual(
            item["buffer_post_id"],
            "buf-sent",
        )

        client.create_post.assert_not_called()

    def test_share_now_sent_receipt_recovers_without_duplicate(
        self,
    ):
        state = self.state_with_queue(
            items=[
                {
                    "slot": "10:15",
                    "text": "ShareNow recovery signal",
                }
            ]
        )

        client = Mock()

        client.recent_posts.return_value = [
            {
                "id": "share-now-sent",
                "text": "ShareNow recovery signal",
                "status": "sent",
                "createdAt":
                    "2026-10-07T08:31:00Z",
                "dueAt":
                    "2026-10-07T08:31:00Z",
            }
        ]

        args = (
            queue.build_parser()
            .parse_args(
                [
                    "slot",
                    "--state",
                    "unused.json",
                    "--state-output",
                    "unused-output.json",
                    "--slot",
                    "10:15",
                    "--now",
                    self.at(
                        "2026-10-07",
                        "10:32",
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
                social_publish.BufferClient,
                "from_env",
                return_value=client,
            ),
            contextlib.redirect_stdout(
                io.StringIO()
            ),
        ):
            self.assertEqual(
                args.func(args),
                0,
            )

        item = self.items(state)[0]

        self.assertEqual(
            item["status"],
            "published",
        )

        self.assertEqual(
            item["buffer_post_id"],
            "share-now-sent",
        )

        client.create_post.assert_not_called()

    def test_manual_workflow_has_slot(self):
        text = (
            ROOT
            / ".github"
            / "workflows"
            / "publish-x-fr.yml"
        ).read_text(encoding="utf-8")

        start = text.index(
            "Schedule or preview frozen core posts manually"
        )

        end = text.index(
            "Recover or preview one missed core queue slot",
            start,
        )

        manual = text[start:end]

        self.assertIn(
            '--slot "${{ steps.mode.outputs.slot }}"',
            manual,
        )

        self.assertIn(
            "Reconcile prior Buffer delivery before queue rollover",
            text,
        )


if __name__ == "__main__":
    unittest.main()
