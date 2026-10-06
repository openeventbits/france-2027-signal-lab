"""Current-data routing contracts; destinations are never display-name guesses."""
import json
import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from dashboard_navigation import navigation_model, poll_href
from build_search_entrypoints import NAV_START, NAV_END, render_navigation

ROOT = Path(__file__).resolve().parent


class Anchors(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.anchors = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchors.append(dict(attrs))


class DashboardNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = navigation_model()
        cls.events = json.loads((ROOT / "polls.json").read_text(encoding="utf-8"))
        cls.registry = json.loads((ROOT / "route_registry.json").read_text(encoding="utf-8"))["routes"]

    def test_every_current_event_has_one_exact_bilingual_page_and_fragment(self):
        manifest = json.loads((ROOT / "poll_pages_manifest.json").read_text(encoding="utf-8"))
        waves = json.loads((ROOT / "poll_explorer.json").read_text(encoding="utf-8"))["waves"]
        pages = {p["wave_id"]: p for p in manifest["pages"]}
        indexed = {}
        for wave in waves:
            for number, scenario in enumerate(wave["scenarios"], 1):
                self.assertNotIn(scenario["event_id"], indexed)
                indexed[scenario["event_id"]] = (wave, number, scenario)
        for event in self.events:
            if event["round"] != "first_round":
                continue
            wave, number, scenario = indexed[event["event_id"]]
            self.assertEqual(self.routes["events"][event["event_id"]], [wave["wave_id"], number])
            for language in ("fr", "en"):
                href = poll_href(self.routes, event["event_id"], language)
                self.assertEqual(href, pages[wave["wave_id"]][f"page_path_{language}"] + f"#scenario-{number}")
                source = (ROOT / href.split("#")[0].lstrip("/") / "index.html").read_text(encoding="utf-8")
                self.assertIn(f'id="scenario-{number}"', source)
                scenario_markup = re.search(rf'<details\b[^>]*id="scenario-{number}"[^>]*>.*?</details>', source, re.DOTALL)
                self.assertIsNotNone(scenario_markup)
                self.assertIn(event["event_id"], scenario_markup.group(0))
                self.assertIn(scenario["source_url"].replace("&", "&amp;"), source)
                self.assertIn(wave["pollster"], source)
                self.assertIn(wave["fieldwork_end"], source)

    def test_detail_routes_match_published_registry_and_files(self):
        kinds = {"candidates": "candidate-detail", "issues": "issue-detail", "agenda": "agenda-detail"}
        for family, kind in kinds.items():
            registry = {(r["entity_id"], r["language"]): r["path"] for r in self.registry if r["kind"] == kind}
            for entity, routes in self.routes[family].items():
                for language, href in routes.items():
                    self.assertEqual(href, registry[entity, language])
                    self.assertTrue((ROOT / href.lstrip("/") / "index.html").is_file())
                    self.assertNotRegex(href, r"/history/|/historique/")

    def test_dashboard_has_no_redundant_family_hub_strip(self):
        for language, file in (("fr", "index.html"), ("en", "en/index.html")):
            text = (ROOT / file).read_text(encoding="utf-8")
            anchors = Anchors(text).anchors
            self.assertNotIn("dashboard-family-navigation", text)
            self.assertFalse([a for a in anchors if "data-dashboard-hub" in a])
            self.assertEqual(text.count('id="published-dashboard-navigation"'), 1)
            self.assertEqual(text.count('src="assets/dashboard-navigation.js"'), 1)
            embedded = re.search(r'id="published-dashboard-navigation">(.*?)</script>', text).group(1)
            self.assertEqual(json.loads(embedded), self.routes)
            race = next(a for a in anchors if a.get("id") == "race-source")
            selected = json.loads((ROOT / "candidate_signals.json").read_text(encoding="utf-8"))["featured_poll_board"]["selected_event_id"]
            self.assertEqual(race["href"], poll_href(self.routes, selected, language))
            self.assertNotIn("target", race)

    def test_runtime_resolver_matches_projection_and_unknowns_are_safe(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const document={documentElement:{lang:input.lang},getElementById:()=>({textContent:JSON.stringify(input.routes)})};
const window={};vm.runInNewContext(fs.readFileSync('assets/dashboard-navigation.js','utf8'),{window,document,globalThis:window});
const n=window.FR27DashboardNavigation;
console.log(JSON.stringify({polls:Object.fromEntries(Object.keys(input.routes.events).map(id=>[id,n.poll(id)])),details:Object.fromEntries(['candidates','issues','agenda'].map(f=>[f,Object.fromEntries(Object.keys(input.routes[f]).map(id=>[id,n.detail(f,id)]))])),unknown:n.detail('candidates','No Guessed Name'),fallback:n.poll('unpublished-event'),prototypeFallback:n.poll('toString')}));
'''
        for language in ("fr", "en"):
            result = subprocess.run(["node", "-e", script], cwd=ROOT, input=json.dumps({"lang": language, "routes": self.routes}), text=True, capture_output=True, check=True)
            actual = json.loads(result.stdout)
            self.assertEqual(actual["polls"], {id: poll_href(self.routes, id, language) for id in self.routes["events"]})
            for family, details in actual["details"].items():
                self.assertEqual(details, {id: route[language] for id, route in self.routes[family].items()})
            self.assertEqual(actual["unknown"], "")
            self.assertEqual(actual["fallback"], self.routes["hubs"]["polls"][language])
            self.assertEqual(actual["prototypeFallback"], self.routes["hubs"]["polls"][language])

    def test_builder_navigation_is_idempotent(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for language in ("fr", "en"):
            first = render_navigation(source, language)
            self.assertEqual(first, render_navigation(first, language))
            self.assertEqual(first.count(NAV_START), 1)
            self.assertEqual(first.count(NAV_END), 1)

    def test_candidate_dossier_link_disappears_after_selecting_unpublished_identity(self):
        from test_candidate_signals_workspace import candidate, payload, run_workspace
        source = payload([candidate("marine-le-pen", "Marine Le Pen"),
                          candidate("unpublished-identity", "Unpublished identity")])
        for language in ("fr", "en"):
            first = run_workspace(source, selected_id="marine-le-pen", locale=language, navigation=self.routes)
            expected = self.routes["candidates"]["marine-le-pen"][language]
            self.assertEqual(first["navigationHrefs"], [expected])
            second = run_workspace(source, selected_id="marine-le-pen", action="click-second", locale=language, navigation=self.routes)
            self.assertEqual(second["navigationHrefs"], [])
            self.assertTrue(any(href.startswith("https://") for href in second["linkHrefs"]))

    def test_builder_rejects_missing_or_ambiguous_current_poll_mappings(self):
        original = json.loads((ROOT / "poll_explorer.json").read_text(encoding="utf-8"))
        real_read = Path.read_text
        for mode in ("missing", "ambiguous"):
            payload = json.loads(json.dumps(original))
            if mode == "missing":
                payload["waves"][0]["scenarios"].pop()
            else:
                payload["waves"][0]["scenarios"].append(payload["waves"][0]["scenarios"][0])
            def read(path, *args, **kwargs):
                return json.dumps(payload) if path.name == "poll_explorer.json" else real_read(path, *args, **kwargs)
            with patch.object(Path, "read_text", read), self.assertRaises(ValueError):
                navigation_model()


if __name__ == "__main__":
    unittest.main()
