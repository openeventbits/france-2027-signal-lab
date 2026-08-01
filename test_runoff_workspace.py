from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from fetch_polls import (
    SECOND_ROUND,
    derive_closest_tested_runoff,
    validate_second_round_event,
)
from poll_contract import make_event_id, make_scenario_key


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
HYBRID_JS = ROOT / "assets" / "hybrid-dashboard.js"
HYBRID_CSS = ROOT / "assets" / "hybrid-dashboard.css"

PHILIPPE_LE_PEN = ("Édouard Philippe", "Marine Le Pen")
BARDella_ATTAL = ("Jordan Bardella", "Gabriel Attal")
GLUCKSMANN_ZEMMOUR = ("Raphaël Glucksmann", "Éric Zemmour")


def second_round_event(
    pollster: str,
    matchup: tuple[str, str],
    left_score: int | float,
    right_score: int | float,
    *,
    start: str = "2026-07-01",
    end: str = "2026-07-02",
    source_scope: str = "current_tested",
    source_url: str | None = None,
) -> dict:
    names = list(matchup)
    hypothesis = "Second round — " + " vs ".join(names)
    source_url = source_url or (
        "https://example.test/"
        + pollster.casefold().replace(" ", "-")
        + "/"
        + make_scenario_key(names, round_name=SECOND_ROUND)[:8]
    )
    event = {
        "event_id": make_event_id(
            pollster,
            start,
            end,
            hypothesis,
            source_url,
            round_name=SECOND_ROUND,
        ),
        "round": SECOND_ROUND,
        "pollster": pollster,
        "fieldwork_start": start,
        "fieldwork_end": end,
        "matchup_key": make_scenario_key(names, round_name=SECOND_ROUND),
        "hypothesis": hypothesis,
        "candidates": [
            {"name": names[0], "score": left_score},
            {"name": names[1], "score": right_score},
        ],
        "margin": abs(left_score - right_score),
        "source_url": source_url,
        "source_scope": source_scope,
    }
    validate_second_round_event(event)
    return event


def margin_event(
    pollster: str,
    matchup: tuple[str, str],
    margin: int | float,
    **kwargs,
) -> dict:
    return second_round_event(
        pollster,
        matchup,
        50 + margin / 2,
        50 - margin / 2,
        **kwargs,
    )


def qualifying_events(
    pollster_margins: dict[str, tuple[int | float, int | float]],
    *,
    start: str = "2026-07-01",
    end: str = "2026-07-02",
) -> list[dict]:
    events = []
    for pollster, (first_margin, second_margin) in pollster_margins.items():
        events.extend(
            [
                margin_event(
                    pollster,
                    PHILIPPE_LE_PEN,
                    first_margin,
                    start=start,
                    end=end,
                ),
                margin_event(
                    pollster,
                    BARDella_ATTAL,
                    second_margin,
                    start=start,
                    end=end,
                ),
            ]
        )
    return events


def frontend_result(
    pollster: str,
    margin: int | float,
    *,
    source_url: str = "https://example.test/source",
    fieldwork_end: str | None = None,
    candidates: tuple[str, str] = PHILIPPE_LE_PEN,
) -> dict:
    result = {
        "event_id": pollster.casefold().replace(" ", "-"),
        "pollster": pollster,
        "candidates": [
            {"name": candidates[0], "score": 50 + margin / 2},
            {"name": candidates[1], "score": 50 - margin / 2},
        ],
        "margin": margin,
        "source_url": source_url,
    }
    if fieldwork_end is not None:
        result["fieldwork_end"] = fieldwork_end
    return result


def agreed_payload(results: list[dict] | None = None) -> dict:
    results = results or [
        frontend_result("Ifop", 4),
        frontend_result("Ipsos", 6, source_url="https://example.test/ipsos"),
    ]
    selected_key = "selected-key"
    selected = {
        "matchup_key": selected_key,
        "candidates": list(PHILIPPE_LE_PEN),
        "results": results,
    }
    return {
        "status": "agree",
        "message": "Pollsters agree on the closest tested runoff",
        "disclosure": "Source-reported second-round observations.",
        "fieldwork_window": {"start": "2026-07-01", "end": "2026-07-02"},
        "pollster_count": len({item["pollster"] for item in results}),
        "common_matchup_count": 1,
        "selected_matchup": selected,
        "pollsters": [],
        "common_matchups": [selected],
    }


