from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import build_poll_hub_static_links as static_links


ROOT = Path(__file__).resolve().parent


class PollHubStaticLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.explorer = json.loads(
            (ROOT / "poll_explorer.json").read_text(
                encoding="utf-8"
            )
        )
        cls.waves = cls.explorer["waves"]

    def test_committed_hubs_match_generated_contract(self):
        for language, path in static_links.HUBS.items():
            with self.subTest(language=language):
                actual = path.read_text(
                    encoding="utf-8"
                )

                expected = static_links.expected_document(
                    path,
                    waves=self.waves,
                    language=language,
                )

                self.assertEqual(actual, expected)

    def test_every_wave_has_crawlable_static_link(self):
        expected_count = (
            len(self.waves)
            + min(10, len(self.waves))
        )

        for language, path in static_links.HUBS.items():
            with self.subTest(language=language):
                document = path.read_text(
                    encoding="utf-8"
                )

                hrefs = re.findall(
                    r'<a class="polling-wave-open-link" '
                    r'href="([^"]+)"',
                    document,
                )

                self.assertEqual(
                    len(hrefs),
                    expected_count,
                )

                key = (
                    "page_path_fr"
                    if language == "fr"
                    else "page_path_en"
                )

                for wave in self.waves:
                    self.assertIn(
                        wave[key],
                        hrefs,
                    )

    def test_latest_ten_are_linked_twice(self):
        for language, path in static_links.HUBS.items():
            with self.subTest(language=language):
                document = path.read_text(
                    encoding="utf-8"
                )

                hrefs = re.findall(
                    r'<a class="polling-wave-open-link" '
                    r'href="([^"]+)"',
                    document,
                )

                key = (
                    "page_path_fr"
                    if language == "fr"
                    else "page_path_en"
                )

                latest_paths = {
                    wave[key]
                    for wave in self.waves[:10]
                }

                for wave in self.waves:
                    expected = (
                        2
                        if wave[key] in latest_paths
                        else 1
                    )

                    self.assertEqual(
                        hrefs.count(wave[key]),
                        expected,
                    )

    def test_static_links_are_language_safe(self):
        fr_document = static_links.HUBS[
            "fr"
        ].read_text(encoding="utf-8")

        en_document = static_links.HUBS[
            "en"
        ].read_text(encoding="utf-8")

        fr_hrefs = re.findall(
            r'<a class="polling-wave-open-link" '
            r'href="([^"]+)"',
            fr_document,
        )

        en_hrefs = re.findall(
            r'<a class="polling-wave-open-link" '
            r'href="([^"]+)"',
            en_document,
        )

        self.assertTrue(
            all(
                href.startswith("/sondages/")
                for href in fr_hrefs
            )
        )

        self.assertTrue(
            all(
                href.startswith("/en/sondages/")
                for href in en_hrefs
            )
        )

    def test_og_cover_workflow_validates_static_links(self):
        workflow = (
            ROOT
            / ".github"
            / "workflows"
            / "refresh-og-cover.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "test_poll_hub_static_links.py",
            workflow,
        )



    def test_update_polls_workflow_regenerates_static_links(self):
        workflow = (
            ROOT
            / ".github"
            / "workflows"
            / "update-polls.yml"
        ).read_text(encoding="utf-8")

        commands = [
            line.strip()
            for line in workflow.splitlines()
        ]

        self.assertEqual(
            commands.count(
                "python -B "
                "build_poll_hub_static_links.py"
            ),
            2,
        )

        self.assertEqual(
            commands.count(
                "python -B "
                "build_poll_hub_static_links.py "
                "--check"
            ),
            2,
        )

        self.assertIn(
            "test_poll_hub_static_links.py",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
