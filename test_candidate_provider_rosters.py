"""Offline roster transitions using retained Wikipedia and published evidence."""
import copy
import gzip
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import fetch_candidate_candidacy_status as fetch
import reconcile_candidate_provider_rosters as repair
from candidate_candidacy_status import load_curated_candidacy_sources
from test_candidate_universe_workflow_contract import step_block


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "test_fixtures/candidate_universe"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def source_transition():
    responses = json.loads(gzip.decompress((FIXTURES / "wikipedia_240829045.json.gz").read_bytes()))

    def replay(params):
        match = next(row for row in responses if row["params"] == params)
        return copy.deepcopy(match["response"])

    bundle = json.loads(gzip.decompress((FIXTURES / "provider_evidence_68ad12f.json.gz").read_bytes()))
    with tempfile.TemporaryDirectory() as directory:
        sources = Path(directory) / "candidate_candidacy_sources.json"
        sources.write_text(bundle["candidate_candidacy_sources.json"], encoding="utf-8")
        return fetch.fetch_candidate_candidacy_status(
            replay, previous_registry=load("previous_registry_240468913.json"),
            curated_sources=load_curated_candidacy_sources(sources), as_of="2026-10-30T10:49:08Z",
        ).payload


class ProviderRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = source_transition()
        cls.previous = load("previous_registry_240468913.json")
        cls.bundle = json.loads(gzip.decompress(
            (FIXTURES / "provider_evidence_68ad12f.json.gz").read_bytes()))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, content in self.bundle.items():
            (self.root / name).write_text(content, encoding="utf-8", newline="\n")
        self.previous_path = self.root / "previous.json"
        self.expected_path = self.root / "expected.json"
        self.previous_path.write_text(self.bundle["candidate_candidacy_status.json"], encoding="utf-8", newline="\n")
        self.write("expected.json", self.registry)
        self.write("candidate_candidacy_status.json", self.registry)

    def write(self, name, payload):
        (self.root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def read(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def run_repair(self, **kwargs):
        return repair.reconcile(self.root, previous_registry_path=self.previous_path,
                                expected_registry_path=self.expected_path, **kwargs)

    def bytes(self):
        return {name: (self.root / name).read_bytes() for name in repair.OUTPUTS}

    def test_exact_revision_roster_and_status_difference(self):
        old = {r["candidate_id"]: r for r in self.previous["candidates"]}
        new = {r["candidate_id"]: r for r in self.registry["candidates"]}
        self.assertEqual(self.registry["source"]["revision_id"], 240829045)
        self.assertEqual(self.registry["source"]["revision_timestamp"], "2026-10-29T14:15:52Z")
        self.assertEqual(new.keys() - old.keys(), {"gerard-larcher"})
        self.assertFalse(old.keys() - new.keys())
        self.assertEqual(len(old.keys() & new.keys()), 76)
        self.assertFalse([i for i in old if old[i]["candidate_name"] != new[i]["candidate_name"]])
        transitions = {i: (old[i]["status"], new[i]["status"]) for i in old
                       if old[i]["status"] != new[i]["status"]}
        self.assertEqual(transitions, {i: ("declared", "primary_contender")
                                      for i in ("gabriel-attal", "bruno-retailleau")})

    def test_new_unmapped_candidate_has_only_empty_evidence(self):
        self.run_repair()
        for provider in repair.MAPPINGS:
            snapshot = self.read(f"candidate_{provider}.json")
            row = next(r for r in snapshot["candidates"] if r["candidate_id"] == "gerard-larcher")
            self.assertTrue(row["status"].startswith("unavailable_no_"))
            self.assertTrue(all(v is None for k, v in row.items() if k not in {"candidate_id", "status"}))
            history = self.read(f"candidate_{provider}_history.json")
            row = next(r for r in history["candidates"] if r["candidate_id"] == "gerard-larcher")
            self.assertEqual(row["points"], [])

    def test_reviewed_candidates_all_observations_history_and_clocks_preserved(self):
        before = {name: self.read(name) for name in repair.OUTPUTS}
        self.run_repair()
        for name, original in before.items():
            result = self.read(name)
            self.assertEqual({k: v for k, v in result.items() if k != "candidates"},
                             {k: v for k, v in original.items() if k != "candidates"})
            kept = {r["candidate_id"]: r for r in result["candidates"]}
            for row in original["candidates"]:
                self.assertEqual(kept[row["candidate_id"]], row)
        bluesky = self.read("candidate_bluesky.json")
        self.assertEqual(sum(r["status"] == "observed" for r in bluesky["candidates"]), 6)

    def test_unchanged_roster_is_byte_identical(self):
        self.write("candidate_candidacy_status.json", self.previous)
        self.write("expected.json", self.previous)
        before = self.bytes()
        self.run_repair()
        self.assertEqual(self.bytes(), before)

    def test_legitimate_status_transition_is_not_an_identity_change(self):
        registry = copy.deepcopy(self.registry)
        registry["candidates"] = [r for r in registry["candidates"] if r["candidate_id"] != "gerard-larcher"]
        self.write("candidate_candidacy_status.json", registry)
        self.write("expected.json", registry)
        before = self.bytes()
        self.run_repair()
        self.assertEqual(self.bytes(), before)

    def test_unavailable_evidence_is_preserved_without_numeric_points(self):
        from candidate_bluesky import empty_record
        for status in ("unavailable_account_missing", "unavailable_public_web_opt_out"):
            with self.subTest(status=status):
                snapshot = json.loads(self.bundle["candidate_bluesky.json"])
                row = next(r for r in snapshot["candidates"] if r["status"] == "observed")
                cid = row["candidate_id"]
                snapshot["candidates"][snapshot["candidates"].index(row)] = empty_record(cid, row, status=status)
                history = json.loads(self.bundle["candidate_bluesky_history.json"])
                result, retained = repair.reconcile_provider(
                    "bluesky", snapshot, history, self.read(repair.MAPPINGS["bluesky"]), self.previous, self.registry)
                self.assertEqual(next(r for r in result["candidates"] if r["candidate_id"] == cid),
                                 empty_record(cid, row, status=status))
                self.assertEqual(next(r for r in retained["candidates"] if r["candidate_id"] == cid),
                                 next(r for r in history["candidates"] if r["candidate_id"] == cid))

    def assert_failure_preserves_bundle(self, pattern=None):
        before = self.bytes()
        with self.assertRaisesRegex(ValueError, pattern or ".+"):
            self.run_repair()
        self.assertEqual(self.bytes(), before)

    def test_failed_or_incomplete_collection_cannot_be_reconciled(self):
        snapshot = self.read("candidate_bluesky.json")
        snapshot["candidates"] = [r for r in snapshot["candidates"] if r["status"] != "observed"]
        self.write("candidate_bluesky.json", snapshot)
        self.assert_failure_preserves_bundle()

    def test_unverified_did_mapping_changes_are_rejected(self):
        mapping = self.read(repair.MAPPINGS["bluesky"])
        mapping["accounts"][0]["did"] = "did:plc:bbbbbbbbbbbbbbbbbbbbbbbb"
        self.write(repair.MAPPINGS["bluesky"], mapping)
        self.assert_failure_preserves_bundle("published provider evidence or reviewed mapping changed")

    def test_unverified_review_handle_or_url_change_is_rejected(self):
        mapping = self.read(repair.MAPPINGS["bluesky"])
        mapping["accounts"][0]["verification_url"] = "https://unreviewed.example.test/"
        self.write(repair.MAPPINGS["bluesky"], mapping)
        self.assert_failure_preserves_bundle("published provider evidence or reviewed mapping changed")

    def test_history_validator_still_rejects_changed_identity(self):
        from candidate_bluesky_history import validate_candidate_bluesky_history
        self.run_repair()
        history = self.read("candidate_bluesky_history.json")
        next(r for r in history["candidates"] if r["did"] is not None)["did"] = "did:plc:bbbbbbbbbbbbbbbbbbbbbbbb"
        with self.assertRaisesRegex(ValueError, "history mapping identity mismatch"):
            validate_candidate_bluesky_history(history, mapping=self.read(repair.MAPPINGS["bluesky"]),
                candidate_ids=repair.registry_ids(self.registry), snapshot=self.read("candidate_bluesky.json"))

    def test_new_reviewed_mapping_requires_authoritative_collection(self):
        mapping = self.read(repair.MAPPINGS["bluesky"])
        mapping["accounts"][0]["candidate_id"] = "gerard-larcher"
        with self.assertRaisesRegex(ValueError, "outside canonical registry"):
            repair.reconcile_provider("bluesky", self.read("candidate_bluesky.json"),
                self.read("candidate_bluesky_history.json"), mapping, self.previous, self.registry)

    def test_missing_duplicate_candidate_ids_fail_before_any_write(self):
        for name in repair.OUTPUTS:
            original = self.read(name)
            for duplicate in (False, True):
                with self.subTest(name=name, duplicate=duplicate):
                    changed = copy.deepcopy(original)
                    if duplicate:
                        changed["candidates"].append(copy.deepcopy(changed["candidates"][0]))
                    else:
                        changed["candidates"].pop()
                    self.write(name, changed)
                    self.assert_failure_preserves_bundle()
                    self.write(name, original)

    def test_registry_removal_and_identity_change_require_review(self):
        registry = copy.deepcopy(self.registry)
        registry["candidates"].pop(0)
        self.write("candidate_candidacy_status.json", registry)
        self.write("expected.json", registry)
        self.assert_failure_preserves_bundle("removed historical candidates")

    def test_source_or_roster_change_since_authentication_fails(self):
        for change in ("source", "roster"):
            with self.subTest(change=change):
                registry = copy.deepcopy(self.registry)
                if change == "source":
                    registry["source"]["revision_id"] += 1
                else:
                    registry["candidates"].pop()
                self.write("candidate_candidacy_status.json", registry)
                self.assert_failure_preserves_bundle("since authentication")

    def test_source_change_during_reconciliation_fails_before_any_write(self):
        original = repair.reconcile_provider
        def raced(*args):
            result = original(*args)
            self.expected_path.write_text('{}', encoding="utf-8")
            return result
        with patch.object(repair, "reconcile_provider", side_effect=raced):
            self.assert_failure_preserves_bundle("changed during reconciliation")

    def test_post_rebase_uses_upstream_evidence_and_revalidates_mapping(self):
        upstream = self.root / "upstream"
        upstream.mkdir()
        for name, content in self.bundle.items():
            (upstream / name).write_text(content, encoding="utf-8", newline="\n")
        # Represent an older local publication by retaining an earlier real point;
        # no new count or successful collection time is invented for this test.
        history = self.read("candidate_bluesky_history.json")
        row = next(r for r in history["candidates"] if len(r["points"]) > 1)
        row["points"].pop()
        self.write("candidate_bluesky_history.json", history)
        self.run_repair(evidence_root=upstream)
        restored = {r["candidate_id"]: r for r in self.read("candidate_bluesky_history.json")["candidates"]}
        for row in json.loads(self.bundle["candidate_bluesky_history.json"])["candidates"]:
            self.assertEqual(restored[row["candidate_id"]], row)
        mapping = self.read(repair.MAPPINGS["bluesky"])
        mapping["accounts"][0]["reviewed_handle"] = "unverified.bsky.social"
        self.write(repair.MAPPINGS["bluesky"], mapping)
        before = self.bytes()
        with self.assertRaisesRegex(ValueError, "mapping changed during rebase"):
            self.run_repair(evidence_root=upstream)
        self.assertEqual(self.bytes(), before)

    def test_post_rebase_newer_registry_fails_closed(self):
        previous = copy.deepcopy(self.registry)
        previous["source"]["revision_id"] += 1
        previous["source"]["revision_url"] = previous["source"]["revision_url"].replace("240829045", "240829046")
        # Check the source pin directly, before old evidence would be considered.
        with self.assertRaisesRegex(ValueError, "revision moved backwards"):
            repair.reconcile_provider("bluesky", {}, {}, {}, previous, self.registry)

    def test_reconciliation_bytes_are_stable_across_python_processes(self):
        upstream = self.root / "upstream"
        upstream.mkdir()
        for name, content in self.bundle.items():
            (upstream / name).write_text(content, encoding="utf-8", newline="\n")
        command = [sys.executable, "-B", str(ROOT / "reconcile_candidate_provider_rosters.py"),
                   "--previous-registry", str(self.previous_path),
                   "--expected-registry", str(self.expected_path), "--evidence-root", str(upstream)]
        outputs = []
        for seed in ("1", "2", "3"):
            result = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                    env={**os.environ, "PYTHONHASHSEED": seed})
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(self.bytes())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])

    def test_manifest_reproduces_failure_then_complete_update_passes(self):
        import build_publication_manifest as manifest
        # Only the input files of the existing manifest and derived builders.
        names = {name for values in manifest.LANE_FILES.values() for name in values}
        names.update(("campaign_event_institutional_seeds.json", "campaign_event_sources.json",
                      "campaign_events_manual.json", "campaign_event_updates_manual.json"))
        for name in names:
            if not (self.root / name).exists():
                shutil.copyfile(ROOT / name, self.root / name)
        for script in ("build_campaign_events.py", "build_candidate_signals.py",
                       "build_candidate_visibility_history.py", "build_candidate_agenda_history.py"):
            args = [sys.executable, "-B", str(ROOT / script)]
            if script == "build_campaign_events.py":
                args += ["--generated-at", "2026-10-31T12:00:00Z", "--preserve-generated-at-from", "campaign_events.json",
                         "--seeds", str(self.root / "campaign_event_institutional_seeds.json"),
                         "--sources", str(self.root / "campaign_event_sources.json"),
                         "--candidates", str(self.root / "candidate_candidacy_status.json"),
                         "--manual-events", str(self.root / "campaign_events_manual.json"),
                         "--event-updates", str(self.root / "campaign_event_updates_manual.json"),
                         "--output", str(self.root / "campaign_events.json")]
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaisesRegex(manifest.ManifestError,
                                    "candidate_bluesky invalid publication: candidate universe differs"):
            manifest.build_manifest(self.root)
        preserved = {name: (self.root / name).read_bytes() for name in names
                     if name not in repair.OUTPUTS}
        files_before = set(self.root.iterdir())
        self.run_repair()
        result = manifest.build_manifest(self.root, published_at="2026-10-31T12:00:00Z")
        manifest.validate_manifest(result)
        baseline_manifest = json.loads(self.bundle["publication_manifest.json"])
        self.assertEqual(result["lanes"]["polls"], baseline_manifest["lanes"]["polls"])
        for provider in repair.MAPPINGS:
            self.assertTrue(result["lanes"][f"candidate_{provider}"]["valid"])
            self.assertTrue(result["lanes"][f"candidate_{provider}_history"]["valid"])
        self.assertEqual(set(self.root.iterdir()), files_before)
        for name, content in preserved.items():
            self.assertEqual((self.root / name).read_bytes(), content, name)
        self.assertEqual({len(self.read(name)["candidates"]) for name in repair.OUTPUTS}, {77})

    def test_workflow_reconciles_and_validates_before_commit_and_push(self):
        workflow = (ROOT / ".github/workflows/update-candidate-universe.yml").read_text(encoding="utf-8")
        initial = workflow.index("Reconcile stored provider rosters on registry change")
        self.assertLess(initial, workflow.index("Rebuild publication manifest on registry change"))
        self.assertLess(initial, workflow.index('git commit -m "Update candidate universe"'))
        block = step_block(workflow, "Commit, rebase, validate, and push candidate universe")
        rebase = block.index("git rebase origin/main")
        reconcile = block.index("python -B reconcile_candidate_provider_rosters.py", rebase)
        self.assertLess(reconcile, block.index("build_manifest(", rebase))
        self.assertIn('--evidence-root /tmp/candidate-provider-upstream', block)
        self.assertLess(block.index("--check \\\n            --published-at"), block.index("git push origin HEAD:main"))
        for name in repair.OUTPUTS:
            self.assertGreaterEqual(block.count(name), 6, name)

    def workflow_transaction(self, *, fail=False):
        """Execute the real workflow shell bodies against a local bare remote."""
        bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
        self.assertTrue(Path(bash).is_file(), "Bash is required for workflow transaction regression")
        checkout = self.root / "checkout"
        checkout.mkdir()
        names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        for name in filter(None, names):
            source, target = ROOT / name, checkout / name
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        shutil.copyfile(ROOT / "reconcile_candidate_provider_rosters.py",
                        checkout / "reconcile_candidate_provider_rosters.py")
        for name, content in self.bundle.items():
            (checkout / name).write_text(content, encoding="utf-8", newline="\n")
        if fail:
            history = json.loads(self.bundle["candidate_polymarket_history.json"])
            history["candidates"].pop()
            (checkout / "candidate_polymarket_history.json").write_text(json.dumps(history), encoding="utf-8")

        def git(*args, cwd=checkout):
            return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.STDOUT).decode().strip()

        remote = self.root / "origin.git"
        git("init", "--bare", "--initial-branch=main", str(remote))
        git("init", "--initial-branch=main")
        git("config", "user.name", "Offline regression")
        git("config", "user.email", "offline@example.test")
        git("config", "core.autocrlf", "true" if os.name == "nt" else "false")
        git("add", ".")
        git("commit", "-qm", "Authenticated baseline")
        git("remote", "add", "origin", str(remote))
        git("push", "-u", "origin", "main")
        baseline = git("rev-parse", "HEAD")
        if not fail:
            # Advance main independently before the workflow fetch/rebase.
            upstream = self.root / "upstream-checkout"
            git("clone", str(remote), str(upstream))
            git("config", "user.name", "Offline upstream", cwd=upstream)
            git("config", "user.email", "offline@example.test", cwd=upstream)
            (upstream / "upstream-note.txt").write_text("Independent main advance\n", encoding="utf-8")
            git("add", "upstream-note.txt", cwd=upstream)
            git("commit", "-qm", "Advance main", cwd=upstream)
            git("push", "origin", "main", cwd=upstream)
            advanced = git("rev-parse", "HEAD", cwd=upstream)
        scratch = self.root / "scratch"
        scratch.mkdir()
        (scratch / "candidate_candidacy_status.json").write_text(json.dumps(self.registry), encoding="utf-8")
        (scratch / "candidate-universe-fetch.json").write_text(json.dumps({"raw_candidate_count": 77}), encoding="utf-8")
        workflow = (ROOT / ".github/workflows/update-candidate-universe.yml").read_text(encoding="utf-8")
        stages = (
            "Validate candidate and promote semantic change atomically",
            "Rebuild Campaign Events on registry change",
            "Rebuild Candidate Signals on registry change",
            "Rebuild Candidate Visibility History on registry change",
            "Rebuild Candidate Agenda History on registry change",
            "Rebuild semantic search entrypoints on registry change",
            "Reconcile stored provider rosters on registry change",
            "Rebuild publication manifest on registry change",
            "Verify bounded generated-file scope",
            "Commit, rebase, validate, and push candidate universe",
        )
        script = "set -euo pipefail\n" + "\n".join(textwrap.dedent(
            step_block(workflow, name).split("        run: |\n", 1)[1]) for name in stages)
        script = script.replace("/tmp/", scratch.as_posix() + "/")
        script = script.replace("${{ steps.registry.outputs.changed }}", "true")
        script = script.replace("python ", shlex.quote(sys.executable.replace("\\", "/")) + " ")
        script_path = self.root / "transaction.sh"
        script_path.write_text(script, encoding="utf-8", newline="\n")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "GITHUB_OUTPUT": str(self.root / "github-output")}
        result = subprocess.run([bash, str(script_path)], cwd=checkout, env=env,
                                capture_output=True, text=True, timeout=180)
        remote_sha = git("rev-parse", "refs/heads/main", cwd=remote)
        if fail:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("published provider evidence or reviewed mapping changed", result.stderr)
            self.assertEqual(git("rev-parse", "HEAD"), baseline)
            self.assertEqual(remote_sha, baseline)
        else:
            diagnostic = "\n".join(line[:800] for line in (result.stdout + result.stderr).splitlines()
                                   if not line.startswith("warning:"))
            self.assertEqual(result.returncode, 0, diagnostic[-12000:])
            self.assertEqual(git("rev-parse", "HEAD"), remote_sha)
            self.assertEqual(git("rev-parse", "HEAD^"), advanced)
            self.assertFalse(git("status", "--porcelain"))
            for name in repair.OUTPUTS:
                payload = json.loads((checkout / name).read_text(encoding="utf-8"))
                self.assertEqual(repair.registry_ids(self.registry), {r["candidate_id"] for r in payload["candidates"]})
            changed = set(git("diff", "--name-only", advanced, "HEAD").splitlines())
            self.assertEqual(changed, {*repair.OUTPUTS, "candidate_candidacy_status.json",
                "candidate_signals.json", "candidate_visibility_history.json", "candidate_agenda_history.json",
                "index.html", "en/index.html", "publication_manifest.json"})

    def test_actual_workflow_post_rebase_regeneration_and_exact_generated_scope(self):
        self.workflow_transaction()

    def test_actual_workflow_failure_has_no_commit_or_push(self):
        self.workflow_transaction(fail=True)


if __name__ == "__main__":
    unittest.main()
