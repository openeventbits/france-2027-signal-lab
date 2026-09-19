import hashlib
import json
import unittest
from pathlib import Path

from lxml import html as lxml_html

from fetch_polls import (
    SECOND_ROUND,
    integrate_french_migration_source,
)
from poll_contract import make_event_id
from poll_migration import (
    FRENCH_FIXTURE,
    _french_runoff_table_plan,
    exact_factual_key,
    load_mediawiki_fixture,
    parse_french_frozen_fixture,
)
from rehearse_fr_poll_migration import (
    RehearsalError,
    reconcile_french_production_source,
)


ROOT = Path(__file__).parent

CURRENT_REVISION = 239587014
CURRENT_FIXTURE = (
    ROOT
    / "test_fixtures"
    / "fr27_polling"
    / f"fr_mediawiki_{CURRENT_REVISION}.json"
)

PREVIOUS_FIRST = (
    ROOT
    / "test_fixtures"
    / "fr27_polling"
    / "post_audit_first_round_9579b90.json"
)

PREVIOUS_SECOND = (
    ROOT
    / "test_fixtures"
    / "fr27_polling"
    / "post_audit_second_round_9579b90.json"
)

EXPECTED_FIXTURE_SHA256 = (
    "97051c09f1bd692c62537618de95f41522b1846f9b6ab4bd6c3c2d4b21e6756e"
)

COMMISSION_IFOP_HEXAGONE = (
    "https://www.commission-des-sondages.fr/notices/files/notices/"
    "2025/mai/9930-pres-ifop-hexagone-5-mai.pdf"
)

SUPERSEDED_IFOP_EVENT_ID = (
    "aa99294773918e4dc5adaffaba64d09f714516d7e4b579a7344a0ed4b97d468a"
)

REPLACEMENT_IFOP_EVENT_ID = (
    "aef3b324f95d30232427645bc4571fc487509755f70742b012b9301db9a16649"
)


def candidate_key(*items):
    return tuple(sorted(items))


CURRENT_SOURCE = {
    "FR-R4r14": (
        "ifop",
        "2025-04-29",
        "2025-04-30",
        1838,
        candidate_key(
            ("edouard-philippe", "52"),
            ("marine-le-pen", "48"),
        ),
    ),
    "FR-R7r2": (
        "odoxa",
        "2025-11-19",
        "2025-11-20",
        1300,
        candidate_key(
            ("gabriel-attal", "44"),
            ("jordan-bardella", "56"),
        ),
    ),
    "FR-R7r3": (
        "ifop",
        "2025-04-11",
        "2025-04-18",
        9128,
        candidate_key(
            ("gabriel-attal", "48"),
            ("jordan-bardella", "52"),
        ),
    ),
    "FR-R8r2": (
        "odoxa",
        "2025-11-19",
        "2025-11-20",
        1300,
        candidate_key(
            ("jordan-bardella", "58"),
            ("raphael-glucksmann", "42"),
        ),
    ),
    "FR-R9r3": (
        "odoxa",
        "2025-11-19",
        "2025-11-20",
        1300,
        candidate_key(
            ("jean-luc-melenchon", "26"),
            ("jordan-bardella", "74"),
        ),
    ),
    "FR-R9r4": (
        "ifop",
        "2025-04-11",
        "2025-04-18",
        9128,
        candidate_key(
            ("jean-luc-melenchon", "33"),
            ("jordan-bardella", "67"),
        ),
    ),
    "FR-R10r4": (
        "odoxa",
        "2026-03-25",
        "2026-03-26",
        1299,
        candidate_key(
            ("edouard-philippe", "52"),
            ("jordan-bardella", "48"),
        ),
    ),
    "FR-R10r5": (
        "odoxa",
        "2025-11-19",
        "2025-11-20",
        1300,
        candidate_key(
            ("edouard-philippe", "47"),
            ("jordan-bardella", "53"),
        ),
    ),
    "FR-R10r6": (
        "ifop",
        "2025-04-11",
        "2025-04-18",
        9128,
        candidate_key(
            ("edouard-philippe", "50"),
            ("jordan-bardella", "50"),
        ),
    ),
    "FR-R11r2": (
        "ifop",
        "2025-04-11",
        "2025-04-18",
        9128,
        candidate_key(
            ("bruno-retailleau", "47"),
            ("jordan-bardella", "53"),
        ),
    ),
}


