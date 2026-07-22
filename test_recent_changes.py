import copy
import json
import unittest
from collections import Counter
from datetime import timedelta
from pathlib import Path

from generate_recent_changes import (
    LedgerError,
    compose_recent_changes,
    parse_datetime,
    poll_entries,
    runoff_entry,
    validate_recent_changes,
)


ROOT = Path(__file__).resolve().parent
FIXED_CLOCK = parse_datetime("2026-07-22T09:00:00Z")


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class RecentChangesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = load("news_wire.json")
        cls.polls = load("polls.json")
        cls.runoff = load("closest_tested_runoff.json")
        cls.second_round = load("second_round_polls.json")
        cls.claims = load("claims_under_scrutiny.json")

    def compose(self, *, previous=None, checked_at=FIXED_CLOCK):
        return compose_recent_changes(
            news=self.news,
            polls=self.polls,
            runoff=self.runoff,
            second_round=self.second_round,
            claims=self.claims,
            previous=previous or {},
            checked_at=checked_at,
        )

    def test_repository_data_generates_a_valid_ledger(self):
        payload = self.compose()
        validate_recent_changes(payload)
        self.assertLessEqual(len(payload["items"]), 12)
        self.assertEqual(payload["source_universe"], [
            "Public Sénat",
            "LCP",
            "Franceinfo Politique",
            "France 24 Français",
            "RFI France",
        ])

    def test_historical_polls_use_fieldwork_end_not_generator_date(self):
        payload = self.compose()
        polling = {
            item["primary_source"]["name"]: item
            for item in payload["items"]
            if item["category"] == "polling"
        }
        self.assertEqual(polling["Elabe"]["trusted_change_at"], "2026-07-10")
        self.assertEqual(polling["Verian"]["trusted_change_at"], "2026-07-10")
        self.assertEqual(polling["OpinionWay"]["trusted_change_at"], "2026-07-09")
        self.assertTrue(all(
            item["trusted_change_date_kind"] == "fieldwork_ended"
            for item in polling.values()
        ))
        self.assertNotIn("2026-07-22", {
            item["trusted_change_at"] for item in polling.values()
        })

    def test_six_hypotheses_create_one_poll_wave_item(self):
        payload = self.compose()
        elabe = [
            item for item in payload["items"]
            if item["category"] == "polling"
            and item["primary_source"]["name"] == "Elabe"
        ]
        self.assertEqual(len(elabe), 1)
        self.assertIn("contains 6 published hypotheses", elabe[0]["headline"])
        self.assertNotIn("poll events", elabe[0]["headline"].lower())

    def test_detection_time_never_controls_ordering(self):
        first = self.compose()
        previous = {item["id"]: copy.deepcopy(item) for item in first["items"]}
        for item in previous.values():
            item["detected_at"] = "2030-01-01T00:00:00Z"
        second = self.compose(previous=previous)
        self.assertEqual(
            [(item["id"], item["trusted_change_at"]) for item in first["items"]],
            [(item["id"], item["trusted_change_at"]) for item in second["items"]],
        )
        self.assertEqual(second["items"][0]["trusted_change_at"], "2026-07-17T08:30:04Z")

    def test_runoff_inherits_underlying_poll_evidence_date(self):
        diagnostics = Counter()
        entries = runoff_entry(
            self.runoff,
            self.second_round,
            {},
            FIXED_CLOCK,
            diagnostics,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["trusted_change_at"], "2026-07-08")
        self.assertEqual(entries[0]["trusted_change_date_kind"], "fieldwork_ended")
        self.assertNotEqual(entries[0]["trusted_change_at"], entries[0]["detected_at"][:10])
        self.assertFalse(any(
            item["category"] == "runoff" for item in self.compose()["items"]
        ))

    def test_undated_poll_wave_is_omitted_instead_of_assigned_today(self):
        event = copy.deepcopy(next(
            event for event in self.polls
            if event["pollster"] == "Verian" and event["fieldwork_end"] == "2026-07-10"
        ))
        event["publication_date"] = None
        event["fieldwork_end"] = None
        for field in ("first_seen_at", "first_seen", "ingested_at"):
            event.pop(field, None)
        diagnostics = Counter()
        entries = poll_entries([event], {}, FIXED_CLOCK, diagnostics)
        self.assertEqual(entries, [])
        self.assertEqual(diagnostics["omitted_polling_missing_trusted_date"], 1)

    def test_frontend_groups_only_by_trusted_change_date(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        derive_start = index.index("function deriveRecentChangeLedger()")
        derive_end = index.index("function renderLedgerEntry", derive_start)
        renderer = index[derive_start:derive_end]
        self.assertIn("item.trusted_change_at", renderer)
        self.assertNotIn("item.detected_at", renderer)
        self.assertNotIn("item.date_value", renderer)

    def test_newest_and_oldest_metadata_match_displayed_records(self):
        payload = self.compose()
        self.assertEqual(
            payload["newest_trusted_change_at"],
            payload["items"][0]["trusted_change_at"],
        )
        self.assertEqual(
            payload["oldest_trusted_change_at"],
            payload["items"][-1]["trusted_change_at"],
        )

    def test_current_run_time_does_not_change_ids_or_order(self):
        first = self.compose(checked_at=FIXED_CLOCK)
        second = self.compose(checked_at=FIXED_CLOCK + timedelta(hours=8))
        self.assertEqual(
            [(item["id"], item["trusted_change_at"]) for item in first["items"]],
            [(item["id"], item["trusted_change_at"]) for item in second["items"]],
        )

    def test_campaign_event_deduplication_preserves_support(self):
        payload = self.compose()
        cazeneuve = [
            item for item in payload["items"]
            if item["category"] == "campaign"
            and "cazeneuve" in item["headline"].lower()
        ]
        self.assertEqual(len(cazeneuve), 1)
        self.assertGreaterEqual(cazeneuve[0]["supporting_source_count"], 1)

    def test_validator_rejects_duplicate_primary_urls(self):
        payload = self.compose()
        broken = copy.deepcopy(payload)
        broken["items"][1]["primary_source"]["url"] = broken["items"][0]["primary_source"]["url"]
        with self.assertRaises(LedgerError):
            validate_recent_changes(broken)


if __name__ == "__main__":
    unittest.main()
