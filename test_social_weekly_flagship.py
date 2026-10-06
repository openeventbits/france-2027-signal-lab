"""Fixed weekly roles, pinned-source parity, and publication receipt safety."""
import argparse
import contextlib
import copy
import io
import json
import re
import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))
import weekly_flagship as flagship
import daily_plan
import daily_queue as queue
import coverage_metric_contract as metrics
import issue_page_contract as issue_authority
import agenda_page_contract as agenda_authority
from social import newsroom_products


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def shift_dates(value, delta):
    if isinstance(value, dict):
        return {k: shift_dates(v, delta) for k, v in value.items()}
    if isinstance(value, list):
        return [shift_dates(v, delta) for v in value]
    if isinstance(value, str):
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(.*)", value)
        if match:
            return (date.fromisoformat(match[1]) + delta).isoformat() + match[2]
    return value


class WeeklyFlagshipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = dict(issue_history=load("issue_coverage_history.json"),
            agenda_history=load("agenda_coverage_history.json"), news=load("news_wire.json"),
            candidate_history=load("candidate_agenda_history.json"),
            issue_manifest=load("issue_pages_manifest.json"), routes=load("route_registry.json"))
        end = date.fromisoformat(cls.base["issue_history"]["period"]["end_date"])
        cls.monday = end - timedelta(days=(end.weekday() + 1) % 7) + timedelta(days=1)
        cls.now = datetime.combine(cls.monday, time(9, 30), tzinfo=flagship.PARIS).astimezone(timezone.utc)
        cls.base["monday"] = cls.monday
        cls.product = replace(flagship.build_product(**cls.base), revision="verified-revision")
        cls.fr = newsroom_products.build_newsroom_products(issue_payload=cls.base["issue_history"],
            agenda_payload=cls.base["agenda_history"], locale="fr")
        cls.en = newsroom_products.build_newsroom_products(issue_payload=cls.base["issue_history"],
            agenda_payload=cls.base["agenda_history"], locale="en")

    def setUp(self):
        self.args = copy.deepcopy(self.base)
        self.qualified = {r.entity_id for r in self.product.issues.rows}
        self.daily = {row["id"]: row["daily"] for row in self.args["issue_history"]["issues"]}

    def posts(self, now=None, roundup="", products=None):
        return daily_plan._build_newsroom_fr_posts(products=self.fr if products is None else products,
            roundup=roundup, now=now or self.now, max_posts=6)

    def select(self, issues=None, agenda=None, qualified=None, daily=None):
        return flagship.select_rows(issues or self.product.issues, agenda or self.product.agenda,
            self.qualified if qualified is None else qualified, self.daily if daily is None else daily)

    def test_only_monday_has_flagship_and_all_three_specialist_slots_are_suppressed(self):
        posts = self.posts(roundup="Events")
        self.assertEqual([p.slot for p in posts], ["08:45", "09:30", "16:45", "18:30"])
        self.assertFalse({"10:15", "12:15", "14:30"} & {p.slot for p in posts})
        self.assertEqual(posts[1].lane, "weekly_flagship_slot")
        self.assertEqual(posts[1].text, "")
        self.assertIsNone(posts[1].score)

    def test_tuesday_through_sunday_preserve_specialists_candidate_and_radar(self):
        products = [p for p in self.fr if p.window_mode == "complete_day"]
        movers = {p.family: p for p in products if p.rank_kind == "movers"}
        self.assertEqual(set(movers), {"issues", "agenda"})
        self.assertEqual(movers["issues"].current_end, movers["agenda"].current_end)
        eligible_date = date.fromisoformat(movers["issues"].current_end) + timedelta(days=1)
        if eligible_date.weekday() == 0:
            # When a refreshed fixture's complete-day pair is publishable on
            # Monday, create a separate Tuesday source fixture with identical
            # evidence. Shift the histories, not individual product metadata.
            products = [p for p in newsroom_products.build_newsroom_products(
                issue_payload=shift_dates(self.args["issue_history"], timedelta(days=1)),
                agenda_payload=shift_dates(self.args["agenda_history"], timedelta(days=1)),
                locale="fr") if p.window_mode == "complete_day"]
            eligible_date += timedelta(days=1)
        eligible_now = datetime.combine(eligible_date, time(9, 30), tzinfo=flagship.PARIS).astimezone(timezone.utc)
        self.assertEqual([p.slot for p in self.posts(now=eligible_now, products=products)],
                         ["10:15", "12:15", "14:30", "16:45", "18:30"])

        monday = eligible_date - timedelta(days=eligible_date.weekday())
        for offset in range(1, 7):
            day = monday + timedelta(days=offset)
            now = datetime.combine(day, time(9, 30), tzinfo=flagship.PARIS).astimezone(timezone.utc)
            end = (now.astimezone(timezone.utc).date() - timedelta(days=1)).isoformat()
            with self.subTest(day=day):
                posts = self.posts(now=now, products=products)
                slots = {p.slot: p for p in posts}
                self.assertNotIn("09:30", slots)
                self.assertFalse(any(p.key.startswith("weekly_flagship_fr:") for p in posts))
                for slot, lane, identity in (("16:45", "candidate_slot", "candidate_media_pulse_current"),
                                             ("18:30", "radar_slot", "radar_media_publishers_current")):
                    self.assertEqual(slots[slot].lane, lane)
                    self.assertEqual(slots[slot].key, f"{identity}:slot:{day.isoformat()}:fr")
                    self.assertEqual(slots[slot].text, "")

                # Products already passed their evidence/rendering gates.
                # Their actual complete-day boundary decides readiness here;
                # Monday suppression must never remove a fresh specialist.
                expected_slots = []
                for slot, family, kind in (("10:15", "issues", "movers"),
                                          ("12:15", "agenda", "movers"),
                                          ("14:30", daily_plan.dominance_family_for_date(now), "dominance")):
                    ready = next((p for p in products if p.family == family
                                  and p.rank_kind == kind and p.current_end == end), None)
                    if ready is None:
                        self.assertNotIn(slot, slots)
                    else:
                        expected_slots.append(slot)
                        self.assertEqual(slots[slot].key, ready.product_id)
                        self.assertEqual(slots[slot].text, ready.text)
                self.assertEqual([p.slot for p in posts], expected_slots + ["16:45", "18:30"])
                if day > eligible_date:
                    self.assertTrue(all(p.current_end < end for p in products))
                    self.assertEqual([p.slot for p in posts], ["16:45", "18:30"])

    def test_english_monday_behavior_is_unchanged(self):
        posts = daily_plan._build_newsroom_en_posts(products=self.en, now=self.now, max_posts=2)
        self.assertEqual([p.slot for p in posts], ["11:30", "19:30"])
        self.assertEqual(len({p.key.split("_")[0] for p in posts}), 2)
        self.assertTrue(all("_movers_complete_week" in p.key for p in posts))

    def test_candidate_and_radar_instructions_remain_late_bound(self):
        posts = {p.slot: p for p in self.posts()}
        for slot, lane in (("16:45", "candidate_slot"), ("18:30", "radar_slot")):
            self.assertEqual(posts[slot].lane, lane)
            self.assertEqual(posts[slot].text, "")

    def test_old_monday_queue_cannot_restore_suppressed_specialists(self):
        for slot in ("10:15", "12:15", "14:30"):
            item = dict(locale="fr", slot=slot, lane="newsroom", key="old-specialist", text="Frozen copy", score=1.0)
            with self.subTest(slot=slot), contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(queue.resolve_slot_post(item, now=self.now))
                ordinary = queue.resolve_slot_post(item, now=self.now + timedelta(days=1))
                self.assertEqual(ordinary.text, "Frozen copy")

    def test_issue_and_agenda_selection_consume_shared_authorities(self):
        with (patch.object(issue_authority, "build_issue_period_metric", wraps=issue_authority.build_issue_period_metric) as issue,
              patch.object(agenda_authority, "build_agenda_period_metric", wraps=agenda_authority.build_agenda_period_metric) as agenda):
            product = flagship.build_product(**self.args)
        self.assertGreaterEqual(issue.call_count, 4)
        self.assertGreaterEqual(agenda.call_count, 4)
        rows = self.select()
        self.assertEqual(product.issue_rows, rows[0])
        self.assertEqual((product.increase, product.decrease), rows[1:])

    def test_issue_ranking_uses_display_then_current_evidence_then_id(self):
        tied = replace(self.product.issues, rows=tuple(replace(r, current_display=5.0,
            current_evidence=10) for r in reversed(self.product.issues.rows)))
        ids = sorted(r.entity_id for r in tied.rows if sum(p["publisher_count"] > 0
            for p in self.daily[r.entity_id] if tied.current_start <= p["date"] <= tied.current_end) >= 2)
        self.assertEqual([r.entity_id for r in self.select(issues=tied)[0]], ids[:3])

    def test_agenda_signed_rankings_use_evidence_then_id_ties(self):
        ids = [r.entity_id for r in self.product.agenda.rows if r.entity_id != "polls_race"]
        tied = replace(self.product.agenda, rows=tuple(replace(r,
            display_delta=1.0 if r.entity_id in ids[:3] else -1.0,
            previous_evidence=10, current_evidence=10) for r in reversed(self.product.agenda.rows)))
        _, increase, decrease = self.select(agenda=tied)
        self.assertEqual(increase.entity_id, min(ids[:3]))
        self.assertEqual(decrease.entity_id, min(ids[3:]))

    def test_polls_stay_in_denominator_and_cannot_be_selected(self):
        self.assertEqual(sum(r.current_evidence for r in self.product.agenda.rows),
                         self.product.agenda.rows[0].current_denominator)
        polls = next(r for r in self.product.agenda.rows if r.entity_id == "polls_race")
        self.assertGreater(polls.current_evidence, 0)
        self.assertNotIn("polls_race", (self.product.increase.entity_id, self.product.decrease.entity_id))
        snapshot = replace(self.product.agenda, rows=tuple(
            replace(row, display_delta=999.0) if row.entity_id == "polls_race" else row
            for row in self.product.agenda.rows))
        self.assertNotIn("polls_race", [r.entity_id for r in self.select(agenda=snapshot)[1:]])

    def test_no_cross_family_score_and_exactly_five_fixed_rows(self):
        self.assertFalse(hasattr(self.product, "score"))
        self.assertEqual(len(self.product.issue_rows) + 2, 5)
        lines = [s for s in self.product.text.splitlines() if s.startswith(("Enjeu #", "Agenda "))]
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(s.startswith("Enjeu #") for s in lines[:3]))

    def test_exact_calendar_week_identity_is_required(self):
        for offset in (-7, 1, 7):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                flagship.build_product(**{**self.args, "monday": self.monday + timedelta(days=offset)})

    def test_unproven_utc_day_boundaries_fail_closed(self):
        for key in ("issue_history", "agenda_history"):
            args = copy.deepcopy(self.args)
            args[key]["period"]["day_boundary"] = "Europe/Paris"
            with self.subTest(family=key), self.assertRaisesRegex(ValueError, "UTC day boundaries"):
                flagship.build_product(**args)

    def test_morning_incomplete_metrics_still_queue_flagship_without_filler(self):
        plan = daily_plan.build_plan(issue_payload={}, agenda_payload={},
            recent_changes={"items": []}, campaign_events={"campaign_events": []},
            now=self.now, max_updates=0)
        self.assertEqual([p["slot"] for p in plan["fr_posts"]], ["09:30", "16:45", "18:30"])
        self.assertEqual(plan["fr_posts"][0]["text"], "")

    def test_incomplete_issue_week_fails_closed(self):
        self.args["issue_history"]["corpus"]["daily"].pop(-5)
        with self.assertRaises(ValueError):
            flagship.build_product(**self.args)

    def test_incomplete_agenda_week_fails_closed(self):
        self.args["agenda_history"]["topics"][0]["daily"].pop(-5)
        with self.assertRaises(ValueError):
            flagship.build_product(**self.args)

    def test_all_four_denominator_floors_fail_closed(self):
        for family in ("issues", "agenda"):
            for field in ("previous_denominator", "current_denominator"):
                snapshot = getattr(self.product, family)
                invalid = replace(snapshot, rows=tuple(replace(r, **{field: 99}) for r in snapshot.rows))
                builder = "build_issue_metric_snapshot" if family == "issues" else "build_agenda_metric_snapshot"
                with self.subTest(family=family, field=field), patch.object(metrics, builder, return_value=invalid):
                    with self.assertRaisesRegex(ValueError, "100 source-days"):
                        flagship.build_product(**self.args)

    def test_fewer_than_three_qualified_issues_fails(self):
        with self.assertRaisesRegex(ValueError, "fewer than three"):
            self.select(qualified={self.product.issue_rows[0].entity_id, self.product.issue_rows[1].entity_id})

    def test_issue_source_day_evidence_floor_fails(self):
        invalid = replace(self.product.issues, rows=tuple(replace(r, current_evidence=4) for r in self.product.issues.rows))
        with self.assertRaisesRegex(ValueError, "fewer than three"):
            self.select(issues=invalid)

    def test_issue_active_date_evidence_floor_fails(self):
        daily = {key: [{"date": self.product.issues.current_end, "publisher_count": 10}] for key in self.daily}
        with self.assertRaisesRegex(ValueError, "fewer than three"):
            self.select(daily=daily)

    def test_no_positive_nonpoll_movement_fails(self):
        invalid = replace(self.product.agenda, rows=tuple(replace(r, display_delta=-1.0)
                                                         for r in self.product.agenda.rows))
        with self.assertRaisesRegex(ValueError, "positive and negative"):
            self.select(agenda=invalid)

    def test_no_negative_nonpoll_movement_fails(self):
        invalid = replace(self.product.agenda, rows=tuple(replace(r, display_delta=1.0)
                                                         for r in self.product.agenda.rows))
        with self.assertRaisesRegex(ValueError, "positive and negative"):
            self.select(agenda=invalid)

    def test_display_deltas_reconcile_with_visible_endpoints(self):
        for row in (self.product.increase, self.product.decrease):
            self.assertEqual(row.display_delta, metrics.display_round(row.current_display - row.previous_display))

    def test_exact_five_rows_are_required_by_renderer(self):
        with self.assertRaises(ValueError):
            flagship.render(self.product.issue_rows[:2], self.product.increase, self.product.decrease,
                            self.product.issues.current_start, self.product.issues.current_end)

    def test_canonical_homepage_is_required_and_only_url_in_copy(self):
        self.assertEqual(re.findall(r"https?://\S+", self.product.text), [flagship.URL])
        self.args["routes"]["routes"] = []
        with self.assertRaisesRegex(ValueError, "canonical FR homepage"):
            flagship.build_product(**self.args)

    def test_copy_uses_approved_aliases_no_raw_counts_and_fits(self):
        self.assertLessEqual(self.product.weighted_length, 280)
        self.assertEqual(self.product.weighted_length, flagship.weighted_x_length(self.product.text))
        self.assertNotIn("&", self.product.text)
        self.assertNotRegex(self.product.text, r"n=|record_count|source_day_count|articles")
        self.assertIn("Couverture suivie · ≠ prévision.", self.product.text)

    def test_overlong_aliases_fail_without_url_truncation(self):
        aliases = {key: ("Long " * 100, "Long " * 100) for key in flagship.LABELS}
        with patch.object(flagship, "LABELS", aliases), self.assertRaisesRegex(ValueError, "weighted length"):
            flagship.build_product(**self.args)

    def test_page_authority_disagreement_fails(self):
        with patch.object(issue_authority, "build_issue_history_period_metric",
                          wraps=issue_authority.build_issue_history_period_metric) as calculate:
            original = calculate._mock_wraps
            calculate.side_effect = lambda *a, **k: replace(original(*a, **k), rows=tuple(
                replace(r, raw_share=r.raw_share + .01) for r in original(*a, **k).rows))
            with self.assertRaisesRegex(ValueError, "parity failed"):
                flagship.build_product(**self.args)

    def ready_revision(self):
        # Synthetic Monday producer revision; all metrics retain their source
        # relationships. No Git repository or publication artifacts are written.
        delta = self.monday - date.fromisoformat(self.args["news"]["policy_agenda"]["evolution"]["period_end"])
        args = shift_dates(self.args, delta)
        generated = (self.now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        args["news"]["generated_at"] = generated
        args["issue_history"]["data_as_of"] = generated
        args["agenda_history"]["data_as_of"] = generated
        # The real Agenda ledger can refresh a day behind Issues. For this
        # explicitly ready revision, reconstruct its daily inputs from the
        # same synthetic page source through the complete Sunday.
        sunday = flagship.expected_weeks(self.monday)[3]
        evolution = args["news"]["campaign_agenda"]["evolution"]
        points = {t["id"]: [copy.deepcopy(p) for p in t["daily_activity"] if p["date"] <= sunday]
                  for t in evolution["topics"]}
        for topic in args["agenda_history"]["topics"]:
            topic["daily"] = points[topic["id"]]
        days = [p["date"] for p in next(iter(points.values()))]
        args["agenda_history"]["daily"] = [dict(date=day, total_agenda_topic_source_days=sum(
            p["source_day_count"] for rows in points.values() for p in rows if p["date"] == day)) for day in days]
        args["agenda_history"]["period"].update(start_date=days[0], end_date=sunday, days=len(days))
        product = flagship.build_product(**args)
        files = {name: json.dumps(args[key], ensure_ascii=False) for name, key in (
            ("news_wire.json", "news"), ("issue_coverage_history.json", "issue_history"),
            ("agenda_coverage_history.json", "agenda_history"), ("candidate_agenda_history.json", "candidate_history"),
            ("issue_pages_manifest.json", "issue_manifest"), ("route_registry.json", "routes"))}
        files["index.html"] = '<link rel="canonical" href="' + flagship.URL + '">'
        def bars(family, row):
            text = '<link rel="canonical" href="' + row.canonical_url_fr + '">'
            for start, role in ((product.issues.previous_start, "is-previous"), (product.issues.current_start, "is-latest")):
                for i in range(7):
                    day = (date.fromisoformat(start) + timedelta(days=i)).isoformat()
                    count = ""
                    if family == "agenda":
                        topic = next(t for t in args["news"]["campaign_agenda"]["evolution"]["topics"] if t["id"] == row.entity_id)
                        point = next(p for p in topic["daily_activity"] if p["date"] == day)
                        count = f' data-source-days="{point["source_day_count"]}"'
                    text += f'<i class="{family}-detail-activity-bar {role}" data-date="{day}"{count}></i>'
            return text
        for row in product.issue_rows:
            files[row.canonical_url_fr.removeprefix(flagship.URL) + "index.html"] = bars("issue", row) + (
                f'data-previous-incidence="{round(row.previous_raw / 100, 6)}" data-latest-incidence="{round(row.current_raw / 100, 6)}"')
        for row in (product.increase, product.decrease):
            previous, current = [f"{n:.1f}".replace(".", ",") for n in (row.previous_raw, row.current_raw)]
            files[row.canonical_url_fr.removeprefix(flagship.URL) + "index.html"] = bars("agenda", row) + (
                f'Jours-sources : {row.previous_evidence} → {row.current_evidence}. Part agenda : {previous} % → {current} %')
        return files, product

    def mock_git(self, files, *, dirty=False, changed_head=False):
        calls = []
        def git(args, **kwargs):
            calls.append(args)
            if args[1:3] == ["rev-parse", "HEAD"]:
                return "revision-B\n" if changed_head and sum(c[1:3] == ["rev-parse", "HEAD"] for c in calls) > 1 else "revision-A\n"
            if args[1] == "show":
                self.assertTrue(args[2].startswith("revision-A:"))
                return files[args[2].split(":", 1)[1]]
            if args[1] == "diff":
                return "news_wire.json\n" if dirty else ""
            raise AssertionError(args)
        return git, calls

    def test_execution_reads_one_pinned_revision_and_validates_pages(self):
        files, expected = self.ready_revision()
        git, calls = self.mock_git(files)
        with patch.object(flagship.subprocess, "check_output", side_effect=git):
            actual = flagship.load_product(root=ROOT, now=self.now)
        self.assertEqual(actual.text, expected.text)
        self.assertEqual(actual.revision, "revision-A")
        self.assertGreater(len([c for c in calls if c[1] == "show"]), 6)

    def test_execution_rejects_dirty_or_changing_checkout(self):
        for options in ({"dirty": True}, {"changed_head": True}):
            files, _ = self.ready_revision()
            git, _ = self.mock_git(files, **options)
            with self.subTest(options=options), patch.object(flagship.subprocess, "check_output", side_effect=git):
                with self.assertRaisesRegex(ValueError, "checkout changed"):
                    flagship.load_product(root=ROOT, now=self.now)

    def test_execution_rejects_mixed_refreshes(self):
        files, _ = self.ready_revision()
        history = json.loads(files["agenda_coverage_history.json"])
        history["data_as_of"] = (self.now - timedelta(minutes=10)).isoformat()
        files["agenda_coverage_history.json"] = json.dumps(history)
        git, _ = self.mock_git(files)
        with patch.object(flagship.subprocess, "check_output", side_effect=git), self.assertRaisesRegex(ValueError, "different refreshes"):
            flagship.load_product(root=ROOT, now=self.now)

    def test_execution_rejects_stale_future_or_naive_source_times(self):
        for stamp in ((self.now - timedelta(days=1)).isoformat(),
                      (self.now + timedelta(minutes=1)).isoformat(),
                      self.now.replace(tzinfo=None).isoformat()):
            files, _ = self.ready_revision()
            for path, key in (("news_wire.json", "generated_at"),
                              ("issue_coverage_history.json", "data_as_of"),
                              ("agenda_coverage_history.json", "data_as_of")):
                payload = json.loads(files[path]); payload[key] = stamp
                files[path] = json.dumps(payload)
            git, _ = self.mock_git(files)
            with self.subTest(stamp=stamp), patch.object(flagship.subprocess, "check_output", side_effect=git):
                with self.assertRaisesRegex(ValueError, "stale, future"):
                    flagship.load_product(root=ROOT, now=self.now)

    def test_execution_rejects_wrong_published_window(self):
        files, product = self.ready_revision()
        path = product.issue_rows[0].canonical_url_fr.removeprefix(flagship.URL) + "index.html"
        files[path] = files[path].replace('is-latest', 'is-previous', 1)
        git, _ = self.mock_git(files)
        with patch.object(flagship.subprocess, "check_output", side_effect=git), self.assertRaisesRegex(ValueError, "activity dates"):
            flagship.load_product(root=ROOT, now=self.now)

    def test_execution_rejects_published_issue_or_agenda_parity_failure(self):
        for family in ("issue", "agenda"):
            files, product = self.ready_revision()
            row = product.issue_rows[0] if family == "issue" else product.increase
            path = row.canonical_url_fr.removeprefix(flagship.URL) + "index.html"
            files[path] = files[path].replace('data-latest-incidence="', 'data-latest-incidence="9') if family == "issue" else files[path].replace("Part agenda :", "Wrong metric :")
            git, _ = self.mock_git(files)
            with self.subTest(family=family), patch.object(flagship.subprocess, "check_output", side_effect=git), self.assertRaisesRegex(ValueError, "parity failed"):
                flagship.load_product(root=ROOT, now=self.now)

    def test_execution_rejects_non_monday(self):
        with self.assertRaises(ValueError):
            flagship.load_product(root=ROOT, now=self.now + timedelta(days=1))

    def state(self, monday=None, state=None):
        monday = monday or self.monday
        now = datetime.combine(monday, time(9, 30), tzinfo=flagship.PARIS)
        state = state or queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=now)
        instruction = flagship.slot_instruction(monday)
        q = queue.new_queue(queue_date=monday.isoformat(), created_at=now,
            posts=[dict(locale="fr", slot="09:30", lane="weekly_flagship_slot", key=instruction.product_id, text="", score=None)])
        queue.attach_queue(state, q)
        return state

    def publish(self, state, *, product=None, fail=False, dry_run=False, now=None, skip=False):
        client = Mock()
        client.recent_post_texts.return_value = set()
        client.create_post.return_value = "successful-receipt"
        if fail:
            client.create_post.side_effect = RuntimeError("mock Buffer failure")
        args = argparse.Namespace(state="unused.json", state_output="unused-output.json", slot="09:30",
                                  now=(now or self.now).isoformat(), dry_run=dry_run)
        with (patch.object(queue, "_load_json", return_value=state), patch.object(queue, "save_state") as save,
              patch.object(queue.weekly_flagship, "load_product", return_value=product or self.product) as build,
              patch.object(queue.social_publish.BufferClient, "from_env", return_value=client) as factory,
              contextlib.redirect_stdout(io.StringIO())):
            if skip:
                build.side_effect = flagship.FlagshipError("not ready")
            if fail:
                with self.assertRaisesRegex(RuntimeError, "mock Buffer failure"):
                    queue.run_slot(args)
            else:
                self.assertEqual(queue.run_slot(args), 0)
        return client, save, factory

    def test_buffer_success_marks_completed_week_with_receipt_and_revision(self):
        state = self.state()
        client, save, _ = self.publish(state)
        receipt = state["planner"][flagship.STATE_KEY][self.product.product_id]
        self.assertEqual(receipt["buffer_post_id"], "successful-receipt")
        self.assertEqual(receipt["revision"], "verified-revision")
        self.assertEqual(client.create_post.call_args.args[0], self.product.text)
        item = state["planner"]["daily_queue"]["items"][0]
        self.assertEqual(item["post_type"], "weekly_flagship")
        self.assertEqual((item["window_start"], item["window_end"]),
                         (self.product.issues.current_start, self.product.issues.current_end))
        self.assertTrue(item["late_bound"])
        save.assert_called_once()

    def test_execution_publishes_refreshed_values_without_morning_text(self):
        state = self.state()
        self.assertEqual(state["planner"]["daily_queue"]["items"][0]["text"], "")
        rows = (replace(self.product.issue_rows[0], current_display=25.0), *self.product.issue_rows[1:])
        fresh = replace(self.product, issue_rows=rows, revision="fresh-revision",
                        text=flagship.render(rows, self.product.increase, self.product.decrease,
                                             self.product.issues.current_start, self.product.issues.current_end))
        client, _, _ = self.publish(state, product=fresh)
        self.assertIn("25,0 %", client.create_post.call_args.args[0])
        self.assertNotEqual(client.create_post.call_args.args[0], self.product.text)
        self.assertEqual(state["planner"][flagship.STATE_KEY][self.product.product_id]["revision"], "fresh-revision")

    def test_wrong_completed_week_cannot_publish(self):
        wrong = replace(self.product, product_id=flagship.slot_instruction(self.monday + timedelta(days=7)).product_id)
        state = self.state()
        _, save, factory = self.publish(state, product=wrong)
        factory.assert_not_called()
        save.assert_not_called()

    def test_failed_publication_does_not_mark_week(self):
        state = self.state()
        before = copy.deepcopy(state)
        _, save, _ = self.publish(state, fail=True)
        self.assertEqual(state, before)
        save.assert_not_called()

    def test_duplicate_week_is_prevented_even_after_queue_rebuild(self):
        state = self.state()
        self.publish(state)
        self.state(state=state)
        before = copy.deepcopy(state)
        client, save, factory = self.publish(state)
        factory.assert_not_called()
        self.assertEqual(state, before)
        save.assert_not_called()

    def test_new_week_can_publish_with_identical_metric_values(self):
        state = self.state()
        self.publish(state)
        monday = self.monday + timedelta(days=7)
        start, end = flagship.expected_weeks(monday)[2:]
        previous_start, previous_end = flagship.expected_weeks(monday)[:2]
        new = replace(self.product, product_id=flagship.slot_instruction(monday).product_id,
                      issues=replace(self.product.issues, previous_start=previous_start, previous_end=previous_end,
                                     current_start=start, current_end=end),
                      agenda=replace(self.product.agenda, previous_start=previous_start, previous_end=previous_end,
                                     current_start=start, current_end=end),
                      text=flagship.render(self.product.issue_rows, self.product.increase, self.product.decrease, start, end))
        self.state(monday=monday, state=state)
        self.publish(state, product=new, now=self.now + timedelta(days=7))
        self.assertEqual(len(state["planner"][flagship.STATE_KEY]), 2)
        self.assertEqual(state["planner"]["daily_queue"]["items"][0]["window_end"], end)

    def test_not_ready_skip_and_dry_run_never_mark_or_call_buffer(self):
        for options in ({"skip": True}, {"dry_run": True}):
            state = self.state()
            before = copy.deepcopy(state)
            _, save, factory = self.publish(state, **options)
            factory.assert_not_called()
            save.assert_not_called()
            self.assertEqual(state, before)
            self.assertFalse({"10:15", "12:15", "14:30"} & {p.slot for p in self.posts()})

    def test_empty_receipt_cannot_mark_week(self):
        state = self.state()
        item = state["planner"]["daily_queue"]["items"][0]
        resolved = queue.ResolvedFlagshipPost("fr", "09:30", "newsroom", self.product.product_id,
            self.product.text, None, "verified-revision")
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            queue.mark_item_published(state=state, item=item, published_at=self.now,
                                      buffer_post_id="", resolved_post=resolved)
        self.assertEqual(state, before)

    def test_frozen_flagship_instruction_is_rejected(self):
        state = self.state()
        item = state["planner"]["daily_queue"]["items"][0]
        item["text"] = self.product.text
        with patch.object(queue.weekly_flagship, "load_product") as build:
            self.assertIsNone(queue.resolve_slot_post(item, now=self.now, state=state))
        build.assert_not_called()

    def test_existing_workflow_adds_monday_0930_and_preserves_safety_and_dynamics(self):
        path = ".github/workflows/publish-x-fr.yml"
        text = (ROOT / path).read_text(encoding="utf-8")
        old = subprocess.check_output(["git", "show", "HEAD:" + path], cwd=ROOT, encoding="utf-8")
        self.assertIn("cron: '30 9 * * 1'\n      timezone: 'Europe/Paris'", text)
        self.assertRegex(text, r"'30 9 \* \* 1'\)\s+mode=\"slot\"\s+slot=\"09:30\"")
        self.assertIn("vars.FR27_SOCIAL_ENABLED == 'true'", text)
        for beginning, ending in (("      '5 9,13,17,20 * * *')", "              *)"),
                                  ("      - name: Publish or preview core queue slot", "      # ------------------------------------------------------\n      # DYNAMIC"),
                                  ("      - name: Dry-run dynamic developments", "      - name: Upload full dry-run plan")):
            self.assertEqual(text[text.index(beginning):text.index(ending, text.index(beginning))],
                             old[old.index(beginning):old.index(ending, old.index(beginning))])


if __name__ == "__main__":
    unittest.main()
