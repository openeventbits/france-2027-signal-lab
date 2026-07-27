import unittest

from fetch_news_wire import (
    CANDIDATE_COVERAGE_SCOPES,
    classify_candidate_coverage_scope,
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


if __name__ == "__main__":
    unittest.main()
