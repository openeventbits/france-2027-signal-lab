import copy
import unittest
from history_test_support import HistoryCases


class YoutubeHistoryTests(HistoryCases, unittest.TestCase):
    provider = "youtube"
    identity = "channel_id"
    metric = "subscriber_count"
    mapping_file = "youtube_candidate_channels.json"
    changed_identity = "UCzzzzzzzzzzzzzzzzzzzzzz"

    def test_hidden_and_null_subscribers_never_become_zero(self):
        row = next(r for r in self.snapshot["candidates"] if r["candidate_id"] == self.cid)
        row.update(hidden_subscriber_count=True, subscriber_count=None)
        result = self.build()
        self.assertEqual(next(r for r in result["candidates"] if r["candidate_id"] == self.cid)["points"], [])
        row["hidden_subscriber_count"] = False
        with self.assertRaises(ValueError): self.build()

    def test_provider_rounded_values_preserved_without_extra_precision(self):
        row = next(r for r in self.snapshot["candidates"] if r["candidate_id"] == self.cid)
        row["subscriber_count"] = 1290000
        self.assertEqual(next(r for r in self.build()["candidates"] if r["candidate_id"] == self.cid)["points"][0]["subscriber_count"], 1290000)
