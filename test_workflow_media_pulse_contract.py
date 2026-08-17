import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
class WorkflowMediaPulseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = Path(
            ".github/workflows/update-news-wire.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_runs_analytical_contract_tests(self):
        for filename in (
            "test_candidate_coverage_scope.py",
            "test_candidate_identity_contract.py",
            "test_candidate_visibility_history_contract.py",
            "test_build_candidate_visibility_history.py",
            "test_campaign_agenda_evidence.py",
            "test_news_workflow_contract.py",
            "test_workflow_media_pulse_contract.py",
        ):
            with self.subTest(filename=filename):
                self.assertIn(filename, self.workflow)

    def test_workflow_uses_canonical_inventory_schema(self):
        self.assertIn(
            "INVENTORY_SCHEMA_VERSION,",
            self.workflow,
        )
        self.assertIn(
            'inventory.get("schema_version")',
            self.workflow,
        )
        self.assertIn(
            "!= INVENTORY_SCHEMA_VERSION",
            self.workflow,
        )
        self.assertNotIn(
            'inventory.get("schema_version") != 3',
            self.workflow,
        )

    def test_candidate_visibility_participates_in_change_detection(self):
        projection_start = self.workflow.index(
            "def wire_projection("
        )
        projection_end = self.workflow.index(
            "inventory_changed =",
            projection_start,
        )
        projection = self.workflow[
            projection_start:projection_end
        ]

        self.assertIn(
            '"candidate_visibility": payload.get(',
            projection,
        )
        self.assertIn(
            '"campaign_agenda": payload.get(',
            projection,
        )

    def test_workflow_accepts_partitioned_visibility_schema(self):
        for field in (
            '"primary_scopes",',
            '"secondary_scope",',
            '"general_current_period",',
            '"general_prior_period",',
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.workflow)

    def test_news_uses_registry_while_active_projection_stays_downstream(self):
        collector = (ROOT / "fetch_news_wire.py").read_text(encoding="utf-8")
        self.assertIn("from candidate_candidacy_status import (", collector)
        self.assertIn("active_news_candidate_roster(", collector)
        self.assertNotIn("active_field_visibility", collector)
        self.assertIn("build_candidate_visibility(", collector)

        fetch = self.workflow.index("python fetch_news_wire.py")
        finalized = self.workflow.index(
            "shutil.copyfile(\n                  TEMP_WIRE,\n                  CURRENT_WIRE,"
        )
        derived = self.workflow.index(
            "python -B build_candidate_signals.py",
            finalized,
        )
        self.assertLess(fetch, finalized)
        self.assertLess(finalized, derived)

    def test_candidate_visibility_history_stays_downstream_of_news(self):
        history_build = self.workflow.index(
            "python -B build_candidate_visibility_history.py"
        )

        promotion = self.workflow.index(
            "- name: Validate and promote generated data"
        )

        self.assertLess(
            history_build,
            promotion,
        )

        self.assertIn(
            "--news /tmp/news_wire.json",
            self.workflow,
        )
        self.assertIn(
            "--output /tmp/candidate_visibility_history.json",
            self.workflow,
        )
        self.assertIn(
            "validate_candidate_visibility_history(",
            self.workflow,
        )

        collector = (
            ROOT
            / "fetch_news_wire.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "candidate_visibility_history",
            collector,
        )


    def test_source_wide_candidate_visibility_contract_is_not_weakened(self):
        self.assertIn('"candidate_visibility": payload.get(', self.workflow)
        self.assertIn("validate_output(wire)", self.workflow)
        self.assertNotIn("active_field_visibility", self.workflow)

    def test_workflow_validates_agenda_classification_coverage(self):
        for contract in (
            '"classified_item_count"',
            '"unclassified_item_count"',
            '"other_campaign"',
            '"campaign_agenda classification counts "',
        ):
            with self.subTest(
                contract=contract
            ):
                self.assertIn(
                    contract,
                    self.workflow,
                )

    def test_generated_wire_still_uses_canonical_validator(self):
        self.assertIn(
            "validate_output(wire)",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
