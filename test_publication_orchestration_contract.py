from __future__ import annotations

import ast
import copy
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import fetch_claims_under_scrutiny as claims_collector
import fetch_news_wire as news_collector
import build_route_registry as route_builder
from test_candidate_attention_registry_v2 import build_payload, candidate, registry


ROOT = Path(__file__).resolve().parent
WORKFLOWS = ROOT / ".github" / "workflows"


def read_workflow(filename: str) -> str:
    return (WORKFLOWS / filename).read_text(encoding="utf-8")


def trigger_block(text: str) -> str:
    return text.split("\npermissions:", 1)[0]


def workflow_run_producers(text: str) -> set[str]:
    trigger = trigger_block(text)
    match = re.search(
        r"(?ms)^  workflow_run:\n"
        r"    workflows:\n"
        r"(?P<body>.*?)"
        r"    types:\n",
        trigger,
    )
    if match is None:
        return set()
    return set(
        re.findall(
            r'- "([^"]+)"',
            match.group("body"),
        )
    )


def workflow_step(text: str, name: str) -> str:
    start = text.index(f"      - name: {name}\n")
    end = text.find("\n      - name:", start + 1)
    return text[start:] if end == -1 else text[start:end]


def inline_python(text: str, name: str) -> str:
    block = workflow_step(text, name)
    code = re.search(r"<<'PY'\n(.*?)\n          PY", block, re.S).group(1)
    return "\n".join(line[10:] for line in code.splitlines())


