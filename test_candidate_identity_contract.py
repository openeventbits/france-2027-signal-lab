import inspect
import json
import unittest
from pathlib import Path

import candidate_identity
from candidate_candidacy_status import (
    active_candidate_names,
    load_candidate_candidacy_status,
    validate_candidate_candidacy_status,
)
from fetch_news_wire import (
    active_news_candidate_roster,
    canonical_news_candidate_roster,
    candidate_names_from_matches,
    match_news_candidates,
    news_candidate_aliases,
)


class CandidateIdentityContractTests(unittest.TestCase):
    def test_poll_label_variants_collapse_to_full_identities(self):
        roster = canonical_news_candidate_roster(
            [
                "Attal",
                "Gabriel Attal",
                "de Villepin",
                "Dominique de Villepin",
                "Dupont-Aignan",
                "Nicolas Dupont-Aignan",
                "Philippe",
                "Édouard Philippe",
            ]
        )

        self.assertEqual(
            roster,
            [
                "Dominique de Villepin",
                "Gabriel Attal",
                "Nicolas Dupont-Aignan",
                "Édouard Philippe",
            ],
        )

    def test_multi_token_variants_remain_exact_news_aliases(self):
        aliases = dict(
            news_candidate_aliases(
                [
                    "de Villepin",
                    "Dominique de Villepin",
                    "Dupont-Aignan",
                    "Nicolas Dupont-Aignan",
                ]
            )
        )

        self.assertEqual(
            set(aliases),
            {
                "Dominique de Villepin",
                "Nicolas Dupont-Aignan",
            },
        )
        self.assertIn(
            "de villepin",
            aliases["Dominique de Villepin"],
        )
        self.assertIn(
            "dupont aignan",
            aliases["Nicolas Dupont-Aignan"],
        )

    def test_duplicate_roster_labels_create_one_match_per_person(self):
        matches = match_news_candidates(
            (
                "Dominique de Villepin débat avec "
                "Nicolas Dupont-Aignan"
            ),
            "",
            [
                "de Villepin",
                "Dominique de Villepin",
                "Dupont-Aignan",
                "Nicolas Dupont-Aignan",
            ],
        )

        self.assertEqual(
            candidate_names_from_matches(matches),
            [
                "Dominique de Villepin",
                "Nicolas Dupont-Aignan",
            ],
        )
        self.assertEqual(len(matches), 2)

    def test_reviewed_multi_token_short_forms_match_canonical_people(self):
        matches = match_news_candidates(
            "De Villepin rencontre Dupont-Aignan",
            "",
            [
                "de Villepin",
                "Dominique de Villepin",
                "Dupont-Aignan",
                "Nicolas Dupont-Aignan",
            ],
        )

        self.assertEqual(
            candidate_names_from_matches(matches),
            [
                "Dominique de Villepin",
                "Nicolas Dupont-Aignan",
            ],
        )

    def test_surname_only_poll_labels_do_not_become_text_aliases(self):
        aliases = dict(
            news_candidate_aliases(
                [
                    "Attal",
                    "Gabriel Attal",
                    "Philippe",
                    "Édouard Philippe",
                ]
            )
        )

        self.assertNotIn(
            "attal",
            aliases["Gabriel Attal"],
        )
        self.assertNotIn(
            "philippe",
            aliases["Édouard Philippe"],
        )

        self.assertEqual(
            match_news_candidates(
                "Attal et Philippe se rencontrent",
                "",
                [
                    "Attal",
                    "Gabriel Attal",
                    "Philippe",
                    "Édouard Philippe",
                ],
            ),
            [],
        )

    def test_active_news_roster_uses_validated_registry_identities(self):
        root = Path(__file__).resolve().parent
        registry = load_candidate_candidacy_status(
            root / "candidate_candidacy_status.json"
        )
        roster = active_news_candidate_roster(registry)
        self.assertEqual(
            roster,
            active_candidate_names(registry),
        )
        source = inspect.getsource(active_news_candidate_roster)
        self.assertIn("active_candidate_names", source)
        self.assertNotIn("poll", source.casefold())

    def test_registry_has_exact_identity_parity_with_candidate_signals(self):
        root = Path(__file__).resolve().parent
        registry = load_candidate_candidacy_status(
            root / "candidate_candidacy_status.json"
        )
        with (root / "candidate_signals.json").open(
            "r",
            encoding="utf-8",
        ) as source:
            candidate_signals = json.load(source)

        validate_candidate_candidacy_status(
            registry,
            candidate_universe=candidate_signals["candidates"],
        )
        self.assertEqual(
            [
                (candidate["candidate_id"], candidate["candidate_name"])
                for candidate in registry["candidates"]
            ],
            [
                (candidate["candidate_id"], candidate["candidate_name"])
                for candidate in candidate_signals["candidates"]
            ],
        )

    def test_candidate_identity_contains_no_candidacy_logic(self):
        source = inspect.getsource(candidate_identity).casefold()
        self.assertNotIn("candidacy", source)


if __name__ == "__main__":
    unittest.main()