RETAINED_SAMPLE_CORRECTIONS = {
    "75ed87a4a48d81558c42f89166562c80f26ca80c12126d20a5c3de591b1bea3f": 776,
    "35d60d5654ce84831234eacb14e214eb40d29f7123249a96d0c9f5070d1acc92": 795,
    "fc7fa8547298e5e76d9157730548fbf2e260526eb386a56b0a9ad2e608ba9209": 689,
    "0a128d1a04d4987eef7023fef8c544869788d018edf2a8c8fa9e3c78c4cdc941": 803,
    "f7a3b8a301038c0e4233e412894d9c43e1ebf44e9a68243a145cdc2b8f4c3436": 812,
}


SOURCE_DRIFT_ONLY_RETAINED = {
    "d479888da6e05531ab54707e992f04da151d82128c632fac33f257f057f63e6c",
    "bae60c73fe365cadcc1cc4f6db5f2c0b3054d68f0ec6c90f4914994d6d25f5a2",
    "cfb9ecc41fc4fbc37065a249bb18b1f5be781096e7662bae869879326087221f",
    "b8473b739910f3b9b2a62cbf1c379188e3e8c9eb4fff92754a8419d4763514b1",
}


def read_previous_first():
    payload = json.loads(PREVIOUS_FIRST.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise AssertionError("previous first-round fixture is malformed")
    return payload


def read_previous_second():
    payload = json.loads(PREVIOUS_SECOND.read_text(encoding="utf-8"))
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        raise AssertionError("previous second-round fixture is malformed")
    return events


def event_facts(event):
    return {
        "pollster": event["pollster"],
        "fieldwork_start": event["fieldwork_start"],
        "fieldwork_end": event["fieldwork_end"],
        "sample_size": event["sample_size"],
        "candidates": tuple(
            sorted(
                (candidate["name"], candidate["score"])
                for candidate in event["candidates"]
            )
        ),
    }


class CurrentSecondRoundEvidenceDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_mediawiki_fixture(
            CURRENT_FIXTURE,
            CURRENT_REVISION,
        )
        cls.parsed = parse_french_frozen_fixture(cls.fixture)
        cls.rows = {
            record["source_locator"]: record
            for record in cls.parsed[SECOND_ROUND]
            if record["source_locator"] in CURRENT_SOURCE
        }

    def test_current_revision_fixture_and_ten_raw_rows_are_exact(self):
        self.assertEqual(
            hashlib.sha256(CURRENT_FIXTURE.read_bytes()).hexdigest(),
            EXPECTED_FIXTURE_SHA256,
        )
        self.assertEqual(self.fixture["revid"], CURRENT_REVISION)
        self.assertEqual(set(self.rows), set(CURRENT_SOURCE))

        for locator, expected in CURRENT_SOURCE.items():
            with self.subTest(locator=locator):
                key = exact_factual_key(
                    self.rows[locator],
                    sample_scope="reported",
                )
                actual = (
                    key.pollster_identity,
                    key.fieldwork_start,
                    key.fieldwork_end,
                    key.sample_size,
                    tuple(key.candidates),
                )
                self.assertEqual(actual, expected)

    def test_source_can_adopt_reviewed_matchup_samples(self):
        fixture = json.loads(json.dumps(self.fixture))
        document = lxml_html.fromstring(fixture["text"])
        replacements = {
            "FR-R7r2": 776,
            "FR-R8r2": 795,
            "FR-R10r4": 812,
            "FR-R10r5": 803,
        }
        replaced = set()

        for family_locator, table in _french_runoff_table_plan(
            document.xpath("//table")
        ):
            rows = table.xpath(".//tr[td]")
            for row_index, row in enumerate(rows):
                locator = f"{family_locator}r{row_index}"
                if locator not in replacements:
                    continue

                cells = row.xpath("./td")
                if len(cells) < 3:
                    raise AssertionError(
                        f"{locator} lacks the expected sample cell"
                    )

                cells[2].clear()
                cells[2].text = str(replacements[locator])
                replaced.add(locator)

        self.assertEqual(replaced, set(replacements))

        fixture["text"] = lxml_html.tostring(
            document,
            encoding="unicode",
        )
        fixture["revid"] += 1

        result = reconcile_french_production_source(
            fixture,
            read_previous_first(),
            read_previous_second(),
        )

        after = {
            event["event_id"]: event
            for event in result.second_round_events
        }

        for event_id, sample_size in RETAINED_SAMPLE_CORRECTIONS.items():
            with self.subTest(event_id=event_id):
                self.assertEqual(
                    after[event_id]["sample_size"],
                    sample_size,
                )

        self.assertEqual(
            result.report["second_round_evidence_reconciliations"],
            {
                "retain_existing": 4,
                "correct_retained_sample": 5,
                "supersede_event": 1,
            },
        )

    def test_one_ifop_event_is_explicitly_superseded(self):
        previous_first = read_previous_first()
        previous_second = read_previous_second()

        result = reconcile_french_production_source(
            self.fixture,
            previous_first,
            previous_second,
        )

        before = {
            event["event_id"]: event
            for event in previous_second
        }
        after = {
            event["event_id"]: event
            for event in result.second_round_events
        }

        row = self.rows["FR-R4r14"]

        self.assertEqual(row["source_url"], COMMISSION_IFOP_HEXAGONE)

        hypothesis = (
            "Second round — "
            + " vs ".join(candidate["name"] for candidate in row["candidates"])
        )

        replacement_id = make_event_id(
            row["pollster"],
            row["fieldwork_start"],
            row["fieldwork_end"],
            hypothesis,
            row["source_url"],
            round_name=SECOND_ROUND,
        )

        self.assertEqual(
            set(before) - set(after),
            {SUPERSEDED_IFOP_EVENT_ID},
        )
        self.assertNotIn(SUPERSEDED_IFOP_EVENT_ID, after)
        self.assertIn(replacement_id, after)

        replacement = after[replacement_id]

        self.assertEqual(replacement["pollster"], "Ifop")
        self.assertEqual(
            (
                replacement["fieldwork_start"],
                replacement["fieldwork_end"],
            ),
            ("2025-04-29", "2025-04-30"),
        )
        self.assertEqual(replacement["sample_size"], 1838)
        self.assertEqual(replacement["source_url"], COMMISSION_IFOP_HEXAGONE)
        self.assertEqual(replacement["candidates"], row["candidates"])

    def test_production_integration_accepts_only_reviewed_supersession(self):
        previous_first = read_previous_first()
        previous_second = read_previous_second()

        _first, second, report, _official = integrate_french_migration_source(
            self.fixture,
            previous_first,
            previous_second,
            [],
        )

        before_ids = {
            event["event_id"]
            for event in previous_second
        }
        after_ids = {
            event["event_id"]
            for event in second
        }

        row = self.rows["FR-R4r14"]

        hypothesis = (
            "Second round — "
            + " vs ".join(
                candidate["name"]
                for candidate in row["candidates"]
            )
        )

        replacement_id = make_event_id(
            row["pollster"],
            row["fieldwork_start"],
            row["fieldwork_end"],
            hypothesis,
            row["source_url"],
            round_name=SECOND_ROUND,
        )

        self.assertEqual(
            before_ids - after_ids,
            {SUPERSEDED_IFOP_EVENT_ID},
        )

        added_ids = after_ids - before_ids
        self.assertIn(replacement_id, added_ids)

        direct = reconcile_french_production_source(
            self.fixture,
            previous_first,
            previous_second,
        )
        direct_ids = {
            event["event_id"]
            for event in direct.second_round_events
        }

        self.assertEqual(after_ids, direct_ids)

        self.assertEqual(
            report["superseded_second_round_event_ids"],
            [SUPERSEDED_IFOP_EVENT_ID],
        )
        self.assertEqual(
            report["second_round_evidence_reconciliations"],
            {
                "retain_existing": 4,
                "correct_retained_sample": 5,
                "supersede_event": 1,
            },
        )


    def test_production_integration_rejects_unknown_superseded_event_id(self):
        from unittest.mock import patch

        previous_first = read_previous_first()
        previous_second = read_previous_second()

        fake = reconcile_french_production_source(
            self.fixture,
            previous_first,
            previous_second,
        )
        fake.report["superseded_second_round_event_ids"] = ["0" * 64]

        with patch(
            "rehearse_fr_poll_migration.reconcile_french_production_source",
            return_value=fake,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "reported unknown superseded second-round event IDs",
            ):
                integrate_french_migration_source(
                    self.fixture,
                    previous_first,
                    previous_second,
                    [],
                )

    def test_production_integration_rejects_superseded_event_still_retained(self):
        from unittest.mock import patch

        previous_first = read_previous_first()
        previous_second = read_previous_second()

        fake = reconcile_french_production_source(
            self.fixture,
            previous_first,
            previous_second,
        )

        previous_ids = {
            event["event_id"]
            for event in previous_second
        }
        final_ids = {
            event["event_id"]
            for event in fake.second_round_events
        }
        retained_id = sorted(previous_ids & final_ids)[0]

        fake.report["superseded_second_round_event_ids"] = [retained_id]

        with patch(
            "rehearse_fr_poll_migration.reconcile_french_production_source",
            return_value=fake,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "retained an event reported as superseded",
            ):
                integrate_french_migration_source(
                    self.fixture,
                    previous_first,
                    previous_second,
                    [],
                )

    def test_historical_fixture_accepts_exact_registered_successor_after_supersession(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = payload["events"]

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        result = reconcile_french_production_source(
            historical_fixture,
            previous_first,
            previous_second,
        )

        after = {
            event["event_id"]: event
            for event in result.second_round_events
        }

        self.assertNotIn(SUPERSEDED_IFOP_EVENT_ID, after)
        self.assertIn(REPLACEMENT_IFOP_EVENT_ID, after)

    def test_historical_fixture_rejects_missing_registered_successor(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = [
            event
            for event in payload["events"]
            if event["event_id"] != REPLACEMENT_IFOP_EVENT_ID
        ]

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        with self.assertRaisesRegex(
            RehearsalError,
            "reviewed mapping supersession replacement is absent",
        ):
            reconcile_french_production_source(
                historical_fixture,
                previous_first,
                previous_second,
            )

    def test_historical_fixture_rejects_mutated_registered_successor(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = json.loads(json.dumps(payload["events"]))

        replacement = next(
            event
            for event in previous_second
            if event["event_id"] == REPLACEMENT_IFOP_EVENT_ID
        )
        replacement["sample_size"] = 1839

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        with self.assertRaisesRegex(
            RehearsalError,
            "reviewed mapping supersession replacement facts changed",
        ):
            reconcile_french_production_source(
                historical_fixture,
                previous_first,
                previous_second,
            )

    def test_current_evidence_application_is_idempotent_on_second_pass(self):
        previous_first = read_previous_first()
        previous_second = read_previous_second()

        first = reconcile_french_production_source(
            self.fixture,
            previous_first,
            previous_second,
        )

        second = reconcile_french_production_source(
            self.fixture,
            first.first_round_events,
            first.second_round_events,
        )

        first_first = {
            event["event_id"]: event
            for event in first.first_round_events
        }
        second_first = {
            event["event_id"]: event
            for event in second.first_round_events
        }
        first_second = {
            event["event_id"]: event
            for event in first.second_round_events
        }
        second_second = {
            event["event_id"]: event
            for event in second.second_round_events
        }

        self.assertEqual(second_first, first_first)
        self.assertEqual(second_second, first_second)
        self.assertEqual(
            second.report["superseded_second_round_event_ids"],
            [],
        )

    def test_historical_fixture_post_evidence_replay_is_exact_noop_for_all_ten_records(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = payload["events"]

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        result = reconcile_french_production_source(
            historical_fixture,
            previous_first,
            previous_second,
        )

        before_first = {
            event["event_id"]: event
            for event in previous_first
        }
        after_first = {
            event["event_id"]: event
            for event in result.first_round_events
        }
        before_second = {
            event["event_id"]: event
            for event in previous_second
        }
        after_second = {
            event["event_id"]: event
            for event in result.second_round_events
        }

        self.assertEqual(after_first, before_first)
        self.assertEqual(after_second, before_second)
        self.assertEqual(
            result.report["second_round_evidence_already_applied"],
            {
                "retain_existing": 4,
                "correct_retained_sample": 5,
                "supersede_event": 1,
            },
        )
        self.assertEqual(
            result.report["superseded_second_round_event_ids"],
            [],
        )

    def test_historical_fixture_rejects_mixed_pre_and_post_evidence_state(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = json.loads(json.dumps(payload["events"]))

        pre_transition = {
            event["event_id"]: event
            for event in read_previous_second()
        }

        corrected_id = (
            "f7a3b8a301038c0e4233e412894d9c43e1ebf44e9a68243a145cdc2b8f4c3436"
        )

        previous_second = [
            pre_transition[corrected_id]
            if event["event_id"] == corrected_id
            else event
            for event in previous_second
        ]

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        with self.assertRaisesRegex(
            RehearsalError,
            "mixed second-round evidence lifecycle state",
        ):
            reconcile_french_production_source(
                historical_fixture,
                previous_first,
                previous_second,
            )

    def test_historical_fixture_rejects_both_superseded_and_replacement_ids(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = json.loads(json.dumps(payload["events"]))

        old_event = next(
            event
            for event in read_previous_second()
            if event["event_id"] == SUPERSEDED_IFOP_EVENT_ID
        )
        previous_second.append(old_event)

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        with self.assertRaisesRegex(
            RehearsalError,
            "second-round evidence supersession contains both old and replacement event IDs",
        ):
            reconcile_french_production_source(
                historical_fixture,
                previous_first,
                previous_second,
            )

    def test_historical_fixture_rejects_mutated_corrected_event_facts(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = json.loads(json.dumps(payload["events"]))

        corrected_id = (
            "f7a3b8a301038c0e4233e412894d9c43e1ebf44e9a68243a145cdc2b8f4c3436"
        )
        corrected = next(
            event
            for event in previous_second
            if event["event_id"] == corrected_id
        )
        corrected["sample_size"] = 813

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        with self.assertRaisesRegex(
            RehearsalError,
            "second-round evidence corrected event facts changed",
        ):
            reconcile_french_production_source(
                historical_fixture,
                previous_first,
                previous_second,
            )

    def test_historical_fixture_rejects_mutated_replacement_provenance(self):
        previous_first = json.loads(
            (ROOT / "polls.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (ROOT / "second_round_polls.json").read_text(encoding="utf-8")
        )
        previous_second = json.loads(json.dumps(payload["events"]))

        replacement = next(
            event
            for event in previous_second
            if event["event_id"] == REPLACEMENT_IFOP_EVENT_ID
        )
        replacement["migration_source_locator"] = "FR-R4r999"

        historical_fixture = load_mediawiki_fixture(
            FRENCH_FIXTURE,
            238906992,
        )

        with self.assertRaisesRegex(
            RehearsalError,
            "second-round evidence replacement provenance changed",
        ):
            reconcile_french_production_source(
                historical_fixture,
                previous_first,
                previous_second,
            )

    def test_five_odoxa_events_only_change_sample_size(self):
        previous_first = read_previous_first()
        previous_second = read_previous_second()

        result = reconcile_french_production_source(
            self.fixture,
            previous_first,
            previous_second,
        )

        before = {
            event["event_id"]: event
            for event in previous_second
        }
        after = {
            event["event_id"]: event
            for event in result.second_round_events
        }

        common_ids = set(before) & set(after)

        changed = {
            event_id
            for event_id in common_ids
            if event_facts(before[event_id]) != event_facts(after[event_id])
        }

        self.assertEqual(
            changed,
            set(RETAINED_SAMPLE_CORRECTIONS),
        )

        for event_id, sample_size in RETAINED_SAMPLE_CORRECTIONS.items():
            with self.subTest(event_id=event_id):
                old = before[event_id]
                new = after[event_id]

                self.assertEqual(new["event_id"], event_id)
                self.assertEqual(new["pollster"], old["pollster"])
                self.assertEqual(
                    new["fieldwork_start"],
                    old["fieldwork_start"],
                )
                self.assertEqual(
                    new["fieldwork_end"],
                    old["fieldwork_end"],
                )
                self.assertEqual(
                    new["candidates"],
                    old["candidates"],
                )
                self.assertEqual(
                    new["source_url"],
                    old["source_url"],
                )
                self.assertEqual(new["sample_size"], sample_size)

        for event_id in SOURCE_DRIFT_ONLY_RETAINED:
            with self.subTest(source_drift_only_event_id=event_id):
                self.assertEqual(
                    event_facts(after[event_id]),
                    event_facts(before[event_id]),
                )


if __name__ == "__main__":
    unittest.main()
