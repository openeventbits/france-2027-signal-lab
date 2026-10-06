"""Complete event lines, canonical link and weighted X budget regression."""
import contextlib
import io
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "social"))
import social_publish as social


INCIDENT_TITLE = "Conférence de presse de Marine Le Pen sur le contre-budget et la trajectoire budgétaire"


class EventRoundupTests(unittest.TestCase):
    now = datetime.fromisoformat("2026-10-06T08:25:00+02:00")
    header = "AUJOURD’HUI DANS LA CAMPAGNE 2027 👇"
    url = "https://france2027.app/#signal-events"

    def event(self, title, clock="10:00"):
        return dict(title=title, scheduled_start=f"2026-10-06T{clock}:00+02:00" if clock else "2026-10-06",
                    status="confirmed")

    def render(self, events):
        return social.render_today_events({"campaign_events": events}, now=self.now)

    def assert_clean(self, text, events):
        self.assertTrue(text.startswith(self.header + "\n\n"))
        self.assertTrue(text.endswith("\n\n" + self.url))
        self.assertLessEqual(social.standard_fr27_weighted_length(text), 280)
        self.assertNotIn("…", text)
        self.assertNotIn("trajectoire budgétai…", text)
        full_lines = set()
        for event in events:
            _, clock = social._event_paris_date_and_time(event["scheduled_start"])
            full_lines.add((clock + " · " if clock else "") + event["title"])
        lines = text.split("\n\n")[1].splitlines()
        self.assertTrue(set(lines) <= full_lines)
        return lines

    def test_short_complete_titles_unchanged(self):
        events = [self.event("Réunion publique à Lyon")]
        text = self.render(events)
        self.assertEqual(text, self.header + "\n\n10h00 · Réunion publique à Lyon\n\n" + self.url)
        self.assert_clean(text, events)

    def test_incident_full_title_never_sliced(self):
        events = [self.event(INCIDENT_TITLE)]
        text = self.render(events)
        self.assertIn("10h00 · " + INCIDENT_TITLE, text)
        self.assert_clean(text, events)

    def test_overflow_omits_lower_priority_whole_lines(self):
        events = [self.event(INCIDENT_TITLE), self.event("Rencontre publique à Lyon", "11:00"),
                  self.event("Présentation du programme économique pour la prochaine campagne et des propositions pour la France", "12:00")]
        text = self.render(events)
        lines = self.assert_clean(text, events)
        self.assertEqual(lines, ["10h00 · " + INCIDENT_TITLE, "11h00 · Rencontre publique à Lyon"])
        self.assertNotIn(events[2]["title"], text)

    def test_one_full_event_fits(self):
        events = [self.event(INCIDENT_TITLE),
                  self.event(INCIDENT_TITLE + " et les propositions fiscales pour la France", "11:00")]
        self.assertEqual(self.assert_clean(self.render(events), events), ["10h00 · " + INCIDENT_TITLE])

    def test_no_full_event_fits_roundup_skipped(self):
        events = [self.event("Titre complet " * 40)]
        self.assertEqual(self.render(events), "")

    def test_skip_calls_no_buffer(self):
        args = SimpleNamespace(now=self.now.isoformat(), campaign_events="unused.json", max_events=4, dry_run=False)
        with (patch.object(social, "_load_json", return_value={"campaign_events": [self.event("Titre " * 100)]}),
              patch.object(social.BufferClient, "from_env") as factory,
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(social.run_today_events(args), 0)
        factory.assert_not_called()

    def test_oversized_line_omitted_later_complete_event_can_fit(self):
        events = [self.event("Titre " * 100), self.event("Réunion publique à Lyon", "11:00")]
        self.assertEqual(self.assert_clean(self.render(events), events), ["11h00 · Réunion publique à Lyon"])

    def test_all_complete_events_that_fit_are_included(self):
        events = [self.event(f"Réunion {i}", f"{9+i:02d}:00") for i in range(6)]
        self.assertEqual(len(self.assert_clean(self.render(events), events)), 6)

    def test_scan_past_oversized_events_and_honor_optional_inclusion_cap(self):
        events = [self.event("Titre " * 100, f"{9+i:02d}:00") for i in range(4)]
        events += [self.event("Réunion à Lyon", "13:00"), self.event("Réunion à Paris", "14:00")]
        text = social.render_today_events({"campaign_events": events}, now=self.now, limit=1)
        self.assertEqual(self.assert_clean(text, events), ["13h00 · Réunion à Lyon"])

    def test_deterministic_time_then_title_untimed_last(self):
        events = [self.event("Zèbre", "09:00"), self.event("alpha", "09:00"),
                  self.event("Alpha", "09:00"), self.event("Sans horaire", "")]
        text = self.render(events)
        self.assertEqual(text, self.render(list(reversed(events))))
        self.assertEqual(self.assert_clean(text, events),
                         ["09h00 · Alpha", "09h00 · alpha", "09h00 · Zèbre", "Sans horaire"])

    def test_unicode_weighted_budget_keeps_complete_lines(self):
        for title in ("界" * 100, "😀" * 100, "Présentation " * 30):
            with self.subTest(title=title):
                events = [self.event(title), self.event(title, "11:00")]
                text = self.render(events)
                if text:
                    self.assert_clean(text, events)
                else:
                    candidate = self.header + "\n\n10h00 · " + title.strip() + "\n\n" + self.url
                    self.assertGreater(social.standard_fr27_weighted_length(candidate), 280)


if __name__ == "__main__":
    unittest.main()
