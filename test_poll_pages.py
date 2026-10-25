from __future__ import annotations

import copy
import hashlib
from unittest.mock import patch
from lxml import html
import poll_source_tables as source
import build_poll_hub_static_links as hubs
import build_route_registry as routes
import build_sitemaps as sitemaps
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

    def test_polling_routes_share_site_og_cover(self):
        root_document = (
            ROOT / "index.html"
        ).read_text(encoding="utf-8")

        match = re.search(
            r'<meta\s+property="og:image"\s+'
            r'content="([^"]+)">',
            root_document,
            flags=re.IGNORECASE,
        )

        self.assertIsNotNone(match)
        og_image_url = match.group(1)

        expected_og = (
            f'<meta property="og:image" '
            f'content="{og_image_url}">'
        )

        expected_twitter = (
            f'<meta name="twitter:image" '
            f'content="{og_image_url}">'
        )

        expected_card = (
            '<meta name="twitter:card" '
            'content="summary_large_image">'
        )

        for relative in (
            Path("sondages/index.html"),
            Path("en/sondages/index.html"),
        ):
            document = (
                ROOT / relative
            ).read_text(encoding="utf-8")

            self.assertEqual(
                document.count(expected_og),
                1,
            )
            self.assertEqual(
                document.count(expected_twitter),
                1,
            )
            self.assertEqual(
                document.count(expected_card),
                1,
            )

        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            for key in (
                "page_path_fr",
                "page_path_en",
            ):
                relative = pages.page_file_from_url(
                    wave[key]
                )

                document = (
                    root / relative
                ).read_text(encoding="utf-8")

                self.assertEqual(
                    document.count(expected_og),
                    1,
                )
                self.assertEqual(
                    document.count(expected_twitter),
                    1,
                )
                self.assertEqual(
                    document.count(expected_card),
                    1,
                )


    def test_polling_routes_share_site_favicon(self):
        root_document = (
            ROOT / "index.html"
        ).read_text(encoding="utf-8")

        match = re.search(
            r'<link\s+rel="icon"\s+'
            r'type="image/svg\+xml"\s+'
            r'href="data:image/svg\+xml;base64,[^"]+">',
            root_document,
            flags=re.IGNORECASE,
        )

        self.assertIsNotNone(match)
        favicon = match.group(0)

        for relative in (
            Path("sondages/index.html"),
            Path("en/sondages/index.html"),
        ):
            document = (
                ROOT / relative
            ).read_text(encoding="utf-8")

            self.assertEqual(
                document.count(favicon),
                1,
                relative.as_posix(),
            )

        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        for wave in self.explorer["waves"]:
            for key in (
                "page_path_fr",
                "page_path_en",
            ):
                relative = pages.page_file_from_url(
                    wave[key]
                )

                document = (
                    root / relative
                ).read_text(encoding="utf-8")

                self.assertEqual(
                    document.count(favicon),
                    1,
                    relative.as_posix(),
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
                    label = pages.candidate_label(candidate, "en")
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

    def test_compact_date_ranges_and_generated_harris_pages(self):
        cases = (
            ("2026-09-08", "2026-09-10", "en", "8–10 September 2026"),
            ("2026-09-08", "2026-09-10", "fr", "8–10 septembre 2026"),
            ("2026-08-31", "2026-09-02", "en", "31 Aug–2 Sep 2026"),
            ("2026-08-31", "2026-09-02", "fr", "31 août–2 sept. 2026"),
            ("2025-12-30", "2026-01-02", "en", "30 Dec 2025–2 Jan 2026"),
            ("2025-12-30", "2026-01-02", "fr", "30 déc. 2025–2 janv. 2026"),
            ("2026-09-08", "2026-09-08", "en", "8 September 2026"),
            ("2026-09-08", "2026-09-08", "fr", "8 septembre 2026"),
        )

        for start, end, language, expected in cases:
            with self.subTest(
                start=start,
                end=end,
                language=language,
            ):
                self.assertEqual(
                    pages.format_date_range(start, end, language),
                    expected,
                )

        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        wave_index = next(
            index
            for index, candidate in enumerate(self.explorer["waves"])
            if candidate["page_slug"]
            == "2026-09-10-harris-73b34108d6ec9da8"
        )
        wave = self.explorer["waves"][wave_index]
        related = pages.nearby_waves(
            self.explorer["waves"],
            wave_index,
            limit=6,
        )
        self.assertEqual(len(related), 6)

        fr = (
            root / pages.page_file_from_url(wave["page_path_fr"])
        ).read_text(encoding="utf-8")

        en = (
            root / pages.page_file_from_url(wave["page_path_en"])
        ).read_text(encoding="utf-8")

        self.assertIn(
            '<div class="poll-detail-metric poll-detail-metric-fieldwork">',
            fr,
        )
        self.assertIn("<strong>8–10 septembre 2026</strong>", fr)
        self.assertIn("<strong>8–10 September 2026</strong>", en)
        self.assertEqual(
            fr.count('<a class="poll-detail-related-card"'),
            6,
        )
        self.assertEqual(
            en.count('<a class="poll-detail-related-card"'),
            6,
        )

        for related_wave in related:
            fr_date = pages.format_date_range(
                related_wave["fieldwork_start"],
                related_wave["fieldwork_end"],
                "fr",
            )
            en_date = pages.format_date_range(
                related_wave["fieldwork_start"],
                related_wave["fieldwork_end"],
                "en",
            )

            with self.subTest(
                related_poll=related_wave["page_slug"],
            ):
                self.assertIn(
                    '<a class="poll-detail-related-card" '
                    f'href="{related_wave["page_path_fr"]}">',
                    fr,
                )
                self.assertIn(
                    '<span class="poll-detail-related-date">'
                    f"{fr_date}</span>",
                    fr,
                )
                self.assertIn(
                    '<a class="poll-detail-related-card" '
                    f'href="{related_wave["page_path_en"]}">',
                    en,
                )
                self.assertIn(
                    '<span class="poll-detail-related-date">'
                    f"{en_date}</span>",
                    en,
                )
        self.assertNotIn(
            "8 septembre 2026 → 10 septembre 2026",
            fr,
        )
        self.assertNotIn(
            "8 September 2026 → 10 September 2026",
            en,
        )
        self.assertIn(
            '<a class="poll-detail-related-all" href="/sondages/">'
            "VOIR TOUS LES SONDAGES →</a>",
            fr,
        )
        self.assertIn(
            '<a class="poll-detail-related-all" href="/en/sondages/">'
            "VIEW ALL POLLS →</a>",
            en,
        )
        self.assertNotIn(
            '<a class="poll-detail-back-cta" href="/sondages/">',
            fr,
        )
        self.assertNotIn(
            '<a class="poll-detail-back-cta" href="/en/sondages/">',
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

    def test_related_poll_directory_cta_is_text_only(self):
        css = (ROOT / "assets/poll-page.css").read_text(
            encoding="utf-8"
        )

        match = re.search(
            r"\.poll-detail-related-all \{(?P<body>.*?)\n\}",
            css,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("min-height: 0;", body)
        self.assertIn("padding: 2px 0;", body)
        self.assertIn("border: 0;", body)
        self.assertIn("border-radius: 0;", body)
        self.assertIn("background: transparent;", body)
        self.assertIn("color: var(--poll-detail-cyan);", body)

        self.assertIn(
            ".poll-detail-related-all:focus-visible",
            css,
        )

    def test_phase2_disclosure_controls_js_is_standalone(self):
        script = (ROOT / "assets/poll-page.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("data-poll-expand-all", script)
        self.assertIn("data-poll-collapse-all", script)
        self.assertIn(".poll-detail-scenario-toggle-text", script)
        self.assertIn('details.addEventListener("toggle"', script)

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
                    'content="summary_large_image">',
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



    def test_pollster_note_is_moved_into_accessible_tooltip(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        wave = self.explorer["waves"][0]

        fr = (
            root
            / pages.page_file_from_url(
                wave["page_path_fr"]
            )
        ).read_text(encoding="utf-8")

        en = (
            root
            / pages.page_file_from_url(
                wave["page_path_en"]
            )
        ).read_text(encoding="utf-8")

        for document in (fr, en):
            self.assertNotIn(
                'class="poll-detail-deck"',
                document,
            )

            self.assertIn(
                "data-poll-tooltip-trigger",
                document,
            )

            self.assertIn(
                'aria-describedby="poll-wave-note"',
                document,
            )

            self.assertIn(
                'aria-controls="poll-wave-note"',
                document,
            )

            self.assertIn(
                'aria-expanded="false"',
                document,
            )

            self.assertIn(
                'id="poll-wave-note"',
                document,
            )

            self.assertIn(
                'role="tooltip"',
                document,
            )

        self.assertIn(
            "Les scénarios sont présentés séparément afin "
            "de préserver la composition exacte des bulletins testés.",
            fr,
        )

        self.assertIn(
            "Scenarios are kept separate to preserve "
            "the exact composition of the ballots tested.",
            en,
        )

        css = (
            ROOT / "assets" / "poll-page.css"
        ).read_text(encoding="utf-8")

        js = (
            ROOT / "assets" / "poll-page.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".poll-detail-tooltip-trigger",
            css,
        )

        self.assertIn(
            '.poll-detail-tooltip-wrap[data-open="true"] '
            ".poll-detail-tooltip",
            css,
        )

        self.assertIn(
            "[data-poll-tooltip-trigger]",
            js,
        )

        self.assertIn(
            '"aria-expanded"',
            js,
        )

        self.assertIn(
            '"Escape"',
            js,
        )


    def test_phase4_uses_simple_flow_and_related_poll_discovery(self):
        temporary, root, _manifest = self.build_temp()
        self.addCleanup(temporary.cleanup)

        wave_index = max(
            range(len(self.explorer["waves"])),
            key=lambda index:
                self.explorer["waves"][index]["scenario_count"],
        )

        wave = self.explorer["waves"][wave_index]

        document = (
            root
            / pages.page_file_from_url(
                wave["page_path_en"]
            )
        ).read_text(encoding="utf-8")

        # Removed duplicate support UI.
        self.assertNotIn(
            'id="scenario-navigation-title"',
            document,
        )

        self.assertNotIn(
            'id="wave-sources-title"',
            document,
        )

        self.assertNotIn(
            'class="poll-detail-support-stack"',
            document,
        )

        self.assertNotIn(
            'class="poll-detail-support-row"',
            document,
        )

        # Core reading flow remains.
        self.assertIn(
            'class="poll-detail-panel poll-detail-results"',
            document,
        )

        self.assertIn(
            'class="poll-detail-panel poll-detail-related"',
            document,
        )

        # Six deterministic nearby poll links.
        expected_related = pages.nearby_waves(
            self.explorer["waves"],
            wave_index,
            limit=6,
        )

        self.assertEqual(
            len(expected_related),
            6,
        )

        self.assertEqual(
            document.count(
                'class="poll-detail-related-card"'
            ),
            6,
        )

        for related in expected_related:
            self.assertIn(
                f'href="{related["page_path_en"]}"',
                document,
            )

        # Discovery appears after the actual poll evidence.
        hero_position = document.index(
            'class="poll-detail-hero"'
        )

        results_position = document.index(
            'class="poll-detail-panel poll-detail-results"'
        )

        related_position = document.index(
            'class="poll-detail-panel poll-detail-related"'
        )

        self.assertLess(
            hero_position,
            results_position,
        )

        self.assertLess(
            results_position,
            related_position,
        )

        if "poll-detail-variation-panel" in document:
            variation_position = document.index(
                "poll-detail-variation-panel"
            )

            self.assertLess(
                hero_position,
                variation_position,
            )

            self.assertLess(
                variation_position,
                results_position,
            )

        # Generator must not emit trailing whitespace.
        for line in document.splitlines():
            self.assertEqual(
                line,
                line.rstrip(),
            )

        css = (
            ROOT / "assets" / "poll-page.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".poll-detail-related-grid",
            css,
        )

        self.assertIn(
            ".poll-detail-related-card",
            css,
        )

        self.assertNotIn(
            "FLAT HORIZONTAL SUPPORT LAYOUT",
            css,
        )


class ExceptionalSourceTableTests(unittest.TestCase):
    """Presentation evidence stays separate from numerical events and routes."""

    @classmethod
    def setUpClass(cls):
        import poll_source_tables as source
        cls.source = source
        cls.record = source.load_source_tables()
        cls.explorer = json.loads((ROOT / "poll_explorer.json").read_text(encoding="utf-8"))
        cls.artifacts, cls.manifest = pages.expected_artifacts(cls.explorer, template_root=ROOT)

    def test_source_records_and_documentary_hashes_are_pinned(self):
        expected = {
            "10327": (14, "39b82377458a44db5c7de3ad95ca4f7938f87dd791163083206538c32795fac5"),
            "10264": (12, "3e427407804098116e859a47f1ba3b0d0428145714b35c593e900e800768cd27"),
            "10260": (14, "bcc6f5e46048615f31188b9d98cd708339f276e8fe959d3c9c1b5833a1d58b0c"),
            "10319": (12, "c66cc3da2bcdbf8cfcf5d93552242d8a20b09554eecee399be458e90282a079d"),
            "10333": (12, "cfe91916d69dc57bb57aa4979f09d00430bd25983a0ee77d087a0cab7020df94"),
        }
        self.assertEqual(set(self.record["tables"]), set(expected))
        self.assertEqual(set(self.record["existing_pages"]), {"10327", "10260"})
        for notice, (page, sha) in expected.items():
            table = self.record["tables"][notice]["table"]
            self.assertEqual((table["source"]["pdf_page"], table["source"]["pdf_sha256"]), (page, sha))
            self.assertEqual(table["numerical_comparisons"], "excluded_whole_table")

    def test_missing_altered_or_fabricated_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            with self.assertRaises(FileNotFoundError):
                self.source.load_source_tables(path)
            for change in ("literal", "review", "pdf", "extra"):
                with self.subTest(change=change):
                    altered = copy.deepcopy(self.record)
                    if change == "literal":
                        altered["tables"]["10327"]["table"]["rows"][0]["result"]["literal"] = "0"
                    elif change == "review":
                        altered["provenance"]["review_sha256"] = "0" * 64
                    elif change == "pdf":
                        altered["tables"]["10264"]["table"]["source"]["pdf_sha256"] = "0" * 64
                    else:
                        altered["tables"]["99999"] = altered["tables"]["10264"]
                    path.write_text(json.dumps(altered), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "evidence changed"):
                        self.source.load_source_tables(path)

    def test_wave_association_rejects_changed_or_duplicated_numerical_facts(self):
        for pin in self.record["existing_pages"].values():
            wave = next(w for w in self.explorer["waves"] if w["wave_id"] == pin["wave_id"])
            for change in ("score", "date", "sample", "event", "duplicate", "count"):
                with self.subTest(wave=wave["wave_id"], change=change):
                    altered = copy.deepcopy(wave)
                    if change == "score":
                        altered["scenarios"][0]["candidates"][0]["score"] += 1
                    elif change == "date":
                        altered["fieldwork_start"] = "2026-01-01"
                    elif change == "sample":
                        altered["sample_size"] += 1
                    elif change == "event":
                        altered["scenarios"][0]["event_id"] = "0" * 64
                    elif change == "duplicate":
                        altered["scenarios"][0]["candidates"].append(altered["scenarios"][0]["candidates"][0])
                    else:
                        altered["scenario_count"] += 1
                    with self.assertRaisesRegex(ValueError, "association changed"):
                        self.source.source_table_for_wave(altered, self.record)

    def test_all_literal_values_names_positions_and_pdf_links_in_both_languages(self):
        from lxml import html
        for notice, entry in self.record["tables"].items():
            table = entry["table"]
            for language in ("fr", "en"):
                with self.subTest(notice=notice, language=language):
                    card = html.fromstring(self.source.render_source_card(table, language))
                    actual = [(row.find("th").text_content(), row.find("td").text_content(),
                               row.find("td").get("data-published-literal")) for row in card.xpath('.//tbody/tr')]
                    expected = [(row["published_name"], "–" if row["result"]["kind"] == "source_dash"
                                 else row["result"]["literal"], row["result"]["literal"]) for row in table["rows"]]
                    self.assertEqual(actual, expected)
                    self.assertEqual(card.get("id"), "source-table-" + notice)
                    self.assertIsNotNone(card.find("summary"))
                    self.assertTrue(card.xpath('.//th[@scope="row"]'))
                    self.assertIn(table["source"]["pdf_url"] + "#page=" + str(table["source"]["pdf_page"]),
                                  card.xpath('.//a/@href'))
                    self.assertIn("SOURCE UNIQUEMENT" if language == "fr" else "SOURCE ONLY", card.text_content())
        self.assertEqual(self.record["tables"]["10327"]["table"]["rows"][0]["result"]["kind"], "source_dash")
        for notice, names in (("10264", {"sebastien-bonnal"}),
                              ("10260", {"nathalie-arthaud", "karim-bouamrane"})):
            self.assertEqual({r["identity_id"] for r in self.record["tables"][notice]["table"]["rows"]
                              if r["result"]["literal"] == "<1%"}, names)

    def test_numerical_cards_counts_metadata_and_entire_remaining_page_are_unchanged(self):
        shell = pages.load_shell_templates(ROOT)
        for index, wave in enumerate(self.explorer["waves"]):
            table = self.source.source_table_for_wave(wave, self.record)
            for language in ("fr", "en"):
                relative = pages.page_file_from_url(wave[f"page_path_{language}"])
                if table is None:
                    self.assertEqual(self.artifacts[relative].decode(), (ROOT / relative).read_text(encoding="utf-8"))
                    continue
                original = pages.render_page(wave, language=language, wave_count=len(self.explorer["waves"]),
                    header=shell[language]["header"], footer=shell[language]["footer"],
                    favicon=pages._site_favicon_link(ROOT), og_image_url=pages._site_og_image_url(ROOT),
                    related_waves=pages.nearby_waves(self.explorer["waves"], index, limit=6)).decode()
                added = "\n        " + self.source.render_source_card(table, language)
                rendered = self.artifacts[relative].decode()
                self.assertEqual(rendered.replace(added, "", 1), original)
                self.assertGreater(rendered.index('id="source-table-'), rendered.index(f'id="scenario-{wave["scenario_count"]}"'))
        self.assertEqual(self.manifest, pages.manifest_payload(self.explorer["waves"]))

    def test_presentation_cannot_mutate_numeric_inputs_or_explorer(self):
        original = copy.deepcopy(self.explorer)
        numeric = {name: (ROOT / name).read_bytes() for name in ("polls.json", "second_round_polls.json", "poll_explorer.json")}
        pages.expected_artifacts(self.explorer, template_root=ROOT)
        for language in ("fr", "en"):
            pages.render_source_evidence_page(language=language, template_root=ROOT)
        self.assertEqual(self.explorer, original)
        self.assertEqual(numeric, {name: (ROOT / name).read_bytes() for name in numeric})

    def test_bonnal_is_unregistered_noindex_evidence_with_exact_sample_bases(self):
        from lxml import html
        self.assertFalse(any("preview" in str(path) or "10264" in str(path) for path in self.artifacts))
        for name in ("route_registry.json", "poll_pages_manifest.json", "sitemap.xml", "sitemap-polls.xml"):
            path = ROOT / name
            if path.exists():
                self.assertNotIn("/preview/evidence/10264/", path.read_text(encoding="utf-8"))
        for language in ("fr", "en"):
            document = pages.render_source_evidence_page(language=language, template_root=ROOT).decode()
            tree = html.fromstring(document)
            self.assertEqual(tree.get("lang"), language)
            self.assertFalse(tree.xpath('//link[@rel="canonical"] | //script[@type="application/ld+json"]'))
            self.assertEqual(tree.xpath('//meta[@name="robots"]/@content'), ["noindex,nofollow"])
            self.assertFalse(tree.xpath('//details[starts-with(@id,"scenario-")]'))
            self.assertIn("1 034" if language == "fr" else "1,034", document)
            self.assertIn("951", document)
            self.assertIn("700", document)
            self.assertIn("2–4 septembre 2026" if language == "fr" else "2–4 September 2026", document)

    def test_standalone_and_normal_builds_are_reproducible_without_preview_dependencies(self):
        again, manifest = pages.expected_artifacts(self.explorer, template_root=ROOT)
        self.assertEqual((again, manifest), (self.artifacts, self.manifest))
        for language in ("fr", "en"):
            self.assertEqual(pages.render_source_evidence_page(language=language, template_root=ROOT),
                             pages.render_source_evidence_page(language=language, template_root=ROOT))
        import subprocess
        import sys
        # -S proves normal rendering needs only the standard library, in a fresh
        # process rather than depending on which other tests were collected.
        code = (f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
                "import build_poll_pages as p; "
                "p.render_source_evidence_page(language='en'); "
                "assert 'preview_exceptional_source_tables' not in sys.modules; "
                "assert 'poll_migration' not in sys.modules")
        result = subprocess.run([sys.executable, "-B", "-S", "-c", code],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class CnewsSourcePublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = source.load_source_tables()
        cls.review = json.loads((ROOT / 'fr27_reviewed_scenario_manifest.json').read_text(encoding='utf-8'))
        cls.explorer = json.loads((ROOT / 'poll_explorer.json').read_text(encoding='utf-8'))

    def test_reviewed_transcriptions_and_candidate_identities_are_exact(self):
        for notice in ('10319', '10333'):
            survey = next(s for s in self.review['surveys'] if s['document_id'] == notice)
            scenario = next(s for s in survey['scenarios'] if s['round'] == 'first_round')
            table = self.record['tables'][notice]['table']
            self.assertEqual(table['rows'], scenario['rows'])
            self.assertEqual(len(table['rows']), 13)
            self.assertEqual(len({r['identity_id'] for r in table['rows']}), 13)
            self.assertEqual(table['source']['published_column'], scenario['published_column'])
            self.assertEqual(table['reviewed_scenario_id'], scenario['scenario_id'])
            self.assertEqual(table['commissioner'], 'CNEWS')
            self.assertEqual(table['numerical_comparisons'], 'excluded_whole_table')

    def test_all_three_strict_bounds_have_no_exact_numeric_value(self):
        bounds = [(n, r['identity_id'], r['result']) for n in ('10319', '10333')
                  for r in self.record['tables'][n]['table']['rows'] if r['result']['kind'] != 'exact']
        self.assertEqual([(n, identity) for n, identity, _ in bounds], [
            ('10319', 'karim-bouamrane'), ('10333', 'nathalie-arthaud'), ('10333', 'karim-bouamrane')])
        for _, _, result in bounds:
            self.assertEqual(result, {'kind': 'strict_upper_bound', 'literal': '<1%', 'upper_percent': 1.0})
            self.assertNotIn('percent', result)

    def test_authentication_of_external_pdf_cache_is_fail_closed(self):
        # Controlled document bytes, never copies or substitutes for originals.
        record = copy.deepcopy(self.record)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            for n in record['standalone_pages']:
                raw = ('controlled source ' + n).encode()
                (cache / (n + '.pdf')).write_bytes(raw)
                record['tables'][n]['table']['source']['pdf_sha256'] = hashlib.sha256(raw).hexdigest()
            with patch.object(source, 'load_source_tables', return_value=record):
                self.assertEqual(len(source.authenticate_source_documents(cache)), 2)
                (cache / '10319.pdf').write_bytes(b'changed source')
                with self.assertRaisesRegex(ValueError, 'document changed: 10319'):
                    source.authenticate_source_documents(cache)
                (cache / '10319.pdf').unlink()
                with self.assertRaises(FileNotFoundError):
                    source.authenticate_source_documents(cache)

    def test_published_row_source_population_or_route_changes_require_new_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tables.json'
            for change in ('literal', 'score', 'candidate', 'base', 'source', 'column', 'commissioner', 'route'):
                with self.subTest(change=change):
                    record = copy.deepcopy(self.record)
                    table = record['tables']['10333']['table']
                    if change == 'literal': table['rows'][0]['result']['literal'] = '0%'
                    if change == 'score': table['rows'][1]['result']['percent'] = 17
                    if change == 'candidate': table['rows'].pop()
                    if change == 'base': table['respondent_bases'][0]['count'] = 731
                    if change == 'source': table['source']['pdf_sha256'] = '0' * 64
                    if change == 'column': table['source']['published_column'] = 'Brut'
                    if change == 'commissioner': table['commissioner'] = 'Les Échos / Radio Classique'
                    if change == 'route': record['standalone_pages']['10264'] = record['standalone_pages']['10333']
                    path.write_text(json.dumps(record), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'evidence changed'):
                        source.load_source_tables(path)
                    if change != 'route':
                        # Changing only the collection pin cannot bypass the individual row pin.
                        with patch.object(source, 'RECORD_SHA256', source.digest(record)):
                            with self.assertRaisesRegex(ValueError, 'source table changed'):
                                source.load_source_tables(path)

    def test_individual_prior_records_keep_their_approved_hashes(self):
        expected = {'10327': '20f19e4d8d2200408f23700bab1fe7108ace220152e81ad15f8d5564ecd00970',
                    '10260': '535cb08075a8c3bb1eb9b8d9ddd0178b7296308872490e546e03c19250369788',
                    '10264': '90fd17b6433f8af12e7fa0cd4914b142e91148e8da8d5e4d5c97e9f1feaacc70'}
        # Bonnal's original pin is also authenticated by the collection's prior hash.
        previous = {k: v for k, v in self.record.items() if k not in ('extension_review', 'standalone_pages')}
        previous['tables'] = {k: v for k, v in previous['tables'].items() if k in expected}
        self.assertEqual(source.digest(previous), '4ede22b9d7973257cedd2f76ff0edeb137ff43d8e67ca946800d7251d76eb526')
        for n in expected:
            self.assertEqual(self.record['tables'][n]['record_sha256'], expected[n])

    def test_bases_population_nonexpression_and_weighting_are_distinct(self):
        for n, expected in [('10319', [1043, 978, 731]), ('10333', [1033, 973, 731, 680])]:
            table = self.record['tables'][n]['table']
            self.assertEqual([b['count'] for b in table['respondent_bases']], expected)
            self.assertEqual(table['methodology']['non_expression']['population_scope'], 'all_respondents')
            self.assertEqual(table['methodology']['non_expression']['result']['literal'], '15%' if n == '10319' else '13%')
            self.assertEqual(table['methodology']['expressed_base_status'], 'unverified' if n == '10319' else 'published')
            self.assertEqual(table['questionnaire_other_options']['source_page'], 5)
            self.assertFalse(table['questionnaire_other_options']['separate_candidate_scores'])

    def test_four_pages_are_literal_bilingual_canonical_and_documentary(self):
        for page in source.published_source_pages():
            n = page['notice_id']
            table = self.record['tables'][n]['table']
            for language in ('fr', 'en'):
                rendered = pages.render_published_source_page(n, language=language)
                tree = html.fromstring(rendered)
                self.assertEqual(tree.get('lang'), language)
                canonical = 'https://france2027.app' + page[f'page_path_{language}']
                self.assertEqual(tree.xpath('//link[@rel="canonical"]/@href'), [canonical])
                self.assertEqual(dict(zip(tree.xpath('//link[@rel="alternate"]/@hreflang'), tree.xpath('//link[@rel="alternate"]/@href'))),
                                 {'fr': 'https://france2027.app' + page['page_path_fr'], 'en': 'https://france2027.app' + page['page_path_en'], 'x-default': 'https://france2027.app' + page['page_path_fr']})
                rows = tree.xpath('//tbody/tr')
                self.assertEqual([(r.find('th').text_content(), r.find('td').text_content()) for r in rows],
                                 [(r['published_name'], r['result']['literal']) for r in table['rows']])
                self.assertEqual(len(rows), 13)
                self.assertEqual(set(tree.xpath('//@data-coverage-state')), {'SOURCE_DOCUMENT_VERIFIED', 'DOCUMENTARY_COVERAGE_PUBLISHED', 'NUMERICAL_OBSERVATION_ABSENT'})
                self.assertFalse(tree.xpath('//details[starts-with(@id,"scenario-")] | //script[@type="application/ld+json"]'))
                self.assertIn(table['source']['pdf_url'] + '#page=12', tree.xpath('//a/@href'))
                self.assertEqual(rendered, pages.render_published_source_page(n, language=language))
                self.assertIn('candidate-app-hud', rendered.decode())
                self.assertIn('candidate-masthead', rendered.decode())

    def test_bonnal_has_no_public_renderer_or_routes(self):
        with self.assertRaisesRegex(pages.PollPageError, 'no reviewed public route'):
            pages.render_published_source_page('10264', language='fr')
        with self.assertRaises(pages.PollPageError):
            pages.render_published_source_page('10319', language='es')
        self.assertEqual({p['notice_id'] for p in source.published_source_pages()}, {'10319', '10333'})

    def test_manifest_routes_sitemap_and_hub_links_agree(self):
        manifest = json.loads((ROOT / pages.MANIFEST_NAME).read_text(encoding='utf-8'))
        registry = json.loads((ROOT / 'route_registry.json').read_text(encoding='utf-8'))
        documentary = [r for r in registry['routes'] if r['kind'] == 'poll-source-evidence']
        self.assertEqual(len(documentary), 4)
        self.assertEqual(manifest['source_page_count'], 4)
        self.assertEqual(manifest['wave_count'], len(self.explorer['waves']))
        self.assertEqual(manifest['page_count'], 2 * len(self.explorer['waves']))
        expected = {p[f'page_path_{lang}'] for p in source.published_source_pages() for lang in ('fr', 'en')}
        self.assertEqual({r['path'] for r in documentary}, expected)
        self.assertFalse(expected & {w[k] for w in self.explorer['waves'] for k in ('page_path_fr', 'page_path_en')})
        xml = sitemaps.expected_artifacts(registry)
        self.assertEqual(sum(v.count(('https://france2027.app' + path + '</loc>').encode()) for path in expected for v in xml.values()), 4)
        for language in ('fr', 'en'):
            tree = html.fromstring(hubs.HUBS[language].read_text(encoding='utf-8'))
            links = tree.xpath('//*[@id="source-evidence"]//a/@href')
            self.assertEqual(set(links), {p[f'page_path_{language}'] for p in source.published_source_pages()})
            self.assertFalse(tree.xpath('//*[@data-static-poll-directory]//a[contains(@href,"/documents/")]'))
            once = hubs.expected_document(hubs.HUBS[language], waves=self.explorer['waves'], language=language)
            self.assertEqual(once, hubs.HUBS[language].read_text(encoding='utf-8'))

    def test_reject_fabricated_manifest_route(self):
        manifest = pages.manifest_payload(self.explorer['waves'])
        manifest['source_pages'][0]['page_path_fr'] = '/sondages/fabricated/'
        with self.assertRaisesRegex(routes.RouteRegistryError, 'Unreviewed'):
            routes.discover_routes(manifest, json.loads((ROOT / 'candidate_candidacy_status.json').read_text(encoding='utf-8')), root=ROOT)

    def test_no_analytics_or_ingestion_dependency_on_source_tables(self):
        for name in ('fetch_polls.py', 'poll_contract.py', 'poll_migration.py', 'build_poll_explorer.py',
                     'build_candidate_signals.py', 'assets/polling-lab.js'):
            self.assertNotIn('poll_source_tables', (ROOT / name).read_text(encoding='utf-8'))
        for page in source.published_source_pages():
            self.assertNotIn(page['source_table_id'], json.dumps(self.explorer))

    def test_unchanged_numeric_page_bytes_survive_windows_regeneration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.html'
            original = b'<html>\r\nunchanged numerical page\r\n</html>\r\n'
            path.write_bytes(original)
            pages._atomic_write(path, original.replace(b'\r\n', b'\n'))
            self.assertEqual(path.read_bytes(), original)
            pages._atomic_write(path, b'<html>reviewed change</html>\n')
            self.assertEqual(path.read_bytes(), b'<html>reviewed change</html>\n')


if __name__ == "__main__":
    unittest.main()
