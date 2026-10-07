import copy
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))
import candidate_media_pulse as product
import daily_plan
import daily_queue
from candidate_visibility_history_contract import round_visibility_ratio


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class CandidateMediaPulseTests(unittest.TestCase):
    def setUp(self):
        self.signals = load("candidate_signals.json")
        self.registry = load("candidate_candidacy_status.json")
        self.routes = load("route_registry.json")
        self.history = load("candidate_visibility_history.json")
        self.issues = load("issue_coverage_history.json")
        self.agenda = load("agenda_coverage_history.json")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.by_id = {c["candidate_id"]: c for c in self.signals["candidates"]}
        self.history_by_id = {c["candidate_id"]: c for c in self.history["candidates"]}
        self.align(date(2026, 10, 7))
        for lane in (product.GENERAL_LANE, product.CAMPAIGN_LANE):
            for row in self.history["lanes"][lane]["daily_denominators"]:
                row.update(record_count=10, publisher_count=1)
            for candidate in self.history["candidates"]:
                for row in candidate[lane]["daily_series"]:
                    row.update(record_count=0, publisher_count=0, share=0.0)
        self.only("raphael-glucksmann", "edouard-philippe")
        self.point("raphael-glucksmann", product.GENERAL_LANE, -2, 1)
        self.point("raphael-glucksmann", product.GENERAL_LANE, -1, 5)
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -2, 1)
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -1, 3)

    def align(self, today):
        self.today = today
        self.now = datetime.combine(today, time(16, 45), tzinfo=ZoneInfo("Europe/Paris")).astimezone(timezone.utc)
        self.morning = self.now.replace(hour=6, minute=25)
        dates = [(today - timedelta(days=29-i)).isoformat() for i in range(29)]
        self.history["period"].update(start_date=dates[0], end_date=dates[-1], data_as_of=dates[-1])
        for lane in (product.GENERAL_LANE, product.CAMPAIGN_LANE):
            for row, day in zip(self.history["lanes"][lane]["daily_denominators"], dates):
                row["date"] = day
            for candidate in self.history["candidates"]:
                for row, day in zip(candidate[lane]["daily_series"], dates):
                    row["date"] = day
        for key in ("current_period", "general_current_period"):
            self.signals["visibility"][key].update(start_date=(today-timedelta(days=6)).isoformat(), end_date=today.isoformat())

    def only(self, *identifiers):
        for identifier, candidate in self.by_id.items():
            for lane in (product.GENERAL_LANE, product.CAMPAIGN_LANE):
                candidate[lane].update(evidence_state="reported" if identifier in identifiers else "not_observed",
                                       share=0.5 if identifier in identifiers else None,
                                       record_count=5 if identifier in identifiers else None)

    def point(self, identifier, lane, index, count):
        row = self.history_by_id[identifier][lane]["daily_series"][index]
        denominator = self.history["lanes"][lane]["daily_denominators"][index]["record_count"]
        row.update(record_count=count, publisher_count=1 if count else 0,
                   share=round_visibility_ratio(count / denominator) if denominator else None)

    def denominator(self, lane, index, count):
        self.history["lanes"][lane]["daily_denominators"][index].update(record_count=count, publisher_count=1 if count else 0)
        for identifier in self.history_by_id:
            self.point(identifier, lane, index, 0)

    def build(self, **kwargs):
        return product.build_product(candidate_signals=self.signals, candidacy_registry=self.registry,
            route_registry=self.routes, visibility_history=self.history,
            planner_date=kwargs.pop("planner_date", self.today), site_root=self.site, **kwargs)

    def write_sources(self):
        for name, payload in (("candidate_signals.json", self.signals),
                              ("candidate_visibility_history.json", self.history),
                              ("candidate_candidacy_status.json", self.registry),
                              ("route_registry.json", self.routes)):
            (self.site / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def plan(self):
        return daily_plan.build_plan(candidate_payload=self.history, issue_payload=self.issues,
            agenda_payload=self.agenda, recent_changes={"items": []}, campaign_events={"campaign_events": []},
            now=self.now, max_fr=8, max_en=2, max_updates=0, planner_state=daily_plan.new_planner_state(),
            candidate_signals_payload=self.signals, candidacy_payload=self.registry,
            route_payload=self.routes, candidate_site_root=self.site)

    def resolve(self):
        self.write_sources()
        post = next(p for p in self.plan()["fr_posts"] if p["slot"] == "16:45")
        return daily_queue.resolve_slot_post(post, now=self.now, site_root=self.site)

    def morning_state(self):
        state = daily_queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=self.morning)
        with patch.object(daily_queue, "build_core_plan", return_value=self.plan()):
            daily_queue.build_queue(state=state, now=self.morning)
        return state

    def execute(self, state):
        self.write_sources()
        args = Namespace(state="unused.json", state_output="unused-output.json", slot="16:45",
                         now=self.now.isoformat(), dry_run=False)
        with patch.object(daily_queue, "ROOT", self.site), \
             patch.object(daily_queue, "_load_json", return_value=state), \
             patch.object(daily_queue, "save_state") as save, \
             patch.object(sys, "stdout", new_callable=io.StringIO), \
             patch.object(daily_queue.social_publish.BufferClient, "from_env") as client:
            client.return_value.recent_posts.return_value = []
            client.return_value.create_post.return_value = "mock-post-id"
            self.assertEqual(daily_queue.run_slot(args), 0)
        return client, save

    def test_general_daily_values_and_url(self):
        selected = self.build()
        self.assertEqual(selected.lane, product.GENERAL_LANE)
        self.assertEqual((selected.current_percentage, selected.previous_percentage, selected.delta_pp), (50, 10, 40))
        self.assertIn("VISIBILITÉ MÉDIATIQUE · 24 H · VS 24 H PRÉCÉDENTES", selected.text)
        self.assertIn("50,0 %", selected.text)
        self.assertIn("contre 10,0 %", selected.text)
        self.assertIn("+40,0 pts", selected.text)
        self.assertIn("hors campagne", selected.text)
        self.assertIn("pas intentions de vote", selected.text)
        self.assertTrue(selected.text.endswith("https://france2027.app/candidates/raphael-glucksmann/"))

    def test_campaign_daily_negative_strongest_movement(self):
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -2, 9)
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -1, 1)
        selected = self.build()
        self.assertEqual(selected.candidate_id, "edouard-philippe")
        self.assertEqual(selected.lane, product.CAMPAIGN_LANE)
        self.assertIn("VISIBILITÉ DE CAMPAGNE · 24 H", selected.text)
        self.assertIn("−80,0 pts", selected.text)
        self.assertIn("Visibilité de campagne, pas intentions de vote.", selected.text)

    def test_values_are_from_counts_not_signals_or_rounded_daily_shares(self):
        before = self.build()
        self.by_id[before.candidate_id][before.lane].update(share=0.999, record_count=999)
        self.assertEqual(self.build(), before)

    def test_tie_break_evidence_then_id_then_lane(self):
        self.only("edouard-philippe", "raphael-glucksmann")
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -2, 2)
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -1, 6)
        self.assertEqual(self.build().candidate_id, "edouard-philippe")
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -2, 1)
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -1, 5)
        self.point("edouard-philippe", product.GENERAL_LANE, -2, 1)
        self.point("edouard-philippe", product.GENERAL_LANE, -1, 5)
        self.assertEqual((self.build().candidate_id, self.build().lane), ("edouard-philippe", product.GENERAL_LANE))
        self.signals["candidates"].reverse()
        self.assertEqual(self.build().candidate_id, "edouard-philippe")

    def test_ineligible_and_temporarily_missing_candidates_are_excluded(self):
        for identifier in ("jordan-bardella", "antoine-mikolajczak"):
            self.only(identifier, "raphael-glucksmann")
            self.point(identifier, product.CAMPAIGN_LANE, -1, 10)
            self.assertEqual(self.build().candidate_id, "raphael-glucksmann")

    def test_registry_is_eligibility_authority(self):
        selected = self.build()
        self.by_id[selected.candidate_id]["candidacy"]["active_field_eligible"] = False
        self.assertEqual(self.build().candidate_id, selected.candidate_id)
        record = next(c for c in self.registry["candidates"] if c["candidate_id"] == selected.candidate_id)
        record["upstream_presence"] = "temporarily_missing"
        self.assertNotEqual(self.build().candidate_id, selected.candidate_id)

    def test_no_reported_evidence_fails_closed(self):
        self.only()
        self.assertIsNone(self.build())
        self.assertIsNone(self.resolve())

    def test_null_or_invalid_reported_readiness_is_unavailable(self):
        self.only("raphael-glucksmann")
        for lane in (product.GENERAL_LANE, product.CAMPAIGN_LANE):
            self.by_id["raphael-glucksmann"][lane]["share"] = None
        self.assertIsNone(self.build())
        self.by_id["raphael-glucksmann"][product.GENERAL_LANE]["share"] = float("nan")
        self.assertIsNone(self.resolve())

    def test_zero_denominator_is_rejected_for_either_period_and_lane(self):
        for index in (-2, -1):
            for lane in (product.GENERAL_LANE, product.CAMPAIGN_LANE):
                self.denominator(lane, index, 0)
        self.assertIsNone(self.build())
        self.assertIsNone(self.resolve())

    def test_insufficient_or_gapped_or_malformed_history_fails_closed(self):
        for count in (1, 13):
            with self.subTest(count=count):
                history = copy.deepcopy(self.history)
                self.history["lanes"][product.GENERAL_LANE]["daily_denominators"] = history["lanes"][product.GENERAL_LANE]["daily_denominators"][-count:]
                self.assertIsNone(self.resolve())
                self.history = history
        self.history["candidates"][0][product.GENERAL_LANE]["daily_series"][-1]["share"] = float("nan")
        self.assertIsNone(self.resolve())

    def test_stale_or_future_history_and_unready_signals_fail_closed(self):
        for day in (self.today-timedelta(days=1), self.today+timedelta(days=1)):
            self.assertIsNone(self.build(planner_date=day))
        self.signals["visibility"]["current_period"]["end_date"] = "2026-10-06"
        self.assertIsNone(self.build())

    def test_complete_utc_day_excludes_current_day_across_paris_midnight(self):
        # At 00:30 Paris the previous UTC day is still in progress.
        self.assertIsNone(self.build(utc_date=self.today-timedelta(days=1)))
        self.assertEqual(self.build().current_end, "2026-10-06")

    def test_monday_weekly_sum_of_counts_not_average_percentages(self):
        self.align(date(2026, 10, 12))
        self.only("raphael-glucksmann")
        for index in range(-14, 0):
            self.denominator(product.GENERAL_LANE, index, 100 if index == -1 else 2)
            self.point("raphael-glucksmann", product.GENERAL_LANE, index, 1)
        selected = self.build()
        self.assertEqual(selected.window_mode, "complete_week")
        self.assertEqual((selected.previous_numerator, selected.previous_denominator), (7, 14))
        self.assertEqual((selected.current_numerator, selected.current_denominator), (7, 112))
        self.assertEqual(selected.current_percentage, 6.3)
        self.assertEqual(selected.delta_pp, -43.7)
        self.assertNotEqual(selected.current_percentage, round((6*50+1)/7, 1))
        self.assertIn("7 JOURS · VS 7 JOURS PRÉCÉDENTS", selected.text)
        self.assertLessEqual(selected.weighted_length, 270)
        self.assertNotIn("articles", selected.text)
        self.assertNotIn("mentions", selected.text)
        self.assertIn("hors campagne", selected.text)
        self.assertIn("pas intentions de vote", selected.text)
        self.assertIn(selected.destination_url, selected.text)
        self.assertEqual((selected.current_start, selected.current_end), ("2026-10-05", "2026-10-11"))
        self.assertEqual((selected.previous_start, selected.previous_end), ("2026-09-28", "2026-10-04"))

    def test_tuesday_through_sunday_use_daily(self):
        for offset in range(1, 7):
            self.align(date(2026, 10, 12)+timedelta(days=offset))
            self.assertEqual(self.build().window_mode, "complete_day")

    def test_one_existing_blank_late_bound_slot_on_monday_and_ordinary_day(self):
        for day in (date(2026, 10, 7), date(2026, 10, 12)):
            self.align(day)
            posts = self.plan()["fr_posts"]
            candidate = [p for p in posts if p["slot"] == "16:45"]
            self.assertEqual(len(candidate), 1)
            self.assertEqual(candidate[0]["lane"], "candidate_slot")
            self.assertEqual(candidate[0]["text"], "")
            self.assertEqual(sum(p["key"].startswith(product.PRODUCT_TYPE+":") for p in posts), 1)

    def test_canonical_route_missing_duplicate_or_wrong_fails_closed(self):
        selected = self.build()
        route = next(r for r in self.routes["routes"] if r["entity_id"] == selected.candidate_id and r["language"] == "fr")
        self.routes["routes"].remove(route)
        self.assertIsNone(self.resolve())
        self.routes["routes"].extend([route, copy.deepcopy(route)])
        self.assertIsNone(self.resolve())
        self.routes["routes"].pop()
        route["canonical_url"] = "https://example.com/"
        self.assertIsNone(self.resolve())

    def test_identity_keeps_original_type_and_publication_date(self):
        selected = self.build()
        self.assertEqual(selected.product_id, f"candidate_media_pulse_current:{selected.candidate_id}:{self.today}:fr")

    def test_weighted_length_and_required_copy(self):
        for lane in (product.GENERAL_LANE, product.CAMPAIGN_LANE):
            self.only("raphael-glucksmann")
            self.point("raphael-glucksmann", lane, -1, 10)
            selected = self.build()
            self.assertLessEqual(selected.weighted_length, 270)
            self.assertEqual(selected.weighted_length, product.weighted_x_length(selected.text))
            for token in ("contre", "Écart", "pas intentions de vote", selected.destination_url):
                self.assertIn(token, selected.text)
            self.assertIn("hors campagne" if lane == product.GENERAL_LANE else "visibilité de campagne", selected.text)
            for forbidden in ("articles", "mentions", "👀", "↑", "↓", "popularité", "momentum", "#"):
                self.assertNotIn(forbidden, selected.text)
        self.assertEqual(product.weighted_x_length("👀≠"), 4)

    def test_queue_preserves_exact_rendered_copy(self):
        selected = self.build()
        raw = dict(locale="fr", slot="16:45", lane="newsroom", key=selected.product_id,
                   text=selected.text, score=selected.score)
        queue = daily_queue.new_queue(queue_date=str(self.today), created_at=self.morning, posts=[raw])
        self.assertEqual(queue["items"][0]["text"], selected.text)
        for variant in ({**raw, "locale": "en"}, {**raw, "text": selected.text+"x"*281},
                        {**raw, "text": selected.text.replace(selected.destination_url, "https://example.com/")}):
            with self.assertRaises(ValueError):
                daily_queue.new_queue(queue_date=str(self.today), created_at=self.morning, posts=[variant])

    def test_same_day_queue_is_immutable(self):
        state = self.morning_state()
        original = copy.deepcopy(daily_queue.queue_from_state(state))
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -1, 10)
        with patch.object(daily_queue, "build_core_plan") as rebuild:
            result = daily_queue.build_queue(state=state, now=self.morning)
        rebuild.assert_not_called()
        self.assertEqual(result, original)

    def test_execution_uses_refreshed_history_and_records_actual_metadata(self):
        state = self.morning_state()
        original = copy.deepcopy(daily_queue.queue_from_state(state))
        self.point("edouard-philippe", product.CAMPAIGN_LANE, -1, 10)
        selected = self.build()
        client, save = self.execute(state)
        self.assertEqual(client.return_value.create_post.call_args.args[0], selected.text)
        save.assert_called_once()
        item = next(i for i in daily_queue.queue_from_state(state)["items"] if i["slot"] == "16:45")
        self.assertEqual(item["status"], "published")
        self.assertEqual(item["metric_id"], selected.lane)
        self.assertEqual(item["window_mode"], selected.window_mode)
        self.assertEqual(item["comparison_end"], selected.previous_end)
        for before in original["items"]:
            if before["slot"] != "16:45":
                self.assertEqual(next(i for i in daily_queue.queue_from_state(state)["items"] if i["id"] == before["id"]), before)

    def test_unavailable_history_skips_before_buffer_and_save(self):
        state = self.morning_state()
        self.history["period"]["data_as_of"] = "2026-10-05"
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()

    def test_missing_history_skips_and_never_uses_frozen_copy(self):
        selected = self.build()
        raw = dict(locale="fr", slot="16:45", lane="newsroom", key=selected.product_id,
                   text=selected.text, score=selected.score)
        self.write_sources()
        (self.site / "candidate_visibility_history.json").unlink()
        self.assertIsNone(daily_queue.resolve_slot_post(raw, now=self.now, site_root=self.site))

    def test_frozen_instruction_or_overlong_identity_skips(self):
        state = self.morning_state()
        item = next(i for i in daily_queue.queue_from_state(state)["items"] if i["slot"] == "16:45")
        item["text"] = self.build().text
        client, save = self.execute(state)
        client.assert_not_called()
        save.assert_not_called()
        identifier = self.build().candidate_id
        long_name = ("Raphaël " * 60).strip()
        self.by_id[identifier]["candidate_name"] = long_name
        self.history_by_id[identifier]["candidate_name"] = long_name
        next(c for c in self.registry["candidates"] if c["candidate_id"] == identifier)["candidate_name"] = long_name
        self.assertIsNone(self.resolve())

    def test_empty_morning_can_resolve_after_readiness_refresh(self):
        self.only()
        state = self.morning_state()
        self.only("raphael-glucksmann")
        client, save = self.execute(state)
        self.assertIn("50,0 %", client.return_value.create_post.call_args.args[0])
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
