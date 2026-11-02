"""The extracted manual source lookup cannot require a publishing client."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import resolve_source_urls as research


class SourceUrlResearchTests(unittest.TestCase):
    def test_direct_urls_work_without_optional_decoder(self):
        with patch.dict(sys.modules, {"googlenewsdecoder": None}):
            self.assertEqual(research.resolve_publisher_urls([
                " https://publisher.example/article ", "https://publisher.example/article",
                "mailto:reader@example.test", ""]),
                {"https://publisher.example/article": "https://publisher.example/article"})

    def test_batch_lookup_deduplicates_and_keeps_only_verified_publisher_results(self):
        urls = ["https://news.google.com/rss/articles/" + str(i) for i in range(4)]
        decode = Mock(return_value=[
            {"success": True, "decoded_url": "https://publisher.example/article"},
            {"status": True, "decoded_url": urls[1]},
            {"success": False, "decoded_url": "https://publisher.example/unverified"},
            {"success": True, "decoded_url": "javascript:invalid"},
        ])
        with patch.dict(sys.modules, {"googlenewsdecoder": SimpleNamespace(gnewsdecoder=decode)}):
            result = research.resolve_publisher_urls(urls + [urls[0]])
        self.assertEqual(result, {urls[0]: "https://publisher.example/article"})
        decode.assert_called_once_with(urls, timeout=15.0)

    def test_failed_lookup_preserves_direct_sources_and_omits_unresolved_links(self):
        decode = Mock(side_effect=RuntimeError("offline"))
        with patch.dict(sys.modules, {"googlenewsdecoder": SimpleNamespace(gnewsdecoder=decode)}), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            result = research.resolve_publisher_urls([
                "https://publisher.example/article", "https://news.google.com/rss/articles/opaque"])
        self.assertEqual(result, {"https://publisher.example/article": "https://publisher.example/article"})
        self.assertIn("batch decode failed", error.getvalue())

    def test_missing_optional_dependency_explains_manual_installation(self):
        with patch.dict(sys.modules, {"googlenewsdecoder": None}):
            with self.assertRaisesRegex(RuntimeError, "tools/research-requirements.txt"):
                research.resolve_publisher_urls(["https://news.google.com/rss/articles/opaque"])

    def test_manual_cli_prints_mapping_without_writing_evidence(self):
        tool = Path(__file__).resolve().parent / "tools/resolve_source_urls.py"
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "news_wire.json"
            evidence.write_bytes(b'{"retained": "source evidence"}\n')
            before = evidence.read_bytes()
            result = subprocess.run([sys.executable, "-B", str(tool),
                "https://publisher.example/article"], cwd=temporary,
                capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout),
                {"https://publisher.example/article": "https://publisher.example/article"})
            self.assertEqual(evidence.read_bytes(), before)
            self.assertEqual({path.name for path in Path(temporary).iterdir()}, {"news_wire.json"})


if __name__ == "__main__":
    unittest.main()
