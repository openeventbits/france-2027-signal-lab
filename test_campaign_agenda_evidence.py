import copy
import unittest
from datetime import datetime, timedelta, timezone

from fetch_news_wire import (
    CAMPAIGN_AGENDA_SUPPORT_LIMIT,
    STRICT_NOTABLE_TERMS,
    build_campaign_agenda,
    classify_campaign_agenda,
    classify_notable_development,
    normalize,
    validate_campaign_agenda,
    validate_campaign_agenda_topic,
)


class CampaignAgendaEvidenceTests(unittest.TestCase):
    @staticmethod
    def item(index, published_at, publisher):
        return {
            "id": f"item-{index:02d}",
            "publisher": publisher,
            "published_at": published_at,
            "headline": (
                "Présidentielle 2027 : "
                f"annonce de candidature {index:02d}"
            ),
            "url": (
                f"https://example.test/topic/{index:02d}"
            ),
            "candidates": ["Gabriel Attal"],
            "development_category": (
                "candidacies_endorsements"
            ),
            "development_label": (
                "Candidacies and endorsements"
            ),
            "matched_terms": ["candidature"],
        }

    def build_items(self):
        anchor = datetime(
            2026,
            7,
            26,
            20,
            tzinfo=timezone.utc,
        )

        items = [
            self.item(
                index,
                (
                    anchor - timedelta(hours=index)
                ).isoformat().replace("+00:00", "Z"),
                (
                    "Le Monde"
                    if index % 2 == 0
                    else "Le Figaro"
                ),
            )
            for index in range(25)
        ]

        return items[::2] + items[1::2]

    def test_exports_twenty_items_and_reports_omissions(self):
        agenda = build_campaign_agenda(
            self.build_items(),
            window_days=30,
        )
        topic = agenda["topics"][0]

        self.assertEqual(
            agenda["input_item_count"],
            25,
        )
        self.assertEqual(
            agenda["classified_item_count"],
            25,
        )
        self.assertEqual(
            agenda["unclassified_item_count"],
            0,
        )

        self.assertEqual(
            CAMPAIGN_AGENDA_SUPPORT_LIMIT,
            20,
        )
        self.assertEqual(topic["item_count"], 25)
        self.assertEqual(
            topic["supporting_item_count"],
            20,
        )
        self.assertEqual(topic["omitted_item_count"], 5)
        self.assertEqual(
            len(topic["supporting_items"]),
            20,
        )
        self.assertEqual(
            [
                item["id"]
                for item in topic["supporting_items"]
            ],
            [
                f"item-{index:02d}"
                for index in range(20)
            ],
        )

        seen = set()
        validate_campaign_agenda_topic(
            topic,
            seen,
        )
        self.assertEqual(
            seen,
            {"candidacies_endorsements"},
        )

        validate_campaign_agenda(
            agenda,
            self.build_items(),
        )

    def test_unclassified_relevant_news_is_omitted_from_topics(self):
        item = {
            "id": "race-analysis",
            "publisher": "Example",
            "published_at": "2026-07-26T12:00:00Z",
            "headline": (
                "Présidentielle 2027 : "
                "où en est la course"
            ),
            "url": (
                "https://example.test/"
                "race-analysis"
            ),
            "candidates": [],
            "explicit_election": True,
        }

        agenda = build_campaign_agenda(
            [item],
            window_days=30,
        )

        self.assertEqual(
            agenda["input_item_count"],
            1,
        )
        self.assertEqual(
            agenda["classified_item_count"],
            0,
        )
        self.assertEqual(
            agenda["unclassified_item_count"],
            1,
        )
        self.assertEqual(
            agenda["topics"],
            [],
        )

        validate_campaign_agenda(
            agenda,
            [item],
        )

    def test_nice_matin_support_is_not_endorsement_evidence(self):
        headline = (
            "« Ces maisons détruites, ces animaux morts, ça fait forcément "
            "penser à des scènes de guerre » : président des maires de "
            "France, David Lisnard est allé au soutien des communes "
            "incendiées dans le Var"
        )
        item = {
            "id": "46d9840b9e91f688480a",
            "publisher": "Nice-Matin",
            "published_at": "2026-07-28T04:00:01Z",
            "headline": headline,
            "url": "https://example.test/nice-matin-wildfire",
            "candidates": ["David Lisnard"],
            "explicit_election": False,
        }

        self.assertIsNone(
            classify_campaign_agenda(
                normalize(headline),
                explicit_election=False,
                matched_candidates=["David Lisnard"],
            )
        )
        agenda = build_campaign_agenda([item], window_days=30)
        self.assertEqual(agenda["classified_item_count"], 0)
        self.assertEqual(agenda["unclassified_item_count"], 1)
        self.assertEqual(agenda["topics"], [])

    def test_ordinary_support_and_bare_rallying_are_not_agenda_evidence(self):
        headlines = (
            "Le candidat François Hollande apporte son soutien aux victimes",
            "Le président François Hollande soutient les agriculteurs",
            "François Hollande soutient une réforme",
            "François Hollande apporte son soutien aux pompiers",
            "François Hollande annonce un ralliement",
            "François Hollande rallie les élus à une réforme",
            "Les jeunes soutiens du candidat Édouard Philippe font escale à Arles",
            "Le soutien de David Lisnard aux pompiers",
            "Les élus soutenus par David Lisnard après l'incendie",
            "François Hollande appelle à voter pour une réforme",
            "Marine Le Pen soutient les agriculteurs à l’approche de la présidentielle",
            "David Lisnard apporte son soutien aux communes pendant la campagne présidentielle",
            "Édouard Philippe soutient une réforme pour l’élection présidentielle",
            "X soutient les victimes avant le second tour",
            "X se rallie aux agriculteurs avant la présidentielle",
            "X appelle à voter pour une réforme à la présidentielle",
            "X apporte son soutien à une campagne de vaccination",
            "X apporte son appui à une campagne associative avant l’élection",
            "X soutient une coalition humanitaire pendant la présidentielle",
        )
        for headline in headlines:
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_campaign_agenda(
                        normalize(headline),
                        matched_candidates=["François Hollande"],
                    )
                )

    def test_structured_electoral_support_is_endorsement_evidence(self):
        cases = [
            ("François Hollande annonce son soutien à la candidature de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande soutient la candidature de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le parti apporte son soutien au candidat", []),
            ("François Hollande se rallie à Raphaël Glucksmann pour la présidentielle", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande officialise son ralliement à Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande appelle à voter pour Raphaël Glucksmann au second tour", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande soutient Raphaël Glucksmann au second tour", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le soutien d'Elon Musk au RN relance la campagne de Marine Le Pen", ["Marine Le Pen"]),
            ('"Marine Le Pen est le dernier espoir de la France": le soutien d\'Elon Musk au RN provoque des accusations d\'"ingérence étrangère"', ["Marine Le Pen"]),
            ("Les élus RN de la région dieppoise au soutien de Marine Le Pen", ["Marine Le Pen"]),
            ("Le soutien de François Hollande à la candidature de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le ralliement de François Hollande à Marine Le Pen", ["François Hollande", "Marine Le Pen"]),
            ("François Hollande apporte son soutien à la campagne présidentielle de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("François Hollande apporte son soutien à la campagne de Raphaël Glucksmann", ["François Hollande", "Raphaël Glucksmann"]),
            ("Le parti apporte son soutien à la campagne du candidat", []),
        ]
        for headline, candidates in cases:
            classification = classify_campaign_agenda(
                normalize(headline),
                matched_candidates=candidates,
            )
            with self.subTest(headline=headline):
                self.assertIsNotNone(classification)
                self.assertEqual(
                    classification["id"],
                    "candidacies_endorsements",
                )

    def test_ambiguous_rules_terms_require_presidential_headline(self):
        routine = classify_campaign_agenda(
            normalize(
                "Fin de vie : le Conseil "
                "constitutionnel est saisi"
            ),
            explicit_election=False,
        )
        presidential = classify_campaign_agenda(
            normalize(
                "Présidentielle 2027 : "
                "le Conseil constitutionnel "
                "précise les règles"
            ),
            explicit_election=True,
        )

        self.assertIsNone(routine)
        self.assertIsNotNone(presidential)
        self.assertEqual(
            presidential["id"],
            "rules_calendar",
        )
        self.assertEqual(
            presidential["matched_terms"],
            ["conseil constitutionnel"],
        )

    def test_generic_departure_and_preparation_are_not_topics(self):
        headlines = (
            (
                "Olivier Girardin quitte la direction "
                "du PS aubois et se rapproche de "
                "Dominique de Villepin"
            ),
            (
                "Comment le Sénat se prépare à "
                "l'arrivée possible d'un groupe RN"
            ),
        )

        for headline in headlines:
            with self.subTest(headline=headline):
                self.assertIsNone(
                    classify_campaign_agenda(
                        normalize(headline),
                        explicit_election=False,
                    )
                )

    def test_generic_preparation_is_not_a_notable_development(self):
        headline = normalize(
            "Il faut pousser les murs : "
            "comment le Sénat se prépare à "
            "l'arrivée possible d'un groupe RN "
            "après les sénatoriales de septembre"
        )

        self.assertNotIn(
            "se prepare",
            STRICT_NOTABLE_TERMS[
                "candidacies_endorsements"
            ],
        )
        self.assertIn(
            "se prepare a entrer en campagne",
            STRICT_NOTABLE_TERMS[
                "candidacies_endorsements"
            ],
        )

        classification = classify_notable_development(
            headline,
            [],
            {},
            normalized_headline=headline,
            candidate_matches=[],
        )

        self.assertIsNone(classification)

    def test_presidential_candidate_preparation_requires_specific_evidence(self):
        classification = classify_campaign_agenda(
            normalize(
                "François Hollande se prépare "
                "discrètement à l'élection "
                "présidentielle"
            ),
            explicit_election=True,
        )

        self.assertIsNone(classification)

    def test_campaign_financing_phrase_variant_is_classified(self):
        classification = classify_campaign_agenda(
            normalize(
                "Financement de la campagne pour "
                "la présidentielle 2027 : "
                "l'État pourrait garantir un emprunt"
            ),
            explicit_election=True,
        )

        self.assertIsNotNone(classification)
        self.assertEqual(
            classification["id"],
            "rules_calendar",
        )
        self.assertEqual(
            classification["matched_terms"],
            ["financement de la campagne"],
        )

    def test_notable_development_category_is_authoritative(self):
        relevant = {
            "id": "legal-event",
            "publisher": "Example",
            "published_at": "2026-07-26T12:00:00Z",
            "headline": (
                "Marine Le Pen face à "
                "une nouvelle décision"
            ),
            "url": (
                "https://example.test/"
                "legal-event"
            ),
            "candidates": ["Marine Le Pen"],
            "explicit_election": False,
        }
        notable = {
            **relevant,
            "development_category": (
                "legal_eligibility"
            ),
            "development_label": (
                "Legal cases & eligibility"
            ),
            "matched_terms": [
                "condamnation",
            ],
        }

        agenda = build_campaign_agenda(
            [relevant],
            window_days=30,
            notable_developments=[notable],
        )

        self.assertEqual(
            agenda["classified_item_count"],
            1,
        )
        self.assertEqual(
            agenda["unclassified_item_count"],
            0,
        )
        self.assertEqual(
            agenda["topics"][0]["id"],
            "legal_eligibility",
        )
        self.assertEqual(
            agenda["topics"][0][
                "supporting_items"
            ][0]["matched_terms"],
            ["condamnation"],
        )

        validate_campaign_agenda(
            agenda,
            [relevant],
        )

    def test_smaller_topics_export_all_evidence(self):
        agenda = build_campaign_agenda(
            self.build_items()[:7],
            window_days=30,
        )
        topic = agenda["topics"][0]

        self.assertEqual(topic["item_count"], 7)
        self.assertEqual(
            topic["supporting_item_count"],
            7,
        )
        self.assertEqual(
            topic["omitted_item_count"],
            0,
        )

    def test_equal_timestamps_use_stable_tie_breakers(self):
        published_at = "2026-07-26T12:00:00Z"
        items = [
            self.item(2, published_at, "Le Monde"),
            self.item(1, published_at, "Franceinfo"),
            self.item(0, published_at, "Le Figaro"),
        ]

        topic = build_campaign_agenda(
            items,
            window_days=30,
        )["topics"][0]

        self.assertEqual(
            [
                item["publisher"]
                for item in topic["supporting_items"]
            ],
            [
                "Franceinfo",
                "Le Figaro",
                "Le Monde",
            ],
        )

    def test_agenda_validator_rejects_coverage_count_corruption(self):
        items = self.build_items()[:7]
        agenda = build_campaign_agenda(
            items,
            window_days=30,
        )

        mutations = {
            "classified": (
                lambda value: value.update(
                    classified_item_count=6
                )
            ),
            "unclassified": (
                lambda value: value.update(
                    unclassified_item_count=1
                )
            ),
            "input": (
                lambda value: value.update(
                    input_item_count=8
                )
            ),
            "catch-all": (
                lambda value: value["topics"][
                    0
                ].update(
                    id="other_campaign",
                    label=(
                        "Other campaign coverage"
                    ),
                )
            ),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(
                    agenda
                )
                mutate(invalid)

                with self.assertRaises(
                    RuntimeError
                ):
                    validate_campaign_agenda(
                        invalid,
                        items,
                    )

    def test_validator_rejects_contract_corruption(self):
        topic = build_campaign_agenda(
            self.build_items(),
            window_days=30,
        )["topics"][0]

        mutations = {
            "support count": lambda value: value.update(
                supporting_item_count=19
            ),
            "omitted count": lambda value: value.update(
                omitted_item_count=4
            ),
            "ordering": lambda value: value.update(
                supporting_items=list(
                    reversed(
                        value["supporting_items"]
                    )
                )
            ),
            "duplicate evidence": lambda value: value[
                "supporting_items"
            ].__setitem__(
                1,
                copy.deepcopy(
                    value["supporting_items"][0]
                ),
            ),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(topic)
                mutate(invalid)

                with self.assertRaises(RuntimeError):
                    validate_campaign_agenda_topic(
                        invalid,
                        set(),
                    )


if __name__ == "__main__":
    unittest.main()
