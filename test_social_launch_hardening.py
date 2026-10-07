"""Additive identity, old-state execution and cold-start V2.1 isolation."""
import argparse
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))
import daily_plan
import daily_queue as queue
import queue_metadata as metadata
import newsroom_products
import candidate_media_pulse
import radar_media
import weekly_flagship


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def real_dry_run_matrix():
    """Real CLI parsers/runners, checked-in sources, temporary bootstrap state.

    Only Buffer initialization is guarded. No analytical source, page, clock
    freshness or product loader is mocked to manufacture readiness.
    """
    source_end = date.fromisoformat(load("issue_coverage_history.json")["period"]["end_date"])
    ordinary = source_end + timedelta(days=1)
    if ordinary.weekday() == 0:
        ordinary += timedelta(days=1)
    monday = ordinary - timedelta(days=ordinary.weekday())
    rows = []

    def at(day, slot):
        return datetime.combine(day, time.fromisoformat(slot), tzinfo=weekly_flagship.PARIS).isoformat()

    def invoke(parser, argv):
        output = io.StringIO()
        args = parser.parse_args(argv)
        with contextlib.redirect_stdout(output):
            if args.func(args) != 0:
                raise AssertionError("real dry-run runner failed")
        return output.getvalue()

    with (tempfile.TemporaryDirectory() as directory,
          patch.object(queue.social_publish.BufferClient, "from_env",
                       side_effect=AssertionError("Buffer forbidden during real dry run")) as buffer):
        temp = Path(directory)

        def build(day, label):
            baseline, state = temp / (label + "-bootstrap.json"), temp / (label + "-queue-state.json")
            invoke(queue.social_publish.build_parser(), ["bootstrap", "--output", str(baseline),
                "--now", at(day, "08:25")])
            invoke(queue.build_parser(), ["build", "--state", str(baseline), "--state-output", str(state),
                "--queue-output", str(temp / (label + "-queue.json")), "--now", at(day, "08:25")])
            q = json.loads(state.read_text(encoding="utf-8"))["planner"]["daily_queue"]
            if any(metadata.from_item(item) is None for item in q["items"]):
                raise AssertionError("active planner lost structured identity")
            rows.append(dict(DATE=day.isoformat(), SLOT="08:25", PRODUCT="core_queue",
                RESULT="PUBLISHABLE_DRY_RUN", REASON="Temporary queue built; no publication attempted"))
            return state, q

        def slot(day, clock, state, q):
            original = state.read_bytes()
            output_state = temp / "forbidden-publication-state.json"
            text = invoke(queue.build_parser(), ["slot", "--state", str(state), "--state-output", str(output_state),
                "--now", at(day, clock), "--slot", clock, "--dry-run"])
            if state.read_bytes() != original or output_state.exists():
                raise AssertionError("dry-run slot changed publication state")
            item = next((item for item in q["items"] if item["slot"] == clock), None)
            ready = "dry_run=true" in text
            reason = "Immutable queued text validated" if ready else next(
                (line for line in text.splitlines() if "skipped=" in line or "no pending item" in line), text.strip())
            if ready and item["late_bound"]:
                reason = "Fresh product passed source, destination, identity and length checks"
            rows.append(dict(DATE=day.isoformat(), SLOT=clock,
                PRODUCT=(item["post_type"] + "/" + item["family"]) if item else "conditional_core_slot",
                RESULT="PUBLISHABLE_DRY_RUN" if ready else "EXPECTED_SKIP", REASON=reason))

        monday_state, monday_queue = build(monday, "monday")
        for clock in ("08:45", "09:30", "11:30", "16:45", "18:30", "19:30"):
            slot(monday, clock, monday_state, monday_queue)
        ordinary_state, ordinary_queue = build(ordinary, "ordinary")
        for clock in ("08:45", "10:15", "11:30", "12:15", "14:30", "16:45", "18:30", "19:30"):
            slot(ordinary, clock, ordinary_state, ordinary_queue)

        for clock in ("09:05", "13:05", "17:05", "20:05"):
            before = ordinary_state.read_bytes()
            output_state = temp / "forbidden-dynamic-state.json"
            text = invoke(queue.social_publish.build_parser(), ["updates", "--state", str(ordinary_state),
                "--state-output", str(output_state), "--now", at(ordinary, clock), "--lookback-hours", "24",
                "--max-posts", "1", "--daily-limit", "3", "--dry-run"])
            if ordinary_state.read_bytes() != before or output_state.exists():
                raise AssertionError("dynamic dry run changed publication state")
            ready = "[recent_change]" in text or "[campaign_event]" in text
            rows.append(dict(DATE=ordinary.isoformat(), SLOT=clock, PRODUCT="dynamic_evolutions",
                RESULT="PUBLISHABLE_DRY_RUN" if ready else "EXPECTED_SKIP",
                REASON="Eligible development previewed" if ready else "No unseen eligible development after bootstrap and readiness gates"))

        # Also exercise a genuine retained event date if both reference days
        # have no roundup. No events are synthesized or rescheduled.
        if not any(row["SLOT"] == "08:45" and row["RESULT"] == "PUBLISHABLE_DRY_RUN" for row in rows):
            dates = [queue.social_publish._event_paris_date_and_time(e.get("scheduled_start"))[0]
                for e in load("campaign_events.json")["campaign_events"]
                if e.get("status") in {"scheduled", "confirmed"} and e.get("title")]
            dates = [day for day in dates if day is not None]
            if dates:
                event_day = min(dates, key=lambda day: abs((day - ordinary).days))
                state, q = build(event_day, "events")
                slot(event_day, "08:45", state, q)
        buffer.assert_not_called()
    return rows


class LaunchHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.issues = load("issue_coverage_history.json")
        cls.agenda = load("agenda_coverage_history.json")
        cls.products = newsroom_products.build_newsroom_products(
            issue_payload=cls.issues, agenda_payload=cls.agenda, locale="fr")
        end = date.fromisoformat(cls.issues["period"]["end_date"])
        cls.ordinary = end + timedelta(days=1)
        if cls.ordinary.weekday() == 0:
            cls.ordinary += timedelta(days=1)
        cls.now = datetime.combine(cls.ordinary, time(10, 15), tzinfo=weekly_flagship.PARIS)
        cls.monday = cls.ordinary - timedelta(days=cls.ordinary.weekday())

    def state(self, *, structured=False):
        state = queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=self.now)
        raw = dict(locale="fr", slot="10:15", lane="newsroom", key="old-immutable-newsroom",
            text="Couverture suivie.\nhttps://france2027.app/enjeux/", score=1.0)
        if structured:
            raw["metadata"] = metadata.newsroom(self.products[0])
        q = queue.new_queue(queue_date=self.ordinary.isoformat(), created_at=self.now, posts=[raw])
        queue.attach_queue(state, q)
        return state

    def execute(self, state, *, fail=False, duplicate=False, dry_run=False):
        client = Mock()
        client.create_post.return_value = "mock-success"
        if fail:
            client.create_post.side_effect = RuntimeError("mock rejection")
        text = state["planner"]["daily_queue"]["items"][0]["text"]
        client.recent_posts.return_value = [{
            "id": "buffer-existing", "text": text, "status": "sent",
            "dueAt": self.now.isoformat(), "createdAt": self.now.isoformat(),
        }] if duplicate else []
        args = argparse.Namespace(now=self.now.isoformat(), state="unused.json", state_output="unused.json",
                                  slot="10:15", dry_run=dry_run)
        with (patch.object(queue, "_load_json", return_value=state),
              patch.object(queue, "save_state") as save,
              patch.object(queue.social_publish.BufferClient, "from_env", return_value=client) as factory,
              contextlib.redirect_stdout(io.StringIO())):
            if fail:
                with self.assertRaisesRegex(RuntimeError, "mock rejection"):
                    queue.run_slot(args)
            else:
                self.assertEqual(queue.run_slot(args), 0)
        return client, save, factory

    def test_canonical_newsroom_identity_is_copied_without_metric_arithmetic(self):
        for product in self.products:
            with self.subTest(product=product.product_id):
                m = metadata.newsroom(product)
                self.assertEqual(set(m), set(metadata.FIELDS))
                for name in ("family", "metric_id", "aggregation_unit", "denominator_id", "window_mode", "rank_kind"):
                    self.assertEqual(m[name], getattr(product, name))
                self.assertEqual((m["window_start"], m["window_end"]), (product.current_start, product.current_end))
                self.assertEqual(m["canonical_url"], product.destination_url)
                self.assertFalse(m["late_bound"])
                self.assertEqual(m["comparison_start"], product.previous_start if product.rank_kind == "movers" else None)

    def test_new_queue_exposes_identity_at_top_level(self):
        state = self.state(structured=True)
        item = state["planner"]["daily_queue"]["items"][0]
        self.assertNotIn("metadata", item)
        self.assertEqual(metadata.from_item(item), metadata.newsroom(self.products[0]))
        self.assertEqual(state["planner"]["daily_queue"]["schema_version"], 1)

    def test_monday_descriptors_have_explicit_identity_and_unresolved_sources(self):
        now = datetime.combine(self.monday, time(8, 25), tzinfo=weekly_flagship.PARIS)
        posts = daily_plan._build_newsroom_fr_posts(products=self.products, roundup="", now=now, max_posts=6)
        self.assertEqual([p.slot for p in posts], ["09:30", "16:45", "18:30"])
        self.assertTrue(all(p.metadata["late_bound"] and not p.text for p in posts))
        f, c, r = (p.metadata for p in posts)
        self.assertEqual(f["window_mode"], "complete_week")
        self.assertEqual((f["comparison_start"], f["comparison_end"], f["window_start"], f["window_end"]),
                         weekly_flagship.expected_weeks(self.monday))
        self.assertIsNone(f["metric_id"])
        self.assertIsNone(f["denominator_id"])
        self.assertIsNone(f["aggregation_unit"])
        self.assertEqual(c["metric_id"], candidate_media_pulse.METRIC_ID)
        self.assertIsNone(c["window_start"])
        self.assertIsNone(c["canonical_url"])
        self.assertEqual(r["metric_id"], radar_media.METRIC_ID)
        self.assertIsNone(r["window_end"])
        self.assertEqual(r["canonical_url"], radar_media.URL)

    def test_candidate_metadata_uses_actual_resolved_period_and_destination(self):
        period = load("candidate_signals.json")["visibility"]["current_period"]
        product = SimpleNamespace(current_start=period["start_date"], current_end=period["end_date"],
                                  destination_url="https://france2027.app/candidates/raphael-glucksmann/",
                                  lane="general_visibility", window_mode="complete_day",
                                  previous_start="2026-10-04", previous_end="2026-10-04")
        m = metadata.candidate(product)
        self.assertEqual(m["metric_id"], product.lane)
        self.assertEqual(m["window_mode"], product.window_mode)
        self.assertEqual((m["comparison_start"], m["comparison_end"]),
                         (product.previous_start, product.previous_end))
        self.assertEqual((m["window_start"], m["window_end"]), (product.current_start, product.current_end))
        self.assertEqual(m["canonical_url"], product.destination_url)
        self.assertTrue(m["late_bound"])

    def test_radar_metadata_uses_snapshot_timestamps_without_reaggregation(self):
        product = SimpleNamespace(window_start=(self.now - timedelta(days=30)).isoformat(), window_end=self.now.isoformat())
        m = metadata.radar(product)
        self.assertEqual((m["window_start"], m["window_end"]), (product.window_start, product.window_end))
        self.assertEqual(m["denominator_id"], radar_media.DENOMINATOR_ID)
        self.assertIsNone(m["comparison_start"])

    def test_events_have_no_invented_metric_or_window(self):
        m = metadata.events(queue.social_publish.campaign_events_destination())
        self.assertEqual(m["canonical_url"], "https://france2027.app/#signal-events")
        self.assertIsNone(m["metric_id"])
        self.assertIsNone(m["window_mode"])
        self.assertFalse(m["late_bound"])

    def test_old_social_state_upgrades_without_losing_seen_registries(self):
        state = self.state()
        del state["planner"]
        state["seen"] = dict(recent_changes=["seen-change"], campaign_events=["seen-event"])
        old_seen = copy.deepcopy(state["seen"])
        queue.social_publish._validate_state(state)
        self.assertEqual(state["seen"], old_seen)
        self.assertEqual(state["planner"]["schema_version"], 1)

    def test_old_planner_without_dynamic_registry_still_loads(self):
        state = self.state()
        del state["planner"]["dynamic_updates"]
        queue.planner_from_state(state)
        self.assertEqual(state["planner"]["dynamic_updates"], [])

    def test_old_queue_load_is_byte_preserving(self):
        state = self.state()
        original = json.dumps(state, sort_keys=True)
        queue.queue_from_state(state)
        self.assertEqual(json.dumps(state, sort_keys=True), original)
        self.assertIsNone(metadata.from_item(state["planner"]["daily_queue"]["items"][0]))

    def test_published_old_item_and_buffer_id_are_preserved(self):
        state = self.state()
        item = state["planner"]["daily_queue"]["items"][0]
        item.update(status="published", published_at=self.now.isoformat(), buffer_post_id="original-id")
        original = copy.deepcopy(state)
        _, save, factory = self.execute(state)
        factory.assert_not_called()
        save.assert_not_called()
        self.assertEqual(state, original)

    def test_rebuild_returns_same_old_queue_with_publication_ledgers(self):
        state = self.state()
        state["planner"][radar_media.STATE_KEY] = {"opaque_old_receipt": "preserved"}
        state["planner"][weekly_flagship.STATE_KEY] = {"old_receipt": "preserved"}
        original = copy.deepcopy(state)
        q = state["planner"]["daily_queue"]
        with patch.object(queue, "build_core_plan", side_effect=AssertionError("must not replan")):
            self.assertIs(queue.build_queue(state=state, now=self.now), q)
        self.assertEqual(state, original)

    def test_old_item_executes_and_success_marks_published(self):
        state = self.state()
        item = state["planner"]["daily_queue"]["items"][0]
        text = item["text"]
        client, save, _ = self.execute(state)
        self.assertEqual(client.create_post.call_args.args[0], text)
        self.assertEqual((item["status"], item["buffer_post_id"]), ("published", "mock-success"))
        self.assertIsNone(metadata.from_item(item))
        save.assert_called_once()

    def test_failed_buffer_call_leaves_state_unchanged(self):
        state = self.state(structured=True)
        before = copy.deepcopy(state)
        _, save, _ = self.execute(state, fail=True)
        self.assertEqual(state, before)
        save.assert_not_called()

    def test_existing_buffer_duplicate_is_resolved_without_creation(self):
        state = self.state()
        client, save, _ = self.execute(state, duplicate=True)
        client.create_post.assert_not_called()
        item = state["planner"]["daily_queue"]["items"][0]
        self.assertEqual((item["status"], item["buffer_post_id"]), ("published", "buffer-existing"))
        save.assert_called_once()

    def test_immutable_newsroom_text_and_identity_never_recalculate_at_execution(self):
        state = self.state(structured=True)
        before = copy.deepcopy(state)
        with patch.object(newsroom_products, "build_newsroom_products", side_effect=AssertionError("no recalculation")):
            client, save, factory = self.execute(state, dry_run=True)
        self.assertEqual(state, before)
        factory.assert_not_called()
        save.assert_not_called()

    def test_invalid_resolved_metadata_cannot_partially_update_queue(self):
        state = self.state()
        item = state["planner"]["daily_queue"]["items"][0]
        before = copy.deepcopy(state)
        resolved = daily_plan.PlannedPost("fr", "10:15", "newsroom", "changed", "Changed text",
                                         metadata={"post_type": "incomplete"})
        with self.assertRaises(ValueError):
            queue.mark_item_published(state=state, item=item, published_at=self.now,
                                      buffer_post_id="mock-success", resolved_post=resolved)
        self.assertEqual(state, before)

    def test_active_newsroom_never_calls_legacy_article_share_utility(self):
        with patch.object(newsroom_products.contract, "_share", side_effect=AssertionError("legacy metric forbidden")):
            products = newsroom_products.build_newsroom_products(
                issue_payload=self.issues, agenda_payload=self.agenda, locale="fr")
        self.assertEqual(products, self.products)

    def test_bad_metadata_fails_closed_without_rewriting_state(self):
        for changes in ({"late_bound": "true"}, {"window_end": None}, {"metric_id": 42}):
            state = self.state(structured=True)
            state["planner"]["daily_queue"]["items"][0].update(changes)
            original = copy.deepcopy(state)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                queue.queue_from_state(state)
            self.assertEqual(state, original)

    def test_unknown_additive_fields_are_preserved(self):
        state = self.state(structured=True)
        state["planner"]["daily_queue"]["items"][0]["future_extra"] = {"value": 1}
        original = copy.deepcopy(state)
        queue.queue_from_state(state)
        self.assertEqual(state, original)

    def test_schema_versions_and_bootstrap_baseline_remain_unchanged(self):
        self.assertEqual((queue.QUEUE_SCHEMA_VERSION, daily_plan.PLANNER_STATE_SCHEMA_VERSION,
                          queue.social_publish.STATE_SCHEMA_VERSION), (1, 1, 1))
        state = queue.social_publish.build_bootstrap_state({"items": [{"id": "a"}]},
            {"campaign_events": [{"event_id": "b"}]}, now=self.now)
        self.assertEqual(state["seen"], {"recent_changes": ["a"], "campaign_events": ["b"]})
        self.assertEqual(set(state["planner"]), {"schema_version", "published_quantitative", "roundup_dates", "dynamic_updates"})

    def test_cold_active_planner_queue_and_preview_do_not_import_legacy_engine(self):
        script = """
import json,sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,'social')
import daily_queue as q
assert 'signal_engine' not in sys.modules
q.daily_plan._parser()
for stamp in sys.argv[1:]:
 now=datetime.fromisoformat(stamp)
 state=q.social_publish.build_bootstrap_state({'items':[]},{'campaign_events':[]},now=now)
 q.build_queue(state=state,now=now)
assert 'signal_engine' not in sys.modules
"""
        monday = datetime.combine(self.monday, time(8, 25), tzinfo=weekly_flagship.PARIS)
        subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", script, monday.isoformat(), self.now.isoformat()],
                       cwd=ROOT, check=True, capture_output=True, text=True)

    def test_workflow_schedule_and_inert_gate_are_unchanged(self):
        workflow = (ROOT / ".github/workflows/publish-x-fr.yml").read_text(encoding="utf-8")
        crons = ("25 8 * * *", "45 8 * * *", "30 9 * * 1", "15 10 * * *", "30 11 * * *",
                 "15 12 * * *", "30 14 * * *", "45 16 * * *", "30 18 * * *", "30 19 * * *",
                 "5 9 * * *", "5 13 * * *", "5 17 * * *", "5 20 * * *")
        for cron in crons:
            self.assertIn(f"cron: '{cron}'\n      timezone: 'Europe/Paris'", workflow)
        self.assertIn("vars.FR27_SOCIAL_ENABLED == 'true'", workflow)
        self.assertIn("--daily-limit 3", workflow)
        self.assertNotIn("signal_engine.py", workflow)
        self.assertNotIn("--candidate-history", workflow)
        self.assertNotIn("social_publish.py visual", workflow)

    def test_real_planner_queue_runner_matrix_is_side_effect_free(self):
        rows = real_dry_run_matrix()
        self.assertTrue({"09:30", "16:45", "18:30", "10:15", "12:15", "14:30", "11:30", "19:30", "09:05", "08:45"}
                        <= {row["SLOT"] for row in rows})
        self.assertTrue(all(row["RESULT"] in {"PUBLISHABLE_DRY_RUN", "EXPECTED_SKIP"} for row in rows))
        self.assertTrue(any(row["SLOT"] == "08:45" and row["RESULT"] == "PUBLISHABLE_DRY_RUN" for row in rows))


if __name__ == "__main__":
    unittest.main()
