import copy
import unittest

from fetch_polls import (
    SOURCE_URL,
    SECOND_ROUND,
    canonical_candidate_name,
    canonical_matchup_candidate,
    canonical_pollster_name,
    discover_first_round_tables,
    parse_wikipedia_first_round_html,
    validate_second_round_event,
)
from poll_contract import (
    PollContractError,
    apply_completeness_contract,
    make_event_id,
    make_scenario_key,
    validate_poll_event,
)


def polling_table(
    *,
    pollster="Ifop",
    dates="1–2 Jul 2026",
    sample="1,000",
    candidates=(
        ("Edouard Philippe", "30"),
        ("Eric Zemmour", "30"),
        ("Glucksmann", "40"),
    ),
):
    headers = "".join(f"<th>{name}</th>" for name, _ in candidates)
    scores = "".join(f"<td>{score}</td>" for _, score in candidates)
    return f"""
      <table class="wikitable">
        <thead><tr>
          <th>Polling firm</th><th>Dates conducted</th><th>Sample size</th>
          {headers}
        </tr></thead>
        <tbody><tr>
          <td><a href="https://example.test/poll">{pollster}</a></td>
          <td>{dates}</td><td>{sample}</td>{scores}
        </tr></tbody>
      </table>
    """


def first_round_page(*tables):
    return "<html><body><h2>First round</h2>" + "".join(tables) + "</body></html>"


class CandidateNameEvidenceTests(unittest.TestCase):
    def test_reviewed_aliases_and_corrupted_accents_still_normalize(self):
        self.assertEqual(canonical_candidate_name("Edouard Philippe"), "Édouard Philippe")
        self.assertEqual(
            canonical_candidate_name("Rapha�l GLUCKSMANN", strict=True),
            "Raphaël Glucksmann",
        )

    def test_unknown_clean_first_round_candidate_passes_through(self):
        page = first_round_page(
            polling_table(
                candidates=(
                    ("Nouvelle Personne", "20"),
                    ("Edouard Philippe", "30"),
                    ("Eric Zemmour", "50"),
                )
            )
        )
        events, skipped = parse_wikipedia_first_round_html(page)
        self.assertEqual(skipped, [])
        self.assertEqual(
            [row["name"] for row in events[0]["candidates"]],
            ["Nouvelle Personne", "Édouard Philippe", "Éric Zemmour"],
        )

    def test_unknown_clean_second_round_candidate_is_valid_source_evidence(self):
        names = ["Nouvelle Personne", "Édouard Philippe"]
        event = {
            "event_id": make_event_id(
                "Ifop", "2026-07-01", "2026-07-02", "Nouvelle Personne vs Édouard Philippe",
                "https://example.test/runoff", round_name=SECOND_ROUND,
            ),
            "round": SECOND_ROUND,
            "pollster": "Ifop",
            "fieldwork_start": "2026-07-01",
            "fieldwork_end": "2026-07-02",
            "hypothesis": "Nouvelle Personne vs Édouard Philippe",
            "source_url": "https://example.test/runoff",
            "source_scope": "current_tested",
            "matchup_key": make_scenario_key(names, round_name=SECOND_ROUND),
            "margin": 4,
            "candidates": [
                {"name": "Nouvelle Personne", "score": 52},
                {"name": "Édouard Philippe", "score": 48},
            ],
        }
        validate_second_round_event(event)
        self.assertEqual(canonical_matchup_candidate("Nouvelle Personne"), "Nouvelle Personne")

    def test_second_round_still_requires_exactly_two_candidates(self):
        event = {"candidates": [{"name": "Nouvelle Personne", "score": 100}]}
        with self.assertRaisesRegex(ValueError, "exactly two"):
            validate_second_round_event(event)


