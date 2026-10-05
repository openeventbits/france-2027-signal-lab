import copy
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))

import candidate_media_pulse as product
import daily_plan
import daily_queue
from build_candidate_reference import _percent as dossier_percent
from candidate_candidacy_status import active_candidate_records


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class CandidateMediaPulseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_signals = load("candidate_signals.json")
        cls.source_registry = load("candidate_candidacy_status.json")
        cls.source_routes = load("route_registry.json")
        cls.issues = load("issue_coverage_history.json")
        cls.agenda = load("agenda_coverage_history.json")
        cls.monday = datetime(2026, 10, 5, 10, tzinfo=timezone.utc)

    def setUp(self):
        self.signals = copy.deepcopy(self.source_signals)
        self.registry = copy.deepcopy(self.source_registry)
        self.routes = copy.deepcopy(self.source_routes)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.by_id = {c["candidate_id"]: c for c in self.signals["candidates"]}
        for candidate in self.by_id.values():
            if candidate["campaign_attention"]["evidence_state"] == "reported":
                self.write_dossier(candidate)

    def write_dossier(self, candidate):
        path = self.site / "candidates" / candidate["candidate_id"] / "data.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        period = self.signals["visibility"]["current_period"]
        path.write_text(json.dumps({
            "candidate_id": candidate["candidate_id"],
            "dossier": {"media_pulse": candidate["campaign_attention"]},
            "media": {"period": {k: period[k] for k in ("start_date", "end_date")}},
        }, ensure_ascii=False), encoding="utf-8")

    def metric(self, identifier, share, count=10, state="reported"):
        candidate = self.by_id[identifier]
        candidate["campaign_attention"].update(
            evidence_state=state, share=share, record_count=count,
        )
        self.write_dossier(candidate)

    def only(self, *identifiers):
        for identifier, candidate in self.by_id.items():
            if identifier not in identifiers:
                candidate["campaign_attention"].update(
                    evidence_state="not_observed", share=None, record_count=None,
                )

    def build(self, planner_date=date(2026, 10, 5)):
        return product.build_product(
            candidate_signals=self.signals, candidacy_registry=self.registry,
            route_registry=self.routes, planner_date=planner_date, site_root=self.site,
        )

    def write_sources(self):
        for name, payload in (
            ("candidate_signals.json", self.signals),
            ("candidate_candidacy_status.json", self.registry),
            ("route_registry.json", self.routes),
        ):
            (self.site / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def resolve(self, now=None):
        self.write_sources()
        return daily_queue.resolve_slot_post(
            self.plan(now)["fr_posts"][-1], now=now or self.monday, site_root=self.site,
        )

    def morning_state(self):
        state = daily_queue.social_publish.build_bootstrap_state(
            {"items": []}, {"campaign_events": []}, now=self.monday,
        )
        plan = self.plan()
        plan["fr_posts"].insert(0, {
            "locale": "fr", "slot": "08:45", "lane": "today_events",
            "key": "today-events:2026-10-05", "score": None,
            "text": "ÉVÉNEMENTS DU JOUR\nhttps://france2027.app/#signal-events",
        })
        with patch.object(daily_queue, "build_core_plan", return_value=plan):
            daily_queue.build_queue(state=state, now=self.monday)
        return state

    def execute(self, state):
        self.write_sources()
        args = Namespace(
            state="unused.json", state_output="unused-output.json", slot="16:45",
            now="2026-10-05T14:45:00Z", dry_run=False,
        )
        with patch.object(daily_queue, "ROOT", self.site), \
             patch.object(daily_queue, "_load_json", return_value=state), \
             patch.object(daily_queue, "save_state") as save, \
             patch.object(sys, "stdout", new_callable=io.StringIO), \
             patch.object(daily_queue.social_publish.BufferClient, "from_env") as client:
            client.return_value.recent_post_texts.return_value = set()
            client.return_value.create_post.return_value = "mock-post-id"
            self.assertEqual(daily_queue.run_slot(args), 0)
        return client, save

    def plan(self, now=None, legacy_history=None):
        return daily_plan.build_plan(
            candidate_payload=legacy_history,
            issue_payload=self.issues, agenda_payload=self.agenda,
            recent_changes={"items": []}, campaign_events={"campaign_events": []},
            now=now or self.monday, max_fr=5, max_en=2, max_updates=0,
            planner_state=daily_plan.new_planner_state(),
            candidate_signals_payload=self.signals, candidacy_payload=self.registry,
            route_payload=self.routes, candidate_site_root=self.site,
        )

    def test_selection_uses_canonical_active_registry(self):
        # Neither Signals flags nor inclusion in a history universe grants eligibility.
        self.by_id["raphael-glucksmann"]["candidacy"]["active_field_eligible"] = False
        selected = self.build()
        active_ids = {c["candidate_id"] for c in active_candidate_records(self.registry)}
        self.assertIn(selected.candidate_id, active_ids)
        self.assertEqual(selected.candidate_id, "raphael-glucksmann")

    def test_hidden_candidate_with_larger_share_is_excluded(self):
        self.metric("jordan-bardella", 0.999, 999)
        self.assertEqual(self.build().candidate_id, "raphael-glucksmann")

    def test_temporarily_missing_candidate_is_excluded(self):
        self.metric("antoine-mikolajczak", 0.999, 999)
        self.assertEqual(self.build().candidate_id, "raphael-glucksmann")

    def test_null_and_unobserved_shares_are_excluded(self):
        self.metric("raphael-glucksmann", None)
        self.metric("edouard-philippe", 0.999, state="not_observed")
        self.assertEqual(self.build().candidate_id, "marine-le-pen")

    def test_no_reported_candidates_means_no_filler(self):
        self.only()
        self.assertIsNone(self.build())
        self.assertIsNone(self.resolve())

    def test_ranking_uses_display_then_count_then_id(self):
        self.only("david-lisnard", "francois-ruffin")
        self.metric("david-lisnard", 0.10014, 5)
        self.metric("francois-ruffin", 0.10011, 6)
        # Equal displayed shares; the lower raw share wins on count.
        self.assertEqual(self.build().candidate_id, "francois-ruffin")
        self.metric("david-lisnard", 0.10014, 6)
        self.assertEqual(self.build().candidate_id, "david-lisnard")
        self.signals["candidates"].reverse()
        self.assertEqual(self.build().candidate_id, "david-lisnard")
        self.metric("francois-ruffin", 0.102, 1)
        self.assertEqual(self.build().candidate_id, "francois-ruffin")

    def test_display_matches_actual_dossier_formatter(self):
        selected = self.build()
        self.assertEqual(selected.displayed_percentage.replace(" %", "%"),
                         dossier_percent(selected.stored_share))
        self.assertIn("Raphaël Glucksmann — 21,2 %", selected.text)

    def test_all_real_reported_eligible_dossiers_have_exact_parity(self):
        signals = {c["candidate_id"]: c for c in self.source_signals["candidates"]}
        checked = 0
        for record in active_candidate_records(self.source_registry):
            identifier = record["candidate_id"]
            metric = signals[identifier]["campaign_attention"]
            if metric["evidence_state"] != "reported" or metric["share"] is None:
                continue
            with self.subTest(candidate_id=identifier):
                page = load(f"candidates/{identifier}/data.json")
                self.assertEqual(metric["share"], page["dossier"]["media_pulse"]["share"])
                self.assertEqual(page["media"]["period"], {
                    k: self.source_signals["visibility"]["current_period"][k]
                    for k in ("start_date", "end_date")
                })
                self.assertEqual(dossier_percent(metric["share"]),
                                 dossier_percent(page["dossier"]["media_pulse"]["share"]))
                checked += 1
        self.assertGreater(checked, 0)
        self.assertEqual(checked, sum(
            signals[c["candidate_id"]]["campaign_attention"]["evidence_state"] == "reported"
            and signals[c["candidate_id"]]["campaign_attention"]["share"] is not None
            for c in active_candidate_records(self.source_registry)
        ))

    def test_selected_parity_failure_omits_slot_without_runner_up(self):
        path = self.site / "candidates/raphael-glucksmann/data.json"
        page = json.loads(path.read_text(encoding="utf-8"))
        page["dossier"]["media_pulse"]["share"] = 0.211
        path.write_text(json.dumps(page), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "parity failed"):
            self.build()
        plan = self.plan()
        self.assertIsNone(self.resolve())
        self.assertIn("parity failed", plan["candidate_media_pulse_error"])

    def test_missing_or_wrong_period_dossier_fails_closed(self):
        path = self.site / "candidates/raphael-glucksmann/data.json"
        page = json.loads(path.read_text(encoding="utf-8"))
        page["media"]["period"]["end_date"] = "2026-10-04"
        path.write_text(json.dumps(page), encoding="utf-8")
        self.assertIsNone(self.resolve())
        path.unlink()
        self.assertIsNone(self.resolve())

    def test_canonical_fr_route_is_required_and_unique(self):
        selected = self.build()
        self.assertEqual(selected.destination_url,
                         "https://france2027.app/candidates/raphael-glucksmann/")
        route = next(r for r in self.routes["routes"]
                     if r["entity_id"] == selected.candidate_id and r["language"] == "fr")
        self.routes["routes"].remove(route)
        self.assertIsNone(self.resolve())
        self.routes["routes"].extend([route, copy.deepcopy(route)])
        self.assertIsNone(self.resolve())
        self.routes["routes"].pop()
        route["canonical_url"] = "https://example.com/candidate/"
        self.assertIsNone(self.resolve())

    def test_stale_and_future_end_dates_suppress_candidate_slot(self):
        for day in (date(2026, 10, 4), date(2026, 10, 6)):
            with self.subTest(day=day):
                self.assertIsNone(self.build(planner_date=day))
                now = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                self.assertIsNone(self.resolve(now))

    def test_freshness_uses_paris_date_across_utc_midnight(self):
        now = datetime(2026, 10, 4, 22, 30, tzinfo=timezone.utc)
        self.assertIsNotNone(self.resolve(now))

    def test_monday_has_weekly_issues_agenda_and_current_candidate(self):
        plan = self.plan()
        self.assertEqual(plan["rules"]["newsroom_window"], "complete_week")
        self.assertEqual([p["slot"] for p in plan["fr_posts"]],
                         ["10:15", "12:15", "14:30", "16:45"])
        self.assertIn("issues_movers_complete_week", plan["fr_posts"][0]["key"])
        self.assertIn("agenda_movers_complete_week", plan["fr_posts"][1]["key"])
        self.assertEqual(plan["fr_posts"][3]["key"], "candidate_media_pulse_current:slot:2026-10-05:fr")
        self.assertEqual(plan["fr_posts"][3]["text"], "")
        self.assertEqual(plan["candidate_media_pulse_preview"]["current_start"], "2026-09-29")
        self.assertEqual(plan["candidate_media_pulse_preview"]["current_end"], "2026-10-05")

    def test_english_planner_is_unchanged(self):
        with_candidate = self.plan()["en_posts"]
        self.only()
        without_candidate = self.plan()["en_posts"]
        self.assertEqual(with_candidate, without_candidate)
        self.assertEqual([p["slot"] for p in with_candidate], ["11:30", "19:30"])
        self.assertTrue(all("_movers_complete_week" in p["key"] for p in with_candidate))

    def test_ordinary_day_keeps_current_dossier_window(self):
        period = self.signals["visibility"]["current_period"]
        period.update(start_date="2026-09-30", end_date="2026-10-06")
        self.write_dossier(self.by_id["raphael-glucksmann"])
        now = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        plan = self.plan(now)
        self.assertEqual(plan["rules"]["newsroom_window"], "complete_day")
        candidate = next(p for p in plan["fr_posts"] if p["slot"] == "16:45")
        self.assertEqual(candidate["lane"], "candidate_slot")
        self.assertIn("30 sept.–6 oct.", self.resolve(now).text)

    def test_events_keep_0845_and_candidate_keeps_1645(self):
        with patch.object(daily_plan.social_publish, "render_today_events", return_value="ÉVÉNEMENTS DU JOUR"):
            plan = self.plan()
        self.assertEqual([p["slot"] for p in plan["fr_posts"]],
                         ["08:45", "10:15", "12:15", "14:30", "16:45"])

    def test_legacy_history_cannot_replace_candidate_signals(self):
        self.only()
        with patch.object(daily_plan.candidate_media_pulse, "load_json",
                          side_effect=AssertionError("must use supplied sources")):
            plan = self.plan(legacy_history={
                "candidates": [{
                    "candidate_id": "raphael-glucksmann",
                    "campaign_attention": {"daily_series": [{"record_count": 999999}]},
                }],
            })
        self.assertIsNone(plan["candidate_media_pulse_preview"])

    def test_public_copy_has_boundaries_and_no_raw_counts_or_movers(self):
        self.metric("raphael-glucksmann", 0.212, 123456)
        text = self.build().text
        self.assertNotIn("123456", text)
        self.assertIn("Couverture élection + campagne suivie.", text)
        self.assertIn("Associations non exclusives · ≠ soutien.", text)
        for forbidden in ("popularité", "intention de vote", "gagne", "progresse",
                          "momentum", "leader de la présidentielle"):
            self.assertNotIn(forbidden, text.lower())

    def test_weighted_length_includes_eye_emoji_and_not_equal_sign(self):
        selected = self.build()
        # Independent check for this known template: each of these two
        # codepoints contributes one extra unit; its URL contributes 23.
        expected = len(selected.text) - len(selected.destination_url) + 23 + 2
        self.assertEqual(selected.weighted_length, expected)
        self.assertLessEqual(selected.weighted_length, 280)
        self.assertEqual(product.weighted_x_length("👀≠"), 4)

    def test_identity_contains_candidate_end_and_locale(self):
        self.assertEqual(self.build().product_id,
                         "candidate_media_pulse_current:raphael-glucksmann:2026-10-05:fr")

    def test_queue_preserves_exact_candidate_product_text(self):
        selected = self.build()
        source = {"locale": "fr", "slot": "16:45", "lane": "newsroom",
                  "key": selected.product_id, "text": selected.text, "score": selected.score}
        source["text"] += "\n"  # Queue must preserve even this rendered whitespace.
        queue = daily_queue.new_queue(queue_date="2026-10-05", created_at=self.monday,
                                      posts=[source])
        self.assertEqual(queue["items"][0]["text"], source["text"])

    def test_queue_rejects_wrong_url_locale_date_or_excess_length(self):
        selected = self.build()
        source = {"locale": "fr", "slot": "16:45", "lane": "newsroom",
                  "key": selected.product_id, "text": selected.text, "score": selected.score}
        variants = [
            {**source, "text": source["text"].replace("raphael-glucksmann/", "marine-le-pen/")},
            {**source, "text": source["text"] + " https://example.com/"},
            {**source, "text": source["text"] + "x" * 281},
            {**source, "locale": "en"},
            {**source, "key": source["key"].replace("2026-10-05", "2026-10-04")},
            {**source, "key": product.PRODUCT_TYPE + ":bad"},
        ]
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                daily_queue.new_queue(queue_date="2026-10-05", created_at=self.monday,
                                      posts=[variant])

    def test_same_day_queue_does_not_rerank_or_rerender(self):
        state = daily_queue.social_publish.build_bootstrap_state(
            {"items": []}, {"campaign_events": []}, now=self.monday,
        )
        with patch.object(daily_queue, "build_core_plan", return_value=self.plan()) as build:
            first = daily_queue.build_queue(state=state, now=self.monday)
            self.metric("edouard-philippe", 0.999, 999)
            second = daily_queue.build_queue(state=state, now=self.monday)
        self.assertIs(first, second)
        self.assertEqual(build.call_count, 1)
        candidate = next(p for p in second["items"] if p["slot"] == "16:45")
        self.assertEqual(candidate["text"], "")
        self.assertEqual(candidate["lane"], "candidate_slot")

    def test_date_reuses_editorial_range_helper(self):
        self.assertIn("\n29 sept.–5 oct.\n", self.build().text)
        self.assertNotIn("29/09/2026", self.build().text)

    def test_refreshed_value_is_the_actual_sent_payload(self):
        state = self.morning_state()
        self.metric("raphael-glucksmann", 0.250, 70)
        client, save = self.execute(state)
        sent = client.return_value.create_post.call_args.args[0]
        self.assertIn("Raphaël Glucksmann — 25,0 %", sent)
        self.assertNotIn("21,2 %", sent)
        save.assert_called_once()
        item = next(i for i in daily_queue.queue_from_state(state)["items"] if i["slot"] == "16:45")
        self.assertEqual(item["text"], sent)
        self.assertEqual(item["status"], "published")

    def test_refreshed_leader_is_published_and_others_stay_immutable(self):
        state = self.morning_state()
        original = copy.deepcopy(daily_queue.queue_from_state(state))
        self.metric("edouard-philippe", 0.333, 88)
        client, _save = self.execute(state)
        sent = client.return_value.create_post.call_args.args[0]
        self.assertIn("Édouard Philippe — 33,3 %", sent)
        self.assertTrue(sent.endswith("https://france2027.app/candidates/edouard-philippe/"))
        current = daily_queue.queue_from_state(state)
        self.assertEqual([i for i in original["items"] if i["slot"] != "16:45"],
                         [i for i in current["items"] if i["slot"] != "16:45"])
        for item in original["items"]:
            if item["slot"] != "16:45":
                self.assertEqual(daily_queue.resolve_slot_post(item, now=self.monday).text, item["text"])

    def test_fresh_parity_failure_skips_before_any_buffer_call(self):
        state = self.morning_state()
        self.metric("raphael-glucksmann", 0.250, 70)
        path = self.site / "candidates/raphael-glucksmann/data.json"
        page = json.loads(path.read_text(encoding="utf-8"))
        page["dossier"]["media_pulse"]["share"] = 0.212
        path.write_text(json.dumps(page), encoding="utf-8")
        before = copy.deepcopy(state)
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()
        self.assertEqual(state, before)

    def test_fresh_stale_period_skips_before_any_buffer_call(self):
        state = self.morning_state()
        self.signals["visibility"]["current_period"].update(
            start_date="2026-09-28", end_date="2026-10-04",
        )
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()

    def test_fresh_eligibility_is_rechecked_at_execution(self):
        state = self.morning_state()
        record = next(c for c in self.registry["candidates"] if c["candidate_id"] == "raphael-glucksmann")
        record["upstream_presence"] = "temporarily_missing"
        client, _save = self.execute(state)
        self.assertIn("Édouard Philippe — 20,1 %", client.return_value.create_post.call_args.args[0])

    def test_fresh_canonical_route_failure_skips(self):
        state = self.morning_state()
        self.routes["routes"] = [r for r in self.routes["routes"]
                                 if not (r["entity_id"] == "raphael-glucksmann" and r["language"] == "fr")]
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()

    def test_fresh_weighted_length_failure_skips(self):
        state = self.morning_state()
        name = "Raphaël " * 60
        self.by_id["raphael-glucksmann"]["candidate_name"] = name
        record = next(c for c in self.registry["candidates"] if c["candidate_id"] == "raphael-glucksmann")
        record["candidate_name"] = name
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()

    def test_candidate_instruction_rejects_frozen_text_at_execution(self):
        state = self.morning_state()
        item = next(i for i in daily_queue.queue_from_state(state)["items"] if i["slot"] == "16:45")
        item["text"] = self.build().text
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()

    def test_new_evidence_after_empty_morning_can_fill_instruction(self):
        self.only()
        state = self.morning_state()
        self.metric("raphael-glucksmann", 0.250, 70)
        client, _save = self.execute(state)
        self.assertIn("25,0 %", client.return_value.create_post.call_args.args[0])

    def test_legacy_frozen_candidate_item_is_never_used_as_fallback(self):
        selected = self.build()
        legacy = {"locale": "fr", "slot": "16:45", "lane": "newsroom",
                  "key": selected.product_id, "text": selected.text, "score": selected.score}
        self.metric("edouard-philippe", 0.333, 88)
        self.write_sources()
        fresh = daily_queue.resolve_slot_post(legacy, now=self.monday, site_root=self.site)
        self.assertIn("Édouard Philippe — 33,3 %", fresh.text)
        (self.site / "candidate_signals.json").unlink()
        self.assertIsNone(daily_queue.resolve_slot_post(legacy, now=self.monday, site_root=self.site))


if __name__ == "__main__":
    unittest.main()
