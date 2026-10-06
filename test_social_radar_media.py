"""Radar authority, publication lifecycle, failure gates and repetition contracts."""
import argparse
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))
import radar_media as radar
import daily_queue as queue
import daily_plan as planner

NOW = datetime(2026, 10, 5, 16, 30, tzinfo=timezone.utc)


class RadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_news = radar.load_json(ROOT / "news_wire.json")
        cls.signals = radar.load_json(ROOT / "candidate_signals.json")
        cls.routes = radar.load_json(ROOT / "route_registry.json")
        cls.base = cls.snapshot()

    @classmethod
    def snapshot(cls, counts=(400, 250, 150, 100, 100),
                 labels=("Zeta", "Alpha", "Écho", "Delta", "Institution"), generated=None):
        news = copy.deepcopy(cls.real_news)
        news["generated_at"] = generated or "2026-10-05T14:00:00Z"
        news["election_news"] = []
        for label, count in zip(labels, counts):
            for _ in range(count):
                item = copy.deepcopy(cls.real_news["election_news"][0])
                index = len(news["election_news"])
                item.update(publisher=label, published_at=news["generated_at"],
                            id=hashlib.sha256(str(index).encode()).hexdigest()[:20],
                            url=f"https://example.com/news/{index}")
                news["election_news"].append(item)
        news["counts"]["election_news"] = len(news["election_news"])
        model = radar.media_snapshot_model(cls.signals, news_payload=news)["fr"]["model"]
        return dict(news=news, shared_model=model, page_model=copy.deepcopy(model), routes=cls.routes, now=NOW)

    def setUp(self):
        self.args = copy.deepcopy(self.base)

    def build(self, **overrides):
        return radar.build_product(**dict(self.args, **overrides))

    def previous(self):
        product = self.build()
        return dict(payload=product.payload, fingerprint=product.fingerprint,
                    published_at="2026-10-04T16:30:00Z", buffer_post_id="old-success")

    def test_shared_ranking_numerator_denominator_and_raw_share_parity(self):
        product = self.build()
        self.assertEqual([row["name"] for row in product.rows],
                         [row["name"] for row in self.args["shared_model"]["publisherRanking"][:3]])
        for public, shared in zip(product.rows, self.args["shared_model"]["publisherRanking"]):
            for field in ("count", "denominator", "rawShare"):
                self.assertEqual(public[field], shared[field])
        self.assertEqual(product.denominator, 1000)
        self.assertEqual(len(self.args["shared_model"]["feedItems"]), 50)
        self.assertAlmostEqual(sum(row["rawShare"] for row in self.args["shared_model"]["publisherRanking"]), 1)

    def test_ties_and_normalized_labels_follow_existing_french_order(self):
        args = self.snapshot(counts=(300, 300, 300, 50, 50), labels=(" Zeta ", "Alpha", "Écho", "Delta", "Institution"))
        product = radar.build_product(**args)
        self.assertEqual([row["name"] for row in product.rows], ["Alpha", "Écho", "Zeta"])

    def test_copy_one_decimal_boundary_date_and_exact_url(self):
        product = self.build()
        self.assertIn("5 oct. · instantané sur 30 j", product.text)
        self.assertIn("Sources les plus représentées :", product.text)
        self.assertIn("1. Zeta — 40,0 %", product.text)
        self.assertIn("Couverture suivie · ≠ opinion.", product.text)
        self.assertTrue(product.text.endswith("https://france2027.app/"))
        self.assertNotIn("1000", product.text)
        self.assertNotIn("400", product.text)
        self.assertLessEqual(product.weighted_length, 280)

    def test_v21_half_up_display_rounding(self):
        args = self.snapshot(counts=(4005, 2500, 1500, 1000, 995))
        self.assertEqual(radar.build_product(**args).rows[0]["display_share"], 40.1)

    def test_identical_payload_skips(self):
        self.assertIsNone(self.build(last_publication=self.previous()))

    def test_date_only_change_skips(self):
        previous = self.previous()
        args = self.snapshot(generated="2026-10-06T14:00:00Z")
        args["now"] = NOW + timedelta(days=1)
        self.assertIsNone(radar.build_product(**args, last_publication=previous))

    def test_displayed_point_one_change_publishes(self):
        changed = self.snapshot(counts=(401, 250, 150, 100, 99))
        product = radar.build_product(**changed, last_publication=self.previous())
        self.assertEqual(product.rows[0]["display_share"], 40.1)

    def test_raw_change_without_display_change_skips(self):
        args = self.snapshot(counts=(4001, 2500, 1500, 1000, 999))
        self.assertIsNone(radar.build_product(**args, last_publication=self.previous()))

    def test_membership_change_publishes(self):
        args = self.snapshot(labels=("New source", "Alpha", "Écho", "Delta", "Institution"))
        self.assertIsNotNone(radar.build_product(**args, last_publication=self.previous()))

    def test_order_change_publishes(self):
        args = self.snapshot(labels=("Alpha", "Zeta", "Écho", "Delta", "Institution"))
        self.assertIsNotNone(radar.build_product(**args, last_publication=self.previous()))

    def test_freshness_uses_paris_publication_date(self):
        self.assertIsNotNone(self.build())
        for now in (NOW + timedelta(days=1), NOW - timedelta(days=1)):
            with self.assertRaises(radar.RadarError):
                self.build(now=now)
        args = self.snapshot(generated="2026-10-04T23:30:00Z")
        self.assertIsNotNone(radar.build_product(**args))

    def test_page_parity_fails_for_each_metric_field(self):
        for field in ("generatedAt", "electionNewsCount", "publisherRanking", "topPublishers"):
            with self.subTest(field=field):
                page = copy.deepcopy(self.args["page_model"])
                page[field] = None
                with self.assertRaises(radar.RadarError):
                    self.build(page_model=page)

    def test_insufficient_denominator_and_explicit_cap_fail(self):
        args = self.snapshot(counts=(40, 25, 15, 10, 9))
        with self.assertRaises(radar.RadarError):
            radar.build_product(**args)
        self.args["news"]["max_items"] = 50
        with self.assertRaises(radar.RadarError):
            self.build()

    def test_fewer_than_five_publishers_or_three_valid_rows_fail(self):
        for counts in ((400, 300, 200, 100), (500, 500)):
            with self.assertRaises(radar.RadarError):
                radar.build_product(**self.snapshot(counts=counts))
        for row in self.args["shared_model"]["publisherRanking"][:3]:
            row["rawShare"] = None
        with self.assertRaises(radar.RadarError):
            self.build()

    def test_feed_failure_and_corrupt_source_records_fail(self):
        for mutation in ("health", "duplicate_id", "duplicate_url", "blank", "out_of_window", "count"):
            args = copy.deepcopy(self.args)
            if mutation == "health":
                args["news"]["feed_coverage"]["feeds_successful_this_run"] -= 1
            elif mutation == "duplicate_id":
                args["news"]["election_news"][1]["id"] = args["news"]["election_news"][0]["id"]
            elif mutation == "duplicate_url":
                args["news"]["election_news"][1]["url"] = args["news"]["election_news"][0]["url"]
            elif mutation == "blank":
                args["news"]["election_news"][0]["publisher"] = " "
            elif mutation == "out_of_window":
                args["news"]["election_news"][0]["published_at"] = "2026-09-01T00:00:00Z"
            else:
                args["news"]["counts"]["election_news"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(radar.RadarError):
                radar.build_product(**args)

    def test_publisher_count_sum_and_denominator_mismatch_fail(self):
        for field in ("count", "denominator"):
            args = copy.deepcopy(self.args)
            args["shared_model"]["publisherRanking"][0][field] += 1
            with self.assertRaises(radar.RadarError):
                radar.build_product(**args)

    def test_canonical_route_must_be_unique_and_exact(self):
        home = next(row for row in self.routes["routes"] if row["route_id"] == "home:fr")
        for routes in ({"routes": []}, {"routes": [home, home]},
                       {"routes": [dict(home, canonical_url=radar.URL + "#signal-media")]}):
            with self.assertRaises(radar.RadarError):
                self.build(routes=routes)

    def test_overlength_fails_without_truncating_or_dropping_url(self):
        args = self.snapshot(labels=("Long source " * 30, "Alpha", "Écho", "Delta", "Institution"))
        with self.assertRaisesRegex(radar.RadarError, "weighted length"):
            radar.build_product(**args)

    def test_corrupt_repetition_state_fails_closed(self):
        for previous in ({}, {"payload": self.build().payload, "fingerprint": "wrong"}, "invalid"):
            with self.assertRaises(radar.RadarError):
                self.build(last_publication=previous)

    def test_current_production_data_has_exact_published_model_parity(self):
        generated = datetime.fromisoformat(self.real_news["generated_at"].replace("Z", "+00:00"))
        product = radar.load_product(root=ROOT, now=generated + timedelta(minutes=1))
        self.assertEqual(product.denominator, len(self.real_news["election_news"]))
        self.assertEqual([row["name"] for row in product.rows],
                         [row["name"] for row in radar.published_media(ROOT)["publisherRanking"][:3]])

    def write_snapshot(self, root, args):
        for name, value in (("news_wire.json", args["news"]), ("candidate_signals.json", self.signals),
                            ("route_registry.json", self.routes)):
            (root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        (root / "index.html").write_text('<link rel="canonical" href="https://france2027.app/">'
            '<script id="published-media-snapshot">' + json.dumps(args["page_model"]) + '</script>', encoding="utf-8")

    def state_with_queue(self):
        state = queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=NOW)
        instruction = radar.slot_instruction(NOW.date())
        posts = [dict(locale="fr", slot="08:45", lane="today_events", key="events:day", text="Frozen events"),
                 dict(locale="fr", slot=instruction.slot, lane="radar_slot", key=instruction.product_id, text="")]
        q = queue.new_queue(queue_date=NOW.date().isoformat(), created_at=NOW, posts=posts)
        queue.attach_queue(state, q)
        return state, q["items"][1]

    def test_late_binding_refreshes_independently_and_keeps_queue_immutable(self):
        state, item = self.state_with_queue()
        original = copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_snapshot(root, self.args)
            morning = queue.resolve_slot_post(item, now=NOW, site_root=root, state=state)
            refreshed = self.snapshot(counts=(401, 250, 150, 100, 99))
            self.write_snapshot(root, refreshed)
            fresh = queue.resolve_slot_post(item, now=NOW, site_root=root, state=state)
            self.assertIn("40,0 %", morning.text)
            self.assertIn("40,1 %", fresh.text)
            (root / "candidate_signals.json").unlink()
            self.assertEqual(queue.resolve_slot_post(item, now=NOW, site_root=root, state=state).text, fresh.text)
            self.assertEqual(state, original)

    def test_execution_quality_failure_skips_without_buffer_or_state_mutation(self):
        state, item = self.state_with_queue()
        original = copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for failure in ("stale", "parity", "unhealthy", "insufficient", "publishers", "long"):
                args = copy.deepcopy(self.args)
                if failure == "stale":
                    args["news"]["generated_at"] = "2026-10-04T14:00:00Z"
                elif failure == "parity":
                    args["page_model"]["publisherRanking"][0]["rawShare"] += 0.01
                elif failure == "unhealthy":
                    args["news"]["sources"][0]["status"] = "error"
                elif failure == "insufficient":
                    args = self.snapshot(counts=(40, 25, 15, 10, 9))
                elif failure == "publishers":
                    args = self.snapshot(counts=(400, 300, 200, 100))
                else:
                    args = self.snapshot(labels=("Long " * 100, "Alpha", "Écho", "Delta", "Institution"))
                self.write_snapshot(root, args)
                with self.subTest(failure=failure), mock.patch.object(queue.social_publish.BufferClient, "from_env") as client:
                    self.assertIsNone(queue.resolve_slot_post(item, now=NOW, site_root=root, state=state))
                    client.assert_not_called()
                    self.assertEqual(state, original)
            self.assertEqual(queue.resolve_slot_post(state["planner"]["daily_queue"]["items"][0], now=NOW).text,
                             "Frozen events")
            (root / "index.html").unlink()
            self.assertIsNone(queue.resolve_slot_post(item, now=NOW, site_root=root, state=state))
            self.assertEqual(state, original)

    def run_publication(self, fail=False, dry_run=False, unchanged=False):
        state, item = self.state_with_queue()
        if unchanged:
            state["planner"][radar.STATE_KEY] = self.previous()
        if fail:
            previous = self.previous()
            previous["payload"]["rows"][0]["display_tenths"] -= 1
            previous["fingerprint"] = radar.fingerprint(previous["payload"])
            state["planner"][radar.STATE_KEY] = previous
        original = copy.deepcopy(state)
        product = self.build()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_snapshot(root, self.args)
            input_path, output_path = root / "state.json", root / "result.json"
            input_path.write_text(json.dumps(state), encoding="utf-8")
            args = argparse.Namespace(state=str(input_path), state_output=str(output_path),
                                      slot="18:30", now=NOW.isoformat(), dry_run=dry_run)
            client = mock.Mock()
            client.recent_post_texts.return_value = set()
            client.create_post.return_value = "mock-success"
            if fail:
                client.create_post.side_effect = RuntimeError("mock Buffer failure")
            with mock.patch.object(queue, "ROOT", root), mock.patch.object(
                    queue.social_publish.BufferClient, "from_env", return_value=client):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "mock Buffer failure"):
                        queue.run_slot(args)
                else:
                    self.assertEqual(queue.run_slot(args), 0)
            if fail or dry_run or unchanged:
                self.assertFalse(output_path.exists())
                self.assertEqual(json.loads(input_path.read_text(encoding="utf-8")), original)
            else:
                saved = json.loads(output_path.read_text(encoding="utf-8"))
                receipt = saved["planner"][radar.STATE_KEY]
                self.assertEqual(receipt["payload"], product.payload)
                self.assertEqual(receipt["fingerprint"], product.fingerprint)
                self.assertEqual(receipt["buffer_post_id"], "mock-success")
                self.assertEqual(saved["planner"]["daily_queue"]["items"][1]["status"], "published")
                item = saved["planner"]["daily_queue"]["items"][1]
                self.assertEqual(item["metric_id"], radar.METRIC_ID)
                self.assertEqual((item["window_start"], item["window_end"]), (product.window_start, product.window_end))
                self.assertTrue(item["late_bound"])
                self.assertEqual(saved["planner"]["daily_queue"]["items"][0], original["planner"]["daily_queue"]["items"][0])
            if dry_run or unchanged:
                client.create_post.assert_not_called()
            return client

    def test_success_persists_last_successful_payload(self):
        self.run_publication()

    def test_buffer_failure_keeps_previous_fingerprint(self):
        self.run_publication(fail=True)

    def test_dry_run_does_not_advance_repetition_state(self):
        self.run_publication(dry_run=True)

    def test_unchanged_execution_skips_without_state_corruption_or_buffer(self):
        self.run_publication(unchanged=True)

    def test_new_core_slot_is_separate_from_candidate_and_english_slots(self):
        products = queue.build_core_plan(state=self.state_with_queue()[0], now=NOW)
        slots = {row["slot"]: row for row in products["fr_posts"]}
        self.assertEqual(slots["16:45"]["lane"], "candidate_slot")
        self.assertEqual(slots["18:30"]["lane"], "radar_slot")
        self.assertEqual(slots["16:45"]["text"], "")
        self.assertEqual(slots["18:30"]["text"], "")
        self.assertEqual(products["rules"]["fr_newsroom_slots"][radar.PRODUCT_TYPE], "18:30")

    def test_workflow_schedule_mapping_and_safety_gate(self):
        workflow = (ROOT / ".github/workflows/publish-x-fr.yml").read_text(encoding="utf-8")
        self.assertIn("- cron: '30 18 * * *'\n      timezone: 'Europe/Paris'", workflow)
        self.assertIn("'30 18 * * *')\n                mode=\"slot\"\n                slot=\"18:30\"", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch' ||\n      vars.FR27_SOCIAL_ENABLED == 'true'", workflow)
        self.assertIn("- cron: '5 9,13,17,20 * * *'", workflow)


if __name__ == "__main__":
    unittest.main()
