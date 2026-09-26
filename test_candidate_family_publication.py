from __future__ import annotations

import unittest
from pathlib import Path

from build_candidate_reference import (
    SOURCE_FILES,
)


ROOT = Path(__file__).resolve().parent
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "publish-candidate-family.yml"
)


class CandidateFamilyPublicationWorkflowTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(
            encoding="utf-8"
        )

        cls.trigger = cls.text.split(
            "\npermissions:",
            1,
        )[0]

    def test_trigger_covers_every_candidate_reference_source(self):
        for filename in SOURCE_FILES.values():
            with self.subTest(
                source=filename
            ):
                self.assertIn(
                    f'- "{filename}"',
                    self.trigger,
                )

        self.assertIn(
            'cron: "41 10 * * *"',
            self.trigger,
        )

        self.assertIn(
            "workflow_dispatch:",
            self.trigger,
        )

    def test_workflow_run_follows_all_automated_source_writers(self):
        expected = (
            "Update polls",
            "Update Election News Wire",
            "Update Claims Under Scrutiny",
            "Update candidate universe",
            "Update candidate attention",
            "Validate campaign events",
        )

        self.assertIn(
            "workflow_run:",
            self.trigger,
        )

        for workflow_name in expected:
            with self.subTest(
                workflow=workflow_name
            ):
                self.assertIn(
                    f'- "{workflow_name}"',
                    self.trigger,
                )

        self.assertIn(
            "- completed",
            self.trigger,
        )

    def test_workflow_run_requires_success(self):
        self.assertIn(
            (
                "github.event_name != 'workflow_run' ||\n"
                "      github.event.workflow_run.conclusion == 'success'"
            ),
            self.text,
        )

    def test_pages_build_is_explicit_after_generated_push(self):
        self.assertIn(
            "pages: write",
            self.text,
        )

        push = self.text.index(
            "git push origin HEAD:main"
        )

        pages = self.text.index(
            "/pages/builds",
            push,
        )

        self.assertLess(
            push,
            pages,
        )

        self.assertIn(
            "Authorization: Bearer ${GH_TOKEN}",
            self.text,
        )

    def test_generated_outputs_do_not_form_push_trigger_loop(self):
        self.assertNotIn(
            '"candidates/**"',
            self.trigger,
        )

        self.assertNotIn(
            '"en/candidates/**"',
            self.trigger,
        )

        self.assertNotIn(
            '"sitemap.xml"',
            self.trigger,
        )

    def test_pipeline_rebuilds_and_checks_candidate_family_and_sitemap(self):
        self.assertGreaterEqual(
            self.text.count(
                (
                    "python -B "
                    "build_candidate_reference.py "
                    "--all-active"
                )
            ),
            2,
        )

        self.assertGreaterEqual(
            self.text.count(
                (
                    "python -B "
                    "build_route_registry.py"
                )
            ),
            2,
        )

        self.assertGreaterEqual(
            self.text.count(
                "python -B build_sitemaps.py"
            ),
            4,
        )

        self.assertIn(
            "build_candidate_reference.py --all-active --check",
            self.text,
        )

        self.assertIn(
            (
                "python -B build_route_registry.py --check"
            ),
            self.text,
        )

        self.assertIn(
            "python -B build_sitemaps.py --check",
            self.text,
        )

    def test_commit_scope_is_exact(self):
        self.assertIn(
            (
                "git add -- \\\n"
                "            candidates en/candidates \\\n"
                "            route_registry.json sitemap.xml "
                "sitemap-candidates.xml"
            ),
            self.text,
        )

        self.assertNotIn(
            "git add -A",
            self.text,
        )

        self.assertNotIn(
            "git add --all",
            self.text,
        )

    def test_rebase_rebuilds_before_push(self):
        rebase = self.text.index(
            "git rebase origin/main"
        )

        rebuild = self.text.index(
            (
                "python -B "
                "build_candidate_reference.py "
                "--all-active"
            ),
            rebase,
        )

        sitemap = self.text.index(
            (
                "python -B "
                "build_route_registry.py"
            ),
            rebuild,
        )

        push = self.text.index(
            "git push origin HEAD:main",
            sitemap,
        )

        self.assertLess(
            rebase,
            rebuild,
        )

        self.assertLess(
            rebuild,
            sitemap,
        )

        self.assertLess(
            sitemap,
            push,
        )

    def test_pipeline_runs_candidate_and_search_contracts(self):
        for test_module in (
            "test_candidate_reference",
            "test_candidate_hub",
            "test_candidate_page_contract",
            "test_candidate_family_publication",
            "test_route_registry",
            "test_search_foundation",
        ):
            with self.subTest(
                module=test_module
            ):
                self.assertIn(
                    test_module,
                    self.text,
                )

    def test_main_checkout_and_shared_writer_lock_are_explicit(self):
        self.assertIn("uses: actions/checkout@v7", self.text)
        self.assertIn("ref: main", self.text)
        self.assertIn("group: production-data-update", self.text)

    def test_core_and_poll_sitemaps_are_validation_only(self):
        self.assertIn(
            "git diff --exit-code -- sitemap-core.xml sitemap-polls.xml",
            self.text,
        )
        stage = self.text[
            self.text.index("git add --"):
            self.text.index("git commit -m")
        ]
        self.assertNotIn("sitemap-core.xml", stage)
        self.assertNotIn("sitemap-polls.xml", stage)


if __name__ == "__main__":
    unittest.main()
