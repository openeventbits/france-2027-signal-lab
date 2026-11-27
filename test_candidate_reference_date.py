"""Snapshot dates are explicit inputs, independent of verification wall time."""
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import build_candidate_reference as reference

ROOT = Path(__file__).resolve().parent
DAY = date(2026, 11, 9)


class Clock(datetime):
    instant = datetime.fromisoformat("2026-11-09T22:55:00+00:00")

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz)


class CandidateSnapshotDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = reference.load_sources(ROOT)
        # Validate this immutable source fixture once; event fixture mutations
        # below exercise projection rules separately from source contracts.
        reference.validate_sources(cls.sources, ROOT)
        cls.projection = reference.build_projection(
            cls.sources, ROOT, event_reference_date=DAY, _sources_validated=True,
        )
        cls.html = {
            lang: reference.render_html(cls.projection, reference.derive_hud_metrics(cls.sources),
                                        lang=lang, root=ROOT)
            for lang in ("fr", "en")
        }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        self.data = self.output / "data.json"
        self.fr = self.output / "fr.html"
        self.en = self.output / "en.html"
        self.data.write_bytes(reference.serialize_projection(self.projection))
        self.fr.write_bytes(self.html["fr"])
        self.en.write_bytes(self.html["en"])

    def check(self, *, sources=None, extra=()):
        argv = ["builder", "--root", str(ROOT), "--output", str(self.data),
                "--html-output", str(self.fr), "--html-output-en", str(self.en),
                "--check", *extra]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(reference, "load_sources", return_value=sources or self.sources), \
             mock.patch.object(reference, "validate_sources"), mock.patch.dict(os.environ), redirect_stdout(io.StringIO()):
            os.environ.pop("CANDIDATE_EVENT_REFERENCE_DATE", None)
            return reference.main()

    def test_identical_snapshot_checks_before_and_after_paris_midnight(self):
        before = {p: p.read_bytes() for p in (self.data, self.fr, self.en)}
        for instant in ("2026-11-09T22:55:00+00:00", "2026-11-09T23:07:00+00:00"):
            Clock.instant = datetime.fromisoformat(instant)
            with mock.patch.object(reference, "datetime", Clock), \
                 mock.patch.object(reference, "_event_reference_date", side_effect=AssertionError("clock consulted")):
                self.assertEqual(self.check(), 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def event_sources(self):
        sources = dict(self.sources)
        events = copy.deepcopy(self.sources["campaign_events"])
        original = events["campaign_events"][0]
        rows = []
        for identifier, scheduled, status in (
            ("past", "2026-11-08", "scheduled"),
            ("today", "2026-11-09", "scheduled"),
            ("future", "2026-11-10", "scheduled"),
            ("cancelled-past", "2026-11-08", "cancelled"),
            ("cancelled-today", "2026-11-09", "cancelled"),
            ("cancelled-future", "2026-11-10", "cancelled"),
        ):
            row = copy.deepcopy(original)
            row.update(event_id=identifier, scheduled_start=scheduled,
                       status=status, candidate_ids=[reference.CANDIDATE_ID])
            rows.append(row)
        events.update(campaign_events=rows, institutional_milestones=[], event_watch=[])
        sources["campaign_events"] = events
        return sources

    def projection_at(self, sources, day):
        with mock.patch.object(reference, "_event_reference_date", side_effect=AssertionError("clock consulted")):
            return reference.build_projection(sources, ROOT, event_reference_date=day,
                                              _sources_validated=True)

    def test_new_next_day_snapshot_reallocates_same_day_events(self):
        sources = self.event_sources()
        today = self.projection_at(sources, DAY)["events"]
        tomorrow = self.projection_at(sources, date(2026, 11, 10))["events"]
        ids = lambda rows: {row["event_id"] for row in rows}
        self.assertEqual(ids(today["upcoming"]), {"today", "future"})
        self.assertEqual(ids(today["recent"]), {"past", "cancelled-past"})
        self.assertEqual(ids(tomorrow["upcoming"]), {"future"})
        self.assertEqual(ids(tomorrow["recent"]),
                         {"past", "today", "cancelled-past", "cancelled-today"})
        self.assertEqual(tomorrow["reference_date"], "2026-11-10")

    def test_same_explicit_date_is_deterministic_across_clocks(self):
        sources = self.event_sources()
        outputs = []
        for instant in ("2026-11-09T22:55:00+00:00", "2026-11-10T23:07:00+00:00"):
            Clock.instant = datetime.fromisoformat(instant)
            with mock.patch.object(reference, "datetime", Clock):
                outputs.append(reference.serialize_projection(self.projection_at(sources, DAY)))
        self.assertEqual(*outputs)

    def test_stale_source_evidence_is_still_rejected(self):
        sources = copy.deepcopy(self.sources)
        sources["recent_changes"]["generated_at"] = "2026-11-10T12:00:00Z"
        with self.assertRaisesRegex(SystemExit, "stale candidate reference projection"):
            self.check(sources=sources)

    def test_corruption_is_still_rejected(self):
        self.data.write_bytes(self.data.read_bytes() + b" ")
        with self.assertRaisesRegex(SystemExit, "stale candidate reference projection"):
            self.check()

    def test_explicit_date_disagreement_is_rejected(self):
        with self.assertRaisesRegex(reference.CandidateReferenceError, "date mismatch"):
            self.check(extra=("--event-reference-date", "2026-11-10"))

    def test_missing_or_invalid_date_has_no_clock_fallback(self):
        for value in (None, "", "2026-11-31", "20261109", "2026-W46-1"):
            payload = copy.deepcopy(self.projection)
            payload["events"]["reference_date"] = value
            self.data.write_text(json.dumps(payload), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(reference.CandidateReferenceError), \
                 mock.patch.object(reference, "_event_reference_date", side_effect=AssertionError):
                self.check()

    def test_active_and_archive_metadata_must_be_unanimous(self):
        lifecycle = reference.project_candidate_page_lifecycle(self.sources["candidate_candidacy_status"], ROOT)
        self.assertTrue(lifecycle["retained_archived_ids"])
        self.assertEqual(len(lifecycle["active_ids"]), len(reference.active_candidate_records(
            self.sources["candidate_candidacy_status"])))
        for candidate_id in lifecycle["published_ids"]:
            path = self.output / "candidates" / candidate_id / "data.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"events": {"reference_date": DAY.isoformat()}}))
        with mock.patch.object(reference, "_event_reference_date", side_effect=AssertionError):
            self.assertEqual(reference.snapshot_event_reference_date(self.output, lifecycle["published_ids"]), DAY)
        archive = self.output / "candidates" / lifecycle["retained_archived_ids"][0] / "data.json"
        archive.write_text('{"events":{"reference_date":"2026-11-10"}}')
        with self.assertRaisesRegex(reference.CandidateReferenceError, "unanimous"):
            reference.snapshot_event_reference_date(self.output, lifecycle["published_ids"])
        archive.unlink()
        with self.assertRaisesRegex(reference.CandidateReferenceError, "invalid candidate snapshot"):
            reference.snapshot_event_reference_date(self.output, lifecycle["published_ids"])

    def test_paris_clock_handles_midnight_and_both_dst_transitions(self):
        for instant, expected in (
            ("2026-03-28T22:55:00+00:00", "2026-03-28"),
            ("2026-03-28T23:07:00+00:00", "2026-03-29"),
            ("2026-03-29T00:59:00+00:00", "2026-03-29"),
            ("2026-03-29T01:01:00+00:00", "2026-03-29"),
            ("2026-10-24T21:55:00+00:00", "2026-10-24"),
            ("2026-10-24T22:07:00+00:00", "2026-10-25"),
            ("2026-10-25T00:59:00+00:00", "2026-10-25"),
            ("2026-10-25T01:01:00+00:00", "2026-10-25"),
        ):
            Clock.instant = datetime.fromisoformat(instant)
            with self.subTest(instant=instant), mock.patch.object(reference, "datetime", Clock), mock.patch.dict(os.environ):
                os.environ.pop("CANDIDATE_EVENT_REFERENCE_DATE", None)
                self.assertEqual(reference._event_reference_date().isoformat(), expected)
                self.assertEqual(self.projection_at(self.sources, date.fromisoformat(expected))["events"]["reference_date"], expected)

    def test_transaction_environment_pins_direct_builder_calls(self):
        with mock.patch.dict(os.environ, {"CANDIDATE_EVENT_REFERENCE_DATE": DAY.isoformat()}), \
             mock.patch.object(reference, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = AssertionError("clock consulted")
            self.assertEqual(reference._event_reference_date(), DAY)
            projection = reference.build_projection(self.sources, ROOT, _sources_validated=True)
            self.assertEqual(projection["events"]["reference_date"], DAY.isoformat())
            argv = ["builder", "--root", str(ROOT), "--output", str(self.data),
                    "--html-output", str(self.fr), "--html-output-en", str(self.en), "--check"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(reference, "validate_sources"), redirect_stdout(io.StringIO()):
                self.assertEqual(reference.main(), 0)
            os.environ["CANDIDATE_EVENT_REFERENCE_DATE"] = "2026-11-10"
            with mock.patch.object(sys, "argv", argv), self.assertRaisesRegex(reference.CandidateReferenceError, "date mismatch"):
                reference.main()
        with mock.patch.dict(os.environ, {"CANDIDATE_EVENT_REFERENCE_DATE": ""}), \
             self.assertRaises(reference.CandidateReferenceError):
            reference._event_reference_date()

    def test_candidate_transaction_propagates_date_through_reconciliation(self):
        workflow = (ROOT / ".github/workflows/publish-candidate-family.yml").read_text(encoding="utf-8")
        self.assertIn('event_reference_date=$event_reference_date', workflow)
        self.assertIn('export CANDIDATE_EVENT_REFERENCE_DATE="$event_reference_date"', workflow)
        self.assertIn("CANDIDATE_EVENT_REFERENCE_DATE: ${{ steps.build.outputs.event_reference_date }}", workflow)
        self.assertEqual(workflow.count('python -B build_candidate_reference.py --all-active\n'), 2)
        self.assertEqual(workflow.count('python -B build_candidate_reference.py --all-active --check\n'), 2)


class CandidateFamilySnapshotDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = reference.load_sources(ROOT)
        cls.day = reference.snapshot_event_reference_date(
            ROOT, reference.project_candidate_page_lifecycle(
                cls.sources["candidate_candidacy_status"], ROOT,
            )["published_ids"],
        )
        with mock.patch.object(reference, "_event_reference_date", side_effect=AssertionError("clock consulted")):
            cls.artifacts = reference.build_all_active_artifacts(
                cls.sources, ROOT, event_reference_date=cls.day,
            )

    def test_full_family_generation_matches_existing_production_bytes(self):
        for path, content in self.artifacts.items():
            with self.subTest(path=path):
                self.assertTrue(reference._newline_equivalent((ROOT / path).read_bytes(), content))

    def test_full_family_repeated_generation_and_single_clock_capture(self):
        with mock.patch.object(reference, "_event_reference_date", side_effect=[self.day, date(2026, 11, 11)]) as clock:
            repeated = reference.build_all_active_artifacts(self.sources, ROOT)
        clock.assert_called_once_with()
        self.assertEqual(self.artifacts, repeated)
        dates = {json.loads(content)["events"]["reference_date"]
                 for path, content in repeated.items() if path.name == "data.json"}
        self.assertEqual(dates, {self.day.isoformat()})

    def test_agenda_reconciliation_then_issue_verify_same_immutable_snapshot(self):
        from test_publication_orchestration_contract import inline_python, read_workflow

        agenda = read_workflow("publish-agenda-family.yml")
        reconciliation = agenda.split("# BEGIN reconciliation readiness", 1)[1].split(
            "# END reconciliation readiness", 1)[0]
        code = reconciliation.split("<<'PY'\n", 1)[1].split("\n          PY", 1)[0]
        reconciliation_code = "\n".join(line[10:] for line in code.splitlines())
        stages = (
            (inline_python(agenda, "Check candidate publication readiness"), "2026-11-10T22:55:00+00:00"),
            (reconciliation_code, "2026-11-10T23:07:00+00:00"),
            (inline_python(read_workflow("publish-issue-family.yml"), "Check candidate publication readiness"),
             "2026-11-10T23:07:00+00:00"),
        )
        real_run = subprocess.run
        checks = []

        def regenerated(sources, root, *, site_root, event_reference_date):
            # Generation above used the real builder. Cache only this expensive
            # recomputation while exercising each real CLI metadata/byte check.
            self.assertEqual(sources, self.sources)
            self.assertEqual(root, ROOT)
            self.assertEqual(site_root, ROOT)
            self.assertEqual(event_reference_date, self.day)
            return self.artifacts

        def checked(arguments, **kwargs):
            if arguments[2] != "build_candidate_reference.py":
                return real_run(arguments, **kwargs)
            checks.append(arguments)
            with mock.patch.object(sys, "argv", arguments[2:]), redirect_stdout(io.StringIO()):
                result = reference.main()
            return subprocess.CompletedProcess(arguments, result, "", "")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            summary = Path(directory) / "summary"
            for code, instant in stages:
                Clock.instant = datetime.fromisoformat(instant)
                output.write_text("")
                with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}), \
                     mock.patch.object(reference, "datetime", Clock), \
                     mock.patch.object(reference, "_event_reference_date", side_effect=AssertionError("clock consulted")), \
                     mock.patch.object(reference, "build_all_active_artifacts", side_effect=regenerated), \
                     mock.patch("subprocess.run", side_effect=checked), redirect_stdout(io.StringIO()):
                    exec(compile(code, "workflow-readiness", "exec"), {})
                self.assertEqual(output.read_text(), "ready=true\n")
        self.assertEqual(len(checks), 3)


if __name__ == "__main__":
    unittest.main()
