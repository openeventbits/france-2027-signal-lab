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
RUNOFF_ARCHIVE = ROOT / "second_round_polls.json"
RUNOFF_DERIVED = ROOT / "closest_tested_runoff.json"

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


def run_runoff_script(
    payload: dict | None,
    expression: str,
    *,
    load_state: str = "ready",
    archive_state: dict | None = None,
):
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
Promise.resolve(eval(input.expression))
  .then(result => process.stdout.write(JSON.stringify(result)))
  .catch(error => {
    process.stderr.write(error.stack);
    process.exitCode = 1;
  });
'''
    completed = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {
                "payload": payload,
                "expression": expression,
                "loadState": load_state,
                "archiveState": archive_state,
            }
        ),
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def run_runoff_loader(
    payload: dict | None,
    *,
    fetch_mode: str = "success",
    legacy_throws: bool = False,
) -> dict:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node.js is required for frontend contract tests")
    script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("index.html", "utf8").replace(/\r\n?/g, "\n");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const extract = (startMarker, endMarker) => {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error(`Could not extract ${startMarker}`);
  return source.slice(start, end);
};
const markDatasetSource = extract(
  "    function markDataset(",
  "\n\n    function dashboardTimestamp"
);
const validationSource = extract(
  "    function isValidRunoffResult(",
  "\n\n    function runoffSourceLink"
);
const loaderSource = extract(
  "    function loadClosestRunoff(",
  "\n\n    function candidateScore"
);
const warnings = [];
const events = [];
const publishedPayloads = [];
const legacyCalls = [];
const elements = new Map();
const otherState = {
  candidates: { sentinel: "candidates" },
  events: { sentinel: "events" },
  agenda: { sentinel: "agenda" },
  claims: { sentinel: "claims" },
  pollCompare: { sentinel: "poll-compare" }
};
const dashboardState = {
  ...otherState,
  runoff: null,
  loadState: {
    candidates: "loaded",
    events: "loaded",
    agenda: "loaded",
    claims: "loaded",
    pollCompare: "loaded",
    runoff: "loading"
  },
  updatedAt: {}
};
const otherStateBefore = JSON.stringify(otherState);
const document = {
  documentElement: { dataset: {} },
  querySelector(selector) {
    if (!elements.has(selector)) {
      elements.set(selector, { hidden: true, className: "", textContent: "", innerHTML: "" });
    }
    return elements.get(selector);
  },
  dispatchEvent(event) {
    events.push(event.detail);
    if (event.detail.name === "runoff" && event.detail.status === "loaded") {
      publishedPayloads.push(dashboardState.runoff);
    }
  }
};
const fetch = () => {
  if (input.fetchMode === "reject") {
    return Promise.reject(new Error("synthetic fetch failure"));
  }
  return Promise.resolve({
    ok: true,
    status: 200,
    json() {
      if (input.fetchMode === "invalid-json") {
        return Promise.reject(new SyntaxError("synthetic invalid JSON"));
      }
      return Promise.resolve(input.payload);
    }
  });
};
const context = {
  URL,
  Set,
  Number,
  Promise,
  dashboardState,
  document,
  CustomEvent: class CustomEvent {
    constructor(_name, options) { this.detail = options.detail; }
  },
  fetch,
  $: selector => document.querySelector(selector),
  escapeHtml: value => String(value ?? ""),
  safeSourceUrl(value) {
    try {
      const url = new URL(String(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_error) {
      return "";
    }
  },
  renderMastheadMetadata() {},
  renderContextStrip() {},
  renderWhatChanged() {},
  renderClosestRunoff(value) {
    legacyCalls.push({
      payload: value,
      state: dashboardState.loadState.runoff,
      publishedCount: publishedPayloads.length
    });
    if (input.legacyThrows) throw new Error("synthetic legacy render failure");
    document.documentElement.dataset.runoffReady = value.status;
  },
  console: {
    warn(...values) {
      warnings.push(values.map(value => value instanceof Error ? value.message : String(value)));
    }
  }
};
vm.runInNewContext(
  [markDatasetSource, validationSource, loaderSource].join("\n"),
  context
);
(async () => {
  await context.loadClosestRunoff();
  const otherStateAfter = {
    candidates: dashboardState.candidates,
    events: dashboardState.events,
    agenda: dashboardState.agenda,
    claims: dashboardState.claims,
    pollCompare: dashboardState.pollCompare
  };
  process.stdout.write(JSON.stringify({
    runoff: dashboardState.runoff,
    runoffState: dashboardState.loadState.runoff,
    updatedAt: dashboardState.updatedAt.runoff || null,
    events,
    publishedPayloads,
    legacyCalls,
    warnings,
    documentRunoffReady: document.documentElement.dataset.runoffReady || null,
    unavailableHtml: elements.get("#closest-runoff-hero")?.innerHTML || null,
    otherStateUnchanged: otherStateBefore === JSON.stringify(otherStateAfter),
    errorStates: Object.entries(dashboardState.loadState)
      .filter(([_name, status]) => status === "error")
      .map(([name]) => name)
  }));
})().catch(error => {
  process.stderr.write(error.stack);
  process.exitCode = 1;
});
'''
    completed = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {
                "payload": payload,
                "fetchMode": fetch_mode,
                "legacyThrows": legacy_throws,
            }
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
    @classmethod
    def setUpClass(cls):
        cls.derived = json.loads(RUNOFF_DERIVED.read_text(encoding="utf-8"))
        cls.archive_payload = json.loads(RUNOFF_ARCHIVE.read_text(encoding="utf-8"))
        cls.archive_state = {"status": "ready", "events": cls.archive_payload["events"], "error": ""}

    def build_and_render(
        self,
        payload: dict,
        archive_state: dict | None = None,
    ) -> dict:
        return run_runoff_script(
            payload,
            "(() => { const model = api.buildRunoffViewModel(input.archiveState || undefined); return { model, html: api.renderRunoffPanel(model) }; })()",
            archive_state=archive_state,
        )

    def render_real(self) -> dict:
        return self.build_and_render(self.derived, self.archive_state)

    def test_current_comparison_uses_exact_source_separated_evidence(self):
        output = self.render_real()
        html = output["html"]
        observations = output["model"]["selectedMatchup"]["observations"]
        self.assertEqual([item["pollster"] for item in observations], ["Harris Interactive", "Ifop"])
        self.assertEqual([item["sampleSize"] for item in observations], [1582, 984])
        for exact in (
            "Édouard Philippe vs Marine Le Pen",
            "49%",
            "51%",
            "46%",
            "54%",
            "hybrid-runoff-margin-tile",
            "NARROWEST OBSERVED MARGIN · 2 PTS",
            "n=1,582",
            "n=984",
            "7–8 Jul 2026",
            "50 percent centre reference",
        ):
            self.assertIn(exact, html)
        self.assertEqual(html.count('class="hybrid-observation hybrid-runoff-source-observation"'), 2)
        self.assertEqual(html.count('class="hybrid-runoff-margin-tile"'), 2)
        self.assertEqual(html.count('target="_blank" rel="noopener noreferrer"'), 16)
        self.assertEqual(html.count('is-compact is-icon-only'), 16)
        self.assertIn('class="hybrid-runoff-title-icon"', html)
        self.assertIn('class="hybrid-runoff-inline-icon"', html)
        self.assertIn("Both pollsters agree this is the closest tested runoff", html)

    def test_raw_join_is_event_id_only_and_does_not_mutate_payloads(self):
        derived = copy.deepcopy(self.derived)
        archive_state = copy.deepcopy(self.archive_state)
        before_derived = json.dumps(derived, ensure_ascii=False, sort_keys=True)
        before_archive = json.dumps(archive_state, ensure_ascii=False, sort_keys=True)
        derived["selected_matchup"]["results"][0]["event_id"] = "not-an-archive-event"
        for matchup in derived["common_matchups"]:
            if matchup["matchup_key"] == derived["selected_matchup"]["matchup_key"]:
                matchup["results"][0]["event_id"] = "not-an-archive-event"
        output = self.build_and_render(derived, archive_state)
        self.assertIsNone(output["model"]["selectedMatchup"]["observations"][0]["sampleSize"])
        self.assertFalse(output["model"]["selectedMatchup"]["observations"][0]["archiveMatched"])
        self.assertEqual(before_archive, json.dumps(archive_state, ensure_ascii=False, sort_keys=True))
        self.assertNotEqual(before_derived, json.dumps(derived, ensure_ascii=False, sort_keys=True))
        unchanged = run_runoff_script(
            self.derived,
            "(() => { const before = JSON.stringify(context.dashboardState.runoff); const rawBefore = JSON.stringify(input.archiveState); const model = api.buildRunoffViewModel(input.archiveState); api.renderRunoffPanel(model); return { derived: before === JSON.stringify(context.dashboardState.runoff), raw: rawBefore === JSON.stringify(input.archiveState) }; })()",
            archive_state=self.archive_state,
        )
        self.assertEqual(unchanged, {"derived": True, "raw": True})

    def test_raw_failure_is_local_and_current_comparison_survives(self):
        output = self.build_and_render(
            self.derived,
            {"status": "unavailable", "events": [], "error": "synthetic"},
        )
        html = output["html"]
        self.assertEqual(output["model"]["status"], "agree")
        self.assertEqual(len(output["model"]["selectedMatchup"]["observations"]), 2)
        self.assertIn("49%", html)
        self.assertIn("54%", html)
        self.assertIn("Archive coverage and history are locally unavailable", html)
        self.assertNotIn("n=1,582", html)

    def test_current_common_matchups_and_selected_structure_are_exact(self):
        output = self.render_real()
        html = output["html"]
        self.assertEqual(len(output["model"]["commonMatchups"]), 3)
        for matchup in (
            "Édouard Philippe vs Marine Le Pen",
            "Gabriel Attal vs Marine Le Pen",
            "Jean-Luc Mélenchon vs Marine Le Pen",
        ):
            self.assertIn(matchup, html)
        self.assertIn("CLOSEST COMMON MATCHUP", html)
        self.assertIn("<strong>2 / 8</strong><small>pts</small>", html)
        self.assertIn("<strong>10 / 10</strong><small>pts</small>", html)
        self.assertIn("<strong>34 / 40</strong><small>pts</small>", html)
        self.assertEqual(html.count('class="hybrid-runoff-compact-rail"'), 12)
        for forbidden in ("🏆", "winner", "leader", "favored", "advantage", "Smallest reported margin"):
            self.assertNotIn(forbidden.casefold(), html.casefold())

    def test_archive_history_and_remaining_matchups_are_complete(self):
        output = self.render_real()
        model = output["model"]
        html = output["html"]
        footprint = model["archive"]["footprint"]
        self.assertEqual(
            {key: footprint[key] for key in ("observationCount", "matchupCount", "pollsterCount", "windowCount")},
            {"observationCount": 38, "matchupCount": 9, "pollsterCount": 6, "windowCount": 11},
        )
        self.assertEqual(model["archive"]["selectedHistoryKey"], self.derived["selected_matchup"]["matchup_key"])
        self.assertEqual(len(model["archive"]["history"]), 8)
        self.assertEqual(len(model["archive"]["otherMatchups"]), 6)
        self.assertIn("31 Jan–1 Feb 2024", html)
        self.assertIn("7–8 Jul 2026", html)
        for matchup in (
            "Édouard Philippe vs Jordan Bardella",
            "Gabriel Attal vs Jordan Bardella",
            "Jean-Luc Mélenchon vs Jordan Bardella",
            "Bruno Retailleau vs Jordan Bardella",
            "Raphaël Glucksmann vs Jordan Bardella",
            "François Ruffin vs Marine Le Pen",
        ):
            self.assertIn(matchup, html)
        self.assertIn("SELECTED MATCHUP HISTORY", html)
        self.assertIn('aria-label="8 exact source observations"', html)
        self.assertEqual(html.count('class="hybrid-runoff-history-entry"'), 8)
        self.assertEqual(html.count('class="hybrid-runoff-history-position'), 8)
        self.assertEqual(html.count('hybrid-runoff-history-position is-paired'), 0)
        self.assertNotIn("Each mark is a separate source observation · marks are not connected", html)
        self.assertNotIn('<dl class="hybrid-runoff-footprint-grid">', html)
        self.assertNotIn("EVIDENCE FOOTPRINT", html)
        self.assertIn("OTHER TESTED MATCHUPS", html)

    def test_other_tested_matchups_keep_populated_desktop_rows(self):
        html = self.render_real()["html"]
        cards = re.findall(
            r'<article class="hybrid-runoff-other-card".*?</article>',
            html,
            re.DOTALL,
        )

        self.assertEqual(len(cards), 6)
        for card in cards:
            with self.subTest(card=card[:100]):
                self.assertRegex(
                    card,
                    r"<strong>\d+(?:\.\d+)?%</strong>[\s\S]*"
                    r"<strong>\d+(?:\.\d+)?%</strong>",
                )

        density = HYBRID_CSS.read_text(encoding="utf-8").split(
            "/* RUNOFF PANEL 3 DENSITY V4: START */",
            1,
        )[1].split(
            "/* RUNOFF PANEL 3 DENSITY V4: END */",
            1,
        )[0]
        self.assertIn("@media (min-width: 1024px)", density)
        self.assertIn("flex: 0 0 38px !important;", density)
        self.assertIn(
            "grid-template-rows: minmax(0, 1fr) !important;",
            density,
        )
        self.assertNotIn(
            "grid-template-rows: minmax(68px, 1fr)",
            density,
        )

    def test_history_window_grouping_is_exact_deterministic_and_non_mutating(self):
        output = run_runoff_script(
            self.derived,
            "(() => { const model = api.buildRunoffViewModel(input.archiveState); const before = JSON.stringify(model.archive.history); const groups = api.groupRunoffHistoryWindows(model.archive.history); return { unchanged: before === JSON.stringify(model.archive.history), count: groups.length, sizes: groups.map(group => group.observations.length), keys: groups.map(group => group.key), finalPollsters: groups.at(-1).observations.map(item => item.pollster) }; })()",
            archive_state=self.archive_state,
        )
        self.assertTrue(output["unchanged"])
        self.assertEqual(output["count"], 7)
        self.assertEqual(output["sizes"], [1, 1, 1, 1, 1, 1, 2])
        self.assertEqual(len(output["keys"]), len(set(output["keys"])))
        self.assertEqual(output["finalPollsters"], ["Harris Interactive", "Ifop"])
    def test_history_accepts_an_exact_matchup_key(self):
        target = "78ee22bdc7b20f010e4240afc3268ceb9f2bdb50e8a49b6be5fccd3c5f8e77f9"
        output = run_runoff_script(
            self.derived,
            "(() => { const archive = api.buildRunoffArchiveModel(input.archiveState, [], '" + target + "'); return { key: archive.selectedHistoryKey, count: archive.history.length, matchup: archive.matchups.find(item => item.key === archive.selectedHistoryKey).candidates }; })()",
            archive_state=self.archive_state,
        )
        self.assertEqual(output, {"key": target, "count": 1, "matchup": ["François Ruffin", "Marine Le Pen"]})

    def test_status_fallbacks_never_fabricate_a_shared_selection(self):
        split = self.build_and_render(unresolved_payload("split"))["html"]
        ambiguous = self.build_and_render(unresolved_payload("ambiguous"))["html"]
        insufficient = self.build_and_render(unresolved_payload("insufficient"))["html"]
        self.assertIn("different uniquely closest matchups", split)
        self.assertNotIn("hybrid-runoff-candidate-pair", split)
        self.assertIn("multiple matchups tied", ambiguous)
        self.assertIn("No score comparison is shown", insufficient)
        self.assertNotIn("hybrid-runoff-balance", insufficient)

    def test_loading_malformed_and_failed_derived_states_remain_accessible(self):
        cases = [
            (self.derived, "loading", "Loading repository data"),
            ({}, "ready", "derived artifact is malformed"),
            (None, "error", "This data domain is unavailable"),
        ]
        for payload, load_state, expected in cases:
            with self.subTest(expected=expected):
                output = run_runoff_script(
                    payload,
                    "(() => { const model = api.buildRunoffViewModel(); return api.renderRunoffPanel(model); })()",
                    load_state=load_state,
                )
                self.assertIn(expected, output)
                self.assertIn('aria-live="polite"', output)

    def test_methodology_and_semantics_are_neutral(self):
        html = self.render_real()["html"]
        self.assertIn("no forecast", html)
        self.assertNotIn("No polling average, probability, forecast, voter-transfer model, or synthetic ranking is calculated", html)
        for forbidden in ("momentum", "viability", "confidence gauge", "projection", "winner", "leader", "trophy"):
            self.assertNotIn(forbidden, html.casefold())
        self.assertNotIn("is-green", html)

    def test_archive_loader_fetches_once_and_isolates_malformed_payloads(self):
        loaded = run_runoff_script(
            self.derived,
            """(async () => { let calls = 0; const fetcher = () => { calls += 1; return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ events: input.archiveState.events }) }); }; const first = api.loadRunoffArchive(fetcher); const second = api.loadRunoffArchive(fetcher); const state = await first; return { calls, sameRequest: first === second, status: state.status, count: state.events.length }; })()""",
            archive_state=self.archive_state,
        )
        self.assertEqual(loaded, {"calls": 1, "sameRequest": True, "status": "ready", "count": 38})
        malformed = run_runoff_script(
            self.derived,
            """(async () => { const fetcher = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ events: [{ event_id: 'broken' }] }) }); const state = await api.loadRunoffArchive(fetcher); const model = api.buildRunoffViewModel(state); return { status: state.status, currentStatus: model.status, currentCount: model.selectedMatchup.observations.length, archiveState: model.archive.state }; })()""",
        )
        self.assertEqual(
            malformed,
            {"status": "unavailable", "currentStatus": "agree", "currentCount": 2, "archiveState": "unavailable"},
        )

class RunoffActiveLoadIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = derive_closest_tested_runoff(
            qualifying_events({"Ifop": (4, 8), "Ipsos": (5, 9)})
        )
        cls.payload["disclosure"] = "Source-reported second-round observations."

    def test_valid_payload_is_published_before_successful_legacy_render(self):
        output = run_runoff_loader(self.payload)
        self.assertEqual(output["runoffState"], "loaded")
        self.assertEqual(output["runoff"], self.payload)
        self.assertEqual(output["updatedAt"], "2026-07-02")
        self.assertEqual(output["publishedPayloads"], [self.payload])
        self.assertEqual(output["legacyCalls"], [{
            "payload": self.payload,
            "state": "loaded",
            "publishedCount": 1,
        }])
        self.assertEqual(output["events"], [{"name": "runoff", "status": "loaded"}])
        self.assertEqual(output["documentRunoffReady"], "agree")
        self.assertEqual(output["warnings"], [])
        self.assertTrue(output["otherStateUnchanged"])

    def test_legacy_render_failure_does_not_reclassify_valid_payload(self):
        output = run_runoff_loader(self.payload, legacy_throws=True)
        self.assertEqual(output["runoffState"], "loaded")
        self.assertEqual(output["runoff"], self.payload)
        self.assertEqual(output["updatedAt"], "2026-07-02")
        self.assertEqual(output["publishedPayloads"], [self.payload])
        self.assertEqual(output["events"], [{"name": "runoff", "status": "loaded"}])
        self.assertEqual(output["errorStates"], [])
        self.assertTrue(output["otherStateUnchanged"])
        self.assertEqual(output["legacyCalls"][0]["state"], "loaded")
        self.assertEqual(output["legacyCalls"][0]["publishedCount"], 1)
        self.assertIsNone(output["documentRunoffReady"])
        self.assertIn("Legacy runoff card unavailable.", output["warnings"][0])
        self.assertIn("synthetic legacy render failure", output["warnings"][0])

    def test_invalid_payload_keeps_existing_unavailable_behavior(self):
        output = run_runoff_loader({})
        self.assertEqual(output["runoffState"], "error")
        self.assertIsNone(output["runoff"])
        self.assertEqual(output["events"], [{"name": "runoff", "status": "error"}])
        self.assertEqual(output["publishedPayloads"], [])
        self.assertEqual(output["legacyCalls"], [])
        self.assertEqual(output["documentRunoffReady"], "error")
        self.assertIn("Runoff comparison unavailable", output["unavailableHtml"])
        self.assertEqual(output["errorStates"], ["runoff"])
        self.assertTrue(output["otherStateUnchanged"])

    def test_invalid_json_keeps_existing_unavailable_behavior(self):
        output = run_runoff_loader(None, fetch_mode="invalid-json")
        self.assertEqual(output["runoffState"], "error")
        self.assertIsNone(output["runoff"])
        self.assertEqual(output["events"], [{"name": "runoff", "status": "error"}])
        self.assertEqual(output["publishedPayloads"], [])
        self.assertEqual(output["legacyCalls"], [])
        self.assertEqual(output["documentRunoffReady"], "error")
        self.assertIn("Runoff comparison unavailable", output["unavailableHtml"])
        self.assertEqual(output["errorStates"], ["runoff"])
        self.assertTrue(output["otherStateUnchanged"])

    def test_failed_fetch_keeps_existing_unavailable_behavior(self):
        output = run_runoff_loader(None, fetch_mode="reject")
        self.assertEqual(output["runoffState"], "error")
        self.assertIsNone(output["runoff"])
        self.assertEqual(output["events"], [{"name": "runoff", "status": "error"}])
        self.assertEqual(output["publishedPayloads"], [])
        self.assertEqual(output["legacyCalls"], [])
        self.assertEqual(output["documentRunoffReady"], "error")
        self.assertIn("Runoff comparison unavailable", output["unavailableHtml"])
        self.assertEqual(output["errorStates"], ["runoff"])
        self.assertTrue(output["otherStateUnchanged"])


class RunoffIsolationAndStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.js = HYBRID_JS.read_text(encoding="utf-8")
        cls.css = HYBRID_CSS.read_text(encoding="utf-8")
        cls.runoff_css = cls.css[cls.css.index("/* RUNOFF WORKSPACE REDESIGN V1") :]

    def test_tab_panel_hash_and_aria_contract_is_stable(self):
        runoff_config = re.search(
            r"runoff:\s*\{(?P<body>.*?)\n\s*\},\n\s*events:",
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

    def test_archive_load_and_join_contract_is_exact(self):
        self.assertEqual(self.js.count('loadRunoffArchive();'), 1)
        self.assertEqual(self.js.count('fetchImplementation("second_round_polls.json"'), 1)
        join = re.search(
            r"function enrichRunoffResult\(result, eventById\) \{(?P<body>.*?)\n  \}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(join)
        self.assertIn("eventById.get(result.event_id)", join.group("body"))
        for forbidden in ("candidate", "pollster", "source_url"):
            self.assertNotIn(forbidden, join.group("body").replace("archiveMatched", ""))


    def test_runoff_dom_order_and_native_history_control(self):
        renderer = self._runoff_source()

        panel_start = renderer.index(
            "function renderRunoffPanel(model)"
        )

        panel_end = len(renderer)

        for token in ("\n  function ", "\nfunction "):
            position = renderer.find(
                token,
                panel_start + 1,
            )

            if position >= 0:
                panel_end = min(panel_end, position)

        panel_renderer = renderer[
            panel_start:
            panel_end
        ]

        ordered = [
            "renderRunoffHeader(model)",
            "renderRunoffClosest(model)",
            "renderRunoffCommonMatchups(model)",
            "renderRunoffOtherMatchups(model)",
            "renderRunoffHistory(model)",
        ]

        positions = [
            panel_renderer.index(item)
            for item in ordered
        ]

        self.assertEqual(
            positions,
            sorted(positions),
        )

        self.assertIn(
            '<select class="hybrid-runoff-history-select" data-hybrid-runoff-history>',
            renderer,
        )

        self.assertIn(
            'runoffHistory.addEventListener("change"',
            self.js,
        )

        self.assertNotIn(
            'document.addEventListener("change"',
            self.js,
        )


    def test_shared_geometry_and_single_runoff_scroll_region(self):
        shared = self.css[
            self.css.index("/* SHARED WORKSPACE HEIGHT PARITY V1"):
            self.css.index("/* RUNOFF WORKSPACE REDESIGN V1")
        ]

        self.assertIn(
            ".hybrid-workspace > .hybrid-panel",
            shared,
        )

        for contract in (
            "height: 462px",
            "min-height: 462px",
            "max-height: 462px",
            "overflow-y: auto",
        ):
            self.assertIn(contract, shared)

        self.assertIn(
            ".hybrid-workspace > .hybrid-panel#signal-candidates-panel",
            shared,
        )

        self.assertIn(
            "overflow: hidden",
            shared,
        )

        self.assertNotRegex(
            shared,
            r"(?m)^\s*\.hybrid-panel\s*\{",
        )

        self.assertEqual(
            self.runoff_css.count("overflow-y: auto"),
            3,
        )

        common_matrix_rules = re.findall(
            r"\.hybrid-panel#signal-runoff-panel\s+"
            r"\.hybrid-runoff-common\s+"
            r"\.hybrid-runoff-matrix\s*\{"
            r"(?P<body>.*?)\}",
            self.runoff_css,
            re.DOTALL,
        )

        self.assertTrue(
            any(
                "min-height: 0" in body
                and "overflow-x: hidden" in body
                and "overflow-y: auto" in body
                for body in common_matrix_rules
            )
        )

        self.assertNotIn(
            "overflow-y: scroll",
            self.runoff_css,
        )

        other_grid_rules = re.findall(
            r"\.hybrid-panel#signal-runoff-panel "
            r"\.hybrid-runoff-other-grid\s*\{"
            r"(?P<body>.*?)\}",
            self.runoff_css,
            re.DOTALL,
        )

        self.assertTrue(
            any(
                "overflow-y: auto" in body
                for body in other_grid_rules
            )
        )

        history_scroll_rules = re.findall(
            r"\.hybrid-panel#signal-runoff-panel "
            r"\.hybrid-runoff-history-scroll\s*\{"
            r"(?P<body>.*?)\}",
            self.runoff_css,
            re.DOTALL,
        )

        self.assertTrue(history_scroll_rules)

        self.assertTrue(
            any(
                "overflow-x: auto" in body
                and "overflow-y: hidden" in body
                for body in history_scroll_rules
            )
        )

    def test_locked_runoff_typography_and_dashboard_geometry_are_static(self):
        for contract in (
            "grid-template-columns: minmax(390px, 1.12fr) minmax(390px, 1.12fr) minmax(280px, .96fr)",
            "grid-template-columns: minmax(0, .96fr) minmax(0, 1.04fr)",
            "font-size: 29px",
            "font-weight: 720",
            "line-height: 24.94px",
            "letter-spacing: -1.015px",
            "font-size: 15px",
            "font-weight: 760",
            "line-height: 16.5px",
            "font-size: 14px",
            "font-weight: 730",
            "line-height: 14px",
        ):
            self.assertIn(contract, self.runoff_css)
        self.assertIn("RUNOFF FINAL ARCHITECTURE V1", self.runoff_css)
        self.assertIn(".hybrid-runoff-step", self.runoff_css)
        self.assertIn(".hybrid-runoff-other-grid", self.runoff_css)
        self.assertIn("overflow-y: auto", self.runoff_css)
        self.assertIn(".hybrid-runoff-archive-grid", self.runoff_css)

    def test_all_new_runoff_css_is_owned_and_mobile_stacks(self):
        css_without_comments = re.sub(
            r"/\*.*?\*/",
            "",
            self.runoff_css,
            flags=re.DOTALL,
        )

        selector_groups = re.findall(
            r"([^{}]+)\{",
            css_without_comments,
            re.DOTALL,
        )

        self.assertTrue(selector_groups)

        checked = 0

        for selector_group in selector_groups:
            selector_group = " ".join(
                selector_group.split()
            )

            if (
                not selector_group
                or selector_group.startswith("@")
            ):
                continue

            for selector in selector_group.split(","):
                selector = " ".join(
                    selector.split()
                )

                if (
                    not selector
                    or selector.startswith(("from", "to"))
                ):
                    continue

                checked += 1

                self.assertTrue(
                    selector.startswith(
                        ".hybrid-panel#signal-runoff-panel"
                    ),
                    (
                        "Runoff selector escaped the owned panel: "
                        f"{selector}"
                    ),
                )

        self.assertGreater(checked, 0)

        mobile = re.search(
            r"@media \(max-width: 679px\) \{"
            r"(?P<body>.*)\n\}",
            self.runoff_css,
            re.DOTALL,
        )

        self.assertIsNotNone(mobile)

        for selector in (
            ".hybrid-runoff-observations",
            ".hybrid-runoff-chronology",
            ".hybrid-runoff-other-grid",
        ):
            self.assertIn(
                selector,
                mobile.group("body"),
            )

        self.assertIn(
            "grid-template-columns: 1fr",
            mobile.group("body"),
        )

    def test_accessibility_and_neutral_visual_semantics_are_static(self):
        renderer = self._runoff_source()
        for contract in (
            'role="img"',
            'aria-live="polite"',
            'target="_blank" rel="noopener noreferrer"',
            'aria-labelledby="hybrid-runoff-closest-title"',
        ):
            self.assertIn(contract, renderer)
        self.assertIn("focus-visible", self.runoff_css)
        for forbidden in ("is-green", "#00ff", "trophy", "winner", "leader", "momentum"):
            self.assertNotIn(forbidden, (renderer + self.runoff_css).casefold())

    def test_runoff_implementation_remains_isolated(self):
        source = self._runoff_source().casefold()
        for forbidden in (
            "candidate-signals.js",
            "candidate-signals-workspace.js",
            "candidate-signals.css",
            "candidate_signals.json",
            "france2027candidatesignals",
        ):
            self.assertNotIn(forbidden, source)
        self.assertEqual(self.js.count('window.addEventListener("hashchange", handleSignalHashChange);'), 1)
        self.assertEqual(self.js.count('document.addEventListener("hybrid:dataset", renderAll);'), 1)
        self.assertNotIn("document.addEventListener", source)
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

    def _runoff_source(self) -> str:
        model_start = self.js.index("function exactRunoffWindowLabel(")
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
