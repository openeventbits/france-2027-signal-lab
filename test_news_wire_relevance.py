import json
import tempfile
import unittest
from pathlib import Path

from fetch_news_wire import (
    SOURCES,
    classify_notable_development,
    explicit_election_match,
    limit_items,
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

    def test_zero_item_limit_means_unlimited(self):
        items = [{"id": index} for index in range(75)]
        self.assertEqual(limit_items(items, 0), items)
        self.assertEqual(len(limit_items(items, 12)), 12)


if __name__ == "__main__":
    unittest.main()
