"""Contracts for the dashboard-only production publisher (stdlib only)."""
import ast
import fnmatch
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from test_production_publication_queue import production_concurrency

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/publish-dashboard.yml"
GENERATED = {
    "index.html", "en/index.html", "route_registry.json", "sitemap.xml",
    "sitemap-core.xml", "sitemap-candidates.xml", "sitemap-polls.xml",
    "sitemap-issues.xml", "sitemap-agenda.xml",
}
REQUIRED_TRIGGERS = {
    "build_search_entrypoints.py", "dashboard_navigation.py", "fr27_section_launcher.py",
    "assets/candidate-signals-workspace.js", "assets/dashboard-navigation.css",
    "assets/dashboard-navigation.js", "assets/hybrid-dashboard.js",
    "assets/final-dashboard-shell.css", "assets/fr27-section-launcher.css",
    "assets/fr27-section-launcher.js", "assets/localization.js",
    "locales/fr.js", "locales/en.js", "index.html", "en/index.html",
    "build_route_registry.py", "build_sitemaps.py", "test_dashboard_navigation.py",
    "test_candidate_signals_workspace.py", "test_race_glance_defaults.py",
    "test_search_foundation.py", ".github/workflows/publish-dashboard.yml",
}
REQUIRED_TESTS = {
    "test_dashboard_navigation", "test_candidate_signals_workspace",
    "test_race_glance_defaults", "test_search_foundation", "test_route_registry",
    "test_final_dashboard_shell", "test_frontend_facts",
    "test_production_publication_queue", "test_dashboard_publication_automation",
}


def run_blocks(text):
    """Read literal shell steps without requiring PyYAML in production."""
    return [
        "\n".join(line[10:] for line in match.splitlines()) + "\n"
        for match in re.findall(r"(?m)^        run: \|\n((?:          .*\n|\n)+)", text)
    ]


def step(text, name):
    tail = text.split("      - name: " + name + "\n", 1)[1]
    return tail.split("\n      - name: ", 1)[0]


def function(script, name):
    match = re.search(r"(?ms)^" + name + r"\(\) \{\n(.*?)^\}\n", script)
    if not match:
        raise AssertionError(f"missing shell function: {name}")
    return match.group(1)


class DashboardPublicationAutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.script = run_blocks(cls.text)[0]
        trigger = cls.text.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
        cls.trigger_paths = re.findall(r'(?m)^      - "([^"]+)"$', trigger)
        cls.allowed = set(re.search(
            r"readonly -a generated_files=\(\n(.*?)\n\)", cls.script, re.S
        ).group(1).split())
        cls.boundary_code = re.search(
            r"<<'PY'\n(.*?)\nPY", function(cls.script, "assert_allowed_changes"), re.S
        ).group(1)

    def test_workflow_name_and_only_main_push_and_manual_triggers(self):
        self.assertTrue(WORKFLOW.is_file())
        self.assertTrue(self.text.startswith("name: Publish dashboard\n"))
        trigger = self.text.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"(?m)^  ([\w_]+):", trigger), ["push", "workflow_dispatch"])
        self.assertRegex(trigger, r"(?m)^    branches: \[main\]$")
        self.assertNotRegex(trigger, r"\bschedule:|\bworkflow_run:")

    def test_authored_inputs_and_downstream_builders_are_triggered(self):
        self.assertTrue(REQUIRED_TRIGGERS <= set(self.trigger_paths), REQUIRED_TRIGGERS - set(self.trigger_paths))
        self.assertEqual(len(self.trigger_paths), len(set(self.trigger_paths)))
        for path in self.trigger_paths:
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertNotIn("*", path, "use audited authored files, not broad globs")
        self.assertNotIn("route_registry.json", self.trigger_paths)
        self.assertFalse(any(path.endswith(".xml") or path.endswith(".json") for path in self.trigger_paths))

    def test_hypothetical_main_changes_close_the_publication_gap(self):
        for path in ("dashboard_navigation.py", "build_search_entrypoints.py", "locales/fr.js", "assets/hybrid-dashboard.js"):
            with self.subTest(path=path):
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in self.trigger_paths))
        for path in ("README.md", "news_wire.json", "polls.json", "publication_manifest.json"):
            with self.subTest(path=path):
                self.assertFalse(any(fnmatch.fnmatchcase(path, pattern) for pattern in self.trigger_paths))

    def test_exact_permissions_and_workflow_level_waiting_queue(self):
        permissions = self.text.split("permissions:\n", 1)[1].split("\nconcurrency:", 1)[0]
        self.assertEqual(set(permissions.split()), {"contents:", "pages:", "write"})
        self.assertEqual([line.strip() for line in permissions.splitlines() if line.strip()], ["contents: write", "pages: write"])
        self.assertEqual(production_concurrency(self.text), [{
            "group": "production-data-update", "cancel-in-progress": "false", "queue": "max",
        }])

    def test_checkout_main_full_history_and_required_runtimes(self):
        checkout = step(self.text, "Check out current main")
        self.assertIn("uses: actions/checkout@v7", checkout)
        self.assertIn("ref: main", checkout)
        self.assertIn("fetch-depth: 0", checkout)
        self.assertIn('python-version: "3.12"', self.text)
        self.assertIn("run: node --version", self.text)
        self.assertNotIn("pip install", self.text)

    def test_authoritative_builder_and_check_order(self):
        build = function(self.script, "generate_dashboard_publication")
        commands = [line.strip() for line in build.splitlines() if line.strip()]
        self.assertEqual(commands, [
            "python -B build_search_entrypoints.py",
            "python -B build_search_entrypoints.py --check",
            'python -B build_route_registry.py --effective-date "$effective_date"',
            "python -B build_route_registry.py --check",
            "python -B build_sitemaps.py", "python -B build_sitemaps.py --check",
        ])
        initial = step(self.text, "Generate and validate dashboard publication")
        self.assertIn('effective_date="$(date -u +\'%Y-%m-%d\')"', initial)
        reconcile = step(self.text, "Reconcile current main and push dashboard publication")
        self.assertIn("${{ steps.build.outputs.effective_date }}", reconcile)
        self.assertIn('effective_date="$EFFECTIVE_DATE"', reconcile)

    def test_exact_nine_output_boundary_and_staging(self):
        self.assertEqual(self.allowed, GENERATED)
        self.assertEqual(self.text.count('git add -- "${generated_files[@]}"'), 2)
        self.assertNotRegex(self.text, r"git add (?:-A|--all|\.)|git commit -a")
        self.assertIn('"--untracked-files=all"', self.boundary_code)
        for name in ("Commit generated dashboard publication", "Reconcile current main and push dashboard publication"):
            body = step(self.text, name)
            self.assertIn("git diff --cached --check", body)

    def check_boundary(self, status):
        with patch.object(subprocess, "check_output", return_value=status), patch.object(sys, "argv", ["-", *sorted(GENERATED)]):
            exec(compile(self.boundary_code, str(WORKFLOW), "exec"), {})

    def test_boundary_accepts_only_allowed_tracked_or_untracked_paths(self):
        self.check_boundary(b"")
        self.check_boundary(b" M index.html\0 M en/index.html\0?? sitemap.xml\0")
        self.check_boundary(b"R  index.html\0en/index.html\0")

    def test_boundary_rejects_source_data_family_assets_and_untracked_output(self):
        for path in ("news_wire.json", "publication_manifest.json", "assets/hybrid-dashboard.js", "candidats/example/index.html", "untracked-output.txt"):
            for status in (b" M ", b"?? "):
                with self.subTest(path=path, status=status), self.assertRaisesRegex(SystemExit, "Unexpected generated paths"):
                    self.check_boundary(status + path.encode() + b"\0")

    def test_boundary_checks_rename_and_copy_sources_not_only_destinations(self):
        for status in (b"R ", b" C"):
            with self.subTest(status=status), self.assertRaisesRegex(SystemExit, "news_wire.json"):
                self.check_boundary(status + b" index.html\0news_wire.json\0")
        with self.assertRaisesRegex(SystemExit, "Malformed rename/copy"):
            self.check_boundary(b"R  index.html\0")

    def test_snapshot_covers_status_binary_diff_and_exact_byte_hashes(self):
        snapshot = function(self.script, "snapshot_generated_state")
        self.assertIn('git status --porcelain=v1 -z --untracked-files=all -- "${generated_files[@]}"', snapshot)
        self.assertIn('git diff --binary HEAD -- "${generated_files[@]}"', snapshot)
        self.assertIn("hashlib.sha256(Path(name).read_bytes())", snapshot)
        for code in re.findall(r"<<'PY'\n(.*?)\nPY", self.script, re.S):
            ast.parse(code)

    def test_second_full_generation_requires_identical_status_diff_and_hashes(self):
        validate = function(self.script, "validate_deterministic_publication")
        calls = [line.strip() for line in validate.splitlines()]
        self.assertEqual(calls.count("generate_dashboard_publication"), 2)
        first = calls.index("snapshot_generated_state first")
        second = calls.index("snapshot_generated_state second")
        self.assertIn("generate_dashboard_publication", calls[first + 1:second])
        for suffix in ("status", "diff", "sha256"):
            self.assertIn(f'cmp "$RUNNER_TEMP/dashboard-first.{suffix}" "$RUNNER_TEMP/dashboard-second.{suffix}"', validate)
        self.assertEqual(calls.count("assert_allowed_changes"), 3)
        self.assertEqual(calls.count("git diff --check"), 3)

    def test_focused_and_sitemap_tests_run_before_commit_and_after_rebase(self):
        tests = function(self.script, "run_publication_tests")
        self.assertIn("test_route_registry includes the existing SitemapTests", tests)
        for module in REQUIRED_TESTS:
            self.assertRegex(tests, r"(?m)^\s+" + module + r"\s*(?:\\)?$")
        validate = function(self.script, "validate_deterministic_publication")
        self.assertIn("run_publication_tests", validate)
        for name in ("Generate and validate dashboard publication", "Reconcile current main and push dashboard publication"):
            body = step(self.text, name)
            self.assertIn('source "$RUNNER_TEMP/dashboard-publication.sh"', body)
            self.assertIn("validate_deterministic_publication", body)
        self.assertIn("test_dashboard_publication_automation", (ROOT / ".github/workflows/validate-dashboard.yml").read_text(encoding="utf-8"))

    def test_no_op_skips_commit_push_and_pages(self):
        commit = step(self.text, "Commit generated dashboard publication")
        no_op = commit.split('echo "changed=false"', 1)[1].split("fi", 1)[0]
        self.assertIn("exit 0", no_op)
        self.assertIn('git status --porcelain=v1 --untracked-files=all -- "${generated_files[@]}"', commit)
        self.assertIn("if: steps.commit.outputs.changed == 'true'", self.text)
        self.assertIn('git commit -m "Refresh dashboard publication"', commit)
        self.assertIn('github-actions[bot]', commit)

    def test_rebase_regenerates_and_amends_only_the_publication_commit(self):
        body = step(self.text, "Reconcile current main and push dashboard publication")
        needles = ["git fetch origin main", "git rebase origin/main", "validate_deterministic_publication", 'git add -- "${generated_files[@]}"', "git diff --cached --check", "git commit --amend --no-edit", "git push origin HEAD:main"]
        positions = [body.index(needle) for needle in needles]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("git rev-list --count origin/main..HEAD", body)
        self.assertIn("if (( ahead > 1 )); then", body)
        self.assertIn("if (( ahead == 1 )); then\n              git commit --amend --no-edit", body)
        self.assertIn("git diff --cached --quiet", body)
        self.assertIn("Working tree is not clean after reconciliation", body)
        self.assertIn('git status --porcelain=v1 --untracked-files=all)', body)
        self.assertNotRegex(self.text, r"git (?:push[^\n]*(?:--force|-f\b|\+)|reset|clean|stash)")

    def test_successful_changed_push_is_required_for_pages(self):
        body = step(self.text, "Request GitHub Pages build")
        self.assertIn("steps.commit.outputs.changed == 'true' &&\n          steps.reconcile.outputs.pushed == 'true'", body)
        self.assertIn("GH_TOKEN: ${{ github.token }}", body)
        self.assertIn("curl --fail-with-body --location --request POST", body)
        self.assertIn('"${GITHUB_API_URL}/repos/${GITHUB_REPOSITORY}/pages/builds"', body)
        reconcile = step(self.text, "Reconcile current main and push dashboard publication")
        self.assertLess(reconcile.index("git push origin HEAD:main"), reconcile.index('echo "pushed=true"'))
        self.assertIn('echo "pushed=false"', reconcile)

    def test_uses_standard_token_without_dispatch_loop_or_collectors(self):
        # GitHub suppresses push-triggered workflows for GITHUB_TOKEN commits.
        # News still owns regeneration for its own data publication; no workflow_run chain.
        self.assertNotIn("repository_dispatch", self.text)
        self.assertNotIn("workflow_run:", self.text)
        self.assertNotIn("secrets.", self.text)
        self.assertNotRegex(self.text, r"python -B (?:fetch_|update_|build_(?:candidate_pages|issue_pages|agenda_pages|publication_manifest))")


if __name__ == "__main__":
    unittest.main()
