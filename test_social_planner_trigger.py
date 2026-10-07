"""Fail-closed production snapshot barrier and executable planner trigger contract."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "social"))
import daily_queue as queue
import planner_readiness as readiness

WORKFLOW = (ROOT / ".github/workflows/publish-x-fr.yml").read_text(encoding="utf-8")
BASH = shutil.which("bash") or next((str(p) for p in (
    Path("C:/Program Files/Git/bin/bash.exe"),
    Path("C:/Program Files/Git/usr/bin/bash.exe")) if p.exists()), None)


def step(name):
    return WORKFLOW.split("      - name: " + name + "\n", 1)[1].split("      - name:", 1)[0]


def evaluate(expression, values):
    expression = expression.strip().removeprefix(">-").strip()
    expression = re.sub(r"(?:steps|vars|github)\.[\w.]+",
                        lambda match: repr(values[match[0]]), expression)
    return eval(" ".join(expression.replace("&&", " and ").replace("||", " or ").split()),
                {"__builtins__": {}}, {"contains": lambda items, item: item in items,
                                        "fromJSON": json.loads})


class PlannerTriggerTests(unittest.TestCase):
    now = datetime.fromisoformat("2026-10-07T08:00:00+02:00")

    def fixture(self, root):
        stamp = (self.now - timedelta(minutes=30)).isoformat()
        for name, payload in {
            "news_wire.json": {"generated_at": stamp},
            "issue_coverage_history.json": {"data_as_of": stamp},
            "agenda_coverage_history.json": {"data_as_of": stamp},
            "campaign_events.json": {"generated_at": "2026-01-01T00:00:00Z", "campaign_events": []},
            "recent_changes.json": {"items": []},
            "route_registry.json": {"routes": []},
        }.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")

    def checker(self, root, script, *args):
        if script == "build_campaign_events.py":
            output = Path(args[args.index("--output") + 1])
            output.write_bytes((root / "campaign_events.json").read_bytes())

    def resolve(self, *, event="workflow_run", conclusion="success", cron="",
                ready=True, branch="main", repository="openeventbits/france-2027-signal-lab",
                upstream_event="schedule", mode="build-queue", publish="true"):
        if not BASH:
            self.skipTest("Bash is required to execute the workflow resolver")
        script = step("Resolve execution mode").split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in script.splitlines())
        values = {"github.event_name": event, "github.event.schedule": cron,
                  "inputs.mode": mode, "inputs.publish": publish, "inputs.slot": "10:15"}
        script = re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda m: values[m[1]], script)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            env = {**os.environ, "GITHUB_OUTPUT": output.as_posix(),
                   "GITHUB_REPOSITORY": "openeventbits/france-2027-signal-lab",
                   "UPSTREAM_CONCLUSION": conclusion, "UPSTREAM_BRANCH": branch,
                   "UPSTREAM_REPOSITORY": repository, "UPSTREAM_EVENT": upstream_event}
            # The real Bash control flow runs; only the local readiness process
            # is replaced, to test both outcomes without using production data.
            script = f"python() {{ return {0 if ready else 1}; }}\n" + script
            result = subprocess.run([BASH, "-c", script], env=env, cwd=ROOT,
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())

    def allowed(self, name, outputs, flag):
        values = {f"steps.mode.outputs.{key}": value for key, value in outputs.items()}
        values["vars.FR27_BUFFER_SCHEDULING_ENABLED"] = flag
        values["github.event_name"] = "workflow_run"
        values["steps.dynamic_timeliness.outputs.eligible"] = ""
        expression = step(name).split("        if:", 1)[1].split("        shell:", 1)[0]
        return evaluate(expression, values)

    def test_success_and_0825_fallback_resolve_to_build_queue(self):
        for event, cron in (("workflow_run", ""), ("schedule", "25 8 * * *")):
            with self.subTest(event=event):
                self.assertEqual(self.resolve(event=event, cron=cron),
                                 {"mode": "build-queue", "publish": "true", "slot": ""})
        self.assertIn("- cron: '25 8 * * *'\n      timezone: 'Europe/Paris'", WORKFLOW)

    def test_failed_cancelled_untrusted_and_non_main_events_are_inert(self):
        cases = [{"conclusion": c} for c in ("failure", "cancelled", "timed_out", "skipped", "")]
        cases += [{"branch": "feature"}, {"repository": "fork/repository"},
                  {"upstream_event": "pull_request"}]
        for case in cases:
            with self.subTest(case=case):
                outputs = self.resolve(**case)
                self.assertEqual(outputs["mode"], "planner-deferred")
                self.assertEqual(outputs["publish"], "false")

    def test_automatic_job_master_and_upstream_gates(self):
        expression = WORKFLOW.split("    if: >-", 1)[1].split("    # Acquire", 1)[0]
        for master in ("", "false", "true"):
            for conclusion in ("success", "failure", "cancelled"):
                values = {"github.event_name": "workflow_run", "vars.FR27_SOCIAL_ENABLED": master,
                          "github.event.workflow_run.conclusion": conclusion,
                          "github.event.workflow_run.head_branch": "main",
                          "github.event.workflow_run.head_repository.full_name": "owner/repo",
                          "github.repository": "owner/repo", "github.event.workflow_run.event": "schedule"}
                self.assertEqual(evaluate(expression, values), master == "true" and conclusion == "success")

    def test_readiness_failure_blocks_all_planner_side_effects(self):
        for event, cron in (("workflow_run", ""), ("schedule", "25 8 * * *"),
                            ("workflow_dispatch", "")):
            outputs = self.resolve(event=event, cron=cron, ready=False)
            self.assertEqual(outputs["mode"], "planner-deferred")
            for name in ("Validate Buffer configuration", "Build immutable daily core queue",
                         "Reconcile prior Buffer delivery before queue rollover",
                         "Schedule frozen core posts with Buffer clock"):
                self.assertFalse(self.allowed(name, outputs, "true"), name)
            for name in ("Inspect persistent social state branch", "Persist unified social state"):
                self.assertNotIn('"planner-deferred"', step(name))
        self.assertLess(WORKFLOW.index("social/planner_readiness.py"),
                        WORKFLOW.index("- name: Validate Buffer configuration"))

    def test_planning_lock_is_acquired_before_checkout_and_state_writes_are_serial(self):
        self.assertIn("group: fr27-social-publish\n  cancel-in-progress: false\n  queue: max", WORKFLOW)
        job_lock = WORKFLOW.split("    concurrency:", 1)[1].split("    runs-on:", 1)[0]
        for value in ("workflow_run", "25 8 * * *", "inputs.mode == 'build-queue'",
                      "'production-data-update'", "queue: max", "cancel-in-progress: false"):
            self.assertIn(value, job_lock)
        for name in ("update-news-wire", "update-polls", "update-candidate-universe",
                     "publish-issue-family", "publish-agenda-family", "publish-candidate-family"):
            producer = (ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8")
            self.assertIn("group: production-data-update", producer)
            self.assertIn(producer.split("name: ", 1)[1].splitlines()[0], WORKFLOW.split("  schedule:", 1)[0])

    def test_barrier_checks_both_full_histories_pages_routes_and_events_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with patch.object(readiness, "check_command", side_effect=self.checker) as check:
                readiness.verify_readiness(root=root, now=self.now)
            self.assertEqual([c.args[1] for c in check.call_args_list], [
                "build_issue_coverage_history.py", "build_issue_pages.py",
                "build_agenda_coverage_history.py", "build_agenda_pages.py",
                "build_route_registry.py", "build_campaign_events.py"])
            for call in check.call_args_list[:-1]:
                self.assertEqual(call.args[2:], ("--check",))
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_stale_future_missing_malformed_and_overnight_inputs_fail_closed(self):
        cases = [("news_wire.json", {"generated_at": stamp}) for stamp in (
            "2026-10-06T23:59:00Z", "2026-10-07T00:00:00Z", "2026-10-07T08:00:00Z",
            "2026-10-07T05:30:00", "garbage")]
        cases += [("issue_coverage_history.json", {"data_as_of": "2026-10-07T05:00:00Z"}),
                  ("agenda_coverage_history.json", {"data_as_of": "2026-10-07T05:00:00Z"}),
                  ("news_wire.json", None), ("recent_changes.json", [])]
        for name, payload in cases:
            with self.subTest(name=name, payload=payload), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                if payload is None:
                    (root / name).unlink()
                else:
                    (root / name).write_text(json.dumps(payload), encoding="utf-8")
                with patch.object(readiness, "check_command", side_effect=self.checker):
                    with self.assertRaises((ValueError, OSError)):
                        readiness.verify_readiness(root=root, now=self.now)
        with patch.object(readiness, "load_json") as load:
            with self.assertRaisesRegex(ValueError, "06:00"):
                readiness.verify_readiness(root=ROOT, now=self.now.replace(hour=1))
            load.assert_not_called()

    def test_equal_timestamps_do_not_allow_partial_histories_or_stale_pages_routes(self):
        for failed in ("build_issue_coverage_history.py", "build_agenda_coverage_history.py",
                       "build_issue_pages.py", "build_agenda_pages.py", "build_route_registry.py"):
            with self.subTest(check=failed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                def reject(root, script, *args):
                    if script == failed:
                        raise subprocess.CalledProcessError(1, script)
                    self.checker(root, script, *args)
                with patch.object(readiness, "check_command", side_effect=reject), \
                     patch.object(queue, "build_core_plan") as build, \
                     patch.object(queue.social_publish.BufferClient, "from_env") as buffer:
                    try:
                        readiness.verify_readiness(root=root, now=self.now)
                        queue.build_queue(state={}, now=self.now)
                    except subprocess.CalledProcessError:
                        pass
                    else:
                        self.fail("partial production publication must defer planning")
                    outputs = self.resolve(ready=False)
                    self.assertFalse(self.allowed("Schedule frozen core posts with Buffer clock", outputs, "true"))
                    build.assert_not_called()
                    buffer.assert_not_called()

    def test_unsynchronized_campaign_events_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            def changed(root, script, *args):
                self.checker(root, script, *args)
                if script == "build_campaign_events.py":
                    Path(args[args.index("--output") + 1]).write_text('{"changed": true}', encoding="utf-8")
            with patch.object(readiness, "check_command", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "authoritative inputs"):
                    readiness.verify_readiness(root=root, now=self.now)

    def test_news_freshness_boundary_and_timezone_aware_clock(self):
        for age, accepted in ((timedelta(hours=6), True),
                              (timedelta(hours=6, seconds=1), False),
                              (timedelta(seconds=-1), False)):
            with self.subTest(age=age), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                stamp = (self.now - age).isoformat()
                for name, field in (("news_wire.json", "generated_at"),
                                    ("issue_coverage_history.json", "data_as_of"),
                                    ("agenda_coverage_history.json", "data_as_of")):
                    (root / name).write_text(json.dumps({field: stamp}), encoding="utf-8")
                with patch.object(readiness, "check_command", side_effect=self.checker):
                    if accepted:
                        readiness.verify_readiness(root=root, now=self.now)
                    else:
                        with self.assertRaisesRegex(ValueError, "six hours"):
                            readiness.verify_readiness(root=root, now=self.now)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            readiness.verify_readiness(root=ROOT, now=self.now.replace(tzinfo=None))

    def test_cli_only_emits_receipt_after_readiness_success(self):
        for ready in (False, True):
            with self.subTest(ready=ready), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                proof = root / "proof.json"
                with patch.object(readiness, "ROOT", root), \
                     patch.object(readiness, "verify_readiness",
                                  side_effect=None if ready else subprocess.TimeoutExpired("checker", 180)), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(readiness.main(["--now", self.now.isoformat(), "--proof-output", str(proof)]),
                                     0 if ready else 1)
                    self.assertEqual(proof.exists(), ready)
                    if ready:
                        readiness.validate_proof(json.loads(proof.read_text(encoding="utf-8")), root=root, now=self.now)

    def run_planner(self, path, flag):
        outputs = self.resolve()
        self.assertTrue(self.allowed("Build immutable daily core queue", outputs, flag))
        self.fixture(path.parent)
        proof_path = path.parent / "proof.json"
        proof_path.write_text(json.dumps(readiness.snapshot_proof(root=path.parent, now=self.now)), encoding="utf-8")
        args = queue.build_parser().parse_args(["build", "--state", str(path),
            "--state-output", str(path), "--now", self.now.isoformat(), "--readiness-proof", str(proof_path)])
        with patch.object(queue, "ROOT", path.parent):
            self.assertEqual(args.func(args), 0)
        if self.allowed("Schedule frozen core posts with Buffer clock", outputs, flag):
            args = queue.build_parser().parse_args(["schedule-frozen", "--state", str(path),
                "--state-output", str(path), "--now", self.now.isoformat()])
            self.assertEqual(args.func(args), 0)

    def test_repeated_ready_event_builds_with_disabled_flag_need_no_credentials_or_api(self):
        for flag in ("", "false"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "state.json"
                state = queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=self.now)
                queue.save_state(path, state)
                outputs = self.resolve()
                for name in ("Validate Buffer configuration", "Reconcile prior Buffer delivery before queue rollover",
                             "Schedule frozen core posts with Buffer clock"):
                    self.assertFalse(self.allowed(name, outputs, flag))
                with patch.dict(os.environ, {"FR27_BUFFER_SCHEDULING_ENABLED": flag}, clear=True), \
                     patch.object(queue, "build_core_plan", return_value=self.plan()) as build, \
                     patch.object(queue.social_publish.BufferClient, "from_env") as buffer, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.run_planner(path, flag)
                    first = path.read_bytes()
                    self.run_planner(path, flag)
                    self.assertEqual(first, path.read_bytes())
                    build.assert_called_once()
                    buffer.assert_not_called()

    def plan(self):
        return {"fr_posts": [dict(locale="fr", slot="10:15", lane="today_events",
            key="fixture:events", text="Frozen events https://france2027.app/", score=None)], "en_posts": []}

    def test_repeated_ready_events_preserve_one_buffer_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=self.now)
            queue.save_state(path, state)
            client = Mock()
            client.recent_posts.return_value = []
            client.create_scheduled_post.return_value = {"id": "fixture-buffer-receipt", "status": "scheduled",
                                                        "dueAt": "2026-10-07T08:15:00Z"}
            with patch.dict(os.environ, {"FR27_BUFFER_SCHEDULING_ENABLED": "true"}), \
                 patch.object(queue, "build_core_plan", return_value=self.plan()) as build, \
                 patch.object(queue.social_publish.BufferClient, "from_env", return_value=client), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.run_planner(path, "true")
                first = path.read_bytes()
                self.run_planner(path, "true")
                self.assertEqual(path.read_bytes(), first)
                build.assert_called_once()
                client.create_scheduled_post.assert_called_once()
                item = queue.queue_from_state(json.loads(first))["items"][0]
                self.assertEqual(item["buffer_post_id"], "fixture-buffer-receipt")
                self.assertEqual(item["status"], "scheduled")

    def test_unproven_existing_queue_and_changed_snapshot_cannot_be_scheduled_by_planner(self):
        for problem in ("legacy-queue", "changed-input", "missing-proof"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                path, proof_path = root / "state.json", root / "proof.json"
                proof = readiness.snapshot_proof(root=root, now=self.now)
                proof_path.write_text(json.dumps(proof), encoding="utf-8")
                state = queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=self.now)
                if problem == "legacy-queue":
                    queue.attach_queue(state, queue.new_queue(queue_date="2026-10-07", created_at=self.now,
                                                             posts=self.plan()["fr_posts"]))
                elif problem == "changed-input":
                    (root / "issue_coverage_history.json").write_text('{"changed": true}', encoding="utf-8")
                else:
                    proof_path.unlink()
                queue.save_state(path, state)
                before = path.read_bytes()
                args = queue.build_parser().parse_args(["build", "--state", str(path),
                    "--state-output", str(path), "--now", self.now.isoformat(),
                    "--readiness-proof", str(proof_path)])
                with patch.object(queue, "ROOT", root), \
                     patch.object(queue, "build_core_plan") as build, \
                     patch.object(queue.social_publish.BufferClient, "from_env") as buffer:
                    with self.assertRaises((ValueError, OSError)):
                        args.func(args)
                    self.assertEqual(before, path.read_bytes())
                    build.assert_not_called()
                    buffer.assert_not_called()

    def test_old_proven_queue_receipt_survives_new_ready_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            state = queue.social_publish.build_bootstrap_state({"items": []}, {"campaign_events": []}, now=self.now)
            frozen = queue.new_queue(queue_date="2026-10-07", created_at=self.now,
                                     posts=self.plan()["fr_posts"])
            old_proof = readiness.snapshot_proof(root=root, now=self.now)
            frozen["planner_readiness"] = old_proof
            queue.attach_queue(state, frozen)
            path, proof_path = root / "state.json", root / "proof.json"
            queue.save_state(path, state)
            before = path.read_bytes()
            (root / "news_wire.json").write_text('{"generated_at": "2026-10-07T06:00:00Z"}', encoding="utf-8")
            proof_path.write_text(json.dumps(readiness.snapshot_proof(root=root, now=self.now)), encoding="utf-8")
            args = queue.build_parser().parse_args(["build", "--state", str(path),
                "--state-output", str(path), "--now", self.now.isoformat(), "--readiness-proof", str(proof_path)])
            with patch.object(queue, "ROOT", root), patch.object(queue, "build_core_plan") as build, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(args.func(args), 0)
                self.assertEqual(before, path.read_bytes())
                build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
