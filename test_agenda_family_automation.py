import re
import ast
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import build_route_registry as registry_builder
import build_sitemaps as sitemap_builder
import build_agenda_coverage_history as history_builder
import test_build_agenda_coverage_history as history_fixtures
from datetime import date, datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "publish-agenda-family.yml"


def run_blocks(text):
    """Read literal shell steps without adding a YAML runtime dependency."""
    return [
        "\n".join(line[10:] for line in match.splitlines()) + "\n"
        for match in re.findall(r"(?m)^        run: \|\n((?:          .*\n|\n)+)", text)
    ]


class AgendaFamilyAutomationContractTests(unittest.TestCase):
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
        self.assertTrue(self.text.startswith("name: Publish agenda family\n"))
        self.assertIn("workflow_run:", self.text)
        self.assertIn('- "Update polls"', self.text)
        self.assertIn('- "Update Election News Wire"', self.text)
        self.assertIn('- "Update candidate universe"', self.text)
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
        self.assertIn("queue: max", self.text)

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
            "agenda_pages_manifest.json",
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
            "python -B build_agenda_coverage_history.py\n",
            "python -B build_agenda_coverage_history.py --check",
            "python -B build_agenda_pages.py\n",
            "python -B build_agenda_pages.py --check",
            "python -B build_agenda_pages.py --thin-audit",
            "python -B -m unittest -v test_agenda_pages",
            "python -B build_route_registry.py",
            "--agenda-manifest agenda_pages_manifest.json",
            "python -B build_sitemaps.py\n",
            "python -B build_sitemaps.py --check",
        )

    def test_cross_family_tests_run_before_commit(self):
        commit_position = self.text.index("- name: Commit generated Agenda publication")
        for module in (
            "test_agenda_pages",
            "test_route_registry",
            "test_search_foundation",
            "test_agenda_family_automation",
        ):
            self.assertLess(self.text.index(module), commit_position)
        self.assertLess(self.text.index("git diff --check"), commit_position)

    def test_second_generation_is_compared_byte_for_byte(self):
        self.assertIn("snapshot_generated_state first", self.text)
        self.assertIn("snapshot_generated_state second", self.text)
        self.assertIn('cmp "$RUNNER_TEMP/agenda-first.status"', self.text)
        self.assertIn('cmp "$RUNNER_TEMP/agenda-first.diff"', self.text)
        self.assertIn('cmp "$RUNNER_TEMP/agenda-first.sha256"', self.text)
        first = self.text.index("snapshot_generated_state first")
        second_history = self.text.index("python -B build_agenda_coverage_history.py", first)
        second_pages = self.text.index("python -B build_agenda_pages.py", second_history)
        second_registry = self.text.index("python -B build_route_registry.py", second_pages)
        second_sitemaps = self.text.index("python -B build_sitemaps.py", second_registry)
        second_snapshot = self.text.index("snapshot_generated_state second", second_sitemaps)
        self.assertLess(second_history, second_pages)
        self.assertLess(second_pages, second_registry)
        self.assertLess(second_registry, second_sitemaps)
        self.assertLess(second_sitemaps, second_snapshot)

    def test_runtime_allowlist_is_exact_and_fail_closed(self):
        case_lines = re.findall(
            r"(?m)^\s+(agenda_coverage_history\.json\|[^\n]+)\)\s*$", self.text
        )
        self.assertGreaterEqual(len(case_lines), 2)
        expected = {
            "agenda_coverage_history.json",
            "agenda_pages_manifest.json",
            "agenda/*",
            "en/agenda/*",
            "route_registry.json",
            "sitemap.xml",
            "sitemap-core.xml",
            "sitemap-candidates.xml",
            "sitemap-polls.xml",
            "sitemap-issues.xml",
            "sitemap-agenda.xml",
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
            self.assertIn("agenda_coverage_history.json", block)
            self.assertIn("agenda_pages_manifest.json", block)
            self.assertIn("agenda en/agenda", block)
            self.assertIn("route_registry.json", block)
            self.assertIn("sitemap-issues.xml", block)
            self.assertIn("sitemap-agenda.xml", block)
            self.assertNotIn("publication_manifest.json", block)

    def test_search_entrypoints_are_not_rebuilt(self):
        self.assertNotIn("build_search_entrypoints.py", self.text)

    def test_no_op_avoids_commit_push_and_pages(self):
        self.assertIn('echo "changed=false" >> "$GITHUB_OUTPUT"', self.text)
        self.assertIn("if: steps.commit.outputs.changed == 'true'", self.text)
        self.assertIn('echo "pushed=false" >> "$GITHUB_OUTPUT"', self.text)
        self.assertIn("steps.reconcile.outputs.pushed == 'true'", self.text)

    def test_reconciliation_regenerates_and_can_amend_before_push(self):
        self.assert_in_order(
            'git commit -m "Refresh Agenda family"',
            "git fetch origin main",
            "git rebase origin/main",
            "publication_manifest.json is not synchronized after rebase",
            "python -B build_agenda_coverage_history.py",
            "python -B build_agenda_pages.py",
            "python -B build_route_registry.py",
            "python -B build_sitemaps.py",
            "git commit --amend --no-edit",
            "git push origin HEAD:main",
        )
        self.assertIn("git diff --quiet origin/main --", self.text)
        self.assertIn("Working tree is not clean after Agenda reconciliation.", self.text)
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

    def test_producers_are_exact_and_generated_outputs_cannot_self_trigger(self):
        producers = re.search(r"(?s)  workflow_run:\n    workflows:\n(.*?)    types:", self.text)[1]
        self.assertEqual(set(re.findall(r'- "([^"]+)"', producers)), {
            "Update Election News Wire", "Update candidate universe", "Update polls",
        })
        paths = re.search(r"(?s)    paths:\n(.*?)\n  #", self.text)[1]
        paths = set(re.findall(r'- "([^"]+)"', paths))
        for path in (
            "news_wire.json", "candidate_agenda_history.json", "candidate_candidacy_status.json",
            "poll_pages_manifest.json", "publication_manifest.json", "assets/agenda.css",
            "assets/agenda.js", "test_agenda_page_contract.py", "test_build_agenda_coverage_history.py",
            "build_poll_pages.py", "candidate_page_contract.py", "sondages/index.html",
            "en/sondages/index.html",
        ):
            self.assertIn(path, paths)
        self.assertFalse(paths & {
            "agenda/**", "en/agenda/**", "agenda_coverage_history.json",
            "agenda_pages_manifest.json", "route_registry.json", "sitemap.xml", "sitemap-agenda.xml",
        })
        self.assertFalse(any(path.startswith(("agenda/", "en/agenda/")) for path in paths))
        self.assertIn('cron: "53 11 * * *"', self.text)
        for sibling in ("publish-candidate-family.yml", "publish-issue-family.yml"):
            self.assertNotIn('cron: "53 11 * * *"', (WORKFLOW.parent / sibling).read_text())

    def test_complete_suite_runs_before_commit_and_after_rebase(self):
        before, after = self.text.split("          git rebase origin/main", 1)
        before = before[:before.index("- name: Commit generated Agenda publication")]
        after = after[:after.index("git push origin HEAD:main")]
        for phase in (before, after):
            for module in (
                "test_agenda_page_contract", "test_build_agenda_coverage_history", "test_agenda_pages",
                "test_campaign_agenda_evidence", "test_build_candidate_agenda_history",
                "test_candidate_agenda_history_contract", "test_route_registry", "test_search_foundation",
                "test_publication_manifest", "test_publication_manifest_registry_v2",
                "test_agenda_family_automation", "test_production_publication_queue",
            ):
                self.assertIn(module, phase)
        self.assert_in_order(
            "git rebase origin/main", "validate_manifest(stored)",
            "python -B build_publication_manifest.py", "python -B build_agenda_coverage_history.py",
            "python -B build_agenda_coverage_history.py --check", "python -B build_agenda_pages.py",
            "python -B build_agenda_pages.py --check", "python -B build_agenda_pages.py --thin-audit",
            "--agenda-manifest agenda_pages_manifest.json", "python -B build_sitemaps.py --check",
            "test_production_publication_queue", "git diff --check", "assert_allowed_changes",
            "snapshot_generated_state rebased-first", "python -B build_agenda_coverage_history.py",
            "snapshot_generated_state rebased-second", 'cmp "$RUNNER_TEMP/agenda-rebased-first.sha256"',
            "git add --", "git diff --cached --check", "git commit --amend --no-edit",
            "Working tree is not clean after Agenda reconciliation.", "git push origin HEAD:main",
            'echo "pushed=true"',
        )

    def test_every_complete_pass_checks_the_generators_and_thin_audit(self):
        for command in (
            "build_agenda_coverage_history.py", "build_agenda_pages.py", "build_route_registry.py",
            "build_sitemaps.py",
        ):
            self.assertEqual(self.text.count("python -B " + command), 12 if command == "build_agenda_pages.py" else 8)
        self.assertEqual(self.text.count("python -B build_agenda_pages.py --thin-audit"), 4)

    def test_no_other_family_pages_or_source_artifacts_are_generated(self):
        for builder in (
            "build_candidate_reference.py", "build_issue_pages.py", "build_poll_pages.py",
            "build_candidate_agenda_history.py", "build_search_entrypoints.py",
        ):
            self.assertNotIn("python -B " + builder, self.text)
        self.assertNotIn("python -B build_publication_manifest.py \\\n            --published-at", self.text)
        self.assertIn("Checkout must be clean before Agenda generation.", self.text)

    def test_inline_python_and_shell_syntax(self):
        blocks = run_blocks(self.text)
        self.assertEqual(len(blocks), 5)
        bash = shutil.which("bash")
        if os.name == "nt":
            bash = str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe")
        for index, script in enumerate(blocks):
            for code in re.findall(r"<<'PY'\n(.*?)\nPY", script, re.S):
                ast.parse(code)
            if bash and Path(bash).is_file():
                result = subprocess.run([bash, "-n"], input=script, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, f"step {index}: {result.stderr}")

    def test_runtime_scope_guard_rejects_forbidden_paths_and_renames(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            bash = str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe")
        if not bash or not Path(bash).is_file():
            self.skipTest("Bash is required to execute the workflow scope guard")
        guards = re.findall(r"(?ms)^          assert_allowed_changes\(\) \{\n.*?^          \}", self.text)
        self.assertEqual(len(guards), 2)
        allowed = (
            "agenda_coverage_history.json", "agenda_pages_manifest.json", "agenda/topic/index.html",
            "en/agenda/history/topic/index.html", "route_registry.json", "sitemap.xml",
            "sitemap-core.xml", "sitemap-candidates.xml", "sitemap-polls.xml", "sitemap-issues.xml",
            "sitemap-agenda.xml",
        )
        forbidden = (
            "candidates/a/index.html", "en/candidates/a/index.html", "enjeux/a/index.html",
            "en/issues/a/index.html", "sondages/a/index.html", "en/sondages/a/index.html",
            "polls.json", "news_wire.json", "candidate_agenda_history.json",
            "candidate_candidacy_status.json", "index.html", "en/index.html", "publication_manifest.json",
        )
        for guard in guards:
            script = "\n".join(line[10:] for line in guard.splitlines())
            # Only a stubbed git status is executed; no publication command runs.
            script += '\ngit() { printf "%s\\0" "$STATUS_ENTRY"; }\nassert_allowed_changes\n'
            for path in allowed + forbidden:
                with self.subTest(path=path):
                    result = subprocess.run([bash], input=script, text=True, capture_output=True,
                                            env={**os.environ, "STATUS_ENTRY": " M " + path})
                    self.assertEqual(result.returncode == 0, path in allowed, result.stderr)
            result = subprocess.run([bash], input=script, text=True, capture_output=True,
                                    env={**os.environ, "STATUS_ENTRY": "R  agenda/topic/index.html"})
            self.assertNotEqual(result.returncode, 0)

    def test_sibling_registry_rebuilds_keep_agenda_routes_and_sitemap(self):
        prior = json.loads((ROOT / "route_registry.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "agenda_pages_manifest.json").read_text(encoding="utf-8"))
        agenda = [route for route in prior["routes"] if route["family"] == "agenda"]
        expected_xml = sitemap_builder.expected_artifacts(prior)[Path("sitemap-agenda.xml")]
        original_hash = registry_builder._route_content_hash
        for family, workflow_name in (
            ("candidates", "publish-candidate-family.yml"),
            ("issues", "publish-issue-family.yml"), ("polls", "update-polls.yml"),
        ):
            with self.subTest(family=family):
                workflow = (WORKFLOW.parent / workflow_name).read_text(encoding="utf-8")
                self.assertIn("python -B build_route_registry.py", workflow)
                # Simulate legitimate changed sibling content without writing political artifacts.
                def changed_hash(**kwargs):
                    value = original_hash(**kwargs)
                    return "f" * 64 if kwargs["route"]["family"] == family else value
                with patch.object(registry_builder, "_route_content_hash", side_effect=changed_hash):
                    rebuilt = registry_builder.build_registry(
                        root=ROOT, effective_date="2099-01-01",
                        **({"issue_manifest_path": ROOT / "issue_pages_manifest.json"} if family == "issues" else {}),
                    )
                rebuilt_agenda = [route for route in rebuilt["routes"] if route["family"] == "agenda"]
                self.assertEqual(len(rebuilt_agenda), manifest["page_count"])
                self.assertEqual(rebuilt_agenda, agenda)
                self.assertEqual(sitemap_builder.expected_artifacts(rebuilt)[Path("sitemap-agenda.xml")], expected_xml)

    def test_next_news_utc_day_advances_history_without_including_partial_day(self):
        first_snapshot = history_fixtures.snapshot()
        first_instant = datetime.fromisoformat(first_snapshot["generated_at"].replace("Z", "+00:00"))
        next_instant = first_instant + timedelta(days=1)
        next_snapshot = history_fixtures.snapshot(generated_at=next_instant.isoformat().replace("+00:00", "Z"))
        observation = {"commit": "a" * 40, "committed_at": first_instant, "blob": "b" * 40}
        artifacts = []
        for current in (first_snapshot, next_snapshot):
            retained = [(observation, first_snapshot)]
            if current is next_snapshot:
                retained.append((
                    {"commit": "c" * 40, "committed_at": next_instant, "blob": "d" * 40},
                    next_snapshot,
                ))
            with (
                patch.object(history_builder, "_first_inventory_timestamp", return_value=(
                    datetime(2026, 1, 1, 12, tzinfo=timezone.utc), "inventory-commit")),
                patch.object(history_builder, "_campaign_introduction_date", return_value=date(2026, 1, 1)),
                patch.object(history_builder, "_history_observations", return_value=[item[0] for item in retained]),
                patch.object(history_builder, "_read_blobs", return_value=retained),
            ):
                artifact = history_builder.build_history_payload(
                    root=ROOT, news_wire_path=history_fixtures.MemoryJsonPath(current))
            current_day = datetime.fromisoformat(current["generated_at"].replace("Z", "+00:00")).date()
            self.assertEqual(artifact["period"]["end_date"], (current_day - timedelta(days=1)).isoformat())
            self.assertNotIn(current_day.isoformat(), {point["date"] for point in artifact["daily"]})
            artifacts.append(artifact)
        self.assertEqual(artifacts[1]["period"]["days"], artifacts[0]["period"]["days"] + 1)
        self.assertIn(first_instant.date().isoformat(), {point["date"] for point in artifacts[1]["daily"]})


if __name__ == "__main__":
    unittest.main()
