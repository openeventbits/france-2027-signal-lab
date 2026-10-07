"""Exact Issue source-day authority parity; publication artifacts are not written."""
import copy
import json
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import build_issue_pages as page
import build_issue_coverage_history as history_builder
import issue_page_contract as authority
import coverage_metric_contract as social
from social import newsroom_products


ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class IssueSharedMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = load("issue_coverage_history.json")
        cls.news = load("news_wire.json")
        cls.candidate_history = load("candidate_agenda_history.json")
        cls.agenda = load("agenda_coverage_history.json")
        cls.evolution = cls.news["policy_agenda"]["evolution"]
        cls.current_day = cls.history["period"]["end_date"]
        cls.previous_day = (date.fromisoformat(cls.current_day) - timedelta(days=1)).isoformat()

    def page_period(self, start, end, evolution=None, **kwargs):
        evolution = self.evolution if evolution is None else evolution
        return authority.build_issue_period_metric(
            evolution["topics"], start_date=start, end_date=end,
            daily_denominators=evolution["accepted_daily_activity"], **kwargs,
        )

    def assert_period_parity(self, mode):
        snapshot = social.build_issue_metric_snapshot(self.history, window_mode=mode)
        previous = self.page_period(snapshot.previous_start, snapshot.previous_end)
        current = self.page_period(snapshot.current_start, snapshot.current_end)
        for before, after, row in zip(previous.rows, current.rows, snapshot.rows):
            with self.subTest(issue=row.entity_id, mode=mode):
                self.assertEqual(row.entity_id, before.issue_id)
                self.assertEqual(row.previous_evidence, before.numerator)
                self.assertEqual(row.current_evidence, after.numerator)
                self.assertEqual(row.previous_denominator, before.denominator)
                self.assertEqual(row.current_denominator, after.denominator)
                self.assertEqual(row.previous_raw, before.raw_share * 100.0)
                self.assertEqual(row.current_raw, after.raw_share * 100.0)
                self.assertEqual(row.display_delta, social.display_round(
                    row.current_display - row.previous_display))
        self.assertEqual(snapshot.aggregation_unit, current.aggregation_unit)
        self.assertEqual(snapshot.denominator_id, current.denominator_id)
        return snapshot

    def test_real_daily_numerators_denominators_and_raw_shares_match_page_authority(self):
        snapshot = self.assert_period_parity(social.WINDOW_COMPLETE_DAY)
        self.assertEqual(date.fromisoformat(snapshot.previous_end) + timedelta(days=1),
                         date.fromisoformat(snapshot.current_start))

    def test_real_weekly_numerators_denominators_and_raw_shares_match_page_authority(self):
        snapshot = self.assert_period_parity(social.WINDOW_COMPLETE_WEEK)
        self.assertEqual(date.fromisoformat(snapshot.current_start).weekday(), 0)
        self.assertEqual(date.fromisoformat(snapshot.current_end).weekday(), 6)
        self.assertEqual(date.fromisoformat(snapshot.previous_end) + timedelta(days=1),
                         date.fromisoformat(snapshot.current_start))
        self.assertEqual((date.fromisoformat(snapshot.current_end) -
                          date.fromisoformat(snapshot.current_start)).days, 6)

    def test_actual_page_projection_uses_shared_authority_and_preserves_values(self):
        with patch.object(authority, "build_issue_period_metric",
                          wraps=authority.build_issue_period_metric) as calculate:
            projection = authority.project_issue_pages(self.news, self.candidate_history)
        self.assertEqual(calculate.call_count, 2)
        for issue in projection["issues"]:
            comparison = issue["current_coverage"]["comparison_7d"]
            for prefix, period in (("previous", self.page_period(
                    comparison["previous_start"], comparison["previous_end"])),
                    ("latest", self.page_period(comparison["latest_start"], comparison["latest_end"]))):
                row = next(r for r in period.rows if r.issue_id == issue["issue_id"])
                self.assertEqual(comparison[prefix + "_source_day_count"], row.numerator)
                self.assertEqual(comparison[prefix + "_incidence"], round(row.raw_share, 6))

    def test_social_consumes_authority_rows_without_independent_share_division(self):
        with patch.object(authority, "build_issue_period_metric",
                          wraps=authority.build_issue_period_metric) as calculate, \
             patch.object(social, "_share", side_effect=AssertionError("must consume authority")):
            social.build_issue_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_WEEK)
        self.assertEqual(calculate.call_count, 2)

    def test_more_articles_from_an_existing_source_day_do_not_change_incidence(self):
        history = copy.deepcopy(self.history)
        issue = next(i for i in history["issues"] if i["id"] == "work_purchasing_power_pensions")
        point = next(p for p in reversed(issue["daily"]) if p["item_count"] > 0)
        point["item_count"] += 1
        issue["total_item_count"] += 1
        point["corpus_share_percent"] = round(point["item_count"] / point["corpus_item_count"] * 100, 4)
        for mode in (social.WINDOW_COMPLETE_DAY, social.WINDOW_COMPLETE_WEEK):
            self.assertEqual(social.build_issue_metric_snapshot(history, window_mode=mode),
                             social.build_issue_metric_snapshot(self.history, window_mode=mode))

    def test_returned_authority_rows_drive_both_consumers(self):
        def changed(*args, **kwargs):
            metric = original(*args, **kwargs)
            return replace(metric, rows=tuple(replace(row, numerator=1, raw_share=.25)
                                               for row in metric.rows))
        original = authority.build_issue_period_metric
        with patch.object(authority, "build_issue_period_metric", side_effect=changed):
            snapshot = social.build_issue_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_DAY)
            self.assertTrue(all(row.current_evidence == 1 and row.current_raw == 25.0
                                for row in snapshot.rows))
            with self.assertRaisesRegex(authority.IssuePageContractError, "source_day_count is inconsistent"):
                authority.project_issue_pages(self.news, self.candidate_history)

    def test_all_published_issue_urls_and_displayed_weekly_endpoints_match_pages(self):
        snapshot = self.assert_period_parity(social.WINDOW_COMPLETE_WEEK)
        projection = authority.project_issue_pages(self.news, self.candidate_history)
        published = {issue["issue_id"]: issue for issue in projection["issues"] if issue["public"]}
        self.assertEqual(set(published), {row.entity_id for row in snapshot.rows})
        registry = load("route_registry.json")["routes"]
        for row in snapshot.rows:
            issue = published[row.entity_id]
            comparison = issue["current_coverage"]["comparison_7d"]
            # The page card rolls seven complete days; calendar-week parity
            # applies when those dates coincide (Monday-generated artifacts).
            calendar_card = (snapshot.current_start, snapshot.current_end) == (
                comparison["latest_start"], comparison["latest_end"])
            current = next(r for r in self.page_period(snapshot.current_start, snapshot.current_end).rows
                           if r.issue_id == row.entity_id)
            previous = next(r for r in self.page_period(snapshot.previous_start, snapshot.previous_end).rows
                            if r.issue_id == row.entity_id)
            if calendar_card:
                self.assertEqual(comparison["latest_incidence"], round(current.raw_share, 6))
                self.assertEqual(comparison["previous_incidence"], round(previous.raw_share, 6))
            for locale, url in (("fr", row.canonical_url_fr), ("en", row.canonical_url_en)):
                self.assertEqual(url, issue["canonical"][locale])
                self.assertEqual(sum(r["canonical_url"] == url for r in registry), 1)
                self.assertEqual(page._incidence_label(round(current.raw_share, 6), locale),
                                 page._incidence_label(row.current_display / 100, locale))
                self.assertEqual(page._incidence_label(round(previous.raw_share, 6), locale),
                                 page._incidence_label(row.previous_display / 100, locale))

    def test_observed_work_rounding_discrepancy_is_not_copied_to_social(self):
        # Preserve the audited example independently of subsequent news refreshes.
        previous_raw, current_raw = 16 / 282, 30 / 225
        self.assertEqual(social.display_triplet(previous_raw * 100, current_raw * 100), (5.7, 13.3, 7.6))
        stored_page_delta = round((current_raw - previous_raw) * 100, 3)
        self.assertEqual(page._signed_pp(stored_page_delta, "fr"), "+7,7pp")

    def test_multiple_issues_can_each_reach_100_percent_without_normalization(self):
        # One accepted publisher-day is associated with every Issue.
        topics = [{"id": issue_id, "daily_activity": [
            {"date": self.current_day, "source_day_count": 1}]} for issue_id in authority.CANONICAL_ISSUE_IDS]
        metric = authority.build_issue_period_metric(topics, start_date=self.current_day,
            end_date=self.current_day, daily_denominators=[{"date": self.current_day, "source_day_count": 1}])
        self.assertEqual(sum(row.raw_share for row in metric.rows), 8.0)
        self.assertTrue(all(row.raw_share == 1.0 for row in metric.rows))

    def test_real_shares_are_not_renormalized_to_100_percent(self):
        snapshot = social.build_issue_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_WEEK)
        self.assertNotEqual(sum(row.current_raw for row in snapshot.rows), 100.0)
        self.assertIn("multilabel", snapshot.interpretation_boundary_fr)

    def test_history_builder_retains_page_source_days_as_publisher_counts(self):
        snapshot = social.build_issue_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_WEEK)
        start, end = snapshot.previous_start, snapshot.current_end
        observations = history_builder._snapshot_days(self.news,
            start=date.fromisoformat(start), end=date.fromisoformat(end))
        accepted = {p["date"]: p["source_day_count"] for p in self.evolution["accepted_daily_activity"]}
        for day, observation in observations.items():
            self.assertEqual(observation["corpus_publisher_count"], accepted[day])
            for topic in self.evolution["topics"]:
                point = next(p for p in topic["daily_activity"] if p["date"] == day)
                self.assertEqual(observation["issues"][topic["id"]]["publisher_count"],
                                 point["source_day_count"])
        self.assertEqual(len(observations), 14)

    def test_real_history_validation_and_source_day_adapter(self):
        index = authority.validate_issue_coverage_history(self.history)
        self.assertEqual(set(index), set(authority.CANONICAL_ISSUE_IDS))
        metric = authority.build_issue_history_period_metric(self.history,
            start_date=self.previous_day, end_date=self.current_day)
        self.assertEqual(metric, self.page_period(self.previous_day, self.current_day))

    def test_zero_observed_issue_is_valid_but_missing_observation_fails_closed(self):
        evolution = copy.deepcopy(self.evolution)
        for point in evolution["topics"][0]["daily_activity"]:
            point["source_day_count"] = 0
        metric = self.page_period(self.previous_day, self.current_day, evolution)
        self.assertEqual(next(row for row in metric.rows
                              if row.issue_id == evolution["topics"][0]["id"]).raw_share, 0)
        evolution["topics"][0]["daily_activity"] = [p for p in
            evolution["topics"][0]["daily_activity"] if p["date"] != self.current_day]
        with self.assertRaisesRegex(authority.IssuePageContractError, "missing required"):
            self.page_period(self.previous_day, self.current_day, evolution)

    def test_empty_denominator_fails_publication_but_page_presentation_is_preserved(self):
        evolution = copy.deepcopy(self.evolution)
        for point in evolution["accepted_daily_activity"]:
            point["source_day_count"] = 0
        for topic in evolution["topics"]:
            for point in topic["daily_activity"]:
                point["source_day_count"] = 0
        with self.assertRaisesRegex(authority.IssuePageContractError, "denominator must be positive"):
            self.page_period(self.previous_day, self.current_day, evolution)
        metric = self.page_period(self.previous_day, self.current_day, evolution, allow_empty_denominator=True)
        self.assertEqual(metric.denominator, 0)
        self.assertTrue(all(row.raw_share == 0 for row in metric.rows))

    def test_missing_week_or_topic_dates_and_incomplete_period_fail_closed(self):
        for change in (lambda p: p["corpus"]["daily"].pop(-5),
                       lambda p: p["issues"][0]["daily"].pop(-5),
                       lambda p: p["period"].__setitem__("current_utc_day_excluded", False),
                       lambda p: p.__setitem__("data_as_of", (date.fromisoformat(self.current_day) + timedelta(days=2)).isoformat() + "T00:00:00Z")):
            history = copy.deepcopy(self.history)
            change(history)
            with self.assertRaises(social.MetricContractError):
                social.build_issue_metric_snapshot(history, window_mode=social.WINDOW_COMPLETE_WEEK)

    def test_invalid_counts_duplicate_taxonomy_and_impossible_incidence_fail_closed(self):
        for change in (lambda e: e["topics"].append(e["topics"][0]),
                       lambda e: e["topics"][0]["daily_activity"][-2].__setitem__("source_day_count", -1),
                       lambda e: e["topics"][0]["daily_activity"][-2].__setitem__("source_day_count", True),
                       lambda e: e["topics"][0]["daily_activity"][-2].__setitem__("source_day_count", 99999)):
            evolution = copy.deepcopy(self.evolution)
            change(evolution)
            with self.assertRaises(authority.IssuePageContractError):
                self.page_period(self.previous_day, self.current_day, evolution)

    def test_deterministic_ranking_and_ties(self):
        snapshot = social.build_issue_metric_snapshot(self.history, window_mode=social.WINDOW_COMPLETE_WEEK)
        tied = replace(snapshot, rows=tuple(replace(row, previous_evidence=1, current_evidence=1,
            display_delta=1.0, current_display=2.0) for row in reversed(snapshot.rows)))
        for rank in (social.rank_movers, social.rank_current_share):
            self.assertEqual([r.entity_id for r in rank(tied, limit=8)], sorted(r.entity_id for r in tied.rows))
        self.assertEqual(list(social.rank_movers(snapshot, limit=8)), sorted(snapshot.rows,
            key=lambda row: (-abs(row.display_delta), -(row.current_evidence + row.previous_evidence), row.entity_id)))
        self.assertEqual(list(social.rank_current_share(snapshot, limit=8)), sorted(snapshot.rows,
            key=lambda row: (-row.current_display, -row.current_evidence, row.entity_id)))

    def test_fr_and_en_daily_weekly_movers_and_dominance_fit_and_keep_boundary(self):
        for locale in ("fr", "en"):
            products = newsroom_products.build_newsroom_products(issue_payload=self.history,
                agenda_payload=self.agenda, locale=locale)
            issues = [p for p in products if p.family == "issues"]
            self.assertEqual(len(issues), 4)
            for product in issues:
                self.assertLessEqual(
                    product.weighted_length,
                    newsroom_products.MAX_X_WEIGHTED_LENGTH,
                )
                self.assertEqual(len(product.rows), 1 if locale == "fr" else 5)
                self.assertTrue(product.text.endswith(product.destination_url))
                boundary = "Un même article peut relever de plusieurs enjeux." if locale == "fr" else "Coverage · multilabel · ≠ opinion."
                self.assertIn(boundary, product.text)
                self.assertEqual(product.metric_id, "issues_source_day_incidence_" + product.window_mode)


if __name__ == "__main__":
    unittest.main()
