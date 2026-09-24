from __future__ import annotations

import json
import unicodedata
import unittest
from pathlib import Path

from candidate_candidacy_status import (
    active_candidate_records,
    project_active_monitoring_field,
)
from candidate_page_contract import project_candidate_page_index


ROOT = Path(__file__).resolve().parent


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).casefold()


class CandidatePageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(
            (ROOT / "candidate_candidacy_status.json").read_text(
                encoding="utf-8"
            )
        )
        cls.index = project_candidate_page_index(cls.registry)

    def test_count_is_derived_from_active_registry(self):
        active = active_candidate_records(self.registry)
        field = project_active_monitoring_field(self.registry)

        self.assertEqual(
            self.index["counts"]["active"],
            len(active),
        )
        self.assertEqual(
            self.index["counts"]["main"],
            field["counts"]["main"],
        )
        self.assertEqual(
            self.index["counts"]["secondary"],
            field["counts"]["secondary"],
        )

    def test_projected_membership_exactly_matches_active_registry(self):
        expected = {
            candidate["candidate_id"]
            for candidate in active_candidate_records(self.registry)
        }
        projected = {
            candidate["candidate_id"]
            for candidate in self.index["candidates"]
        }

        self.assertEqual(projected, expected)

        self.assertTrue(
            all(
                candidate["display_tier"] in {"main", "secondary"}
                for candidate in self.index["candidates"]
            )
        )

    def test_public_hub_order_is_alphabetical_and_deterministic(self):
        candidates = self.index["candidates"]

        current = [
            (_name_key(candidate["candidate_name"]), candidate["candidate_id"])
            for candidate in candidates
        ]

        self.assertEqual(current, sorted(current))

    def test_every_active_candidate_has_fr_and_en_routes(self):
        for candidate in self.index["candidates"]:
            candidate_id = candidate["candidate_id"]

            self.assertEqual(
                candidate["routes"]["fr"],
                f"/candidates/{candidate_id}/",
            )
            self.assertEqual(
                candidate["routes"]["en"],
                f"/en/candidates/{candidate_id}/",
            )

            self.assertEqual(
                candidate["canonical"]["fr"],
                (
                    "https://france2027.app"
                    f"/candidates/{candidate_id}/"
                ),
            )
            self.assertEqual(
                candidate["canonical"]["en"],
                (
                    "https://france2027.app"
                    f"/en/candidates/{candidate_id}/"
                ),
            )

    def test_projection_keeps_registry_provenance(self):
        provenance = self.index["provenance"]

        self.assertEqual(
            provenance["source"],
            "candidate_candidacy_status.json",
        )
        self.assertEqual(
            provenance["rule"],
            "active_monitoring_field",
        )
        self.assertEqual(
            provenance["status_as_of"],
            self.registry["status_as_of"],
        )

    def test_contract_contains_no_fixed_candidate_count(self):
        source = (
            ROOT / "candidate_page_contract.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("44", source)
        self.assertIn(
            '"active": len(records)',
            source,
        )


if __name__ == "__main__":
    unittest.main()
