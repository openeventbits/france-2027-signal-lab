import copy
import unittest
from datetime import datetime, timezone

from fetch_news_wire import (
    POLICY_AGENDA_TOPICS,
    build_policy_agenda,
    build_policy_analysis_input,
    classify_policy_agenda,
    validate_policy_agenda,
)


class PolicyAgendaTests(unittest.TestCase):
    @staticmethod
    def item(
        item_id,
        headline,
        *,
        summary="",
        publisher="Le Monde",
        published_at="2026-08-19T12:00:00Z",
        candidates=None,
    ):
        return {
            "id": item_id,
            "publisher": publisher,
            "published_at": published_at,
            "headline": headline,
            "summary": summary,
            "url": f"https://example.test/{item_id}",
            "candidates": candidates or [],
            "explicit_election": True,
        }

    def test_taxonomy_has_eight_stable_roots(self):
        self.assertEqual(
            len(POLICY_AGENDA_TOPICS),
            8,
        )

        self.assertEqual(
            [topic["id"] for topic in POLICY_AGENDA_TOPICS],
            [
                "economy_public_finances",
                "work_purchasing_power_pensions",
                "immigration_identity_secularism",
                "security_justice",
                "health_education_public_services",
                "climate_energy_agriculture",
                "europe_defence_foreign_affairs",
                "institutions_democracy_territories",
            ],
        )

    def test_classifier_is_multilabel(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 : "
                "retraites, pouvoir d'achat et "
                "déficit public au cœur du débat"
            )
        )

        self.assertEqual(
            [item["id"] for item in classifications],
            [
                "economy_public_finances",
                "work_purchasing_power_pensions",
            ],
        )

        economy = classifications[0]
        work = classifications[1]

        self.assertIn(
            "deficit public",
            economy["matched_terms"],
        )
        self.assertIn(
            "deficit_debt",
            economy["subtopics"],
        )
        self.assertIn(
            "pensions",
            work["subtopics"],
        )
        self.assertIn(
            "purchasing_power",
            work["subtopics"],
        )

    def test_summary_can_supply_policy_context(self):
        classifications = classify_policy_agenda(
            "Présidentielle 2027 : les candidats détaillent leurs priorités",
            (
                "Le débat porte sur le nucléaire, "
                "les énergies renouvelables et "
                "l'agriculture."
            ),
        )

        self.assertEqual(
            [item["id"] for item in classifications],
            [
                "climate_energy_agriculture",
            ],
        )

        self.assertIn(
            "energy",
            classifications[0]["subtopics"],
        )
        self.assertIn(
            "agriculture",
            classifications[0]["subtopics"],
        )

    def test_unique_classified_count_differs_from_assignments(self):
        items = [
            self.item(
                "multi",
                (
                    "Présidentielle 2027 : "
                    "déficit public, retraites "
                    "et pouvoir d'achat"
                ),
                candidates=["Candidate A"],
            ),
            self.item(
                "health",
                (
                    "Présidentielle 2027 : "
                    "hôpital, médecins et santé"
                ),
                publisher="Le Figaro",
                candidates=["Candidate B"],
            ),
            self.item(
                "race-only",
                (
                    "Présidentielle 2027 : "
                    "qui prendra la tête de la course ?"
                ),
                publisher="Franceinfo",
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            agenda["input_item_count"],
            3,
        )
        self.assertEqual(
            agenda["classified_item_count"],
            2,
        )
        self.assertEqual(
            agenda["unclassified_item_count"],
            1,
        )
        self.assertEqual(
            agenda["label_assignment_count"],
            3,
        )

    def test_source_day_recurrence_deduplicates_same_publisher_day(self):
        items = [
            self.item(
                "budget-1",
                "Présidentielle 2027 : débat sur le budget",
                publisher="Le Monde",
                published_at="2026-08-19T08:00:00Z",
            ),
            self.item(
                "budget-2",
                "Présidentielle 2027 : le déficit public en débat",
                publisher="Le Monde",
                published_at="2026-08-19T18:00:00Z",
            ),
            self.item(
                "budget-3",
                "Présidentielle 2027 : dette publique et budget",
                publisher="Le Figaro",
                published_at="2026-08-19T19:00:00Z",
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        topic = agenda["topics"][0]

        self.assertEqual(
            topic["id"],
            "economy_public_finances",
        )
        self.assertEqual(
            topic["item_count"],
            3,
        )
        self.assertEqual(
            topic["source_day_count"],
            2,
        )
        self.assertEqual(
            topic["publisher_count"],
            2,
        )

    def test_subtopics_and_candidate_associations_are_topic_local(self):
        items = [
            self.item(
                "econ-a",
                (
                    "Présidentielle 2027 : "
                    "budget et fiscalité"
                ),
                publisher="Le Monde",
                candidates=["Candidate A"],
            ),
            self.item(
                "econ-b",
                (
                    "Présidentielle 2027 : "
                    "dette publique et impôts"
                ),
                publisher="Le Figaro",
                candidates=[
                    "Candidate A",
                    "Candidate B",
                ],
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        topic = agenda["topics"][0]

        subtopics = {
            item["id"]: item["item_count"]
            for item in topic["subtopic_counts"]
        }

        candidates = {
            item["candidate"]: item["item_count"]
            for item in topic["candidate_counts"]
        }

        self.assertEqual(
            subtopics["budget"],
            1,
        )
        self.assertEqual(
            subtopics["deficit_debt"],
            1,
        )
        self.assertEqual(
            subtopics["taxation"],
            2,
        )

        self.assertEqual(
            candidates,
            {
                "Candidate A": 2,
                "Candidate B": 1,
            },
        )

    def test_incidence_uses_all_accepted_source_days_as_denominator(self):
        items = [
            self.item(
                "econ",
                "Présidentielle 2027 : débat sur le budget",
                publisher="Le Monde",
                published_at="2026-08-19T08:00:00Z",
            ),
            self.item(
                "health",
                "Présidentielle 2027 : débat sur la santé",
                publisher="Le Figaro",
                published_at="2026-08-19T09:00:00Z",
            ),
            self.item(
                "race",
                "Présidentielle 2027 : état de la course",
                publisher="Franceinfo",
                published_at="2026-08-19T10:00:00Z",
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        economy = next(
            topic
            for topic in agenda["evolution"]["topics"]
            if topic["id"] == "economy_public_finances"
        )

        self.assertEqual(
            economy["latest_source_day_count"],
            1,
        )

        self.assertAlmostEqual(
            economy["latest_incidence"],
            1 / 3,
            places=6,
        )

        self.assertAlmostEqual(
            economy["incidence_change_pp"],
            33.333,
            places=3,
        )

    def test_current_partial_day_is_excluded_from_week_comparison(self):
        items = [
            self.item(
                "today-budget",
                "Présidentielle 2027 : budget et déficit public",
                publisher="Le Monde",
                published_at="2026-08-20T08:00:00Z",
            ),
            self.item(
                "yesterday-health",
                "Présidentielle 2027 : santé et hôpital",
                publisher="Le Figaro",
                published_at="2026-08-19T08:00:00Z",
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        economy = next(
            topic
            for topic in agenda["evolution"]["topics"]
            if topic["id"] == "economy_public_finances"
        )

        self.assertEqual(
            economy["source_day_count"],
            1,
        )
        self.assertEqual(
            economy["latest_source_day_count"],
            0,
        )
        self.assertEqual(
            economy["latest_incidence"],
            0.0,
        )


    def test_analysis_input_reattaches_summary_without_mutating_public_item(self):
        public_item = self.item(
            "summary-bridge",
            "Présidentielle 2027 : les priorités du candidat",
        )
        public_item.pop("summary")

        inventory_item = {
            "id": "summary-bridge",
            "summary": (
                "Le candidat détaille sa politique "
                "nucléaire et agricole."
            ),
        }

        enriched = build_policy_analysis_input(
            [public_item],
            [inventory_item],
        )

        self.assertNotIn(
            "summary",
            public_item,
        )
        self.assertIn(
            "nucléaire",
            enriched[0]["summary"],
        )

        classifications = classify_policy_agenda(
            enriched[0]["headline"],
            enriched[0]["summary"],
        )

        self.assertEqual(
            [item["id"] for item in classifications],
            [
                "climate_energy_agriculture",
            ],
        )

    def test_validator_accepts_multilabel_contract(self):
        items = [
            self.item(
                "validated-multi",
                (
                    "Présidentielle 2027 : "
                    "déficit public, retraites "
                    "et pouvoir d'achat"
                ),
                publisher="Le Monde",
            ),
            self.item(
                "validated-health",
                (
                    "Présidentielle 2027 : "
                    "santé et hôpital"
                ),
                publisher="Le Figaro",
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        validate_policy_agenda(
            agenda,
            items,
        )

    def test_validator_rejects_assignment_corruption(self):
        items = [
            self.item(
                "assignment",
                (
                    "Présidentielle 2027 : "
                    "budget et retraites"
                ),
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        invalid = copy.deepcopy(
            agenda
        )
        invalid[
            "label_assignment_count"
        ] += 1

        with self.assertRaises(
            RuntimeError
        ):
            validate_policy_agenda(
                invalid,
                items,
            )

    def test_validator_rejects_incidence_corruption(self):
        items = [
            self.item(
                "incidence",
                (
                    "Présidentielle 2027 : "
                    "budget et déficit public"
                ),
                published_at=(
                    "2026-08-19T12:00:00Z"
                ),
            ),
        ]

        agenda = build_policy_agenda(
            items,
            window_days=30,
            generated_at=datetime(
                2026,
                8,
                20,
                14,
                tzinfo=timezone.utc,
            ),
        )

        invalid = copy.deepcopy(
            agenda
        )

        invalid[
            "evolution"
        ][
            "topics"
        ][0][
            "latest_incidence"
        ] = 0.123456

        with self.assertRaises(
            RuntimeError
        ):
            validate_policy_agenda(
                invalid,
                items,
            )



    def test_france3_regions_brand_is_not_decentralisation(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 : "
                "Gérald Darmanin se rallie à Édouard Philippe"
            ),
            (
                "Présidentielle 2027 : "
                "Gérald Darmanin se rallie à Édouard Philippe "
                "France 3 Régions"
            ),
        )

        self.assertNotIn(
            "institutions_democracy_territories",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_public_senat_brand_is_not_parliament_policy(self):
        classifications = classify_policy_agenda(
            (
                "Procès en appel de Marine Le Pen : "
                "quels cas permettraient sa candidature ?"
            ),
            (
                "Procès en appel de Marine Le Pen : "
                "quels cas permettraient sa candidature ? "
                "Public Sénat"
            ),
        )

        self.assertNotIn(
            "institutions_democracy_territories",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_political_summer_university_is_not_education_policy(self):
        classifications = classify_policy_agenda(
            (
                "Les universités d'été des partis de gauche, "
                "une rentrée politique avant la présidentielle"
            )
        )

        self.assertNotIn(
            "health_education_public_services",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_candidate_personal_health_is_not_healthcare_policy(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 : Édouard Philippe "
                "visé par une fake-news sur sa santé"
            )
        )

        self.assertNotIn(
            "health_education_public_services",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_securite_civile_is_not_security_justice(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 : les candidats "
                "présentent leurs propositions contre les feux"
            ),
            (
                "Ils demandent notamment un Beauvau "
                "de la sécurité civile."
            ),
        )

        self.assertNotIn(
            "security_justice",
            {
                item["id"]
                for item in classifications
            },
        )



    def test_generic_school_reference_is_not_education_policy(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 et ingérences russes : "
                "l'école, premier rempart de la démocratie "
                "face aux deepfakes"
            )
        )

        self.assertNotIn(
            "health_education_public_services",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_personal_health_rumour_is_not_health_policy(self):
        classifications = classify_policy_agenda(
            (
                "Rumeur sur la santé d'Édouard Philippe : "
                "une opération de désinformation russe "
                "vise le candidat"
            )
        )

        self.assertNotIn(
            "health_education_public_services",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_personal_health_disinformation_is_not_health_policy(self):
        classifications = classify_policy_agenda(
            (
                "Édouard Philippe visé par une campagne "
                "de désinformation russe évoquant sa santé"
            )
        )

        self.assertNotIn(
            "health_education_public_services",
            {
                item["id"]
                for item in classifications
            },
        )

    def test_genuine_health_policy_is_classified(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 : les candidats "
                "veulent réformer le système de santé "
                "et renforcer les hôpitaux"
            )
        )

        ids = {
            item["id"]
            for item in classifications
        }

        self.assertIn(
            "health_education_public_services",
            ids,
        )

        topic = next(
            item
            for item in classifications
            if item["id"]
            == "health_education_public_services"
        )

        self.assertIn(
            "health",
            topic["subtopics"],
        )

    def test_genuine_education_policy_is_classified(self):
        classifications = classify_policy_agenda(
            (
                "Présidentielle 2027 : réforme de "
                "l'Éducation nationale, enseignants "
                "et programmes scolaires au débat"
            )
        )

        ids = {
            item["id"]
            for item in classifications
        }

        self.assertIn(
            "health_education_public_services",
            ids,
        )

        topic = next(
            item
            for item in classifications
            if item["id"]
            == "health_education_public_services"
        )

        self.assertIn(
            "education",
            topic["subtopics"],
        )



if __name__ == "__main__":
    unittest.main()
