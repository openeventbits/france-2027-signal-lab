import unittest
from pathlib import Path


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
            "test_campaign_agenda_evidence.py",
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

    def test_generated_wire_still_uses_canonical_validator(self):
        self.assertIn(
            "validate_output(wire)",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
