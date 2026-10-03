from __future__ import annotations

import hashlib
import inspect
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import build_route_registry as routes
import build_sitemaps as sitemaps
from candidate_page_contract import project_candidate_route_index


ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "route_registry.json"
POLL_MANIFEST = ROOT / "poll_pages_manifest.json"
CANDIDATE_REGISTRY = ROOT / "candidate_candidacy_status.json"
ISSUE_MANIFEST = ROOT / "issue_pages_manifest.json"
AGENDA_MANIFEST = ROOT / "agenda_pages_manifest.json"

SM = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}


class RouteRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            REGISTRY.read_text(encoding="utf-8")
        )
        cls.manifest = json.loads(
            POLL_MANIFEST.read_text(encoding="utf-8")
        )
        cls.candidate_registry = json.loads(
            CANDIDATE_REGISTRY.read_text(encoding="utf-8")
        )
        cls.issue_manifest = json.loads(
            ISSUE_MANIFEST.read_text(encoding="utf-8")
        )
        cls.agenda_manifest = json.loads(
            AGENDA_MANIFEST.read_text(encoding="utf-8")
        )
        cls.candidate_index = project_candidate_route_index(
            cls.candidate_registry,
            ROOT,
        )

    def test_registry_matches_manifest_route_census(self):
        wave_count = self.manifest["wave_count"]
        page_count = self.manifest["page_count"]
        pages = self.manifest["pages"]

        self.assertEqual(len(pages), wave_count)
        self.assertEqual(page_count, wave_count * 2)

        expected_poll_routes = 2 + page_count
        expected_candidate_routes = (
            2 + 2 * self.candidate_index["counts"]["published"]
        )
        expected_issue_routes = self.issue_manifest["page_count"]
        expected_agenda_routes = self.agenda_manifest["page_count"]
        self.assertEqual(
            expected_agenda_routes,
            4 + 4 * self.agenda_manifest["public_topic_count"],
        )
        self.assertEqual(expected_agenda_routes, 28)
        expected_total_routes = (
            2
            + expected_candidate_routes
            + expected_poll_routes
            + expected_issue_routes
            + expected_agenda_routes
        )

        self.assertEqual(
            self.registry["route_count"],
            expected_total_routes,
        )

        self.assertEqual(
            self.registry["family_counts"],
            {
                "agenda": expected_agenda_routes,
                "core": 2,
                "candidates": expected_candidate_routes,
                "issues": expected_issue_routes,
                "polls": expected_poll_routes,
            },
        )


    def test_new_issue_adds_current_and_history_language_pairs(self):
        poll_manifest = json.loads(
            (ROOT / "poll_pages_manifest.json")
            .read_text(encoding="utf-8")
        )

        empty_issue_manifest = {
            "schema_version": "1.0",
            "issue_count": 0,
            "page_count": 4,
            "hubs": {
                "fr": "/enjeux/",
                "en": "/en/issues/",
            },
            "history_hubs": {
                "fr": "/enjeux/historique/",
                "en": "/en/issues/history/",
            },
            "pages": [],
        }

        one_issue_manifest = {
            **empty_issue_manifest,
            "issue_count": 1,
            "page_count": 8,
            "pages": [
                {
                    "issue_id": "security_justice",
                    "lifecycle": "current",
                    "page_path_fr": (
                        "/enjeux/securite-justice/"
                    ),
                    "page_path_en": (
                        "/en/issues/security-justice/"
                    ),
                    "history_page_path_fr": (
                        "/enjeux/historique/"
                        "securite-justice/"
                    ),
                    "history_page_path_en": (
                        "/en/issues/history/"
                        "security-justice/"
                    ),
                }
            ],
        }

        before = routes.discover_routes(
            poll_manifest,
            root=ROOT,
            issue_manifest=empty_issue_manifest,
        )

        after = routes.discover_routes(
            poll_manifest,
            root=ROOT,
            issue_manifest=one_issue_manifest,
        )

        self.assertEqual(
            len(after) - len(before),
            4,
        )


    def test_new_poll_wave_adds_exactly_one_language_pair(self):
        empty_manifest = {"pages": []}
        one_wave_manifest = {
            "pages": [
                {
                    "wave_id": "wave-regression",
                    "page_path_fr": "/sondages/regression/",
                    "page_path_en": "/en/sondages/regression/",
                }
            ]
        }

        before = routes.discover_routes(empty_manifest)
        after = routes.discover_routes(one_wave_manifest)

        self.assertEqual(len(after) - len(before), 2)

        added = [
            route
            for route in after
            if route["route_key"] == "poll-wave:wave-regression"
        ]

        self.assertEqual(len(added), 2)
        self.assertEqual(
            {route["language"] for route in added},
            {"fr", "en"},
        )

    def test_every_registered_source_file_exists(self):
        for route in self.registry["routes"]:
            with self.subTest(
                route_id=route["route_id"]
            ):
                self.assertTrue(
                    (ROOT / route["source_file"]).exists()
                )

    def test_canonical_urls_are_unique(self):
        urls = [
            route["canonical_url"]
            for route in self.registry["routes"]
        ]

        self.assertEqual(
            len(urls),
            len(set(urls)),
        )

    def test_every_route_has_reciprocal_language_pair(self):
        by_key = {}

        for route in self.registry["routes"]:
            by_key.setdefault(
                route["route_key"],
                {},
            )[route["language"]] = route

        for route_key, pair in by_key.items():
            with self.subTest(route_key=route_key):
                self.assertEqual(
                    set(pair),
                    {"fr", "en"},
                )

                french = pair["fr"]
                english = pair["en"]

                self.assertEqual(
                    french["alternate_url_fr"],
                    french["canonical_url"],
                )

                self.assertEqual(
                    english["alternate_url_en"],
                    english["canonical_url"],
                )

                self.assertEqual(
                    french["alternate_url_en"],
                    english["canonical_url"],
                )

                self.assertEqual(
                    english["alternate_url_fr"],
                    french["canonical_url"],
                )

                self.assertEqual(
                    french["x_default_url"],
                    french["canonical_url"],
                )

                self.assertEqual(
                    english["x_default_url"],
                    french["canonical_url"],
                )

    def test_poll_manifest_routes_are_all_registered(self):
        canonicals = {
            route["canonical_url"]
            for route in self.registry["routes"]
        }

        for page in self.manifest["pages"]:
            self.assertIn(
                "https://france2027.app"
                + page["page_path_fr"],
                canonicals,
            )
            self.assertIn(
                "https://france2027.app"
                + page["page_path_en"],
                canonicals,
            )

    def test_candidate_lifecycle_routes_are_all_registered(self):
        candidate_routes = [
            route
            for route in self.registry["routes"]
            if route["family"] == "candidates"
            and route["kind"] != "hub"
        ]
        expected = {
            f"https://france2027.app{path}"
            for candidate in self.candidate_index["candidates"]
            for path in candidate["routes"].values()
        }

        self.assertEqual(
            {route["canonical_url"] for route in candidate_routes},
            expected,
        )
        self.assertEqual(
            len(candidate_routes),
            2 * self.candidate_index["counts"]["published"],
        )


    def test_issue_manifest_is_sole_issue_membership_authority(self):
        registry = json.loads(
            (ROOT / "route_registry.json")
            .read_text(encoding="utf-8")
        )

        manifest = json.loads(
            (ROOT / "issue_pages_manifest.json")
            .read_text(encoding="utf-8")
        )

        registered = {
            route["canonical_url"]
            for route in registry["routes"]
            if route["family"] == "issues"
        }

        expected = {
            "https://france2027.app/enjeux/",
            "https://france2027.app/en/issues/",
            (
                "https://france2027.app"
                "/enjeux/historique/"
            ),
            (
                "https://france2027.app"
                "/en/issues/history/"
            ),
        }

        expected.update(
            f"https://france2027.app{path}"
            for page in manifest["pages"]
            for path in (
                page["page_path_fr"],
                page["page_path_en"],
                page[
                    "history_page_path_fr"
                ],
                page[
                    "history_page_path_en"
                ],
            )
        )

        self.assertEqual(
            registered,
            expected,
        )

    def test_agenda_manifest_is_sole_agenda_membership_authority(self):
        registered = {
            route["canonical_url"]
            for route in self.registry["routes"]
            if route["family"] == "agenda"
        }
        expected = {
            f"https://france2027.app{path}"
            for path in (
                *self.agenda_manifest["hubs"].values(),
                *self.agenda_manifest["history_hubs"].values(),
            )
        }
        expected.update(
            f"https://france2027.app{path}"
            for page in self.agenda_manifest["pages"]
            for path in (
                page["page_path_fr"],
                page["page_path_en"],
                page["history_page_path_fr"],
                page["history_page_path_en"],
            )
        )

        self.assertEqual(registered, expected)
        self.assertEqual(len(registered), 28)

    def test_agenda_route_keys_kinds_and_entities_are_correct(self):
        agenda_routes = [
            route
            for route in self.registry["routes"]
            if route["family"] == "agenda"
        ]
        expected = {
            "agenda-lab": ("hub", "agenda-lab"),
            "agenda-history": ("history-hub", "agenda-history"),
        }
        for page in self.agenda_manifest["pages"]:
            topic_id = page["topic_id"]
            expected[f"agenda:{topic_id}"] = (
                "agenda-detail",
                topic_id,
            )
            expected[f"agenda-history:{topic_id}"] = (
                "agenda-history-detail",
                topic_id,
            )

        by_key = {}
        for route in agenda_routes:
            by_key.setdefault(route["route_key"], []).append(route)

        self.assertEqual(set(by_key), set(expected))
        for route_key, pair in by_key.items():
            with self.subTest(route_key=route_key):
                self.assertEqual(len(pair), 2)
                self.assertEqual(
                    {route["language"] for route in pair},
                    {"fr", "en"},
                )
                self.assertEqual(
                    {(route["kind"], route["entity_id"]) for route in pair},
                    {expected[route_key]},
                )


    def test_titles_and_descriptions_are_present(self):
        for route in self.registry["routes"]:
            with self.subTest(
                route_id=route["route_id"]
            ):
                self.assertTrue(
                    route["title"].strip()
                )
                self.assertTrue(
                    route["description"].strip()
                )

    def test_lastmod_is_iso_date(self):
        for route in self.registry["routes"]:
            self.assertRegex(
                route["lastmod"],
                r"^\d{4}-\d{2}-\d{2}$",
            )

    def test_registry_check_mode_is_clean(self):
        self.assertEqual(
            routes.check_registry(
                root=ROOT,
                poll_manifest_path=POLL_MANIFEST,
                registry_path=REGISTRY,
            ),
            [],
        )

    def test_semantic_hash_ignores_hud_poll_counter(self):
        source = (
            '<strong id="fr27-hud-polls-value">'
            '65'
            '</strong>'
        ).encode("utf-8")

        changed = (
            '<strong id="fr27-hud-polls-value">'
            '66'
            '</strong>'
        ).encode("utf-8")

        first = hashlib.sha256(
            routes._semantic_html_bytes(source)
        ).hexdigest()

        second = hashlib.sha256(
            routes._semantic_html_bytes(changed)
        ).hexdigest()

        self.assertEqual(first, second)

    def test_semantic_hash_ignores_og_cover_cache_version(self):
        first_html = (
            '<meta property="og:image" '
            'content="https://france2027.app/assets/'
            'og-cover.png?v=20260923-090129">'
        ).encode("utf-8")

        second_html = (
            '<meta property="og:image" '
            'content="https://france2027.app/assets/'
            'og-cover.png?v=20270101-120000">'
        ).encode("utf-8")

        first = hashlib.sha256(
            routes._semantic_html_bytes(first_html)
        ).hexdigest()

        second = hashlib.sha256(
            routes._semantic_html_bytes(second_html)
        ).hexdigest()

        self.assertEqual(first, second)

    def test_candidate_detail_hash_includes_published_projection(self):
        candidate_id = self.candidate_index["candidates"][0][
            "candidate_id"
        ]
        source = ROOT / "candidates" / candidate_id / "index.html"

        with mock.patch.object(
            routes,
            "_semantic_json_bytes",
            side_effect=(b"projection-one", b"projection-two"),
        ):
            first = routes._candidate_detail_content_hash(
                root=ROOT,
                source_path=source,
                candidate_id=candidate_id,
            )
            second = routes._candidate_detail_content_hash(
                root=ROOT,
                source_path=source,
                candidate_id=candidate_id,
            )

        self.assertNotEqual(first, second)

    def test_candidate_detail_hash_excludes_css_dependencies(self):
        implementation = inspect.getsource(
            routes._candidate_detail_content_hash
        )

        self.assertNotIn(".css", implementation)
        self.assertNotIn("candidate-page.css", implementation)


    def test_unchanged_content_preserves_lastmod(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            registry = temp / "registry.json"

            original = routes.build_registry(
                root=ROOT,
                poll_manifest_path=POLL_MANIFEST,
                existing_registry_path=registry,
                effective_date="2026-09-23",
            )

            registry.write_bytes(
                routes.serialize_registry(original)
            )

            rebuilt = routes.build_registry(
                root=ROOT,
                poll_manifest_path=POLL_MANIFEST,
                existing_registry_path=registry,
                effective_date="2027-01-01",
            )

            self.assertEqual(
                [
                    item["lastmod"]
                    for item in original["routes"]
                ],
                [
                    item["lastmod"]
                    for item in rebuilt["routes"]
                ],
            )


class SitemapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            REGISTRY.read_text(encoding="utf-8")
        )
        cls.families = sorted(cls.registry["family_counts"])

    def test_sitemap_index_lists_current_families(self):
        tree = ET.parse(ROOT / "sitemap.xml")

        urls = [
            node.text
            for node in tree.findall(
                "sm:sitemap/sm:loc",
                SM,
            )
        ]

        self.assertEqual(
            urls,
            [
                f"https://france2027.app/sitemap-{family}.xml"
                for family in self.families
            ],
        )

    def test_agenda_sitemap_matches_agenda_registry_routes(self):
        agenda_path = ROOT / "sitemap-agenda.xml"
        self.assertTrue(agenda_path.exists())

        index = ET.parse(ROOT / "sitemap.xml")
        agenda_index_url = "https://france2027.app/sitemap-agenda.xml"
        self.assertEqual(
            [
                node.text
                for node in index.findall("sm:sitemap/sm:loc", SM)
            ].count(agenda_index_url),
            1,
        )

        tree = ET.parse(agenda_path)
        nodes = tree.findall("sm:url", SM)
        canonicals = {
            node.find("sm:loc", SM).text
            for node in nodes
        }
        expected = {
            route["canonical_url"]
            for route in self.registry["routes"]
            if route["family"] == "agenda"
        }
        self.assertEqual(canonicals, expected)
        self.assertEqual(len(nodes), 28)

        for node in nodes:
            alternates = node.findall("xhtml:link", SM)
            self.assertEqual(
                {link.attrib["hreflang"] for link in alternates},
                {"fr", "en", "x-default"},
            )

    def test_every_canonical_url_occurs_once_in_family_sitemaps(self):
        discovered = []

        for family in self.families:
            tree = ET.parse(
                ROOT / f"sitemap-{family}.xml"
            )

            discovered.extend(
                node.text
                for node in tree.findall(
                    "sm:url/sm:loc",
                    SM,
                )
            )

        expected = {
            route["canonical_url"]
            for route in self.registry["routes"]
        }

        self.assertEqual(
            len(discovered),
            len(expected),
        )

        self.assertEqual(
            set(discovered),
            expected,
        )

    def test_family_sitemaps_include_lastmod(self):
        for family in self.families:
            tree = ET.parse(
                ROOT / f"sitemap-{family}.xml"
            )

            for node in tree.findall(
                "sm:url",
                SM,
            ):
                lastmod = node.find(
                    "sm:lastmod",
                    SM,
                )

                self.assertIsNotNone(lastmod)
                self.assertRegex(
                    lastmod.text or "",
                    r"^\d{4}-\d{2}-\d{2}$",
                )

    def test_family_sitemaps_include_hreflang_triplet(self):
        for family in self.families:
            tree = ET.parse(
                ROOT / f"sitemap-{family}.xml"
            )

            for node in tree.findall(
                "sm:url",
                SM,
            ):
                alternates = node.findall(
                    "xhtml:link",
                    SM,
                )

                values = {
                    item.attrib.get("hreflang")
                    for item in alternates
                }

                self.assertEqual(
                    values,
                    {"fr", "en", "x-default"},
                )

    def test_sitemap_builder_check_is_clean(self):
        self.assertEqual(
            sitemaps.check_from_paths(
                REGISTRY,
                output_root=ROOT,
            ),
            [],
        )

    def test_no_sitemap_url_uses_www_or_lang_query(self):
        for family in self.families:
            tree = ET.parse(
                ROOT / f"sitemap-{family}.xml"
            )

            for node in tree.findall(
                "sm:url/sm:loc",
                SM,
            ):
                value = node.text or ""
                self.assertNotIn("www.", value)
                self.assertNotIn("?lang=", value)


