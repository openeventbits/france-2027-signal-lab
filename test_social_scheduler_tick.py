"""Core-only recovery, inclusive Paris windows, existing executor and state safety."""
import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))
import daily_queue as queue


class SchedulerTickTests(unittest.TestCase):
    # Synthetic calendar fixture, independent of production artifact freshness.
    day = date(2026, 10, 6)

    def at(self, clock, day=None):
        return datetime.combine(day or self.day, time.fromisoformat(clock),
                                tzinfo=queue.social_publish.PARIS)

    def state(self, slots=("14:30",), day=None):
        day = day or self.day
        now = self.at("08:25", day)
        state = queue.social_publish.build_bootstrap_state(
            {"items": []}, {"campaign_events": []}, now=now)
        posts = [dict(locale="fr", slot=slot, lane="today_events", key=f"fixture:{slot}",
                      text=f"Frozen {slot}", score=None) for slot in slots]
        queue.attach_queue(state, queue.new_queue(queue_date=day.isoformat(), created_at=now, posts=posts))
        return state

    def items(self, state):
        return state["planner"]["daily_queue"]["items"]

    def select(self, state, clock, day=None):
        return queue.fallback_item(queue.queue_from_state(state), now=self.at(clock, day))

    def invoke(self, state, clock, *, dry_run=True, client=None, day=None):
        args = queue.build_parser().parse_args(["scheduler-tick", "--state", "unused.json",
            "--state-output", "unused-output.json", "--now", self.at(clock, day).isoformat()]
            + (["--dry-run"] if dry_run else []))
        output = io.StringIO()
        with (patch.object(queue, "_load_json", return_value=state),
              patch.object(queue, "save_state") as save,
              patch.object(queue.social_publish.BufferClient, "from_env", return_value=client) as factory,
              contextlib.redirect_stdout(output)):
            result = args.func(args)
        return result, output.getvalue(), save, factory

    def test_exact_due_slot(self):
        self.assertEqual(self.select(self.state(), "14:30")["slot"], "14:30")

    def test_fifteen_minutes_late(self):
        self.assertEqual(self.select(self.state(), "14:45")["slot"], "14:30")

    def test_fifty_nine_minutes_late(self):
        self.assertIsNotNone(self.select(self.state(), "15:29"))

    def test_sixty_minutes_inclusive(self):
        self.assertIsNotNone(self.select(self.state(), "15:30"))

    def test_sixty_one_minutes_late(self):
        self.assertIsNone(self.select(self.state(), "15:31"))

    def test_one_second_past_limit(self):
        self.assertIsNone(self.select(self.state(), "15:30:01"))

    def test_future_item(self):
        self.assertIsNone(self.select(self.state(), "14:29:59"))

    def test_published_item(self):
        state = self.state()
        self.items(state)[0]["status"] = "published"
        self.assertIsNone(self.select(state, "14:30"))

    def test_controlled_issues_item_never_selected(self):
        state = self.state(("08:45", "10:15", "11:30", "12:15", "14:30", "16:45"))
        item = next(i for i in self.items(state) if i["slot"] == "10:15")
        item.update(status="published", buffer_post_id="controlled-receipt")
        for clock in ("10:15", "10:30", "11:15", "15:12", "15:31", "16:47", "17:02"):
            with self.subTest(clock=clock):
                selected = self.select(state, clock)
                self.assertTrue(selected is None or selected["id"] != item["id"])
        self.assertEqual(self.select(state, "15:12")["slot"], "14:30")
        self.assertIsNone(self.select(state, "15:31"))
        self.assertEqual(self.select(state, "16:47")["slot"], "16:45")
        next(i for i in self.items(state) if i["slot"] == "16:45")["status"] = "published"
        self.assertIsNone(self.select(state, "17:02"))

    def test_oldest_due_independent_of_list_order(self):
        state = self.state(("14:30", "14:45", "15:00"))
        self.items(state).reverse()
        self.assertEqual(self.select(state, "15:12")["slot"], "14:30")

    def test_max_one_publication(self):
        state = self.state(("14:30", "14:45", "15:00"))
        client = Mock()
        client.recent_post_texts.return_value = set()
        client.create_post.return_value = "mock-receipt"
        result, _, save, factory = self.invoke(state, "15:12", dry_run=False, client=client)
        self.assertEqual(result, 0)
        client.create_post.assert_called_once_with("Frozen 14:30")
        factory.assert_called_once()
        save.assert_called_once()
        self.assertEqual([i["status"] for i in self.items(state)], ["published", "pending", "pending"])

    def test_previous_queue_date_ignored(self):
        self.assertIsNone(self.select(self.state(day=self.day - timedelta(days=1)), "14:30"))

    def test_misdated_item_ignored(self):
        state = self.state()
        self.items(state)[0]["id"] = "2026-10-05:fr:14:30:fixture"
        self.assertIsNone(self.select(state, "14:30"))

    def test_missing_queue_calls_canonical_builder(self):
        state = self.state()
        del state["planner"]["daily_queue"]
        with patch.object(queue, "build_core_plan", return_value={"fr_posts": [], "en_posts": []}) as builder:
            _, text, save, factory = self.invoke(state, "08:32")
        builder.assert_called_once()
        self.assertEqual(queue.queue_from_state(state)["date"], self.day.isoformat())
        self.assertIn("scheduler_queue_built=true", text)
        save.assert_not_called()
        factory.assert_not_called()

    def test_previous_day_queue_rebuilt_never_executed(self):
        state = self.state(day=self.day - timedelta(days=1))
        with patch.object(queue, "build_core_plan", return_value={"fr_posts": [], "en_posts": []}) as builder:
            _, text, save, factory = self.invoke(state, "14:30")
        builder.assert_called_once()
        self.assertIn("scheduler_tick=NOOP", text)
        self.assertEqual(queue.queue_from_state(state)["date"], self.day.isoformat())
        factory.assert_not_called()
        save.assert_not_called()

    def test_live_new_queue_persisted_on_noop(self):
        state = self.state()
        del state["planner"]["daily_queue"]
        with patch.object(queue, "build_core_plan", return_value={"fr_posts": [], "en_posts": []}):
            _, _, save, factory = self.invoke(state, "08:32", dry_run=False)
        save.assert_called_once()
        factory.assert_not_called()

    def test_existing_queue_noop_does_not_write(self):
        state = self.state()
        before = copy.deepcopy(state)
        _, text, save, factory = self.invoke(state, "15:31", dry_run=False)
        self.assertIn("scheduler_tick=NOOP", text)
        self.assertEqual(state, before)
        save.assert_not_called()
        factory.assert_not_called()

    def test_dry_run_zero_buffer_and_no_state_mutation(self):
        state = self.state()
        before = copy.deepcopy(state)
        _, text, save, factory = self.invoke(state, "14:45")
        self.assertIn("slot=14:30 lateness_minutes=15", text)
        self.assertEqual(state, before)
        factory.assert_not_called()
        save.assert_not_called()

    def test_dry_run_missing_queue_input_bytes_unchanged(self):
        state = self.state()
        del state["planner"]["daily_queue"]
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "state.json", Path(directory) / "output.json"
            source.write_text(json.dumps(state), encoding="utf-8")
            original = source.read_bytes()
            args = queue.build_parser().parse_args(["scheduler-tick", "--state", str(source),
                "--state-output", str(output), "--now", self.at("08:32").isoformat(), "--dry-run"])
            with (patch.object(queue, "build_core_plan", return_value={"fr_posts": [], "en_posts": []}),
                  patch.object(queue.social_publish.BufferClient, "from_env") as factory,
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(args.func(args), 0)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(output.exists())
            factory.assert_not_called()

    def test_buffer_failure_leaves_pending_and_writes_nothing(self):
        state = self.state()
        before = copy.deepcopy(state)
        client = Mock()
        client.recent_post_texts.return_value = set()
        client.create_post.side_effect = RuntimeError("mock API failure")
        args = SimpleNamespace(state="unused", state_output="unused", now=self.at("14:45").isoformat(),
                               dry_run=False)
        with (patch.object(queue, "_load_json", return_value=state),
              patch.object(queue, "save_state") as save,
              patch.object(queue.social_publish.BufferClient, "from_env", return_value=client),
              contextlib.redirect_stdout(io.StringIO())):
            with self.assertRaisesRegex(RuntimeError, "mock API failure"):
                queue.run_scheduler_tick(args)
        self.assertEqual(state, before)
        save.assert_not_called()

    def test_exact_then_heartbeat_cannot_duplicate(self):
        state = self.state()
        client = Mock()
        client.recent_post_texts.return_value = set()
        client.create_post.return_value = "exact-receipt"
        args = SimpleNamespace(slot="14:30", state_output="unused", dry_run=False)
        with (patch.object(queue.social_publish.BufferClient, "from_env", return_value=client),
              patch.object(queue, "save_state"), contextlib.redirect_stdout(io.StringIO())):
            queue.execute_slot(args, state=state, now=self.at("14:30"))
        _, text, save, factory = self.invoke(state, "14:47", dry_run=False, client=client)
        self.assertIn("scheduler_tick=NOOP", text)
        client.create_post.assert_called_once()
        factory.assert_not_called()
        save.assert_not_called()

    def test_heartbeat_then_exact_cannot_duplicate(self):
        state = self.state()
        client = Mock()
        client.recent_post_texts.return_value = set()
        client.create_post.return_value = "tick-receipt"
        self.invoke(state, "14:47", dry_run=False, client=client)
        args = SimpleNamespace(slot="14:30", state_output="unused", dry_run=False)
        with (patch.object(queue.social_publish.BufferClient, "from_env") as factory,
              patch.object(queue, "save_state"), contextlib.redirect_stdout(io.StringIO())):
            queue.execute_slot(args, state=state, now=self.at("14:48"))
        factory.assert_not_called()

    def test_existing_buffer_duplicate_resolves_without_creation(self):
        state = self.state()
        client = Mock()
        client.recent_post_texts.return_value = {"Frozen 14:30"}
        self.invoke(state, "14:47", dry_run=False, client=client)
        client.create_post.assert_not_called()
        self.assertEqual(self.items(state)[0]["buffer_post_id"], "buffer-existing")

    def instruction_state(self, instruction, day=None):
        state = self.state((), day=day)
        now = self.at("08:25", day)
        lanes = {queue.candidate_media_pulse.PRODUCT_TYPE: "candidate_slot",
                 queue.radar_media.PRODUCT_TYPE: "radar_slot",
                 queue.weekly_flagship.PRODUCT_TYPE: "weekly_flagship_slot"}
        queue.attach_queue(state, queue.new_queue(queue_date=(day or self.day).isoformat(), created_at=now,
            posts=[dict(locale="fr", slot=instruction.slot, lane=lanes[instruction.product_id.split(":")[0]],
                        key=instruction.product_id, text="", score=None)]))
        return state

    def test_candidate_uses_existing_late_bound_executor(self):
        contract = queue.candidate_media_pulse
        state = self.instruction_state(contract.slot_instruction(self.day))
        product = SimpleNamespace(locale="fr", slot="16:45", product_id=f"{contract.PRODUCT_TYPE}:fresh:{self.day}:fr",
            text="Fresh candidate", score=1, current_start="2026-09-30", current_end=self.day.isoformat(),
            destination_url="https://france2027.app/candidates/fresh/")
        before = copy.deepcopy(state)
        with (patch.object(contract, "load_json", return_value={}),
              patch.object(contract, "build_product", return_value=product) as build,
              patch.object(queue, "execute_slot", wraps=queue.execute_slot) as executor):
            _, text, save, factory = self.invoke(state, "16:47")
        executor.assert_called_once()
        build.assert_called_once()
        self.assertIn("Fresh candidate", text)
        self.assertEqual(state, before)
        save.assert_not_called()
        factory.assert_not_called()

    def test_radar_uses_existing_late_bound_executor(self):
        contract = queue.radar_media
        state = self.instruction_state(contract.slot_instruction(self.day))
        product = SimpleNamespace(product_id="resolved-radar", text="Fresh Radar", payload={"synthetic": True},
            window_start="2026-09-07", window_end=self.day.isoformat())
        before = copy.deepcopy(state)
        with (patch.object(contract, "load_product", return_value=product) as load,
              patch.object(queue, "execute_slot", wraps=queue.execute_slot) as executor):
            _, text, save, factory = self.invoke(state, "18:32")
        executor.assert_called_once()
        load.assert_called_once()
        self.assertIn("Fresh Radar", text)
        self.assertEqual(state, before)
        save.assert_not_called()
        factory.assert_not_called()

    def test_flagship_quality_skip_unchanged_no_filler(self):
        monday = self.day - timedelta(days=1)
        contract = queue.weekly_flagship
        state = self.instruction_state(contract.slot_instruction(monday), day=monday)
        before = copy.deepcopy(state)
        with (patch.object(contract, "load_product", side_effect=ValueError("not ready")) as load,
              patch.object(queue, "execute_slot", wraps=queue.execute_slot) as executor):
            _, text, save, factory = self.invoke(state, "09:32", day=monday)
        executor.assert_called_once()
        load.assert_called_once()
        self.assertIn("late_bound_flagship_skipped=not ready", text)
        self.assertEqual(state, before)
        save.assert_not_called()
        factory.assert_not_called()

    def test_candidate_expected_skip_leaves_pending_without_filler(self):
        contract = queue.candidate_media_pulse
        state = self.instruction_state(contract.slot_instruction(self.day))
        before = copy.deepcopy(state)
        with (patch.object(contract, "load_json", return_value={}),
              patch.object(contract, "build_product", return_value=None)):
            _, text, save, factory = self.invoke(state, "16:47", dry_run=False)
        self.assertIn("late_bound_candidate_skipped=", text)
        self.assertEqual(state, before)
        save.assert_not_called()
        factory.assert_not_called()

    def test_old_state_upgrade_unchanged(self):
        state = self.state()
        del state["planner"]
        state["seen"]["recent_changes"] = ["old-seen"]
        with patch.object(queue, "build_core_plan", return_value={"fr_posts": [], "en_posts": []}):
            _, _, save, factory = self.invoke(state, "08:32")
        self.assertEqual(state["seen"]["recent_changes"], ["old-seen"])
        self.assertEqual(state["planner"]["schema_version"], 1)
        save.assert_not_called()
        factory.assert_not_called()

    def test_paris_calendar_and_dst_conversion(self):
        for day, utc_clock in ((date(2026, 10, 6), "12:30"), (date(2026, 12, 1), "13:30")):
            with self.subTest(day=day):
                now = datetime.combine(day, time.fromisoformat(utc_clock), tzinfo=timezone.utc)
                self.assertEqual(queue.fallback_item(queue.queue_from_state(self.state(day=day)), now=now)["slot"], "14:30")

    def test_workflow_preserves_all_exact_schedules_adds_one_heartbeat(self):
        path = ".github/workflows/publish-x-fr.yml"
        after = (ROOT / path).read_text(encoding="utf-8")
        pattern = r"- cron: '([^']+)'\s+timezone: '([^']+)'"
        old = [(cron, "Europe/Paris") for cron in ("25 8 * * *", "45 8 * * *", "30 9 * * 1",
            "15 10 * * *", "30 11 * * *", "15 12 * * *", "30 14 * * *", "45 16 * * *",
            "30 18 * * *", "30 19 * * *", "5 9,13,17,20 * * *")]
        new = re.findall(pattern, after)
        self.assertEqual(new, old + [("2,17,32,47 8-20 * * *", "Europe/Paris")])
        self.assertIn("mode=\"scheduler-tick\"", after)
        self.assertIn("publish=\"true\"", after)
        self.assertIn("          - scheduler-tick", after)
        self.assertIn("python -B social/daily_queue.py scheduler-tick", after)
        self.assertIn("group: fr27-social-publish\n  cancel-in-progress: false", after)
        self.assertIn("vars.FR27_SOCIAL_ENABLED == 'true'", after)
        self.assertIn('fromJSON(\'["bootstrap","build-queue","slot","scheduler-tick","updates"]\')', after)
        self.assertIn('fromJSON(\'["build-queue","slot","scheduler-tick","updates"]\')', after)
        self.assertIn('if [[ ! -f "$output" ]]; then', after)


if __name__ == "__main__":
    unittest.main()
