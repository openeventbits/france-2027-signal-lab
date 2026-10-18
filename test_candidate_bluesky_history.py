import copy
import unittest
from history_test_support import HistoryCases


class BlueskyHistoryTests(HistoryCases, unittest.TestCase):
    provider = "bluesky"
    identity = "did"
    metric = "followers_count"
    mapping_file = "bluesky_candidate_accounts.json"
    changed_identity = "did:plc:bbbbbbbbbbbbbbbbbbbbbbbb"

    def test_handle_change_keeps_did_history(self):
        row = next(r for r in self.snapshot["candidates"] if r["candidate_id"] == self.cid)
        row["handle"] = "new-name.bsky.social"
        self.advance(days=1)
        updated = self.build(self.history)
        new = next(r for r in updated["candidates"] if r["candidate_id"] == self.cid)
        self.assertEqual(new["did"], self.row["did"])
        self.assertEqual(len(new["points"]), 2)

    def test_opt_out_and_unavailable_never_create_numeric_points(self):
        from candidate_bluesky import ROW_KEYS
        for status in ("unavailable_public_web_opt_out", "unavailable_account_missing"):
            snapshot = copy.deepcopy(self.snapshot)
            row = next(r for r in self.snapshot["candidates"] if r["candidate_id"] == self.cid)
            for key in ROW_KEYS - {"candidate_id", "status", "did"}: row[key] = None
            row["status"] = status
            result = self.build()
            self.assertEqual(next(r for r in result["candidates"] if r["candidate_id"] == self.cid)["points"], [])
            self.snapshot = snapshot
