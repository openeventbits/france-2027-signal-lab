from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from build_candidate_agenda_history import (
    CandidateAgendaHistoryBuildError,
    build_candidate_agenda_history,
)
from candidate_agenda_history_contract import serialize_candidate_agenda_history


ROOT = Path(__file__).resolve().parent


def candidates(*rows):
    return [
        {
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "previous_names": list(previous_names),
        }
        for candidate_id, candidate_name, previous_names in rows
    ]


BASE_CANDIDATES = candidates(
    ("alice", "Alice", ("Alice Ancienne",)),
    ("bob", "Bob", ()),
)


def item(day, headline, names, suffix="item", *, explicit=True):
    return {
        "id": suffix,
        "published_at": f"{day}T12:00:00Z",
        "headline": headline,
        "explicit_election": explicit,
        "candidates": list(names),
        "candidate_matches": [
            {
                "candidate": name,
                "matched_aliases": [name],
                "locations": ["headline"],
            }
            for name in names
        ],
    }


def build(items=(), *, generated="2026-08-29T01:00:00Z", roster=None, previous=None):
    return build_candidate_agenda_history(
        relevant_news=list(items),
        generated_at=generated,
        window_days=30,
        candidates=roster or BASE_CANDIDATES,
        previous=previous,
    )


def candidate(payload, candidate_id):
    return next(row for row in payload["candidates"] if row["candidate_id"] == candidate_id)


def day(payload, candidate_id, date_value):
    return next(
        row
        for row in candidate(payload, candidate_id)["daily_series"]
        if row["date"] == date_value
    )


