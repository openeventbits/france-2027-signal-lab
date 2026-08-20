import copy
import unittest
from pathlib import Path
from datetime import date, timedelta

from test_final_dashboard_shell import (
    agenda_evolution_payload,
    run_media_model_script,
)


def policy_payload():
    payload = copy.deepcopy(
        agenda_evolution_payload()
    )

    campaign_evolution = payload[
        "campaign_agenda"
    ]["evolution"]

    start = date.fromisoformat(
        campaign_evolution[
            "period_start"
        ]
    )

    dates = [
        (
            start +
            timedelta(days=index)
        ).isoformat()
        for index in range(30)
    ]

    base_topics = [
        {
            "id":
                "work_purchasing_power_pensions",
            "label":
                "Work, Purchasing Power & Pensions",
            "item_count": 5,
            "publisher_count": 4,
            "publisher_names": [
                "BFMTV",
                "LCP",
                "Le Monde",
                "Libération",
            ],
            "source_day_count": 5,
            "active_day_count": 5,
            "display_eligible": True,
            "subtopic_counts": [
                {
                    "id":
                        "pensions",
                    "item_count": 4,
                }
            ],
            "candidate_counts": [
                {
                    "candidate":
                        "Candidate A",
                    "item_count": 3,
                }
            ],
            "supporting_item_count": 1,
            "omitted_item_count": 4,
            "supporting_items": [
                {
                    "id":
                        "policy-work-1",
                    "publisher":
                        "Le Monde",
                    "published_at":
                        dates[-2] +
                        "T12:00:00Z",
                    "headline":
                        "Présidentielle 2027 : retraites et salaires",
                    "url":
                        "https://example.test/policy-work-1",
                    "candidates": [
                        "Candidate A"
                    ],
                    "matched_terms": [
                        "retraites"
                    ],
                    "subtopics": [
                        "pensions"
                    ],
                }
            ],
        },
        {
            "id":
                "economy_public_finances",
            "label":
                "Economy & Public Finances",
            "item_count": 4,
            "publisher_count": 3,
            "publisher_names": [
                "LCP",
                "Le Figaro",
                "Le Monde",
            ],
            "source_day_count": 4,
            "active_day_count": 4,
            "display_eligible": True,
            "subtopic_counts": [
                {
                    "id":
                        "budget",
                    "item_count": 3,
                }
            ],
            "candidate_counts": [
                {
                    "candidate":
                        "Candidate B",
                    "item_count": 2,
                }
            ],
            "supporting_item_count": 1,
            "omitted_item_count": 3,
            "supporting_items": [
                {
                    "id":
                        "policy-economy-1",
                    "publisher":
                        "Le Figaro",
                    "published_at":
                        dates[-3] +
                        "T12:00:00Z",
                    "headline":
                        "Présidentielle 2027 : budget et dette publique",
                    "url":
                        "https://example.test/policy-economy-1",
                    "candidates": [
                        "Candidate B"
                    ],
                    "matched_terms": [
                        "budget"
                    ],
                    "subtopics": [
                        "budget"
                    ],
                }
            ],
        },
    ]

    accepted_daily = [
        {
            "date": day,
            "source_day_count":
                3 if index >= 15
                else 2,
        }
        for index, day
        in enumerate(dates)
    ]

    evolution_topics = []

    schedules = [
        [17, 20, 23, 26, 28],
        [10, 16, 21, 27],
    ]

    for topic_index, base in enumerate(
        base_topics
    ):
        daily = []

        for index, day in enumerate(
            dates
        ):
            source_days = (
                1
                if index in
                schedules[topic_index]
                else 0
            )

            accepted = (
                accepted_daily[index]
                ["source_day_count"]
            )

            daily.append(
                {
                    "date": day,
                    "item_count":
                        source_days,
                    "source_day_count":
                        source_days,
                    "accepted_source_day_count":
                        accepted,
                    "incidence":
                        round(
                            source_days /
                            accepted,
                            6,
                        )
                        if accepted
                        else 0.0,
                }
            )

        latest_source_days = sum(
            day["source_day_count"]
            for day in daily[-8:-1]
        )

        previous_source_days = sum(
            day["source_day_count"]
            for day in daily[-15:-8]
        )

        latest_denominator = sum(
            day["source_day_count"]
            for day
            in accepted_daily[-8:-1]
        )

        previous_denominator = sum(
            day["source_day_count"]
            for day
            in accepted_daily[-15:-8]
        )

        latest_incidence = (
            latest_source_days /
            latest_denominator
        )

        previous_incidence = (
            previous_source_days /
            previous_denominator
        )

        evolution_topics.append(
            {
                "id": base["id"],
                "label":
                    base["label"],
                "item_count":
                    base[
                        "item_count"
                    ],
                "publisher_count":
                    base[
                        "publisher_count"
                    ],
                "source_day_count":
                    base[
                        "source_day_count"
                    ],
                "active_day_count":
                    base[
                        "active_day_count"
                    ],
                "display_eligible":
                    True,
                "latest_source_day_count":
                    latest_source_days,
                "previous_source_day_count":
                    previous_source_days,
                "latest_incidence":
                    round(
                        latest_incidence,
                        6,
                    ),
                "previous_incidence":
                    round(
                        previous_incidence,
                        6,
                    ),
                "incidence_change_pp":
                    round(
                        (
                            latest_incidence -
                            previous_incidence
                        ) * 100,
                        3,
                    ),
                "daily_activity":
                    daily,
                "matched_term_counts":
                    [],
            }
        )

    payload["policy_agenda"] = {
        "window_days": 30,
        "input_item_count": 12,
        "classified_item_count": 8,
        "unclassified_item_count": 4,
        "label_assignment_count": 9,
        "method":
            "accepted_relevant_news_by_policy_issue_multilabel",
        "display_min_source_days": 2,
        "evolution": {
            "period_days": 30,
            "period_start":
                dates[0],
            "period_end":
                dates[-1],
            "period_end_partial":
                True,
            "comparison_days": 7,
            "latest_start":
                dates[-8],
            "latest_end":
                dates[-2],
            "previous_start":
                dates[-15],
            "previous_end":
                dates[-9],
            "accepted_daily_activity":
                accepted_daily,
            "topics":
                evolution_topics,
        },
        "topics":
            base_topics,
    }

    return payload


