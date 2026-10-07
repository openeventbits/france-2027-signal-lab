"""Source contracts and executable promotion/no-op tests for current projections."""
import ast
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from live_projection_contract import (
    build_agenda_live_projection, build_issue_live_projection, validate_live_projection,
)
from live_projection_io import serialize, atomic_write
from agenda_page_contract import CANONICAL_AGENDA_IDS
from issue_page_contract import CANONICAL_ISSUE_IDS

ROOT = Path(__file__).resolve().parent
BASH = shutil.which("bash")
if os.name == "nt":
    bash_path = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    BASH = str(bash_path) if bash_path.is_file() else None
BUILDERS = (("agenda", build_agenda_live_projection), ("issues", build_issue_live_projection))


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class LiveProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = load("news_wire.json")

    def test_deterministic_source_identity_canonical_membership_and_no_mutation(self):
        before = copy.deepcopy(self.news)
        for family, builder in BUILDERS:
            with self.subTest(family=family):
                projection = builder(self.news)
                self.assertEqual(serialize(projection), serialize(builder(self.news)))
                self.assertEqual(projection["source_snapshot"], self.news["generated_at"])
                ids = CANONICAL_AGENDA_IDS if family == "agenda" else CANONICAL_ISSUE_IDS
                self.assertEqual([t["id"] for t in projection["topics"]], list(ids))
                self.assertNotIn("candidate_priorities", projection)
                self.assertLessEqual(len(projection["supporting_evidence"]), 6)
                published = {item["id"] for item in self.news["relevant_news"]}
                for evidence in projection["supporting_evidence"]:
                    self.assertIn(evidence["id"], published)
                    self.assertTrue(set(evidence["topic_ids"]).issubset(ids))
                validate_live_projection(projection, self.news, family)
                self.assertEqual(self.news, before)

    def test_malformed_structures_counts_and_ids_fail_closed(self):
        for family, builder in BUILDERS:
            field = "campaign_agenda" if family == "agenda" else "policy_agenda"
            for kind in ("missing", "list", "duplicate", "unknown", "count", "daily", "denominator"):
                with self.subTest(family=family, kind=kind):
                    news = copy.deepcopy(self.news)
                    if kind == "missing": del news[field]
                    elif kind == "list": news[field] = []
                    elif kind == "duplicate": news[field]["topics"].append(copy.deepcopy(news[field]["topics"][0]))
                    elif kind == "unknown": news[field]["topics"][0]["id"] = "candidate_priorities"
                    elif kind == "count": news[field]["classified_item_count"] += 1
                    elif kind == "daily": news[field]["evolution"]["topics"][0]["daily_activity"][0]["source_day_count"] = -1
                    elif family == "issues": news[field]["evolution"]["accepted_daily_activity"][0]["source_day_count"] += 1
                    else: news[field]["evolution"]["topics"][0]["source_day_count"] += 1
                    with self.assertRaises((ValueError, RuntimeError, TypeError, KeyError)):
                        builder(news)

    def test_source_timestamp_and_rolling_day_are_required(self):
        for stamp in (None, "garbage", "2026-01-01T12:00:00", "2025-01-01T12:00:00Z"):
            for family, builder in BUILDERS:
                with self.subTest(family=family, stamp=stamp):
                    news = copy.deepcopy(self.news); news["generated_at"] = stamp
                    with self.assertRaises(ValueError): builder(news)

    def test_counts_reconcile_and_metric_semantics_are_preserved(self):
        for family, builder in BUILDERS:
            p = builder(self.news)
            self.assertEqual(p["counts"]["classified_item_count"] + p["counts"]["unclassified_item_count"], p["counts"]["input_item_count"])
            self.assertEqual(sum(t["item_count"] for t in p["topics"]),
                             p["counts"]["rolling_assignment_count"])
            for t in p["topics"]:
                self.assertEqual(t["item_count"], sum(d["item_count"] for d in t["daily_activity"]))
                self.assertEqual(t["source_day_count"], sum(d["source_day_count"] for d in t["daily_activity"]))
            self.assertEqual(p["denominator"]["multilabel"], family == "issues")
            if family == "agenda":
                self.assertEqual(p["denominator"]["current"], sum(t["source_day_count"] for t in p["topics"]))
                self.assertAlmostEqual(sum(t["latest_share"] for t in p["topics"]), 1 if p["denominator"]["latest"] else 0)
            else:
                self.assertEqual(p["denominator"]["current"], sum(d["source_day_count"] for d in p["accepted_daily_activity"]))
                self.assertGreaterEqual(p["counts"]["label_assignment_count"], p["counts"]["classified_item_count"])
                self.assertEqual(p["denominator"]["corpus_item_count"], len(self.news["relevant_news"]))
                for t in p["topics"]:
                    self.assertEqual(t["current_share"], t["source_day_count"] / p["denominator"]["current"] if p["denominator"]["current"] else 0)

    def test_multilabel_shares_can_sum_above_one(self):
        from datetime import datetime, timezone
        from fetch_news_wire import build_campaign_agenda, build_policy_agenda
        from test_policy_agenda import PolicyAgendaTests
        # Create a controlled published snapshot before invoking the projection.
        items = [PolicyAgendaTests.item("overlap", "Présidentielle 2027 : déficit public, retraites et pouvoir d'achat")]
        anchor = datetime(2026, 8, 20, 14, tzinfo=timezone.utc)
        news = {
            "generated_at": anchor.isoformat().replace("+00:00", "Z"), "relevant_news": items,
            "campaign_agenda": build_campaign_agenda(items, window_days=30, generated_at=anchor),
            "policy_agenda": build_policy_agenda(items, window_days=30, generated_at=anchor),
        }
        with patch("fetch_news_wire.classify_policy_agenda", side_effect=AssertionError("projection reclassified")):
            p = build_issue_live_projection(news)
        self.assertEqual([t["id"] for t in p["topics"]], list(CANONICAL_ISSUE_IDS))
        self.assertEqual(sum(t["item_count"] == 0 for t in p["topics"]), 6)
        self.assertEqual(p["counts"]["classified_item_count"], 1)
        self.assertEqual(p["counts"]["label_assignment_count"], 2)
        self.assertGreater(sum(t["latest_share"] for t in p["topics"]), 1)
        self.assertGreater(sum(t["current_share"] for t in p["topics"]), 1)

    def test_source_mismatch_and_projection_tampering_fail(self):
        for family, builder in BUILDERS:
            p = builder(self.news)
            p["source_snapshot"] = "2000-01-01T00:00:00Z"
            with self.assertRaises(ValueError): validate_live_projection(p, self.news, family)
            p = builder(self.news); p["topics"][0]["item_count"] += 1
            with self.assertRaises(ValueError): validate_live_projection(p, self.news, family)

    def test_no_network_clock_classification_or_git_reconstruction(self):
        with patch("fetch_news_wire.classify_campaign_agenda", side_effect=AssertionError("reclassification")), \
             patch("fetch_news_wire.classify_policy_agenda", side_effect=AssertionError("reclassification")), \
             patch("subprocess.run", side_effect=AssertionError("Git/network")):
            for _, builder in BUILDERS: builder(self.news)

    def test_explicit_cli_paths_check_and_failed_build_leave_output_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); news = root / "news.json"; news.write_bytes(serialize(self.news))
            for name in ("agenda", "issue"):
                output = root / (name + ".json")
                args = [shutil.which("python") or "python", "-B", str(ROOT / f"build_{name}_live_projection.py"), "--news", str(news), "--output", str(output)]
                self.assertEqual(subprocess.run(args, capture_output=True).returncode, 0)
                original = output.read_bytes()
                self.assertEqual(subprocess.run(args + ["--check"], capture_output=True).returncode, 0)
                output.write_bytes(b"stale")
                self.assertNotEqual(subprocess.run(args + ["--check"], capture_output=True).returncode, 0)
                output.write_bytes(original)
            before = news.read_bytes()
            same_path_args = [shutil.which("python") or "python", "-B", str(ROOT / "build_agenda_live_projection.py"), "--news", str(news), "--output", str(news)]
            self.assertNotEqual(subprocess.run(same_path_args, capture_output=True).returncode, 0)
            self.assertEqual(news.read_bytes(), before)
            news.write_text('{"generated_at":"invalid"}', encoding="utf-8")
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), original)

    def test_atomic_write_keeps_existing_output_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.json"; path.write_bytes(b"fallback")
            with patch("live_projection_io.os.replace", side_effect=OSError("replacement failed")):
                with self.assertRaises(OSError): atomic_write(path, b"new")
            self.assertEqual(path.read_bytes(), b"fallback")
            self.assertEqual(list(Path(directory).iterdir()), [path])


class LiveWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/update-news-wire.yml").read_text(encoding="utf-8")
        block = cls.workflow.split("          python - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
        cls.promotion = "\n".join(line[10:] if line.startswith("          ") else line for line in block.splitlines())

    def test_workflow_builds_checks_promotes_stages_reconciles_and_serializes(self):
        ast.parse(self.promotion)
        before = self.workflow.split("- name: Validate and promote generated data")[0]
        for name, tmp, path in (("agenda", "agenda_live", "agenda/live.json"), ("issue", "issues_live", "enjeux/live.json")):
            self.assertIn(f"build_{name}_live_projection.py --news /tmp/news_wire.json --output /tmp/{tmp}.json", before)
            self.assertIn(f'Path("/tmp/{tmp}.json")', self.promotion)
            self.assertLess(self.promotion.index("validate_live_projection("), self.promotion.index("atomic_write("))
            commit = self.workflow.split("- name: Commit changed rolling news data", 1)[1]
            self.assertIn(path, commit.split("git commit -m", 1)[0])
            post = commit.split('git rebase "origin/$target_branch"', 1)[1]
            self.assertGreaterEqual(post.count(f"python -B build_{name}_live_projection.py\n"), 2)
            self.assertGreaterEqual(post.count(f"python -B build_{name}_live_projection.py --check"), 2)
            for scope in post.split("git diff")[1:]: self.assertIn(path, scope.split("then", 1)[0] if "then" in scope else scope)
        for marker in ("group: production-data-update", "cancel-in-progress: false", "queue: max"):
            self.assertIn(marker, self.workflow)
        self.assertNotIn("build_agenda_pages.py", self.workflow)
        self.assertNotIn("build_issue_pages.py", self.workflow)

    def run_promotion(self, *, semantic_change=False, inventory_bookkeeping=False, invalid=False, missing=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); temporary = root / "temporary"; temporary.mkdir()
            files = ("news_inventory.json", "news_wire.json", "news_corpus_ledger.json", "recent_changes.json", "source_health.json", "candidate_visibility_history.json", "candidate_agenda_history.json")
            for name in files:
                shutil.copyfile(ROOT / name, root / name); shutil.copyfile(ROOT / name, temporary / name)
            for name in ("news_sources.json", "candidate_candidacy_status.json"):
                shutil.copyfile(ROOT / name, root / name)
            current = load("news_wire.json")
            wire = copy.deepcopy(current)
            # A fetch-only time change must not cause projection churn.
            from datetime import datetime, timedelta
            stamp = datetime.fromisoformat(wire["generated_at"].replace("Z", "+00:00")) + timedelta(seconds=1)
            wire["generated_at"] = stamp.isoformat().replace("+00:00", "Z")
            if semantic_change:
                source = next(s for s in wire["sources"] if s["status"] == "ok")
                source["status"] = "error"
                wire["counts"]["successful_sources"] -= 1
                wire["feed_coverage"]["feeds_successful_this_run"] -= 1
            (temporary / "news_wire.json").write_bytes(serialize(wire))
            if inventory_bookkeeping:
                inventory = load("news_inventory.json")
                inventory["generated_at"] = wire["generated_at"]
                inventory["items"][0]["last_seen_at"] = wire["generated_at"]
                (temporary / "news_inventory.json").write_bytes(serialize(inventory))
            original = {}
            for family, builder in BUILDERS:
                path = root / ("agenda/live.json" if family == "agenda" else "enjeux/live.json")
                atomic_write(path, serialize(builder(current))); original[family] = path.read_bytes()
                payload = builder(wire)
                if invalid and family == "issues": payload["source_snapshot"] = current["generated_at"]
                (temporary / ("agenda_live.json" if family == "agenda" else "issues_live.json")).write_bytes(serialize(payload))
            if missing: (root / "agenda/live.json").unlink()
            code = self.promotion.replace("/tmp/", temporary.as_posix() + "/")
            env = {**os.environ, "PYTHONPATH": str(ROOT), "GITHUB_OUTPUT": str(root / "outputs")}
            result = subprocess.run([shutil.which("python") or "python", "-B", "-c", code], cwd=root, env=env, capture_output=True, text=True)
            if invalid:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(load("news_wire.json"), json.loads((root / "news_wire.json").read_text(encoding="utf-8")))
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                committed = json.loads((root / "news_wire.json").read_text(encoding="utf-8"))
                self.assertEqual(committed["generated_at"], wire["generated_at"] if semantic_change else current["generated_at"])
                if not semantic_change:
                    self.assertEqual((root / "news_wire.json").read_bytes(), (ROOT / "news_wire.json").read_bytes())
                for family, _ in BUILDERS:
                    path = root / ("agenda/live.json" if family == "agenda" else "enjeux/live.json")
                    projection = json.loads(path.read_text(encoding="utf-8"))
                    validate_live_projection(projection, committed, family)
                    if not semantic_change: self.assertEqual(path.read_bytes(), original[family])
                self.assertIn("changed=" + str(semantic_change or inventory_bookkeeping or missing).lower(), (root / "outputs").read_text())

    def test_executed_promotion_matches_promoted_source(self): self.run_promotion(semantic_change=True)
    def test_executed_semantic_noop_has_zero_projection_churn(self): self.run_promotion()
    def test_inventory_bookkeeping_preserves_public_snapshot(self): self.run_promotion(inventory_bookkeeping=True)
    def test_inventory_bookkeeping_and_stale_repair_preserve_public_snapshot(self): self.run_promotion(inventory_bookkeeping=True, missing=True)
    def test_executed_stale_artifact_repair_uses_committed_source(self): self.run_promotion(missing=True)
    def test_invalid_projection_prevents_source_promotion(self): self.run_promotion(invalid=True)

    def test_family_fanout_daily_refresh_candidate_and_global_queue(self):
        for family, cron in (("agenda", "53 11 * * *"), ("issue", "17 11 * * *")):
            text = (ROOT / f".github/workflows/publish-{family}-family.yml").read_text(encoding="utf-8")
            upstream = text.split("workflow_run:", 1)[1].split("schedule:", 1)[0]
            self.assertNotIn('"Update Election News Wire"', upstream)
            self.assertIn('"Update polls"', upstream); self.assertIn('"Update candidate universe"', upstream)
            self.assertEqual(text.count("cron:"), 1); self.assertIn(cron, text)
            for marker in ("group: production-data-update", "cancel-in-progress: false", "queue: max"):
                self.assertIn(marker, text)
        text = (ROOT / ".github/workflows/publish-candidate-family.yml").read_text(encoding="utf-8")
        self.assertIn('"Update Election News Wire"', text)


class LiveMarkupTests(unittest.TestCase):
    def test_current_hubs_share_canonical_ids_and_a_single_projection_per_family(self):
        for prefix, paths, expected_ids, url in (
            ("agenda", ("agenda/index.html", "en/agenda/index.html"), CANONICAL_AGENDA_IDS, "/agenda/live.json"),
            ("issue", ("enjeux/index.html", "en/issues/index.html"), CANONICAL_ISSUE_IDS, "/enjeux/live.json"),
        ):
            all_ids = []
            for path in paths:
                text = (ROOT / path).read_text(encoding="utf-8")
                ids = re.findall(r'data-(?:topic|issue)-id="([^"]+)"', text)
                all_ids.append(set(ids))
                self.assertEqual(set(ids), set(expected_ids))
                self.assertEqual(len(ids), len(expected_ids))
                self.assertIn(f'data-{prefix}-live-url="{url}"', text)
                for field in ("count", "publishers", "share", "movement", "signal"):
                    self.assertEqual(text.count(f'data-{prefix}-live="{field}"'), len(ids))
                self.assertIn('application/ld+json', text)
                self.assertIn('rel="canonical"', text)
            self.assertEqual(all_ids[0], all_ids[1])
        self.assertFalse((ROOT / "en/agenda/live.json").exists())
        self.assertFalse((ROOT / "en/issues/live.json").exists())

    def test_history_and_details_keep_static_fetch_isolation(self):
        for root in ("agenda", "en/agenda", "enjeux", "en/issues"):
            for path in (ROOT / root).rglob("index.html"):
                if path == ROOT / root / "index.html": continue
                text = path.read_text(encoding="utf-8")
                self.assertNotIn('data-agenda-live-url', text)
                self.assertNotIn('data-issue-live-url', text)

    @unittest.skipUnless(BASH, "bash syntax/runtime validation requires bash")
    def test_news_shell_syntax_and_generated_scope_guard(self):
        text = (ROOT / ".github/workflows/update-news-wire.yml").read_text(encoding="utf-8")
        for block in re.findall(r"(?m)^        run: \|\n((?:          .*\n|\n)+)", text):
            script = "\n".join(line[10:] for line in block.splitlines())
            result = subprocess.run([BASH, "-n"], input=script, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        function = text.split('          assert_generated_scope() {', 1)[1].split('          assert_generated_scope\n', 1)[0]
        function = 'assert_generated_scope() {' + '\n'.join(line[10:] for line in function.splitlines())
        for path, allowed in (("agenda/live.json", True), ("enjeux/live.json", True),
                              ("news_wire.json", True), ("assets/source-icons/icon.png", True),
                              ("assets/agenda.js", False), ("agenda/index.html", False),
                              ("news_sources.json", False), (".github/workflows/update-polls.yml", False)):
            with self.subTest(path=path):
                script = 'git() { printf "%s\\0" "$TEST_PATH"; }\n' + function + '\nassert_generated_scope\n'
                result = subprocess.run([BASH], input=script, capture_output=True, text=True,
                                        env={**os.environ, "TEST_PATH": path})
                self.assertEqual(result.returncode == 0, allowed, result.stderr)


if __name__ == "__main__": unittest.main()
