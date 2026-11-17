"""Regression coverage: same candidate can attend separate same-day meetings."""
import unittest
from add_campaign_event import find_likely_duplicates


class SameDayCandidateMeetingsTests(unittest.TestCase):
    def setUp(self):
        self.existing = {
            "event_key": "manual-" + "a" * 32,
            "date": "2026-11-17",
            "title": "Meeting with Nathalie Arthaud in Montpellier",
            "event_type": "public_meeting",
            "source_url": "https://example.org/montpellier",
            "participants": ["Nathalie Arthaud"],
            "time": "12:30",
            "locality": "Montpellier",
        }
        self.new = {
            "date": "2026-11-17",
            "title": "Meeting with Nathalie Arthaud in Ales",
            "event_type": "public_meeting",
            "source_url": "https://example.org/ales",
            "participants": ["Nathalie Arthaud"],
            "time": "17:30",
            "locality": "Alès",
        }

    def matches(self, **overrides):
        return find_likely_duplicates([self.existing], self.new | overrides)

    def test_different_city_time_and_first_party_url_allowed(self):
        self.assertEqual(self.matches(), [])

    def test_same_date_same_source_still_rejected(self):
        self.assertTrue(self.matches(source_url=self.existing["source_url"]))

    def test_same_date_same_title_still_rejected(self):
        self.assertTrue(self.matches(title=self.existing["title"]))

    def test_same_city_different_time_still_conservatively_rejected(self):
        self.assertTrue(self.matches(locality=self.existing["locality"]))

    def test_same_time_different_city_still_conservatively_rejected(self):
        self.assertTrue(self.matches(time=self.existing["time"]))

    def test_missing_time_is_rejected(self):
        modified = dict(self.new)
        del modified["time"]
        self.assertTrue(find_likely_duplicates([self.existing], modified))

    def test_missing_city_is_rejected(self):
        modified = dict(self.new)
        del modified["locality"]
        self.assertTrue(find_likely_duplicates([self.existing], modified))


if __name__ == "__main__":
    unittest.main()