def unresolved_payload(status: str) -> dict:
    result = frontend_result("Ifop", 4)
    return {
        "status": status,
        "message": f"Synthetic {status} characterization",
        "disclosure": "Source-reported second-round observations.",
        "fieldwork_window": {"start": "2026-07-01", "end": "2026-07-02"},
        "pollster_count": 2,
        "common_matchup_count": 2,
        "selected_matchup": None,
        "pollsters": [
            {
                "pollster": "Ifop",
                "closest_matchups": [
                    {
                        "matchup_key": "selected-key",
                        "candidates": list(PHILIPPE_LE_PEN),
                        "result": result,
                    }
                ],
            }
        ],
        "common_matchups": [],
    }


def run_runoff_script(payload: dict | None, expression: str, *, load_state: str = "ready"):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node.js is required for frontend contract tests")
    script = r'''
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8");
source = source.replace(
  /\s+retainLegacyComparison\(\);\s+renderAll\(\);\s+window\.addEventListener\("hashchange", handleSignalHashChange\);\s+document\.addEventListener\("hybrid:dataset", renderAll\);/,
  ""
);
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const mount = {};
const safeSourceUrl = value => {
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch (_error) {
    return "";
  }
};
const formatRunoffFieldwork = value => {
  const start = new Date(`${value.start}T00:00:00Z`);
  const end = new Date(`${value.end}T00:00:00Z`);
  const day = date => new Intl.DateTimeFormat("en-GB", { day: "numeric", timeZone: "UTC" }).format(date);
  const month = date => new Intl.DateTimeFormat("en-GB", { month: "short", timeZone: "UTC" }).format(date).toUpperCase();
  const year = date => new Intl.DateTimeFormat("en-GB", { year: "numeric", timeZone: "UTC" }).format(date);
  if (value.start === value.end) return `${day(start)} ${month(start)} ${year(start)}`;
  if (start.getUTCFullYear() === end.getUTCFullYear() && start.getUTCMonth() === end.getUTCMonth()) {
    return `${day(start)}–${day(end)} ${month(end)} ${year(end)}`;
  }
  return `${day(start)} ${month(start)} ${year(start) === year(end) ? "" : year(start)}–${day(end)} ${month(end)} ${year(end)}`.replace(/\s+–/, "–");
};
const context = {
  console,
  URL,
  Date,
  Math,
  Map,
  Set,
  Object,
  Array,
  Number,
  String,
  JSON,
  Intl,
  window: { location: { hash: "" }, addEventListener() {} },
  document: {
    getElementById(id) { return id === "hybrid-signal-board" ? mount : null; },
    addEventListener() {},
    querySelector() { return null; }
  },
  dashboardState: {
    loadState: {
      runoff: input.loadState,
      news: "error",
      agenda: "error",
      claims: "error"
    },
    runoff: input.payload,
    news: null,
    agenda: null,
    claims: null
  },
  candidatePortraits: {},
  newestNewsItems: values => values,
  formatScore: value => Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`,
  formatDate: value => String(value),
  escapeHtml: value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]),
  escapeAttribute: value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]),
  formatNewsDateTime: value => String(value),
  formatRunoffFieldwork,
  safeSourceUrl
};
vm.runInNewContext(source, context);
const api = context.window.hybridDashboard;
const result = eval(input.expression);
process.stdout.write(JSON.stringify(result));
'''
    completed = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {"payload": payload, "expression": expression, "loadState": load_state}
        ),
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class RunoffBackendDerivationTests(unittest.TestCase):
    def test_one_pollster_is_insufficient(self):
        result = derive_closest_tested_runoff(
            qualifying_events({"Ifop": (2, 8)})
        )
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["pollster_count"], 0)

    def test_two_pollsters_with_same_unique_closest_matchup_agree(self):
        result = derive_closest_tested_runoff(
            qualifying_events({"Ifop": (2, 8), "Ipsos": (4, 10)})
        )
        self.assertEqual(result["status"], "agree")
        self.assertEqual(result["pollster_count"], 2)
        self.assertEqual(
            result["selected_matchup"]["matchup_key"],
            make_scenario_key(PHILIPPE_LE_PEN, round_name=SECOND_ROUND),
        )

    def test_three_and_more_pollsters_are_supported(self):
        for count in (3, 4):
            with self.subTest(count=count):
                margins = {
                    f"Pollster {index}": (2 + index, 10 + index)
                    for index in range(count)
                }
                result = derive_closest_tested_runoff(qualifying_events(margins))
                self.assertEqual(result["status"], "agree")
                self.assertEqual(result["pollster_count"], count)
                self.assertIn(f"All {count} pollsters", result["message"])

    def test_different_unique_closest_matchups_split(self):
        result = derive_closest_tested_runoff(
            qualifying_events({"Ifop": (2, 8), "Ipsos": (10, 4)})
        )
        self.assertEqual(result["status"], "split")
        self.assertIsNone(result["selected_matchup"])

    def test_tied_pollster_minimum_is_ambiguous(self):
        result = derive_closest_tested_runoff(
            qualifying_events({"Ifop": (4, 4), "Ipsos": (2, 8)})
        )
        self.assertEqual(result["status"], "ambiguous")
        ifop = next(item for item in result["pollsters"] if item["pollster"] == "Ifop")
        self.assertEqual(len(ifop["closest_matchups"]), 2)

    def test_duplicate_pollster_matchup_and_window_is_rejected(self):
        events = qualifying_events({"Ifop": (2, 8), "Ipsos": (4, 10)})
        events.append(copy.deepcopy(events[0]))
        with self.assertRaisesRegex(ValueError, "duplicate pollster/matchup"):
            derive_closest_tested_runoff(events)

    def test_same_pollster_can_contribute_different_matchup_hypotheses(self):
        result = derive_closest_tested_runoff(
            qualifying_events({"Ifop": (2, 8), "Ipsos": (4, 10)})
        )
        ifop_matchups = {
            item["matchup_key"]
            for item in result["common_matchups"]
            for observation in item["results"]
            if observation["pollster"] == "Ifop"
        }
        self.assertEqual(len(ifop_matchups), 2)

    def test_exactly_matching_fieldwork_windows_qualify(self):
        result = derive_closest_tested_runoff(
            qualifying_events(
                {"Ifop": (2, 8), "Ipsos": (4, 10)},
                start="2026-07-03",
                end="2026-07-05",
            )
        )
        self.assertEqual(result["status"], "agree")
        self.assertEqual(
            result["fieldwork_window"],
            {"start": "2026-07-03", "end": "2026-07-05"},
        )

    def test_partially_overlapping_windows_are_not_shared(self):
        events = qualifying_events(
            {"Ifop": (2, 8)}, start="2026-07-01", end="2026-07-03"
        )
        events += qualifying_events(
            {"Ipsos": (4, 10)}, start="2026-07-02", end="2026-07-03"
        )
        self.assertEqual(derive_closest_tested_runoff(events)["status"], "insufficient")

    def test_non_overlapping_windows_do_not_qualify(self):
        events = qualifying_events(
            {"Ifop": (2, 8)}, start="2026-07-01", end="2026-07-02"
        )
        events += qualifying_events(
            {"Ipsos": (4, 10)}, start="2026-07-05", end="2026-07-06"
        )
        self.assertEqual(derive_closest_tested_runoff(events)["status"], "insufficient")

    def test_newer_invalid_window_falls_back_to_older_exact_window(self):
        older = qualifying_events(
            {"Ifop": (2, 8), "Ipsos": (4, 10)},
            start="2026-07-01",
            end="2026-07-02",
        )
        newer = [
            margin_event(
                pollster,
                PHILIPPE_LE_PEN,
                margin,
                start="2026-07-10",
                end="2026-07-11",
            )
            for pollster, margin in (("Ifop", 1), ("Ipsos", 3))
        ]
        result = derive_closest_tested_runoff(newer + older)
        self.assertEqual(result["status"], "agree")
        self.assertEqual(
            result["fieldwork_window"],
            {"start": "2026-07-01", "end": "2026-07-02"},
        )

    def test_fewer_than_two_common_matchup_keys_is_insufficient(self):
        events = [
            margin_event("Ifop", PHILIPPE_LE_PEN, 2),
            margin_event("Ifop", BARDella_ATTAL, 8),
            margin_event("Ipsos", PHILIPPE_LE_PEN, 4),
            margin_event("Ipsos", GLUCKSMANN_ZEMMOUR, 6),
        ]
        self.assertEqual(derive_closest_tested_runoff(events)["status"], "insufficient")

    def test_equal_candidate_scores_validate_with_zero_margin(self):
        event = second_round_event("Ifop", PHILIPPE_LE_PEN, 50, 50)
        self.assertEqual(event["margin"], 0)
        validate_second_round_event(event)

    def test_margin_is_absolute_score_difference(self):
        event = second_round_event("Ifop", PHILIPPE_LE_PEN, 47, 53)
        self.assertEqual(event["margin"], 6)
        validate_second_round_event(event)
        event["margin"] = -6
        with self.assertRaisesRegex(ValueError, "margin does not match"):
            validate_second_round_event(event)

    def test_matchup_identity_is_independent_of_candidate_order(self):
        forward = second_round_event("Ifop", PHILIPPE_LE_PEN, 47, 53)
        reverse = second_round_event("Ifop", tuple(reversed(PHILIPPE_LE_PEN)), 53, 47)
        self.assertEqual(forward["matchup_key"], reverse["matchup_key"])

    def test_selected_matchup_and_output_order_are_deterministic(self):
        events = qualifying_events(
            {"Zulu Polls": (3, 9), "alpha polls": (5, 11), "Beta Polls": (4, 10)}
        )
        first = derive_closest_tested_runoff(events)
        second = derive_closest_tested_runoff(list(reversed(events)))
        self.assertEqual(first, second)
        self.assertEqual(
            [item["pollster"] for item in first["pollsters"]],
            ["alpha polls", "Beta Polls", "Zulu Polls"],
        )
        self.assertEqual(
            [item["matchup_key"] for item in first["common_matchups"]],
            sorted(item["matchup_key"] for item in first["common_matchups"]),
        )

    def test_ties_do_not_depend_on_input_or_set_order(self):
        events = qualifying_events({"Ifop": (4, 4), "Ipsos": (2, 8)})
        expected = derive_closest_tested_runoff(events)
        for permutation in itertools.permutations(events):
            self.assertEqual(derive_closest_tested_runoff(list(permutation)), expected)