class SemanticFirstRoundDiscoveryTests(unittest.TestCase):
    def test_reordered_tables_and_irrelevant_prefix_do_not_change_eligibility(self):
        irrelevant = """
          <table><tr><th>Year</th><th>Winner</th></tr>
          <tr><td>2022</td><td>Macron</td></tr></table>
        """
        a = polling_table(pollster="Ifop", dates="1–2 Jul 2026")
        b = polling_table(pollster="Ipsos", dates="3–4 Jul 2026")

        first = discover_first_round_tables(
            first_round_page(irrelevant, a, b)
        )
        reordered = discover_first_round_tables(
            first_round_page(irrelevant, irrelevant, b, a)
        )

        self.assertEqual([item[0] for item in first], [1, 2])
        self.assertEqual([item[0] for item in reordered], [2, 3])
        events, _ = parse_wikipedia_first_round_html(
            first_round_page(irrelevant, irrelevant, b, a)
        )
        self.assertEqual(
            [event["pollster"] for event in events],
            ["Ipsos", "Ifop"],
        )

    def test_nested_container_table_is_skipped_without_duplicates(self):
        wrapped = (
            '<table class="layout"><tbody><tr><td>'
            + polling_table(
                pollster="Ifop",
                dates="1–2 Jul 2026",
            )
            + "</td></tr></tbody></table>"
        )

        page = first_round_page(wrapped)
        discovered = discover_first_round_tables(page)

        # Table 0 is the structural wrapper; table 1 is the poll table.
        self.assertEqual([item[0] for item in discovered], [1])

        events, _ = parse_wikipedia_first_round_html(page)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["pollster"], "Ifop")

    def test_runoff_table_is_excluded(self):
        runoff = """
          <h2>Second round</h2>
          <table><tr>
            <th>Polling firm</th><th>Dates conducted</th><th>Sample size</th>
            <th>Edouard Philippe</th><th>Eric Zemmour</th>
          </tr><tr>
            <td>Runoff Pollster</td><td>1–2 Jul 2026</td><td>1,000</td>
            <td>55</td><td>45</td>
          </tr></table>
        """
        page = (
            "<html><body>"
            + runoff
            + "<h2>First round</h2>"
            + polling_table()
            + "</body></html>"
        )
        events, _ = parse_wikipedia_first_round_html(page)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["round"], "first_round")

    def test_deterministic_document_order_and_multiple_scenarios(self):
        scenario_a = polling_table(
            candidates=(
                ("Edouard Philippe", "30"),
                ("Eric Zemmour", "30"),
                ("Glucksmann", "40"),
            )
        )
        scenario_b = polling_table(
            candidates=(
                ("Edouard Philippe", "35"),
                ("Eric Zemmour", "25"),
                ("Marine Le Pen", "40"),
            )
        )
        page = first_round_page(scenario_a, scenario_b)
        first, _ = parse_wikipedia_first_round_html(page)
        second, _ = parse_wikipedia_first_round_html(page)

        self.assertEqual(
            [event["event_id"] for event in first],
            [event["event_id"] for event in second],
        )
        self.assertEqual(len(first), 2)
        self.assertEqual(
            {
                (
                    event["pollster"],
                    event["fieldwork_start"],
                    event["fieldwork_end"],
                    event["sample_size"],
                )
                for event in first
            },
            {("Ifop", "2026-07-01", "2026-07-02", 1000)},
        )
        self.assertNotEqual(first[0]["scenario_key"], first[1]["scenario_key"])

    def test_candidate_and_pollster_aliases_are_canonicalized(self):
        events, _ = parse_wikipedia_first_round_html(
            first_round_page(polling_table(pollster="Opinion Way"))
        )
        self.assertEqual(events[0]["pollster"], "OpinionWay")
        self.assertEqual(
            [candidate["name"] for candidate in events[0]["candidates"]],
            ["Édouard Philippe", "Éric Zemmour", "Raphaël Glucksmann"],
        )
        self.assertEqual(
            canonical_pollster_name("Harris Interactive / Toluna"),
            "Harris Interactive",
        )

    def test_empty_eligible_table_result_fails(self):
        page = """
          <html><body><h2>Second round</h2>
          <table><tr><th>Firm</th><th>A</th><th>B</th></tr>
          <tr><td>X</td><td>51</td><td>49</td></tr></table>
          </body></html>
        """
        with self.assertRaisesRegex(
            ValueError,
            "no eligible first-round polling tables",
        ):
            parse_wikipedia_first_round_html(page)


