import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import build_candidate_signals as candidate_signals_builder

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
            "François Hollande annonce son soutien à la candidature de "
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
    ):
        return {
            "id": item_id,
            "publisher": publisher,
            "published_at": published_at,
            "headline": headline or item_id,
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

        visibility = build_candidate_visibility(
            records,
            self.generated_at,
        )

        self.assertEqual(
            visibility["primary_scopes"],
            ["election", "campaign"],
        )
        self.assertEqual(
            visibility["secondary_scope"],
            "general",
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
        self.assertEqual(current["publisher_count"], 2)
        self.assertEqual(
            [
                metric["candidate"]
                for metric in current["candidate_metrics"]
            ],
            ["Gabriel Attal"],
        )

        attal = current["candidate_metrics"][0]

        self.assertEqual(attal["record_count"], 2)
        self.assertEqual(attal["share"], 1.0)
        self.assertEqual(attal["publisher_count"], 2)
        self.assertEqual(
            attal["publisher_names"],
            ["Le Figaro", "Le Monde"],
        )
        self.assertEqual(attal["headline_match_count"], 1)
        self.assertEqual(
            attal["summary_only_match_count"],
            1,
        )
        self.assertEqual(
            attal["scope_counts"],
            {
                "election": 1,
                "campaign": 1,
                "general": 0,
            },
        )
        self.assertEqual(
            attal["scope_shares"],
            {
                "election": 0.5,
                "campaign": 0.5,
                "general": 0.0,
            },
        )

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
            general_current["candidate_metrics"][0][
                "scope_counts"
            ],
            {
                "election": 0,
                "campaign": 0,
                "general": 1,
            },
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
                "current_record_count"
            ],
            2,
        )
        self.assertEqual(
            visibility["comparison_quality"][
                "prior_record_count"
            ],
            1,
        )

        validate_candidate_visibility(
            visibility,
            records,
            self.generated_at,
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
            records,
            self.generated_at,
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
            records,
            self.generated_at,
        )

        metric = visibility[
            "current_period"
        ]["candidate_metrics"][0]

        self.assertEqual(metric["record_count"], 2)
        self.assertEqual(metric["story_cluster_count"], 1)

        leading_story = metric["story_clusters"][0]
        self.assertEqual(leading_story["record_count"], 2)
        self.assertEqual(leading_story["publisher_count"], 2)
        self.assertEqual(
            set(leading_story["item_ids"]),
            {"primary-one", "primary-two"},
        )
        self.assertEqual(leading_story["share"], 1.0)

        concentration = metric["concentration"]
        self.assertEqual(
            concentration["leading_publisher"],
            "Le Figaro",
        )
        self.assertEqual(
            concentration["leading_publisher_record_count"],
            1,
        )
        self.assertEqual(
            concentration["leading_publisher_share"],
            0.5,
        )
        self.assertEqual(
            concentration["leading_story_record_count"],
            2,
        )
        self.assertEqual(
            concentration["leading_story_share"],
            1.0,
        )

        general_metric = visibility[
            "general_current_period"
        ]["candidate_metrics"][0]

        self.assertEqual(general_metric["record_count"], 1)
        self.assertEqual(
            general_metric["story_cluster_count"],
            1,
        )
        self.assertEqual(
            general_metric["story_clusters"][0]["item_ids"],
            ["factory"],
        )

        validate_candidate_visibility(
            visibility,
            records,
            self.generated_at,
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
            records,
            self.generated_at,
        )

        self.assertEqual(
            visibility["current_period"]["record_count"],
            0,
        )
        self.assertEqual(
            visibility["current_period"]["candidate_metrics"],
            [],
        )

        metric = visibility[
            "general_current_period"
        ]["candidate_metrics"][0]

        self.assertEqual(metric["story_cluster_count"], 2)
        self.assertEqual(
            metric["concentration"]["leading_story_share"],
            0.5,
        )



class ActiveFieldVisibilityScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        cls.registry = json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8")
        )
        cls.field = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )["presidential_field"]
        cls.active = candidate_signals_builder.derive_active_field_visibility(
            cls.news,
            cls.field,
            cls.registry,
        )

    def test_source_wide_visibility_contract_remains_unchanged(self):
        visibility = self.news["candidate_visibility"]
        specifications = {
            "current_period": {"election", "campaign"},
            "prior_period": {"election", "campaign"},
            "general_current_period": {"general"},
            "general_prior_period": {"general"},
        }
        for period_name, scopes in specifications.items():
            period = visibility[period_name]
            records = [
                record for record in self.news["candidate_watch"]
                if period["start_date"] <= record["published_at"][:10] <= period["end_date"]
                and record["coverage_scope"] in scopes
            ]
            self.assertEqual(len(records), len({record["id"] for record in records}))
            self.assertEqual(len(records), period["record_count"])
            self.assertEqual(
                len({record["publisher"] for record in records}),
                period["publisher_count"],
            )

    def test_active_union_denominators_and_publishers_are_separate(self):
        registry_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in self.registry["candidates"]
        }
        active_names = {
            registry_by_id[identifier]["candidate_name"]
            for tier in ("main", "secondary")
            for identifier in self.field[tier]
        }
        visibility = self.news["candidate_visibility"]
        specifications = (
            (
                visibility["current_period"],
                {"election", "campaign"},
                self.active["primary"]["current_period"],
            ),
            (
                visibility["prior_period"],
                {"election", "campaign"},
                self.active["primary"]["prior_period"],
            ),
            (
                visibility["general_current_period"],
                {"general"},
                self.active["general"]["current_period"],
            ),
            (
                visibility["general_prior_period"],
                {"general"},
                self.active["general"]["prior_period"],
            ),
        )
        for source_period, scopes, active_period in specifications:
            records = [
                record for record in self.news["candidate_watch"]
                if source_period["start_date"] <= record["published_at"][:10] <= source_period["end_date"]
                and record["coverage_scope"] in scopes
                and active_names & set(record["candidates"])
            ]
            self.assertEqual(
                len({record["id"] for record in records}),
                active_period["record_count"],
            )
            self.assertEqual(
                len({record["publisher"] for record in records}),
                active_period["publisher_count"],
            )
            self.assertLessEqual(
                active_period["record_count"],
                source_period["record_count"],
            )
            self.assertLessEqual(
                active_period["publisher_count"],
                source_period["publisher_count"],
            )

    def test_hidden_only_evidence_remains_in_source_records(self):
        registry_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in self.registry["candidates"]
        }
        hidden_names = {
            registry_by_id[identifier]["candidate_name"]
            for identifier in self.field["hidden"]
        }
        active_names = {
            registry_by_id[identifier]["candidate_name"]
            for tier in ("main", "secondary")
            for identifier in self.field[tier]
        }
        self.assertTrue(hidden_names)
        self.assertTrue(hidden_names.isdisjoint(active_names))
        current_start = self.news["candidate_visibility"]["current_period"]["start_date"]
        current_end = self.news["candidate_visibility"]["current_period"]["end_date"]
        scopes = (
            (
                [
                    record for record in self.news["candidate_watch"]
                    if current_start <= record["published_at"][:10] <= current_end
                    and record["coverage_scope"] in {"election", "campaign"}
                ],
                self.active["primary"]["current_period"],
            ),
            (
                [
                    record for record in self.news["candidate_watch"]
                    if current_start <= record["published_at"][:10] <= current_end
                    and record["coverage_scope"] == "general"
                ],
                self.active["general"]["current_period"],
            ),
        )
        for records, projection in scopes:
            active_records = [
                record for record in records
                if active_names & set(record["candidates"])
            ]
            hidden_only = [
                record for record in records
                if hidden_names & set(record["candidates"])
                and not active_names & set(record["candidates"])
            ]
            mixed = [
                record for record in records
                if hidden_names & set(record["candidates"])
                and active_names & set(record["candidates"])
            ]
            active_ids = {record["id"] for record in active_records}
            hidden_only_ids = {record["id"] for record in hidden_only}
            mixed_ids = {record["id"] for record in mixed}
            self.assertEqual(len(active_ids), projection["record_count"])
            self.assertTrue(hidden_only_ids.isdisjoint(active_ids))
            self.assertTrue(mixed_ids.issubset(active_ids))
            self.assertTrue(
                all(record in self.news["candidate_watch"] for record in hidden_only + mixed)
            )

if __name__ == "__main__":
    unittest.main()
