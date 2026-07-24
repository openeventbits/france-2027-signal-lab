import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "index.html"
MANIFEST_PATH = ROOT / "publication_manifest.json"


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
