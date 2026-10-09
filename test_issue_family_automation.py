import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "publish-issue-family.yml"


class IssueFamilyAutomationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def assert_in_order(self, *needles):
        position = -1
        for needle in needles:
            next_position = self.text.find(needle, position + 1)
            self.assertNotEqual(next_position, -1, f"missing workflow fragment: {needle}")
            self.assertGreater(next_position, position)
            position = next_position

    def test_workflow_exists_and_has_authoritative_triggers(self):
        self.assertTrue(WORKFLOW.is_file())
        self.assertIn("workflow_run:", self.text)
        self.assertIn('- "Update polls"', self.text)
        self.assertNotIn('- "Update Election News Wire"', self.text)
        self.assertIn('- "Publish candidate family"', self.text)
        self.assertNotIn('- "Update candidate universe"', self.text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertRegex(self.text, r"(?m)^\s+schedule:\s*$")
        self.assertRegex(self.text, r'(?m)^\s+- cron: "[^\"]+"\s*$')

    def test_permissions_and_repository_wide_serialization_are_minimal(self):
        permissions = re.search(
            r"(?ms)^permissions:\n(?P<body>.*?)(?=^concurrency:)", self.text
        )
        self.assertIsNotNone(permissions)
        self.assertEqual(
            {line.strip() for line in permissions.group("body").splitlines() if line.strip()},
            {"contents: write", "pages: write"},
        )
        self.assertIn("group: production-data-update", self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_checkout_is_main_with_complete_history(self):
        self.assertIn("uses: actions/checkout@v7", self.text)
        self.assertIn("ref: main", self.text)
        self.assertIn("fetch-depth: 0", self.text)

    def test_required_inputs_and_manifest_date_anchor_are_validated(self):
        for name in (
            "news_wire.json",
            "candidate_agenda_history.json",
            "candidate_candidacy_status.json",
            "poll_pages_manifest.json",
            "issue_pages_manifest.json",
            "publication_manifest.json",
        ):
            self.assertIn(name, self.text)
        self.assertIn("validate_manifest(stored)", self.text)
        self.assertIn("stored != expected", self.text)
        self.assertIn("instant.astimezone(timezone.utc).date().isoformat()", self.text)
        self.assertIn("build_publication_manifest.py", self.text)
        self.assertIn('--published-at "$published_at"', self.text)

    def test_authoritative_generation_and_validation_order(self):
        self.assert_in_order(
            "python -B build_issue_coverage_history.py\n",
            "python -B build_issue_coverage_history.py --check",
            "python -B build_issue_pages.py\n",
            "python -B build_issue_pages.py --check",
            "python -B build_issue_pages.py --thin-audit",
            "python -B -m unittest -v test_issue_pages",
            "python -B build_route_registry.py",
            "--issue-manifest issue_pages_manifest.json",
            "python -B build_sitemaps.py\n",
            "python -B build_sitemaps.py --check",
        )

    def test_cross_family_tests_run_before_commit(self):
        commit_position = self.text.index("- name: Commit generated issue publication")
        for module in (
            "test_issue_pages",
            "test_route_registry",
            "test_search_foundation",
            "test_issue_family_automation",
        ):
            self.assertLess(self.text.index(module), commit_position)
        self.assertLess(self.text.index("git diff --check"), commit_position)

    def test_second_generation_is_compared_byte_for_byte(self):
        self.assertIn("snapshot_generated_state first", self.text)
        self.assertIn("snapshot_generated_state second", self.text)
        self.assertIn('cmp "$RUNNER_TEMP/issues-first.status"', self.text)
        self.assertIn('cmp "$RUNNER_TEMP/issues-first.diff"', self.text)
        self.assertIn('cmp "$RUNNER_TEMP/issues-first.sha256"', self.text)
        first = self.text.index("snapshot_generated_state first")
        second_history = self.text.index("python -B build_issue_coverage_history.py", first)
        second_pages = self.text.index("python -B build_issue_pages.py", second_history)
        second_registry = self.text.index("python -B build_route_registry.py", second_pages)
        second_sitemaps = self.text.index("python -B build_sitemaps.py", second_registry)
        second_snapshot = self.text.index("snapshot_generated_state second", second_sitemaps)
        self.assertLess(second_history, second_pages)
        self.assertLess(second_pages, second_registry)
        self.assertLess(second_registry, second_sitemaps)
        self.assertLess(second_sitemaps, second_snapshot)

    def test_runtime_allowlist_is_exact_and_fail_closed(self):
        case_lines = re.findall(
            r"(?m)^\s+(issue_coverage_history\.json\|[^\n]+)\)\s*$", self.text
        )
        self.assertGreaterEqual(len(case_lines), 2)
        expected = {
            "issue_coverage_history.json",
            "issue_pages_manifest.json",
            "enjeux/*",
            "en/issues/*",
            "route_registry.json",
            "sitemap.xml",
            "sitemap-core.xml",
            "sitemap-candidates.xml",
            "sitemap-polls.xml",
            "sitemap-issues.xml",
        }
        for line in case_lines:
            self.assertEqual(set(line.split("|")), expected)
        self.assertIn("Unexpected generated path:", self.text)
        self.assertIn("Unexpected path after reconciliation:", self.text)
        self.assertIn("return 1", self.text)

    def test_staging_is_scoped_and_excludes_publication_manifest(self):
        add_blocks = re.findall(
            r"(?ms)^\s+git add -- \\\n(?P<body>.*?)(?=^\s+(?:git diff --cached|if ))",
            self.text,
        )
        self.assertEqual(len(add_blocks), 2)
        for block in add_blocks:
            self.assertIn("issue_coverage_history.json", block)
            self.assertIn("issue_pages_manifest.json", block)
            self.assertIn("enjeux en/issues", block)
            self.assertIn("route_registry.json", block)
            self.assertIn("sitemap-issues.xml", block)
            self.assertNotIn("publication_manifest.json", block)

    def test_search_entrypoints_are_not_rebuilt(self):
        self.assertEqual(self.text.count("build_search_entrypoints.py"), 1)
        self.assertIn('["build_search_entrypoints.py", "--check"]', self.text)
        self.assertNotIn("python -B build_search_entrypoints.py", self.text)

    def test_no_op_avoids_commit_push_and_pages(self):
        self.assertIn('echo "changed=false" >> "$GITHUB_OUTPUT"', self.text)
        self.assertIn("if: steps.commit.outputs.changed == 'true'", self.text)
        self.assertIn('echo "pushed=false" >> "$GITHUB_OUTPUT"', self.text)
        self.assertIn("steps.reconcile.outputs.pushed == 'true'", self.text)

    def test_reconciliation_regenerates_and_can_amend_before_push(self):
        self.assert_in_order(
            'git commit -m "Refresh issue family"',
            "git fetch origin main",
            "git rebase origin/main",
            "publication_manifest.json is not synchronized after rebase",
            "python -B build_issue_coverage_history.py",
            "python -B build_issue_pages.py",
            "python -B build_route_registry.py",
            "python -B build_sitemaps.py",
            "git commit --amend --no-edit",
            "git push origin HEAD:main",
        )
        self.assertIn("git diff --quiet origin/main --", self.text)
        self.assertIn("Working tree is not clean after issue reconciliation.", self.text)
        self.assertNotRegex(self.text, r"git push[^\n]*(?:--force|-f(?:\s|$))")

    def test_pages_request_is_post_push_and_uses_repository_api_contract(self):
        push_position = self.text.index("git push origin HEAD:main")
        pages_position = self.text.index("- name: Request GitHub Pages build")
        self.assertLess(push_position, pages_position)
        self.assertIn('--request POST', self.text)
        self.assertIn('Accept: application/vnd.github+json', self.text)
        self.assertIn('Authorization: Bearer ${GH_TOKEN}', self.text)
        self.assertIn('X-GitHub-Api-Version: 2026-03-10', self.text)
        self.assertIn('${GITHUB_API_URL}/repos/${GITHUB_REPOSITORY}/pages/builds', self.text)


if __name__ == "__main__":
    unittest.main()
