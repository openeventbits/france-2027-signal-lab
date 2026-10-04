"""Global static links, shared host adapters, interaction and publication contracts."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from fr27_section_launcher import (
    FAMILIES, family_for_path, install_section_launcher, prepare_dashboard_header,
    prepare_section_header, render_section_menu,
)

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "fr": (("CANDIDATS", "SONDAGES", "ENJEUX", "AGENDA"),
           ("/candidates/", "/sondages/", "/enjeux/", "/agenda/")),
    "en": (("CANDIDATES", "POLLS", "ISSUES", "AGENDA"),
           ("/en/candidates/", "/en/sondages/", "/en/issues/", "/en/agenda/")),
}


def menu(document):
    return re.search(r'<nav class="fr27-section-menu".*?</nav>', document, re.S).group()


class SectionLauncherContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = json.loads((ROOT / "route_registry.json").read_text(encoding="utf-8"))["routes"]
        cls.documents = [(route, (ROOT / route["source_file"]).read_text(encoding="utf-8"))
                         for route in cls.routes if route["source_file"].endswith(".html")]
        cls.css = (ROOT / "assets/fr27-section-launcher.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "assets/fr27-section-launcher.js").read_text(encoding="utf-8")

    def test_registry_order_routes_and_labels(self):
        self.assertEqual(tuple(row[0] for row in FAMILIES), ("candidates", "polls", "issues", "agenda"))
        for language, (labels, hrefs) in EXPECTED.items():
            rendered = render_section_menu(language, "/")
            self.assertEqual(tuple(re.findall(r'class="fr27-section-label">([^<]+)', rendered)), labels)
            self.assertEqual(tuple(re.findall(r'href="([^"]+)"', rendered)), hrefs)

    def test_path_detection_including_history_and_prefix_boundaries(self):
        for family, fr, en in FAMILIES:
            for _, route in (fr, en):
                for suffix in ("", "detail/", "history/", "history/topic/", "historique/", "historique/topic/"):
                    with self.subTest(route=route + suffix):
                        self.assertEqual(family_for_path(route + suffix), family)
                self.assertIsNone(family_for_path(route.rstrip("/") + "-other/"))
        for path in ("/", "/en/", "/about/"):
            self.assertIsNone(family_for_path(path))

    def test_every_public_html_route_has_one_launcher_and_shared_assets(self):
        paths = {route["path"] for route, _ in self.documents}
        self.assertTrue({"/", "/en/"} <= paths)
        for route, document in self.documents:
            with self.subTest(path=route["path"]):
                self.assertRegex(document, r'<header class="(?:candidate-masthead|masthead)"')
                self.assertEqual(document.count("data-fr27-section-launcher"), 1)
                self.assertEqual(document.count('id="fr27-section-menu"'), 1)
                self.assertEqual(document.count('/assets/fr27-section-launcher.css"'), 1)
                self.assertEqual(document.count('/assets/fr27-section-launcher.js"'), 1)

    def test_four_static_ordinary_anchors_correct_active_family_and_language(self):
        for route, document in self.documents:
            with self.subTest(path=route["path"]):
                panel = menu(document)
                labels, hrefs = EXPECTED[route["language"]]
                self.assertEqual(tuple(re.findall(r'<a\b[^>]*href="([^"]+)"', panel)), hrefs)
                self.assertEqual(tuple(re.findall(r'class="fr27-section-label">([^<]+)', panel)), labels)
                active = family_for_path(route["path"])
                self.assertEqual(re.findall(r'data-section-family="([^"]+)" aria-current="true"', panel),
                                 [active] if active else [])
                self.assertNotRegex(panel, r'aria-disabled|COMING SOON|EN COURS|OVERVIEW|ABOUT|METHODOLOGY|HOME|DASHBOARD')
                self.assertRegex(panel, r'<a[^>]+data-section-family="agenda"')
                for href in hrefs:
                    self.assertTrue((ROOT / href.strip("/") / "index.html").is_file())

    def test_agenda_hub_detail_history_hub_history_detail_both_languages(self):
        for language in EXPECTED:
            routes = [r for r, _ in self.documents if r["family"] == "agenda" and r["language"] == language]
            self.assertEqual({r["kind"] for r in routes},
                             {"hub", "agenda-detail", "history-hub", "agenda-history-detail"})
            self.assertTrue(all(family_for_path(r["path"]) == "agenda" for r in routes))

    def test_named_button_disclosure_and_intact_signal_svg(self):
        for route, document in self.documents:
            with self.subTest(path=route["path"]):
                buttons = re.findall(r'<button class="(?:candidate-mark|mark) fr27-section-launcher-trigger".*?</button>', document, re.S)
                self.assertEqual(len(buttons), 1)
                label = "Explorer les sections" if route["language"] == "fr" else "Explore sections"
                for fragment in ('type="button"', 'aria-expanded="false"', 'aria-controls="fr27-section-menu"',
                                 f'aria-label="{label}"', 'viewBox="0 0 32 32"',
                                 'M6 16A10 10 0 0 1 16 6M26 16A10 10 0 0 1 16 26',
                                 'M10 16A6 6 0 0 1 16 10M22 16A6 6 0 0 1 16 22',
                                 '<circle cx="16" cy="16" r="2.5" fill="#35d5ff"/>'):
                    self.assertIn(fragment, buttons[0])
                self.assertRegex(menu(document), r'<nav[^>]+ hidden>')

    def test_static_wordmark_is_separate_home_link(self):
        for route, document in self.documents:
            if route["family"] == "core":
                continue
            with self.subTest(path=route["path"]):
                brand = re.search(r'<a class="candidate-brand".*?</a>', document, re.S).group()
                home = "/en/" if route["language"] == "en" else "/"
                self.assertIn(f'href="{home}"', brand)
                self.assertIn('FRANCE 2027 <em>SIGNAL LAB</em>', brand)
                self.assertNotRegex(brand, r'<button|<svg|aria-expanded')

    def test_installation_and_header_adapters_are_deterministic(self):
        for route, document in self.documents:
            with self.subTest(path=route["path"]):
                self.assertEqual(install_section_launcher(document, route["language"]), document)
        original = (ROOT / "test_fixtures/fr27_dashboard_masthead.html").read_text(encoding="utf-8").rstrip()
        adapted = prepare_dashboard_header(original, "en")
        self.assertEqual(prepare_dashboard_header(adapted, "en"), adapted)
        self.assertEqual(re.search(r'<svg.*?</svg>', original, re.S).group(),
                         re.search(r'<svg.*?</svg>', adapted, re.S).group())
        for selector in ("masthead-brand-copy", "masthead-tools"):
            self.assertEqual(original.count(selector), adapted.count(selector))
        self.assertNotIn('aria-current="true"', menu(adapted))
        poll_header = re.search(r'<header.*?</header>', (ROOT / "sondages/index.html").read_text(encoding="utf-8"), re.S).group()
        agenda_header = prepare_section_header(poll_header, "fr", "/agenda/historique/topic/")
        self.assertEqual(menu(agenda_header), menu(render_section_menu("fr", "/agenda/")))

    def test_controller_owns_interaction_only_with_normal_tab_order(self):
        for fragment in ('trigger.addEventListener("click"', 'document.addEventListener("click"',
                         'event.key === "Escape"', 'close(true)', 'trigger.focus()',
                         'trigger.setAttribute("aria-expanded", "false")',
                         'trigger.setAttribute("aria-expanded", "true")', 'panel.hidden = true',
                         '!trigger.contains(event.target)', '!panel.contains(event.target)'):
            self.assertIn(fragment, self.js)
        self.assertNotRegex(self.js, r'createElement|innerHTML|insertAdjacentHTML|document\.write|<a\b|\.href\s*=|setAttribute\("href"|event\.key === "Tab"')
        for path in (ROOT / "assets").glob("*.js"):
            if path.name != "fr27-section-launcher.js":
                self.assertNotIn("fr27-section-launcher-trigger", path.read_text(encoding="utf-8"))

    def test_english_search_rebuild_uses_shared_localized_launcher(self):
        from build_search_entrypoints import build_english_entrypoint
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        rebuilt = build_english_entrypoint(source)
        self.assertEqual(menu(rebuilt), menu(render_section_menu("en", "/en/")))
        self.assertIn('aria-label="Explore sections"', rebuilt)

    def test_mobile_grid_closed_space_focus_and_reduced_motion_contract(self):
        for fragment in ('width: 270px', 'position: absolute', '.fr27-section-menu[hidden] { display: none; }',
                         '@media (max-width: 679px)', 'position: static',
                         'grid-template-columns: repeat(2, minmax(0, 1fr))', ':focus-visible',
                         '@media (prefers-reduced-motion: reduce)', 'transition: none', 'animation: none'):
            self.assertIn(fragment, self.css)

    def test_publication_workflows_depend_on_shared_helper_and_assets(self):
        dependencies = ('fr27_section_launcher.py', 'assets/fr27-section-launcher.css', 'assets/fr27-section-launcher.js')
        for name in ('publish-candidate-family.yml', 'publish-issue-family.yml', 'publish-agenda-family.yml', 'update-polls.yml'):
            text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            trigger = text.split("permissions:")[0]
            with self.subTest(workflow=name):
                for dependency in dependencies:
                    self.assertIn(f'- "{dependency}"', trigger)
                self.assertIn("group: production-data-update", text)
                self.assertIn("cancel-in-progress: false", text)
                self.assertIn("queue: max", text)
        polls = (ROOT / ".github/workflows/update-polls.yml").read_text(encoding="utf-8")
        self.assertEqual(polls.count("python -B fr27_section_launcher.py\n"), 2)
        trigger = polls.split("permissions:")[0]
        self.assertIn('branches:\n      - main', trigger)
        self.assertEqual(tuple(re.findall(r'      - "([^"]+)"', trigger)), dependencies)
        self.assertIn("test_fr27_section_launcher", (ROOT / ".github/workflows/validate-dashboard.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
