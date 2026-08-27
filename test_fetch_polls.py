import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from commission_notice_coverage import reconcile_commission_notices
from commission_notice_discovery import load_registry
from fetch_polls import (
    SOURCE_URL,
    SECOND_ROUND,
    apply_official_poll_sources,
    atomic_write_json,
    canonical_candidate_name,
    canonical_matchup_candidate,
    canonical_pollster_name,
    discover_first_round_tables,
    integrate_french_migration_source,
    load_poll_wave_overrides,
    load_previous_second_round_events,
    main as fetch_polls_main,
    merge_previous_first_round_events,
    parse_fieldwork,
    parse_wikipedia_first_round_html,
    validate_reporting_source_wave_anomalies,
    validate_second_round_event,
)
from poll_migration import (
    FRENCH_FIXTURE,
    load_mediawiki_fixture,
    load_migration_registry,
)
from poll_contract import (
    PollContractError,
    apply_completeness_contract,
    make_event_id,
    make_scenario_key,
    validate_poll_event,
)


ROOT = Path(__file__).parent
PRE_CUTOVER_FIRST_ROUND = (
    ROOT / "test_fixtures/fr27_polling/pre_cutover_first_round_203.json"
)
PRE_CUTOVER_SECOND_ROUND = (
    ROOT / "test_fixtures/fr27_polling/pre_cutover_second_round_38.json"
)
PRE_CUTOVER_COMMISSION_REGISTRY = (
    ROOT / "test_fixtures/fr27_polling/pre_cutover_commission_notice_registry.json"
)


