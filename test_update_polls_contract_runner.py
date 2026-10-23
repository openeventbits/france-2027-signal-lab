"""Bounded regression checks for the test-only Update polls entry point."""

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run_update_polls_contract_tests as runner
from fetch_polls import validate_second_round_event
from poll_contract import make_event_id


NEW_RUNOFF_IDS = {
    "a8de0876a090ae834c855ab01609e187699517db8c2a0408625e978021f7fa4e",
    "958f109b9119fd764d32cf7eb16cc373f29954dec1f6f0a1e2f186ddc7ad219e",
}


class ContractRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("polls.json", "second_round_polls.json",
                     "fr27_commission_barometer_review.json",
                     "fr27_commission_10205_composite_review.json",
                     "commission_notice_registry.json"):
            shutil.copyfile(runner.ROOT / name, self.root / name)

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def invoke(self, *, fail_assertion=False, expected_runoffs=None):
        # Use the real CLI and original setups/assertions in a fresh process.
        # Only its current checkout paths point to our disposable input directory.
        script = '''
import functools, json, sys, unittest
from contextlib import contextmanager
from pathlib import Path
import run_update_polls_contract_tests as r
import test_commission_notice_coverage as a
import test_commission_10205_composite as b
from fetch_polls import validate_second_round_event
root = Path(sys.argv[1])
a.__file__ = str(root / "test_commission_notice_coverage.py")
b.ROOT = root
r.historical_context = functools.partial(r.historical_context, root=root)
if (root / "manifest.json").exists():
    r.historical_inputs = functools.partial(r.historical_inputs, manifest_path=root / "manifest.json")
expected = int(sys.argv[2])
expected_first = len(r.read(root / "polls.json"))
required_ids = set(sys.argv[4:])
class CurrentProbe(b.CompositeRnTests):
    def test_current_data(self):
        self.assertEqual(len(self.first), expected_first)
        self.assertEqual(len(self.second), expected)
        self.assertTrue(required_ids <= {e["event_id"] for e in self.second})
        for event in self.second:
            validate_second_round_event(event)
if sys.argv[3] == "fail":
    original_context = r.historical_context
    @contextmanager
    def failing_context():
        with original_context():
            # Corrupt the disposable, already-authenticated copy so the real,
            # unchanged numeric-table assertion must report a failure.
            path = Path(a.__file__).parent / "polls.json"
            data = r.read(path)
            review = r.read(root / "fr27_commission_barometer_review.json")
            event_id = review["notices"][0]["configurations"][0]["published_event_id"]
            changed = next(e for e in data if e["event_id"] == event_id)
            changed["candidates"][0]["score"] += 0.5
            changed["candidates"][1]["score"] -= 0.5
            path.write_text(json.dumps(data), encoding="utf-8")
            yield
    r.historical_context = failing_context
sys.argv = [sys.argv[0], "-v", "__main__.CurrentProbe.test_current_data", *sorted(r.HISTORICAL_TESTS)]
raise SystemExit(r.main())
'''
        if expected_runoffs is None:
            expected_runoffs = len(runner.read(runner.ROOT / "second_round_polls.json")["events"])
        return subprocess.run(
            [sys.executable, "-B", "-c", script, str(self.root),
             str(expected_runoffs), "fail" if fail_assertion else "pass",
             *sorted(NEW_RUNOFF_IDS)],
            cwd=runner.ROOT, capture_output=True, text=True, timeout=90,
        )

    def test_current_corpus_and_only_two_historical_tests(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 current-data tests + 2 authenticated historical tests", result.stdout)
        self.assertIn("Ran 3 tests", result.stderr)
        self.assertNotIn("skipped", result.stderr)

    def test_missing_source_file_fails_process(self):
        (self.root / "second_round_polls.json").unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FileNotFoundError", result.stderr)

    def test_missing_historical_object_fails_process(self):
        source = runner.read(self.root / "second_round_polls.json")
        event_id = runner.read(runner.MANIFEST)["corpora"]["second_round_polls.json"]["event_ids"][0]
        source["events"] = [event for event in source["events"] if event["event_id"] != event_id]
        self.write("second_round_polls.json", source)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing historical objects", result.stderr)

    def test_modified_historical_source_fails_process(self):
        source = runner.read(self.root / "polls.json")
        source[0]["sample_size"] += 1
        self.write("polls.json", source)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("historical objects changed", result.stderr)

    def test_duplicate_object_fails(self):
        source = runner.read(self.root / "polls.json")
        source.append(copy.deepcopy(source[0]))
        self.write("polls.json", source)
        with self.assertRaisesRegex(ValueError, "duplicate production event ID"):
            runner.historical_inputs(self.root)

    def test_fabricated_replacement_object_fails(self):
        source = runner.read(self.root / "polls.json")
        source[0]["event_id"] = "f" * 64
        self.write("polls.json", source)
        with self.assertRaisesRegex(ValueError, "missing historical objects"):
            runner.historical_inputs(self.root)

    def test_unexpected_historical_selection_fails(self):
        manifest = runner.read(runner.MANIFEST)
        manifest["corpora"]["second_round_polls.json"]["event_ids"].append(sorted(NEW_RUNOFF_IDS)[0])
        self.write("manifest.json", manifest)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("historical ID manifest changed", result.stderr)

    def test_changed_review_fails(self):
        review = runner.read(self.root / "fr27_commission_barometer_review.json")
        review["review_id"] = "unreviewed"
        self.write("fr27_commission_barometer_review.json", review)
        with self.assertRaisesRegex(ValueError, "historical review changed"):
            runner.historical_inputs(self.root)

    def test_additional_valid_current_runoff_keeps_historical_tests_valid(self):
        source = runner.read(self.root / "second_round_polls.json")
        event = copy.deepcopy(next(e for e in source["events"] if e["event_id"] in NEW_RUNOFF_IDS))
        event["fieldwork_start"], event["fieldwork_end"] = "2026-10-22", "2026-10-23"
        event["event_id"] = make_event_id(
            event["pollster"], event["fieldwork_start"], event["fieldwork_end"],
            event["hypothesis"], event["source_url"], round_name="second_round",
        )
        validate_second_round_event(event)
        source["events"].append(event)
        self.write("second_round_polls.json", source)
        result = self.invoke(expected_runoffs=len(source["events"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 3 tests", result.stderr)

    def test_historical_assertion_failure_fails_process(self):
        result = self.invoke(fail_assertion=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("self.assertEqual(published, expected)", result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)

    def test_missing_selected_method_and_duplicate_selection_fail_process(self):
        names = sorted(runner.HISTORICAL_TESTS)
        for selection in (names[:1], names + names[:1]):
            with self.subTest(selection=selection):
                result = subprocess.run(
                    [sys.executable, "-B", str(runner.ROOT / "run_update_polls_contract_tests.py"), *selection],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("select each historical method exactly once", result.stderr)


if __name__ == "__main__":
    unittest.main()
