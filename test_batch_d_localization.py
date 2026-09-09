from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unittest

from test_runoff_workspace import margin_event, run_runoff_script


ROOT = Path(__file__).resolve().parent
HYBRID = (ROOT / "assets" / "hybrid-dashboard.js").read_text(encoding="utf-8")


def catalog(locale: str) -> dict[str, str]:
    source = (ROOT / "locales" / f"{locale}.js").read_text(encoding="utf-8")
    match = re.search(
        r"const messages = Object\.freeze\((\{.*?\})\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{locale} catalog was not found")
    return json.loads(match.group(1))


def result_from_event(event: dict) -> dict:
    return {
        key: copy.deepcopy(event[key])
        for key in (
            "event_id",
            "pollster",
            "candidates",
            "margin",
            "source_url",
        )
    }


def semantic_fixture() -> tuple[dict, dict]:
    closest = ("Élodie Martin", "Maël Dubois")
    common_other = ("Élodie Martin", "Inès Bernard")
    archive_only = ("Noémie Laurent", "Maël Dubois")

    current_events = [
        margin_event(
            "Institut Lumière",
            closest,
            3.5,
            start="2026-09-07",
            end="2026-09-08",
            source_url="https://example.test/lumiere/closest?raw=1",
        ),
        margin_event(
            "Sondages Hexagone",
            closest,
            4.5,
            start="2026-09-07",
            end="2026-09-08",
            source_url="https://example.test/hexagone/closest?raw=2",
        ),
        margin_event(
            "Institut Lumière",
            common_other,
            8,
            start="2026-09-07",
            end="2026-09-08",
            source_url="https://example.test/lumiere/common?raw=3",
        ),
        margin_event(
            "Sondages Hexagone",
            common_other,
            9,
            start="2026-09-07",
            end="2026-09-08",
            source_url="https://example.test/hexagone/common?raw=4",
        ),
    ]
    current_events[0]["sample_size"] = 1582
    current_events[1]["sample_size"] = 2000
    current_events[2]["sample_size"] = 1499
    current_events[3]["sample_size"] = 1701

    historical = margin_event(
        "Institut Lumière",
        closest,
        5.5,
        start="2026-07-11",
        end="2026-07-12",
        source_url="https://example.test/lumiere/history?raw=5",
    )
    historical["sample_size"] = 1450
    other = margin_event(
        "Observatoire Rhône",
        archive_only,
        6.5,
        start="2026-08-01",
        end="2026-08-02",
        source_url="https://example.test/rhone/other?raw=6",
    )
    other["sample_size"] = 1600
    archive_events = [historical, other, *current_events]

    selected_results = [result_from_event(event) for event in current_events[:2]]
    other_results = [result_from_event(event) for event in current_events[2:]]
    selected_key = current_events[0]["matchup_key"]
    common_other_key = current_events[2]["matchup_key"]
    selected = {
        "matchup_key": selected_key,
        "candidates": list(closest),
        "results": selected_results,
    }
    common = {
        "matchup_key": common_other_key,
        "candidates": list(common_other),
        "results": other_results,
    }
    payload = {
        "status": "agree",
        "message": "RAW ENGLISH APP MESSAGE — MUST NOT DRIVE FRENCH PRESENTATION",
        "disclosure": "RAW ENGLISH DISCLOSURE — KEEP IN ARTIFACT",
        "fieldwork_window": {"start": "2026-09-07", "end": "2026-09-08"},
        "pollster_count": 2,
        "common_matchup_count": 2,
        "selected_matchup": selected,
        "pollsters": [
            {
                "pollster": event["pollster"],
                "closest_matchups": [
                    {
                        "matchup_key": selected_key,
                        "candidates": list(closest),
                        "result": result_from_event(event),
                    }
                ],
            }
            for event in current_events[:2]
        ],
        "common_matchups": [selected, common],
    }
    archive_state = {"status": "ready", "events": archive_events, "error": ""}
    return payload, archive_state


def render(payload: dict | None, locale: str, archive_state: dict | None = None, load_state: str = "ready") -> dict:
    return run_runoff_script(
        payload,
        "(() => { const rawBefore = JSON.stringify(context.dashboardState.runoff); const archiveBefore = JSON.stringify(input.archiveState); const model = api.buildRunoffViewModel(input.archiveState || undefined); const html = api.renderRunoffPanel(model); return { model, html, rawUnchanged: rawBefore === JSON.stringify(context.dashboardState.runoff), archiveUnchanged: archiveBefore === JSON.stringify(input.archiveState) }; })()",
        archive_state=archive_state,
        load_state=load_state,
        locale=locale,
    )


class BatchDLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.archive_state = semantic_fixture()
        cls.fr = render(cls.payload, "fr", cls.archive_state)
        cls.en = render(cls.payload, "en", cls.archive_state)
        cls.en_catalog = catalog("en")
        cls.fr_catalog = catalog("fr")

    def test_french_live_runoff_modules_render_required_terminology(self):
        html = self.fr["html"]
        for expected in (
            "SIGNAUX DU 2E TOUR",
            "DUEL TESTÉ LE PLUS SERRÉ",
            "ÉCART MINIMAL OBSERVÉ",
            "DUELS TESTÉS EN COMMUN",
            "DUEL",
            "ÉCARTS",
            "DUEL COMMUN LE PLUS SERRÉ",
            "HISTORIQUE DU DUEL SÉLECTIONNÉ",
            "CHOISIR UN DUEL",
            "AUTRES DUELS TESTÉS",
        ):
            self.assertIn(expected, html)

    def test_status_labels_and_explanations_derive_from_stable_ids(self):
        cases = {
            "agree": (
                "CONVERGENCE",
                "Les deux sondeurs identifient ce duel comme le plus serré.",
            ),
            "split": (
                "DIVERGENCE",
                "Les sondeurs identifient chacun un duel unique différent comme le plus serré parmi les duels testés en commun.",
            ),
            "ambiguous": (
                "NON UNIQUE",
                "Au moins un sondeur a plusieurs duels à égalité pour son écart publié minimal.",
            ),
            "insufficient": ("INSUFFISANT", "Comparaison actuelle indisponible."),
        }
        for status, (label, explanation) in cases.items():
            with self.subTest(status=status):
                fixture = copy.deepcopy(self.payload)
                fixture["status"] = status
                fixture["message"] = f"RAW ENGLISH {status.upper()} MESSAGE"
                if status != "agree":
                    fixture["selected_matchup"] = None
                    fixture["common_matchups"] = []
                    fixture["pollsters"] = self.payload["pollsters"]
                output = render(fixture, "fr", self.archive_state)
                self.assertEqual(output["model"]["status"], status)
                self.assertIn(f'is-{status}', output["html"])
                self.assertIn(label, output["html"])
                self.assertIn(explanation, output["html"])
                self.assertNotIn(f"RAW ENGLISH {status.upper()} MESSAGE", output["html"])

    def test_french_numbers_dates_months_and_unavailable_labels_are_localized(self):
        html = self.fr["html"]
        self.assertIn("n=1\u202f582", html)
        self.assertIn("3,5", html)
        self.assertIn("48,3\u00a0%", html)
        self.assertIn("7–8 sept. 2026", html)

        missing_fieldwork = copy.deepcopy(self.payload)
        missing_fieldwork["fieldwork_window"] = None
        unavailable = render(missing_fieldwork, "fr", self.archive_state)
        self.assertIn("Terrain indisponible", unavailable["html"])

    def test_english_live_runoff_presentation_remains_unchanged(self):
        html = self.en["html"]
        for expected in (
            "RUNOFF SIGNALS",
            "Source-separated second-round evidence · no averages · no forecast",
            "CLOSEST TESTED RUNOFF",
            "Same closest matchup · different reported distance",
            "NARROWEST OBSERVED MARGIN",
            "CURRENT COMMON MATCHUPS",
            "MATCHUP",
            "MARGINS",
            "CLOSEST COMMON MATCHUP",
            "SELECTED MATCHUP HISTORY",
            "INSPECT MATCHUP",
            "OTHER TESTED MATCHUPS",
            "Both pollsters agree this is the closest tested runoff",
            "n=1,582",
            "7–8 SEPT 2026",
        ):
            self.assertIn(expected, html)

    def test_source_data_and_identity_are_unchanged(self):
        model = self.fr["model"]
        self.assertTrue(self.fr["rawUnchanged"])
        self.assertTrue(self.fr["archiveUnchanged"])
        self.assertEqual(model["status"], self.payload["status"])
        self.assertEqual(model["selectedMatchup"]["key"], self.payload["selected_matchup"]["matchup_key"])
        self.assertEqual(model["selectedMatchup"]["candidates"], self.payload["selected_matchup"]["candidates"])
        self.assertEqual(
            [item["event_id"] for item in model["selectedMatchup"]["observations"]],
            [item["event_id"] for item in self.payload["selected_matchup"]["results"]],
        )
        for event in self.archive_state["events"]:
            for value in (event["pollster"], *(candidate["name"] for candidate in event["candidates"])):
                self.assertIn(value, self.fr["html"])
        self.assertEqual(
            [
                result["source_url"]
                for matchup in model["commonMatchups"]
                for result in matchup["results"]
            ],
            [
                result["source_url"]
                for matchup in self.payload["common_matchups"]
                for result in matchup["results"]
            ],
        )
        for event in (
            self.archive_state["events"][0],
            self.archive_state["events"][1],
            *self.archive_state["events"][2:4],
        ):
            self.assertIn(event["source_url"], self.fr["html"])

    def test_source_link_accessibility_is_localized_without_changing_href(self):
        source_url = self.payload["selected_matchup"]["results"][0]["source_url"]
        self.assertIn(f'href="{source_url}"', self.fr["html"])
        self.assertIn(
            'aria-label="Ouvrir la source Institut Lumière pour Élodie Martin face à Maël Dubois"',
            self.fr["html"],
        )
        self.assertIn(
            'aria-label="Open Institut Lumière source for Élodie Martin versus Maël Dubois"',
            self.en["html"],
        )

    def test_loading_invalid_unavailable_and_archive_states_are_localized(self):
        loading = render(self.payload, "fr", load_state="loading")["html"]
        invalid = render({}, "fr")["html"]
        unavailable = render(None, "fr", load_state="error")["html"]
        archive = render(
            self.payload,
            "fr",
            {"status": "unavailable", "events": [], "error": "raw failure"},
        )["html"]
        self.assertIn("Chargement des données du dépôt", loading)
        self.assertIn("artefact dérivé est mal formé", invalid)
        self.assertIn("Les autres signaux restent accessibles", unavailable)
        self.assertIn("l’historique sont indisponibles localement", archive)

    def test_french_fixture_has_no_obvious_app_owned_english(self):
        html = self.fr["html"]
        for english in (
            "RUNOFF SIGNALS",
            "Source-separated second-round evidence",
            "CLOSEST TESTED RUNOFF",
            "Same closest matchup",
            "NARROWEST OBSERVED MARGIN",
            "CURRENT COMMON MATCHUPS",
            "CLOSEST COMMON MATCHUP",
            "Candidate 1",
            "Candidate 2",
            "Exact source-reported scores",
            "SELECTED MATCHUP HISTORY",
            "INSPECT MATCHUP",
            "Discrete source observations only",
            "OTHER TESTED MATCHUPS",
            "Evidence catalogue",
            "Margin",
            "Open Institut",
            "RAW ENGLISH APP MESSAGE",
            "RAW ENGLISH DISCLOSURE",
        ):
            self.assertNotIn(english, html)

    def test_catalog_family_is_semantic_and_dormant_paths_stay_out_of_batch(self):
        required = {
            "runoff_workspace.title",
            "runoff_workspace.closest_tested_runoff",
            "runoff_workspace.current_common_matchups",
            "runoff_workspace.selected_matchup_history",
            "runoff_workspace.other_tested_matchups",
            "runoff_workspace.status.agree",
            "runoff_workspace.status.split",
            "runoff_workspace.status.ambiguous",
            "runoff_workspace.status.insufficient",
        }
        self.assertTrue(required.issubset(self.en_catalog))
        self.assertTrue(required.issubset(self.fr_catalog))
        self.assertEqual(HYBRID.count("renderRunoffFootprint("), 1)
        self.assertEqual(HYBRID.count("renderRunoffSummary("), 2)
        panel = HYBRID.split("  function renderRunoffPanel(model) {", 1)[1].split(
            "\n  function renderMediaPanel(model) {", 1
        )[0]
        self.assertNotIn("renderRunoffFootprint", panel)
        self.assertNotIn("renderRunoffSummary", panel)


if __name__ == "__main__":
    unittest.main()


def test_runoff_other_column_headers_are_locale_owned():
    from pathlib import Path

    source = Path("assets/hybrid-dashboard.js").read_text(encoding="utf-8")
    css = Path("assets/hybrid-dashboard.css").read_text(encoding="utf-8")
    en = Path("locales/en.js").read_text(encoding="utf-8")
    fr = Path("locales/fr.js").read_text(encoding="utf-8")

    assert "data-matchup-label" in source
    assert "data-latest-result-label" in source
    assert '"runoff_workspace.latest_result_balance"' in source
    assert "content: attr(data-matchup-label);" in css
    assert "content: attr(data-latest-result-label);" in css
    assert 'content: "MATCHUP";' not in css
    assert '"runoff_workspace.latest_result_balance": "LATEST RESULT · BALANCE"' in en
    assert '"runoff_workspace.latest_result_balance": "DERNIER RÉSULTAT · ÉQUILIBRE"' in fr
