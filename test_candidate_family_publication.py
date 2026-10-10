from __future__ import annotations

import re
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

    def test_candidate_universe_waits_for_claims_refresh(self):
        self.assertNotIn(
            '- "Update candidate universe"',
            self.trigger,
        )

        dependency = self.text.index(
            "- name: Check candidate publication dependencies"
        )
        build = self.text.index(
            "- name: Build and validate candidate publication"
        )
        dependency_block = self.text[dependency:build]

        self.assertLess(dependency, build)
        self.assertIn("validate_public_bundle", dependency_block)
        self.assertIn(
            "candidacy_payload=candidacy",
            dependency_block,
        )
        self.assertIn(
            "candidate query does not match active registry projection",
            dependency_block,
        )
        self.assertGreaterEqual(
            self.text.count(
                "if: steps.dependencies.outputs.ready == 'true'"
            ),
            2,
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

    def test_python_runtime_dependencies_are_installed(self):
        self.assertIn(
            "uses: actions/setup-python@v6",
            self.text,
        )

        self.assertIn(
            "python -m pip install --disable-pip-version-check",
            self.text,
        )

        for package in (
            "pandas",
            "lxml",
            "pypdf",
        ):
            with self.subTest(package=package):
                self.assertIn(
                    package,
                    self.text,
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
        blocks = re.findall(
            r"(?m)^          git add -- \\\n((?:            .*\n)+)",
            self.text,
        )
        self.assertEqual(len(blocks), 2)
        expected = {
            "candidates", "en/candidates", "route_registry.json",
            "sitemap.xml", "sitemap-candidates.xml", "sitemap-core.xml",
            "sitemap-polls.xml", "index.html", "en/index.html",
        }
        for block in blocks:
            self.assertEqual(set(block.replace("\\", "").split()), expected)

        self.assertNotIn(
            "git add -A",
            self.text,
        )

        self.assertNotIn(
            "git add --all",
            self.text,
        )

    def test_both_transactions_finalize_route_hashes_before_sitemaps_and_tests(self):
        initial_start = self.text.index("- name: Build and validate candidate publication")
        commit_start = self.text.index("- name: Commit generated candidate publication")
        reconciliation_start = self.text.index("- name: Rebase, reconcile and push")
        expected = [
            "build_candidate_reference.py --all-active",
            "build_candidate_reference.py --all-active --check",
            "build_route_registry.py",
            "build_route_registry.py --check",
            "build_search_entrypoints.py",
            "build_search_entrypoints.py --check",
            "build_route_registry.py",
            "build_route_registry.py --check",
            "build_search_entrypoints.py --check",
            "build_sitemaps.py",
            "build_sitemaps.py --check",
            "-m unittest -v",
        ]
        for name, block, date_variable in (
            ("initial", self.text[initial_start:commit_start], "$effective_date"),
            ("reconciliation", self.text[reconciliation_start:], "$ROUTE_EFFECTIVE_DATE"),
        ):
            with self.subTest(path=name):
                commands = [line.strip().removeprefix("python -B ").rstrip(" \\")
                            for line in block.splitlines()
                            if line.strip().startswith("python -B ")]
                self.assertEqual(commands, expected)
                self.assertEqual(block.count(f'--effective-date "{date_variable}"'), 2)

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

    def test_all_sitemap_families_are_reconciled_atomically(self):
        self.assertNotIn(
            "git diff --exit-code -- sitemap-core.xml sitemap-polls.xml",
            self.text,
        )

        commit_start = self.text.index(
            "- name: Commit generated candidate publication"
        )
        rebase_start = self.text.index(
            "- name: Rebase, reconcile and push",
            commit_start,
        )

        initial_commit = self.text[
            commit_start:rebase_start
        ]
        rebase = self.text[rebase_start:]

        for section in (
            initial_commit,
            rebase,
        ):
            with self.subTest(
                phase=(
                    "initial"
                    if section is initial_commit
                    else "rebase"
                )
            ):
                self.assertIn(
                    "sitemap-core.xml",
                    section,
                )
                self.assertIn(
                    "sitemap-polls.xml",
                    section,
                )

        no_change_start = initial_commit.index(
            'git status --porcelain --'
        )
        no_change_end = initial_commit.index(
            ' ]]; then',
            no_change_start,
        )
        no_change = initial_commit[
            no_change_start:no_change_end
        ]

        self.assertIn(
            "sitemap-core.xml",
            no_change,
        )
        self.assertIn(
            "sitemap-polls.xml",
            no_change,
        )


if __name__ == "__main__":
    unittest.main()
