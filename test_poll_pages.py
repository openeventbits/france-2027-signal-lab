from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import build_poll_pages as pages


ROOT = Path(__file__).resolve().parent


class PollPageGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.explorer = json.loads(
            (ROOT / "poll_explorer.json").read_text(encoding="utf-8")
        )

    def build_temp(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)

        manifest = pages.build_from_paths(
            ROOT / "poll_explorer.json",
            output_root=root,
            template_root=ROOT,
        )

        return temporary, root, manifest

    def test_builds_two_pages_for_every_wave(self):
        temporary, root, manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        self.assertEqual(manifest["wave_count"], len(self.explorer["waves"]))
        self.assertEqual(
            manifest["page_count"],
            len(self.explorer["waves"]) * 2,
        )

        for wave in self.explorer["waves"]:
            self.assertTrue(
                (root / pages.page_file_from_url(wave["page_path_fr"])).exists()
            )
            self.assertTrue(
                (root / pages.page_file_from_url(wave["page_path_en"])).exists()
            )

    def test_manifest_is_deterministic(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        first = (root / pages.MANIFEST_NAME).read_bytes()

        pages.build_from_paths(
            ROOT / "poll_explorer.json",
            output_root=root,
            template_root=ROOT,
        )

        second = (root / pages.MANIFEST_NAME).read_bytes()

        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))

    def test_generated_pages_are_deterministic(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        wave = self.explorer["waves"][0]
        target = root / pages.page_file_from_url(wave["page_path_fr"])

        first = target.read_bytes()

        pages.build_from_paths(
            ROOT / "poll_explorer.json",
            output_root=root,
            template_root=ROOT,
        )

        self.assertEqual(first, target.read_bytes())

    def test_canonical_and_hreflang_contract(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            fr = (
                root / pages.page_file_from_url(wave["page_path_fr"])
            ).read_text(encoding="utf-8")

            en = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            canonical_fr = f"https://france2027.app{wave['page_path_fr']}"
            canonical_en = f"https://france2027.app{wave['page_path_en']}"

            self.assertIn('<html lang="fr">', fr)
            self.assertIn('<html lang="en">', en)

            self.assertIn(
                f'rel="canonical" href="{canonical_fr}"',
                fr,
            )
            self.assertIn(
                f'rel="canonical" href="{canonical_en}"',
                en,
            )

            for document in (fr, en):
                self.assertIn(
                    f'hreflang="fr" href="{canonical_fr}"',
                    document,
                )
                self.assertIn(
                    f'hreflang="en" href="{canonical_en}"',
                    document,
                )
                self.assertIn(
                    f'hreflang="x-default" href="{canonical_fr}"',
                    document,
                )

    def test_every_page_contains_all_scenarios(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            document = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            for index, scenario in enumerate(wave["scenarios"], start=1):
                self.assertIn(f"SCENARIO {index}", document)

                for candidate in scenario["candidates"]:
                    label = pages.candidate_label(candidate)
                    self.assertIn(label, document)
                    self.assertIn(
                        pages.format_score(candidate["score"], "en"),
                        document,
                    )

    def test_external_sources_are_exposed_on_detail_pages(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            document = (
                root / pages.page_file_from_url(wave["page_path_fr"])
            ).read_text(encoding="utf-8")

            for source in pages.wave_sources(wave):
                self.assertIn(f'href="{source}"', document)

    def test_raw_hypothesis_vocabulary_does_not_drive_page_copy(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        corpus = []

        for wave in self.explorer["waves"]:
            corpus.append(
                (
                    root / pages.page_file_from_url(wave["page_path_fr"])
                ).read_text(encoding="utf-8")
            )

        rendered = "\n".join(corpus)

        self.assertNotIn("French rehearsal", rendered)
        self.assertNotIn("French source", rendered)
        self.assertNotRegex(rendered, r">\s*Generic\s+")

    def test_boundary_language_is_present(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        wave = self.explorer["waves"][0]

        fr = (
            root / pages.page_file_from_url(wave["page_path_fr"])
        ).read_text(encoding="utf-8")

        en = (
            root / pages.page_file_from_url(wave["page_path_en"])
        ).read_text(encoding="utf-8")

        self.assertIn("AUCUNE MOYENNE DE SONDAGES", fr)
        self.assertIn("AUCUNE PRÉVISION", fr)
        self.assertIn("AUCUN CONSEIL DE VOTE", fr)

        self.assertIn("NO POLLING AVERAGES", en)
        self.assertIn("NO FORECAST", en)
        self.assertIn("NO VOTING ADVICE", en)

    def test_page_titles_are_unique_within_each_language(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for language, key in (
            ("fr", "page_path_fr"),
            ("en", "page_path_en"),
        ):
            titles = []

            for wave in self.explorer["waves"]:
                document = (
                    root / pages.page_file_from_url(wave[key])
                ).read_text(encoding="utf-8")

                match = re.search(r"<title>(.*?)</title>", document)

                self.assertIsNotNone(match)
                titles.append(match.group(1))

            self.assertEqual(len(titles), len(set(titles)))

    def test_generated_tree_passes_check_mode(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        errors = pages.check_from_paths(
            ROOT / "poll_explorer.json",
            output_root=root,
            template_root=ROOT,
        )

        self.assertEqual(errors, [])


    def test_phase2_scenarios_use_native_disclosures(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            document = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            scenario_tags = re.findall(
                r'<details class="poll-detail-scenario"[^>]*>',
                document,
            )

            self.assertEqual(
                len(scenario_tags),
                wave["scenario_count"],
            )

            for index in range(1, wave["scenario_count"] + 1):
                self.assertIn(
                    f'id="scenario-{index}"',
                    document,
                )

    def test_phase2_single_scenario_is_open_by_default(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            if wave["scenario_count"] != 1:
                continue

            document = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            tag = re.search(
                r'<details class="poll-detail-scenario"[^>]*>',
                document,
            )

            self.assertIsNotNone(tag)
            self.assertIn(" open>", tag.group(0))

    def test_phase2_multi_scenario_pages_start_collapsed(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            if wave["scenario_count"] <= 1:
                continue

            document = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            tags = re.findall(
                r'<details class="poll-detail-scenario"[^>]*>',
                document,
            )

            self.assertTrue(tags)
            self.assertTrue(
                all(" open>" not in tag for tag in tags)
            )

    def test_phase2_expand_collapse_controls_only_for_multi_scenario(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            document = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            if wave["scenario_count"] > 1:
                self.assertIn("data-poll-expand-all", document)
                self.assertIn("data-poll-collapse-all", document)
            else:
                self.assertNotIn("data-poll-expand-all", document)
                self.assertNotIn("data-poll-collapse-all", document)

    def test_phase2_scenario_navigation_matches_wave_count(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            fr = (
                root / pages.page_file_from_url(wave["page_path_fr"])
            ).read_text(encoding="utf-8")

            en = (
                root / pages.page_file_from_url(wave["page_path_en"])
            ).read_text(encoding="utf-8")

            fr_links = re.findall(
                r'class="poll-detail-scenario-nav-link"',
                fr,
            )

            en_links = re.findall(
                r'class="poll-detail-scenario-nav-link"',
                en,
            )

            expected = (
                wave["scenario_count"]
                if wave["scenario_count"] > 1
                else 0
            )

            self.assertEqual(len(fr_links), expected)
            self.assertEqual(len(en_links), expected)

            if expected:
                for index in range(1, expected + 1):
                    self.assertIn(
                        f'href="#scenario-{index}"',
                        fr,
                    )
                    self.assertIn(
                        f'href="#scenario-{index}"',
                        en,
                    )

    def test_phase2_uses_dashboard_purple_not_green_for_status(self):
        css = (ROOT / "assets/poll-page.css").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("--poll-detail-green", css)
        self.assertIn(
            "--poll-detail-violet-base: var(--final-violet, #8b79ff);",
            css,
        )
        self.assertIn(
            "--poll-detail-violet: #b9a7ff;",
            css,
        )
        self.assertIn(
            "color: var(--poll-detail-violet);",
            css,
        )
        self.assertIn(
            ".poll-detail-scenario-status.is-partial",
            css,
        )

    def test_phase2_right_rail_is_sticky_on_desktop(self):
        css = (ROOT / "assets/poll-page.css").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ".poll-detail-side-column {\n"
            "    position: sticky;",
            css,
        )
        self.assertIn(
            ".poll-detail-scenario-nav-list",
            css,
        )

    def test_phase2_navigation_js_is_standalone(self):
        script = (ROOT / "assets/poll-page.js").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "FR27 POLL DETAIL PHASE 2 — SCENARIO NAVIGATION",
            script,
        )
        self.assertIn("data-scenario-target", script)
        self.assertIn("data-poll-expand-all", script)
        self.assertIn("data-poll-collapse-all", script)
        self.assertIn("openFromHash", script)

        self.assertNotIn("state.", script)
        self.assertNotIn("nodes.", script)
        self.assertNotIn("renderExplorer(", script)



    def test_phase3_search_metadata_and_breadcrumb_contract(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            for language, key in (
                ("fr", "page_path_fr"),
                ("en", "page_path_en"),
            ):
                document = (
                    root
                    / pages.page_file_from_url(wave[key])
                ).read_text(encoding="utf-8")

                canonical = (
                    "https://france2027.app"
                    + wave[key]
                )

                canonical_fr = (
                    "https://france2027.app"
                    + wave["page_path_fr"]
                )

                canonical_en = (
                    "https://france2027.app"
                    + wave["page_path_en"]
                )

                self.assertIn(
                    '<meta name="robots" '
                    'content="index,follow,max-image-preview:large">',
                    document,
                )

                self.assertIn(
                    f'<link rel="canonical" '
                    f'href="{canonical}">',
                    document,
                )

                self.assertIn(
                    f'<link rel="alternate" '
                    f'hreflang="fr" '
                    f'href="{canonical_fr}">',
                    document,
                )

                self.assertIn(
                    f'<link rel="alternate" '
                    f'hreflang="en" '
                    f'href="{canonical_en}">',
                    document,
                )

                self.assertIn(
                    f'<link rel="alternate" '
                    f'hreflang="x-default" '
                    f'href="{canonical_fr}">',
                    document,
                )

                self.assertIn(
                    '<meta property="og:type" '
                    'content="website">',
                    document,
                )

                self.assertIn(
                    '<meta property="og:site_name" '
                    'content="France 2027 Signal Lab">',
                    document,
                )

                expected_locale = (
                    "fr_FR"
                    if language == "fr"
                    else "en_GB"
                )

                alternate_locale = (
                    "en_GB"
                    if language == "fr"
                    else "fr_FR"
                )

                self.assertIn(
                    f'<meta property="og:locale" '
                    f'content="{expected_locale}">',
                    document,
                )

                self.assertIn(
                    f'<meta property="og:locale:alternate" '
                    f'content="{alternate_locale}">',
                    document,
                )

                self.assertIn(
                    '<meta name="twitter:card" '
                    'content="summary">',
                    document,
                )

                self.assertIn(
                    '<meta name="twitter:title"',
                    document,
                )

                self.assertIn(
                    '<meta name="twitter:description"',
                    document,
                )

                blocks = re.findall(
                    r'<script type="application/ld\+json">'
                    r'(.*?)'
                    r'</script>',
                    document,
                    flags=re.DOTALL,
                )

                self.assertEqual(
                    len(blocks),
                    2,
                )

                payloads = [
                    json.loads(block)
                    for block in blocks
                ]

                by_type = {
                    payload["@type"]: payload
                    for payload in payloads
                }

                self.assertEqual(
                    set(by_type),
                    {"Dataset", "BreadcrumbList"},
                )

                dataset = by_type["Dataset"]

                self.assertEqual(
                    dataset["url"],
                    canonical,
                )

                self.assertEqual(
                    dataset["inLanguage"],
                    language,
                )

                breadcrumb = by_type["BreadcrumbList"]
                items = breadcrumb["itemListElement"]

                self.assertEqual(
                    [item["position"] for item in items],
                    [1, 2, 3],
                )

                expected_home = (
                    "https://france2027.app/"
                    if language == "fr"
                    else "https://france2027.app/en/"
                )

                expected_poll_hub = (
                    "https://france2027.app/sondages/"
                    if language == "fr"
                    else "https://france2027.app/en/sondages/"
                )

                self.assertEqual(
                    items[0]["item"],
                    expected_home,
                )

                self.assertEqual(
                    items[1]["item"],
                    expected_poll_hub,
                )

                self.assertEqual(
                    items[2]["item"],
                    canonical,
                )

                title_match = re.search(
                    r"<title>(.*?)</title>",
                    document,
                )

                self.assertIsNotNone(title_match)

                title = title_match.group(1)

                self.assertIn(
                    wave["pollster"],
                    title,
                )

                if language == "fr":
                    self.assertIn(
                        "Sondage présidentiel",
                        title,
                    )
                else:
                    self.assertIn(
                        "Presidential Poll",
                        title,
                    )

    def test_page_descriptions_are_unique_within_each_language(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for key in (
            "page_path_fr",
            "page_path_en",
        ):
            descriptions = []

            for wave in self.explorer["waves"]:
                document = (
                    root
                    / pages.page_file_from_url(wave[key])
                ).read_text(encoding="utf-8")

                match = re.search(
                    r'<meta name="description" '
                    r'content="([^"]+)">',
                    document,
                )

                self.assertIsNotNone(match)

                description = match.group(1)

                self.assertIn(
                    wave["pollster"],
                    description,
                )

                descriptions.append(description)

            self.assertEqual(
                len(descriptions),
                len(set(descriptions)),
            )


if __name__ == "__main__":
    unittest.main()