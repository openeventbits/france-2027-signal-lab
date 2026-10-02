import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "social" / "social_publish.py"
SPEC = importlib.util.spec_from_file_location("fr27_social_publish", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SocialPublishTests(unittest.TestCase):
    def test_recent_change_is_headline_plus_source_url(self):
        item = {
            "headline": "Présidentielle 2027. Un nouvel élément de campagne est publié",
            "primary_source": {"url": "https://example.test/article"},
        }
        rendered = MODULE.render_recent_change(item)
        self.assertEqual(
            rendered,
            "Présidentielle 2027. Un nouvel élément de campagne est publié\n\n"
            "https://example.test/article",
        )
        self.assertLessEqual(MODULE._weighted_x_length(rendered), 280)

    def test_event_includes_event_date_and_source(self):
        item = {
            "title": "Réunion publique à Lyon",
            "scheduled_start": "2026-10-02T19:00:00+02:00",
            "evidence": [{"source_url": "https://example.test/event"}],
        }
        rendered = MODULE.render_campaign_event(item)
        self.assertEqual(
            rendered,
            "Réunion publique à Lyon\n\n2 oct. 2026\n\nhttps://example.test/event",
        )

    def test_bootstrap_baselines_existing_ids(self):
        now = datetime(2026, 9, 29, 10, tzinfo=timezone.utc)
        state = MODULE.build_bootstrap_state(
            {"items": [{"id": "existing-change"}]},
            {"campaign_events": [{"event_id": "existing-event"}]},
            now=now,
        )
        self.assertEqual(state["seen"]["recent_changes"], ["existing-change"])
        self.assertEqual(state["seen"]["campaign_events"], ["existing-event"])
        self.assertEqual(state["initialized_at"], "2026-09-29T10:00:00Z")

    def test_state_prevents_historical_backfill_and_reverification_reposts(self):
        now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        state = {
            "schema_version": 1,
            "initialized_at": "2026-09-29T10:00:00Z",
            "updated_at": "2026-09-29T10:00:00Z",
            "seen": {
                "recent_changes": ["old"],
                "campaign_events": ["existing-event"],
            },
        }
        recent = {
            "items": [
                {
                    "id": "old",
                    "category": "campaign",
                    "headline": "Old",
                    "detected_at": "2026-09-29T11:00:00Z",
                    "primary_source": {"url": "https://example.test/old"},
                },
                {
                    "id": "new",
                    "category": "campaign",
                    "headline": "New",
                    "detected_at": "2026-09-29T11:01:00Z",
                    "primary_source": {"url": "https://example.test/new"},
                },
            ]
        }
        events = {
            "campaign_events": [
                {
                    "event_id": "existing-event",
                    "title": "Existing future event reverified",
                    "status": "scheduled",
                    "scheduled_start": "2026-10-02",
                    "last_verified_at": "2026-09-29T11:30:00Z",
                    "evidence": [{"source_url": "https://example.test/existing"}],
                },
                {
                    "event_id": "new-event",
                    "title": "New future event",
                    "status": "scheduled",
                    "scheduled_start": "2026-10-03",
                    "last_verified_at": "2026-09-29T11:31:00Z",
                    "evidence": [{"source_url": "https://example.test/new-event"}],
                },
            ]
        }
        candidates = MODULE.collect_update_candidates(
            recent,
            events,
            state,
            now=now,
            lookback_hours=24,
        )
        self.assertEqual([c.key for c in candidates], ["new", "new-event"])

    def test_event_requires_current_or_future_date(self):
        now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        state = {
            "schema_version": 1,
            "initialized_at": "2026-09-29T00:00:00Z",
            "updated_at": "2026-09-29T00:00:00Z",
            "seen": {"recent_changes": [], "campaign_events": []},
        }
        events = {
            "campaign_events": [
                {
                    "event_id": "past",
                    "title": "Past event",
                    "status": "scheduled",
                    "scheduled_start": "2026-09-28",
                    "last_verified_at": "2026-09-29T10:00:00Z",
                    "evidence": [{"source_url": "https://example.test/past"}],
                },
                {
                    "event_id": "future",
                    "title": "Future event",
                    "status": "scheduled",
                    "scheduled_start": "2026-10-02",
                    "last_verified_at": "2026-09-29T10:00:00Z",
                    "evidence": [{"source_url": "https://example.test/future"}],
                },
            ]
        }
        candidates = MODULE.collect_update_candidates(
            {"items": []},
            events,
            state,
            now=now,
            lookback_hours=24,
        )
        self.assertEqual([c.key for c in candidates], ["future"])

    def test_mark_seen_updates_right_registry(self):
        state = {
            "schema_version": 1,
            "initialized_at": "2026-09-29T00:00:00Z",
            "updated_at": "2026-09-29T00:00:00Z",
            "seen": {"recent_changes": [], "campaign_events": []},
        }
        candidate = MODULE.SocialCandidate(
            key="change-1",
            kind="recent_change",
            observed_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
            text="Example\n\nhttps://example.test",
            source_url="https://example.test",
        )
        MODULE._mark_seen(state, candidate)
        self.assertEqual(state["seen"]["recent_changes"], ["change-1"])
        self.assertEqual(state["seen"]["campaign_events"], [])

    def test_visual_captions_fit_x(self):
        now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        for kind in ("media", "agenda", "issues"):
            with self.subTest(kind=kind):
                caption = MODULE.visual_caption(kind, now)
                self.assertLessEqual(MODULE._weighted_x_length(caption), 280)
                self.assertIn("france2027.app", caption)


    def test_recent_changes_exclude_polling_and_runoff(self):
        cutoff = datetime(2026, 9, 29, 0, tzinfo=timezone.utc)
        payload = {
            "items": [
                {
                    "id": "campaign",
                    "category": "campaign",
                    "headline": "Campaign item",
                    "detected_at": "2026-09-29T10:00:00Z",
                    "primary_source": {"url": "https://example.test/campaign"},
                },
                {
                    "id": "poll",
                    "category": "polling",
                    "headline": "Poll item",
                    "detected_at": "2026-09-29T10:00:00Z",
                    "primary_source": {"url": "https://example.test/poll"},
                },
                {
                    "id": "runoff",
                    "category": "runoff",
                    "headline": "Runoff item",
                    "detected_at": "2026-09-29T10:00:00Z",
                    "primary_source": {"url": "https://example.test/runoff"},
                },
                {
                    "id": "legal",
                    "category": "legal",
                    "headline": "Legal item",
                    "detected_at": "2026-09-29T10:00:00Z",
                    "primary_source": {"url": "https://example.test/legal"},
                },
            ]
        }
        rows = MODULE.collect_recent_changes(payload, cutoff=cutoff, seen_ids=set())
        self.assertEqual([row.key for row in rows], ["campaign", "legal"])

    def test_visual_captions_surface_top_observed_changes(self):
        now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        media = MODULE.visual_caption(
            "media",
            now,
            {
                "comparison_label": "Δ pts",
                "rows": [
                    {"name": "A", "delta": "▲ +14,3 pts"},
                    {"name": "B", "delta": "▲ +7,2 pts"},
                    {"name": "C", "delta": "▼ -1,3 pts"},
                ],
            },
        )
        self.assertIn("A  +14,3 pts", media)
        self.assertIn("B  +7,2 pts", media)

        agenda = MODULE.visual_caption(
            "agenda",
            now,
            {
                "rows": [
                    {"label": "Sondages", "count": "14 → 39", "delta": "▲ +14,9pp"},
                    {"label": "Primaires", "count": "140 → 103", "delta": "▼ -12,5pp"},
                    {"label": "Candidatures", "count": "38 → 35", "delta": "• +0,6pp"},
                ]
            },
        )
        self.assertIn("Sondages 14 → 39 · +14,9 pts", agenda)
        self.assertIn("Primaires 140 → 103 · −12,5 pts", agenda)

        issues = MODULE.visual_caption(
            "issues",
            now,
            {
                "rows": [
                    {"label": "Immigration & identité", "delta": "▼ -5,6pp"},
                    {"label": "Europe & défense", "delta": "▲ +3,9pp"},
                    {"label": "Travail & pouvoir d’achat", "delta": "• -3,2pp"},
                ]
            },
        )
        self.assertIn("Immigration & identité  −5,6 pts", issues)
        self.assertIn("Europe & défense  +3,9 pts", issues)


    def test_realistic_visual_captions_fit_x(self):
        now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        metrics = {
            "media": {
                "comparison_label": "Δ pts",
                "rows": [
                    {"name": "Jean-Luc Mélenchon", "delta": "▲ +14 pts"},
                    {"name": "Marine Tondelier", "delta": "▲ +8.6 pts"},
                    {"name": "Marine Le Pen", "delta": "▲ +7.6 pts"},
                ],
            },
            "agenda": {
                "rows": [
                    {"label": "Sondages et rapports de force", "count": "14 → 39", "delta": "▲ +14,9pp"},
                    {"label": "Primaires et stratégies partisanes", "count": "140 → 103", "delta": "▼ -12,5pp"},
                    {"label": "Règles, calendrier et organisation de la campagne", "count": "3 → 0", "delta": "• -1,5pp"},
                ],
            },
            "issues": {
                "rows": [
                    {"label": "Immigration, identité et laïcité", "delta": "▼ -5,6pp"},
                    {"label": "Europe, défense et affaires étrangères", "delta": "• +3,9pp"},
                    {"label": "Travail, pouvoir d’achat et retraites", "delta": "• -3,2pp"},
                ],
            },
        }
        for kind, payload in metrics.items():
            with self.subTest(kind=kind):
                caption = MODULE.visual_caption(kind, now, payload)
                self.assertLessEqual(MODULE._weighted_x_length(caption), 280)
                self.assertIn("france2027.app", caption)

    def test_google_news_url_is_resolved_to_publisher_url(self):
        google_url = "https://news.google.com/rss/articles/opaque?oc=5"
        item = {
            "id": "g1",
            "category": "campaign",
            "headline": "Présidentielle 2027 : développement de campagne",
            "trusted_change_at": "2026-09-29T08:00:00Z",
            "detected_at": "2026-09-29T08:05:00Z",
            "candidate_ids": ["candidate-a"],
            "primary_source": {"url": google_url},
        }
        rows = MODULE.collect_recent_changes(
            {"items": [item]},
            cutoff=datetime(2026, 9, 29, 0, tzinfo=timezone.utc),
            seen_ids=set(),
            url_resolver=lambda urls: {google_url: "https://publisher.test/article"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source_url, "https://publisher.test/article")
        self.assertTrue(rows[0].text.endswith("https://publisher.test/article"))
        self.assertNotIn("news.google.com", rows[0].text)

    def test_unresolved_google_news_url_is_not_publishable(self):
        google_url = "https://news.google.com/rss/articles/opaque?oc=5"
        item = {
            "id": "g1",
            "category": "campaign",
            "headline": "Présidentielle 2027 : développement de campagne",
            "trusted_change_at": "2026-09-29T08:00:00Z",
            "detected_at": "2026-09-29T08:05:00Z",
            "candidate_ids": ["candidate-a"],
            "primary_source": {"url": google_url},
        }
        rows = MODULE.collect_recent_changes(
            {"items": [item]},
            cutoff=datetime(2026, 9, 29, 0, tzinfo=timezone.utc),
            seen_ids=set(),
            url_resolver=lambda urls: {},
        )
        self.assertEqual(rows, [])

    def test_social_dedup_collapses_same_campaign_development(self):
        items = [
            {
                "id": "arthaud-a",
                "category": "campaign",
                "headline": "Nathalie Arthaud lance sa campagne avec un premier meeting à Paris",
                "trusted_change_at": "2026-09-27T10:37:00Z",
                "detected_at": "2026-09-27T14:02:59Z",
                "candidate_ids": ["nathalie-arthaud"],
                "primary_source": {"url": "https://publisher-a.test/a"},
            },
            {
                "id": "arthaud-b",
                "category": "campaign",
                "headline": "Présidentielle 2027 : Nathalie Arthaud lance sa campagne pour Lutte Ouvrière et cible Jean-Luc Mélenchon",
                "trusted_change_at": "2026-09-27T11:00:00Z",
                "detected_at": "2026-09-27T14:10:00Z",
                "candidate_ids": ["nathalie-arthaud", "jean-luc-melenchon"],
                "primary_source": {"url": "https://publisher-b.test/b"},
            },
        ]
        rows = MODULE.collect_recent_changes(
            {"items": items},
            cutoff=datetime(2026, 9, 27, 0, tzinfo=timezone.utc),
            seen_ids=set(),
            url_resolver=lambda urls: {url: url for url in urls},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].key, "arthaud-a")

    def test_social_dedup_collapses_same_candidacy_with_different_quotes(self):
        items = [
            {
                "id": "becht-a",
                "category": "campaign",
                "headline": "« Je suis candidat à la présidentielle » : le député alsacien Olivier Becht se lance dans la course",
                "trusted_change_at": "2026-09-24T06:56:15Z",
                "detected_at": "2026-09-24T17:04:49Z",
                "candidate_ids": ["olivier-becht"],
                "primary_source": {"url": "https://publisher-a.test/a"},
            },
            {
                "id": "becht-b",
                "category": "campaign",
                "headline": "Présidentielle 2027 : Quand on n’a aucune chance, il faut la saisir… Olivier Becht se lance dans la course à l’Élysée",
                "trusted_change_at": "2026-09-24T13:49:00Z",
                "detected_at": "2026-09-24T14:41:44Z",
                "candidate_ids": ["olivier-becht"],
                "primary_source": {"url": "https://publisher-b.test/b"},
            },
        ]
        rows = MODULE.collect_recent_changes(
            {"items": items},
            cutoff=datetime(2026, 9, 24, 0, tzinfo=timezone.utc),
            seen_ids=set(),
            url_resolver=lambda urls: {url: url for url in urls},
        )
        self.assertEqual(len(rows), 1)
        self.assertIn(rows[0].key, {"becht-a", "becht-b"})

    def test_social_dedup_prefers_direct_source_over_google_news_duplicate(self):
        google = "https://news.google.com/rss/articles/opaque?oc=5"
        direct = "https://franceinfo.test/article"
        items = [
            {
                "id": "jadot-google",
                "category": "campaign",
                "headline": "Présidentielle 2027 : Yannick Jadot suspendu temporairement des Écologistes pour son soutien à Raphaël Glucksmann",
                "trusted_change_at": "2026-09-26T12:00:00Z",
                "detected_at": "2026-09-26T12:10:00Z",
                "candidate_ids": ["yannick-jadot", "raphael-glucksmann"],
                "primary_source": {"url": google},
            },
            {
                "id": "jadot-direct",
                "category": "campaign",
                "headline": "Yannick Jadot suspendu temporairement des Ecologistes après avoir soutenu Raphaël Glucksmann pour la présidentielle",
                "trusted_change_at": "2026-09-26T12:02:00Z",
                "detected_at": "2026-09-26T12:12:00Z",
                "candidate_ids": ["yannick-jadot", "raphael-glucksmann"],
                "primary_source": {"url": direct},
            },
        ]
        rows = MODULE.collect_recent_changes(
            {"items": items},
            cutoff=datetime(2026, 9, 26, 0, tzinfo=timezone.utc),
            seen_ids=set(),
            url_resolver=lambda urls: {google: "https://other.test/article", direct: direct},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].key, "jadot-direct")
        self.assertEqual(rows[0].source_url, direct)

    def test_social_dedup_does_not_merge_separate_endorsements(self):
        items = [
            {
                "id": "support-a",
                "category": "campaign",
                "headline": "Stéphane Le Foll apporte son soutien à Raphaël Glucksmann",
                "trusted_change_at": "2026-09-29T08:00:00Z",
                "detected_at": "2026-09-29T08:05:00Z",
                "candidate_ids": ["raphael-glucksmann"],
                "primary_source": {"url": "https://a.test/1"},
            },
            {
                "id": "support-b",
                "category": "campaign",
                "headline": "Une trentaine d’élus sarthois soutiennent Raphaël Glucksmann",
                "trusted_change_at": "2026-09-29T09:00:00Z",
                "detected_at": "2026-09-29T09:05:00Z",
                "candidate_ids": ["raphael-glucksmann"],
                "primary_source": {"url": "https://b.test/2"},
            },
        ]
        rows = MODULE.collect_recent_changes(
            {"items": items},
            cutoff=datetime(2026, 9, 29, 0, tzinfo=timezone.utc),
            seen_ids=set(),
            url_resolver=lambda urls: {url: url for url in urls},
        )
        self.assertEqual([row.key for row in rows], ["support-a", "support-b"])

    def test_seen_duplicate_development_is_not_resurrected(self):
        items = [
            {
                "id": "old",
                "category": "campaign",
                "headline": "Nathalie Arthaud lance sa campagne avec un premier meeting à Paris",
                "trusted_change_at": "2026-09-27T10:37:00Z",
                "detected_at": "2026-09-27T14:02:59Z",
                "candidate_ids": ["nathalie-arthaud"],
                "primary_source": {"url": "https://a.test/old"},
            },
            {
                "id": "new-duplicate",
                "category": "campaign",
                "headline": "Présidentielle 2027 : Nathalie Arthaud lance sa campagne pour Lutte Ouvrière et cible Jean-Luc Mélenchon",
                "trusted_change_at": "2026-09-27T11:00:00Z",
                "detected_at": "2026-09-27T14:10:00Z",
                "candidate_ids": ["nathalie-arthaud", "jean-luc-melenchon"],
                "primary_source": {"url": "https://b.test/new"},
            },
        ]
        rows = MODULE.collect_recent_changes(
            {"items": items},
            cutoff=datetime(2026, 9, 27, 14, 5, tzinfo=timezone.utc),
            seen_ids={"old"},
            url_resolver=lambda urls: {url: url for url in urls},
        )
        self.assertEqual(rows, [])

    def test_long_headline_is_truncated_before_url(self):
        item = {
            "headline": "A" * 400,
            "primary_source": {"url": "https://example.test/really/long/source/url"},
        }
        rendered = MODULE.render_recent_change(item)
        self.assertLessEqual(MODULE._weighted_x_length(rendered), 280)
        self.assertTrue(rendered.endswith("https://example.test/really/long/source/url"))
        self.assertIn("…", rendered)


if __name__ == "__main__":
    unittest.main()
