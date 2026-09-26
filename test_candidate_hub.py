import json
import re
import subprocess
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
        cls.shell_css = (ROOT / "assets/candidate-page-shell.css").read_text(
            encoding="utf-8"
        )
        cls.hud_javascript = (
            ROOT / "assets/candidate-family-hud.js"
        ).read_text(encoding="utf-8")

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

    def test_order_matches_candidate_monitor_contract(self):
        import json
        import candidate_hub as hub

        root = Path(__file__).resolve().parent

        payload = json.loads(
            (root / "candidate_signals.json").read_text(
                encoding="utf-8"
            )
        )

        ordered_ids = hub._workspace_order_candidate_ids(
            payload
        )

        by_id = {
            candidate["candidate_id"]: candidate
            for candidate in payload["candidates"]
        }

        # Candidate Monitor supplies relative order.
        # The public directory presents current non-potential profiles
        # first, followed seamlessly by current potential profiles.
        expected_main = [
            candidate_id
            for candidate_id in ordered_ids
            if by_id[candidate_id]["candidacy"]["status"]
            != "active_potential"
        ]

        expected_potential = [
            candidate_id
            for candidate_id in ordered_ids
            if by_id[candidate_id]["candidacy"]["status"]
            == "active_potential"
        ]

        expected = [
            *expected_main,
            *expected_potential,
        ]

        self.assertEqual(
            self._candidate_ids(self.fr),
            expected,
        )
        self.assertEqual(
            self._candidate_ids(self.en),
            expected,
        )

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

    def test_hubs_include_breadcrumb_json_ld(self):
        for document, home_name, hub_name, home_url, hub_url in (
            (
                self.fr,
                "ACCUEIL",
                "CANDIDATS",
                "https://france2027.app/",
                "https://france2027.app/candidates/",
            ),
            (
                self.en,
                "HOME",
                "CANDIDATES",
                "https://france2027.app/en/",
                "https://france2027.app/en/candidates/",
            ),
        ):
            match = re.search(
                r'<script type="application/ld\+json">(.*?)</script>',
                document,
                re.DOTALL,
            )
            self.assertIsNotNone(match)
            payload = json.loads(match.group(1))
            self.assertEqual(payload["@type"], "BreadcrumbList")
            crumbs = payload["itemListElement"]
            self.assertEqual(
                [(item["name"], item["item"]) for item in crumbs],
                [(home_name, home_url), (hub_name, hub_url)],
            )
            self.assertIn(f'<a href="{home_url.removeprefix("https://france2027.app")}">{home_name}</a>', document)

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

    def test_search_status_controls_and_visible_count_remain_present(self):
        for document in (self.fr, self.en):
            self.assertIn("data-candidate-search", document)
            self.assertIn("data-candidate-status", document)
            self.assertIn("data-candidate-visible-count", document)
            self.assertIn("<noscript>", document)

    def test_polling_lab_aligned_masthead_countdown_metrics_and_hud(self):
        for document in (self.fr, self.en):
            self.assertIn('class="candidate-masthead-tools"', document)
            self.assertIn('class="candidate-countdown" data-countdown', document)
            self.assertIn('class="candidate-hub-metrics"', document)
            self.assertEqual(document.count('class="candidate-hub-metric"'), 5)
            self.assertIn('id="candidate-app-hud" class="fr27-app-hud"', document)
            self.assertIn('id="fr27-hud-paris-time"', document)
            self.assertIn('id="fr27-hud-countdown-days"', document)
            self.assertIn('id="fr27-hud-domains-value"', document)
            self.assertIn('id="fr27-hud-polls-value"', document)
            self.assertIn('class="fr27-dashboard-cta"', document)
            self.assertIn('<link rel="stylesheet" href="/assets/candidate-page.css">', document)
            self.assertIn('<script src="/assets/candidate-family-hud.js" defer></script>', document)

    def test_summary_metrics_are_derived_from_canonical_statuses(self):
        expected = {
            status: sum(candidate["status"] == status for candidate in self.active)
            for status in (
                "declared",
                "party_selected",
                "primary_contender",
                "active_potential",
            )
        }
        for document in (self.fr, self.en):
            for count in expected.values():
                self.assertIn(f"<strong>{count}</strong>", document)

    def test_dashboard_link_is_visible_and_crawlable(self):
        self.assertIn(
            'class="fr27-dashboard-cta" href="https://france2027.app/"',
            self.fr,
        )
        self.assertIn(
            'class="fr27-dashboard-cta" href="https://france2027.app/en/"',
            self.en,
        )

    def test_canonical_hud_exists_on_every_bilingual_candidate_route(self):
        hierarchy = (
            'id="candidate-app-hud" class="fr27-app-hud"',
            'class="fr27-app-hud-toggle"',
            'class="fr27-app-hud-surface"',
            'class="fr27-app-hud-content fr27-linear-console"',
            'class="fr27-linear-zone fr27-zone-live"',
            'class="fr27-linear-zone fr27-zone-countdown"',
            'class="fr27-linear-zone fr27-zone-infra"',
            'class="fr27-linear-zone fr27-zone-dashboard"',
            'class="fr27-linear-zone fr27-zone-utility"',
            'class="fr27-dashboard-cta"',
            'class="fr27-linear-actions"',
            'class="fr27-hud-contact-popover"',
            'class="fr27-hud-info-popover"',
        )
        expected_paths = []
        for candidate in self.active:
            candidate_id = candidate["candidate_id"]
            expected_paths.extend((
                Path("candidates") / candidate_id / "index.html",
                Path("en") / "candidates" / candidate_id / "index.html",
            ))

        self.assertEqual(len(expected_paths), len(self.active) * 2)
        for path in expected_paths:
            document = self.artifacts[path].decode("utf-8")
            for token in hierarchy:
                self.assertIn(token, document, str(path))
            self.assertIn('id="fr27-hud-polls-value">—</strong>', document)
            self.assertIn('id="fr27-hud-email-toggle"', document)
            self.assertIn('id="fr27-hud-info-toggle"', document)
            self.assertIn('href="https://x.com/fr27signal"', document)
            self.assertIn(
                'href="https://github.com/openeventbits/france-2027-signal-lab"',
                document,
            )
            self.assertIn(
                '<script src="/assets/candidate-family-hud.js" defer></script>',
                document,
            )

    def test_hud_poll_metric_has_no_generated_or_template_literal_dependency(self):
        documents = [self.fr, self.en] + [
            content.decode("utf-8")
            for path, content in self.artifacts.items()
            if path.name == "index.html"
        ]
        for document in documents:
            self.assertIn('id="fr27-hud-polls-value">—</strong>', document)
            self.assertNotRegex(
                document,
                r'id="fr27-hud-polls-value">(?:65|66)</strong>',
            )

        template_source = "\n".join(
            (ROOT / filename).read_text(encoding="utf-8")
            for filename in ("candidate_hub.py", "build_candidate_reference.py")
        )
        self.assertNotIn('hud_metrics["poll_packages"]', template_source)
        self.assertNotRegex(
            template_source,
            r'id="fr27-hud-polls-value">(?:65|66)</strong>',
        )
        self.assertIn('fetch("/poll_explorer.json"', self.hud_javascript)
        self.assertIn("metrics.wave_count", self.hud_javascript)
        self.assertNotIn("poll_packages", self.hud_javascript)
        self.assertNotIn("polls.json", self.hud_javascript)

    def test_runtime_poll_metric_follows_only_explorer_payload(self):
        harness = r'''
const hudPollsValue = { textContent: "—" };
global.window = globalThis;
window.setInterval = () => 0;
window.setTimeout = setTimeout;
global.document = {
  documentElement: { lang: "en" },
  readyState: "complete",
  querySelector: () => null,
  getElementById: id => id === "fr27-hud-polls-value" ? hudPollsValue : null
};
global.fetch = async url => ({
  ok: url === "/poll_explorer.json",
  json: async () => JSON.parse(process.argv[1])
});
require(process.argv[2]);
setTimeout(() => process.stdout.write(hudPollsValue.textContent), 20);
'''
        observed = []
        for wave_count in (17, 18):
            test_payload = json.dumps({"metrics": {"wave_count": wave_count}})
            result = subprocess.run(
                [
                    "node",
                    "-e",
                    harness,
                    test_payload,
                    str(ROOT / "assets" / "candidate-family-hud.js"),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            observed.append(result.stdout)
        self.assertEqual(observed, ["17", "18"])

    def test_status_filters_include_archive_lifecycle_category(self):
        import re

        for html in (self.fr, self.en):
            card_statuses = set(
                re.findall(
                    r'data-candidate-status="([^"]+)"',
                    html,
                )
            )

            options = set(
                re.findall(
                    r'<option value="([^"]*)"',
                    html,
                )
            )

            self.assertEqual(
                options,
                {
                    "",
                    *card_statuses,
                    "archived",
                },
            )

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

    def test_mobile_masthead_has_explicit_stable_control_breakpoint(self):
        mobile_start = self.shell_css.index(
            "@media (max-width: 679px)"
        )
        small_start = self.shell_css.index(
            "@media (max-width: 359px)"
        )

        mobile = self.shell_css[
            mobile_start:small_start
        ]

        small = self.shell_css[
            small_start:
        ]

        self.assertIn(
            "flex-wrap: nowrap",
            mobile,
        )
        self.assertIn(
            "width: 92px",
            mobile,
        )
        self.assertIn(
            "flex: 0 0 92px",
            mobile,
        )
        self.assertIn(
            "flex: 1 1 0",
            mobile,
        )
        self.assertIn(
            "width: auto",
            mobile,
        )

        self.assertIn(
            "flex-wrap: wrap",
            small,
        )
        self.assertIn(
            "flex: 1 0 100%",
            small,
        )

    def test_css_uses_established_three_responsive_regimes(self):
        self.assertIn("@media (min-width: 760px) and (max-width: 1349px)", self.css)
        self.assertIn("@media (max-width: 759px)", self.css)
        self.assertIn("repeat(4, minmax(0, 1fr))", self.css)


    def test_archive_lifecycle_contract(self):
        import candidate_hub as hub

        self.assertEqual(
            set(hub.ARCHIVED_CANDIDACY_STATUSES),
            {
                "ruled_out",
                "withdrawn",
                "historical_poll_only",
            },
        )

        self.assertTrue(
            hub.is_archived_candidacy_status("withdrawn")
        )
        self.assertFalse(
            hub.is_archived_candidacy_status("active_potential")
        )

    def test_directory_uses_one_continuous_grid(self):
        for html in (self.fr, self.en):
            self.assertEqual(
                html.count("data-candidate-directory-grid"),
                1,
            )
            self.assertNotIn(
                "data-candidate-main-grid",
                html,
            )
            self.assertNotIn(
                "data-candidate-potential-grid",
                html,
            )

        self.assertIn("AFFICHER PLUS", self.fr)
        self.assertIn("SHOW MORE", self.en)


if __name__ == "__main__":
    unittest.main()
