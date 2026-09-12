"""Search-engine foundation contracts for FR27."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from build_search_entrypoints import build_english_entrypoint


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
ENGLISH_INDEX = ROOT / "en" / "index.html"
ROBOTS = ROOT / "robots.txt"
SITEMAP = ROOT / "sitemap.xml"

ROOT_URL = "https://france2027.app/"
ENGLISH_URL = "https://france2027.app/en/"

FRENCH_TITLE = "France 2027 Signal Lab — Signaux électoraux sourcés"
ENGLISH_TITLE = "France 2027 Signal Lab — Source-Linked Election Signals"

FRENCH_DESCRIPTION = (
    "Sondages sourcés, actualité électorale, couverture des candidats et "
    "vérifications pour la présidentielle française de 2027. "
    "Aucune moyenne, aucune prévision, aucun conseil de vote."
)
ENGLISH_DESCRIPTION = (
    "Source-linked polling, election news, candidate coverage and fact checks "
    "for France's 2027 presidential race. "
    "No averages, no forecast, no voting advice."
)


class SearchFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_html = INDEX.read_text(encoding="utf-8")
        cls.english_html = ENGLISH_INDEX.read_text(encoding="utf-8")

    def test_root_is_static_french_canonical(self):
        self.assertIn(
            '<html lang="fr" data-site-root="./"',
            self.root_html,
        )
        self.assertNotIn('<base href="/">', self.root_html)
        self.assertIn(
            f'<link rel="canonical" href="{ROOT_URL}">',
            self.root_html,
        )
        self.assertIn(
            f'<meta property="og:url" content="{ROOT_URL}">',
            self.root_html,
        )
        self.assertIn(
            f"<title>{FRENCH_TITLE}</title>",
            self.root_html,
        )
        self.assertIn(
            f'<meta name="description" content="{FRENCH_DESCRIPTION}">',
            self.root_html,
        )

    def test_english_entrypoint_is_static_english_canonical(self):
        self.assertIn(
            '<html lang="en" data-site-root="/"',
            self.english_html,
        )
        self.assertEqual(
            self.english_html.count('<base href="/">'),
            1,
        )
        self.assertIn(
            f'<link rel="canonical" href="{ENGLISH_URL}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta property="og:url" content="{ENGLISH_URL}">',
            self.english_html,
        )
        self.assertIn(
            f"<title>{ENGLISH_TITLE}</title>",
            self.english_html,
        )
        self.assertIn(
            f'<meta name="description" content="{ENGLISH_DESCRIPTION}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta property="og:title" content="{ENGLISH_TITLE}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta property="og:description" content="{ENGLISH_DESCRIPTION}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta name="twitter:title" content="{ENGLISH_TITLE}">',
            self.english_html,
        )
        self.assertIn(
            f'<meta name="twitter:description" content="{ENGLISH_DESCRIPTION}">',
            self.english_html,
        )

    def test_hreflang_cluster_is_reciprocal_and_identical(self):
        expected = (
            f'<link rel="alternate" hreflang="fr" href="{ROOT_URL}">',
            f'<link rel="alternate" hreflang="en" href="{ENGLISH_URL}">',
            f'<link rel="alternate" hreflang="x-default" href="{ROOT_URL}">',
        )
        for html in (self.root_html, self.english_html):
            for tag in expected:
                self.assertEqual(html.count(tag), 1)

    def test_static_language_links_use_canonical_routes(self):
        for html in (self.root_html, self.english_html):
            self.assertIn(
                '<a href="/" data-fr27-language="fr"',
                html,
            )
            self.assertIn(
                '<a href="/en/" data-fr27-language="en"',
                html,
            )
            self.assertNotIn('href="?lang=en"', html)

    def test_committed_english_entrypoint_is_deterministic(self):
        source = INDEX.read_text(encoding="utf-8")
        generated = build_english_entrypoint(source)
        self.assertEqual(generated, self.english_html)
        self.assertEqual(
            build_english_entrypoint(source),
            generated,
        )

    def test_sitemap_contains_only_canonical_language_urls(self):
        tree = ET.parse(SITEMAP)
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [
            node.text
            for node in tree.findall("sm:url/sm:loc", namespace)
        ]
        self.assertEqual(urls, [ROOT_URL, ENGLISH_URL])
        for url in urls:
            self.assertNotIn("www.", url)
            self.assertNotIn("?lang=", url)

    def test_robots_is_permissive_and_advertises_sitemap(self):
        text = ROBOTS.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "User-agent: *\n"
            "Allow: /\n"
            "\n"
            "Sitemap: https://france2027.app/sitemap.xml\n",
        )

    def test_og_cover_workflow_regenerates_and_stages_english_entrypoint(self):
        workflow = (
            ROOT / ".github" / "workflows" / "refresh-og-cover.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "python .\\build_search_entrypoints.py",
            workflow,
        )
        self.assertIn(
            "python -m unittest test_search_foundation.py",
            workflow,
        )
        self.assertIn(
            '"en/index.html",',
            workflow,
        )
        self.assertIn(
            "            en/index.html `",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()