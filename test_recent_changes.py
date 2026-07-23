import copy
import json
import unittest
from collections import Counter
from datetime import timedelta
from pathlib import Path

from fetch_news_wire import SOURCES
from generate_recent_changes import (
    LedgerError,
    classify_candidate_watch_change,
    classify_news_change,
    icon_key,
    compose_recent_changes,
    fact_check_entries,
    news_entries,
    normalized_title,
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
        self.assertGreaterEqual(len(payload["items"]), 1)
        self.assertEqual(payload["window"]["max_items"], 0)
        self.assertEqual(len(SOURCES), 19)
        self.assertEqual(
            payload["source_universe"],
            [source["name"] for source in SOURCES],
        )

    def test_historical_polls_use_fieldwork_end_not_generator_date(self):
        diagnostics = Counter()
        entries = poll_entries(
            self.polls,
            {},
            FIXED_CLOCK,
            diagnostics,
        )

        expected = {
            "Elabe": "2026-07-10",
            "Verian": "2026-07-10",
            "OpinionWay": "2026-07-09",
        }
        for pollster, trusted_date in expected.items():
            matches = [
                item for item in entries
                if item["primary_source"]["name"] == pollster
                and item["trusted_change_at"] == trusted_date
            ]
            self.assertEqual(
                len(matches),
                1,
                f"expected one {pollster} wave dated {trusted_date}",
            )
            self.assertEqual(
                matches[0]["trusted_change_date_kind"],
                "fieldwork_ended",
            )
            self.assertNotEqual(
                matches[0]["trusted_change_at"],
                FIXED_CLOCK.date().isoformat(),
            )

    def test_six_hypotheses_create_one_poll_wave_item(self):
        diagnostics = Counter()
        entries = poll_entries(self.polls, {}, FIXED_CLOCK, diagnostics)
        elabe = [
            item for item in entries
            if item["primary_source"]["name"] == "Elabe"
            and item["trusted_change_at"] == "2026-07-10"
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
        self.assertEqual(
            second["items"][0]["trusted_change_at"],
            first["items"][0]["trusted_change_at"],
        )

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

    def test_frontend_reports_partial_news_feeds_and_aliases_lcp_icon(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('"lcp actualites", "lcp"', index)
        self.assertIn('unavailableNewsSources', index)
        self.assertIn('" news feeds ready"', index)
        self.assertIn('image.style.visibility = "hidden"', index)

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

    def test_campaign_deduplication_preserves_only_genuine_support(self):
        primary = {
            "id": "cazeneuve-lcp",
            "publisher": "LCP — Actualités",
            "published_at": "2026-07-16T19:23:28Z",
            "headline": (
                "Présidentielle 2027 : Bernard Cazeneuve décline "
                "la primaire socialiste"
            ),
            "summary": "",
            "url": "https://lcp.fr/example-cazeneuve-primary",
            "explicit_election": True,
            "candidates": ["Bernard Cazeneuve"],
        }

        supporting = {
            "id": "cazeneuve-public-senat",
            "publisher": "Public Sénat",
            "published_at": "2026-07-17T10:00:00Z",
            "headline": (
                "Présidentielle 2027 : Bernard Cazeneuve décline "
                "la primaire du Parti socialiste"
            ),
            "summary": "",
            "url": "https://publicsenat.fr/example-cazeneuve-primary",
            "explicit_election": True,
            "candidates": ["Bernard Cazeneuve"],
        }

        commentary = {
            "id": "cazeneuve-commentary",
            "publisher": "Le Nouvel Obs",
            "published_at": "2026-07-17T14:00:00Z",
            "headline": (
                "Présidentielle 2027 : la candidature de Bernard Cazeneuve "
                "traduit les difficultés de la gauche"
            ),
            "summary": (
                "Une analyse de la stratégie et du renouvellement "
                "du personnel politique."
            ),
            "url": "https://nouvelobs.com/example-cazeneuve-commentary",
            "explicit_election": True,
            "candidates": ["Bernard Cazeneuve"],
        }

        payload = {
            "generated_at": "2026-07-22T09:00:00Z",
            "election_news": [
                primary,
                supporting,
                commentary,
            ],
            "notable_developments": [],
            # Repeated upstream-lane copies must not become support.
            "candidate_watch": [
                copy.deepcopy(primary),
                copy.deepcopy(commentary),
            ],
        }

        entries = news_entries(
            payload,
            {},
            FIXED_CLOCK,
            Counter(),
        )

        cazeneuve = [
            item for item in entries
            if item["category"] == "campaign"
            and "cazeneuve" in item["headline"].lower()
        ]

        self.assertEqual(len(cazeneuve), 1)
        self.assertEqual(cazeneuve[0]["supporting_source_count"], 1)
        self.assertEqual(
            [
                source["name"]
                for source in cazeneuve[0]["supporting_sources"]
            ],
            ["Public Sénat"],
        )
        self.assertNotIn(
            "Le Nouvel Obs",
            {
                source["name"]
                for source in cazeneuve[0]["supporting_sources"]
            },
        )

    def test_distinct_ps_events_are_not_clustered_as_support(self):
        shared_candidates = [
            "François Hollande",
            "Jean-Luc Mélenchon",
            "Marine Le Pen",
            "Marine Tondelier",
            "Olivier Faure",
            "Raphaël Glucksmann",
        ]
        headlines = [
            (
                "ps-vote-preview",
                "Présidentielle 2027: pourquoi le vote organisé ce jeudi "
                "au PS s’avère si crucial pour la gauche",
            ),
            (
                "ps-primary-result",
                "Présidentielle: le PS se prononce pour une primaire "
                "fermée, un désaveu pour Olivier Faure",
            ),
            (
                "tondelier-rupture",
                "Les adhérents du PS ont décidé d’enterrer la primaire: "
                "Marine Tondelier acte la rupture avant la présidentielle",
            ),
            (
                "royal-candidacy",
                "Présidentielle 2027: Ségolène Royal annonce sa "
                "candidature à la primaire socialiste",
            ),
        ]
        items = [
            {
                "id": item_id,
                "publisher": "LCP — Actualités",
                "published_at": f"2026-07-{9 + index:02d}T10:00:00Z",
                "headline": headline,
                "summary": "",
                "url": f"https://lcp.fr/{item_id}",
                "explicit_election": True,
                # Simulate broad summary-derived candidate associations.
                "candidates": shared_candidates,
            }
            for index, (item_id, headline) in enumerate(headlines)
        ]
        entries = news_entries(
            {
                "generated_at": "2026-07-22T09:00:00Z",
                "election_news": items,
                "notable_developments": [],
                "candidate_watch": copy.deepcopy(items),
            },
            {},
            FIXED_CLOCK,
            Counter(),
        )
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(
            item["supporting_source_count"] == 0
            for item in entries
        ))
        self.assertNotIn(
            "pourquoi le vote organisé",
            " ".join(item["headline"].lower() for item in entries),
        )

    def test_fact_checks_of_the_same_claim_cluster_across_publishers(self):
        claims = {
            "generated_at": "2026-07-17T12:00:19Z",
            "reviews": [
                {
                    "id": "tf1-melenchon",
                    "review_url": "https://tf1info.fr/melenchon-claim",
                    "publisher_name": "TF1 Info",
                    "review_date": "2026-07-15",
                    "claim_text": (
                        "Jean-Luc Mélenchon déclaré dans une interview en "
                        "1991 que le Front national réhabilite la politique"
                    ),
                    "rating": "Plutôt faux",
                    "candidate_associations": [
                        {
                            "candidate_id": "jean-luc-melenchon",
                            "candidate_name": "Jean-Luc Mélenchon",
                        }
                    ],
                },
                {
                    "id": "franceinfo-melenchon",
                    "review_url": "https://franceinfo.fr/melenchon-claim",
                    "publisher_name": "franceinfo",
                    "review_date": "2026-07-17",
                    "claim_text": (
                        "Jean-Luc Mélenchon a déclaré que le seul parti qui "
                        "réhabilite la politique est le Front national"
                    ),
                    "rating": "C’est plus compliqué",
                    "candidate_associations": [
                        {
                            "candidate_id": "jean-luc-melenchon",
                            "candidate_name": "Jean-Luc Mélenchon",
                        }
                    ],
                },
            ],
        }
        entries = fact_check_entries(
            claims,
            {},
            FIXED_CLOCK,
            Counter(),
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["primary_source"]["name"], "franceinfo")
        self.assertEqual(entries[0]["trusted_change_at"], "2026-07-17")
        self.assertEqual(entries[0]["supporting_source_count"], 1)
        self.assertEqual(
            entries[0]["supporting_sources"][0]["name"],
            "TF1 Info",
        )

    def test_candidate_watch_filter_admits_only_material_changes(self):
        accepted = [
            (
                {
                    "headline": (
                        "Présidentielle : François Hollande se prépare et met "
                        "en garde contre les candidatures de témoignage"
                    ),
                    "candidates": ["François Hollande"],
                    "explicit_election": False,
                },
                "campaign",
            ),
            (
                {
                    "headline": (
                        "Visé par une enquête, Edouard Philippe échoue à faire "
                        "annuler le statut de la lanceuse d’alerte"
                    ),
                    "candidates": ["Édouard Philippe"],
                    "explicit_election": False,
                },
                "legal",
            ),
            (
                {
                    "headline": (
                        "Pourquoi Gabriel Attal assigne Marine Le Pen et le RN "
                        "en justice"
                    ),
                    "candidates": ["Gabriel Attal", "Marine Le Pen"],
                    "explicit_election": False,
                },
                "legal",
            ),
        ]
        for item, expected_category in accepted:
            classification = classify_candidate_watch_change(item)
            self.assertIsNotNone(classification)
            self.assertEqual(classification[0], expected_category)

        rejected = [
            {
                "headline": "Marine Le Pen joue au golf avec Jordan Bardella",
                "candidates": ["Marine Le Pen", "Jordan Bardella"],
                "explicit_election": False,
            },
            {
                "headline": (
                    "Sébastien Lecornu révèle que des personnes ont été "
                    "écartées après des tests positifs dans les ministères"
                ),
                "candidates": ["Sébastien Lecornu"],
                "explicit_election": False,
            },
            {
                "headline": "Marine Le Pen ou le trumpisme à la française",
                "candidates": ["Marine Le Pen"],
                "explicit_election": False,
            },
            {
                "headline": (
                    "Protoxyde d'azote, rodéos urbains, free parties : le "
                    "Parlement adopte définitivement le projet de loi Ripost "
                    "de Laurent Nuñez"
                ),
                "candidates": ["Laurent Nuñez"],
                "explicit_election": False,
            },
            {
                "headline": (
                    "Sénatoriales dans les Bouches-du-Rhône : Valérie Boyer "
                    "se lance de son côté"
                ),
                "candidates": ["Valérie Boyer"],
                "explicit_election": False,
            },
            {
                "headline": (
                    "Finalement, la ministre Monique Barbut décide de rester "
                    "au gouvernement après avoir vu Emmanuel Macron"
                ),
                "candidates": ["Emmanuel Macron"],
                "explicit_election": False,
            },
        ]
        self.assertTrue(all(
            classify_candidate_watch_change(item) is None
            for item in rejected
        ))

    def test_headline_first_change_classifier_accepts_required_events(self):
        accepted = [
            (
                {
                    "headline": "Présidentielle : François Hollande se prépare",
                    "candidates": ["François Hollande"],
                    "explicit_election": True,
                },
                "campaign",
            ),
            (
                {
                    "headline": (
                        "Présidentielle 2027: Bernard Cazeneuve décline "
                        "la primaire socialiste"
                    ),
                    "candidates": ["Bernard Cazeneuve"],
                    "explicit_election": True,
                },
                "campaign",
            ),
            (
                {
                    "headline": "Ségolène Royal annonce sa candidature",
                    "candidates": ["Ségolène Royal"],
                    "explicit_election": True,
                },
                "campaign",
            ),
            (
                {
                    "headline": (
                        "Présidentielle: le parti modifie le processus "
                        "de primaire"
                    ),
                    "candidates": [],
                    "explicit_election": True,
                },
                "campaign",
            ),
            (
                {
                    "headline": (
                        "Edouard Philippe échoue à faire annuler une "
                        "décision de justice"
                    ),
                    "candidates": ["Édouard Philippe"],
                    "explicit_election": False,
                },
                "legal",
            ),
            (
                {
                    "headline": (
                        "Gabriel Attal assigne Marine Le Pen et le RN "
                        "en justice"
                    ),
                    "candidates": ["Gabriel Attal", "Marine Le Pen"],
                    "explicit_election": False,
                },
                "legal",
            ),
            (
                {
                    "headline": (
                        "La cour statue sur l’éligibilité de Marine Le Pen"
                    ),
                    "candidates": ["Marine Le Pen"],
                    "explicit_election": False,
                },
                "legal",
            ),
            (
                {
                    "headline": (
                        "Présidentielle 2027: les règles de parrainage "
                        "sont modifiées"
                    ),
                    "candidates": [],
                    "explicit_election": True,
                },
                "legal",
            ),
        ]
        for item, expected_category in accepted:
            classification = classify_news_change(item)
            self.assertIsNotNone(classification, item["headline"])
            self.assertEqual(classification[0], expected_category)

    def test_headline_first_change_classifier_rejects_commentary_and_routine_news(self):
        rejected = [
            {
                "headline": "Marine Le Pen ou le trumpisme à la française",
                "summary": (
                    "L’éditorial rappelle sa condamnation et sa candidature "
                    "à la présidentielle."
                ),
                "candidates": ["Marine Le Pen"],
                "explicit_election": True,
                "development_category": "legal_eligibility",
            },
            {
                "headline": (
                    "Présidentielle 2027: pourquoi le vote organisé ce jeudi "
                    "au PS s’avère si crucial pour la gauche"
                ),
                "candidates": [],
                "explicit_election": True,
            },
            {
                "headline": (
                    "Marine Le Pen, Xavier Milei, Jair Bolsonaro… La longue "
                    "liste des dirigeants d’extrême droite soutenus par "
                    "Elon Musk"
                ),
                "candidates": ["Marine Le Pen"],
                "explicit_election": True,
            },
            {
                "headline": "Marine Le Pen joue au golf avec Jordan Bardella",
                "candidates": ["Marine Le Pen", "Jordan Bardella"],
                "explicit_election": False,
            },
            {
                "headline": "L’Assemblée adopte définitivement la loi sur l’aide à mourir",
                "candidates": [],
                "explicit_election": False,
            },
            {
                "headline": "Le Parlement adopte une loi sur les réseaux sociaux",
                "candidates": [],
                "explicit_election": False,
            },
            {
                "headline": "La ministre décide de rester au gouvernement",
                "candidates": [],
                "explicit_election": False,
            },
            {
                "headline": "François-Noël Buffet nommé Défenseur des droits",
                "candidates": ["François-Noël Buffet"],
                "explicit_election": False,
            },
            {
                "headline": "Sénatoriales: Valérie Boyer annonce sa candidature",
                "candidates": ["Valérie Boyer"],
                "explicit_election": False,
            },
            {
                "headline": "Marine Le Pen commente la stratégie de son parti",
                "candidates": ["Marine Le Pen"],
                "explicit_election": True,
            },
            {
                "headline": "Marine Le Pen présente sa stratégie politique",
                "summary": "Le texte rappelle sa condamnation et son appel.",
                "candidates": ["Marine Le Pen"],
                "explicit_election": True,
            },
            {
                "headline": (
                    "Interdiction du voile: Marine Le Pen envisage la piste "
                    "d’un référendum"
                ),
                "candidates": ["Marine Le Pen"],
                "explicit_election": True,
            },
        ]
        for item in rejected:
            self.assertIsNone(
                classify_news_change(item),
                item["headline"],
            )

    def test_upstream_legal_label_cannot_force_commentary_into_ledger(self):
        commentary = {
            "id": "le-pen-commentary",
            "published_at": "2026-07-15T16:30:13Z",
            "publisher": "Le Nouvel Obs — Politique",
            "url": "https://example.test/le-pen-commentary",
            "headline": "Marine Le Pen ou le trumpisme à la française",
            "summary": (
                "L’éditorial rappelle sa condamnation et sa candidature "
                "à la présidentielle."
            ),
            "candidates": ["Marine Le Pen"],
            "explicit_election": False,
            "development_category": "legal_eligibility",
            "development_label": "Legal status & eligibility",
            "matched_terms": ["condamnation"],
        }
        diagnostics = Counter()
        entries = news_entries(
            {
                "generated_at": "2026-07-22T09:00:00Z",
                "election_news": [],
                "notable_developments": [copy.deepcopy(commentary)],
                "candidate_watch": [copy.deepcopy(commentary)],
            },
            {},
            FIXED_CLOCK,
            diagnostics,
        )
        self.assertEqual(entries, [])
        self.assertEqual(diagnostics["omitted_news_non_material"], 1)

    def test_presidential_alliance_proposal_is_a_campaign_change(self):
        item = {
            "headline": (
                "Présidentielle 2027: Jean-Luc Mélenchon tend la main aux "
                "Écologistes et leur propose un accord global et carré"
            ),
            "candidates": ["Jean-Luc Mélenchon", "Marine Tondelier"],
            "explicit_election": True,
        }
        classification = classify_candidate_watch_change(item)
        self.assertIsNotNone(classification)
        self.assertEqual(classification[0], "campaign")

    def test_alliance_reports_cluster_as_one_event_with_support(self):
        bfmtv = {
            "id": "melenchon-agreement-bfmtv",
            "published_at": "2026-07-22T11:38:32Z",
            "publisher": "BFMTV — Politique",
            "url": "https://example.test/melenchon-agreement-bfmtv",
            "headline": (
                "Présidentielle 2027: Jean-Luc Mélenchon tend la main aux "
                "Écologistes et leur propose un accord global et carré"
            ),
            "candidates": ["Jean-Luc Mélenchon", "Marine Tondelier"],
            "explicit_election": True,
        }
        huffpost = {
            "id": "melenchon-agreement-huffpost",
            "published_at": "2026-07-22T16:59:06Z",
            "publisher": "HuffPost France — Headlines",
            "url": "https://example.test/melenchon-agreement-huffpost",
            "headline": (
                "Pour 2027, Mélenchon tend toujours la main aux Écologistes "
                "mais avec un ultimatum"
            ),
            "candidates": ["Jean-Luc Mélenchon", "Marine Tondelier"],
            "explicit_election": False,
        }
        diagnostics = Counter()
        entries = news_entries(
            {
                "generated_at": "2026-07-22T18:00:00Z",
                "election_news": [copy.deepcopy(bfmtv)],
                "notable_developments": [],
                "candidate_watch": [copy.deepcopy(huffpost)],
            },
            {},
            FIXED_CLOCK,
            diagnostics,
        )
        matches = [
            item for item in entries
            if "melenchon" in normalized_title(item["headline"])
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["supporting_source_count"], 1)
        self.assertEqual(
            matches[0]["supporting_sources"][0]["name"],
            "HuffPost France — Headlines",
        )

    def test_material_candidate_watch_items_enter_news_entries(self):
        payload = {
            "generated_at": "2026-07-22T09:00:00Z",
            "election_news": [],
            "candidate_watch": [
                {
                    "id": "hollande-prepares",
                    "published_at": "2026-07-16T18:20:55Z",
                    "publisher": "Public Sénat",
                    "url": "https://example.test/hollande-prepares",
                    "headline": (
                        "Présidentielle : François Hollande se prépare et met "
                        "en garde contre les candidatures de témoignage"
                    ),
                    "candidates": ["François Hollande"],
                    "explicit_election": False,
                },
                {
                    "id": "philippe-legal",
                    "published_at": "2026-07-18T12:36:49Z",
                    "publisher": "Le Nouvel Obs — Politique",
                    "url": "https://example.test/philippe-legal",
                    "headline": (
                        "Visé par une enquête, Edouard Philippe échoue à faire "
                        "annuler le statut de la lanceuse d’alerte"
                    ),
                    "candidates": ["Édouard Philippe"],
                    "explicit_election": False,
                },
                {
                    "id": "golf",
                    "published_at": "2026-07-18T09:30:14Z",
                    "publisher": "Le Nouvel Obs — Politique",
                    "url": "https://example.test/golf",
                    "headline": "Marine Le Pen joue au golf avec Jordan Bardella",
                    "candidates": ["Marine Le Pen", "Jordan Bardella"],
                    "explicit_election": False,
                },
            ],
        }
        diagnostics = Counter()
        entries = news_entries(payload, {}, FIXED_CLOCK, diagnostics)
        self.assertEqual(
            {item["id"] for item in entries},
            {"campaign-hollande-prepares", "legal-philippe-legal"},
        )
        self.assertEqual(diagnostics["omitted_candidate_watch_non_material"], 1)

    def test_duplicate_item_across_news_lanes_is_not_repeated(self):
        item = {
            "id": "royal-candidacy",
            "published_at": "2026-07-10T12:04:12Z",
            "publisher": "LCP — Actualités",
            "url": "https://example.test/royal-candidacy",
            "headline": (
                "Présidentielle 2027: Ségolène Royal annonce sa candidature "
                "à la primaire socialiste"
            ),
            "candidates": ["Ségolène Royal"],
            "explicit_election": True,
        }
        diagnostics = Counter()
        entries = news_entries(
            {
                "generated_at": "2026-07-22T09:00:00Z",
                "election_news": [copy.deepcopy(item)],
                "candidate_watch": [copy.deepcopy(item)],
            },
            {},
            FIXED_CLOCK,
            diagnostics,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "campaign-royal-candidacy")
        self.assertEqual(diagnostics["omitted_candidate_watch_duplicate"], 1)

    def test_ledger_retains_all_qualifying_changes_in_window(self):
        election_news = []
        for index in range(15):
            candidate_name = f"Personne{index} Unique{index}"
            election_news.append(
                {
                    "id": f"candidate-{index}",
                    "published_at": "2026-07-20T12:00:00Z",
                    "publisher": f"Publisher {index}",
                    "url": f"https://example.test/candidate-{index}",
                    "headline": (
                        f"Présidentielle 2027: {candidate_name} annonce sa "
                        f"candidature et présente le projet distinct {index}"
                    ),
                    "candidates": [candidate_name],
                    "explicit_election": True,
                }
            )
        payload = compose_recent_changes(
            news={
                "generated_at": "2026-07-22T09:00:00Z",
                "election_news": election_news,
                "notable_developments": [],
                "candidate_watch": [],
            },
            polls=[],
            runoff={"status": "insufficient"},
            second_round={"events": []},
            claims={"reviews": []},
            previous={},
            checked_at=FIXED_CLOCK,
        )
        self.assertEqual(len(payload["items"]), 15)
        self.assertEqual(payload["diagnostics"]["omitted_over_output_limit"], 0)

    def test_lcp_actualites_uses_cached_lcp_icon_key(self):
        self.assertEqual(icon_key("LCP — Actualités"), "LCP")
        self.assertEqual(icon_key("France 24 — France"), "France 24 Français")

    def test_validator_rejects_duplicate_primary_urls(self):
        payload = self.compose()
        broken = copy.deepcopy(payload)
        broken["items"][1]["primary_source"]["url"] = broken["items"][0]["primary_source"]["url"]
        with self.assertRaises(LedgerError):
            validate_recent_changes(broken)


    def test_same_day_melenchon_ecologists_reports_cluster(self):
        bfmtv = {
            "id": "melenchon-alliance-bfmtv",
            "publisher": "BFMTV — Politique",
            "published_at": "2026-07-22T07:00:00Z",
            "headline": (
                "Présidentielle 2027: Jean-Luc Mélenchon tend "
                "une nouvelle fois la main aux Écologistes et leur "
                "propose un accord global et carré"
            ),
            "summary": "",
            "url": "https://example.test/bfmtv-alliance",
            "explicit_election": True,
            "candidates": [
                "Jean-Luc Mélenchon",
                "Marine Tondelier",
            ],
        }

        huffpost = {
            "id": "melenchon-alliance-huffpost",
            "publisher": "HuffPost France — Headlines",
            "published_at": "2026-07-22T08:00:00Z",
            "headline": (
                "Pour 2027, Mélenchon tend toujours la main aux "
                "Écologistes mais avec un ultimatum"
            ),
            "summary": "",
            "url": "https://example.test/huffpost-alliance",
            "explicit_election": True,
            "candidates": ["Marine Tondelier"],
        }

        entries = news_entries(
            {
                "generated_at": "2026-07-22T09:00:00Z",
                "election_news": [bfmtv, huffpost],
                "notable_developments": [],
                "candidate_watch": [],
            },
            {},
            FIXED_CLOCK,
            Counter(),
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["primary_source"]["name"],
            "BFMTV — Politique",
        )
        self.assertEqual(
            entries[0]["supporting_source_count"],
            1,
        )
        self.assertEqual(
            entries[0]["supporting_sources"][0]["name"],
            "HuffPost France — Headlines",
        )
        self.assertIn(
            "global et carré",
            entries[0]["headline"],
        )

if __name__ == "__main__":
    unittest.main()
