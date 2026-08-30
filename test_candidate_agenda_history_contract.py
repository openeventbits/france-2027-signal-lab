from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from candidate_agenda_history_contract import (
    CAMPAIGN_TAXONOMY,
    POLICY_TAXONOMY,
    CandidateAgendaHistoryContractError,
    validate_candidate_agenda_history,
)


ROOT = Path(__file__).resolve().parent


class CandidateAgendaHistoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (ROOT / "candidate_agenda_history.json").read_text(encoding="utf-8")
        )
        cls.registry = json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(encoding="utf-8")
        )

    def test_exact_schema_tracking_and_taxonomies(self):
        validate_candidate_agenda_history(
            self.payload, expected_candidates=self.registry["candidates"]
        )
        self.assertEqual(
            set(self.payload),
            {"schema_version", "tracking", "methodology", "taxonomies", "candidates"},
        )
        self.assertEqual(self.payload["schema_version"], "1.0")
        news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        expected_as_of = datetime.fromisoformat(
            news["generated_at"].replace("Z", "+00:00")
        ).date().isoformat()
        expected_start = (
            datetime.fromisoformat(expected_as_of).date()
            - timedelta(days=29)
        ).isoformat()
        self.assertEqual(
            self.payload["tracking"]["start_date"],
            expected_start,
        )
        self.assertEqual(self.payload["tracking"]["data_as_of"], expected_as_of)
        self.assertEqual(self.payload["tracking"]["day_boundary"], "UTC")
        self.assertIs(self.payload["tracking"]["current_utc_day_excluded"], False)
        self.assertEqual(
            [(row["id"], row["label"]) for row in self.payload["taxonomies"]["policy"]],
            [
                ("economy_public_finances", "Economy & Public Finances"),
                ("work_purchasing_power_pensions", "Work, Purchasing Power & Pensions"),
                ("immigration_identity_secularism", "Immigration, Identity & Secularism"),
                ("security_justice", "Security & Justice"),
                ("health_education_public_services", "Health, Education & Public Services"),
                ("climate_energy_agriculture", "Climate, Energy & Agriculture"),
                ("europe_defence_foreign_affairs", "Europe, Defence & Foreign Affairs"),
                ("institutions_democracy_territories", "Institutions, Democracy & Territories"),
            ],
        )
        self.assertEqual(
            [(row["id"], row["label"]) for row in self.payload["taxonomies"]["campaign"]],
            [
                ("legal_eligibility", "Legal cases & eligibility"),
                ("selection_strategy", "Primaries & party strategy"),
                ("candidacies_endorsements", "Candidacies & endorsements"),
                ("rules_calendar", "Rules, calendar & campaign mechanics"),
                ("positioning_integrity", "Positioning & political image"),
                ("polls_race", "Polling & race narratives"),
            ],
        )
        candidate = self.payload["candidates"][0]
        self.assertEqual(
            set(candidate),
            {
                "candidate_id",
                "candidate_name",
                "tracking_start",
                "daily_series",
                "cumulative_profile",
            },
        )
        self.assertEqual(
            set(candidate["daily_series"][0]),
            {"date", "policy_counts", "campaign_counts"},
        )
        self.assertEqual(
            set(candidate["cumulative_profile"]),
            {
                "profile_mode",
                "period_start",
                "period_end",
                "day_count",
                "association_count",
                "topics",
            },
        )
        self.assertEqual(
            set(candidate["cumulative_profile"]["topics"][0]),
            {"id", "label", "count", "share"},
        )

    def test_daily_series_and_full_topic_dictionaries_are_enforced(self):
        malformed = copy.deepcopy(self.payload)
        del malformed["candidates"][0]["daily_series"][0]["policy_counts"][
            POLICY_TAXONOMY[0][0]
        ]
        with self.assertRaisesRegex(
            CandidateAgendaHistoryContractError, "every canonical topic"
        ):
            validate_candidate_agenda_history(malformed)

        malformed = copy.deepcopy(self.payload)
        malformed["candidates"][0]["daily_series"][0]["campaign_counts"][
            CAMPAIGN_TAXONOMY[0][0]
        ] = -1
        with self.assertRaisesRegex(
            CandidateAgendaHistoryContractError, "non-negative integer"
        ):
            validate_candidate_agenda_history(malformed)

        malformed = copy.deepcopy(self.payload)
        malformed["candidates"][0]["daily_series"][1]["date"] = malformed[
            "candidates"
        ][0]["daily_series"][0]["date"]
        with self.assertRaisesRegex(
            CandidateAgendaHistoryContractError, "unique, ascending, and contiguous"
        ):
            validate_candidate_agenda_history(malformed)

    def test_candidate_registry_parity_is_exact(self):
        expected = copy.deepcopy(self.registry["candidates"])
        expected[0]["candidate_name"] = "Reviewed Rename"
        with self.assertRaisesRegex(
            CandidateAgendaHistoryContractError, "exactly match"
        ):
            validate_candidate_agenda_history(
                self.payload, expected_candidates=expected
            )

    def test_cumulative_profile_must_reconcile_without_mixed_taxonomies(self):
        malformed = copy.deepcopy(self.payload)
        malformed["candidates"][0]["cumulative_profile"]["topics"].append(
            {"id": POLICY_TAXONOMY[0][0], "label": POLICY_TAXONOMY[0][1], "count": 0, "share": 0.0}
        )
        with self.assertRaisesRegex(
            CandidateAgendaHistoryContractError, "selected taxonomy"
        ):
            validate_candidate_agenda_history(malformed)


if __name__ == "__main__":
    unittest.main()
