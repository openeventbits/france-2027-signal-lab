import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import build_candidate_signals as candidate_signals_builder
from candidate_candidacy_status import (
    project_active_monitoring_field,
    project_display_tiers,
)
from test_build_candidate_signals import candidate_signals_news_fixture

from fetch_news_wire import (
    CANDIDATE_COVERAGE_SCOPES,
    build_candidate_visibility,
    classify_candidate_coverage_scope,
    classify_notable_development,
    classify_relevant_news,
    classify_structured_electoral_support,
    explicit_election_match,
    match_news_candidates,
    normalize,
    validate_candidate_visibility,
)


ROOT = Path(__file__).resolve().parent


class CandidateCoverageScopeTests(unittest.TestCase):
    def test_scope_vocabulary_is_locked(self) -> None:
        self.assertEqual(
            CANDIDATE_COVERAGE_SCOPES,
            ("election", "campaign", "general"),
        )

    def test_current_election_headline_has_election_scope(self) -> None:
        scope = classify_candidate_coverage_scope(
            is_election_news=True,
            relevance={
                "reason": "explicit_election",
                "matched_terms": ["explicit_election"],
            },
            development={
                "id": "candidacies_endorsements",
                "label": "Candidacies and endorsements",
                "matched_terms": ["candidature"],
            },
        )

        self.assertEqual(scope, "election")

    def test_other_relevant_race_coverage_has_campaign_scope(self) -> None:
        scope = classify_candidate_coverage_scope(
            is_election_news=False,
            relevance={
                "reason": "candidate_campaign_context",
                "matched_terms": ["campagne"],
            },
            development=None,
        )

        self.assertEqual(scope, "campaign")

    def test_concrete_campaign_development_has_campaign_scope(self) -> None:
        scope = classify_candidate_coverage_scope(
            is_election_news=False,
            relevance=None,
            development={
                "id": "selection_strategy",
                "label": "Selection strategy",
                "matched_terms": ["primaire"],
            },
        )

        self.assertEqual(scope, "campaign")

    def test_nice_matin_support_visibility_has_general_scope(self) -> None:
        headline = normalize(
            "« Ces maisons détruites, ces animaux morts, ça fait forcément "
            "penser à des scènes de guerre » : président des maires de "
            "France, David Lisnard est allé au soutien des communes "
            "incendiées dans le Var"
        )
        matches = match_news_candidates(
            headline,
            headline,
            ["David Lisnard"],
        )
        relevance = classify_relevant_news(
            headline,
            headline,
            ["David Lisnard"],
            matches,
        )

        self.assertIsNone(relevance)
        self.assertTrue(matches)
        self.assertEqual(
            classify_candidate_coverage_scope(
                is_election_news=False,
                relevance=relevance,
                development=None,
            ),
            "general",
        )

    def test_electoral_support_visibility_keeps_campaign_scope(self) -> None:
        headline = normalize(
            "François Hollande annonce son soutien à la candidature présidentielle de "
            "Raphaël Glucksmann"
        )
        candidates = ["François Hollande", "Raphaël Glucksmann"]
        matches = match_news_candidates(headline, "", candidates)
        relevance = classify_relevant_news(
            headline,
            "",
            candidates,
            matches,
        )

        self.assertIsNotNone(relevance)
        self.assertEqual(
            classify_candidate_coverage_scope(
                is_election_news=False,
                relevance=relevance,
                development=None,
            ),
            "campaign",
        )

    def test_later_electoral_context_does_not_create_support_scope(self) -> None:
        cases = [
            ("Marine Le Pen soutient les agriculteurs à l’approche de la présidentielle", ["Marine Le Pen"]),
            ("David Lisnard apporte son soutien aux communes pendant la campagne présidentielle", ["David Lisnard"]),
            ("Édouard Philippe soutient une réforme pour l’élection présidentielle", ["Édouard Philippe"]),
            ("X soutient les victimes avant le second tour", ["X"]),
            ("X se rallie aux agriculteurs avant la présidentielle", ["X"]),
            ("X appelle à voter pour une réforme à la présidentielle", ["X"]),
            ("X apporte son soutien à une campagne de vaccination", ["X"]),
            ("X apporte son appui à une campagne associative avant l’élection", ["X"]),
            ("X soutient une coalition humanitaire pendant la présidentielle", ["X"]),
        ]

        for headline, candidates in cases:
            normalized = normalize(headline)
            matches = match_news_candidates(normalized, "", candidates)
            evidence = classify_structured_electoral_support(
                normalized,
                candidates,
            )
            relevance = classify_relevant_news(
                normalized,
                "",
                candidates,
                matches,
            )
            development = classify_notable_development(
                normalized,
                candidates,
                {"politics_specific": True},
                normalized,
                matches,
            )
            scope = classify_candidate_coverage_scope(
                is_election_news=explicit_election_match(normalized),
                relevance=relevance,
                development=development,
            )

            with self.subTest(headline=headline):
                self.assertEqual(evidence["matched_terms"], [])
                self.assertIsNone(relevance)
                self.assertIsNone(development)
                self.assertNotEqual(scope, "campaign")

    def test_routine_candidate_visibility_has_general_scope(self) -> None:
        scope = classify_candidate_coverage_scope(
            is_election_news=False,
            relevance=None,
            development=None,
        )

        self.assertEqual(scope, "general")

    def test_candidate_identity_does_not_create_race_scope(self) -> None:
        cases = [
            "Gérald Darmanin ouvre une enquête sur les défaillances dans l'affaire Lyhanna",
            "Gérald Darmanin fait le point sur les menaces contre le maire d'Alès",
            "Gérald Darmanin présente sa réforme des tribunaux pour mineurs",
            "Gérald Darmanin détaille son plan contre le narcotrafic et la surpopulation carcérale",
            "Gérald Darmanin annonce une nouvelle mesure du ministère de la Justice",
            "Entretien avec Gérald Darmanin sur la surpopulation carcérale",
            "Portrait de Marine Le Pen",
            "Édouard Philippe analyse la situation politique française",
            "Visé par une enquête, Édouard Philippe échoue à faire annuler le statut de la lanceuse d'alerte",
            "Jérôme Karsenti : Marine Le Pen a bafoué les principes démocratiques",
            "Marine Le Pen réagit à l'élection présidentielle américaine",
            "Réduction du nombre de parlementaires : Gabriel Attal reprend une promesse de campagne de 2017",
            "Pour son anniversaire, les proches de François Hollande lui offrent une campagne d'affichage",
            "Jordan Bardella seul candidat à sa réélection à la tête du Rassemblement national",
            "Sur l'immigration, la stratégie de François Ruffin est marginale en France",
            "Raphaël Glucksmann visé par une campagne de désinformation russe",
            "Gérald Darmanin annonce deux nouvelles prisons en 2027",
            "Marine Tondelier dénonce la pénurie de lunettes pour l'éclipse solaire",
            "Marine Tondelier critiquée par la droite pendant la canicule",
            "Marine Le Pen candidate au Sénat",
            "François Hollande revient sur la présidentielle de 2012",
        ]
        candidates = [
            "Gérald Darmanin",
            "Gabriel Attal",
            "François Hollande",
            "François Ruffin",
            "Jordan Bardella",
            "Marine Le Pen",
            "Raphaël Glucksmann",
            "Marine Tondelier",
            "Édouard Philippe",
        ]

        for headline_value in cases:
            headline = normalize(headline_value)
            matches = match_news_candidates(headline, "", candidates)
            matched_candidates = [
                match["candidate"] for match in matches
            ]
            relevance = classify_relevant_news(
                headline,
                "",
                matched_candidates,
                matches,
            )
            development = classify_notable_development(
                headline,
                matched_candidates,
                {"politics_specific": True},
                headline,
                matches,
            )

            with self.subTest(headline=headline_value):
                self.assertTrue(matches)
                self.assertIsNone(relevance)
                self.assertIsNone(development)
                self.assertEqual(
                    classify_candidate_coverage_scope(
                        is_election_news=False,
                        relevance=relevance,
                        development=development,
                    ),
                    "general",
                )

    def test_melenchon_boundary_probes_lock_general_campaign_election(self) -> None:
        headline = "Attal critique la politique économique de Mélenchon"
        candidates = ["Gabriel Attal", "Jean-Luc Mélenchon"]
        cases = [
            (
                headline,
                "Les deux responsables politiques pourraient être candidats "
                "en 2027.",
                "general",
            ),
            (
                headline,
                "Les deux candidats à la présidentielle de 2027 "
                "s'opposent sur la dette.",
                "campaign",
            ),
            (
                "Présidentielle 2027 : Attal attaque Mélenchon sur la dette",
                "",
                "election",
            ),
        ]

        for headline_value, summary, expected_scope in cases:
            relevance = classify_relevant_news(
                headline_value,
                summary,
                candidates,
            )
            scope = classify_candidate_coverage_scope(
                is_election_news=explicit_election_match(
                    normalize(headline_value)
                ),
                relevance=relevance,
                development=None,
            )
            with self.subTest(expected_scope=expected_scope):
                self.assertEqual(scope, expected_scope)

    def test_true_presidential_evidence_remains_race_qualified(self) -> None:
        cases = [
            "Présidentielle 2027 : Gabriel Attal annonce sa candidature",
            "Gérald Darmanin dit envisager une candidature en 2027",
            "Marine Le Pen se retire de la course à l'Élysée",
            "Le parti désigne Gabriel Attal comme candidat à la présidentielle",
            "Marine Le Pen remporte la primaire présidentielle",
            "François Hollande soutient la candidature présidentielle de Gabriel Attal",
            "Gabriel Attal dévoile son programme présidentiel",
            "Gabriel Attal explique ce qu'il ferait sur l'immigration s'il était élu président",
            "Marine Le Pen en tête dans un nouveau sondage présidentiel",
            "Enquête sur le financement de la campagne présidentielle de Marine Le Pen",
            "Une ingérence étrangère cible la présidentielle française de 2027",
        ]
        candidates = [
            "Gabriel Attal",
            "Gérald Darmanin",
            "Marine Le Pen",
            "François Hollande",
        ]

        for headline_value in cases:
            headline = normalize(headline_value)
            matches = match_news_candidates(headline, "", candidates)
            matched_candidates = [
                match["candidate"] for match in matches
            ]
            relevance = classify_relevant_news(
                headline,
                "",
                matched_candidates,
                matches,
            )

            with self.subTest(headline=headline_value):
                self.assertIsNotNone(relevance)

    def test_eligibility_consequences_remain_campaign_developments(self) -> None:
        cases = [
            "Édouard Philippe reste éligible à la présidentielle après la décision de justice",
            "Marine Le Pen devient inéligible et ne peut plus être candidate",
        ]
        candidates = ["Édouard Philippe", "Marine Le Pen"]

        for headline_value in cases:
            headline = normalize(headline_value)
            matches = match_news_candidates(headline, "", candidates)
            matched_candidates = [
                match["candidate"] for match in matches
            ]
            development = classify_notable_development(
                headline,
                matched_candidates,
                {"politics_specific": True},
                headline,
                matches,
            )

            with self.subTest(headline=headline_value):
                self.assertIsNotNone(development)
                self.assertEqual(development["id"], "legal_eligibility")
                self.assertEqual(
                    classify_candidate_coverage_scope(
                        is_election_news=False,
                        relevance=None,
                        development=development,
                    ),
                    "campaign",
                )


