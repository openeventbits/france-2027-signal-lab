import importlib.util
import json
import contextlib
import io
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "social" / "social_publish.py"
SPEC = importlib.util.spec_from_file_location("fr27_social_publish", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SocialPublishTests(unittest.TestCase):
    def test_dynamic_target_boundary_and_paris_dst(self):
        for day, offset in (("2026-03-29", "+02:00"), ("2026-10-25", "+01:00")):
            for slot in ("09:05", "13:05", "17:05", "20:05"):
                target = datetime.fromisoformat(f"{day}T{slot}:00{offset}")
                self.assertEqual(target.astimezone(MODULE.PARIS).strftime("%H:%M"), slot)
                for seconds, eligible in ((-1, False), (0, True), (3599, True), (3600, True), (3601, False), (86400, False)):
                    with self.subTest(day=day, slot=slot, seconds=seconds):
                        self.assertEqual(MODULE.dynamic_target_eligible(
                            target, now=target.astimezone(timezone.utc) + timedelta(seconds=seconds)), eligible)

    def test_stale_scheduled_update_skips_before_reading_state_or_buffer(self):
        args = MODULE.build_parser().parse_args([
            "updates", "--state", "unused", "--state-output", "unused",
            "--scheduled-target", "2026-10-07T07:05:00Z",
        ])
        with (patch.object(MODULE, "datetime", wraps=datetime) as clock,
              patch.object(MODULE, "_load_json") as load,
              patch.object(MODULE, "_save_json") as save,
              patch.object(MODULE.BufferClient, "from_env") as factory,
              contextlib.redirect_stdout(io.StringIO()) as output):
            clock.now.return_value = datetime.fromisoformat("2026-10-07T08:05:01+00:00")
            self.assertEqual(MODULE.run_updates(args), 0)
        self.assertIn("REASON=DYNAMIC_SLOT_STALE", output.getvalue())
        load.assert_not_called()
        save.assert_not_called()
        factory.assert_not_called()

    def test_update_expiration_during_resolution_and_buffer_lookup(self):
        target = datetime.fromisoformat("2026-10-07T07:05:00+00:00")
        for phase in ("resolution", "lookup", "manual", "boundary"):
            with self.subTest(phase=phase):
                args = MODULE.build_parser().parse_args([
                    "updates", "--state", "unused", "--state-output", "unused", "--max-posts", "1",
                ])
                args.scheduled_target = None if phase == "manual" else target.isoformat()
                state = MODULE.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=target)
                candidate = MODULE.SocialCandidate(
                    kind="recent_change", key="new", observed_at=target, text="New development", source_url="https://example.test/new")
                client = Mock()
                client.recent_post_texts.return_value = set()
                client.create_post.return_value = "post-1"
                inside = target + timedelta(minutes=59)
                outside = target + timedelta(minutes=60, seconds=1)
                times = {
                    "resolution": [inside, inside, outside],
                    "lookup": [inside, inside, inside, outside],
                    "boundary": [inside, inside, inside, target + timedelta(minutes=60)],
                }
                with (patch.object(MODULE, "datetime", wraps=datetime) as clock,
                      patch.object(MODULE, "_load_json", return_value=state),
                      patch.object(MODULE, "collect_update_candidates", return_value=[candidate]),
                      patch.object(MODULE, "_save_json") as save,
                      patch.object(MODULE.BufferClient, "from_env", return_value=client) as factory,
                      contextlib.redirect_stdout(io.StringIO())):
                    clock.now.side_effect = times.get(phase, [outside])
                    self.assertEqual(MODULE.run_updates(args), 0)
                if phase == "resolution":
                    factory.assert_not_called()
                if phase in {"resolution", "lookup"}:
                    client.create_post.assert_not_called()
                    save.assert_not_called()
                else:
                    client.create_post.assert_called_once()
                    save.assert_called_once()

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
                self.assertNotIn("http", caption)

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
                    {"label": "Sondages", "current": "39,0%", "delta": "▲ +14,9pp"},
                    {"label": "Primaires", "current": "20,0%", "delta": "▼ -12,5pp"},
                    {"label": "Candidatures", "current": "10,0%", "delta": "• +0,6pp"},
                ]
            },
        )
        self.assertIn("Sondages  +14,9 pts", agenda)
        self.assertIn("Primaires  −12,5 pts", agenda)

        issues = MODULE.visual_caption(
            "issues",
            now,
            {
                "rows": [
                    {"label": "Immigration & identité", "current": "0,0%", "delta": "▼ -5,6pp"},
                    {"label": "Europe & défense", "current": "7,9%", "delta": "▲ +3,9pp"},
                    {"label": "Travail & pouvoir d’achat", "current": "5,4%", "delta": "• -3,2pp"},
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
                    {"label": "Sondages et rapports de force", "current": "39,0%", "delta": "▲ +14,9pp"},
                    {"label": "Primaires et stratégies partisanes", "current": "20,0%", "delta": "▼ -12,5pp"},
                    {"label": "Règles, calendrier et organisation de la campagne", "current": "3,0%", "delta": "• -1,5pp"},
                ],
            },
            "issues": {
                "rows": [
                    {"label": "Immigration, identité et laïcité", "current": "0,0%", "delta": "▼ -5,6pp"},
                    {"label": "Europe, défense et affaires étrangères", "current": "7,9%", "delta": "• +3,9pp"},
                    {"label": "Travail, pouvoir d’achat et retraites", "current": "5,4%", "delta": "• -3,2pp"},
                ],
            },
        }
        for kind, payload in metrics.items():
            with self.subTest(kind=kind):
                caption = MODULE.visual_caption(kind, now, payload)
                self.assertLessEqual(MODULE._weighted_x_length(caption), 280)
                self.assertNotIn("http", caption)

    def test_growth_visual_captions_are_plain_and_linkless(self):
        now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
        agenda = MODULE.visual_caption(
            "agenda",
            now,
            {
                "rows": [
                    {"label": "Sondages et rapports de force", "current": "37,4%", "delta": "+25,3pp"},
                    {"label": "Primaires et stratégies partisanes", "current": "44,4%", "delta": "−22,7pp"},
                    {"label": "Candidatures et soutiens", "current": "15,2%", "delta": "−5,1pp"},
                ]
            },
        )
        self.assertIn("AGENDA · CETTE SEMAINE", agenda)
        self.assertIn("Ce qui monte et ce qui recule dans la campagne 👇", agenda)
        self.assertIn("Sondages et rapports de force  +25,3 pts", agenda)
        self.assertNotIn("37,4%", agenda)
        self.assertNotIn("http", agenda)

        issues = MODULE.visual_caption(
            "issues",
            now,
            {
                "rows": [
                    {"label": "Travail, pouvoir d’achat & retraites", "current": "12,8%", "delta": "+7,0pp"},
                    {"label": "Europe, défense & affaires étrangères", "current": "4,1%", "delta": "−4,1pp"},
                    {"label": "Économie & finances publiques", "current": "7,3%", "delta": "+3,6pp"},
                ]
            },
        )
        self.assertIn("ENJEUX · CETTE SEMAINE", issues)
        self.assertIn("Les sujets qui montent et ceux qui reculent", issues)
        self.assertIn("Travail, pouvoir d’achat & retraites  +7,0 pts", issues)
        self.assertNotIn("12,8%", issues)
        self.assertNotIn("http", issues)

    def test_compact_visual_titles_and_subtitles(self):
        now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
        expected = {
            "media": ("RADAR MÉDIAS · AUJOURD’HUI", "Qui monte ou recule le plus dans les médias aujourd’hui ? 👇"),
            "agenda": ("AGENDA · CETTE SEMAINE", "Ce qui monte et ce qui recule dans la campagne 👇"),
            "issues": ("ENJEUX · CETTE SEMAINE", "Les sujets qui montent et ceux qui reculent 👇"),
        }
        for kind, (title, subtitle) in expected.items():
            for metrics in (None, {"comparison_label": "Δ pts", "rows": [
                {"name": "Édouard Philippe", "label": "Travail", "delta": "+7,0pp"},
            ]}):
                with self.subTest(kind=kind, metrics=metrics):
                    caption = MODULE.visual_caption(kind, now, metrics)
                    self.assertTrue(caption.startswith(title + "\n\n" + subtitle))
                    self.assertNotIn("http", caption)

    def test_today_events_without_time_keep_event_but_omit_time_placeholder(self):
        now = datetime(
            2026,
            10,
            5,
            6,
            30,
            tzinfo=timezone.utc,
        )

        caption = MODULE.render_today_events(
            {
                "campaign_events": [
                    {
                        "title":
                            "Rencontre publique",
                        "status":
                            "scheduled",
                        "scheduled_start":
                            "2026-10-05",
                    },
                    {
                        "title":
                            "Entretien",
                        "status":
                            "confirmed",
                        "scheduled_start":
                            "2026-10-05T09:00:00+02:00",
                    },
                ]
            },
            now=now,
        )

        lines = caption.splitlines()

        self.assertIn(
            "09h00 · Entretien",
            lines,
        )

        self.assertIn(
            "Rencontre publique",
            lines,
        )

        self.assertNotIn(
            "Heure non précisée",
            caption,
        )

        self.assertNotIn(
            "Heure non precisee",
            caption,
        )

        self.assertLess(
            lines.index(
                "09h00 · Entretien"
            ),
            lines.index(
                "Rencontre publique"
            ),
        )

        self.assertLessEqual(
            MODULE._weighted_x_length(
                caption
            ),
            280,
        )

    def test_today_events_untimed_long_title_fits_x_without_placeholder(self):
        caption = MODULE.render_today_events(
            {
                "campaign_events": [
                    {
                        "title":
                            "Rencontre " * 15,
                        "status":
                            "confirmed",
                        "scheduled_start":
                            "2026-10-05",
                    },
                ]
            },
            now=datetime(
                2026,
                10,
                5,
                6,
                30,
                tzinfo=timezone.utc,
            ),
        )

        self.assertNotIn(
            "Heure non précisée",
            caption,
        )

        self.assertTrue(
            any(
                line.startswith(
                    "Rencontre"
                )
                for line
                in caption.splitlines()
            )
        )

        self.assertIn(("Rencontre " * 15).strip(), caption)
        self.assertNotIn("…", caption)

        self.assertLessEqual(
            MODULE._weighted_x_length(
                caption
            ),
            280,
        )

    def test_today_events_roundup_is_daily_compact_and_has_internal_destination(self):
        now = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)
        payload = {
            "campaign_events": [
                {
                    "title": "Gabriel Attal dans La parole est à vous",
                    "status": "scheduled",
                    "scheduled_start": "2026-10-05T20:00:00+02:00",
                },
                {
                    "title": "Raphaël Glucksmann rencontre à Marseille",
                    "status": "confirmed",
                    "scheduled_start": "2026-10-05T19:00:00+02:00",
                },
                {
                    "title": "Événement demain",
                    "status": "scheduled",
                    "scheduled_start": "2026-10-06T10:00:00+02:00",
                },
            ]
        }
        caption = MODULE.render_today_events(payload, now=now)
        self.assertIn("AUJOURD’HUI DANS LA CAMPAGNE 2027", caption)
        self.assertIn("19h00 · Raphaël Glucksmann", caption)
        self.assertIn("20h00 · Gabriel Attal", caption)
        self.assertNotIn("Événement demain", caption)
        self.assertTrue(caption.endswith("https://france2027.app/#signal-events"))
        self.assertLessEqual(MODULE._weighted_x_length(caption), 280)

    def test_events_destination_is_registered_home_and_published_events_view(self):
        root = Path(__file__).parent
        routes = json.loads((root / "route_registry.json").read_text(encoding="utf-8"))["routes"]
        home = [r for r in routes if r["route_id"] == "home:fr"]
        self.assertEqual(len(home), 1)
        self.assertEqual(MODULE.campaign_events_destination(), home[0]["canonical_url"] + "#signal-events")
        self.assertTrue((root / home[0]["source_file"]).is_file())
        dashboard = (root / "assets/hybrid-dashboard.js").read_text(encoding="utf-8")
        self.assertIn('hash: "#signal-events"', dashboard)
        self.assertIn('panelId: "signal-events-panel"', dashboard)
        self.assertIn('hashToView.get(window.location.hash)', dashboard)

    def test_long_event_roundup_keeps_complete_url_and_reduces_events(self):
        payload = {"campaign_events": [
            {"title": f"Rencontre {i} " + "événement 👀 " * 8,
             "status": "confirmed", "scheduled_start": f"2026-10-05T{10+i:02d}:00:00+02:00"}
            for i in range(4)
        ]}
        now = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)
        text = MODULE.render_today_events(payload, now=now)
        self.assertEqual(text, MODULE.render_today_events(payload, now=now))
        self.assertTrue(text.endswith("https://france2027.app/#signal-events"))
        listed = [line for line in text.splitlines() if "h00 · " in line]
        self.assertGreater(len(listed), 0)
        self.assertLess(len(listed), 4)
        self.assertEqual(listed, ["10h00 · " + payload["campaign_events"][0]["title"].strip()])
        self.assertNotIn("…", text)
        self.assertLessEqual(MODULE.standard_fr27_weighted_length(text), 280)

    def test_event_roundup_missing_canonical_destination_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            path.write_text(json.dumps({"routes": []}), encoding="utf-8")
            with patch.object(MODULE, "ROUTE_REGISTRY_PATH", path):
                with self.assertRaisesRegex(ValueError, "canonical FR27"):
                    MODULE.render_today_events({"campaign_events": [
                        {"title": "Rencontre", "status": "confirmed", "scheduled_start": "2026-10-05"}
                    ]}, now=datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc))

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


    def test_online_speaking_time_development_is_collapsed(self):
        left = {
            "id": "arcom-a",
            "category": "legal",
            "headline": (
                "Présidentielle 2027 : "
                "l’Arcom pourrait compter le temps "
                "de parole politique dans les "
                "podcasts de ces influenceurs ?"
            ),
            "trusted_change_at": (
                "2026-10-04T10:00:00Z"
            ),
        }

        right = {
            "id": "arcom-b",
            "category": "campaign",
            "headline": (
                "Présidentielle 2027 : "
                "Sam Zirah, Legend, Hugo Décrypte… "
                "Les interviews politiques en ligne "
                "bientôt comptabilisées dans le "
                "temps de parole"
            ),
            "trusted_change_at": (
                "2026-10-04T14:00:00Z"
            ),
        }

        self.assertTrue(
            MODULE._recent_changes_social_match(
                left,
                right,
            )
        )

    def test_online_speaking_time_dedupe_does_not_cross_large_date_gap(self):
        left = {
            "category": "legal",
            "headline": (
                "Arcom : temps de parole politique "
                "dans les podcasts d’influenceurs"
            ),
            "trusted_change_at": (
                "2026-10-01T10:00:00Z"
            ),
        }

        right = {
            "category": "campaign",
            "headline": (
                "Interviews politiques en ligne : "
                "nouvelle règle de temps de parole "
                "pour Hugo Décrypte"
            ),
            "trusted_change_at": (
                "2026-10-05T10:00:00Z"
            ),
        }

        self.assertFalse(
            MODULE._recent_changes_social_match(
                left,
                right,
            )
        )

    def test_unrelated_temps_de_parole_story_is_not_collapsed(self):
        left = {
            "category": "legal",
            "headline": (
                "Temps de parole dans les podcasts "
                "des influenceurs"
            ),
            "trusted_change_at": (
                "2026-10-04T10:00:00Z"
            ),
        }

        right = {
            "category": "legal",
            "headline": (
                "Temps de parole à l’Assemblée "
                "nationale après une polémique"
            ),
            "trusted_change_at": (
                "2026-10-04T11:00:00Z"
            ),
        }

        self.assertFalse(
            MODULE._recent_changes_social_match(
                left,
                right,
            )
        )


    def test_bootstrap_includes_empty_planner_state(self):
        state = MODULE.build_bootstrap_state(
            {
                "items": [
                    {
                        "id":
                            "existing-change"
                    }
                ]
            },
            {
                "campaign_events": [
                    {
                        "event_id":
                            "existing-event"
                    }
                ]
            },
            now=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            state["planner"],
            {
                "schema_version": 1,
                "published_quantitative": [],
                "roundup_dates": [],
                "dynamic_updates": [],
            },
        )

    def test_validate_state_upgrades_legacy_state_without_losing_seen_ids(self):
        state = {
            "schema_version": 1,
            "initialized_at":
                "2026-10-01T00:00:00Z",
            "updated_at":
                "2026-10-01T00:00:00Z",
            "seen": {
                "recent_changes": [
                    "change-a"
                ],
                "campaign_events": [
                    "event-a"
                ],
            },
        }

        result = MODULE._validate_state(
            state
        )

        self.assertEqual(
            result["seen"][
                "recent_changes"
            ],
            ["change-a"],
        )

        self.assertEqual(
            result["seen"][
                "campaign_events"
            ],
            ["event-a"],
        )

        self.assertEqual(
            result["planner"][
                "schema_version"
            ],
            1,
        )


    def test_dynamic_quota_starts_at_three(self):
        state = MODULE.build_bootstrap_state(
            {"items": []},
            {"campaign_events": []},
            now=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            MODULE._dynamic_quota_remaining(
                state,
                now=datetime(
                    2026,
                    10,
                    5,
                    10,
                    tzinfo=timezone.utc,
                ),
            ),
            3,
        )

    def test_dynamic_quota_counts_only_same_paris_day(self):
        state = MODULE.build_bootstrap_state(
            {"items": []},
            {"campaign_events": []},
            now=datetime(
                2026,
                10,
                4,
                6,
                tzinfo=timezone.utc,
            ),
        )

        planner = state["planner"]

        planner["dynamic_updates"] = [
            {
                "kind": "recent_change",
                "key": "old",
                "date": "2026-10-04",
                "published_at":
                    "2026-10-04T12:00:00Z",
            },
            {
                "kind": "recent_change",
                "key": "today-a",
                "date": "2026-10-05",
                "published_at":
                    "2026-10-05T08:00:00Z",
            },
            {
                "kind": "campaign_event",
                "key": "today-b",
                "date": "2026-10-05",
                "published_at":
                    "2026-10-05T09:00:00Z",
            },
        ]

        self.assertEqual(
            MODULE._dynamic_quota_remaining(
                state,
                now=datetime(
                    2026,
                    10,
                    5,
                    12,
                    tzinfo=timezone.utc,
                ),
            ),
            1,
        )

    def test_dynamic_record_is_idempotent(self):
        state = MODULE.build_bootstrap_state(
            {"items": []},
            {"campaign_events": []},
            now=datetime(
                2026,
                10,
                5,
                6,
                tzinfo=timezone.utc,
            ),
        )

        candidate = MODULE.SocialCandidate(
            key="change-a",
            kind="recent_change",
            observed_at=datetime(
                2026,
                10,
                5,
                8,
                tzinfo=timezone.utc,
            ),
            text="Example",
            source_url=(
                "https://example.test/a"
            ),
        )

        now = datetime(
            2026,
            10,
            5,
            10,
            tzinfo=timezone.utc,
        )

        MODULE._record_dynamic_update(
            state,
            candidate,
            published_at=now,
        )

        MODULE._record_dynamic_update(
            state,
            candidate,
            published_at=now,
        )

        self.assertEqual(
            len(
                state["planner"][
                    "dynamic_updates"
                ]
            ),
            1,
        )

        self.assertEqual(
            MODULE._dynamic_quota_remaining(
                state,
                now=now,
            ),
            2,
        )

    def test_legacy_planner_gains_dynamic_ledger(self):
        state = {
            "schema_version": 1,
            "initialized_at":
                "2026-10-01T00:00:00Z",
            "updated_at":
                "2026-10-01T00:00:00Z",
            "seen": {
                "recent_changes": [],
                "campaign_events": [],
            },
            "planner": {
                "schema_version": 1,
                "published_quantitative": [],
                "roundup_dates": [],
            },
        }

        MODULE._validate_state(
            state
        )

        self.assertEqual(
            state["planner"][
                "dynamic_updates"
            ],
            [],
        )



    def test_updates_noop_does_not_write_state_or_call_buffer(self):
        now = datetime(
            2026,
            10,
            5,
            12,
            tzinfo=timezone.utc,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            state_path = root / "state.json"
            output_path = root / "output.json"
            recent_path = root / "recent.json"
            events_path = root / "events.json"

            state = MODULE.build_bootstrap_state(
                {"items": []},
                {"campaign_events": []},
                now=now,
            )

            MODULE._save_json(
                str(state_path),
                state,
            )

            MODULE._save_json(
                str(recent_path),
                {"items": []},
            )

            MODULE._save_json(
                str(events_path),
                {"campaign_events": []},
            )

            args = SimpleNamespace(
                state=str(state_path),
                state_output=str(output_path),
                recent_changes=str(recent_path),
                campaign_events=str(events_path),
                now="2026-10-05T12:00:00Z",
                lookback_hours=24,
                daily_limit=3,
                max_posts=1,
                dry_run=False,
            )

            with patch.object(
                MODULE,
                "collect_update_candidates",
                return_value=[],
            ):
                with patch.object(
                    MODULE.BufferClient,
                    "from_env",
                    side_effect=AssertionError(
                        "Buffer must not be touched "
                        "for a no-op update check"
                    ),
                ):
                    result = MODULE.run_updates(
                        args
                    )

            self.assertEqual(
                result,
                0,
            )

            self.assertFalse(
                output_path.exists()
            )


    def test_duplicate_recovery_consumes_final_daily_quota_slot(self):
        now = datetime(
            2026,
            10,
            5,
            12,
            tzinfo=timezone.utc,
        )

        duplicate = MODULE.SocialCandidate(
            key="duplicate-change",
            kind="recent_change",
            observed_at=datetime(
                2026,
                10,
                5,
                10,
                tzinfo=timezone.utc,
            ),
            text=(
                "Duplicate development\n\n"
                "https://example.test/duplicate"
            ),
            source_url=(
                "https://example.test/duplicate"
            ),
        )

        fresh = MODULE.SocialCandidate(
            key="fresh-change",
            kind="recent_change",
            observed_at=datetime(
                2026,
                10,
                5,
                10,
                30,
                tzinfo=timezone.utc,
            ),
            text=(
                "Fresh development\n\n"
                "https://example.test/fresh"
            ),
            source_url=(
                "https://example.test/fresh"
            ),
        )

        class FakeBuffer:
            def __init__(self):
                self.created = []

            def recent_post_texts(
                self,
                *,
                since,
            ):
                return {
                    duplicate.text.strip()
                }

            def create_post(
                self,
                text,
                image_url="",
            ):
                self.created.append(
                    text
                )
                return "unexpected-post-id"

        fake_buffer = FakeBuffer()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            state_path = root / "state.json"
            output_path = root / "output.json"
            recent_path = root / "recent.json"
            events_path = root / "events.json"

            state = MODULE.build_bootstrap_state(
                {"items": []},
                {"campaign_events": []},
                now=now,
            )

            state["planner"][
                "dynamic_updates"
            ] = [
                {
                    "kind": "recent_change",
                    "key": "already-a",
                    "date": "2026-10-05",
                    "published_at":
                        "2026-10-05T08:00:00Z",
                },
                {
                    "kind": "campaign_event",
                    "key": "already-b",
                    "date": "2026-10-05",
                    "published_at":
                        "2026-10-05T09:00:00Z",
                },
            ]

            MODULE._save_json(
                str(state_path),
                state,
            )

            MODULE._save_json(
                str(recent_path),
                {"items": []},
            )

            MODULE._save_json(
                str(events_path),
                {"campaign_events": []},
            )

            args = SimpleNamespace(
                state=str(state_path),
                state_output=str(output_path),
                recent_changes=str(recent_path),
                campaign_events=str(events_path),
                now="2026-10-05T12:00:00Z",
                lookback_hours=24,
                daily_limit=3,
                max_posts=3,
                dry_run=False,
            )

            with patch.object(
                MODULE,
                "collect_update_candidates",
                return_value=[
                    duplicate,
                    fresh,
                ],
            ):
                with patch.object(
                    MODULE.BufferClient,
                    "from_env",
                    return_value=fake_buffer,
                ):
                    result = MODULE.run_updates(
                        args
                    )

            self.assertEqual(
                result,
                0,
            )

            # The duplicate occupies the third and final
            # daily slot. The fresh candidate must not be
            # published in the same run.
            self.assertEqual(
                fake_buffer.created,
                [],
            )

            self.assertTrue(
                output_path.exists()
            )

            updated = MODULE._load_json(
                str(output_path)
            )

            self.assertIn(
                "duplicate-change",
                updated["seen"][
                    "recent_changes"
                ],
            )

            self.assertNotIn(
                "fresh-change",
                updated["seen"][
                    "recent_changes"
                ],
            )

            self.assertEqual(
                len(
                    MODULE._dynamic_updates_today(
                        updated,
                        now=now,
                    )
                ),
                3,
            )

            self.assertEqual(
                MODULE._dynamic_quota_remaining(
                    updated,
                    now=now,
                    limit=3,
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
