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
    ):
        return {
            "id": item_id,
            "publisher": publisher,
            "published_at": published_at,
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

    def test_period_metrics_capture_scope_breadth_and_provenance(self):
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
        current = visibility["current_period"]
        prior = visibility["prior_period"]

        self.assertEqual(current["record_count"], 4)
        self.assertEqual(
            [metric["candidate"] for metric in current["candidate_metrics"]],
            ["Gabriel Attal", "Édouard Philippe"],
        )

        attal = current["candidate_metrics"][0]
        self.assertEqual(
            attal,
            {
                "candidate": "Gabriel Attal",
                "record_count": 3,
                "share": 0.75,
                "publisher_count": 2,
                "publisher_names": ["Le Figaro", "Le Monde"],
                "active_day_count": 2,
                "headline_match_count": 2,
                "summary_only_match_count": 1,
                "scope_counts": {
                    "election": 1,
                    "campaign": 1,
                    "general": 1,
                },
                "scope_shares": {
                    "election": 0.333,
                    "campaign": 0.333,
                    "general": 0.333,
                },
            },
        )

        philippe = current["candidate_metrics"][1]
        self.assertEqual(philippe["record_count"], 1)
        self.assertEqual(philippe["share"], 0.25)
        self.assertEqual(
            philippe["scope_counts"],
            {
                "election": 0,
                "campaign": 0,
                "general": 1,
            },
        )

        self.assertEqual(
            prior["candidate_metrics"][0]["candidate"],
            "Gabriel Attal",
        )
        self.assertEqual(
            prior["candidate_metrics"][0]["scope_counts"]["campaign"],
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
        )["current_period"]["candidate_metrics"]

        self.assertEqual(
            [metric["candidate"] for metric in metrics],
            ["Gabriel Attal", "Édouard Philippe"],
        )


if __name__ == "__main__":
    unittest.main()
