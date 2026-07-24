import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "index.html"
MANIFEST_PATH = ROOT / "publication_manifest.json"


def function_body(source, function_name, next_function_name):
    start = source.index(f"function {function_name}(")
    end = source.index(f"function {next_function_name}(", start)
    return source[start:end]


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


if __name__ == "__main__":
    unittest.main()