@contextmanager
def in_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PublicationOrchestrationContractTests(unittest.TestCase):
    def test_candidate_universe_refreshes_all_candidate_aware_collectors(
        self,
    ):
        for filename in (
            "update-candidate-attention.yml",
            "update-claims-under-scrutiny.yml",
            "update-news-wire.yml",
        ):
            with self.subTest(workflow=filename):
                text = read_workflow(filename)

                self.assertIn(
                    "Update candidate universe",
                    workflow_run_producers(text),
                )
                self.assertIn(
                    "github.event_name != 'workflow_run' ||",
                    text,
                )
                self.assertIn(
                    "github.event.workflow_run.conclusion == 'success'",
                    text,
                )

    def test_candidate_publication_has_three_way_readiness_barrier(
        self,
    ):
        text = read_workflow(
            "publish-candidate-family.yml"
        )

        dependency = text.index(
            "- name: Check candidate publication dependencies"
        )
        build = text.index(
            "- name: Build and validate candidate publication"
        )
        block = text[dependency:build]

        for artifact in (
            "claims_under_scrutiny.json",
            "candidate_attention.json",
            "news_wire.json",
        ):
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, block)

        for marker in (
            "validate_public_bundle",
            "validate_candidate_attention",
            "active_candidate_records",
            "candidate_roster",
            "source_revision_id",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, block)

        self.assertGreaterEqual(
            text.count(
                "if: steps.dependencies.outputs.ready == 'true'"
            ),
            2,
        )

    def test_candidate_publication_regenerates_search_after_routes(
        self,
    ):
        text = read_workflow(
            "publish-candidate-family.yml"
        )

        build_start = text.index(
            "- name: Build and validate candidate publication"
        )
        commit_start = text.index(
            "- name: Commit generated candidate publication"
        )
        initial = text[build_start:commit_start]

        route = initial.index(
            "python -B build_route_registry.py"
        )
        search = initial.index(
            "python -B build_search_entrypoints.py"
        )
        search_check = initial.index(
            "python -B build_search_entrypoints.py --check"
        )

        self.assertLess(route, search)
        self.assertLess(search, search_check)
        self.assertLess(initial.index("build_candidate_reference.py"), route)
        self.assertLess(search_check, initial.index("build_sitemaps.py"))

        rebase_start = text.index(
            "- name: Rebase, reconcile and push"
        )
        rebase = text[rebase_start:]

        rebase_command = rebase.index(
            "git rebase origin/main"
        )
        rebase_route = rebase.index(
            "python -B build_route_registry.py",
            rebase_command,
        )
        rebase_search = rebase.index(
            "python -B build_search_entrypoints.py",
            rebase_route,
        )
        rebase_search_check = rebase.index(
            "python -B build_search_entrypoints.py --check",
            rebase_search,
        )

        self.assertLess(
            rebase_command,
            rebase_route,
        )
        self.assertLess(
            rebase_route,
            rebase_search,
        )
        self.assertLess(
            rebase_search,
            rebase_search_check,
        )
        self.assertLess(rebase.index("build_candidate_reference.py"), rebase_route)
        self.assertLess(rebase_search_check, rebase.index("build_sitemaps.py"))

        commit = text[commit_start:rebase_start]

        self.assertIn(
            "index.html",
            commit,
        )
        self.assertIn(
            "en/index.html",
            commit,
        )

        self.assertIn(
            "index.html",
            rebase,
        )
        self.assertIn(
            "en/index.html",
            rebase,
        )

    def test_agenda_and_issue_follow_candidate_publication_not_universe(
        self,
    ):
        expected = {
            "Update polls",
            "Publish candidate family",
        }

        for filename in (
            "publish-agenda-family.yml",
            "publish-issue-family.yml",
        ):
            with self.subTest(workflow=filename):
                text = read_workflow(filename)
                producers = workflow_run_producers(
                    text
                )

                self.assertEqual(
                    producers,
                    expected,
                )
                self.assertNotIn(
                    "Update candidate universe",
                    producers,
                )

    def test_agenda_and_issue_defer_if_candidate_publication_is_not_ready(
        self,
    ):
        for filename in (
            "publish-agenda-family.yml",
            "publish-issue-family.yml",
        ):
            with self.subTest(workflow=filename):
                text = read_workflow(filename)

                self.assertIn(
                    "- name: Check candidate publication readiness",
                    text,
                )
                self.assertIn(
                    "id: candidate_readiness",
                    text,
                )
                self.assertIn(
                    "project_candidate_route_index",
                    text,
                )
                self.assertIn(
                    "route_registry.json",
                    text,
                )
                self.assertIn(
                    'output.write(f"ready={str(ready).lower()}\\n")',
                    text,
                )
                self.assertGreaterEqual(
                    text.count(
                        "steps.candidate_readiness.outputs.ready == 'true'"
                    ),
                    2,
                )

                readiness = text.index("- name: Check candidate publication readiness")
                for name in (
                    "Validate inputs and derive publication context",
                    "Build, validate and prove deterministic publication",
                    "Commit generated Agenda publication" if "agenda" in filename
                    else "Commit generated issue publication",
                ):
                    self.assertLess(readiness, text.index(f"- name: {name}"))
                    self.assertIn(
                        "if: steps.candidate_readiness.outputs.ready == 'true'",
                        workflow_step(text, name),
                    )
                code = inline_python(text, "Check candidate publication readiness")
                ast.parse(code)
                self.assertIn('["build_candidate_reference.py", "--all-active", "--check"]', code)
                self.assertIn('["build_search_entrypoints.py", "--check"]', code)


class CandidateDependencyExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = inline_python(
            read_workflow("publish-candidate-family.yml"),
            "Check candidate publication dependencies",
        )
        ast.parse(cls.code)
        cls.candidacy = registry([candidate(1), candidate(2, has_article=False)])
        cls.claims = claims_collector.build_public_bundle(
            cls.candidacy, [], 365, "2026-08-07T05:00:00Z"
        )
        cls.attention = build_payload(cls.candidacy)
        cls.news = json.loads((ROOT / "news_wire.json").read_text(encoding="utf-8"))
        cls.news["candidate_roster"] = news_collector.candidate_roster_metadata(cls.candidacy)

    def setUp(self):
        self.payloads = copy.deepcopy({
            "candidate_candidacy_status.json": self.candidacy,
            "claims_under_scrutiny.json": self.claims,
            "candidate_attention.json": self.attention,
            "news_wire.json": self.news,
        })

    def execute_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in self.payloads.items():
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            with in_directory(root), patch.dict(os.environ, {
                "GITHUB_OUTPUT": str(root / "output"),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
            }), redirect_stdout(io.StringIO()):
                exec(compile(self.code, "candidate-dependencies", "exec"), {})
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
            return (root / "output").read_text(encoding="utf-8")

    def test_aligned_artifacts_are_ready_without_mutation(self):
        self.assertEqual(self.execute_gate(), "ready=true\n")

    def test_each_legitimate_stale_revision_defers(self):
        for artifact, field in (
            ("claims_under_scrutiny.json", "candidate_query"),
            ("candidate_attention.json", "candidate_universe"),
            ("news_wire.json", "candidate_roster"),
        ):
            with self.subTest(artifact=artifact):
                self.setUp()
                self.payloads[artifact][field]["source_revision_id"] -= 1
                self.assertEqual(self.execute_gate(), "ready=false\n")

    def test_stale_attention_identities_defer(self):
        old_registry = registry([candidate(1)])
        self.payloads["candidate_attention.json"] = build_payload(old_registry)
        self.assertEqual(self.execute_gate(), "ready=false\n")

    def test_stale_news_names_defer(self):
        self.payloads["news_wire.json"]["candidate_roster"]["names"][0] = "Former Candidate"
        self.assertEqual(self.execute_gate(), "ready=false\n")

    def test_each_stale_provenance_timestamp_defers(self):
        for artifact, field in (
            ("claims_under_scrutiny.json", "candidate_query"),
            ("candidate_attention.json", "candidate_universe"),
            ("news_wire.json", "candidate_roster"),
        ):
            with self.subTest(artifact=artifact):
                self.setUp()
                self.payloads[artifact][field]["source_revision_timestamp"] = "2026-08-05T20:48:08Z"
                self.assertEqual(self.execute_gate(), "ready=false\n")

    def test_stale_claims_with_corrupt_reviews_remain_hard_failure(self):
        claims = self.payloads["claims_under_scrutiny.json"]
        claims["candidate_query"]["source_revision_id"] -= 1
        claims["reviews"] = [{}]
        with self.assertRaises(claims_collector.CollectorError):
            self.execute_gate()

    def test_stale_attention_with_corrupt_content_remains_hard_failure(self):
        attention = self.payloads["candidate_attention.json"]
        attention["candidate_universe"]["source_revision_id"] -= 1
        attention["candidates"][0]["daily_series"] = []
        with self.assertRaises(ValueError):
            self.execute_gate()

    def test_stale_news_with_corrupt_content_remains_hard_failure(self):
        news = self.payloads["news_wire.json"]
        news["candidate_roster"]["source_revision_id"] -= 1
        news["discovery"] = {}
        with self.assertRaises(RuntimeError):
            self.execute_gate()

    def test_malformed_news_roster_remains_hard_failure(self):
        for field, value in (
            ("source", "polls.json"), ("rule", "unknown"),
            ("count", True), ("count", 999), ("names", [None]),
            ("names", ["Duplicate", "Duplicate"]),
            ("source_revision_id", 0), ("source_revision_id", "old"),
            ("source_revision_timestamp", "invalid"),
            ("source_revision_timestamp", "2026-08-06T20:48:08"),
            ("status_as_of", "invalid"),
        ):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.payloads["news_wire.json"]["candidate_roster"][field] = value
                with self.assertRaises((SystemExit, ValueError)):
                    self.execute_gate()


