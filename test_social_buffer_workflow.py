"""Workflow contract for Buffer-owned frozen X timing."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent

WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "publish-x-fr.yml"
)

QUEUE = (
    ROOT
    / "social"
    / "daily_queue.py"
)


class BufferWorkflowTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(
            encoding="utf-8"
        )

        cls.queue = QUEUE.read_text(
            encoding="utf-8"
        )

    def test_manual_modes_exist(self):
        self.assertIn(
            "- schedule-frozen",
            self.workflow,
        )
        self.assertIn(
            "- reconcile-buffer",
            self.workflow,
        )

    def test_build_queue_schedules_frozen_posts(self):
        self.assertIn(
            "Schedule frozen core posts with Buffer clock",
            self.workflow,
        )
        self.assertIn(
            "daily_queue.py schedule-frozen",
            self.workflow,
        )

    def test_heartbeat_repairs_future_schedule(self):
        self.assertIn(
            "Hand future frozen posts to Buffer after heartbeat",
            self.workflow,
        )

    def test_reconciliation_schedule_exists(self):
        self.assertIn(
            "40 10,12,14,19,21 * * *",
            self.workflow,
        )
        self.assertIn(
            'mode="reconcile-buffer"',
            self.workflow,
        )
        self.assertIn(
            "daily_queue.py reconcile-buffer",
            self.workflow,
        )

    def test_exact_slots_remain_as_guarded_fallbacks(self):
        for cron in (
            "45 8 * * *",
            "30 9 * * 1",
            "15 10 * * *",
            "30 11 * * *",
            "15 12 * * *",
            "30 14 * * *",
            "45 16 * * *",
            "30 18 * * *",
            "30 19 * * *",
            "2,17,32,47 8-20 * * *",
        ):
            with self.subTest(cron=cron):
                self.assertIn(
                    cron,
                    self.workflow,
                )

    def test_scheduled_items_are_not_pending(self):
        self.assertIn(
            '"scheduled"',
            self.queue,
        )
        self.assertIn(
            'item["status"] == "pending"',
            self.queue,
        )

    def test_green_noop_is_explicit(self):
        self.assertIn(
            'print("PUBLICATION=SKIPPED")',
            self.queue,
        )
        self.assertIn(
            'print("PUBLICATION=NOOP")',
            self.queue,
        )
        self.assertIn(
            'print("BUFFER_API_CALLED=false")',
            self.queue,
        )

    def test_share_now_receipt_is_submission_not_confirmation(self):
        self.assertIn(
            'print("PUBLICATION=SUBMITTED_NOW")',
            self.queue,
        )

    def test_buffer_scheduled_confirmation_is_distinct(self):
        self.assertIn(
            '"PUBLICATION=CONFIRMED "',
            self.queue,
        )


if __name__ == "__main__":
    unittest.main()