class PollEventContractTests(unittest.TestCase):
    def parse_one(self, candidates):
        events, _ = parse_wikipedia_first_round_html(
            first_round_page(polling_table(candidates=candidates))
        )
        self.assertEqual(len(events), 1)
        return events[0]

    def test_complete_scenario(self):
        event = self.parse_one(
            (("Edouard Philippe", "30"), ("Eric Zemmour", "30"), ("Glucksmann", "40"))
        )
        self.assertEqual(event["reported_total"], 100)
        self.assertEqual(event["completeness_status"], "complete")
        self.assertFalse(event["partial_scenario"])
        self.assertIsNone(event["unreported_share"])

    def test_partial_scenario_total_97(self):
        event = self.parse_one(
            (("Edouard Philippe", "30"), ("Eric Zemmour", "30"), ("Glucksmann", "37"))
        )
        self.assertEqual(event["reported_total"], 97)
        self.assertEqual(event["completeness_status"], "partial")
        self.assertTrue(event["partial_scenario"])
        self.assertEqual(event["unreported_share"], 3)

    def test_partial_decimal_total(self):
        event = self.parse_one(
            (("Edouard Philippe", "30.2"), ("Eric Zemmour", "30"), ("Glucksmann", "38.3"))
        )
        self.assertEqual(event["reported_total"], 98.5)
        self.assertEqual(event["unreported_share"], 1.5)

    def test_censored_score_skips_ambiguous_row(self):
        valid_table = polling_table(
            pollster="Ifop",
            dates="1–2 Jul 2026",
        )
        censored_table = polling_table(
            pollster="OpinionWay",
            dates="8–9 Jul 2026",
            candidates=(
                ("Edouard Philippe", "30"),
                ("Marine Le Pen", "69"),
                ("Nathalie Arthaud", "<1"),
            ),
        )

        events, skipped = parse_wikipedia_first_round_html(
            first_round_page(
                valid_table,
                censored_table,
            )
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["pollster"], "Ifop")
        self.assertEqual(len(skipped), 1)
        self.assertIn(
            "OpinionWay 8–9 Jul 2026",
            skipped[0],
        )
        self.assertIn(
            "Nathalie Arthaud '<1'",
            skipped[0],
        )
        self.assertIn(
            "censored score",
            skipped[0],
        )

    def test_impossible_total_skips_wikipedia_row(self):
        valid_table = polling_table(
            pollster="Ifop",
            dates="1–2 Jul 2026",
        )
        impossible_table = polling_table(
            pollster="Harris Interactive",
            dates="22 Mar 2026",
            candidates=(
                ("Edouard Philippe", "30"),
                ("Eric Zemmour", "30"),
                ("Glucksmann", "42"),
            ),
        )

        events, skipped = parse_wikipedia_first_round_html(
            first_round_page(
                valid_table,
                impossible_table,
            )
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["pollster"], "Ifop")
        self.assertEqual(len(skipped), 1)
        self.assertIn(
            "Harris Interactive 22 Mar 2026",
            skipped[0],
        )
        self.assertIn(
            "reported total is impossible: 102",
            skipped[0],
        )
        self.assertIn(
            "Wikipedia row rejected",
            skipped[0],
        )

    def test_malformed_numeric_score_fails(self):
        with self.assertRaisesRegex(ValueError, "ambiguous score"):
            self.parse_one(
                (("Edouard Philippe", "30"), ("Eric Zemmour", "thirty"), ("Glucksmann", "40"))
            )

    def test_duplicate_candidate_column_fails(self):
        with self.assertRaisesRegex(ValueError, "duplicate candidates"):
            parse_wikipedia_first_round_html(
                first_round_page(
                    polling_table(
                        candidates=(
                            ("Edouard Philippe", "30"),
                            ("Edouard Philippe", "30"),
                            ("Eric Zemmour", "40"),
                        )
                    )
                )
            )

    def test_reversed_fieldwork_dates_fail(self):
        with self.assertRaisesRegex(
            PollContractError,
            "fieldwork_start must not be after fieldwork_end",
        ):
            parse_wikipedia_first_round_html(
                first_round_page(
                    polling_table(dates="4 Jul–2 Jul 2026")
                )
            )

    def test_event_id_is_stable_when_completeness_metadata_is_added(self):
        event = self.parse_one(
            (("Edouard Philippe", "30"), ("Eric Zemmour", "30"), ("Glucksmann", "37"))
        )
        event_without_metadata = copy.deepcopy(event)
        for field in (
            "reported_total",
            "completeness_status",
            "partial_scenario",
            "unreported_share",
        ):
            event_without_metadata.pop(field)

        event_id_before = make_event_id(
            event_without_metadata["pollster"],
            event_without_metadata["fieldwork_start"],
            event_without_metadata["fieldwork_end"],
            event_without_metadata["hypothesis"],
            event_without_metadata["source_url"],
        )
        apply_completeness_contract(event_without_metadata)
        validate_poll_event(event_without_metadata)

        self.assertEqual(event_id_before, event["event_id"])
        self.assertEqual(event_without_metadata["event_id"], event["event_id"])

    def test_contract_rejects_contradictory_metadata(self):
        event = self.parse_one(
            (("Edouard Philippe", "30"), ("Eric Zemmour", "30"), ("Glucksmann", "37"))
        )
        event["partial_scenario"] = False
        with self.assertRaisesRegex(
            PollContractError,
            "partial_scenario contradicts",
        ):
            validate_poll_event(event)

    def test_source_fallback_does_not_change_contract(self):
        event = self.parse_one(
            (("Edouard Philippe", "30"), ("Eric Zemmour", "30"), ("Glucksmann", "40"))
        )
        self.assertIn(event["source_url"], {"https://example.test/poll", SOURCE_URL})


if __name__ == "__main__":
    unittest.main()