class DownstreamReadinessExecutionTests(unittest.TestCase):
    def execute_gate(self, filename, *, mutate=None, check_failure=None):
        code = inline_python(read_workflow(filename), "Check candidate publication readiness")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidacy = registry([candidate(1)])
            (root / "candidate_candidacy_status.json").write_text(json.dumps(candidacy), encoding="utf-8")
            expected = route_builder._route_pair(
                route_key="candidates", family="candidates", kind="hub", entity_id="candidates",
                path_fr="/candidates/", path_en="/en/candidates/",
            ) + route_builder._route_pair(
                route_key="candidate:candidate-001", family="candidates", kind="candidate-detail",
                entity_id="candidate-001", path_fr="/candidates/candidate-001/",
                path_en="/en/candidates/candidate-001/",
            )
            for route in expected:
                for field, path_field in (
                    ("canonical_url", "path"), ("alternate_url_fr", "alternate_fr"),
                    ("alternate_url_en", "alternate_en"), ("x_default_url", "x_default"),
                ):
                    route[field] = route_builder._canonical_url(route[path_field])
                source = route_builder._source_file(route["path"])
                (root / source).parent.mkdir(parents=True, exist_ok=True)
                (root / source).write_text("<html>Published candidate</html>", encoding="utf-8")
                if route["kind"] == "candidate-detail":
                    (root / "candidates/candidate-001/data.json").write_text('{"candidate": "fixture"}', encoding="utf-8")
                route["source_file"] = source.as_posix()
                route["content_sha256"] = route_builder._route_content_hash(
                    route=route, root=root, source_path=root / source,
                )
            stored = {"schema_version": "1.0", "routes": expected}
            if mutate:
                mutate(root, stored)
            (root / "route_registry.json").write_text(json.dumps(stored), encoding="utf-8")
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

            def checked(arguments, **kwargs):
                self.assertEqual(arguments[1], "-B")
                self.assertIn("--check", arguments)
                return subprocess.CompletedProcess(
                    arguments, int(arguments[2] == check_failure), "", "stale artifact",
                )

            with in_directory(root), patch.dict(os.environ, {
                "GITHUB_OUTPUT": str(root / "output"),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
            }), patch("subprocess.run", side_effect=checked) as checks, redirect_stdout(io.StringIO()):
                exec(compile(code, filename, "exec"), {})
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
            return (root / "output").read_text(encoding="utf-8"), checks.call_args_list

    def test_complete_publication_is_ready_and_checks_both_builders(self):
        for filename in ("publish-agenda-family.yml", "publish-issue-family.yml"):
            with self.subTest(workflow=filename):
                output, checks = self.execute_gate(filename)
                self.assertEqual(output, "ready=true\n")
                self.assertEqual([call.args[0][2:] for call in checks], [
                    ["build_candidate_reference.py", "--all-active", "--check"],
                    ["build_search_entrypoints.py", "--check"],
                ])

    def test_incomplete_projection_stale_routes_and_hashes_defer(self):
        def missing_dossier(root, stored):
            (root / "en/candidates/candidate-001/index.html").unlink()

        def missing_hub_source(root, stored):
            (root / "en/candidates/index.html").unlink()

        def stale_source(root, stored):
            (root / "candidates/candidate-001/data.json").write_text('{"changed": true}', encoding="utf-8")

        mutations = [
            missing_dossier, missing_hub_source, stale_source,
            lambda root, stored: stored["routes"].pop(),
            lambda root, stored: stored["routes"].append(copy.deepcopy(stored["routes"][0])),
            lambda root, stored: stored["routes"][0].update(kind="candidate-detail"),
            lambda root, stored: stored["routes"][0].update(canonical_url="https://example.org/stale/"),
            lambda root, stored: stored["routes"][0].update(content_sha256="0" * 64),
            lambda root, stored: stored["routes"][0].update(source_file="unexpected.html"),
        ]
        for filename in ("publish-agenda-family.yml", "publish-issue-family.yml"):
            for index, mutate in enumerate(mutations):
                with self.subTest(workflow=filename, mutation=index):
                    output, checks = self.execute_gate(filename, mutate=mutate)
                    self.assertEqual(output, "ready=false\n")
                    self.assertEqual(checks, [])

    def test_either_read_only_builder_failure_defers(self):
        for filename in ("publish-agenda-family.yml", "publish-issue-family.yml"):
            for builder in ("build_candidate_reference.py", "build_search_entrypoints.py"):
                with self.subTest(workflow=filename, builder=builder):
                    output, checks = self.execute_gate(filename, check_failure=builder)
                    self.assertEqual(output, "ready=false\n")
                    self.assertEqual(len(checks), 2)


if __name__ == "__main__":
    unittest.main()
