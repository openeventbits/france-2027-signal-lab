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

    def test_pr_validation_installs_candidate_import_dependencies_before_tests(self):
        text = (ROOT / ".github/workflows/validate-dashboard.yml").read_text(encoding="utf-8")
        setup = text.index("- name: Set up Python")
        install = text.index("- name: Install Python dependencies")
        tests = text.index("- name: Run dashboard integration smoke tests")
        self.assertLess(setup, install)
        self.assertLess(install, tests)
        block = text[install:].split("\n      - name:", 1)[0]
        self.assertIn("python -m pip install --disable-pip-version-check", block)
        packages = block.split("--disable-pip-version-check", 1)[1].split()
        self.assertEqual(packages, ["pandas", "lxml", "pypdf"])
        for module in ("test_candidate_public_signals", "test_candidate_refresh_cycle"):
            self.assertIn(module, text[tests:])

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
            "candidate_polymarket_history.json", "candidate_youtube_history.json", "candidate_bluesky_history.json",
            "candidate_bluesky.json", "candidate_polymarket.json", "candidate_youtube.json", "publication_manifest.json",
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
            "build_candidate_polymarket_history.py --check",
            "build_candidate_youtube_history.py --check",
            "build_candidate_bluesky_history.py --check",
            'build_publication_manifest.py --published-at "$publication_time"',
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
            "build_publication_manifest.py --check",
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
                phase_expected = expected.copy()
                if name == "reconciliation":
                    phase_expected[3] = 'build_publication_manifest.py --published-at "$PUBLICATION_TIME"'
                self.assertEqual(commands, phase_expected)
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

    def test_no_artifact_coupled_tests_between_collection_and_coherent_rebuild(self):
        pre = self.text.index("- name: Check offline provider contracts before collection")
        collect = self.text.index("- name: Collect candidate prediction-market evidence")
        rebuild = self.text.index("- name: Build and validate candidate publication")
        publish = self.text.index("- name: Commit generated candidate publication")
        pre_block = self.text[pre:collect]
        self.assertIn("github.event_name == 'schedule'", pre_block)
        self.assertIn("github.event_name == 'workflow_dispatch'", pre_block)
        self.assertIn("YouTubeTransportTests", pre_block)
        self.assertNotIn("TaskOnePreservationTests", pre_block)
        self.assertNotIn("test_candidate_public_signals", pre_block)
        mutation = self.text[collect:rebuild]
        self.assertNotIn("-m unittest", mutation)
        self.assertNotIn("continue-on-error", mutation)
        self.assertNotIn("always()", self.text[collect:publish])
        for provider in ("polymarket", "youtube", "bluesky"):
            self.assertIn(f"build_candidate_{provider}.py", mutation)
            self.assertIn(f"build_candidate_{provider}_history.py", mutation)
            self.assertIn(f"test_candidate_{provider}", self.text[rebuild:publish])
        self.assertIn("test_candidate_refresh_cycle", self.text[rebuild:publish])
        self.assertLess(self.text.index("build_sitemaps.py --check", rebuild),
                        self.text.index("-m unittest", rebuild))

    def test_refresh_regression_is_offline_in_pr_validation(self):
        validation = (ROOT / ".github/workflows/validate-dashboard.yml").read_text(encoding="utf-8")
        self.assertIn("test_candidate_refresh_cycle", validation)
        self.assertNotIn("YOUTUBE_API_KEY", validation)
        for provider in ("polymarket", "youtube", "bluesky"):
            self.assertNotIn(f"build_candidate_{provider}.py", validation)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn("queue: max", self.text)

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
