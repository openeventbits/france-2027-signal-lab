import copy
import json
import unittest
from pathlib import Path

import build_candidate_signals as signals
import fetch_news_wire as news_wire
from candidate_candidacy_status import (
    active_candidate_names,
    validate_candidate_candidacy_status,
)
from candidate_identity import candidate_id
from test_build_candidate_signals import (
    claims_fixture,
    news_fixture,
    poll_event,
    visibility_metric,
)


ROOT = Path(__file__).resolve().parent
DYNAMIC_FIXTURE = (
    ROOT / "test_fixtures" / "candidate_candidacy_status_dynamic.json"
)


class PhaseTwoFixtureMixin:
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(DYNAMIC_FIXTURE.read_text(encoding="utf-8"))
        validate_candidate_candidacy_status(cls.registry)
        cls.active_names = [
            candidate["candidate_name"]
            for candidate in cls.registry["candidates"]
            if candidate["display_tier"] in {"main", "secondary"}
        ]
        cls.polls = [
            poll_event(
                candidates=[
                    ("Alice Observ\u00e9e", 60),
                    ("Personne Hors Registre", 40),
                ]
            )
        ]
        cls.news = news_fixture(
            primary_metrics=[visibility_metric("Alice Observ\u00e9e", "primary")],
            general_metrics=[],
            candidate_watch=[],
            roster_names=cls.active_names,
        )
        cls.claims = claims_fixture(reviews=[])
        cls.payload = signals.build_candidate_signals(
            cls.polls,
            cls.news,
            cls.claims,
            cls.registry,
        )


class NewsRegistryRosterTests(PhaseTwoFixtureMixin, unittest.TestCase):
    def test_active_roster_comes_only_from_registry(self):
        roster = news_wire.active_news_candidate_roster(self.registry)
        self.assertEqual(roster, self.active_names)
        self.assertIn("Alice Observ\u00e9e", roster)
        self.assertIn("Beno\u00eet Non Test\u00e9", roster)
        self.assertIn("Chlo\u00e9 Potentielle", roster)
        self.assertNotIn("David Retir\u00e9", roster)
        self.assertNotIn("\u00c9lise D\u00e9clin\u00e9e", roster)
        self.assertNotIn("Personne Hors Registre", roster)

    def test_discovery_queries_receive_registry_active_roster(self):
        queries = news_wire.generate_discovery_queries(self.active_names, group_size=2)
        candidate_queries = [item for item in queries if item["kind"] == "candidate"]
        combined = " ".join(item["query"] for item in candidate_queries)
        for name in self.active_names:
            self.assertIn(f'"{name}"', combined)
        self.assertNotIn("Personne Hors Registre", combined)

    def test_matching_recognizes_unpolled_registry_candidate(self):
        matches = news_wire.match_news_candidates(
            "Beno\u00eet Non Test\u00e9 lance sa campagne pr\u00e9sidentielle",
            "",
            self.active_names,
        )
        self.assertEqual([match["candidate"] for match in matches], ["Beno\u00eet Non Test\u00e9"])

    def test_metadata_reports_registry_source_and_status_date(self):
        metadata = news_wire.candidate_roster_metadata(self.registry)
        self.assertEqual(metadata["source"], "candidate_candidacy_status.json")
        self.assertEqual(metadata["status_as_of"], "2026-08-01")
        self.assertEqual(metadata["count"], 3)
        self.assertEqual(metadata["names"], self.active_names)
        self.assertNotIn("cutoff_date", metadata)
        self.assertEqual(metadata["rule"], "active_monitoring_field")

    def test_poll_window_changes_cannot_change_membership(self):
        before = news_wire.active_news_candidate_roster(self.registry)
        unrelated_polls = [
            poll_event(
                fieldwork_start="2020-01-01",
                fieldwork_end="2020-01-02",
                candidates=[
                    ("Personne Hors Registre", 70),
                    ("Autre Personne", 30),
                ],
            )
        ]
        self.assertEqual(len(unrelated_polls), 1)
        after = news_wire.active_news_candidate_roster(self.registry)
        self.assertEqual(before, after)

    def test_dynamic_roster_and_identity_order_are_preserved(self):
        changed = copy.deepcopy(self.registry)
        changed["candidates"] = changed["candidates"][:2]
        validate_candidate_candidacy_status(changed)
        self.assertEqual(
            news_wire.active_news_candidate_roster(changed),
            ["Alice Observ\u00e9e", "Beno\u00eet Non Test\u00e9"],
        )
        self.assertEqual(candidate_id("Beno\u00eet Non Test\u00e9"), "benoit-non-teste")


