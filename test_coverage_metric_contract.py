import json
import unittest
from datetime import date
from pathlib import Path

import coverage_metric_contract as MODULE


ROOT = Path(__file__).resolve().parent


class CoverageMetricContractTests(unittest.TestCase):
    def test_visible_delta_uses_displayed_endpoints(self):
        previous, current, delta = MODULE.display_triplet(
            10.04,
            10.06,
        )

        self.assertEqual(previous, 10.0)
        self.assertEqual(current, 10.1)
        self.assertEqual(delta, 0.1)

    def test_issue_daily_is_complete_day_not_24h(self):
        payload = json.loads(
            (ROOT / "issue_coverage_history.json").read_text(
                encoding="utf-8"
            )
        )

        snapshot = MODULE.build_issue_metric_snapshot(
            payload,
            window_mode=MODULE.WINDOW_COMPLETE_DAY,
        )

        self.assertEqual(
            snapshot.metric_id,
            MODULE.ISSUES_DAILY_METRIC_ID,
        )
        self.assertEqual(
            snapshot.window_mode,
            "complete_day",
        )
        self.assertNotIn(
            "24h",
            snapshot.metric_id.lower(),
        )
        self.assertEqual(len(snapshot.rows), 8)

        for row in snapshot.rows:
            self.assertEqual(
                row.display_delta,
                MODULE.display_round(
                    row.current_display - row.previous_display
                ),
            )

    def test_issue_complete_week_is_monday_sunday(self):
        payload = json.loads(
            (ROOT / "issue_coverage_history.json").read_text(
                encoding="utf-8"
            )
        )

        snapshot = MODULE.build_issue_metric_snapshot(
            payload,
            window_mode=MODULE.WINDOW_COMPLETE_WEEK,
        )

        current_start = date.fromisoformat(snapshot.current_start)
        current_end = date.fromisoformat(snapshot.current_end)
        previous_start = date.fromisoformat(snapshot.previous_start)
        previous_end = date.fromisoformat(snapshot.previous_end)

        self.assertEqual(current_start.weekday(), 0)
        self.assertEqual(current_end.weekday(), 6)
        self.assertEqual(previous_start.weekday(), 0)
        self.assertEqual(previous_end.weekday(), 6)

        self.assertEqual(
            (current_end - current_start).days,
            6,
        )
        self.assertEqual(
            (previous_end - previous_start).days,
            6,
        )

    def test_agenda_daily_uses_source_day_metric(self):
        payload = json.loads(
            (ROOT / "agenda_coverage_history.json").read_text(
                encoding="utf-8"
            )
        )

        snapshot = MODULE.build_agenda_metric_snapshot(
            payload,
            window_mode=MODULE.WINDOW_COMPLETE_DAY,
        )

        self.assertEqual(
            snapshot.metric_id,
            MODULE.AGENDA_DAILY_METRIC_ID,
        )
        self.assertEqual(
            snapshot.aggregation_unit,
            "agenda_topic_source_day",
        )
        self.assertEqual(
            snapshot.denominator_id,
            "all_canonical_agenda_topic_source_days",
        )
        self.assertEqual(len(snapshot.rows), 6)

        self.assertEqual(
            sum(
                row.current_evidence
                for row in snapshot.rows
            ),
            snapshot.rows[0].current_denominator,
        )

        self.assertEqual(
            sum(
                row.previous_evidence
                for row in snapshot.rows
            ),
            snapshot.rows[0].previous_denominator,
        )

    def test_agenda_social_ranking_excludes_polls(self):
        payload = json.loads(
            (ROOT / "agenda_coverage_history.json").read_text(
                encoding="utf-8"
            )
        )

        snapshot = MODULE.build_agenda_metric_snapshot(
            payload,
            window_mode=MODULE.WINDOW_COMPLETE_WEEK,
        )

        movers = MODULE.rank_movers(
            snapshot,
            limit=5,
            excluded_entity_ids={"polls_race"},
            require_full=True,
        )

        self.assertEqual(len(movers), 5)

        self.assertNotIn(
            "polls_race",
            {row.entity_id for row in movers},
        )

    def test_agenda_route_is_canonical(self):
        payload = json.loads(
            (ROOT / "agenda_coverage_history.json").read_text(
                encoding="utf-8"
            )
        )

        snapshot = MODULE.build_agenda_metric_snapshot(
            payload,
            window_mode=MODULE.WINDOW_COMPLETE_WEEK,
        )

        row = next(
            item
            for item in snapshot.rows
            if item.entity_id == "selection_strategy"
        )

        self.assertEqual(
            row.canonical_url_fr,
            (
                "https://france2027.app/agenda/"
                "primaires-strategies-partisanes/"
            ),
        )

        self.assertEqual(
            row.canonical_url_en,
            (
                "https://france2027.app/en/agenda/"
                "primaries-party-strategy/"
            ),
        )

    def test_issue_ranking_is_deterministic(self):
        payload = json.loads(
            (ROOT / "issue_coverage_history.json").read_text(
                encoding="utf-8"
            )
        )

        snapshot = MODULE.build_issue_metric_snapshot(
            payload,
            window_mode=MODULE.WINDOW_COMPLETE_DAY,
        )

        ranked = MODULE.rank_current_share(
            snapshot,
            limit=5,
            require_full=True,
        )

        self.assertEqual(len(ranked), 5)

        self.assertEqual(
            list(ranked),
            sorted(
                ranked,
                key=lambda row: (
                    -row.current_display,
                    -row.current_evidence,
                    row.entity_id,
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
