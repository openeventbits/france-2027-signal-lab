"""Manual recovery gates, pinned evidence, queue isolation and receipt safety."""
import argparse
import contextlib
import copy
import hashlib
import io
import json
import re
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import test_social_weekly_flagship as fixtures
from social import weekly_flagship as flagship
from social import weekly_flagship_catchup as catchup

ROOT = Path(__file__).resolve().parent


class CatchupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WeeklyFlagshipTests.setUpClass()

    def setUp(self):
        self.fixture = fixtures.WeeklyFlagshipTests()
        self.fixture.setUp()
        self.now = self.fixture.now + timedelta(days=1)
        self.product = self.fixture.product

    def ready(self, days=1):
        # Real rolling Tuesday artifacts. Wednesday advances only post-target
        # days and the live cards, preserving both target weeks' exact evidence.
        from build_route_registry import _semantic_html_bytes
        args = copy.deepcopy(self.fixture.base)
        now = self.fixture.now + timedelta(days=days)
        stamp = (now - timedelta(minutes=5)).isoformat()
        args["news"]["generated_at"] = stamp
        args["issue_history"]["data_as_of"] = stamp
        args["agenda_history"]["data_as_of"] = stamp
        if days == 2:
            self.advance_wednesday(args, stamp)
        product = flagship.build_product(**args)
        files = {name: json.dumps(args[key], ensure_ascii=False) for name, key in (
            ("news_wire.json", "news"), ("issue_coverage_history.json", "issue_history"),
            ("agenda_coverage_history.json", "agenda_history"), ("candidate_agenda_history.json", "candidate_history"),
            ("issue_pages_manifest.json", "issue_manifest"))}
        routes = args["routes"]
        for route in routes["routes"]:
            if route.get("language") != "fr" or route.get("family") not in ("issues", "agenda", "core"):
                continue
            path = route["source_file"]
            document = (ROOT / path).read_text(encoding="utf-8")
            files[path] = document
            route["lastmod"] = now.astimezone(timezone.utc).date().isoformat()
            route["content_sha256"] = hashlib.sha256(_semantic_html_bytes(document.encode())).hexdigest()
        files["route_registry.json"] = json.dumps(routes)
        if days == 2:
            self.live_html(files, product, args["news"])
        return files, replace(product, revision="revision-A"), now

    def advance_wednesday(self, args, stamp):
        day = (self.fixture.monday + timedelta(days=1)).isoformat()
        history = args["issue_history"]
        history["corpus"]["daily"].append(dict(date=day, item_count=0, publisher_count=0, source_snapshot_at=stamp))
        for row in history["issues"]:
            row["daily"].append(dict(date=day, item_count=0, publisher_count=0,
                                     corpus_item_count=0, corpus_publisher_count=0, corpus_share_percent=0.0))
        history = args["agenda_history"]
        history["daily"].append(dict(date=day, total_classified_agenda_items=0,
                                     total_agenda_topic_source_days=0, source_snapshot_at=stamp))
        for row in history["topics"]:
            row["daily"].append(dict(date=day, item_count=0, source_day_count=0,
                                     total_classified_agenda_items=0, total_agenda_topic_source_days=0,
                                     topic_item_share=0.0, topic_source_day_share=0.0))
        for key in ("issue_history", "agenda_history"):
            args[key]["period"].update(end_date=day, days=args[key]["period"]["days"] + 1)
        for family in ("policy_agenda", "campaign_agenda"):
            evolution = args["news"][family]["evolution"]
            for key in ("period_start", "period_end", "previous_start", "previous_end", "latest_start", "latest_end"):
                evolution[key] = (date.fromisoformat(evolution[key]) + timedelta(days=1)).isoformat()
            series = [t["daily_activity"] for t in evolution["topics"]]
            if "accepted_daily_activity" in evolution:
                series.append(evolution["accepted_daily_activity"])
            for daily in series:
                zero = {key: 0 if isinstance(value, (int, float)) else value for key, value in daily[-1].items()}
                daily[-1].update(zero)
                daily.pop(0)
                daily.append({**zero, "date": evolution["period_end"]})
            for topic in evolution["topics"]:
                topic.update(item_count=sum(p["item_count"] for p in topic["daily_activity"]),
                             source_day_count=sum(p["source_day_count"] for p in topic["daily_activity"]),
                             active_day_count=sum(p["item_count"] > 0 for p in topic["daily_activity"]))
        evolution = args["news"]["policy_agenda"]["evolution"]
        window = tuple(evolution[k] for k in ("previous_start", "previous_end", "latest_start", "latest_end"))
        previous, current = flagship._page_periods(args["news"], window)
        before_by_id = {r.issue_id: r for r in previous[0].rows}
        after_by_id = {r.issue_id: r for r in current[0].rows}
        for topic in evolution["topics"]:
            before, after = before_by_id[topic["id"]], after_by_id[topic["id"]]
            topic.update(previous_source_day_count=before.numerator, latest_source_day_count=after.numerator,
                         previous_incidence=round(before.raw_share, 6), latest_incidence=round(after.raw_share, 6),
                         incidence_change_pp=round((after.raw_share - before.raw_share) * 100, 3))
        args["candidate_history"] = fixtures.shift_dates(args["candidate_history"], timedelta(days=1))
        args["issue_manifest"]["data_as_of"] = evolution["period_end"]

    def live_html(self, files, product, news):
        live = flagship._live_page_product(product, news)
        for family, rows in (("issue", live.issue_rows), ("agenda", (live.increase, live.decrease))):
            for row in rows:
                document = f'<link rel="canonical" href="{row.canonical_url_fr}">'
                for start, role in ((live.issues.previous_start, "is-previous"), (live.issues.current_start, "is-latest")):
                    for i in range(7):
                        day = (date.fromisoformat(start) + timedelta(days=i)).isoformat()
                        count = ""
                        if family == "agenda":
                            topic = next(t for t in news["campaign_agenda"]["evolution"]["topics"] if t["id"] == row.entity_id)
                            point = next(p for p in topic["daily_activity"] if p["date"] == day)
                            count = f' data-source-days="{point["source_day_count"]}"'
                        document += f'<i class="{family}-detail-activity-bar {role}" data-date="{day}"{count}></i>'
                if family == "issue":
                    document += f'data-previous-incidence="{round(row.previous_raw / 100, 6)}" data-latest-incidence="{round(row.current_raw / 100, 6)}"'
                else:
                    before, after = (f"{n:.1f}".replace(".", ",") for n in (row.previous_raw, row.current_raw))
                    document += f'Jours-sources : {row.previous_evidence} → {row.current_evidence}. Part agenda : {before} % → {after} %'
                path = row.canonical_url_fr.removeprefix(flagship.URL) + "index.html"
                files[path] = document
                self.rehash(files, path)

    def load(self, files, now, **options):
        git, calls = self.fixture.mock_git(files, **options)
        def execute(args, **kwargs):
            if args[1] == "ls-files":
                return ""
            return git(args, **kwargs)
        with patch.object(flagship.subprocess, "check_output", side_effect=execute):
            return flagship.load_catchup_product(root=ROOT, now=now)

    def test_tuesday_and_wednesday_derive_only_immediately_preceding_monday(self):
        for day in (6, 7):
            now = datetime(2026, 10, day, 12, tzinfo=flagship.PARIS)
            self.assertEqual(flagship.catchup_monday(now).isoformat(), "2026-10-05")
            self.assertEqual(flagship.expected_weeks(flagship.catchup_monday(now)),
                             ("2026-09-21", "2026-09-27", "2026-09-28", "2026-10-04"))

    def test_all_other_paris_weekdays_and_naive_time_rejected(self):
        for day in (5, 8, 9, 10, 11):
            with self.subTest(day=day), self.assertRaises(flagship.FlagshipError):
                flagship.catchup_monday(datetime(2026, 10, day, 12, tzinfo=flagship.PARIS))
        with self.assertRaises(flagship.FlagshipError):
            flagship.catchup_monday(datetime(2026, 10, 6, 12))

    def test_boundary_uses_paris_not_utc_weekday(self):
        self.assertEqual(flagship.catchup_monday(datetime(2026, 10, 5, 22, 30, tzinfo=timezone.utc)),
                         datetime(2026, 10, 5).date())
        with self.assertRaises(flagship.FlagshipError):
            flagship.catchup_monday(datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc))

    def test_tuesday_wednesday_load_ready_revision_without_changing_product(self):
        for days in (1, 2):
            files, expected, now = self.ready(days)
            product = self.load(files, now)
            self.assertEqual(product.text, expected.text)
            self.assertEqual(product.product_id, expected.product_id)
            self.assertEqual(product.revision, "revision-A")
            self.assertEqual(flagship._window(product.issues), flagship.expected_weeks(self.fixture.monday))
            news = json.loads(files["news_wire.json"])
            self.assertNotEqual(news["policy_agenda"]["evolution"]["latest_end"], product.issues.current_end)
            with self.assertRaises(flagship.FlagshipError):
                flagship.load_product(root=ROOT, now=now)

    def test_stale_future_naive_and_mixed_refreshes_fail_closed(self):
        for kind in ("stale", "future", "naive", "mixed"):
            files, _, now = self.ready()
            stamp = {"stale": now - timedelta(days=1), "future": now + timedelta(minutes=1),
                     "naive": now.replace(tzinfo=None), "mixed": now - timedelta(minutes=10)}[kind].isoformat()
            for name, key in (("news_wire.json", "generated_at"), ("issue_coverage_history.json", "data_as_of"),
                              ("agenda_coverage_history.json", "data_as_of")):
                if kind == "mixed" and name != "agenda_coverage_history.json":
                    continue
                p = json.loads(files[name]); p[key] = stamp; files[name] = json.dumps(p)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "stale, future or from different refreshes"):
                self.load(files, now)

    def test_history_must_extend_through_yesterday_utc(self):
        for name in ("issue_coverage_history.json", "agenda_coverage_history.json"):
            files, _, now = self.ready(2)
            p = json.loads(files[name]); p["period"]["end_date"] = self.fixture.monday.isoformat()
            files[name] = json.dumps(p)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "latest complete UTC day"):
                self.load(files, now)

    def test_candidate_and_manifest_refresh_dates_must_match(self):
        for name in ("candidate_agenda_history.json", "issue_pages_manifest.json"):
            files, _, now = self.ready()
            p = json.loads(files[name]); target = p["tracking"] if name.startswith("candidate") else p
            target["data_as_of"] = "2020-01-01"; files[name] = json.dumps(p)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "match the refresh date"):
                self.load(files, now)

    def test_missing_target_history_and_inconsistent_live_page_dates_fail_closed(self):
        for kind in ("missing", "inconsistent"):
            files, _, now = self.ready()
            if kind == "missing":
                p = json.loads(files["issue_coverage_history.json"]); p["corpus"]["daily"].pop(-5)
                files["issue_coverage_history.json"] = json.dumps(p)
            else:
                p = json.loads(files["news_wire.json"])
                p["policy_agenda"]["evolution"]["latest_end"] = (self.fixture.monday - timedelta(days=1)).isoformat()
                files["news_wire.json"] = json.dumps(p)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.load(files, now)

    def test_normal_monday_still_requires_exact_displayed_target_comparison(self):
        files, product = self.fixture.ready_revision()
        news = json.loads(files["news_wire.json"])
        news["policy_agenda"]["evolution"]["latest_end"] = self.fixture.monday.isoformat()
        with self.assertRaisesRegex(ValueError, "destination comparison dates"):
            flagship.verify_pages(product, news, files.__getitem__)

    def test_target_numerator_denominator_raw_and_display_mismatches_fail(self):
        files, product, _ = self.ready()
        news = json.loads(files["news_wire.json"])
        for family in ("issues", "agenda"):
            for field in ("previous_evidence", "current_evidence", "previous_denominator", "current_denominator",
                          "previous_raw", "current_raw", "previous_display", "current_display", "display_delta"):
                snapshot = getattr(product, family)
                row = replace(snapshot.rows[0], **{field: getattr(snapshot.rows[0], field) + 1})
                invalid = replace(product, **{family: replace(snapshot, rows=(row, *snapshot.rows[1:]))})
                with self.subTest(family=family, field=field), self.assertRaisesRegex(ValueError, "authority parity failed"):
                    flagship.verify_catchup_authority(invalid, news, self.fixture.monday)

    def rehash(self, files, path):
        from build_route_registry import _semantic_html_bytes
        routes = json.loads(files["route_registry.json"])
        row = next(r for r in routes["routes"] if r["source_file"] == path)
        row["content_sha256"] = hashlib.sha256(_semantic_html_bytes(files[path].encode())).hexdigest()
        files["route_registry.json"] = json.dumps(routes)

    def test_historical_html_exposed_target_counts_must_reconcile(self):
        for family in ("issues", "agenda"):
            files, product, now = self.ready()
            routes = json.loads(files["route_registry.json"])["routes"]
            row = product.issue_rows[0] if family == "issues" else product.increase
            route = next(r for r in routes if r["entity_id"] == row.entity_id and r["language"] == "fr"
                         and r["kind"] in ("issue-history-detail", "agenda-history-detail"))
            path = route["source_file"]
            day = product.issues.current_start
            pattern = rf'(<time datetime="{day}".*?</td>\s*<td data-label="ARTICLES">)(\d+)'
            files[path], count = re.subn(pattern, lambda m: m[1] + str(int(m[2]) + 1), files[path], flags=re.S)
            self.assertEqual(count, 1)
            self.rehash(files, path)
            with self.subTest(family=family), self.assertRaisesRegex(ValueError, "historical .* HTML parity failed"):
                self.load(files, now)

    def test_absent_old_period_html_does_not_block_authority_verified_target(self):
        files, expected, now = self.ready()
        routes = json.loads(files["route_registry.json"])["routes"]
        for route in routes:
            if route["language"] == "fr" and route["kind"] in ("issue-history-detail", "agenda-history-detail"):
                path = route["source_file"]
                files[path] = re.sub(r'<table class="(?:issue|agenda)-history-table".*?</table>', '', files[path], flags=re.S)
                self.rehash(files, path)
        self.assertEqual(self.load(files, now).text, expected.text)

    def test_canonical_mismatch_fails_even_with_updated_registry_hash(self):
        files, product, now = self.ready()
        path = product.issue_rows[0].canonical_url_fr.removeprefix(flagship.URL) + "index.html"
        files[path] = files[path].replace('<link rel="canonical"', '<link rel="wrong-canonical"')
        self.rehash(files, path)
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.load(files, now)

    def test_target_data_outside_live_comparison_bands_must_still_match(self):
        files, product, now = self.ready()
        row = product.increase
        path = row.canonical_url_fr.removeprefix(flagship.URL) + "index.html"
        day = product.agenda.previous_start
        pattern = rf'(<i class="agenda-detail-activity-bar is-[^\"]+" data-date="{day}" data-source-days=")(\d+)'
        files[path], count = re.subn(pattern, lambda m: m[1] + str(int(m[2]) + 1), files[path])
        self.assertEqual(count, 1)
        self.rehash(files, path)
        with self.assertRaisesRegex(ValueError, "historical .* activity parity failed"):
            self.load(files, now)

    def test_route_hash_and_visible_page_parity_are_required(self):
        for kind in ("hash", "lastmod", "page"):
            files, product, now = self.ready()
            if kind == "page":
                path = product.issue_rows[0].canonical_url_fr.removeprefix(flagship.URL) + "index.html"
                files[path] = files[path].replace('data-latest-incidence="', 'data-latest-incidence="9')
            else:
                p = json.loads(files["route_registry.json"])
                r = next(r for r in p["routes"] if r.get("canonical_url") == flagship.URL)
                r["content_sha256" if kind == "hash" else "lastmod"] = "invalid"
                files["route_registry.json"] = json.dumps(p)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "parity failed"):
                self.load(files, now)

    def test_dirty_or_changing_checkout_rejected(self):
        for options in ({"dirty": True}, {"changed_head": True}):
            files, _, now = self.ready()
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "checkout changed"):
                self.load(files, now, **options)

    def test_cli_has_no_clock_or_historical_week_override(self):
        for option in ("--now", "--monday", "--week"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                catchup.build_parser().parse_args(["--state", "in", "--state-output", "out", option, "2026-10-05"])

    def run_publish(self, *, dry_run=False, duplicate=False, fail=False, receipt=False, invalid=False):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "state.json", Path(tmp) / "output.json"
            state = self.fixture.state()
            # Tuesday's already persisted queue, with pre-editorial-refinement
            # copy. Catch-up must preserve every byte of its data structure.
            state["planner"]["daily_queue"]["date"] = self.now.astimezone(flagship.PARIS).date().isoformat()
            state["planner"]["daily_queue"]["items"][0]["text"] = "existing Tuesday copy"
            if receipt:
                flagship.record_receipt(state["planner"], flagship.publication_receipt(
                    product_id=self.product.product_id, revision="prior", published_at=self.fixture.now,
                    buffer_post_id="prior-id"))
            source.write_text(json.dumps(state), encoding="utf-8")
            before = source.read_bytes()
            client = Mock()
            client.recent_post_texts.return_value = {self.product.text.strip()} if duplicate else set()
            client.create_post.return_value = "" if invalid else "buffer-id"
            if fail:
                client.create_post.side_effect = RuntimeError("Buffer failed")
            args = argparse.Namespace(state=str(source), state_output=str(output), dry_run=dry_run)
            with (patch.object(catchup.weekly_flagship, "load_catchup_product", return_value=self.product) as load,
                  patch.object(catchup.social_publish.BufferClient, "from_env", return_value=client) as factory,
                  contextlib.redirect_stdout(io.StringIO()) as printed):
                if fail or invalid:
                    with self.assertRaises((RuntimeError, ValueError)):
                        catchup.run_catchup(args, now=self.now)
                else:
                    self.assertEqual(catchup.run_catchup(args, now=self.now), 0)
            self.assertEqual(source.read_bytes(), before)
            saved = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
            if saved:
                self.assertEqual(saved["planner"]["daily_queue"], state["planner"]["daily_queue"])
                self.assertEqual(json.dumps(saved["planner"]["daily_queue"], sort_keys=True).encode(),
                                 json.dumps(state["planner"]["daily_queue"], sort_keys=True).encode())
                for key in ("published_quantitative", "roundup_dates", "dynamic_updates"):
                    self.assertEqual(saved["planner"][key], state["planner"][key])
            return client, factory, load, saved, printed.getvalue()

    def test_dry_run_prints_exact_copy_identity_and_length_without_mutation_or_buffer(self):
        client, factory, _, saved, printed = self.run_publish(dry_run=True)
        factory.assert_not_called(); self.assertIsNone(saved)
        self.assertIn(self.product.text, printed)
        self.assertIn(f"weighted_length={self.product.weighted_length}", printed)
        self.assertIn(f"target_monday={self.fixture.monday}", printed)
        self.assertIn(f"completed_week={self.product.issues.current_start}..{self.product.issues.current_end}", printed)

    def test_already_published_receipt_skips_before_product_or_buffer(self):
        _, factory, load, saved, _ = self.run_publish(receipt=True)
        factory.assert_not_called(); load.assert_not_called(); self.assertIsNone(saved)

    def test_success_records_standard_receipt_and_preserves_immutable_queue(self):
        client, _, _, saved, _ = self.run_publish()
        client.create_post.assert_called_once_with(self.product.text)
        receipt = saved["planner"][flagship.STATE_KEY][self.product.product_id]
        self.assertEqual(set(receipt), {"product_id", "revision", "published_at", "buffer_post_id"})
        self.assertEqual(receipt["revision"], self.product.revision)
        self.assertEqual(receipt["buffer_post_id"], "buffer-id")

    def test_failed_or_empty_buffer_receipt_never_writes_state(self):
        for options in ({"fail": True}, {"invalid": True}):
            _, _, _, saved, _ = self.run_publish(**options)
            self.assertIsNone(saved)

    def test_exact_duplicate_recovers_without_second_post_and_receipt_is_idempotent(self):
        client, _, _, saved, _ = self.run_publish(duplicate=True)
        client.create_post.assert_not_called()
        ledger = saved["planner"][flagship.STATE_KEY]
        self.assertEqual(ledger[self.product.product_id]["buffer_post_id"], "buffer-existing")
        before = copy.deepcopy(ledger)
        flagship.record_receipt(saved["planner"], flagship.publication_receipt(
            product_id=self.product.product_id, revision="later", published_at=self.now, buffer_post_id="other"))
        self.assertEqual(ledger, before)

    def test_dirty_checkout_can_only_print_blocked_dry_run_copy_never_publish(self):
        for dry_run in (True, False):
            state = self.fixture.state()
            with tempfile.TemporaryDirectory() as tmp:
                source, output = Path(tmp) / "input.json", Path(tmp) / "output.json"
                source.write_text(json.dumps(state), encoding="utf-8")
                before = source.read_bytes()
                args = argparse.Namespace(state=str(source), state_output=str(output), dry_run=dry_run)
                with (patch.object(catchup.weekly_flagship, "load_catchup_product",
                                   side_effect=flagship.CatchupCheckoutError(self.product)),
                      patch.object(catchup.social_publish.BufferClient, "from_env") as buffer,
                      contextlib.redirect_stdout(io.StringIO()) as printed):
                    with self.assertRaises(flagship.CatchupCheckoutError):
                        catchup.run_catchup(args, now=self.now)
                buffer.assert_not_called()
                self.assertEqual(source.read_bytes(), before)
                self.assertFalse(output.exists())
                if dry_run:
                    self.assertIn("publishable=false", printed.getvalue())
                    self.assertIn(self.product.text, printed.getvalue())
                else:
                    self.assertNotIn(self.product.text, printed.getvalue())

    def test_workflow_mode_is_manual_only_and_integrated_with_state_and_buffer(self):
        text = (ROOT / ".github/workflows/publish-x-fr.yml").read_text(encoding="utf-8")
        self.assertIn("          - weekly-flagship-catchup", text)
        schedules = text[text.index("case "):text.index('echo "mode=$mode"')]
        self.assertNotIn("weekly-flagship-catchup", schedules)
        for start, end in (("Validate Buffer configuration", "Show Buffer organization"),
                           ("Inspect persistent social state branch", "Refuse live bootstrap"),
                           ("Require persistent state", "# BOOTSTRAP"),
                           ("Persist unified social state", "Safety summary")):
            self.assertIn("weekly-flagship-catchup", text[text.index(start):text.index(end)])
        block = text[text.index("      - name: Publish or preview missed weekly flagship"):text.index("      # PERSISTENCE")]
        self.assertIn("github.event_name == 'workflow_dispatch'", block)
        self.assertIn("--dry-run", block)
        self.assertNotIn("daily_queue.py", block)


if __name__ == "__main__":
    unittest.main()
