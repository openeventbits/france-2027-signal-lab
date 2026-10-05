"""Exact authority/consumer parity; no publication artifacts are regenerated."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import agenda_page_contract as authority
import build_agenda_pages as page
import coverage_metric_contract as social
from social import newsroom_products


ROOT = Path(__file__).resolve().parent


class AgendaSharedMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = json.loads((ROOT / "agenda_coverage_history.json").read_text(encoding="utf-8"))

    def period(self, start, end, payload=None):
        payload = payload if payload is not None else self.history
        return authority.build_agenda_period_metric(
            payload["topics"], start_date=start, end_date=end,
            daily_denominators=payload["daily"],
        )

    def assert_window_parity(self, mode):
        snapshot = social.build_agenda_metric_snapshot(self.history, window_mode=mode)
        previous = self.period(snapshot.previous_start, snapshot.previous_end)
        current = self.period(snapshot.current_start, snapshot.current_end)
        topics = [{"id": t["id"], "daily_activity": t["daily"]} for t in self.history["topics"]]
        period = dict(previous_start=snapshot.previous_start, previous_end=snapshot.previous_end,
                      latest_start=snapshot.current_start, latest_end=snapshot.current_end)
        for topic, before, after, row in zip(topics, previous.rows, current.rows, snapshot.rows):
            with self.subTest(topic=row.entity_id, mode=mode):
                with patch.object(authority, "build_agenda_period_metric", wraps=authority.build_agenda_period_metric) as calculate:
                    comparison = page._window_comparison(topic, topics, period)
                self.assertEqual(calculate.call_count, 2)
                self.assertEqual(row.previous_evidence, before.numerator)
                self.assertEqual(row.current_evidence, after.numerator)
                self.assertEqual(row.previous_denominator, before.denominator)
                self.assertEqual(row.current_denominator, after.denominator)
                self.assertEqual(row.previous_raw, before.raw_share * 100.0)
                self.assertEqual(row.current_raw, after.raw_share * 100.0)
                self.assertEqual(comparison["previous_source_day_count"], before.numerator)
                self.assertEqual(comparison["latest_source_day_count"], after.numerator)
                self.assertEqual(comparison["previous_agenda_share"], before.raw_share)
                self.assertEqual(comparison["latest_agenda_share"], after.raw_share)
                self.assertEqual((row.previous_display, row.current_display, row.display_delta),
                                 social.display_triplet(before.raw_share * 100.0, after.raw_share * 100.0))
        self.assertEqual(previous.denominator_id, snapshot.denominator_id)
        self.assertEqual(current.aggregation_unit, snapshot.aggregation_unit)
        return snapshot

    def test_complete_day_exact_page_social_authority_parity(self):
        self.assert_window_parity(social.WINDOW_COMPLETE_DAY)

    def test_complete_monday_sunday_week_exact_parity(self):
        snapshot = self.assert_window_parity(social.WINDOW_COMPLETE_WEEK)
        from datetime import date
        self.assertEqual(date.fromisoformat(snapshot.current_start).weekday(), 0)
        self.assertEqual(date.fromisoformat(snapshot.current_end).weekday(), 6)

    def test_social_calls_authority_and_does_not_divide_again(self):
        with patch.object(authority, "build_agenda_period_metric", wraps=authority.build_agenda_period_metric) as calculate, \
             patch.object(social, "_share", side_effect=AssertionError("Agenda must use authority shares")):
            social.build_agenda_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_DAY)
        self.assertEqual(calculate.call_count, 2)

    def test_page_and_social_take_returned_rows_from_the_authority(self):
        # Different valid authority rows must drive both consumers' outputs;
        # a ceremonial call followed by an independent calculation would fail.
        rows = authority.agenda_source_day_rows({key: 1 for key in authority.CANONICAL_AGENDA_IDS})
        metric = authority.AgendaPeriodMetric("2026-10-03", "2026-10-04", rows)
        topics = [{"id": t["id"], "daily_activity": t["daily"]} for t in self.history["topics"]]
        with patch.object(authority, "build_agenda_period_metric", return_value=metric):
            snapshot = social.build_agenda_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_DAY)
            comparison = page._window_comparison(topics[0], topics, {
                "previous_start": snapshot.previous_start, "previous_end": snapshot.previous_end,
                "latest_start": snapshot.current_start, "latest_end": snapshot.current_end,
            })
        self.assertEqual(comparison["latest_source_day_count"], 1)
        self.assertEqual(comparison["latest_agenda_share"], rows[0].raw_share)
        for row in snapshot.rows:
            self.assertEqual(row.current_evidence, 1)
            self.assertEqual(row.current_denominator, 6)
            self.assertEqual(row.current_raw, rows[0].raw_share * 100.0)

    def test_historical_page_also_calls_authority(self):
        topics = [{"topic_id": t["id"], "coverage_history": t} for t in self.history["topics"]]
        with patch.object(authority, "build_agenda_period_metric", wraps=authority.build_agenda_period_metric) as calculate:
            comparison = page._history_comparison(topics[0], topics)
        self.assertEqual(calculate.call_count, 2)
        metric = self.period(comparison["latest_start"], comparison["latest_end"])
        self.assertEqual(comparison["latest_source_day_count"], metric.rows[0].numerator)
        self.assertEqual(comparison["latest_agenda_share"], metric.rows[0].raw_share)

    def test_page_composition_denominator_captions_use_authority(self):
        topics = page.build_from_paths(write=False)["projection"]["topics"]
        rows = authority.agenda_source_day_rows({key: 1 for key in authority.CANONICAL_AGENDA_IDS})
        metric = authority.AgendaPeriodMetric("2026-10-03", "2026-10-04", rows)
        for history in (False, True):
            reference = topics[0]["history_comparison"] if history else topics[0]["current"]["comparison"]
            with self.subTest(history=history), patch.object(authority, "build_agenda_period_metric", return_value=metric):
                self.assertEqual(page._comparison_totals(topics, reference, history=history), (6, 6))

    def test_polls_remain_in_denominator_before_public_ranking_filter(self):
        snapshot = social.build_agenda_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_WEEK)
        polls = next(row for row in snapshot.rows if row.entity_id == "polls_race")
        self.assertGreater(polls.current_evidence, 0)
        self.assertEqual(sum(row.current_evidence for row in snapshot.rows), polls.current_denominator)
        self.assertGreater(polls.current_denominator,
                           sum(row.current_evidence for row in snapshot.rows if row.entity_id != "polls_race"))
        for rank in (social.rank_movers, social.rank_current_share):
            self.assertNotIn("polls_race", {r.entity_id for r in rank(snapshot, excluded_entity_ids={"polls_race"})})
        issues = json.loads((ROOT / "issue_coverage_history.json").read_text(encoding="utf-8"))
        products = newsroom_products.build_newsroom_products(issue_payload=issues, agenda_payload=self.history, locale="fr")
        agenda = [p for p in products if p.family == "agenda"]
        self.assertTrue(agenda)
        for product in agenda:
            self.assertNotIn("polls_race", {row.entity_id for row in product.rows})

    def test_display_delta_is_endpoints_first_on_shared_rows(self):
        days = ("2026-10-03", "2026-10-04")
        counts = (100400, 100600)  # 10.04 -> 10.06: raw delta .02, displayed delta .1.
        topics = [{"id": key, "daily": [
            {"date": day, "source_day_count": counts[i] if key == authority.CANONICAL_AGENDA_IDS[0]
             else 1000000 - counts[i] if key == "polls_race" else 0}
            for i, day in enumerate(days)]} for key in authority.CANONICAL_AGENDA_IDS]
        snapshot = social.build_agenda_metric_snapshot({"topics": topics, "daily": [
            {"date": day, "total_agenda_topic_source_days": 1000000} for day in days]},
            window_mode=social.WINDOW_COMPLETE_DAY)
        row = snapshot.rows[0]
        self.assertEqual((row.previous_display, row.current_display, row.display_delta), (10.0, 10.1, 0.1))
        self.assertNotEqual(row.display_delta, social.display_round(row.current_raw - row.previous_raw))

    def test_zero_comparison_denominator_fails_closed(self):
        topics = [{"id": key, "daily": [{"date": "2026-10-04", "source_day_count": 0}]}
                  for key in authority.CANONICAL_AGENDA_IDS]
        with self.assertRaisesRegex(authority.AgendaPageContractError, "denominator must be positive"):
            authority.build_agenda_period_metric(topics, start_date="2026-10-04", end_date="2026-10-04")
        with self.assertRaises(authority.AgendaPageContractError):
            authority.agenda_source_day_share(0, 0)
        self.assertEqual(authority.agenda_source_day_share(0, 0, allow_empty_observation=True), 0.0)
        with self.assertRaises(authority.AgendaPageContractError):
            authority.agenda_source_day_share(1, 0, allow_empty_observation=True)
        for topic in topics:
            topic["daily"].insert(0, {"date": "2026-10-03", "source_day_count": 0})
        with self.assertRaisesRegex(social.MetricContractError, "denominator must be positive"):
            social.build_agenda_metric_snapshot({"topics": topics, "daily": [
                {"date": day, "total_agenda_topic_source_days": 0} for day in ("2026-10-03", "2026-10-04")
            ]}, window_mode=social.WINDOW_COMPLETE_DAY)

    def test_missing_weekly_day_or_topic_point_fails_closed(self):
        snapshot = social.build_agenda_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_WEEK)
        for root_missing in (True, False):
            payload = copy.deepcopy(self.history)
            rows = payload["daily"] if root_missing else payload["topics"][0]["daily"]
            rows[:] = [r for r in rows if r["date"] != snapshot.current_start]
            with self.subTest(root_missing=root_missing), self.assertRaises(social.MetricContractError):
                social.build_agenda_metric_snapshot(payload, window_mode=social.WINDOW_COMPLETE_WEEK)

    def test_missing_duplicate_unknown_topics_and_bad_counts_fail_closed(self):
        day = self.history["daily"][-1]["date"]
        for kind in ("missing", "duplicate", "unknown", "negative", "bool", "float", "string", "missing_count", "impossible"):
            topics = copy.deepcopy(self.history["topics"])
            if kind == "missing": topics.pop()
            elif kind == "duplicate": topics.append(copy.deepcopy(topics[0]))
            elif kind == "unknown": topics[0]["id"] = "not-agenda"
            else:
                point = topics[0]["daily"][-1]
                if kind == "missing_count": point.pop("source_day_count")
                elif kind == "impossible": point["source_day_count"] = point["item_count"] + 1
                else: point["source_day_count"] = {"negative": -1, "bool": True, "float": 1.5, "string": "2"}[kind]
            with self.subTest(kind=kind), self.assertRaises(authority.AgendaPageContractError):
                authority.build_agenda_period_metric(topics, start_date=day, end_date=day)

    def test_dates_and_published_denominator_are_checked(self):
        start, end = [r["date"] for r in self.history["daily"][-2:]]
        for kind in ("duplicate", "unsorted", "denominator", "boundary"):
            payload = copy.deepcopy(self.history)
            if kind == "duplicate": payload["topics"][0]["daily"].append(copy.deepcopy(payload["topics"][0]["daily"][-1]))
            elif kind == "unsorted": payload["topics"][0]["daily"].reverse()
            elif kind == "denominator": payload["daily"][-1]["total_agenda_topic_source_days"] += 1
            with self.subTest(kind=kind), self.assertRaises(authority.AgendaPageContractError):
                self.period(end if kind == "boundary" else start, start if kind == "boundary" else end, payload)

    def test_canonical_order_and_input_purity(self):
        payload = copy.deepcopy(self.history)
        payload["topics"].reverse()
        before = copy.deepcopy(payload)
        day = payload["daily"][-1]["date"]
        metric = self.period(day, day, payload)
        self.assertEqual(tuple(row.topic_id for row in metric.rows), authority.CANONICAL_AGENDA_IDS)
        self.assertEqual(payload, before)


if __name__ == "__main__":
    unittest.main()