import unittest as _hub_hash_unittest


class PollingHubDependencyHashTests(
    _hub_hash_unittest.TestCase
):
    def _fixture(self):
        import json
        import tempfile
        from pathlib import Path

        import build_route_registry as registry

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        root = Path(temporary.name)

        (root / "assets").mkdir(
            parents=True,
            exist_ok=True,
        )

        (root / "sondages").mkdir(
            parents=True,
            exist_ok=True,
        )

        source = (
            root
            / "sondages"
            / "index.html"
        )

        source.write_text(
            """
<!doctype html>
<html>
<body>
<strong id="fr27-hud-polls-value">65</strong>
<strong id="fr27-hud-domains-value">210</strong>
<main>Polling Lab</main>
</body>
</html>
""".strip()
            + "\n",
            encoding="utf-8",
        )

        explorer = {
            "schema_version": "1.0",
            "data_as_of": "2026-09-10",
            "metrics": {
                "wave_count": 65,
            },
            "candidates": [],
            "institutes": [],
            "waves": [],
        }

        (root / "poll_explorer.json").write_text(
            json.dumps(
                explorer,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        (
            root
            / "assets"
            / "polling-lab.js"
        ).write_text(
            'const pollingLabVersion = "one";\n',
            encoding="utf-8",
        )

        (
            root
            / "assets"
            / "polling-lab.css"
        ).write_text(
            ".polling-lab { display: block; }\n",
            encoding="utf-8",
        )

        hub_route = {
            "family": "polls",
            "kind": "hub",
        }

        wave_route = {
            "family": "polls",
            "kind": "poll-wave",
        }

        return (
            registry,
            root,
            source,
            hub_route,
            wave_route,
        )

    def test_hub_hash_ignores_hud_counts_and_css(self):
        registry, root, source, hub_route, _ = (
            self._fixture()
        )

        baseline = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        html = source.read_text(
            encoding="utf-8"
        )

        html = html.replace(
            ">65</strong>",
            ">999</strong>",
        ).replace(
            ">210</strong>",
            ">777</strong>",
        )

        source.write_text(
            html,
            encoding="utf-8",
        )

        (
            root
            / "assets"
            / "polling-lab.css"
        ).write_text(
            ".polling-lab { display: grid; }\n",
            encoding="utf-8",
        )

        changed = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        self.assertEqual(
            baseline,
            changed,
        )

    def test_hub_hash_canonicalizes_explorer_json_formatting(self):
        import json

        registry, root, source, hub_route, _ = (
            self._fixture()
        )

        baseline = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        explorer_path = (
            root
            / "poll_explorer.json"
        )

        payload = json.loads(
            explorer_path.read_text(
                encoding="utf-8"
            )
        )

        explorer_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        changed = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        self.assertEqual(
            baseline,
            changed,
        )

    def test_hub_hash_changes_when_poll_explorer_changes(self):
        import json

        registry, root, source, hub_route, _ = (
            self._fixture()
        )

        baseline = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        explorer_path = (
            root
            / "poll_explorer.json"
        )

        payload = json.loads(
            explorer_path.read_text(
                encoding="utf-8"
            )
        )

        payload["metrics"]["wave_count"] = 66

        explorer_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        changed = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        self.assertNotEqual(
            baseline,
            changed,
        )

    def test_hub_hash_changes_when_polling_lab_runtime_changes(self):
        registry, root, source, hub_route, _ = (
            self._fixture()
        )

        baseline = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        runtime = (
            root
            / "assets"
            / "polling-lab.js"
        )

        runtime.write_text(
            'const pollingLabVersion = "two";\n',
            encoding="utf-8",
        )

        changed = registry._route_content_hash(
            route=hub_route,
            root=root,
            source_path=source,
        )

        self.assertNotEqual(
            baseline,
            changed,
        )

    def test_poll_wave_hash_ignores_hub_dependencies(self):
        import json

        registry, root, source, _, wave_route = (
            self._fixture()
        )

        baseline = registry._route_content_hash(
            route=wave_route,
            root=root,
            source_path=source,
        )

        explorer_path = (
            root
            / "poll_explorer.json"
        )

        payload = json.loads(
            explorer_path.read_text(
                encoding="utf-8"
            )
        )

        payload["metrics"]["wave_count"] = 999

        explorer_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        (
            root
            / "assets"
            / "polling-lab.js"
        ).write_text(
            'const pollingLabVersion = "changed";\n',
            encoding="utf-8",
        )

        changed = registry._route_content_hash(
            route=wave_route,
            root=root,
            source_path=source,
        )

        self.assertEqual(
            baseline,
            changed,
        )


if __name__ == "__main__":
    unittest.main()
