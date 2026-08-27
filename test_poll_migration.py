"""Frozen, offline continuity gates for the FR27 French-source migration."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import build_fr27_poll_migration_registry as registry_builder
from lxml import html as lxml_html
from fetch_polls import (
    SECOND_ROUND,
    make_event_id,
    make_scenario_key,
    validate_second_round_event,
)
from poll_contract import FIRST_ROUND, PollContractError, validate_poll_events
from poll_migration import (
    ENGLISH_FIXTURE,
    FRENCH_FIXTURE,
    POST_AUDIT_HOLLANDE_LE_PEN_LOCATOR,
    apply_wave_scoped_pollster_alias,
    exact_factual_key,
    load_mediawiki_fixture,
    load_migration_registry,
    merge_previous_second_round_events,
    parse_english_frozen_first_round,
    parse_english_frozen_second_round,
    parse_french_frozen_fixture,
    pollster_identity,
    reconcile_runoff_continuity,
    review_anchor,
    reviewed_candidate_name,
    validate_migration_registry,
)
from rehearse_fr_poll_migration import (
    EVENT_ID_CONTRACT_PROBES,
    PHASE4_PRODUCTION_MODIFICATION_FILES,
    PHASE4_PROTECTED_LOGIC_SHA256,
    RehearsalError,
    SourceDriftError,
    phase4a_cutover_contract,
    reconcile_french_production_source,
    rehearse_migration,
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


def read_json(name: str) -> object:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def read_pre_cutover_first_round() -> list[dict]:
    payload = json.loads(PRE_CUTOVER_FIRST_ROUND.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise AssertionError("frozen pre-cutover first-round fixture is malformed")
    return payload


def read_pre_cutover_second_round() -> list[dict]:
    payload = json.loads(PRE_CUTOVER_SECOND_ROUND.read_text(encoding="utf-8"))
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        raise AssertionError("frozen pre-cutover second-round fixture is malformed")
    return events


def rehearse_pre_cutover(parsed: dict):
    return rehearse_migration(
        parsed,
        current_first=read_pre_cutover_first_round(),
        current_second=read_pre_cutover_second_round(),
    )


def post_audit_french_row_fixture() -> dict:
    parsed = copy.deepcopy(load_mediawiki_fixture(FRENCH_FIXTURE, 238906992))
    document = lxml_html.fromstring(parsed["text"])
    rows = document.xpath("//table")[0].xpath(".//tr[td]")
    template = next(
        row
        for row in rows
        if row.xpath("./td")
        and "Verian" in row.xpath("./td")[0].text_content()
    )
    new_row = copy.deepcopy(template)
    cells = new_row.xpath("./td")
    cells[0].clear()
    pollster_link = lxml_html.Element("a")
    pollster_link.set("href", "https://example.test/post-audit-french-poll")
    pollster_link.text = "Ipsos"
    cells[0].append(pollster_link)
    cells[1].clear()
    cells[1].text = "20-21 août"
    cells[2].clear()
    cells[2].text = "1 111"
    template.addprevious(new_row)
    parsed["text"] = lxml_html.tostring(document, encoding="unicode")
    parsed["revid"] = 238906993
    return parsed


def post_audit_hollande_runoff_fixture() -> dict:
    parsed = copy.deepcopy(load_mediawiki_fixture(FRENCH_FIXTURE, 238906992))
    sections = parsed["tocdata"]["sections"]
    ruffin_index = next(
        index
        for index, section in enumerate(sections)
        if section["line"] == "Hypothèse Ruffin – Le Pen"
    )
    sections.insert(
        ruffin_index + 1,
        {
            "tocLevel": 3,
            "hLevel": 4,
            "line": "Hypothèse Hollande – Le Pen",
            "number": "4.1.7",
            "index": "17",
            "anchor": "Hypothèse_Hollande_–_Le_Pen",
        },
    )

    document = lxml_html.fromstring(parsed["text"])
    ruffin_table = document.xpath("//table")[11]
    heading = lxml_html.fragment_fromstring(
        '<div class="mw-heading mw-heading4">'
        '<h4 id="Hypothèse_Hollande_–_Le_Pen">'
        "Hypothèse Hollande – Le Pen"
        "</h4></div>"
    )
    table = lxml_html.fragment_fromstring(
        """
        <table class="wikitable">
          <tbody>
            <tr>
              <th rowspan="3">Sondeur</th>
              <th rowspan="3">Dates</th>
              <th rowspan="3">Échantillon</th>
              <th></th>
              <th></th>
            </tr>
            <tr>
              <th><a href="/wiki/François_Hollande">Hollande</a> (PS)</th>
              <th><a href="/wiki/Marine_Le_Pen">Le Pen</a> (RN)</th>
            </tr>
            <tr><td></td><td></td></tr>
            <tr>
              <td><a href="https://example.test/hollande-le-pen">Ifop</a></td>
              <td>24 - 25 août 2026</td>
              <td>1 598</td>
              <td>46</td>
              <td>54</td>
            </tr>
          </tbody>
        </table>
        """
    )
    ruffin_table.addnext(heading)
    heading.addnext(table)
    parsed["text"] = lxml_html.tostring(document, encoding="unicode")
    parsed["revid"] = 238978513
    return parsed


def key_dict(record: dict, field: str = "canonical_factual_key") -> dict:
    return record[field]


def reviewed_records(
    registry: dict, *, start: str, pollster: str, round_name: str = FIRST_ROUND
) -> list[dict]:
    return [
        record
        for record in registry["reviewed_reconciliations"]
        if key_dict(record)["round"] == round_name
        and key_dict(record)["fieldwork_start"] == start
        and key_dict(record)["pollster_identity"] == pollster
    ]


def production_runoff(record: dict, *, pollster: str | None = None) -> dict:
    candidates = copy.deepcopy(record["candidates"])
    display_pollster = pollster or record["pollster"]
    hypothesis = " vs. ".join(candidate["name"] for candidate in candidates)
    event = {
        "round": SECOND_ROUND,
        "pollster": display_pollster,
        "fieldwork_start": record["fieldwork_start"],
        "fieldwork_end": record["fieldwork_end"],
        "hypothesis": hypothesis,
        "source_url": record["source_url"],
        "source_scope": "current_tested",
        "candidates": candidates,
        "migration_source_locator": record["source_locator"],
    }
    event["matchup_key"] = make_scenario_key(
        [candidate["name"] for candidate in candidates], round_name=SECOND_ROUND
    )
    event["event_id"] = make_event_id(
        display_pollster,
        event["fieldwork_start"],
        event["fieldwork_end"],
        hypothesis,
        event["source_url"],
        round_name=SECOND_ROUND,
    )
    event["margin"] = abs(candidates[0]["score"] - candidates[1]["score"])
    validate_second_round_event(event)
    return event


class FrozenFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.en = load_mediawiki_fixture(ENGLISH_FIXTURE, 1371070883)
        cls.fr = load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)
        cls.en_first, cls.en_skipped = parse_english_frozen_first_round(cls.en)
        cls.en_second = parse_english_frozen_second_round(cls.en)
        cls.fr_parsed = parse_french_frozen_fixture(cls.fr)

    def test_fixtures_are_the_exact_audited_revisions(self) -> None:
        expected = {
            ENGLISH_FIXTURE: "d6f0cfcb0cf33edc04a13e38c0171d917a61b985d49a1f5d863a4027838b2f0a",
            FRENCH_FIXTURE: "62bcad0a3f951a352f7acdb35bdfb5da85bb1aaae3912c61c2d2bc03e197744f",
            PRE_CUTOVER_FIRST_ROUND: "57d1fbdd08a1133dd7e907e7be71cf572e700a6d010a1f0b5fd070893211b913",
            PRE_CUTOVER_SECOND_ROUND: "063176c7af66e29c3380dcc5c5e22d2af632ab564b7f79e160678bb7f08f0d34",
            PRE_CUTOVER_COMMISSION_REGISTRY: "bad7e3924f82b60d6972d24537ace73071a73c049fb4b155df7d8cb392f992d9",
        }
        for path, digest in expected.items():
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_frozen_parsers_cover_both_rounds_without_live_wikipedia(self) -> None:
        self.assertEqual((len(self.en_first), len(self.en_skipped)), (200, 3))
        self.assertEqual(len(self.en_second), 38)
        self.assertEqual(len(self.fr_parsed["first_round"]), 191)
        self.assertEqual(len(self.fr_parsed["second_round"]), 48)
        self.assertEqual(len(self.fr_parsed["rejected"]), 8)

    def test_french_section_structure_and_all_eleven_runoff_families(self) -> None:
        headings = [section["line"] for section in self.fr["tocdata"]["sections"]]
        self.assertIn("Sondages concernant le premier tour", headings)
        self.assertIn("Sondages concernant le second tour", headings)
        hypotheses = [heading for heading in headings if heading.startswith("Hypothèse ")]
        self.assertEqual(len(hypotheses), 11)
        family_counts = Counter(
            record["source_locator"].split("r", 1)[0]
            for record in self.fr_parsed["second_round"]
        )
        self.assertEqual(
            family_counts,
            Counter(
                {
                    "FR-R1": 8,
                    "FR-R2": 1,
                    "FR-R3": 7,
                    "FR-R4": 10,
                    "FR-R5": 1,
                    "FR-R6": 1,
                    "FR-R7": 4,
                    "FR-R8": 2,
                    "FR-R9": 4,
                    "FR-R10": 8,
                    "FR-R11": 2,
                }
            ),
        )

    def test_known_hollande_family_preserves_audited_runoff_locators(self) -> None:
        parsed = parse_french_frozen_fixture(post_audit_hollande_runoff_fixture())
        baseline = {
            record["source_locator"]: record
            for record in self.fr_parsed["second_round"]
        }
        incoming = {
            record["source_locator"]: record for record in parsed["second_round"]
        }
        for locator, record in baseline.items():
            with self.subTest(locator=locator):
                self.assertEqual(incoming[locator], record)

        new_locator = f"{POST_AUDIT_HOLLANDE_LE_PEN_LOCATOR}r1"
        self.assertEqual(set(incoming) - set(baseline), {new_locator})
        self.assertEqual(
            incoming[new_locator]["candidates"],
            [
                {"name": "François Hollande", "score": 46},
                {"name": "Marine Le Pen", "score": 54},
            ],
        )

    def test_known_hollande_family_is_a_normal_post_audit_addition(self) -> None:
        previous_first = read_pre_cutover_first_round()
        previous_second = read_pre_cutover_second_round()
        result = reconcile_french_production_source(
            post_audit_hollande_runoff_fixture(),
            previous_first,
            previous_second,
        )
        self.assertEqual(
            (len(result.first_round_events), len(result.second_round_events)),
            (232, 51),
        )
        self.assertEqual(
            result.report["normal_post_audit_additions"],
            {FIRST_ROUND: 0, SECOND_ROUND: 1},
        )
        previous_second_ids = {event["event_id"] for event in previous_second}
        self.assertTrue(
            previous_second_ids
            <= {event["event_id"] for event in result.second_round_events}
        )
        new_locator = f"{POST_AUDIT_HOLLANDE_LE_PEN_LOCATOR}r1"
        added = [
            event
            for event in result.second_round_events
            if event.get("migration_source_locator") == new_locator
        ]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["migration_source_locator"], new_locator)

    def test_hollande_family_requires_exact_position_and_table_schema(self) -> None:
        previous_first = read_pre_cutover_first_round()
        previous_second = read_pre_cutover_second_round()

        misordered = post_audit_hollande_runoff_fixture()
        sections = misordered["tocdata"]["sections"]
        hollande = next(
            section
            for section in sections
            if section["line"] == "Hypothèse Hollande – Le Pen"
        )
        sections.remove(hollande)
        retailleau_bardella = next(
            index
            for index, section in enumerate(sections)
            if section["line"] == "Hypothèse Retailleau – Bardella"
        )
        sections.insert(retailleau_bardella + 1, hollande)
        with self.subTest(drift="position"), self.assertRaisesRegex(
            SourceDriftError, "heading hierarchy changed"
        ):
            reconcile_french_production_source(
                misordered,
                previous_first,
                previous_second,
            )

        wrong_level = post_audit_hollande_runoff_fixture()
        next(
            section
            for section in wrong_level["tocdata"]["sections"]
            if section["line"] == "Hypothèse Hollande – Le Pen"
        )["tocLevel"] = 2
        with self.subTest(drift="level"), self.assertRaisesRegex(
            SourceDriftError, "heading hierarchy changed"
        ):
            reconcile_french_production_source(
                wrong_level,
                previous_first,
                previous_second,
            )

        added_heading = post_audit_hollande_runoff_fixture()
        sections = added_heading["tocdata"]["sections"]
        hollande_index = next(
            index
            for index, section in enumerate(sections)
            if section["line"] == "Hypothèse Hollande – Le Pen"
        )
        sections.insert(
            hollande_index + 1,
            {"tocLevel": 3, "line": "Hypothèse non auditée – Le Pen"},
        )
        with self.subTest(drift="addition"), self.assertRaisesRegex(
            SourceDriftError, "heading hierarchy changed"
        ):
            reconcile_french_production_source(
                added_heading,
                previous_first,
                previous_second,
            )

        removed_heading = post_audit_hollande_runoff_fixture()
        removed_heading["tocdata"]["sections"] = [
            section
            for section in removed_heading["tocdata"]["sections"]
            if section["line"] != "Hypothèse Ruffin – Le Pen"
        ]
        with self.subTest(drift="removal"), self.assertRaisesRegex(
            SourceDriftError, "heading hierarchy changed"
        ):
            reconcile_french_production_source(
                removed_heading,
                previous_first,
                previous_second,
            )

        mutated = post_audit_hollande_runoff_fixture()
        document = lxml_html.fromstring(mutated["text"])
        hollande_header = document.xpath("//table")[12].xpath(".//tr[2]/th[1]")[0]
        hollande_header.clear()
        hollande_header.text = "Hollande schema mutation"
        mutated["text"] = lxml_html.tostring(document, encoding="unicode")
        with self.subTest(drift="schema"), self.assertRaisesRegex(
            SourceDriftError, "table/header schema changed"
        ):
            reconcile_french_production_source(
                mutated,
                previous_first,
                previous_second,
            )

        missing_table = post_audit_hollande_runoff_fixture()
        document = lxml_html.fromstring(missing_table["text"])
        table = document.xpath("//table")[12]
        table.getparent().remove(table)
        missing_table["text"] = lxml_html.tostring(document, encoding="unicode")
        with self.subTest(drift="missing table"), self.assertRaisesRegex(
            SourceDriftError, "table/header schema changed"
        ):
            reconcile_french_production_source(
                missing_table,
                previous_first,
                previous_second,
            )

    def test_header_reference_marker_does_not_change_semantic_schema(self) -> None:
        parsed = copy.deepcopy(self.fr)
        document = lxml_html.fromstring(parsed["text"])
        attal_header = next(
            header
            for header in document.xpath("//table")[0].xpath(".//th")
            if "Attal" in header.text_content()
        )
        reference = lxml_html.Element("sup", {"class": "reference"})
        reference.text = "c"
        attal_header.append(reference)
        parsed["text"] = lxml_html.tostring(document, encoding="unicode")
        parsed["revid"] += 1
        result = reconcile_french_production_source(
            parsed,
            read_pre_cutover_first_round(),
            read_pre_cutover_second_round(),
        )
        self.assertEqual(
            (len(result.first_round_events), len(result.second_round_events)),
            (232, 50),
        )

    def test_august_harris_first_round_wave_is_frozen(self) -> None:
        wave = [
            record
            for record in self.fr_parsed["first_round"]
            if record["fieldwork_start"] == "2026-08-18"
            and record["fieldwork_end"] == "2026-08-19"
        ]
        self.assertEqual(len(wave), 5)
        self.assertEqual({record["sample_size"] for record in wave}, {1764})
        self.assertEqual(
            {record["source_locator"] for record in wave},
            {"FR-T0R2", "FR-T0R3", "FR-T0R4", "FR-T0R5", "FR-T0R6"},
        )

    def test_august_harris_runoffs_are_exact(self) -> None:
        expected = {
            "FR-R1r1": {"Gabriel Attal": 43, "Marine Le Pen": 57},
            "FR-R3r1": {"Jean-Luc Mélenchon": 32, "Marine Le Pen": 68},
            "FR-R4r1": {"Édouard Philippe": 45, "Marine Le Pen": 55},
        }
        records = {
            record["source_locator"]: record
            for record in self.fr_parsed["second_round"]
        }
        for locator, scores in expected.items():
            with self.subTest(locator=locator):
                record = records[locator]
                self.assertEqual(record["fieldwork_start"], "2026-08-18")
                self.assertEqual(record["fieldwork_end"], "2026-08-19")
                self.assertEqual(record["sample_size"], 1764)
                self.assertEqual(
                    {item["name"]: item["score"] for item in record["candidates"]},
                    scores,
                )

    def test_eight_parser_level_fail_closed_rows_are_exact(self) -> None:
        rejected = {
            record["source_locator"]: record["reason_code"]
            for record in self.fr_parsed["rejected"]
        }
        self.assertEqual(
            rejected,
            {
                "FR-T0R14": "censored_score",
                "FR-T2R46": "unnamed_generic_candidate",
                "FR-T2R47": "unnamed_generic_candidate",
                "FR-T2R48": "unnamed_generic_candidate",
                "FR-T3R5": "censored_score",
                "FR-T3R7": "censored_score",
                "FR-T3R9": "censored_score",
                "FR-T3R10": "censored_score",
            },
        )


class RegistryBuilderTests(unittest.TestCase):
    def test_generation_is_deterministic_and_matches_committed_bytes(self) -> None:
        first = registry_builder.canonical_registry_bytes(
            registry_builder.build_registry()
        )
        second = registry_builder.canonical_registry_bytes(
            registry_builder.build_registry()
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            (ROOT / "fr27_poll_migration_registry.json").read_bytes(),
        )

    def test_help_and_check_are_read_only_cli_operations(self) -> None:
        registry_path = ROOT / "fr27_poll_migration_registry.json"
        builder_path = ROOT / "build_fr27_poll_migration_registry.py"
        before = registry_path.read_bytes()
        before_stat = registry_path.stat()
        for option in ("--help", "--check"):
            with self.subTest(option=option):
                result = subprocess.run(
                    [sys.executable, "-B", str(builder_path), option],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(registry_path.read_bytes(), before)
                self.assertEqual(registry_path.stat().st_mtime_ns, before_stat.st_mtime_ns)
                if option == "--help":
                    self.assertIn("--check", result.stdout)
                else:
                    self.assertIn("Registry check passed", result.stdout)

    def test_check_reports_stale_registry_without_rewriting_it(self) -> None:
        class StaleReadOnlyOutput:
            name = "stale-registry.json"

            def __init__(self) -> None:
                self.read_count = 0

            def read_bytes(self) -> bytes:
                self.read_count += 1
                return b"stale\r\n"

            def __str__(self) -> str:
                return self.name

        stale = StaleReadOnlyOutput()
        with patch.object(registry_builder, "OUTPUT", stale):
            with redirect_stdout(io.StringIO()) as output:
                result = registry_builder.main(["--check"])
        self.assertEqual(result, 1)
        self.assertEqual(stale.read_count, 1)
        self.assertIn("is stale", output.getvalue())


class CutoverRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed = load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)

    def test_frozen_rehearsal_proves_audited_accounting_without_writes(self) -> None:
        production_paths = (ROOT / "polls.json", ROOT / "second_round_polls.json")
        before = {path: path.read_bytes() for path in production_paths}
        result = rehearse_pre_cutover(copy.deepcopy(self.parsed))
        after = {path: path.read_bytes() for path in production_paths}
        self.assertEqual(after, before)
        self.assertEqual(
            result.report,
            {
                "status": "passed",
                "source_revision": 238906992,
                "audited_source_revision": 238906992,
                "parsed": {"first_round": 191, "second_round": 48},
                "reconciled": {"first_round": 232, "second_round": 50},
                "retained_ids": {"first_round": 203, "second_round": 38},
                "new_additions": {"first_round": 29, "second_round": 12},
                "source_only_migrations": {
                    "first_round": 90,
                    "second_round": 12,
                },
                "reviewed_reconciliations": {
                    "first_round": 59,
                    "second_round": 14,
                },
                "exact_common": {"first_round": 10, "second_round": 10},
                "skips": {
                    "fail_closed_rows": 8,
                    "ambiguous_identity_rows": 3,
                },
                "unexplained_historical_losses": 0,
                "unresolved_accepted_ambiguities": 0,
                "duplicate_canonical_factual_identities": 0,
                "source_structure_drift": [],
                "august_harris_18_19_runoffs_verified": 3,
            },
        )

    def test_frozen_cli_uses_pre_cutover_corpora(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "rehearse_fr_poll_migration.py"),
                "--frozen",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(
            report["retained_ids"],
            {"first_round": 203, "second_round": 38},
        )
        self.assertEqual(
            report["reconciled"],
            {"first_round": 232, "second_round": 50},
        )
        self.assertEqual(report["source_structure_drift"], [])

    def test_rehearsal_retains_every_current_id_and_adds_only_audited_rows(self) -> None:
        result = rehearse_pre_cutover(copy.deepcopy(self.parsed))
        current_first = read_pre_cutover_first_round()
        current_second = read_pre_cutover_second_round()
        current_first_ids = {event["event_id"] for event in current_first}
        current_second_ids = {event["event_id"] for event in current_second}
        rehearsed_first_ids = {
            event["event_id"] for event in result.first_round_events
        }
        rehearsed_second_ids = {
            event["event_id"] for event in result.second_round_events
        }
        self.assertTrue(current_first_ids <= rehearsed_first_ids)
        self.assertTrue(current_second_ids <= rehearsed_second_ids)
        first_additions = [
            event
            for event in result.first_round_events
            if event.get("rehearsal_only")
        ]
        second_additions = [
            event
            for event in result.second_round_events
            if event.get("rehearsal_only")
        ]
        self.assertEqual((len(first_additions), len(second_additions)), (29, 12))
        self.assertEqual(
            {event["migration_source_locator"] for event in first_additions},
            {
                record["source_locator"]
                for record in load_migration_registry()["french_additions"][FIRST_ROUND]
            },
        )
        self.assertEqual(
            {event["migration_source_locator"] for event in second_additions},
            {
                record["source_locator"]
                for record in load_migration_registry()["french_additions"][SECOND_ROUND]
            },
        )

    def test_rehearsal_verifies_august_harris_runoffs_exactly(self) -> None:
        result = rehearse_pre_cutover(copy.deepcopy(self.parsed))
        august = {
            event["migration_source_locator"]: {
                candidate["name"]: candidate["score"]
                for candidate in event["candidates"]
            }
            for event in result.second_round_events
            if event.get("migration_source_locator")
            in {"FR-R1r1", "FR-R3r1", "FR-R4r1"}
        }
        self.assertEqual(
            august,
            {
                "FR-R1r1": {"Gabriel Attal": 43, "Marine Le Pen": 57},
                "FR-R3r1": {"Jean-Luc Mélenchon": 32, "Marine Le Pen": 68},
                "FR-R4r1": {"Édouard Philippe": 45, "Marine Le Pen": 55},
            },
        )

    def test_unreviewed_source_structure_drift_fails_closed(self) -> None:
        changed = copy.deepcopy(self.parsed)
        section = next(
            item
            for item in changed["tocdata"]["sections"]
            if item["line"] == "Sondages concernant le second tour"
        )
        section["line"] = "Sondages de second tour non audités"
        with self.assertRaisesRegex(SourceDriftError, "heading hierarchy changed"):
            rehearse_migration(changed)

    def test_cutover_keeps_the_scheduled_source_and_integration_boundary_explicit(
        self,
    ) -> None:
        contract = phase4a_cutover_contract()
        self.assertEqual(contract["phase"], "cutover")
        self.assertEqual(contract["production_source"], "french_wikipedia_scheduled")
        self.assertEqual(
            tuple(contract["phase4_production_modification_files"]),
            PHASE4_PRODUCTION_MODIFICATION_FILES,
        )
        self.assertEqual(
            contract["phase4_protected_logic_files"],
            list(PHASE4_PROTECTED_LOGIC_SHA256),
        )
        self.assertEqual(contract["make_event_id_probes"], EVENT_ID_CONTRACT_PROBES)
        self.assertEqual(
            contract["audited_cutover_counts"],
            {
                "retained_first_round_ids": 203,
                "retained_second_round_ids": 38,
                "new_first_round": 29,
                "new_second_round": 12,
                "reconciled_first_round": 232,
                "reconciled_second_round": 50,
            },
        )

        workflow_path = ROOT / ".github/workflows/update-polls.yml"
        real_read_text = Path.read_text

        def read_without_previous_second_round(
            path: Path, *args: object, **kwargs: object
        ) -> str:
            content = real_read_text(path, *args, **kwargs)
            if path == workflow_path:
                return content.replace(
                    "--previous-second-round second_round_polls.json",
                    "",
                )
            return content

        with (
            patch.object(Path, "read_text", new=read_without_previous_second_round),
            self.assertRaisesRegex(
                RehearsalError,
                "current polling workflow contract changed",
            ),
        ):
            phase4a_cutover_contract()

    def test_valid_post_audit_french_body_row_is_normally_ingested(self) -> None:
        parsed = post_audit_french_row_fixture()
        previous_first = read_pre_cutover_first_round()
        previous_second = read_pre_cutover_second_round()
        result = reconcile_french_production_source(
            parsed,
            previous_first,
            previous_second,
        )
        self.assertEqual(
            (len(result.first_round_events), len(result.second_round_events)),
            (233, 50),
        )
        self.assertEqual(
            result.report["audited_additions_introduced"],
            {FIRST_ROUND: 29, SECOND_ROUND: 12},
        )
        self.assertEqual(
            result.report["normal_post_audit_additions"],
            {FIRST_ROUND: 1, SECOND_ROUND: 0},
        )
        added = [
            event
            for event in result.first_round_events
            if event["source_url"]
            == "https://example.test/post-audit-french-poll"
        ]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["pollster"], "Ipsos")

    def test_post_audit_table_header_mutation_still_fails_closed(self) -> None:
        parsed = post_audit_french_row_fixture()
        document = lxml_html.fromstring(parsed["text"])
        header = document.xpath("//table")[0].xpath(".//th")[0]
        header.text = header.text_content() + " schema mutation"
        parsed["text"] = lxml_html.tostring(document, encoding="unicode")
        with self.assertRaisesRegex(SourceDriftError, "table/header schema"):
            reconcile_french_production_source(
                parsed,
                read_pre_cutover_first_round(),
                read_pre_cutover_second_round(),
            )

    def test_make_event_id_remains_source_sensitive_while_factual_key_does_not(
        self,
    ) -> None:
        event = {
            "round": FIRST_ROUND,
            "pollster": "Harris Interactive",
            "fieldwork_start": "2026-08-18",
            "fieldwork_end": "2026-08-19",
            "sample_size": 1764,
            "sample_scope": "registered_voters",
            "source_url": "https://example.test/english",
            "candidates": [
                {"name": "Gabriel Attal", "score": 14},
                {"name": "Marine Le Pen", "score": 38},
                {"name": "Jean-Luc Mélenchon", "score": 17},
            ],
        }
        migrated = copy.deepcopy(event)
        migrated["source_url"] = "https://example.test/french"
        self.assertEqual(exact_factual_key(event), exact_factual_key(migrated))
        first_id = make_event_id(
            event["pollster"],
            event["fieldwork_start"],
            event["fieldwork_end"],
            "source transition probe",
            event["source_url"],
        )
        migrated_id = make_event_id(
            migrated["pollster"],
            migrated["fieldwork_start"],
            migrated["fieldwork_end"],
            "source transition probe",
            migrated["source_url"],
        )
        self.assertNotEqual(first_id, migrated_id)

    def test_future_fifty_event_runoff_state_has_no_duplicate_factual_matchups(
        self,
    ) -> None:
        result = rehearse_pre_cutover(copy.deepcopy(self.parsed))
        keys = [
            exact_factual_key(
                event, sample_scope=event.get("sample_scope", "reported")
            )
            for event in result.second_round_events
        ]
        self.assertEqual(len(keys), 50)
        self.assertEqual(len(set(keys)), 50)
        current_ids = {
            event["event_id"]
            for event in read_pre_cutover_second_round()
        }
        self.assertTrue(
            current_ids
            <= {event["event_id"] for event in result.second_round_events}
        )

    def test_production_validators_reject_mutated_rehearsal_events(self) -> None:
        result = rehearse_pre_cutover(copy.deepcopy(self.parsed))
        first = copy.deepcopy(result.first_round_events[-1])
        first["candidates"][0]["score"] = -1
        with self.assertRaises(PollContractError):
            validate_poll_events([first])
        second = copy.deepcopy(result.second_round_events[-1])
        second["candidates"].append(copy.deepcopy(second["candidates"][0]))
        with self.assertRaisesRegex(ValueError, "exactly two candidates"):
            validate_second_round_event(second)


class RegistryAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_migration_registry()
        cls.current_first = read_pre_cutover_first_round()
        cls.current_second = read_pre_cutover_second_round()

    def test_exact_audited_acceptance_table(self) -> None:
        self.assertEqual(
            self.registry["acceptance"],
            {
                "current_first_round_preserved": 203,
                "current_second_round_preserved": 38,
                "french_new_first_round": 29,
                "french_new_second_round": 12,
                "source_only_migrations": 102,
                "reviewed_reconciliation_mappings": 73,
                "unexplained_historical_losses": 0,
                "unresolved_accepted_identity_ambiguities": 0,
                "duplicate_canonical_factual_identities": 0,
                "fail_closed_french_rows": 8,
            },
        )

    def test_registry_mapping_counts_and_round_splits(self) -> None:
        source_only = Counter(
            key_dict(record)["round"]
            for record in self.registry["source_only_identity_migrations"]
        )
        reviewed = Counter(
            key_dict(record)["round"]
            for record in self.registry["reviewed_reconciliations"]
        )
        self.assertEqual(source_only, Counter({FIRST_ROUND: 90, SECOND_ROUND: 12}))
        self.assertEqual(reviewed, Counter({FIRST_ROUND: 59, SECOND_ROUND: 14}))
        self.assertEqual(
            [len(self.registry["french_additions"][round_name]) for round_name in (FIRST_ROUND, SECOND_ROUND)],
            [29, 12],
        )

    def test_all_current_event_ids_are_explicitly_preserved(self) -> None:
        mapped = {
            record["retained_event_id"]
            for section in (
                "source_only_identity_migrations",
                "reviewed_reconciliations",
            )
            for record in self.registry[section]
        }
        persisted = {
            round_name: {
                record["event_id"]
                for record in self.registry["persistence_obligations"][round_name]
            }
            for round_name in (FIRST_ROUND, SECOND_ROUND)
        }
        current = {
            FIRST_ROUND: {record["event_id"] for record in self.current_first},
            SECOND_ROUND: {record["event_id"] for record in self.current_second},
        }
        for round_name, exact_same_source_count in (
            (FIRST_ROUND, 10),
            (SECOND_ROUND, 10),
        ):
            round_mapped = {
                record["retained_event_id"]
                for section in (
                    "source_only_identity_migrations",
                    "reviewed_reconciliations",
                )
                for record in self.registry[section]
                if key_dict(record)["round"] == round_name
            }
            self.assertTrue(round_mapped <= current[round_name])
            self.assertTrue(persisted[round_name] <= current[round_name])
            common_same_source = current[round_name] - round_mapped - persisted[round_name]
            self.assertEqual(len(common_same_source), exact_same_source_count)
            self.assertEqual(
                round_mapped | persisted[round_name] | common_same_source,
                current[round_name],
            )
        self.assertEqual((len(current[FIRST_ROUND]), len(current[SECOND_ROUND])), (203, 38))

    def test_no_duplicate_canonical_factual_identities(self) -> None:
        keys = [
            json.dumps(record["canonical_factual_key"], sort_keys=True)
            for section in (
                "source_only_identity_migrations",
                "reviewed_reconciliations",
            )
            for record in self.registry[section]
        ] + [
            json.dumps(record["factual_key"], sort_keys=True)
            for round_name in (FIRST_ROUND, SECOND_ROUND)
            for record in self.registry["french_additions"][round_name]
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_ambiguous_bardella_le_pen_rows_are_explicit_skips(self) -> None:
        self.assertEqual(
            {record["source_locator"] for record in self.registry["identity_skips"]},
            {"FR-T1R9", "FR-T1R10", "FR-T1R11"},
        )
        self.assertTrue(
            all(
                record["reason_code"] == "ambiguous_candidate_identity"
                for record in self.registry["identity_skips"]
            )
        )


class ReviewedDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_migration_registry()

    def assert_sample_decision(
        self, start: str, pollster: str, old: int, incoming: int, canonical: int
    ) -> None:
        records = reviewed_records(self.registry, start=start, pollster=pollster)
        self.assertGreater(len(records), 0)
        for record in records:
            with self.subTest(locator=record["incoming_source_locator"]):
                self.assertEqual(key_dict(record, "old_factual_key")["sample_size"], old)
                self.assertEqual(key_dict(record, "incoming_factual_key")["sample_size"], incoming)
                self.assertEqual(key_dict(record)["sample_size"], canonical)
                self.assertTrue(record["evidence_urls"])

    def test_focused_reviewed_sample_decisions(self) -> None:
        for decision in (
            ("2026-07-07", "harris-interactive", 1582, 1592, 1592),
            ("2026-05-26", "ifop", 1368, 1501, 1368),
            ("2026-03-25", "odoxa", 1005, 1299, 1299),
            ("2025-09-30", "cluster17", 1534, 1531, 1451),
            ("2025-09-24", "ifop", 1210, 1127, 1127),
            ("2023-10-24", "ifop", 1179, 1084, 1084),
            ("2023-04-12", "opinionway", 1038, 965, 965),
            ("2022-11-04", "cluster17", 2151, 2096, 2096),
            ("2022-10-25", "ifop", 1125, 1126, 1126),
        ):
            with self.subTest(start=decision[0], pollster=decision[1]):
                self.assert_sample_decision(*decision)

    def test_ifop_march_2025_date_correction_is_reviewed(self) -> None:
        records = reviewed_records(self.registry, start="2025-03-26", pollster="ifop")
        self.assertEqual(len(records), 3)
        for record in records:
            self.assertEqual(
                (key_dict(record, "incoming_factual_key")["fieldwork_start"], key_dict(record, "incoming_factual_key")["fieldwork_end"]),
                ("2025-03-21", "2025-03-26"),
            )
            self.assertEqual(
                (key_dict(record)["fieldwork_start"], key_dict(record)["fieldwork_end"]),
                ("2025-03-26", "2025-03-27"),
            )

    def test_all_eight_audited_score_decisions_are_explicit(self) -> None:
        records = [
            record
            for record in self.registry["reviewed_reconciliations"]
            if "candidates" in record.get("field_decisions", {})
        ]
        self.assertEqual(len(records), 8)
        expected_locators = {
            "FR-T3R23",
            "FR-T4R18",
            "FR-T4R16",
            "FR-T0R9",
            "FR-T2R3",
            "FR-T0R8",
            "FR-T4R17",
            "FR-T4R15",
        }
        self.assertEqual(
            {record["incoming_source_locator"] for record in records},
            expected_locators,
        )
        for record in records:
            decision = record["field_decisions"]["candidates"]
            self.assertNotEqual(decision["old"], decision["incoming"])
            self.assertIn(decision["canonical"], (decision["old"], decision["incoming"]))
            self.assertEqual(decision["canonical"], key_dict(record)["candidates"])

    def test_ifop_hexagone_alias_is_wave_scoped_only(self) -> None:
        self.assertEqual(
            apply_wave_scoped_pollster_alias(
                "Ifop", "2025-04-11", "2025-04-18", 9128, self.registry
            ),
            "ifop-hexagone",
        )
        self.assertEqual(
            apply_wave_scoped_pollster_alias(
                "Ifop", "2025-04-11", "2025-04-18", 9127, self.registry
            ),
            "ifop",
        )
        self.assertEqual(
            apply_wave_scoped_pollster_alias(
                "Ifop", "2026-05-26", "2026-05-28", 1368, self.registry
            ),
            "ifop",
        )


class FactualIdentityTests(unittest.TestCase):
    def sample_event(self) -> dict:
        return {
            "round": SECOND_ROUND,
            "pollster": "Harris Interactive / Toluna",
            "fieldwork_start": "2026-08-18",
            "fieldwork_end": "2026-08-19",
            "sample_size": 1764,
            "sample_scope": "registered_voters",
            "source_url": "https://example.test/english",
            "candidates": [
                {"name": "Marine Le Pen", "score": 57.0},
                {"name": "Attal", "score": 43},
            ],
        }

    def test_exact_key_is_source_independent_and_score_exact(self) -> None:
        event = self.sample_event()
        changed_source = copy.deepcopy(event)
        changed_source["source_url"] = "https://example.test/french"
        changed_order = copy.deepcopy(changed_source)
        changed_order["candidates"].reverse()
        self.assertEqual(exact_factual_key(event), exact_factual_key(changed_source))
        self.assertEqual(exact_factual_key(event), exact_factual_key(changed_order))
        self.assertEqual(
            exact_factual_key(event).candidates,
            (("gabriel-attal", "43"), ("marine-le-pen", "57")),
        )
        changed_score = copy.deepcopy(event)
        changed_score["candidates"][0]["score"] = 56.9
        self.assertNotEqual(exact_factual_key(event), exact_factual_key(changed_score))

    def test_sample_scope_is_mandatory_and_part_of_the_key(self) -> None:
        event = self.sample_event()
        event.pop("sample_scope")
        with self.assertRaisesRegex(ValueError, "sample_scope"):
            exact_factual_key(event)
        registered = exact_factual_key(event, sample_scope="registered_voters")
        reported = exact_factual_key(event, sample_scope="reported")
        self.assertNotEqual(registered, reported)

    def test_review_anchor_is_only_a_weaker_lookup_aid(self) -> None:
        first = self.sample_event()
        second = copy.deepcopy(first)
        second["sample_size"] = 999
        second["candidates"][0]["score"] = 60
        second["candidates"][1]["score"] = 40
        self.assertEqual(review_anchor(first), review_anchor(second))
        self.assertNotEqual(exact_factual_key(first), exact_factual_key(second))

    def test_generic_ambiguous_and_unseen_candidates_remain_rejected(self) -> None:
        labels = (
            "Candidat RN",
            "Bardella / Le Pen",
            "Candidat PS / PP",
            "Candidat EPR",
            "Candidat LR",
            "Autre(s)",
            "Entirely Unseen Candidate",
        )
        for label in labels:
            with self.subTest(label=label), self.assertRaises(ValueError):
                reviewed_candidate_name(label)


class RegistryValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_migration_registry()

    def mutated(self) -> dict:
        return copy.deepcopy(self.registry)

    def test_duplicate_legacy_ids_fail_closed(self) -> None:
        payload = self.mutated()
        payload["source_only_identity_migrations"][1]["legacy_event_id"] = payload[
            "source_only_identity_migrations"
        ][0]["legacy_event_id"]
        with self.assertRaisesRegex(ValueError, "duplicate legacy event ID"):
            validate_migration_registry(payload)

    def test_duplicate_canonical_mappings_fail_closed(self) -> None:
        payload = self.mutated()
        records = payload["source_only_identity_migrations"]
        records[1]["old_factual_key"] = copy.deepcopy(records[0]["old_factual_key"])
        records[1]["incoming_factual_key"] = copy.deepcopy(records[0]["incoming_factual_key"])
        records[1]["canonical_factual_key"] = copy.deepcopy(records[0]["canonical_factual_key"])
        with self.assertRaisesRegex(ValueError, "duplicate canonical mapping"):
            validate_migration_registry(payload)

    def test_malformed_factual_key_fails_closed(self) -> None:
        payload = self.mutated()
        payload["source_only_identity_migrations"][0]["canonical_factual_key"][
            "sample_size"
        ] = "1000"
        with self.assertRaisesRegex(ValueError, "sample_size"):
            validate_migration_registry(payload)

    def test_unsupported_treatment_fails_closed(self) -> None:
        payload = self.mutated()
        payload["source_only_identity_migrations"][0]["treatment"] = "guess"
        with self.assertRaisesRegex(ValueError, "treatment is unsupported"):
            validate_migration_registry(payload)

    def test_reviewed_correction_without_evidence_fails_closed(self) -> None:
        payload = self.mutated()
        payload["reviewed_reconciliations"][0]["evidence_urls"] = []
        with self.assertRaisesRegex(ValueError, "evidence_urls"):
            validate_migration_registry(payload)

    def test_contradictory_field_decision_fails_closed(self) -> None:
        payload = self.mutated()
        record = next(
            item
            for item in payload["reviewed_reconciliations"]
            if "sample_size" in item["field_decisions"]
        )
        record["field_decisions"]["sample_size"]["canonical"] = 1
        with self.assertRaisesRegex(ValueError, "contradicts its factual key"):
            validate_migration_registry(payload)

    def test_ambiguous_source_locator_fails_closed(self) -> None:
        payload = self.mutated()
        records = payload["source_only_identity_migrations"]
        records[1]["incoming_source_locator"] = records[0]["incoming_source_locator"]
        records[1]["retained_event_id"] = records[0]["retained_event_id"]
        with self.assertRaisesRegex(ValueError, "ambiguous source locator"):
            validate_migration_registry(payload)

    def test_incoming_mapping_to_multiple_retained_ids_fails_closed(self) -> None:
        payload = self.mutated()
        records = payload["source_only_identity_migrations"]
        records[1]["incoming_source_locator"] = records[0]["incoming_source_locator"]
        self.assertNotEqual(records[1]["retained_event_id"], records[0]["retained_event_id"])
        with self.assertRaisesRegex(ValueError, "multiple retained IDs"):
            validate_migration_registry(payload)


class RunoffPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_migration_registry()
        cls.current = read_pre_cutover_second_round()
        cls.fr = parse_french_frozen_fixture(
            load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)
        )["second_round"]

    def test_audited_runoff_continuity_accounting(self) -> None:
        self.assertEqual(
            reconcile_runoff_continuity(self.current, self.registry),
            {
                "current_preserved": 38,
                "reviewed_different_representations": 14,
                "source_only_reconciliations": 12,
                "english_only_historical_preserved": 2,
                "french_new": 12,
                "expected_post_migration": 50,
            },
        )

    def test_future_previous_second_round_merge_preserves_ids_without_duplicates(self) -> None:
        current_by_id = {event["event_id"]: event for event in self.current}
        mapping_records = [
            record
            for section in (
                "source_only_identity_migrations",
                "reviewed_reconciliations",
            )
            for record in self.registry[section]
            if key_dict(record)["round"] == SECOND_ROUND
        ]
        mapped_by_locator = {
            record["incoming_source_locator"]: record for record in mapping_records
        }
        additions = {
            record["source_locator"]: record
            for record in self.registry["french_additions"][SECOND_ROUND]
        }
        current_by_reported_key = {
            exact_factual_key(event, sample_scope="reported"): event
            for event in self.current
        }
        fresh: list[dict] = []
        for frozen in self.fr:
            locator = frozen["source_locator"]
            if locator in mapped_by_locator or locator in additions:
                fresh.append(production_runoff(frozen))
                continue
            current = current_by_reported_key[exact_factual_key(frozen)]
            exact = copy.deepcopy(current)
            exact["migration_source_locator"] = locator
            fresh.append(exact)

        self.assertEqual(len(fresh), 48)
        merged, reconciled = merge_previous_second_round_events(
            fresh, self.current, self.registry
        )
        merged_ids = {event["event_id"] for event in merged}
        self.assertEqual(reconciled, 26)
        self.assertEqual(len(merged), 50)
        self.assertEqual(len(merged_ids), 50)
        self.assertTrue(set(current_by_id) <= merged_ids)
        self.assertEqual(
            sum(
                production_runoff(frozen)["event_id"] in merged_ids
                for frozen in self.fr
                if frozen["source_locator"] in additions
            ),
            12,
        )
        historical_ids = {
            record["event_id"]
            for record in self.registry["persistence_obligations"][SECOND_ROUND]
        }
        self.assertEqual(len(historical_ids), 2)
        self.assertTrue(historical_ids <= merged_ids)

    def test_review_anchor_never_reconciles_without_an_explicit_locator(self) -> None:
        old = self.current[0]
        unregistered = copy.deepcopy(old)
        unregistered["hypothesis"] += " explicit-unregistered-copy"
        unregistered["event_id"] = make_event_id(
            unregistered["pollster"],
            unregistered["fieldwork_start"],
            unregistered["fieldwork_end"],
            unregistered["hypothesis"],
            unregistered["source_url"],
            round_name=SECOND_ROUND,
        )
        validate_second_round_event(unregistered)
        merged, reconciled = merge_previous_second_round_events(
            [unregistered], self.current, self.registry
        )
        self.assertEqual(reconciled, 0)
        self.assertEqual(len(merged), 39)


if __name__ == "__main__":
    unittest.main()