class WikipediaSourceSelectionTests(unittest.TestCase):
    def test_default_source_remains_english_and_scheduled_source_is_french(self):
        self.assertTrue(SOURCE_URL.startswith("https://en.wikipedia.org/"))
        workflow = (ROOT / ".github/workflows/update-polls.yml").read_text(
            encoding="utf-8"
        )
        fetch_step = workflow.split(
            "- name: Fetch polls into temporary files", 1
        )[1].split("- name: Validate and stage fetched data", 1)[0]
        required = (
            "--wikipedia-source french",
            "--previous-first-round polls.json",
            "--previous-second-round second_round_polls.json",
        )
        for marker in required:
            self.assertEqual(fetch_step.count(marker), 1)
        self.assertNotIn("--wikipedia-source english", fetch_step)
        self.assertNotIn("fr.wikipedia.org", workflow)

    def test_workflow_official_wave_validation_excludes_fr_t1r45_only_from_evidence(self):
        workflow = (ROOT / ".github/workflows/update-polls.yml").read_text(
            encoding="utf-8"
        )
        validation_step = workflow.split(
            "- name: Validate and stage fetched data", 1
        )[1]

        self.assertIn(
            'load_migration_registry()["french_additions"][FIRST_ROUND]',
            validation_step,
        )
        self.assertIn(
            'if event.get("migration_source_locator") not in audited_first_locators',
            validation_step,
        )
        self.assertIn(
            "for event in official_validation_events",
            validation_step,
        )

        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        previous_second = load_previous_second_round_events(
            ROOT / "second_round_polls.json"
        )
        parsed = load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)
        migrated, _second, _report, _official = integrate_french_migration_source(
            parsed,
            previous_first,
            previous_second,
            [],
        )

        elabe_wave = [
            event
            for event in migrated
            if event["pollster"] == "Elabe"
            and event["fieldwork_start"] == "2026-03-25"
            and event["fieldwork_end"] == "2026-03-27"
        ]
        self.assertEqual(len(elabe_wave), 7)
        self.assertEqual(
            {
                event.get("migration_source_locator")
                for event in elabe_wave
                if event.get("migration_source_locator")
            },
            {"FR-T1R45"},
        )

        audited_locators = {
            record["source_locator"]
            for record in load_migration_registry()["french_additions"]["first_round"]
        }
        official_elabe_wave = [
            event
            for event in elabe_wave
            if event.get("migration_source_locator") not in audited_locators
        ]
        self.assertEqual(len(official_elabe_wave), 6)
        self.assertTrue(
            all(
                event["source_url"]
                == "https://www.commission-des-sondages.fr/notices/medias/fichiers/add/2166"
                for event in official_elabe_wave
            )
        )
        self.assertIn(
            "FR-T1R45",
            {
                event.get("migration_source_locator")
                for event in migrated
            },
        )

    def test_english_source_accepts_prepared_previous_second_round_argument(self):
        class ParsedArguments(RuntimeError):
            pass

        arguments = [
            "fetch_polls.py",
            "--wikipedia-source",
            "english",
            "--previous-second-round",
            "must-not-be-read.json",
        ]
        with (
            patch.object(sys, "argv", arguments),
            patch(
                "fetch_polls.load_poll_wave_overrides",
                side_effect=ParsedArguments,
            ),
            self.assertRaises(ParsedArguments),
        ):
            fetch_polls_main()

    def test_french_source_requires_both_previous_corpora(self):
        result = subprocess.run(
            [sys.executable, "-B", "fetch_polls.py", "--wikipedia-source", "french"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--previous-first-round", result.stderr)
        self.assertIn("--previous-second-round", result.stderr)

    def test_french_phase4a_mode_refuses_tracked_output_destinations(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "fetch_polls.py",
                "--wikipedia-source",
                "french",
                "--previous-first-round",
                "polls.json",
                "--previous-second-round",
                "second_round_polls.json",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("non-production temporary outputs", result.stderr)

    def test_previous_second_round_loader_validates_all_38_events(self):
        events = load_previous_second_round_events(PRE_CUTOVER_SECOND_ROUND)
        self.assertEqual(len(events), 38)
        self.assertEqual(len({event["event_id"] for event in events}), 38)

    def test_french_integration_path_produces_audited_232_50_in_memory(self):
        previous_first = json.loads(
            PRE_CUTOVER_FIRST_ROUND.read_text(encoding="utf-8")
        )
        previous_second = load_previous_second_round_events(
            PRE_CUTOVER_SECOND_ROUND
        )
        parsed = load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)
        first, second, report, _official = integrate_french_migration_source(
            parsed,
            previous_first,
            previous_second,
            [],
        )
        self.assertEqual((len(first), len(second)), (232, 50))
        self.assertEqual(
            report["audited_additions_introduced"],
            {"first_round": 29, "second_round": 12},
        )
        self.assertTrue(
            {event["event_id"] for event in previous_first}
            <= {event["event_id"] for event in first}
        )
        self.assertTrue(
            {event["event_id"] for event in previous_second}
            <= {event["event_id"] for event in second}
        )

    def test_audited_french_additions_are_excluded_only_from_commission_evidence(self):
        protected_paths = (
            ROOT / "commission_notice_coverage.py",
            ROOT / "commission_notice_discovery.py",
        )
        protected_before = {path: path.read_bytes() for path in protected_paths}
        previous_first = json.loads(
            PRE_CUTOVER_FIRST_ROUND.read_text(encoding="utf-8")
        )
        previous_second = load_previous_second_round_events(
            PRE_CUTOVER_SECOND_ROUND
        )
        parsed = load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)
        migrated, _second, _report, _official = integrate_french_migration_source(
            parsed,
            previous_first,
            previous_second,
            [],
        )

        migration_registry = load_migration_registry()
        audited_locators = {
            record["source_locator"]
            for record in migration_registry["french_additions"]["first_round"]
        }
        audited_additions = [
            event
            for event in migrated
            if event.get("migration_source_locator") in audited_locators
        ]
        self.assertEqual(len(migrated), 232)
        self.assertEqual(len(audited_additions), 29)
        self.assertEqual(
            {event["migration_source_locator"] for event in audited_additions},
            audited_locators,
        )
        self.assertTrue(
            {event["event_id"] for event in audited_additions}
            <= {event["event_id"] for event in migrated}
        )

        unfiltered_registry = load_registry(PRE_CUTOVER_COMMISSION_REGISTRY)
        self.assertEqual(
            reconcile_commission_notices(unfiltered_registry, migrated),
            {
                "relevant": 16,
                "parsed": 3,
                "reconciled": 9,
                "unresolved": 4,
                "unresolved_notice_ids": [
                    "commission:10223",
                    "commission:10193",
                    "commission:10180",
                    "commission:10165",
                ],
            },
        )

        commission_evidence = [
            event
            for event in migrated
            if event.get("migration_source_locator") not in audited_locators
        ]
        retained_ids = {event["event_id"] for event in previous_first}
        evidence_ids = {event["event_id"] for event in commission_evidence}
        non_migration_ids = {
            event["event_id"]
            for event in migrated
            if event.get("migration_source_locator") not in audited_locators
        }
        self.assertEqual(len(commission_evidence), 203)
        self.assertEqual(evidence_ids, non_migration_ids)
        self.assertTrue(retained_ids <= evidence_ids)
        self.assertTrue(
            all(
                event in commission_evidence
                for event in migrated
                if event.get("migration_source_locator") not in audited_locators
            )
        )
        filtered_registry = load_registry(PRE_CUTOVER_COMMISSION_REGISTRY)
        self.assertEqual(
            reconcile_commission_notices(filtered_registry, commission_evidence),
            {
                "relevant": 16,
                "parsed": 3,
                "reconciled": 13,
                "unresolved": 0,
                "unresolved_notice_ids": [],
            },
        )
        self.assertEqual(
            {path: path.read_bytes() for path in protected_paths},
            protected_before,
        )


def polling_table(
    *,
    pollster="Ifop",
    dates="1–2 Jul 2026",
    sample="1,000",
    source="https://example.test/poll",
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
          <td><a href="{source}">{pollster}</a></td>
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
    VERIAN_LHEMICYCLE_URL = (
        "https://lhemicycle.com/2026/07/10/"
        "jordan-bardella-toujours-le-favori-pour-representer-le-rn/"
    )

    def test_reviewed_wave_control_file_loads_expected_interventions(self):
        overrides = load_poll_wave_overrides()
        self.assertEqual(len(overrides), 4)
        self.assertEqual(
            overrides[(
                "harris interactive",
                "2026-08-21",
                "2026-08-22",
                1582,
            )]["status"],
            "rejected",
        )

    def test_reviewed_verian_wave_is_corrected_before_event_identity(self):
        events, skipped = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Verian",
                    dates="9–10 Jul 2026",
                    sample="1,047",
                    source=self.VERIAN_LHEMICYCLE_URL,
                )
            )
        )

        self.assertEqual(skipped, [])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["fieldwork_start"], "2026-07-08")
        self.assertEqual(event["fieldwork_end"], "2026-07-10")
        self.assertEqual(
            event["event_id"],
            make_event_id(
                "Verian",
                "2026-07-08",
                "2026-07-10",
                event["hypothesis"],
                self.VERIAN_LHEMICYCLE_URL,
            ),
        )
        self.assertNotEqual(
            event["event_id"],
            make_event_id(
                "Verian",
                "2026-07-09",
                "2026-07-10",
                event["hypothesis"],
                self.VERIAN_LHEMICYCLE_URL,
            ),
        )

    def test_verian_metadata_correction_rejects_near_matches(self):
        cases = (
            (
                {
                    "pollster": "Verian",
                    "dates": "9–10 Jul 2026",
                    "sample": "1,048",
                    "source": self.VERIAN_LHEMICYCLE_URL,
                },
                ("2026-07-09", "2026-07-10"),
            ),
            (
                {
                    "pollster": "Verian",
                    "dates": "9–10 Jul 2026",
                    "sample": "1,047",
                    "source": "https://example.test/different-verian-wave",
                },
                ("2026-07-09", "2026-07-10"),
            ),
            (
                {
                    "pollster": "Verian France",
                    "dates": "9–10 Jul 2026",
                    "sample": "1,047",
                    "source": self.VERIAN_LHEMICYCLE_URL,
                },
                ("2026-07-09", "2026-07-10"),
            ),
            (
                {
                    "pollster": "Verian",
                    "dates": "9–11 Jul 2026",
                    "sample": "1,047",
                    "source": self.VERIAN_LHEMICYCLE_URL,
                },
                ("2026-07-09", "2026-07-11"),
            ),
        )
        for attributes, expected_dates in cases:
            with self.subTest(attributes=attributes):
                events, _ = parse_wikipedia_first_round_html(
                    first_round_page(
                        polling_table(**attributes)
                    )
                )
                self.assertEqual(
                    (
                        events[0]["fieldwork_start"],
                        events[0]["fieldwork_end"],
                    ),
                    expected_dates,
                )


    def test_missing_previous_wave_is_retained(self):
        fresh, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Ifop",
                    dates="18–19 Aug 2026",
                    source="https://example.test/current-wave",
                )
            )
        )
        previous, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Harris Interactive",
                    dates="18–19 Aug 2026",
                    sample="1,764",
                    source="https://example.test/validated-disappeared-wave",
                )
            )
        )

        merged, retained_events, retained_waves = (
            merge_previous_first_round_events(fresh, previous)
        )

        self.assertEqual(retained_events, 1)
        self.assertEqual(retained_waves, 1)
        self.assertEqual(len(merged), 2)
        self.assertEqual(
            (merged[0]["fieldwork_start"], merged[0]["fieldwork_end"]),
            ("2026-08-18", "2026-08-19"),
        )

    def test_rejected_previous_wave_is_not_resurrected(self):
        fresh, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Ifop",
                    dates="18–19 Aug 2026",
                    source="https://example.test/current-wave",
                )
            )
        )
        rejected, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Harris Interactive",
                    dates="21–22 Aug 2026",
                    sample="1,582",
                    source=(
                        "https://www.rtl.fr/actu/politique/sondage-rtl-"
                        "presidentielle-2027-marine-le-pen-progresse-dans-les-"
                        "intentions-de-vote-apres-l-annonce-de-sa-candidature-"
                        "7900653723"
                    ),
                )
            )
        )

        merged, retained_events, retained_waves = (
            merge_previous_first_round_events(fresh, rejected)
        )

        self.assertEqual(merged, fresh)
        self.assertEqual(retained_events, 0)
        self.assertEqual(retained_waves, 0)

    def test_reviewed_official_sources_enrich_without_replacing_reporting_source(self):
        elabe, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Elabe",
                    dates="9–10 Jul 2026",
                    sample="1,503",
                    source="https://example.test/elabe-reporting-source",
                )
            )
        )
        reporting_source = elabe[0]["source_url"]

        enriched_waves = apply_official_poll_sources(elabe)

        self.assertEqual(enriched_waves, 1)
        self.assertEqual(elabe[0]["source_url"], reporting_source)
        self.assertEqual(
            elabe[0]["official_source_url"],
            "https://elabe.fr/presidentielle-2027-iv3/",
        )

    def test_same_source_same_sample_across_fieldwork_windows_fails_review(self):
        first, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Example Pollster",
                    dates="1–2 Jul 2026",
                    sample="1,000",
                    source="https://example.test/reused-report",
                ),
                polling_table(
                    pollster="Example Pollster",
                    dates="3–4 Jul 2026",
                    sample="1,000",
                    source="https://example.test/reused-report",
                ),
            )
        )
        with self.assertRaisesRegex(
            ValueError,
            "poll wave anomaly requires reviewed override",
        ):
            validate_reporting_source_wave_anomalies(first)

    def test_fresh_wave_is_authoritative_over_previous_wave(self):
        fresh, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Harris Interactive",
                    dates="21–22 Aug 2026",
                    source="https://example.test/fresh-wave",
                    candidates=(
                        ("Edouard Philippe", "35"),
                        ("Eric Zemmour", "25"),
                        ("Marine Le Pen", "40"),
                    ),
                )
            )
        )
        previous, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Harris Interactive",
                    dates="21–22 Aug 2026",
                    source="https://example.test/previous-wave",
                )
            )
        )

        merged, retained_events, retained_waves = (
            merge_previous_first_round_events(fresh, previous)
        )

        self.assertEqual(merged, fresh)
        self.assertEqual(retained_events, 0)
        self.assertEqual(retained_waves, 0)

    def test_reviewed_metadata_correction_drops_obsolete_previous_identity(self):
        fresh, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Verian",
                    dates="9–10 Jul 2026",
                    sample="1,047",
                    source=self.VERIAN_LHEMICYCLE_URL,
                )
            )
        )
        obsolete = copy.deepcopy(fresh[0])
        obsolete["fieldwork_start"] = "2026-07-09"
        obsolete["event_id"] = make_event_id(
            obsolete["pollster"],
            obsolete["fieldwork_start"],
            obsolete["fieldwork_end"],
            obsolete["hypothesis"],
            obsolete["source_url"],
        )

        merged, retained_events, retained_waves = (
            merge_previous_first_round_events(fresh, [obsolete])
        )

        self.assertEqual(merged, fresh)
        self.assertEqual(retained_events, 0)
        self.assertEqual(retained_waves, 0)
        self.assertEqual(merged[0]["fieldwork_start"], "2026-07-08")

    def test_missing_reviewed_corrected_wave_fails_closed(self):
        corrected, _ = parse_wikipedia_first_round_html(
            first_round_page(
                polling_table(
                    pollster="Verian",
                    dates="9–10 Jul 2026",
                    sample="1,047",
                    source=self.VERIAN_LHEMICYCLE_URL,
                )
            )
        )
        obsolete = copy.deepcopy(corrected[0])
        obsolete["fieldwork_start"] = "2026-07-09"
        obsolete["event_id"] = make_event_id(
            obsolete["pollster"],
            obsolete["fieldwork_start"],
            obsolete["fieldwork_end"],
            obsolete["hypothesis"],
            obsolete["source_url"],
        )

        with self.assertRaisesRegex(
            ValueError,
            "reviewed corrected poll wave missing",
        ):
            merge_previous_first_round_events([], [obsolete])


    def test_parse_fieldwork_keeps_source_reported_verian_window(self):
        self.assertEqual(
            parse_fieldwork("9–10 Jul 2026"),
            ("2026-07-09", "2026-07-10"),
        )

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

    def test_repository_harris_repair_keeps_only_verified_wave_identity(self):
        events = json.loads(
            Path(__file__).with_name("polls.json").read_text(encoding="utf-8")
        )
        rejected = [
            event
            for event in events
            if event.get("pollster") == "Harris Interactive"
            and event.get("fieldwork_start") == "2026-08-21"
            and event.get("fieldwork_end") == "2026-08-22"
            and event.get("sample_size") == 1582
        ]
        valid = [
            event
            for event in events
            if event.get("pollster") == "Harris Interactive"
            and event.get("fieldwork_start") == "2026-08-18"
            and event.get("fieldwork_end") == "2026-08-19"
            and event.get("sample_size") == 1764
        ]
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), 5)
        self.assertTrue(all("official_source_url" not in event for event in valid))

    def test_atomic_json_write_preserves_last_good_file_on_replace_failure(self):
        output = Path(__file__).with_name(".test-fetch-polls-atomic.json")
        temporary_files = list(output.parent.glob(f".{output.name}.*.tmp"))
        self.assertEqual(temporary_files, [])
        try:
            output.write_text("last-good\n", encoding="utf-8")
            with patch("fetch_polls.os.replace", side_effect=OSError("blocked")):
                with self.assertRaisesRegex(OSError, "blocked"):
                    atomic_write_json(output, [{"new": "payload"}])
            self.assertEqual(output.read_text(encoding="utf-8"), "last-good\n")
            self.assertEqual(
                list(output.parent.glob(f".{output.name}.*.tmp")),
                [],
            )
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