class CandidateVisibilityMetricTests(unittest.TestCase):
    generated_at = datetime(
        2026,
        7,
        26,
        20,
        35,
        tzinfo=timezone.utc,
    )

    @staticmethod
    def item(
        *,
        item_id,
        candidate,
        publisher,
        published_at,
        locations,
        coverage_scope,
        headline=None,
        story_id=None,
    ):
        return {
            "id": item_id,
            "publisher": publisher,
            "published_at": published_at,
            "headline": headline or item_id,
            "story_id": story_id or item_id,
            "candidates": [candidate],
            "candidate_matches": [
                {
                    "candidate": candidate,
                    "matched_aliases": [
                        candidate.casefold()
                    ],
                    "locations": list(locations),
                }
            ],
            "coverage_scope": coverage_scope,
        }

    def test_period_metrics_partition_race_and_general_visibility(self):
        records = [
            self.item(
                item_id="attal-election",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-26T12:00:00Z",
                locations=("headline",),
                coverage_scope="election",
            ),
            self.item(
                item_id="attal-campaign",
                candidate="Gabriel Attal",
                publisher="Le Figaro",
                published_at="2026-07-25T12:00:00Z",
                locations=("summary",),
                coverage_scope="campaign",
            ),
            self.item(
                item_id="attal-general",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-25T18:00:00Z",
                locations=("headline", "summary"),
                coverage_scope="general",
            ),
            self.item(
                item_id="philippe-general",
                candidate="Édouard Philippe",
                publisher="Franceinfo",
                published_at="2026-07-24T12:00:00Z",
                locations=("headline",),
                coverage_scope="general",
            ),
            self.item(
                item_id="prior-attal",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-19T12:00:00Z",
                locations=("headline",),
                coverage_scope="campaign",
            ),
        ]

        race_records = [
            record for record in records
            if record["coverage_scope"] != "general"
        ]
        active_candidates = [
            "Gabriel Attal", "Édouard Philippe", "Gérald Darmanin"
        ]
        visibility = build_candidate_visibility(
            race_records,
            records,
            self.generated_at,
            active_candidates,
        )

        current = visibility["current_period"]
        prior = visibility["prior_period"]
        general_current = visibility[
            "general_current_period"
        ]
        general_prior = visibility[
            "general_prior_period"
        ]

        self.assertEqual(current["record_count"], 2)
        self.assertEqual(current["exposure_count"], 2)
        self.assertEqual(current["publisher_count"], 2)
        self.assertEqual(
            [
                metric["candidate"]
                for metric in current["candidate_metrics"]
            ],
            ["Gabriel Attal", "Gérald Darmanin", "Édouard Philippe"],
        )

        attal = current["candidate_metrics"][0]

        self.assertEqual(attal["record_count"], 2)
        self.assertEqual(attal["exposure_count"], 2)
        self.assertEqual(attal["share"], 1.0)
        self.assertEqual(attal["publisher_count"], 2)
        self.assertEqual(
            attal["publisher_names"],
            ["Le Figaro", "Le Monde"],
        )
        self.assertEqual(attal["story_count"], 2)
        self.assertEqual(attal["observation_state"], "observed_positive")
        darmanin = current["candidate_metrics"][1]
        self.assertEqual(darmanin["candidate"], "Gérald Darmanin")
        self.assertEqual(darmanin["exposure_count"], 0)
        self.assertEqual(darmanin["share"], 0.0)
        self.assertEqual(darmanin["observation_state"], "observed_zero")

        self.assertEqual(prior["record_count"], 1)
        self.assertEqual(
            prior["candidate_metrics"][0]["candidate"],
            "Gabriel Attal",
        )

        self.assertEqual(
            general_current["record_count"],
            2,
        )
        self.assertEqual(
            [
                metric["candidate"]
                for metric in general_current[
                    "candidate_metrics"
                ]
            ],
            [
                "Gabriel Attal",
                "Édouard Philippe",
            ],
        )
        self.assertEqual(
            general_prior["record_count"],
            0,
        )
        self.assertEqual(
            general_prior["candidate_metrics"],
            [],
        )

        self.assertEqual(
            visibility["comparison_quality"][
                "current_exposure_count"
            ],
            2,
        )
        self.assertEqual(
            visibility["comparison_quality"][
                "prior_exposure_count"
            ],
            1,
        )

        validate_candidate_visibility(
            visibility,
            race_records,
            records,
            self.generated_at,
            active_candidates,
        )

    def test_metrics_are_sorted_by_records_then_candidate_name(self):
        records = [
            self.item(
                item_id="philippe",
                candidate="Édouard Philippe",
                publisher="Franceinfo",
                published_at="2026-07-26T12:00:00Z",
                locations=("headline",),
                coverage_scope="general",
            ),
            self.item(
                item_id="attal",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-26T13:00:00Z",
                locations=("headline",),
                coverage_scope="general",
            ),
        ]

        metrics = build_candidate_visibility(
            [],
            records,
            self.generated_at,
            ["Gabriel Attal", "Édouard Philippe"],
        )["general_current_period"]["candidate_metrics"]

        self.assertEqual(
            [metric["candidate"] for metric in metrics],
            ["Gabriel Attal", "Édouard Philippe"],
        )


    def test_similar_headlines_form_a_supported_story_cluster(self):
        records = [
            self.item(
                item_id="primary-one",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-26T12:00:00Z",
                locations=("headline",),
                coverage_scope="campaign",
                headline=(
                    "Gabriel Attal propose une primaire ouverte "
                    "à droite"
                ),
                story_id="primary-story",
            ),
            self.item(
                item_id="primary-two",
                candidate="Gabriel Attal",
                publisher="Le Figaro",
                published_at="2026-07-25T12:00:00Z",
                locations=("headline",),
                coverage_scope="campaign",
                headline=(
                    "À droite, Gabriel Attal propose une "
                    "primaire ouverte"
                ),
                story_id="primary-story",
            ),
            self.item(
                item_id="factory",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-24T12:00:00Z",
                locations=("headline",),
                coverage_scope="general",
                headline="Gabriel Attal visite une usine à Lyon",
            ),
        ]

        visibility = build_candidate_visibility(
            records[:2],
            records,
            self.generated_at,
            ["Gabriel Attal"],
        )

        metric = visibility[
            "current_period"
        ]["candidate_metrics"][0]

        self.assertEqual(metric["record_count"], 2)
        self.assertEqual(metric["exposure_count"], 2)
        self.assertEqual(metric["story_count"], 1)
        self.assertEqual(metric["publisher_count"], 2)
        self.assertEqual(metric["share"], 1.0)

        general_metric = visibility[
            "general_current_period"
        ]["candidate_metrics"][0]

        self.assertEqual(general_metric["record_count"], 1)
        self.assertEqual(general_metric["publisher_count"], 1)

        validate_candidate_visibility(
            visibility,
            records[:2],
            records,
            self.generated_at,
            ["Gabriel Attal"],
        )

    def test_short_unrelated_headlines_do_not_false_cluster(self):
        records = [
            self.item(
                item_id="matignon",
                candidate="Gabriel Attal",
                publisher="Le Monde",
                published_at="2026-07-26T12:00:00Z",
                locations=("headline",),
                coverage_scope="general",
                headline="Gabriel Attal à Matignon",
            ),
            self.item(
                item_id="lyon",
                candidate="Gabriel Attal",
                publisher="Le Figaro",
                published_at="2026-07-25T12:00:00Z",
                locations=("headline",),
                coverage_scope="general",
                headline="Gabriel Attal à Lyon",
            ),
        ]

        visibility = build_candidate_visibility(
            [],
            records,
            self.generated_at,
            ["Gabriel Attal"],
        )

        self.assertEqual(
            visibility["current_period"]["record_count"],
            0,
        )
        self.assertEqual(
            visibility["current_period"]["candidate_metrics"][0][
                "observation_state"
            ],
            "unavailable",
        )

        metric = visibility[
            "general_current_period"
        ]["candidate_metrics"][0]

        self.assertEqual(metric["record_count"], 2)
        self.assertEqual(metric["publisher_count"], 2)



class ActiveFieldVisibilityScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_news = json.loads(
            (ROOT / "news_wire.json").read_text(encoding="utf-8")
        )
        cls.registry = json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8")
        )
        cls.news = candidate_signals_news_fixture(source_news, cls.registry)
        cls.stored_field = project_display_tiers(cls.registry)
        cls.field = project_active_monitoring_field(cls.registry)
        cls.active = candidate_signals_builder.derive_active_field_visibility(
            cls.news,
            cls.field,
            cls.registry,
        )

    def test_source_visibility_uses_race_exposure_contract(self):
        visibility = self.news["candidate_visibility"]
        self.assertEqual(
            visibility["method"],
            "share_of_active_candidate_publisher_story_race_exposures",
        )
        self.assertEqual(visibility["authoritative_corpus"], "relevant_news")
        self.assertIn("exposure_count", visibility["current_period"])
        self.assertNotIn("share", visibility["general_current_period"])

    def test_active_union_denominators_and_publishers_are_separate(self):
        rows = self.active["race_attention"]
        projected_ids = {
            row["candidate_id"]
            for tier in ("main", "secondary")
            for row in rows[tier]
        }
        expected_ids = set(self.field["main"] + self.field["secondary"])
        self.assertEqual(projected_ids, expected_ids)
        source_current = self.news["candidate_visibility"]["current_period"]
        active_current = rows["current_period"]
        self.assertEqual(
            active_current["exposure_count"],
            source_current["exposure_count"],
        )
        self.assertEqual(
            active_current["publisher_count"],
            source_current["publisher_count"],
        )

    def test_hidden_only_evidence_remains_in_source_records(self):
        projected_ids = {
            row["candidate_id"]
            for tier in ("main", "secondary")
            for row in self.active["race_attention"][tier]
        }
        self.assertTrue(set(self.stored_field["hidden"]).isdisjoint(projected_ids))
        self.assertTrue(all(
            row["current_observation_state"]
            in {"observed_positive", "observed_zero", "unavailable"}
            for tier in ("main", "secondary")
            for row in self.active["race_attention"][tier]
        ))

if __name__ == "__main__":
    unittest.main()
