"""Test-only entry point: two immutable reviews use their authenticated 439 IDs.

The manifest was checked against both documented review bases, cfd9cee36 and
af7fbbc68, reversing only the three exact 10205 successors in the latter review.
All 439 objects also match 1262d31d (run 419) and the hotfix's production base.
No Git history, network access, or additional dependency is needed at runtime.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "test_update_polls_historical_ids.json"
MANIFEST_SHA256 = "fdf8509d5b3bd1361ac035d60e48a4113e67f3f5061a082efe9cb00a114d3be3"
HISTORICAL_TESTS = frozenset({
    "test_commission_notice_coverage.ElectionBarometerCoverageTests."
    "test_original_tables_match_all_numeric_values_and_record_the_literal_conflict",
    "test_commission_10205_composite.CompositeRnTests."
    "test_only_three_ids_change_and_other_436_objects_identical",
})


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def historical_inputs(root=ROOT, manifest_path=MANIFEST):
    """Select by frozen IDs; authenticate every field, type, and review decision.

    Current additions are intentionally allowed. Missing historical IDs, changed
    objects, duplicate IDs (including additions), and altered manifests fail.
    Sorting by ID makes the pins independent of production array ordering.
    """
    manifest = read(manifest_path)
    if digest(manifest) != MANIFEST_SHA256:
        raise ValueError("historical ID manifest changed")
    for name, expected in manifest["review_evidence"].items():
        if digest(read(root / name)) != expected:
            raise ValueError(f"historical review changed: {name}")
    selected = {}
    for name, count in (("polls.json", 337), ("second_round_polls.json", 102)):
        source = read(root / name)
        events = source if name == "polls.json" else source["events"]
        by_id = {event["event_id"]: event for event in events}
        if len(by_id) != len(events):
            raise ValueError(f"duplicate production event ID: {name}")
        pin = manifest["corpora"][name]
        ids = pin["event_ids"]
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError(f"invalid historical ID selection: {name}")
        missing = set(ids) - by_id.keys()
        if missing:
            raise ValueError(f"missing historical objects in {name}: {sorted(missing)}")
        historical = [by_id[event_id] for event_id in ids]
        if digest(historical) != pin["collection_sha256"]:
            raise ValueError(f"historical objects changed: {name}")
        selected[name] = historical if name == "polls.json" else {
            **source, "events": historical,
        }
    return selected


@contextmanager
def historical_context(root=ROOT):
    """Redirect only the two test modules' setup paths to disposable inputs."""
    import test_commission_notice_coverage as barometer
    import test_commission_10205_composite as composite

    inputs = historical_inputs(root)
    with tempfile.TemporaryDirectory(prefix="fr27-historical-tests-") as directory:
        temporary = Path(directory)
        for name, value in inputs.items():
            (temporary / name).write_text(json.dumps(value), encoding="utf-8")
        # Their unchanged setups also read these current, protected sources.
        for name in ("fr27_commission_barometer_review.json", "commission_notice_registry.json"):
            (temporary / name).write_bytes((root / name).read_bytes())
        with ExitStack() as stack:
            stack.enter_context(patch.object(barometer, "__file__", str(temporary / "test_commission_notice_coverage.py")))
            stack.enter_context(patch.object(composite, "ROOT", temporary))
            yield


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


class HistoricalSuite(unittest.TestSuite):
    def run(self, result, debug=False):
        with historical_context():
            return super().run(result, debug)


class ContractProgram(unittest.TestProgram):
    def createTests(self, from_discovery=False, Loader=None):
        super().createTests(from_discovery, Loader)
        if self.testLoader.errors:
            raise ValueError("test loading failed:\n" + "\n".join(self.testLoader.errors))
        tests = list(cases(self.test))
        ids = [test.id() for test in tests]
        if len(ids) != len(set(ids)) or not HISTORICAL_TESTS <= set(ids):
            raise ValueError("select each historical method exactly once; no duplicate tests")
        current = [test for test in tests if test.id() not in HISTORICAL_TESTS]
        historical = [test for test in tests if test.id() in HISTORICAL_TESTS]
        print(f"Production contract: {len(current)} current-data tests + "
              f"{len(historical)} authenticated historical tests", flush=True)
        self.test = unittest.TestSuite([
            unittest.TestSuite(current), HistoricalSuite(historical),
        ])


def main():
    program = ContractProgram(module=None, exit=False)
    # A skip must not silently reduce the workflow's selected test coverage.
    return 0 if program.result.wasSuccessful() and not program.result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