class CandidateAgendaHistoryBuildTests(unittest.TestCase):
    def test_one_and_multi_label_policy_counts_and_two_candidate_linkage(self):
        payload = build(
            [
                item(
                    "2026-08-28",
                    "Budget retraites immigration",
                    ["Alice", "Bob"],
                    "multi",
                )
            ]
        )
        expected = {
            "economy_public_finances",
            "work_purchasing_power_pensions",
            "immigration_identity_secularism",
        }
        for candidate_id in ("alice", "bob"):
            counts = day(payload, candidate_id, "2026-08-28")["policy_counts"]
            self.assertEqual({key for key, value in counts.items() if value}, expected)
            self.assertTrue(all(counts[key] == 1 for key in expected))

    def test_duplicate_published_identity_counts_candidate_once(self):
        duplicate = item(
            "2026-08-28", "Budget", ["Alice", "Alice Ancienne"], "duplicate"
        )
        payload = build([duplicate])
        self.assertEqual(
            day(payload, "alice", "2026-08-28")["policy_counts"][
                "economy_public_finances"
            ],
            1,
        )

    def test_campaign_classifier_uses_existing_single_topic_semantics(self):
        payload = build(
            [item("2026-08-28", "Sondage présidentielle 2027", ["Alice"], "poll")]
        )
        counts = day(payload, "alice", "2026-08-28")["campaign_counts"]
        self.assertEqual(counts["polls_race"], 1)
        self.assertEqual(sum(counts.values()), 1)

    def test_policy_and_campaign_counts_coexist_in_daily_storage(self):
        payload = build(
            [
                item(
                    "2026-08-28",
                    "Sondage présidentielle 2027 sur le budget",
                    ["Alice"],
                    "both",
                )
            ]
        )
        row = day(payload, "alice", "2026-08-28")
        self.assertEqual(row["policy_counts"]["economy_public_finances"], 1)
        self.assertEqual(row["campaign_counts"]["polls_race"], 1)

    def test_exactly_two_policy_topics_falls_back_to_campaign(self):
        payload = build(
            [item("2026-08-28", "Retraites immigration et sondage", ["Alice"])]
        )
        profile = candidate(payload, "alice")["cumulative_profile"]
        self.assertEqual(profile["profile_mode"], "campaign")
        self.assertEqual([row["id"] for row in profile["topics"]][-1], "polls_race")
        self.assertEqual(profile["association_count"], 1)
        self.assertEqual(sum(row["share"] for row in profile["topics"]), 1.0)

    def test_exactly_three_policy_topics_selects_all_policy_topics(self):
        payload = build(
            [item("2026-08-28", "Budget retraites immigration", ["Alice"])]
        )
        profile = candidate(payload, "alice")["cumulative_profile"]
        self.assertEqual(profile["profile_mode"], "policy")
        self.assertEqual(len(profile["topics"]), 8)
        self.assertEqual(profile["association_count"], 3)
        self.assertEqual(sum(row["count"] for row in profile["topics"]), 3)
        self.assertAlmostEqual(sum(row["share"] for row in profile["topics"]), 0.999999)

    def test_zero_association_behavior_matches_current_profile(self):
        profile = candidate(build(), "alice")["cumulative_profile"]
        self.assertEqual(profile["profile_mode"], "campaign")
        self.assertEqual(profile["association_count"], 0)
        self.assertTrue(all(row["share"] == 0.0 for row in profile["topics"]))

    def test_repeated_same_horizon_is_byte_identical(self):
        first = build([item("2026-08-28", "Sondage", ["Alice"])])
        second = build(
            [item("2026-08-28", "Sondage", ["Alice"])],
            generated="2026-08-29T23:59:59Z",
            previous=first,
        )
        self.assertEqual(
            serialize_candidate_agenda_history(first),
            serialize_candidate_agenda_history(second),
        )

    def test_overlap_is_replaced_and_deleted_evidence_removes_stale_count(self):
        first = build([item("2026-08-28", "Sondage", ["Alice"])])
        corrected = build([], previous=first)
        self.assertEqual(
            day(corrected, "alice", "2026-08-28")["campaign_counts"]["polls_race"],
            0,
        )

    def test_new_completed_day_appends_once(self):
        first = build()
        second = build(
            [item("2026-08-29", "Sondage", ["Alice"])],
            generated="2026-08-30T01:00:00Z",
            previous=first,
        )
        third = build(
            [item("2026-08-29", "Sondage", ["Alice"])],
            generated="2026-08-30T20:00:00Z",
            previous=second,
        )
        self.assertEqual(len(candidate(second, "alice")["daily_series"]), 10)
        self.assertEqual(serialize_candidate_agenda_history(second), serialize_candidate_agenda_history(third))

    def test_settled_days_older_than_recomputable_window_survive(self):
        first = build(
            [item("2026-08-20", "Sondage", ["Alice"])],
            generated="2026-09-17T01:00:00Z",
        )
        second = build([], generated="2026-09-20T01:00:00Z", previous=first)
        self.assertEqual(
            day(second, "alice", "2026-08-20")["campaign_counts"]["polls_race"],
            1,
        )

    def test_gap_future_and_malformed_previous_fail_closed(self):
        old = build(generated="2026-08-29T01:00:00Z")
        with self.assertRaisesRegex(CandidateAgendaHistoryBuildError, "missing settled"):
            build(generated="2026-10-01T01:00:00Z", previous=old)
        with self.assertRaisesRegex(CandidateAgendaHistoryBuildError, "later than"):
            build(generated="2026-08-28T01:00:00Z", previous=old)
        malformed = copy.deepcopy(old)
        malformed["candidates"][0]["daily_series"] = []
        with self.assertRaisesRegex(CandidateAgendaHistoryBuildError, "previous.*invalid"):
            build(previous=malformed)

    def test_initial_build_fails_when_frozen_start_is_unreconstructable(self):
        with self.assertRaisesRegex(CandidateAgendaHistoryBuildError, "initial history"):
            build(generated="2026-09-19T01:00:00Z")

    def test_rename_preserves_stable_id_history(self):
        first = build(
            [item("2026-08-20", "Sondage", ["Alice"])],
            generated="2026-09-17T01:00:00Z",
        )
        renamed = candidates(
            ("alice", "Alice Nouvelle", ("Alice", "Alice Ancienne")),
            ("bob", "Bob", ()),
        )
        second = build(
            [], generated="2026-09-20T01:00:00Z", roster=renamed, previous=first
        )
        self.assertEqual(candidate(second, "alice")["candidate_name"], "Alice Nouvelle")
        self.assertEqual(
            day(second, "alice", "2026-08-20")["campaign_counts"]["polls_race"],
            1,
        )

    def test_new_candidate_starts_at_earliest_reconstructable_complete_day(self):
        alice_only = candidates(("alice", "Alice", ()))
        first = build(
            [], generated="2026-09-17T01:00:00Z", roster=alice_only
        )
        second = build(
            [], generated="2026-09-20T01:00:00Z", roster=BASE_CANDIDATES, previous=first
        )
        self.assertEqual(candidate(second, "bob")["tracking_start"], "2026-08-22")
        self.assertEqual(candidate(second, "alice")["tracking_start"], "2026-08-20")

    def test_uncontrolled_candidate_identity_fails_closed(self):
        with self.assertRaisesRegex(CandidateAgendaHistoryBuildError, "uncontrolled"):
            build([item("2026-08-28", "Sondage", ["Unknown"])])

    def test_failed_cli_build_preserves_last_good_output_bytes(self):
        identifier = uuid.uuid4().hex
        previous = ROOT / f".candidate-agenda-history-bad-{identifier}.json"
        output = ROOT / f".candidate-agenda-history-output-{identifier}.json"
        self.addCleanup(previous.unlink, missing_ok=True)
        self.addCleanup(output.unlink, missing_ok=True)
        previous.write_text("{}", encoding="utf-8")
        expected = b"last-good-history\n"
        output.write_bytes(expected)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_candidate_agenda_history.py"),
                "--news",
                str(ROOT / "news_wire.json"),
                "--candidacy-status",
                str(ROOT / "candidate_candidacy_status.json"),
                "--previous",
                str(previous),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
