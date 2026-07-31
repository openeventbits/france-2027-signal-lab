import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "index.html"
MANIFEST_PATH = ROOT / "publication_manifest.json"

CANDIDATE_SIGNALS_PATH = ROOT / "candidate_signals.json"

def function_body(source, function_name, next_function_name):
    start = source.index(f"function {function_name}(")
    end = source.index(f"function {next_function_name}(", start)
    return source[start:end]


def run_comparison_script(index_source, expression):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node.js is required for frontend fact tests")
    functions = function_body(
        index_source,
        "candidateScore",
        "formatComparableDelta",
    )
    result = subprocess.run(
        [node, "-e", functions + "\nconsole.log(JSON.stringify(" + expression + "));"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class FrontendPublicationFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX_PATH.read_text(encoding="utf-8")

    def test_publication_manifest_is_loaded_with_dashboard_data(self):
        self.assertIn(
            'fetch("publication_manifest.json", { cache: "no-store" })',
            self.index,
        )
        self.assertIn("function validatePublicationManifestPayload(", self.index)
        self.assertIn("function loadPublicationManifest(", self.index)
        self.assertIn("loadPublicationManifest();", self.index)
        self.assertTrue(
            MANIFEST_PATH.exists(),
            "publication_manifest.json must be a published static artifact",
        )

    def test_publication_facts_version_active_field_snapshot(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        candidate = json.loads(
            CANDIDATE_SIGNALS_PATH.read_text(encoding="utf-8")
        )
        lane = manifest["lanes"]["candidate_signals"]
        self.assertEqual(manifest["schema_version"], "1.2")
        self.assertEqual(lane["schema_version"], candidate["schema_version"])
        self.assertEqual(candidate["schema_version"], "1.2")
        self.assertEqual(lane["file"], "candidate_signals.json")
        self.assertEqual(lane["record_count"], len(candidate["candidates"]))
        self.assertEqual(
            lane["data_as_of"],
            candidate["candidate_universe"]["as_of_date"],
        )
        active = candidate["active_field_visibility"]
        self.assertEqual(
            active["method"],
            "share_of_active_candidate_linked_records",
        )
        for scope_name in ("primary", "general"):
            scope = active[scope_name]
            quality = scope["comparison_quality"]
            for prefix, period_name in (
                ("current", "current_period"),
                ("prior", "prior_period"),
            ):
                period = scope[period_name]
                self.assertIsInstance(period["record_count"], int)
                self.assertGreaterEqual(period["record_count"], 0)
                self.assertEqual(
                    quality[f"{prefix}_record_count"],
                    period["record_count"],
                )
                self.assertEqual(
                    quality[f"{prefix}_publisher_count"],
                    period["publisher_count"],
                )

    def test_active_field_quality_remains_authoritative_for_frontend_rendering(self):
        candidate = json.loads(
            CANDIDATE_SIGNALS_PATH.read_text(encoding="utf-8")
        )
        primary = candidate["active_field_visibility"]["primary"]
        quality = primary["comparison_quality"]
        self.assertIn(quality["status"], {"comparable", "not_comparable"})
        if quality["status"] == "comparable":
            self.assertEqual(quality["reason"], "comparable")
        else:
            self.assertIn(
                quality["reason"],
                {"insufficient_data", "publisher_panel_changed"},
            )
        rows = primary["main"] + primary["secondary"]
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("current_share", row)
            self.assertIn("prior_share", row)
            if (
                quality["status"] == "comparable"
                and row["current_share"] is not None
                and row["prior_share"] is not None
            ):
                self.assertIsNotNone(row["share_change"])
            else:
                self.assertIsNone(row["share_change"])
        identities = {
            row["candidate_id"]: row["candidate_name"]
            for row in rows
        }
        self.assertNotIn("sarah-knafo", identities)
        self.assertNotIn("sebastien-lecornu", identities)
        self.assertEqual(
            identities["dominique-de-villepin"],
            "Dominique de Villepin",
        )
        dashboard = (
            ROOT / "assets" / "hybrid-dashboard.js"
        ).read_text(encoding="utf-8")
        modal = (
            ROOT / "assets" / "topic-coverage-modal.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("fetch(", dashboard)
        self.assertNotIn("fetch(", modal)

    def test_masthead_uses_snapshot_publication_language(self):
        renderer = function_body(
            self.index,
            "renderMastheadMetadata",
            "pollFieldworkLabel",
        )
        self.assertIn('"Snapshot published "', renderer)
        self.assertIn("manifest.published_at", renderer)
        self.assertIn("mastheadLaneSummaries(manifest)", renderer)
        self.assertIn('"Poll check unknown"', self.index)
        self.assertNotIn("Published data checked", self.index)

    def test_recent_changes_check_is_not_global_dashboard_freshness(self):
        renderer = function_body(
            self.index,
            "renderMastheadMetadata",
            "pollFieldworkLabel",
        )
        self.assertNotIn("recentChanges", renderer)
        self.assertNotIn("last_successful_check_at", renderer)
        self.assertIn("lanes.recent_changes", self.index)
        self.assertIn('"Changes checked "', self.index)

    def test_recent_changes_source_universe_matches_loaded_news(self):
        validator = function_body(
            self.index,
            "validateRecentChangesPayload",
            "loadRecentChanges",
        )
        self.assertNotIn("source_universe.length !== 19", validator)
        self.assertNotIn("source_universe.length !== 18", validator)
        self.assertIn(
            "dashboardState.news?.feed_coverage?.direct_feeds",
            validator,
        )
        self.assertIn(
            "sourceUniverse.length !== expectedDirectSourceCount",
            validator,
        )

        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for frontend fact tests")
        script = """
          const dashboardState = { news: null };
        """ + validator + """
          function payload(sourceUniverse) {
            return {
              schema_version: 1,
              window: {
                days: 14,
                max_items: 0,
                start_date: "2026-07-15",
                end_date: "2026-07-28"
              },
              source_universe: sourceUniverse,
              items: [],
              newest_trusted_change_at: null,
              oldest_trusted_change_at: null
            };
          }
          function names(count) {
            return Array.from(
              { length: count },
              (_, index) => "Source " + index
            );
          }
          function check(directFeeds, sourceUniverse) {
            dashboardState.news = {
              feed_coverage: { direct_feeds: directFeeds }
            };
            try {
              validateRecentChangesPayload(payload(sourceUniverse));
              return "ok";
            } catch (error) {
              return error.message;
            }
          }
          console.log(JSON.stringify({
            current: check(19, names(19)),
            next: check(18, names(18)),
            mismatch: check(18, names(19)),
            duplicate: check(2, ["Source", "Source"]),
            malformed: check(1, [" Source "])
          }));
        """
        result = subprocess.run(
            [node, "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        outcomes = json.loads(result.stdout)
        self.assertEqual(outcomes["current"], "ok")
        self.assertEqual(outcomes["next"], "ok")
        self.assertIn("does not match", outcomes["mismatch"])
        self.assertIn("unique", outcomes["duplicate"])
        self.assertIn("trimmed", outcomes["malformed"])

    def test_source_network_metrics_keep_distinct_labels(self):
        summary = function_body(
            self.index,
            "sourceNetworkSummaryParts",
            "renderSignalDeskNote",
        )
        expected_labels = (
            "approved publisher domains",
            "configured media publishers",
            "configured routes or feeds",
            "routes due this run",
            "successful due routes",
            "contributing publishers in retained period",
            "publishers in accepted election news",
        )
        for label in expected_labels:
            with self.subTest(label=label):
                self.assertIn(label, summary)

        self.assertNotRegex(
            self.index,
            re.compile(
                r"(approved_publisher_domains|configured_media_publishers)"
                r".{0,120}approved sources",
                re.DOTALL,
            ),
        )
        self.assertNotIn('mastheadUnit: "approved sources"', self.index)

    def test_render_bars_passes_selected_event_to_comparison(self):
        renderer = function_body(
            self.index,
            "renderBars",
            "renderMeta",
        )
        self.assertRegex(
            renderer,
            re.compile(
                r"deriveComparableChange\(\s*events,\s*"
                r"candidate\.name,\s*event\.fieldwork_end,\s*event\s*\)",
                re.DOTALL,
            ),
        )

    def test_selected_event_is_anchor_and_cross_pollster_is_unavailable(self):
        fixtures = """
          (() => {
            const currentA = {
              event_id: "current-a", pollster: "A", round: "first_round",
              fieldwork_end: "2026-07-10", scenario_key: "same",
              candidates: [{name: "Candidate", score: 20}]
            };
            const currentB = {
              event_id: "current-b", pollster: "B", round: "first_round",
              fieldwork_end: "2026-07-10", scenario_key: "same",
              candidates: [{name: "Candidate", score: 30}]
            };
            const priorA = {
              event_id: "prior-a", pollster: "A", round: "first_round",
              fieldwork_end: "2026-07-01", scenario_key: "same",
              candidates: [{name: "Candidate", score: 15}]
            };
            const priorB = {
              event_id: "prior-b", pollster: "B", round: "first_round",
              fieldwork_end: "2026-07-01", scenario_key: "same",
              candidates: [{name: "Candidate", score: 10}]
            };
            const anchored = deriveComparableChange(
              [currentA, currentB, priorA, priorB],
              "Candidate",
              "2026-07-10",
              currentA
            );
            const unavailable = deriveComparableChange(
              [currentA, priorB],
              "Candidate",
              "2026-07-10",
              currentA
            );
            return {
              current: anchored.retained[0].current.event_id,
              previous: anchored.retained[0].previous.event_id,
              delta: anchored.deltas[0],
              unavailable: unavailable.classification
            };
          })()
        """
        result = run_comparison_script(self.index, fixtures)
        self.assertEqual(
            result,
            {
                "current": "current-a",
                "previous": "prior-a",
                "delta": 5,
                "unavailable": "NO COMPARABLE PRIOR",
            },
        )

    def test_comparison_requires_same_round_and_scenario(self):
        comparison = function_body(
            self.index,
            "deriveComparableChange",
            "formatComparableDelta",
        )
        self.assertIn("previous.round !== current.round", comparison)
        self.assertIn(
            "previous.scenario_key !== current.scenario_key",
            comparison,
        )
        self.assertIn(
            "normalizeComparableText(previous.pollster) !== currentPollster",
            comparison,
        )
        self.assertNotIn("preferredPool", comparison)

    def test_partial_disclosure_is_gated_to_valid_partial_events(self):
        renderer = function_body(
            self.index,
            "pollPartialDisclosure",
            "renderMeta",
        )
        self.assertIn(
            'event.completeness_status !== "partial"',
            renderer,
        )
        self.assertIn("event.partial_scenario !== true", renderer)
        self.assertIn("Partial reported field", renderer)
        self.assertIn("Reported total", renderer)
        self.assertIn("Unreported share", renderer)

        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for frontend fact tests")
        format_score = re.search(
            r"const formatScore = .*?;",
            self.index,
        ).group(0)
        expression = """
          [
            pollPartialDisclosure({
              completeness_status: "partial",
              partial_scenario: true,
              reported_total: 97,
              unreported_share: 3
            }),
            pollPartialDisclosure({
              completeness_status: "complete",
              partial_scenario: false,
              reported_total: 100,
              unreported_share: null
            })
          ]
        """
        result = subprocess.run(
            [
                node,
                "-e",
                format_score
                + "\n"
                + renderer
                + "\nconsole.log(JSON.stringify("
                + expression
                + "));",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        partial, complete = json.loads(result.stdout)
        self.assertIn("Partial reported field", partial)
        self.assertIn("Reported total 97%", partial)
        self.assertIn("Unreported share 3%", partial)
        self.assertEqual(complete, "")


if __name__ == "__main__":
    unittest.main()