class CandidateSignalsRegistryTests(PhaseTwoFixtureMixin, unittest.TestCase):
    def test_complete_candidate_universe_comes_from_registry(self):
        expected = [
            (candidate["candidate_id"], candidate["candidate_name"])
            for candidate in self.registry["candidates"]
        ]
        actual = [
            (candidate["candidate_id"], candidate["candidate_name"])
            for candidate in self.payload["candidates"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(self.payload["candidate_universe"]["count"], 5)
        self.assertNotIn("personne-hors-registre", {row[0] for row in actual})

    def test_unpolled_and_hidden_candidates_survive_without_fake_zero(self):
        by_name = {
            candidate["candidate_name"]: candidate
            for candidate in self.payload["candidates"]
        }
        for name in (
            "Beno\u00eet Non Test\u00e9",
            "Chlo\u00e9 Potentielle",
            "David Retir\u00e9",
            "\u00c9lise D\u00e9clin\u00e9e",
        ):
            polling = by_name[name]["polling"]
            self.assertEqual(polling["evidence_state"], "not_observed")
            self.assertTrue(
                all(
                    value is None
                    for key, value in polling.items()
                    if key != "evidence_state"
                )
            )
        self.assertEqual(by_name["Alice Observ\u00e9e"]["polling"]["evidence_state"], "reported")

    def test_featured_board_remains_selected_poll_derived(self):
        board_names = [
            row["candidate_name"]
            for row in self.payload["featured_poll_board"]["candidates"]
        ]
        self.assertEqual(board_names, ["Alice Observ\u00e9e", "Personne Hors Registre"])
        self.assertNotIn("Beno\u00eet Non Test\u00e9", board_names)
        self.assertEqual(self.payload["featured_poll_board"]["full_candidate_count"], 2)

    def test_candidates_without_news_claims_or_watch_records_survive(self):
        by_name = {
            candidate["candidate_name"]: candidate
            for candidate in self.payload["candidates"]
        }
        candidate = by_name["Chlo\u00e9 Potentielle"]
        self.assertEqual(
            candidate["campaign_attention"]["observation_state"],
            "observed_zero",
        )
        self.assertEqual(candidate["campaign_attention"]["exposure_count"], 0)
        self.assertEqual(candidate["campaign_attention"]["share"], 0.0)
        self.assertEqual(candidate["general_visibility"]["evidence_state"], "not_observed")
        self.assertEqual(candidate["scrutiny"]["latest_14_days"]["review_count"], 0)
        self.assertEqual(candidate["scrutiny"]["archive"]["review_count"], 0)
        self.assertEqual(candidate["latest_development"]["evidence_state"], "none")

    def test_dynamic_field_counts_and_hidden_visibility_exclusion(self):
        field = self.payload["presidential_field"]
        self.assertEqual(
            field["counts"],
            {"main": 2, "secondary": 1, "hidden": 2, "total": 5},
        )
        self.assertEqual(
            self.payload["active_monitoring_field"]["counts"],
            {"main": 2, "secondary": 1, "active": 3},
        )
        active_ids = set()
        for tier in ("main", "secondary"):
            active_ids.update(
                row["candidate_id"]
                for row in self.payload["active_field_visibility"][
                    "race_attention"
                ][tier]
            )
        self.assertEqual(active_ids, {"alice-observee", "benoit-non-teste", "chloe-potentielle"})
        self.assertTrue(set(field["hidden"]).isdisjoint(active_ids))

    def test_registry_status_metadata_propagates(self):
        self.assertEqual(
            self.payload["candidate_universe"],
            {
                "source": "candidate_candidacy_status.json",
                "rule": signals.CANDIDATE_UNIVERSE_RULE,
                "status_as_of": "2026-08-01",
                "count": 5,
            },
        )
        by_id = {row["candidate_id"]: row for row in self.payload["candidates"]}
        self.assertEqual(by_id["david-retire"]["candidacy"]["status"], "withdrawn")
        self.assertEqual(by_id["elise-declinee"]["candidacy"]["display_tier"], "hidden")

    def test_dynamic_total_above_twenty_validates(self):
        registry = dynamic_registry(25)
        polls = [
            poll_event(
                candidates=[
                    ("Dynamic Candidate 01", 60),
                    ("Poll Only Person", 40),
                ]
            )
        ]
        empty_news = news_fixture(
            primary_metrics=[],
            general_metrics=[],
            candidate_watch=[],
            roster_names=active_candidate_names(registry),
        )
        empty_claims = claims_fixture(reviews=[])
        payload = signals.build_candidate_signals(
            polls,
            empty_news,
            empty_claims,
            registry,
        )
        signals.validate_candidate_signals(
            payload,
            polls=polls,
            news=empty_news,
            claims=empty_claims,
            candidacy_status=registry,
        )
        self.assertEqual(len(payload["candidates"]), 25)
        self.assertEqual(payload["presidential_field"]["counts"]["total"], 25)
        self.assertEqual(
            payload["active_monitoring_field"]["counts"]["active"],
            payload["active_monitoring_field"]["counts"]["main"]
            + payload["active_monitoring_field"]["counts"]["secondary"],
        )


def dynamic_registry(count):
    statuses = (
        ("declared", "main"),
        ("primary_contender", "main"),
        ("active_potential", "secondary"),
        ("withdrawn", "hidden"),
        ("ruled_out", "hidden"),
    )
    candidates = []
    for index in range(1, count + 1):
        name = f"Dynamic Candidate {index:02d}"
        status, tier = statuses[(index - 1) % len(statuses)]
        candidates.append(
            {
                "candidate_id": candidate_id(name),
                "candidate_name": name,
                "status": status,
                "display_tier": tier,
                "status_as_of": "2026-08-01",
                "source_date": "2026-08-01",
                "source_url": "https://fr.wikipedia.org/w/index.php?oldid=1",
                "source_title": "\u00c9lection pr\u00e9sidentielle fran\u00e7aise de 2027",
                "source_publisher": "French Wikipedia",
                "status_note": "Controlled candidacy fixture entry.",
            }
        )
    candidates.sort(key=lambda row: (row["candidate_name"].casefold(), row["candidate_id"]))
    payload = {
        "schema_version": "1.0",
        "status_as_of": "2026-08-01",
        "candidates": candidates,
    }
    validate_candidate_candidacy_status(payload)
    return payload


if __name__ == "__main__":
    unittest.main()
