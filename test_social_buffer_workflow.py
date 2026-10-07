"""Workflow contract for Buffer-owned frozen X timing."""

import unittest
import re
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

    def step(self, name):
        return self.workflow.split("      - name: " + name + "\n", 1)[1].split("      - name:", 1)[0]

    def allows(self, name, *, mode, flag="", publish="true", event="schedule", eligible="", master="true"):
        block = self.step(name)
        expression = block.split("        if:", 1)[1].split("        shell:", 1)[0].strip()
        expression = expression.removeprefix(">-").strip()
        values = {
            "steps.mode.outputs.mode": mode,
            "steps.mode.outputs.publish": publish,
            "vars.FR27_BUFFER_SCHEDULING_ENABLED": flag,
            "vars.FR27_SOCIAL_ENABLED": master,
            "github.event_name": event,
            "steps.dynamic_timeliness.outputs.eligible": eligible,
        }
        expression = re.sub(r"(?:steps|vars|github)\.[\w.]+", lambda match: repr(values[match[0]]), expression)
        expression = expression.replace("&&", " and ").replace("||", " or ")
        return eval(" ".join(expression.split()), {"__builtins__": {}}, {})

    def test_scheduling_gate_behavior_matrix(self):
        for name, mode in (
            ("Reconcile prior Buffer delivery before queue rollover", "build-queue"),
            ("Schedule frozen core posts with Buffer clock", "build-queue"),
            ("Schedule or preview frozen core posts manually", "schedule-frozen"),
            ("Hand future frozen posts to Buffer after heartbeat", "scheduler-tick"),
            ("Reconcile Buffer scheduled delivery state", "reconcile-buffer"),
        ):
            for flag in ("", "false", "TRUE", "true"):
                with self.subTest(step=name, flag=flag):
                    self.assertEqual(self.allows(name, mode=mode, flag=flag), flag == "true")
                    self.assertTrue(self.allows(name, mode=mode, flag=flag, publish="false"))

    def test_build_without_buffer_credentials_and_sharenow_with_scheduling_disabled(self):
        for flag in ("", "false"):
            self.assertTrue(self.allows("Build immutable daily core queue", mode="build-queue", flag=flag))
            self.assertFalse(self.allows("Validate Buffer configuration", mode="build-queue", flag=flag))
            for mode, name in (
                ("slot", "Publish or preview core queue slot"),
                ("scheduler-tick", "Recover or preview one missed core queue slot"),
                ("updates", "Publish or preview one dynamic development"),
            ):
                self.assertTrue(self.allows(name, mode=mode, flag=flag, eligible="true"))
                self.assertTrue(self.allows("Validate Buffer configuration", mode=mode, flag=flag, eligible="true"))

    def test_dynamic_guard_fails_closed_for_missing_output_and_allows_manual_updates(self):
        for name in ("Validate Buffer configuration", "Publish or preview one dynamic development"):
            for eligible in ("", "false", "true"):
                self.assertEqual(self.allows(name, mode="updates", eligible=eligible), eligible == "true")
                self.assertTrue(self.allows(name, mode="updates", event="workflow_dispatch", eligible=eligible))
        block = self.step("Publish or preview one dynamic development")
        self.assertIn('args+=(--scheduled-target "$target")', block)
        self.assertIn('[[ -n "$target" ]]', block)

    def test_master_gate_blocks_live_manual_execution_only(self):
        for master in ("", "false", "true"):
            name = "Require master activation for live manual execution"
            self.assertEqual(self.allows(name, mode="updates", event="workflow_dispatch", master=master), master != "true")
            self.assertFalse(self.allows(name, mode="updates", event="workflow_dispatch", master=master, publish="false"))

    def test_dynamic_cron_to_slot_mapping_is_exact(self):
        for cron, slot in (("5 9 * * *", "09:05"), ("5 13 * * *", "13:05"), ("5 17 * * *", "17:05"), ("5 20 * * *", "20:05")):
            self.assertIn(f"'{cron}')\n                mode=\"updates\"\n                slot=\"{slot}\"", self.workflow)
            self.assertIn(f"- cron: '{cron}'\n      timezone: 'Europe/Paris'", self.workflow)

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

    def test_independent_buffer_scheduling_flag_exists(
        self,
    ):
        self.assertIn(
            "FR27_BUFFER_SCHEDULING_ENABLED",
            self.workflow,
        )

        self.assertGreaterEqual(
            self.workflow.count(
                "vars.FR27_BUFFER_SCHEDULING_ENABLED "
                "== 'true'"
            ),
            5,
        )

    def test_dynamic_crons_are_distinct(
        self,
    ):
        self.assertNotIn(
            "5 9,13,17,20 * * *",
            self.workflow,
        )

        for cron, slot in (
            ("5 9 * * *", "09:05"),
            ("5 13 * * *", "13:05"),
            ("5 17 * * *", "17:05"),
            ("5 20 * * *", "20:05"),
        ):
            with self.subTest(
                cron=cron,
                slot=slot,
            ):
                self.assertIn(
                    cron,
                    self.workflow,
                )
                self.assertIn(
                    f'slot="{slot}"',
                    self.workflow,
                )

    def test_dynamic_stale_guard_is_sixty_minutes(
        self,
    ):
        self.assertIn(
            "0.0 <= lateness <= 60.0",
            self.workflow,
        )
        self.assertIn(
            "DYNAMIC_TIMELINESS=EXPIRED",
            self.workflow,
        )
        self.assertIn(
            "REASON=DYNAMIC_SLOT_STALE",
            self.workflow,
        )

    def test_buffer_flag_is_in_summary(
        self,
    ):
        self.assertIn(
            "FR27_BUFFER_SCHEDULING_ENABLED",
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
