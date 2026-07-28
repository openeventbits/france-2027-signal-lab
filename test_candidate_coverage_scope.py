import unittest
from datetime import datetime, timezone

from fetch_news_wire import (
    CANDIDATE_COVERAGE_SCOPES,
    build_candidate_visibility,
    classify_candidate_coverage_scope,
    validate_candidate_visibility,
)


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


if __name__ == "__main__":
    unittest.main()
