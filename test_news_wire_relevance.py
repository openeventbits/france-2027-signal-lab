import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fetch_news_wire import (
    SOURCES,
    classify_notable_development,
    classify_relevant_news,
    current_presidential_matches,
    explicit_election_match,
    is_static_entity_page,
    limit_items,
    merge_inventory,
    normalize,
    parse_feed,
)


class NewsWireRelevanceTests(unittest.TestCase):
    def test_registry_declares_source_specificity(self):
        self.assertEqual(len(SOURCES), 19)
        self.assertTrue(all(
            isinstance(source.get("politics_specific"), bool)
            for source in SOURCES
        ))

    def test_rss_summary_is_parsed_and_can_supply_election_context(self):
        raw = """<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><item>
          <title>Le parti arrête son calendrier</title>
          <link>https://example.test/article</link>
          <pubDate>Wed, 22 Jul 2026 08:00:00 GMT</pubDate>
          <description>La primaire pour l'election presidentielle 2027 est fixee.</description>
        </item></channel></rss>""".encode("utf-8")
        entries = parse_feed(raw, "Example", "https://example.test/rss")
        self.assertEqual(len(entries), 1)
        combined = normalize(entries[0]["headline"] + " " + entries[0]["summary"])
        self.assertTrue(explicit_election_match(combined))

    def test_summary_legal_word_cannot_create_a_notable_change(self):
        headline = normalize(
            "Marine Le Pen ou le trumpisme à la française"
        )
        combined = normalize(
            "Marine Le Pen ou le trumpisme à la française. "
            "L’éditorial rappelle sa condamnation et sa candidature "
            "à la présidentielle."
        )
        result = classify_notable_development(
            combined,
            ["Marine Le Pen"],
            {"politics_specific": True},
            headline,
        )
        self.assertIsNone(result)

    def test_material_development_gate_accepts_actions_and_rejects_mentions(self):
        source = {"politics_specific": True}
        accepted = classify_notable_development(
            normalize("Edouard Philippe echoue a faire annuler le statut de la lanceuse d alerte"),
            ["Edouard Philippe"],
            source,
        )
        rejected = classify_notable_development(
            normalize("Marine Le Pen joue au golf avec Jordan Bardella"),
            ["Marine Le Pen", "Jordan Bardella"],
            source,
        )
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["id"], "legal_eligibility")
        self.assertIsNone(rejected)


    def test_notable_gate_rejects_unrelated_national_politics(self):
        source = {"politics_specific": True}
        rejected = [
            (
                "Protoxyde d azote rodeos urbains free parties le Parlement "
                "adopte definitivement le projet de loi Ripost de Laurent Nunez",
                ["Laurent Nuñez"],
            ),
            (
                "Finalement la ministre Monique Barbut decide de rester au "
                "gouvernement apres avoir vu Emmanuel Macron",
                ["Emmanuel Macron"],
            ),
            (
                "Interdiction des reseaux sociaux aux moins de 15 ans la loi "
                "vient d etre definitivement adoptee",
                ["Sébastien Lecornu"],
            ),
            (
                "Senatoriales dans les Bouches du Rhone Valerie Boyer se lance "
                "de son cote",
                ["Valérie Boyer"],
            ),
            (
                "France le senateur republicain Francois Noel Buffet nomme "
                "Defenseur des droits",
                ["François-Noël Buffet"],
            ),
        ]
        for headline, candidates in rejected:
            self.assertIsNone(
                classify_notable_development(
                    normalize(headline),
                    candidates,
                    source,
                    normalize(headline),
                ),
                headline,
            )

    def test_notable_gate_keeps_presidential_actions_and_candidate_legal_outcomes(self):
        source = {"politics_specific": True}
        accepted = [
            (
                "Presidentielle Francois Hollande se prepare a entrer en campagne",
                ["François Hollande"],
                "candidacies_endorsements",
            ),
            (
                "Vise par une enquete Edouard Philippe echoue a faire annuler "
                "le statut de la lanceuse d alerte",
                ["Édouard Philippe"],
                "legal_eligibility",
            ),
            (
                "Presidentielle le PS se prononce pour une primaire fermee",
                [],
                "selection_strategy",
            ),
            (
                "Presidentielle Marine Le Pen envisageant la piste d un "
                "referendum met la pression sur le Conseil constitutionnel",
                ["Marine Le Pen"],
                "positioning_integrity",
            ),
        ]
        for headline, candidates, expected in accepted:
            result = classify_notable_development(
                normalize(headline),
                candidates,
                source,
                normalize(headline),
            )
            self.assertIsNotNone(result, headline)
            self.assertEqual(result["id"], expected)

    def test_broad_relevance_accepts_candidate_commentary(self):
        result = classify_relevant_news(
            normalize("Marine Le Pen ou le trumpisme à la française"),
            normalize("Un éditorial analyse son positionnement politique."),
            ["Marine Le Pen"],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "candidate_political_coverage")

    def test_broad_relevance_rejects_candidate_lifestyle(self):
        result = classify_relevant_news(
            normalize("Marine Le Pen joue au golf avec Jordan Bardella"),
            "",
            ["Marine Le Pen", "Jordan Bardella"],
        )
        self.assertIsNone(result)

    def test_broad_relevance_rejects_routine_government_and_legislation(self):
        rejected = [
            (
                "Finalement la ministre Monique Barbut reste au gouvernement "
                "après avoir vu Emmanuel Macron",
                ["Emmanuel Macron"],
            ),
            (
                "Aide à mourir Olivier Falorni présente le calendrier de la loi",
                ["Olivier Falorni"],
            ),
            (
                "Sénatoriales Valérie Boyer annonce sa candidature",
                ["Valérie Boyer"],
            ),
        ]
        for headline, candidates in rejected:
            self.assertIsNone(
                classify_relevant_news(
                    normalize(headline),
                    "",
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_rejects_weak_presidential_false_positives(self):
        rejected = [
            (
                "Emmanuel Macron accueille Ursula von der Leyen a l Elysee",
                "Une rencontre a la presidence de la Republique.",
                [],
            ),
            (
                "Monique Barbut symbole de la desillusion ecologique sous Macron",
                "Le gouvernement prepare le budget 2027.",
                ["Emmanuel Macron"],
            ),
            (
                "Budget 2027 le gouvernement esquisse ses priorites",
                "Le chef de l Etat recevra les ministres a l Elysee.",
                [],
            ),
            (
                "Aide a mourir deux ans de debats et trois gouvernements",
                "Le texte pourrait peser avant la presidentielle 2027.",
                ["Sébastien Lecornu"],
            ),
            (
                "Affaire Balogun la Fifa est verolee de trumpisme",
                "Une controverse pendant la Coupe du monde de football.",
                [],
            ),
            (
                "Presidentielle 2012 la victoire du president normal",
                "Retour historique sur Francois Hollande.",
                ["François Hollande"],
            ),
            (
                "Presidentielle 2007 le duel Sarko Sego",
                "Archive politique.",
                [],
            ),
        ]
        for headline, summary, candidates in rejected:
            self.assertIsNone(
                classify_relevant_news(
                    normalize(headline),
                    normalize(summary),
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_keeps_current_race_analysis_and_summary_confirmation(self):
        accepted = [
            (
                "Presidentielle pour Bernard Cazeneuve LFI n est pas en situation de gouverner",
                "",
                ["Bernard Cazeneuve"],
            ),
            (
                "Pour 2027 Melenchon tend la main aux Ecologistes",
                "La proposition concerne la prochaine presidentielle.",
                ["Jean-Luc Mélenchon"],
            ),
            (
                "Le Parti socialiste arrete son calendrier",
                "La primaire doit designer son candidat a l election presidentielle de 2027.",
                [],
            ),
            (
                "Marine Le Pen ou le trumpisme a la francaise",
                "Un editorial analyse son positionnement politique.",
                ["Marine Le Pen"],
            ),
        ]
        for headline, summary, candidates in accepted:
            self.assertIsNotNone(
                classify_relevant_news(
                    normalize(headline),
                    normalize(summary),
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_accepts_campaign_and_party_selection(self):
        accepted = [
            (
                "Entretien avec François Hollande sur sa stratégie pour 2027",
                "",
                ["François Hollande"],
            ),
            (
                "Le Parti socialiste débat de sa primaire",
                "La formation prépare la présidentielle de 2027.",
                [],
            ),
            (
                "Marine Le Pen détaille sa stratégie",
                "La candidate prépare sa campagne présidentielle.",
                ["Marine Le Pen"],
            ),
        ]
        for headline, summary, candidates in accepted:
            self.assertIsNotNone(
                classify_relevant_news(
                    normalize(headline),
                    normalize(summary),
                    candidates,
                ),
                headline,
            )

    def test_broad_relevance_summary_can_confirm_presidential_context(self):
        result = classify_relevant_news(
            normalize("Le parti arrête son calendrier"),
            normalize(
                "La primaire doit désigner son candidat à l'élection "
                "présidentielle de 2027."
            ),
            [],
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            result["reason"],
            "summary_confirmed_presidential_context",
        )

    def test_current_election_signals_reject_historical_presidential_years(self):
        self.assertEqual(
            current_presidential_matches(
                normalize("Présidentielle 2012: la victoire du président normal")
            ),
            [],
        )
        self.assertTrue(
            current_presidential_matches(
                normalize("Présidentielle 2027: une alliance est proposée")
            )
        )

    def test_static_candidate_directory_pages_are_not_articles(self):
        self.assertTrue(
            is_static_entity_page(
                "Jean-Luc Mélenchon",
                "https://www.bfmtv.com/politique/jean-luc-melenchon_DN-201701010040.html",
                ["Jean-Luc Mélenchon"],
            )
        )
        self.assertTrue(
            is_static_entity_page(
                "Sébastien Lecornu Premier ministre",
                "https://www.bfmtv.com/politique/sebastien-lecornu-premier-ministre_DN-202509100375.html",
                ["Sébastien Lecornu"],
            )
        )
        self.assertFalse(
            is_static_entity_page(
                "Présidentielle 2027: Jean-Luc Mélenchon propose un accord aux Écologistes",
                "https://www.bfmtv.com/politique/example_AD-202607220391.html",
                ["Jean-Luc Mélenchon"],
            )
        )

    def test_zero_item_limit_means_unlimited(self):
        items = [{"id": index} for index in range(75)]
        self.assertEqual(limit_items(items, 0), items)
        self.assertEqual(len(limit_items(items, 12)), 12)


    @staticmethod
    def inventory_entry(
        published_at: datetime,
        headline: str = "Presidentielle 2027 : un article",
        summary: str = "Contexte politique.",
    ):
        return {
            "source_id": "example",
            "publisher": "Example",
            "feed_url": "https://example.test/rss",
            "politics_specific": True,
            "headline": headline,
            "summary": summary,
            "url": "https://example.test/article",
            "canonical_url": "https://example.test/article",
            "published_at": published_at,
            "candidate_names": [],
        }

    def test_inventory_retains_article_after_it_leaves_the_feed(self):
        first_run = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        first, _entries, stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [self.inventory_entry(first_run - timedelta(days=2))],
            first_run,
            30,
        )
        self.assertEqual(stats["new_items_discovered"], 1)

        second, entries, stats = merge_inventory(
            first,
            [],
            first_run + timedelta(hours=1),
            30,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(stats["retained_inventory_items"], 1)
        self.assertEqual(stats["new_items_discovered"], 0)
        self.assertEqual(second, first)

    def test_inventory_prunes_articles_after_the_window(self):
        first_run = datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
        first, _entries, _stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [self.inventory_entry(first_run)],
            first_run,
            30,
        )

        second, entries, stats = merge_inventory(
            first,
            [],
            first_run + timedelta(days=31),
            30,
        )
        self.assertEqual(entries, [])
        self.assertEqual(second["items"], [])
        self.assertEqual(stats["expired_inventory_items"], 1)

    def test_inventory_does_not_store_full_feed_content(self):
        generated_at = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        payload, _entries, _stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [self.inventory_entry(generated_at, summary="x" * 5000)],
            generated_at,
            30,
        )
        self.assertEqual(len(payload["items"][0]["summary"]), 1000)


    def test_inventory_preserves_candidate_matches_beyond_summary_limit(self):
        generated_at = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
        entry = self.inventory_entry(
            generated_at,
            headline="Une actualité gouvernementale",
            summary=("x" * 1200) + " Gabriel Attal",
        )
        # build_wire derives this from the complete feed summary before
        # merge_inventory stores only the bounded summary.
        entry["candidate_names"] = ["Gabriel Attal"]
        entry["relevance_reason"] = "campaign_or_selection_context"
        entry["relevance_terms"] = ["presidentielle"]

        payload, entries, _stats = merge_inventory(
            {"schema_version": 3, "generated_at": None, "window_days": 30, "items": []},
            [entry],
            generated_at,
            30,
        )

        self.assertEqual(len(payload["items"][0]["summary"]), 1000)
        self.assertEqual(
            payload["items"][0]["candidate_names"],
            ["Gabriel Attal"],
        )
        self.assertEqual(entries[0]["candidate_names"], ["Gabriel Attal"])
        self.assertEqual(
            payload["items"][0]["relevance_reason"],
            "campaign_or_selection_context",
        )
        self.assertEqual(
            entries[0]["relevance_terms"],
            ["presidentielle"],
        )


if __name__ == "__main__":
    unittest.main()
