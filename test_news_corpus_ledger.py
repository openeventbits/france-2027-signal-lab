import copy
import json
import unittest
from pathlib import Path

from update_news_corpus_ledger import (
    CorpusLedgerError,
    corpus_counts,
    update_ledger,
    validate_ledger,
)


def baseline_ledger():
    return {
        "schema_version": 1,
        "observation_start_at": "2026-07-16T03:17:21Z",
        "updated_at": "2026-09-20T09:07:09Z",
        "counts": {
            "accepted_election_news": 2,
            "candidate_watch": 1,
            "accepted_news_publishers": 2,
        },
        "accepted_election_news_ids": [
            "news-a",
            "news-b",
        ],
        "candidate_watch_ids": [
            "watch-a",
        ],
        "accepted_news_publishers": [
            "Publisher A",
            "Publisher B",
        ],
    }


def current_wire():
    return {
        "generated_at": "2026-09-23T02:00:00Z",
        "election_news": [
            {
                "id": "news-b",
                "publisher": "Publisher B",
            },
            {
                "id": "news-c",
                "publisher": "Publisher C",
            },
        ],
        "candidate_watch": [
            {
                "id": "watch-a",
            },
            {
                "id": "watch-b",
            },
        ],
    }


class NewsCorpusLedgerTests(unittest.TestCase):
    def test_valid_baseline(self):
        ledger = baseline_ledger()
        validate_ledger(ledger)

    def test_counts_must_match_arrays(self):
        ledger = baseline_ledger()
        ledger["counts"]["candidate_watch"] = 99

        with self.assertRaises(CorpusLedgerError):
            validate_ledger(ledger)

    def test_update_is_union_not_rolling_replacement(self):
        updated = update_ledger(
            baseline_ledger(),
            current_wire(),
        )

        self.assertEqual(
            updated["counts"],
            {
                "accepted_election_news": 3,
                "candidate_watch": 2,
                "accepted_news_publishers": 3,
            },
        )

        self.assertEqual(
            updated["updated_at"],
            "2026-09-23T02:00:00Z",
        )

        self.assertEqual(
            updated["accepted_election_news_ids"],
            [
                "news-a",
                "news-b",
                "news-c",
            ],
        )

        self.assertEqual(
            updated["candidate_watch_ids"],
            [
                "watch-a",
                "watch-b",
            ],
        )

        self.assertEqual(
            updated["accepted_news_publishers"],
            [
                "Publisher A",
                "Publisher B",
                "Publisher C",
            ],
        )

    def test_expiry_from_rolling_wire_does_not_reduce_counts(self):
        grown = update_ledger(
            baseline_ledger(),
            current_wire(),
        )

        later_wire = {
            "generated_at": "2026-10-25T02:00:00Z",
            "election_news": [
                {
                    "id": "news-c",
                    "publisher": "Publisher C",
                }
            ],
            "candidate_watch": [
                {
                    "id": "watch-b",
                }
            ],
        }

        after_expiry = update_ledger(
            copy.deepcopy(grown),
            later_wire,
        )

        self.assertEqual(
            after_expiry["counts"],
            grown["counts"],
        )

        self.assertEqual(
            set(after_expiry["accepted_election_news_ids"]),
            set(grown["accepted_election_news_ids"]),
        )

        self.assertEqual(
            set(after_expiry["candidate_watch_ids"]),
            set(grown["candidate_watch_ids"]),
        )

    def test_repeated_processing_is_idempotent(self):
        once = update_ledger(
            baseline_ledger(),
            current_wire(),
        )

        twice = update_ledger(
            copy.deepcopy(once),
            current_wire(),
        )

        self.assertEqual(once, twice)

    def test_newer_wire_without_new_evidence_is_no_churn(self):
        ledger = baseline_ledger()

        no_change_wire = {
            "generated_at": "2026-09-23T03:00:00Z",
            "election_news": [
                {
                    "id": "news-b",
                    "publisher": "Publisher B",
                }
            ],
            "candidate_watch": [
                {
                    "id": "watch-a",
                }
            ],
        }

        updated = update_ledger(
            copy.deepcopy(ledger),
            no_change_wire,
        )

        self.assertEqual(
            updated,
            ledger,
        )

    def test_older_wire_does_not_move_updated_at_backwards(self):
        ledger = baseline_ledger()

        old_wire = {
            "generated_at": "2026-08-01T00:00:00Z",
            "election_news": [],
            "candidate_watch": [],
        }

        updated = update_ledger(
            ledger,
            old_wire,
        )

        self.assertEqual(
            updated["updated_at"],
            "2026-09-20T09:07:09Z",
        )

    def test_corpus_counts_is_public_projection_only(self):
        ledger = baseline_ledger()

        projection = corpus_counts(ledger)

        self.assertEqual(
            projection,
            {
                "observation_start_at": "2026-07-16T03:17:21Z",
                "updated_at": "2026-09-20T09:07:09Z",
                "accepted_election_news": 2,
                "candidate_watch": 1,
                "accepted_news_publishers": 2,
            },
        )

        self.assertNotIn(
            "accepted_election_news_ids",
            projection,
        )
        self.assertNotIn(
            "candidate_watch_ids",
            projection,
        )

    def test_real_baseline_covers_current_wire(self):
        root = Path(__file__).resolve().parent
        ledger_path = root / "news_corpus_ledger.json"
        wire_path = root / "news_wire.json"

        ledger = json.loads(
            ledger_path.read_text(encoding="utf-8")
        )
        wire = json.loads(
            wire_path.read_text(encoding="utf-8")
        )

        validate_ledger(ledger)

        accepted = set(
            ledger["accepted_election_news_ids"]
        )
        watched = set(
            ledger["candidate_watch_ids"]
        )
        publishers = set(
            ledger["accepted_news_publishers"]
        )

        self.assertTrue(
            {
                item["id"]
                for item in wire["election_news"]
            }.issubset(accepted)
        )

        self.assertTrue(
            {
                item["id"]
                for item in wire["candidate_watch"]
            }.issubset(watched)
        )

        self.assertTrue(
            {
                item["publisher"].strip()
                for item in wire["election_news"]
                if item.get("publisher")
            }.issubset(publishers)
        )


if __name__ == "__main__":
    unittest.main()