class RunoffFrontendContractTests(unittest.TestCase):
    def build_and_render(self, payload: dict) -> dict:
        return run_runoff_script(
            payload,
            "(() => { const model = api.buildRunoffViewModel(); return { model, html: api.renderRunoffPanel(model) }; })()",
        )

    def test_source_reported_observations_render_separately(self):
        output = self.build_and_render(
            agreed_payload(
                [frontend_result("Ifop", 3), frontend_result("Ipsos", 7)]
            )
        )
        self.assertEqual(output["html"].count('<article class="hybrid-observation'), 2)
        self.assertEqual(output["html"].count("Separate observation"), 1)
        self.assertIn(
            "Individual source-reported results and margins are shown separately",
            output["html"],
        )

    def test_two_three_and_more_observations_are_supported(self):
        for count in (2, 3, 4):
            with self.subTest(count=count):
                results = [
                    frontend_result(f"Pollster {index}", index + 1)
                    for index in range(count)
                ]
                output = self.build_and_render(agreed_payload(results))
                self.assertEqual(output["model"]["selectedMatchup"]["observationCount"], count)
                self.assertEqual(output["html"].count('<article class="hybrid-observation'), count)

    def test_smallest_observation_is_featured(self):
        output = self.build_and_render(
            agreed_payload(
                [
                    frontend_result("Largest", 9),
                    frontend_result("Smallest", 1),
                    frontend_result("Middle", 5),
                ]
            )
        )
        self.assertEqual(output["model"]["featuredObservation"]["pollster"], "Smallest")
        featured = re.search(r'<article class="hybrid-observation is-featured">(.*?)</article>', output["html"], re.DOTALL)
        self.assertIsNotNone(featured)
        self.assertIn("Smallest", featured.group(1))

    def test_featured_ties_use_newest_date_then_source_order(self):
        dated = self.build_and_render(
            agreed_payload(
                [
                    frontend_result("Older", 2, fieldwork_end="2026-07-01"),
                    frontend_result("Newer", 2, fieldwork_end="2026-07-03"),
                ]
            )
        )
        self.assertEqual(dated["model"]["featuredObservation"]["pollster"], "Newer")
        same_date = self.build_and_render(
            agreed_payload(
                [
                    frontend_result("First", 2, fieldwork_end="2026-07-03"),
                    frontend_result("Second", 2, fieldwork_end="2026-07-03"),
                ]
            )
        )
        self.assertEqual(same_date["model"]["featuredObservation"]["pollster"], "First")

    def test_observation_count_comes_from_displayed_records(self):
        payload = agreed_payload(
            [frontend_result("Ifop", 2), frontend_result("Ipsos", 4), frontend_result("Elabe", 6)]
        )
        payload["observation_count"] = 99
        output = self.build_and_render(payload)
        self.assertEqual(output["model"]["selectedMatchup"]["observationCount"], 3)
        self.assertIn("3 supporting source-reported observations", output["html"])

    def test_distinct_pollster_count_follows_published_contract(self):
        payload = agreed_payload(
            [frontend_result("Ifop", 2), frontend_result("Ifop", 4), frontend_result("Ipsos", 6)]
        )
        payload["pollster_count"] = 2
        output = self.build_and_render(payload)
        self.assertEqual(output["model"]["pollsterCount"], 2)
        self.assertIn("2 pollsters", output["html"])
        self.assertEqual(output["model"]["selectedMatchup"]["observationCount"], 3)

    def test_http_and_https_sources_render_as_links(self):
        output = self.build_and_render(
            agreed_payload(
                [
                    frontend_result("HTTP", 2, source_url="http://example.test/http"),
                    frontend_result("HTTPS", 4, source_url="https://example.test/https"),
                ]
            )
        )
        self.assertIn('href="http://example.test/http"', output["html"])
        self.assertIn('href="https://example.test/https"', output["html"])
        self.assertEqual(output["model"]["selectedMatchup"]["sourceCount"], 2)

    def test_missing_and_invalid_urls_render_source_unavailable(self):
        output = self.build_and_render(
            agreed_payload(
                [
                    frontend_result("Missing", 2, source_url=""),
                    frontend_result("Invalid", 4, source_url="javascript:alert(1)"),
                    frontend_result("Valid", 6, source_url="https://example.test/valid"),
                ]
            )
        )
        self.assertEqual(output["html"].count("Source unavailable"), 2)
        self.assertNotIn("javascript:", output["html"])
        self.assertEqual(output["model"]["selectedMatchup"]["sourceCount"], 1)

    def test_supported_unresolved_malformed_and_failed_load_states_do_not_throw(self):
        cases = [
            ("agree", agreed_payload(), "ready"),
            ("split", unresolved_payload("split"), "ready"),
            ("ambiguous", unresolved_payload("ambiguous"), "ready"),
            ("insufficient", unresolved_payload("insufficient"), "ready"),
            ("malformed", {}, "ready"),
            ("failed-load", None, "error"),
        ]
        for name, payload, load_state in cases:
            with self.subTest(name=name):
                output = run_runoff_script(
                    payload,
                    "(() => { const model = api.buildRunoffViewModel(); return { state: model.state, html: api.renderRunoffPanel(model) }; })()",
                    load_state=load_state,
                )
                self.assertIsInstance(output["html"], str)
                self.assertTrue(output["html"])

    def test_equal_scores_render_without_winner_or_leader_language(self):
        equal = frontend_result("Tie Poll", 0)
        output = self.build_and_render(agreed_payload([equal, copy.deepcopy(equal)]))
        html = output["html"].casefold()
        self.assertIn("reported margin 0 pts", html)
        self.assertNotRegex(html, r"\b(winner|leader|leading|ahead)\b")

    def test_alternative_matchups_preserve_published_order(self):
        payload = agreed_payload()
        alternatives = [
            {
                "matchup_key": "alternative-a",
                "candidates": list(BARDella_ATTAL),
                "results": [frontend_result("Ifop", 4, candidates=BARDella_ATTAL)],
            },
            {
                "matchup_key": "alternative-b",
                "candidates": list(GLUCKSMANN_ZEMMOUR),
                "results": [frontend_result("Ipsos", 6, candidates=GLUCKSMANN_ZEMMOUR)],
            },
        ]
        payload["common_matchups"] += alternatives
        output = self.build_and_render(payload)
        self.assertEqual(
            [item["matchup_key"] for item in output["model"]["commonMatchups"]],
            ["selected-key", "alternative-a", "alternative-b"],
        )
        self.assertLess(
            output["html"].index("Jordan Bardella vs Gabriel Attal"),
            output["html"].index("Raphaël Glucksmann vs Éric Zemmour"),
        )

    def test_exact_fieldwork_wording_is_preserved(self):
        output = self.build_and_render(agreed_payload())
        self.assertIn("Shared fieldwork window: 1–2 JUL 2026", output["html"])

    def test_active_output_has_no_average_metric(self):
        html = self.build_and_render(agreed_payload())["html"]
        self.assertIn("no average", html)
        self.assertNotIn("hybrid-runoff-average", html)
        self.assertNotRegex(html, r"(?i)average\s*<strong>\s*[-+]?\d")

    def test_active_output_has_no_forecast_metric(self):
        html = self.build_and_render(agreed_payload())["html"]
        self.assertIn("not a forecast", html)
        self.assertNotIn("hybrid-runoff-forecast", html)
        self.assertNotRegex(html, r"(?i)forecast\s*<strong>\s*[-+]?\d")

    def test_active_output_has_no_probability_metric(self):
        html = self.build_and_render(agreed_payload())["html"]
        self.assertIn("no average or probability", html)
        self.assertNotIn("hybrid-runoff-probability", html)
        self.assertNotRegex(html, r"(?i)probability\s*<strong>\s*[-+]?\d")

    def test_active_output_has_no_momentum_score(self):
        html = self.build_and_render(agreed_payload())["html"].casefold()
        self.assertNotIn("momentum", html)

    def test_active_output_has_no_synthetic_ranking(self):
        html = self.build_and_render(agreed_payload())["html"].casefold()
        self.assertNotIn("synthetic", html)
        self.assertNotIn("ranking", html)

    def test_active_output_has_no_inferred_winner_or_leader_label(self):
        html = self.build_and_render(agreed_payload())["html"].casefold()
        self.assertNotRegex(html, r"\b(winner|leader|leading)\b")

    def test_rendering_does_not_mutate_supplied_payload(self):
        result = run_runoff_script(
            agreed_payload(),
            "(() => { const before = JSON.stringify(context.dashboardState.runoff); const model = api.buildRunoffViewModel(); api.renderRunoffSummary(model); api.renderRunoffPanel(model); return { unchanged: before === JSON.stringify(context.dashboardState.runoff) }; })()",
        )
        self.assertTrue(result["unchanged"])

    def test_runoff_failure_model_is_isolated_from_other_workspace_models(self):
        output = run_runoff_script(
            None,
            "(() => { const runoff = api.buildRunoffViewModel(); const html = api.renderFocusWorkspace({ runoff, agenda: { state: 'empty', message: 'Agenda remains isolated' }, claims: { state: 'empty', message: 'Claims remain isolated' } }); return { runoff, html }; })()",
            load_state="error",
        )
        self.assertEqual(output["runoff"]["state"], "unavailable")
        for contract in (
            "This data domain is unavailable",
            "candidate-signals-root",
            "Campaign Events is not yet available",
            "Agenda remains isolated",
            "Claims remain isolated",
            'aria-controls="polling-evidence-lab"',
        ):
            self.assertIn(contract, output["html"])


class RunoffIsolationAndStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.js = HYBRID_JS.read_text(encoding="utf-8")
        cls.css = HYBRID_CSS.read_text(encoding="utf-8")

    def test_tab_panel_hash_and_aria_contract_is_stable(self):
        runoff_config = re.search(
            r"runoff:\s*\{(?P<body>.*?)\n\s*\},\n\s*candidates:",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(runoff_config)
        for contract in (
            'hash: "#signal-runoff"',
            'tabId: "signal-runoff-tab"',
            'panelId: "signal-runoff-panel"',
        ):
            self.assertIn(contract, runoff_config.group("body"))
        self.assertIn('id="signal-runoff-panel" role="tabpanel" aria-labelledby="signal-runoff-tab"', self.js)
        self.assertIn('data-hybrid-view="${key}" aria-controls="${views[key].panelId}"', self.js)

    def test_active_runoff_selectors_keep_hybrid_naming_scheme(self):
        selectors = re.findall(r"(?m)^([^@\n][^\n{]*runoff[^\n{]*)\{", self.css)
        self.assertTrue(selectors)
        for selector_group in selectors:
            for selector in selector_group.split(","):
                selector = selector.strip()
                if selector:
                    self.assertTrue(
                        selector.startswith(".hybrid-"),
                        f"Runoff selector escaped hybrid scope: {selector}",
                    )

    def test_runoff_introduces_no_global_css_or_global_event_listener(self):
        runoff_css = "\n".join(
            line for line in self.css.splitlines() if "runoff" in line.casefold()
        )
        self.assertNotRegex(runoff_css, r"(?m)^\s*(?:html|body|:root|\*)\b")
        runoff_source = self._runoff_source()
        self.assertNotIn("addEventListener", runoff_source)
        self.assertEqual(self.js.count('window.addEventListener("hashchange", handleSignalHashChange);'), 1)
        self.assertEqual(self.js.count('document.addEventListener("hybrid:dataset", renderAll);'), 1)

    def test_narrow_runoff_grids_retain_one_column_fallback(self):
        narrow = re.search(r"@media \(max-width: 679px\) \{(?P<body>.*?)\n\}", self.css, re.DOTALL)
        self.assertIsNotNone(narrow)
        self.assertRegex(
            narrow.group("body"),
            r"\.hybrid-runoff-observations,\s*\n\s*\.hybrid-common-grid\s*\{\s*grid-template-columns:\s*1fr;",
        )

    def test_runoff_implementation_does_not_reference_candidate_workspace_sources(self):
        source = self._runoff_source().casefold()
        for forbidden in (
            "candidate-signals.js",
            "candidate-signals-workspace.js",
            "candidate-signals.css",
            "candidate_signals.json",
            "france2027candidatesignals",
        ):
            self.assertNotIn(forbidden, source)

    def test_active_renderer_is_separate_from_derived_aggregate_metrics(self):
        source = self._runoff_source()
        for forbidden in (
            ".reduce(",
            "Math.random",
            "calculateAverage",
            "calculateForecast",
            "calculateProbability",
            "momentumScore",
            "syntheticRanking",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("number(a.margin) - number(b.margin)", source)
        self.assertIn("Individual source-reported results and margins are shown separately", source)

    def _runoff_source(self) -> str:
        model_start = self.js.index("function buildRunoffViewModel()")
        model_end = self.js.index("function utcDateKey", model_start)
        summary_start = self.js.index("function renderRunoffSummary(")
        summary_end = self.js.index("function activityBars", summary_start)
        panel_start = self.js.index("function sourceLink(")
        panel_end = self.js.index("function renderMediaPanel", panel_start)
        return (
            self.js[model_start:model_end]
            + self.js[summary_start:summary_end]
            + self.js[panel_start:panel_end]
        )


if __name__ == "__main__":
    unittest.main()
