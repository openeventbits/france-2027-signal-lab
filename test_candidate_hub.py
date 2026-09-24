import re
import unittest
from pathlib import Path

import build_candidate_reference as reference
from candidate_candidacy_status import active_candidate_records
from candidate_page_contract import project_candidate_page_index
from candidate_portraits import load_candidate_portraits


ROOT = Path(__file__).resolve().parent


class CandidateHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = reference.load_sources(ROOT)
        cls.active = active_candidate_records(
            cls.sources["candidate_candidacy_status"]
        )
        cls.page_index = project_candidate_page_index(
            cls.sources["candidate_candidacy_status"]
        )
        cls.artifacts = reference.build_all_active_artifacts(
            cls.sources,
            ROOT,
        )
        cls.fr = cls.artifacts[Path("candidates/index.html")].decode("utf-8")
        cls.en = cls.artifacts[Path("en/candidates/index.html")].decode("utf-8")
        cls.javascript = (ROOT / "assets/candidate-hub.js").read_text(
            encoding="utf-8"
        )
        cls.css = (ROOT / "assets/candidate-hub.css").read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _candidate_ids(document):
        return re.findall(r'<article class="candidate-hub-card"[^>]*data-candidate-id="([^"]+)"', document)

    @staticmethod
    def _card_links(document):
        cards = re.findall(
            r'<article class="candidate-hub-card"(?P<attrs>[^>]*)>(?P<body>.*?)</article>',
            document,
            re.DOTALL,
        )
        result = {}
        for attrs, body in cards:
            candidate_id = re.search(r'data-candidate-id="([^"]+)"', attrs).group(1)
            links = re.findall(r'<a[^>]+href="([^"]+)"', body)
            result[candidate_id] = links
        return result

    def test_hub_count_and_membership_equal_canonical_active_roster(self):
        expected = {candidate["candidate_id"] for candidate in self.active}
        for document in (self.fr, self.en):
            ids = self._candidate_ids(document)
            self.assertEqual(len(ids), len(self.active))
            self.assertEqual(set(ids), expected)
            self.assertEqual(len(ids), len(set(ids)))
            self.assertIn(
                f"<strong data-candidate-total>{len(self.active)}</strong>",
                document,
            )

    def test_generator_contains_no_fixed_candidate_count(self):
        for filename in (
            "candidate_hub.py",
            "build_candidates_hub.py",
            "build_candidate_reference.py",
        ):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"\bactive_count\s*=\s*44\b")
            self.assertNotRegex(source, r"\bcount\s*=\s*44\b")
            self.assertNotIn('"44 candidates"', source)
            self.assertNotIn('"44 candidats"', source)

    def test_order_is_unicode_aware_contract_order(self):
        expected = [
            candidate["candidate_id"]
            for candidate in self.page_index["candidates"]
        ]
        self.assertEqual(self._candidate_ids(self.fr), expected)
        self.assertEqual(self._candidate_ids(self.en), expected)

    def test_every_card_has_candidate_id_and_locale_peer_dossier_links(self):
        fr_links = self._card_links(self.fr)
        en_links = self._card_links(self.en)
        self.assertEqual(set(fr_links), set(en_links))
        for candidate_id in fr_links:
            fr_route = f"/candidates/{candidate_id}/"
            en_route = f"/en/candidates/{candidate_id}/"
            self.assertTrue(fr_links[candidate_id])
            self.assertTrue(en_links[candidate_id])
            self.assertTrue(all(link == fr_route for link in fr_links[candidate_id]))
            self.assertTrue(all(link == en_route for link in en_links[candidate_id]))

    def test_search_head_is_indexable_canonical_and_reciprocal(self):
        contracts = (
            (
                self.fr,
                "https://france2027.app/candidates/",
                "fr_FR",
            ),
            (
                self.en,
                "https://france2027.app/en/candidates/",
                "en_GB",
            ),
        )
        for document, canonical, locale in contracts:
            self.assertIn(
                '<meta name="robots" content="index,follow,max-image-preview:large">',
                document,
            )
            self.assertIn(f'<link rel="canonical" href="{canonical}">', document)
            self.assertIn(
                '<link rel="alternate" hreflang="fr" href="https://france2027.app/candidates/">',
                document,
            )
            self.assertIn(
                '<link rel="alternate" hreflang="en" href="https://france2027.app/en/candidates/">',
                document,
            )
            self.assertIn(
                '<link rel="alternate" hreflang="x-default" href="https://france2027.app/candidates/">',
                document,
            )
            self.assertIn(reference.FR27_FAVICON_MARKUP, document)
            self.assertIn(f'<meta property="og:locale" content="{locale}">', document)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', document)

    def test_static_cards_and_links_do_not_depend_on_javascript(self):
        for document in (self.fr, self.en):
            self.assertEqual(
                document.count('data-candidate-card data-candidate-id='),
                len(self.active),
            )
            self.assertEqual(document.count('class="candidate-hub-open"'), len(self.active))
        self.assertNotIn("innerHTML", self.javascript)
        self.assertNotIn("createElement", self.javascript)
        self.assertIn('document.querySelectorAll("[data-candidate-card]")', self.javascript)
        self.assertIn("card.hidden = !show", self.javascript)

    def test_status_filters_are_only_active_canonical_statuses(self):
        expected = {candidate["status"] for candidate in self.active}
        for document in (self.fr, self.en):
            options = set(re.findall(r'<option value="([^"]+)">', document))
            options.discard("")
            self.assertEqual(options, expected)

    def test_portraits_come_from_dashboard_registry_with_initials_fallback(self):
        portraits = load_candidate_portraits(ROOT / "index.html")
        self.assertEqual(
            portraits["Marine Le Pen"],
            "/assets/candidates/lepen.png",
        )
        self.assertIn('src="/assets/candidates/lepen.png"', self.fr)

        expected_fallbacks = [
            candidate
            for candidate in self.page_index["candidates"]
            if candidate["candidate_name"] not in portraits
        ]
        self.assertEqual(
            self.fr.count('candidate-hub-portrait is-fallback'),
            len(expected_fallbacks),
        )
        for candidate in expected_fallbacks:
            self.assertIn(
                f'data-candidate-id="{candidate["candidate_id"]}"',
                self.fr,
            )

    def test_unavailable_attention_is_distinct_from_not_observed(self):
        for document, label in (
            (self.fr, "indisponible"),
            (self.en, "unavailable"),
        ):
            card = re.search(
                r'<article class="candidate-hub-card"[^>]*data-candidate-id="benoit-mathieu".*?</article>',
                document,
                re.DOTALL,
            ).group(0)
            self.assertIn(
                'data-signal="attention" data-available="false" '
                'data-evidence-state="unavailable"',
                card,
            )
            self.assertIn(f"<small>{label}</small>", card)

    def test_no_duplicate_element_ids(self):
        for document in (self.fr, self.en):
            ids = re.findall(r'\sid="([^"]+)"', document)
            self.assertEqual(len(ids), len(set(ids)))

    def test_no_links_to_unimplemented_evidence_hubs(self):
        forbidden = (
            "/polls/",
            "/sondages/",
            "/runoffs/",
            "/issues/",
            "/events/",
            "/sources/",
        )
        for document in (self.fr, self.en):
            hrefs = re.findall(r'href="([^"]+)"', document)
            for href in hrefs:
                self.assertFalse(any(href == route for route in forbidden), href)

    def test_all_active_routes_are_generated_and_hub_links_resolve(self):
        fr_links = self._card_links(self.fr)
        en_links = self._card_links(self.en)
        for candidate in self.page_index["candidates"]:
            candidate_id = candidate["candidate_id"]
            self.assertIn(
                Path("candidates") / candidate_id / "data.json",
                self.artifacts,
            )
            fr_path = Path("candidates") / candidate_id / "index.html"
            en_path = Path("en") / "candidates" / candidate_id / "index.html"
            self.assertIn(fr_path, self.artifacts)
            self.assertIn(en_path, self.artifacts)
            self.assertIn(candidate["routes"]["fr"], fr_links[candidate_id])
            self.assertIn(candidate["routes"]["en"], en_links[candidate_id])

    def test_generated_routes_have_matching_canonical_and_hreflang(self):
        for candidate in self.page_index["candidates"]:
            candidate_id = candidate["candidate_id"]
            fr = self.artifacts[
                Path("candidates") / candidate_id / "index.html"
            ].decode("utf-8")
            en = self.artifacts[
                Path("en") / "candidates" / candidate_id / "index.html"
            ].decode("utf-8")
            fr_url = candidate["canonical"]["fr"]
            en_url = candidate["canonical"]["en"]
            self.assertIn(f'<link rel="canonical" href="{fr_url}">', fr)
            self.assertIn(f'<link rel="canonical" href="{en_url}">', en)
            for document in (fr, en):
                self.assertIn(
                    f'<link rel="alternate" hreflang="fr" href="{fr_url}">',
                    document,
                )
                self.assertIn(
                    f'<link rel="alternate" hreflang="en" href="{en_url}">',
                    document,
                )

    def test_css_uses_established_three_responsive_regimes(self):
        self.assertIn("@media (min-width: 760px) and (max-width: 1349px)", self.css)
        self.assertIn("@media (max-width: 759px)", self.css)
        self.assertIn("repeat(4, minmax(0, 1fr))", self.css)


if __name__ == "__main__":
    unittest.main()