class PolicyAgendaFrontendTests(
    unittest.TestCase
):
    def build_policy(
        self,
        payload
    ):
        return run_media_model_script(
            payload,
            """(() => {
              const model =
                api.buildPolicyAgendaViewModel();

              return {
                state:
                  model.state,
                issueCount:
                  model.topics?.length ?? 0,
                selected:
                  model.selectedIssue?.id ?? null,
                leading:
                  model.diagnostics
                    ?.leadingIssue?.id ?? null,
                incidence:
                  model.selectedIssue
                    ?.latestIncidence ?? null
              };
            })()""",
        )

    def test_valid_policy_contract_is_ready(
        self
    ):
        result = self.build_policy(
            policy_payload()
        )

        self.assertEqual(
            result["state"],
            "ready",
        )

        self.assertEqual(
            result["issueCount"],
            2,
        )

        self.assertIsNotNone(
            result["selected"]
        )

    def test_multilabel_assignment_count_is_supported(
        self
    ):
        payload = policy_payload()

        self.assertGreater(
            payload[
                "policy_agenda"
            ][
                "label_assignment_count"
            ],
            payload[
                "policy_agenda"
            ][
                "classified_item_count"
            ],
        )

        self.assertEqual(
            self.build_policy(
                payload
            )["state"],
            "ready",
        )

    def test_malformed_policy_is_isolated_from_agenda(
        self
    ):
        payload = policy_payload()

        payload[
            "policy_agenda"
        ][
            "label_assignment_count"
        ] = 999

        result = run_media_model_script(
            payload,
            """(() => {
              const agenda =
                api.buildAgendaViewModel();

              const issues =
                api.buildPolicyAgendaViewModel();

              return {
                agenda:
                  agenda.state,
                agendaReady:
                  Boolean(
                    agenda.evolutionReady
                  ),
                issues:
                  issues.state
              };
            })()""",
        )

        self.assertEqual(
            result["agenda"],
            "ready",
        )

        self.assertTrue(
            result[
                "agendaReady"
            ]
        )

        self.assertEqual(
            result["issues"],
            "invalid",
        )

    def test_missing_policy_does_not_damage_agenda(
        self
    ):
        payload = policy_payload()

        del payload[
            "policy_agenda"
        ]

        result = run_media_model_script(
            payload,
            """(() => ({
              agenda:
                api.buildAgendaViewModel()
                  .state,
              issues:
                api.buildPolicyAgendaViewModel()
                  .state
            }))()""",
        )

        self.assertEqual(
            result["agenda"],
            "ready",
        )

        self.assertEqual(
            result["issues"],
            "unavailable",
        )

    def test_issues_renderer_uses_separate_workspace_language(
        self
    ):
        result = run_media_model_script(
            policy_payload(),
            """(() => {
              const model =
                api.buildPolicyAgendaViewModel();

              const html =
                api.renderIssuesPanel(
                  model
                );

              return {
                policyMonitor:
                  html.includes(
                    "POLICY MONITOR"
                  ),
                issueEvolution:
                  html.includes(
                    "ISSUE EVOLUTION"
                  ),
                issueDossier:
                  html.includes(
                    "ISSUE DOSSIER"
                  ),
                candidateAssociations:
                  html.includes(
                    "CANDIDATE ASSOCIATIONS"
                  )
              };
            })()""",
        )

        self.assertTrue(
            result[
                "policyMonitor"
            ]
        )

        self.assertTrue(
            result[
                "issueEvolution"
            ]
        )

        self.assertTrue(
            result[
                "issueDossier"
            ]
        )

        self.assertTrue(
            result[
                "candidateAssociations"
            ]
        )


    def test_poll_compare_is_not_a_workspace(self):
        source = Path(
            "assets/hybrid-dashboard.js"
        ).read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            'pollCompare:',
            source,
        )

        self.assertNotIn(
            '#signal-poll-compare',
            source,
        )

        self.assertNotIn(
            '"POLL COMPARE"',
            source,
        )

        self.assertIn(
            'label: "ISSUES"',
            source,
        )



if __name__ == "__main__":
    unittest.main()
