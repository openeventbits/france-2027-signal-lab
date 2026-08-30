from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
HYBRID_JS = ROOT / "assets" / "hybrid-dashboard.js"
CANDIDATE_JS = ROOT / "assets" / "candidate-signals.js"
AGENDA_HISTORY_JS = ROOT / "assets" / "candidate-agenda-history.js"
AGENDA_HISTORY_JSON = ROOT / "candidate_agenda_history.json"
SHELL_CSS = ROOT / "assets" / "final-dashboard-shell.css"

VIEW_NAMES = [
    "candidates",
    "runoff",
    "events",
    "agenda",
    "issues",
]
TAB_IDS = [
    "signal-candidates-tab",
    "signal-runoff-tab",
    "signal-events-tab",
    "signal-agenda-tab",
    "signal-issues-tab",
]
PANEL_IDS = [
    "signal-candidates-panel",
    "signal-runoff-panel",
    "signal-events-panel",
    "signal-agenda-panel",
    "signal-issues-panel",
]


def run_router_script(hash_value, expression):
    script = r"""
const fs = require("fs");
const vm = require("vm");
let source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8");
source = source.replace(
  /\s+retainLegacyComparison\(\);\s+renderAll\(\);\s+window\.addEventListener\("hashchange", handleSignalHashChange\);\s+document\.addEventListener\("hybrid:dataset", renderAll\);/,
  ""
);
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const names = ["candidates", "runoff", "events", "agenda", "issues"];
const panelIds = [
  "signal-candidates-panel",
  "signal-runoff-panel",
  "signal-events-panel",
  "signal-agenda-panel",
  "signal-issues-panel"
];
const panels = Object.fromEntries(panelIds.map(id => [id, { id, hidden: true }]));
const tabs = names.map((name, index) => ({
  dataset: { hybridView: name },
  attributes: { "aria-controls": panelIds[index] },
  tabIndex: -1,
  focused: false,
  classList: { toggle() {} },
  setAttribute(key, value) { this.attributes[key] = String(value); },
  getAttribute(key) { return this.attributes[key]; },
  closest() { return null; },
  focus() { this.focused = true; }
}));
const mount = {
  innerHTML: "",
  querySelectorAll(selector) {
    if (selector === "[role='tab'][data-hybrid-view]") return tabs;
    if (selector === "[data-hybrid-card]") return [];
    return [];
  },
  querySelector() { return null; }
};
const historyCalls = [];
const windowObject = {
  location: { hash: input.hash },
  history: {
    replaceState(_state, _title, url) {
      historyCalls.push(url);
      windowObject.location.hash = url;
    }
  },
  addEventListener() {},
  matchMedia() { return { matches: true }; },
  innerHeight: 900
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
  window: windowObject,
  document: {
    getElementById(id) {
      if (id === "hybrid-signal-board") return mount;
      return panels[id] || null;
    },
    addEventListener() {},
    querySelector() { return null; }
  },
  dashboardState: {},
  candidatePortraits: {},
  newestNewsItems: values => values,
  formatScore: value => String(value),
  formatDate: value => String(value),
  escapeHtml: value => String(value),
  escapeAttribute: value => String(value),
  formatNewsDateTime: value => String(value),
  formatRunoffFieldwork: value => String(value)
};
vm.runInNewContext(source, context);
const api = context.window.hybridDashboard;
const result = eval(input.expression);
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"hash": hash_value, "expression": expression}),
        cwd=ROOT,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def candidate_payload(candidates=None, schema_version="1.0"):
    return {
        "schema_version": schema_version,
        "candidate_universe": {"count": len(candidates or [])},
        "candidates": candidates or [],
    }


def candidate_row(candidate_id="alpha", candidate_name="Alpha"):
    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate_name,
        "polling": {
            "evidence_state": "reported",
            "hypothesis_count": 2,
            "range_min": 4.5,
            "range_max": 6.0,
            "selected_hypothesis_score": None,
            "selected_hypothesis_rank": None,
        },
        "campaign_attention": {
            "evidence_state": "reported",
            "record_count": 3,
            "share": 0.25,
            "publisher_count": 2,
            "active_day_count": 2,
            "headline_match_count": 2,
            "summary_only_match_count": 1,
            "scope_counts": {"election": 1, "campaign": 2, "general": 0},
            "scope_shares": {
                "election": 0.333,
                "campaign": 0.667,
                "general": 0.0,
            },
            "story_cluster_count": 2,
            "concentration": {
                "leading_publisher": "Example",
                "leading_publisher_record_count": 2,
                "leading_publisher_share": 0.667,
                "leading_story_record_count": 1,
                "leading_story_share": 0.333,
            },
        },
        "general_visibility": {
            "evidence_state": "not_observed",
            "record_count": None,
            "share": None,
            "publisher_count": None,
            "active_day_count": None,
            "headline_match_count": None,
            "summary_only_match_count": None,
            "story_cluster_count": None,
            "concentration": None,
        },
        "scrutiny": {
            "latest_14_days": {
                "review_count": 1,
                "by_count": 0,
                "about_count": 1,
                "newest_review_date": "2026-07-17",
                "newest_review_url": "https://example.test/review",
            },
            "archive": {
                "review_count": 2,
                "by_count": 1,
                "about_count": 1,
                "newest_review_date": "2026-07-17",
                "newest_review_url": "https://example.test/review",
            },
        },
        "latest_development": {
            "evidence_state": "reported",
            "id": "development-alpha",
            "published_at": "2026-07-29T12:00:00Z",
            "publisher": "Example",
            "headline": "Published development",
            "url": "https://example.test/development",
            "coverage_scope": "campaign",
        },
    }


def dynamic_schema_12_payload(tiers=("main", "main", "secondary", "hidden")):
    """Return a small internally consistent schema 1.2 frontend fixture."""

    source = json.loads(
        (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
    )
    template = source["candidates"][0]
    status_by_tier = {
        "main": "declared",
        "secondary": "active_potential",
        "hidden": "withdrawn",
    }
    candidates = []
    for index, tier in enumerate(tiers, start=1):
        if tier not in status_by_tier:
            raise ValueError(f"unsupported fixture tier: {tier}")
        row = json.loads(json.dumps(template))
        row["candidate_id"] = f"dynamic-candidate-{index:02d}"
        row["candidate_name"] = f"Dynamic Candidate {index:02d}"
        row["candidacy"]["status"] = status_by_tier[tier]
        row["candidacy"]["display_tier"] = tier
        row["candidacy"]["active_field_eligible"] = tier != "hidden"
        row["candidacy"].pop("upstream_presence", None)
        row.pop("agenda_profile", None)
        row.pop("poll_history", None)
        candidates.append(row)

    field = {
        "status_as_of": "2026-08-01",
        "main": [],
        "secondary": [],
        "hidden": [],
        "counts": {},
    }
    for candidate in candidates:
        field[candidate["candidacy"]["display_tier"]].append(
            candidate["candidate_id"]
        )
    field["counts"] = {
        "main": len(field["main"]),
        "secondary": len(field["secondary"]),
        "hidden": len(field["hidden"]),
        "active": len(field["main"]) + len(field["secondary"]),
        "total": len(candidates),
    }

    thresholds = json.loads(json.dumps(
        source["active_field_visibility"]["primary"]
        ["comparison_quality"]["thresholds"]
    ))

    def active_scope():
        rows = {"main": [], "secondary": []}
        for candidate in candidates:
            tier = candidate["candidacy"]["display_tier"]
            if tier == "hidden":
                continue
            rows[tier].append({
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate["candidate_name"],
                "status": candidate["candidacy"]["status"],
                "display_tier": tier,
                "current_record_count": 0,
                "current_share": None,
                "prior_record_count": 0,
                "prior_share": None,
                "share_change": None,
            })
        return {
            "current_period": {
                "start_date": "2026-07-26",
                "end_date": "2026-08-01",
                "record_count": 0,
                "publisher_count": 0,
            },
            "prior_period": {
                "start_date": "2026-07-19",
                "end_date": "2026-07-25",
                "record_count": 0,
                "publisher_count": 0,
            },
            "comparison_quality": {
                "status": "not_comparable",
                "reason": "insufficient_data",
                "current_record_count": 0,
                "prior_record_count": 0,
                "current_publisher_count": 0,
                "prior_publisher_count": 0,
                "common_publisher_count": 0,
                "publisher_union_count": 0,
                "publisher_overlap_ratio": 0.0,
                "record_count_ratio": None,
                "thresholds": thresholds,
            },
            "main": rows["main"],
            "secondary": rows["secondary"],
        }

    payload = json.loads(json.dumps(source))
    payload["schema_version"] = "1.2"
    payload.pop("active_monitoring_field", None)
    payload["candidate_universe"] = {
        "source": "candidate_candidacy_status.json",
        "rule": "Dynamic frontend fixture",
        "status_as_of": "2026-08-01",
        "count": len(candidates),
    }
    payload["candidates"] = candidates
    payload["presidential_field"] = field
    payload["active_field_visibility"] = {
        "method": "share_of_active_candidate_linked_records",
        "denominator_scope": (
            "records_linked_to_at_least_one_main_or_secondary_candidate"
        ),
        "status_as_of": field["status_as_of"],
        "primary": active_scope(),
        "general": active_scope(),
    }
    return payload


def run_candidate_module(expression, payload=None, fetch_mode="success"):
    script = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const windowObject = {};
windowObject.fetch = async () => {
  if (input.fetchMode === "fetch_failed") throw new Error("private network text");
  if (input.fetchMode === "http_error") {
    return { ok: false, status: 503, json: async () => input.payload };
  }
  if (input.fetchMode === "malformed_json") {
    return {
      ok: true,
      status: 200,
      json: async () => { throw new SyntaxError("private parser text"); }
    };
  }
  return { ok: true, status: 200, json: async () => input.payload };
};
const context = {
  window: windowObject,
  Object,
  Array,
  Set,
  Map,
  Promise,
  URL
};
vm.runInNewContext(
  fs.readFileSync("assets/candidate-signals.js", "utf8"),
  context
);
(async () => {
  const api = context.window.France2027CandidateSignals;
  const result = await eval(input.expression);
  process.stdout.write(JSON.stringify(result));
})().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(
            {
                "expression": expression,
                "payload": payload,
                "fetchMode": fetch_mode,
            }
        ),
        cwd=ROOT,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def run_agenda_history_module(expression, payload=None, fetch_mode="success"):
    script = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const windowObject = {};
windowObject.fetch = async () => {
  if (input.fetchMode === "fetch_failed") throw new Error("private network text");
  if (input.fetchMode === "http_error") {
    return { ok: false, status: 503, json: async () => input.payload };
  }
  if (input.fetchMode === "malformed_json") {
    return {
      ok: true,
      status: 200,
      json: async () => { throw new SyntaxError("private parser text"); }
    };
  }
  return { ok: true, status: 200, json: async () => input.payload };
};
const context = {
  window: windowObject,
  Date,
  Object,
  Array,
  Set,
  Number,
  Promise
};
vm.runInNewContext(
  fs.readFileSync("assets/candidate-agenda-history.js", "utf8"),
  context
);
(async () => {
  const api = context.window.France2027CandidateAgendaHistory;
  const result = await eval(input.expression);
  process.stdout.write(JSON.stringify(result));
})().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(
            {
                "expression": expression,
                "payload": payload,
                "fetchMode": fetch_mode,
            }
        ),
        cwd=ROOT,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def run_hybrid_candidate_integration(load_mode, expression):
    script = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let source = fs.readFileSync("assets/hybrid-dashboard.js", "utf8");
source = source.replace(
  /\s+retainLegacyComparison\(\);\s+renderAll\(\);\s+window\.addEventListener\("hashchange", handleSignalHashChange\);\s+document\.addEventListener\("hybrid:dataset", renderAll\);/,
  ""
);
let loadCount = 0;
const loadedUrls = [];
let agendaLoadCount = 0;
const agendaLoadedUrls = [];
const candidateRoot = {
  attributes: {},
  setAttribute(key, value) { this.attributes[key] = String(value); }
};
const panelIds = [
  "signal-candidates-panel",
  "signal-runoff-panel",
  "signal-events-panel",
  "signal-agenda-panel",
  "signal-issues-panel"
];
const panels = Object.fromEntries(
  panelIds.map(id => [id, { id, hidden: true }])
);
const names = ["candidates", "runoff", "events", "agenda", "issues"];
const tabs = names.map((name, index) => ({
  dataset: { hybridView: name },
  attributes: { "aria-controls": panelIds[index] },
  tabIndex: -1,
  classList: { toggle() {} },
  setAttribute(key, value) { this.attributes[key] = String(value); },
  getAttribute(key) { return this.attributes[key]; },
  closest() { return null; },
  focus() {}
}));
const mount = {
  innerHTML: "",
  querySelectorAll(selector) {
    if (selector === "[role='tab'][data-hybrid-view]") return tabs;
    if (selector === "[data-hybrid-card]") return [];
    return [];
  },
  querySelector() { return null; }
};
const windowObject = {
  location: { hash: "#signal-candidates" },
  history: { replaceState() {} },
  addEventListener() {},
  matchMedia() { return { matches: true }; },
  innerHeight: 900,
  France2027CandidateSignals: {
    load(url) {
      loadCount += 1;
      loadedUrls.push(url);
      if (input.loadMode === "reject") {
        return Promise.reject(new Error("must remain private"));
      }
      return Promise.resolve({
        status: "ready",
        candidates: [],
        metadata: {},
        reason: null
      });
    }
  },
  France2027CandidateAgendaHistory: {
    load(url) {
      agendaLoadCount += 1;
      agendaLoadedUrls.push(url);
      return Promise.resolve({
        status: "unavailable",
        payload: null,
        reason: null
      });
    }
  }
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
  Promise,
  window: windowObject,
  document: {
    getElementById(id) {
      if (id === "hybrid-signal-board") return mount;
      if (id === "candidate-signals-root") return candidateRoot;
      return panels[id] || null;
    },
    addEventListener() {},
    querySelector() { return null; }
  },
  dashboardState: {},
  candidatePortraits: {},
  newestNewsItems: values => values,
  formatScore: value => String(value),
  formatDate: value => String(value),
  escapeHtml: value => String(value),
  escapeAttribute: value => String(value),
  formatNewsDateTime: value => String(value),
  formatRunoffFieldwork: value => String(value)
};
vm.runInNewContext(source, context);
(async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  const api = context.window.hybridDashboard;
  const result = eval(input.expression);
  process.stdout.write(JSON.stringify(result));
})().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"loadMode": load_mode, "expression": expression}),
        cwd=ROOT,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


class CandidateSignalsRoutingStageATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.js = HYBRID_JS.read_text(encoding="utf-8")
        cls.css = SHELL_CSS.read_text(encoding="utf-8")

        start = cls.js.index(
            "  const views = Object.freeze({"
        )
        end = cls.js.index(
            "  const viewOrder",
            start,
        )
        cls.views = cls.js[start:end]

        workspace_start = cls.js.index(
            "  function renderFocusWorkspace("
        )
        workspace_end = cls.js.index(
            "  function setActiveSignalView(",
            workspace_start,
        )
        cls.workspace = cls.js[
            workspace_start:workspace_end
        ]

    def render_workspace(self, hash_value=""):
        return run_router_script(
            hash_value,
            """api.renderFocusWorkspace({
              runoff: { state: "empty", message: "runoff" },
              events: { state: "empty", message: "events" },
              agenda: { state: "empty", message: "agenda" },
              issues: { state: "empty", message: "issues" },
              claims: { state: "empty", message: "claims" }
            })""",
        )

    def test_exact_five_labels_and_hashes_in_locked_order(self):
        entries = re.findall(
            r'^    (\w+): \{.*?^      '
            r'label: (?:translate\("[^"]+", )?'
            r'"([^"]+)"\)?,'
            r'.*?^      hash: "([^"]+)",',
            self.views,
            re.MULTILINE | re.DOTALL,
        )

        self.assertEqual(
            entries,
            [
                (
                    "candidates",
                    "CANDIDATES",
                    "#signal-candidates",
                ),
                (
                    "runoff",
                    "RUNOFF",
                    "#signal-runoff",
                ),
                (
                    "events",
                    "EVENTS",
                    "#signal-events",
                ),
                (
                    "agenda",
                    "AGENDA",
                    "#signal-agenda",
                ),
                (
                    "issues",
                    "ISSUES",
                    "#signal-issues",
                ),
            ],
        )

    def test_candidates_is_default_and_active_fallback(self):
        self.assertIn(
            'const defaultView = "candidates";',
            self.js,
        )
        self.assertIn(
            "activeView: "
            "hashToView.get(window.location.hash) "
            "|| defaultView",
            self.js,
        )
        self.assertIn(
            "if (!views[view]) view = defaultView;",
            self.js,
        )

        workspace = self.render_workspace("")

        candidate_tab = re.search(
            r'<button class="hybrid-tab" '
            r'id="signal-candidates-tab"[^>]+>',
            workspace,
        ).group(0)

        self.assertIn(
            'aria-selected="true"',
            candidate_tab,
        )
        self.assertIn(
            'tabindex="0"',
            candidate_tab,
        )

    def test_empty_unknown_and_obsolete_hashes_normalize_with_replace_state(self):
        for hash_value in (
            "",
            "#unknown",
            "#signal-media",
            "#signal-claims",
            "#signal-poll-compare",
        ):
            with self.subTest(
                hash_value=hash_value
            ):
                result = run_router_script(
                    hash_value,
                    """(() => {
                      api.handleSignalHashChange();
                      return {
                        hash: windowObject.location.hash,
                        historyCalls,
                        selected:
                          tabs.find(
                            tab =>
                              tab.attributes[
                                "aria-selected"
                              ] === "true"
                          ).dataset.hybridView
                      };
                    })()""",
                )

                self.assertEqual(
                    result["hash"],
                    "#signal-candidates",
                )
                self.assertEqual(
                    result["historyCalls"],
                    ["#signal-candidates"],
                )
                self.assertEqual(
                    result["selected"],
                    "candidates",
                )

        self.assertIn(
            "window.history.replaceState(",
            self.js,
        )

    def test_lower_media_tab_is_absent_but_top_media_pulse_remains(self):
        workspace = self.render_workspace()

        self.assertNotIn(
            "MEDIA PULSE",
            workspace,
        )
        self.assertNotIn(
            "#signal-media",
            self.views,
        )

        for selector in (
            'class="panel top-media-pulse"',
            'id="top-media-pulse-content"',
            'id="top-media-pulse-metrics"',
            'data-top-media-tab="overview"',
            'data-top-media-tab="coverage"',
        ):
            self.assertIn(
                selector,
                self.html + self.js,
            )

        self.assertIn(
            "function renderMediaPanel(",
            self.js,
        )
        self.assertIn(
            "function buildMediaViewModel()",
            self.js,
        )

    def test_candidates_has_real_tab_panel_and_owned_mount(self):
        workspace = self.render_workspace()

        tab = re.search(
            r'<button class="hybrid-tab" '
            r'id="signal-candidates-tab"[^>]+>',
            workspace,
        ).group(0)

        panel = re.search(
            r'<section class="hybrid-panel" '
            r'id="signal-candidates-panel"[^>]+>',
            workspace,
        ).group(0)

        self.assertIn(
            'role="tab"',
            tab,
        )
        self.assertIn(
            'aria-controls="signal-candidates-panel"',
            tab,
        )
        self.assertIn(
            'role="tabpanel"',
            panel,
        )
        self.assertIn(
            'aria-labelledby="signal-candidates-tab"',
            panel,
        )
        self.assertIn(
            'id="candidate-signals-root"',
            workspace,
        )

    def test_stage_b2_replaces_temporary_placeholder(self):
        combined = self.html + self.js

        self.assertIn(
            "candidate-signals.css",
            combined,
        )

        candidate_start = self.workspace.index(
            'id="candidate-signals-root"'
        )
        candidate_end = self.workspace.index(
            "      </section>",
            candidate_start,
        )

        scaffold = self.workspace[
            candidate_start:candidate_end
        ]

        self.assertNotIn(
            "Candidate evidence will be rendered "
            "in the next implementation stage.",
            scaffold,
        )

        self.assertEqual(
            re.findall(
                r"data-candidate-signals-[a-z-]+",
                scaffold,
            ),
            ["data-candidate-signals-state"],
        )

    def test_events_has_real_tab_and_model_driven_empty_panel(self):
        workspace = self.render_workspace()

        self.assertRegex(
            workspace,
            r'id="signal-events-tab"[^>]+'
            r'role="tab"[^>]+'
            r'aria-controls="signal-events-panel"',
        )

        self.assertRegex(
            workspace,
            r'id="signal-events-panel" '
            r'role="tabpanel" '
            r'aria-labelledby="signal-events-tab"'
            r'[^>]* hidden',
        )

        self.assertIn(
            '<span class="hybrid-state is-compact">'
            "events</span>",
            workspace,
        )

        self.assertNotIn(
            "Campaign Events is not yet available.",
            workspace,
        )

    def test_issues_is_real_tab_controlling_owned_panel(self):
        workspace = self.render_workspace()

        tab = re.search(
            r'<button class="hybrid-tab" '
            r'id="signal-issues-tab"[^>]+>',
            workspace,
        ).group(0)

        panel = re.search(
            r'<section class="hybrid-panel" '
            r'id="signal-issues-panel"[^>]+>',
            workspace,
        ).group(0)

        self.assertIn(
            'role="tab"',
            tab,
        )
        self.assertIn(
            'aria-controls="signal-issues-panel"',
            tab,
        )
        self.assertIn(
            'role="tabpanel"',
            panel,
        )
        self.assertIn(
            'aria-labelledby="signal-issues-tab"',
            panel,
        )

    def test_legacy_polling_panel_is_hidden_and_not_routed(self):
        workspace = self.render_workspace()

        self.assertNotIn(
            'id="polling-evidence-lab"',
            workspace,
        )

        opening = re.search(
            r'<section class="panel polling-evidence" '
            r'id="polling-evidence-lab"[^>]+>',
            self.html,
        ).group(0)

        self.assertIn(
            " hidden",
            opening,
        )
        self.assertIn(
            'aria-hidden="true"',
            opening,
        )
        self.assertNotIn(
            'role="tabpanel"',
            opening,
        )
        self.assertNotIn(
            "signal-poll-compare-tab",
            opening,
        )

    def test_no_poll_compare_routing_remains(self):
        self.assertNotIn(
            'view === "pollCompare"',
            self.js,
        )
        self.assertNotIn(
            "#signal-poll-compare",
            self.js,
        )
        self.assertNotIn(
            "signal-poll-compare-tab",
            self.js,
        )
        self.assertNotIn(
            "data-hybrid-poll-compare",
            self.html + self.js,
        )

    def test_tablist_and_all_controls_have_required_aria(self):
        workspace = self.render_workspace()

        self.assertRegex(
            workspace,
            r'<div class="hybrid-tabs" '
            r'role="tablist" '
            r'aria-label="[^"]+" '
            r'aria-orientation="horizontal">',
        )

        controls = re.findall(
            r'<button class="hybrid-tab"[^>]+>'
            r'[\s\S]*?</button>',
            workspace,
        )

        self.assertEqual(
            len(controls),
            5,
        )

        for index, control in enumerate(
            controls
        ):
            self.assertIn(
                f'id="{TAB_IDS[index]}"',
                control,
            )
            self.assertIn(
                'role="tab"',
                control,
            )
            self.assertIn(
                f'aria-controls="{PANEL_IDS[index]}"',
                control,
            )
            self.assertRegex(
                control,
                r'aria-selected="(?:true|false)"',
            )
            self.assertRegex(
                control,
                r'tabindex="(?:0|-1)"',
            )

    def test_active_state_hides_other_panels_and_roves_tabindex(self):
        result = run_router_script(
            "#signal-candidates",
            """(() => {
              api.setActiveSignalView("events");
              return {
                tabs: tabs.map(tab => ({
                  name: tab.dataset.hybridView,
                  selected:
                    tab.attributes["aria-selected"],
                  tabIndex: tab.tabIndex
                })),
                panels:
                  Object.fromEntries(
                    Object.entries(panels).map(
                      ([id, panel]) =>
                        [id, panel.hidden]
                    )
                  )
              };
            })()""",
        )

        selected = [
            tab
            for tab in result["tabs"]
            if tab["selected"] == "true"
        ]

        self.assertEqual(
            selected,
            [
                {
                    "name": "events",
                    "selected": "true",
                    "tabIndex": 0,
                }
            ],
        )

        for tab in result["tabs"]:
            if tab["name"] != "events":
                self.assertEqual(
                    tab["tabIndex"],
                    -1,
                )

        self.assertFalse(
            result["panels"][
                "signal-events-panel"
            ]
        )

        for panel_id, hidden in (
            result["panels"].items()
        ):
            if (
                panel_id
                != "signal-events-panel"
            ):
                self.assertTrue(hidden)

    def test_keyboard_navigation_wraps_and_uses_home_end_across_five_tabs(self):
        start = self.js.index(
            "  function bindInteractions()"
        )
        end = self.js.index(
            '    mount.querySelectorAll('
            '"[data-hybrid-agenda-topic]")',
            start,
        )

        keyboard = self.js[start:end]

        for contract in (
            'event.key === "ArrowRight"',
            "(index + 1) % tabs.length",
            'event.key === "ArrowLeft"',
            "(index - 1 + tabs.length) % tabs.length",
            'event.key === "Home"',
            "nextIndex = 0",
            'event.key === "End"',
            "nextIndex = tabs.length - 1",
            "setActiveSignalView("
            "next, { focusTab: true })",
        ):
            self.assertIn(
                contract,
                keyboard,
            )

        self.assertEqual(
            len(VIEW_NAMES),
            5,
        )

    def test_direct_hashes_and_hashchange_activate_recognized_views(self):
        hashes = [
            "#signal-candidates",
            "#signal-runoff",
            "#signal-events",
            "#signal-agenda",
            "#signal-issues",
        ]

        for tab_id, hash_value in zip(
            TAB_IDS,
            hashes,
        ):
            with self.subTest(
                hash_value=hash_value
            ):
                workspace = self.render_workspace(
                    hash_value
                )

                tab = re.search(
                    rf'<button class="hybrid-tab" '
                    rf'id="{tab_id}"[^>]+>',
                    workspace,
                ).group(0)

                self.assertIn(
                    'aria-selected="true"',
                    tab,
                )
                self.assertIn(
                    'tabindex="0"',
                    tab,
                )

    def test_user_changes_use_hash_navigation_for_browser_history(self):
        start = self.js.index(
            "  function setViewHash("
        )
        end = self.js.index(
            "  function scrollWorkspaceIfNeeded(",
            start,
        )

        setter = self.js[start:end]

        self.assertIn(
            "window.location.hash = views[view].hash;",
            setter,
        )
        self.assertNotIn(
            "replaceState",
            setter,
        )
        self.assertIn(
            'window.addEventListener('
            '"hashchange", handleSignalHashChange);',
            self.js,
        )

    def test_five_workspace_navigation_contract_remains(self):
        self.assertEqual(
            VIEW_NAMES,
            [
                "candidates",
                "runoff",
                "events",
                "agenda",
                "issues",
            ],
        )

        narrow_index = self.html[
            self.html.index(
                "@media (max-width: 700px)"
            ):
        ]

        self.assertIn(
            "overflow-x: auto;",
            narrow_index,
        )

        narrow_shell = self.css[
            self.css.index(
                "@media (max-width: 860px)"
            ):
        ]

        self.assertIn(
            "overflow-x: auto;",
            narrow_shell,
        )

        self.assertIn(
            "function revealActiveTab(tab)",
            self.js,
        )


class CandidateSignalsDataModelStageB1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.hybrid_js = HYBRID_JS.read_text(encoding="utf-8")
        cls.candidate_js = CANDIDATE_JS.read_text(encoding="utf-8")
        cls.agenda_history_js = AGENDA_HISTORY_JS.read_text(
            encoding="utf-8"
        )

    def test_module_exists_and_loads_before_dashboard(self):
        self.assertTrue(CANDIDATE_JS.is_file())
        candidate_script = '<script src="assets/candidate-signals.js"></script>'
        dashboard_script = '<script src="assets/hybrid-dashboard.js"></script>'
        self.assertIn(candidate_script, self.html)
        self.assertLess(
            self.html.index(candidate_script),
            self.html.index(dashboard_script),
        )

        history_script = (
            '<script src="assets/candidate-agenda-history.js"></script>'
        )
        self.assertTrue(AGENDA_HISTORY_JS.is_file())
        self.assertIn(history_script, self.html)
        self.assertLess(
            self.html.index(history_script),
            self.html.index(dashboard_script),
        )

    def test_agenda_history_optional_loader_validates_published_artifact(self):
        published = json.loads(
            AGENDA_HISTORY_JSON.read_text(encoding="utf-8")
        )
        result = run_agenda_history_module(
            """(() => {
              const state = api.normalize(input.payload);
              return {
                status: state.status,
                candidateCount: state.payload.candidates.length,
                samePayload: state.payload === input.payload
              };
            })()""",
            published,
        )
        self.assertEqual(result, {
            "status": "ready",
            "candidateCount": len(published["candidates"]),
            "samePayload": True,
        })

    def test_agenda_history_malformed_optional_payload_fails_locally(self):
        published = json.loads(
            AGENDA_HISTORY_JSON.read_text(encoding="utf-8")
        )
        malformed = []

        duplicate = json.loads(json.dumps(published))
        duplicate["candidates"].append(duplicate["candidates"][0])
        malformed.append(duplicate)

        invalid_mode = json.loads(json.dumps(published))
        invalid_mode["candidates"][0]["cumulative_profile"][
            "profile_mode"
        ] = "mixed"
        malformed.append(invalid_mode)

        invalid_count = json.loads(json.dumps(published))
        invalid_count["candidates"][0]["cumulative_profile"][
            "topics"
        ][0]["count"] = -1
        malformed.append(invalid_count)

        invalid_share = json.loads(json.dumps(published))
        invalid_share["candidates"][0]["cumulative_profile"][
            "topics"
        ][0]["share"] = 1.01
        malformed.append(invalid_share)

        for payload_value in malformed:
            with self.subTest():
                state = run_agenda_history_module(
                    "api.normalize(input.payload)",
                    payload_value,
                )
                self.assertEqual(state, {
                    "status": "unavailable",
                    "payload": None,
                    "reason": "invalid_payload",
                })

        failure = run_agenda_history_module(
            'api.load("candidate_agenda_history.json")',
            published,
            fetch_mode="fetch_failed",
        )
        self.assertEqual(failure["status"], "unavailable")
        self.assertIsNone(failure["payload"])

    def test_exact_namespace_frozen_api_and_states(self):
        result = run_candidate_module(
            """({
              namespaceExists: !!api,
              apiKeys: Object.keys(api).sort(),
              apiFrozen: Object.isFrozen(api),
              stateKeys: Object.keys(api.STATES),
              stateValues: Object.values(api.STATES),
              statesFrozen: Object.isFrozen(api.STATES)
            })"""
        )
        self.assertTrue(result["namespaceExists"])
        self.assertEqual(result["apiKeys"], ["STATES", "load", "normalize"])
        self.assertTrue(result["apiFrozen"])
        self.assertEqual(
            result["stateKeys"],
            ["loading", "ready", "empty", "unavailable"],
        )
        self.assertEqual(
            result["stateValues"],
            ["loading", "ready", "empty", "unavailable"],
        )
        self.assertTrue(result["statesFrozen"])
        self.assertIn(
            "window.France2027CandidateSignals = Object.freeze({",
            self.candidate_js,
        )

    def test_successful_nonempty_and_empty_payload_states(self):
        ready = run_candidate_module(
            'api.load("candidate_signals.json")',
            candidate_payload([candidate_row()]),
        )
        empty = run_candidate_module(
            'api.load("candidate_signals.json")',
            candidate_payload([]),
        )
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(len(ready["candidates"]), 1)
        self.assertEqual(ready["reason"], None)
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(empty["candidates"], [])
        self.assertEqual(empty["reason"], None)
        for state in (ready, empty):
            self.assertEqual(
                sorted(state),
                ["candidates", "metadata", "reason", "status"],
            )
            self.assertIsInstance(state["metadata"], dict)

    def test_fetch_http_and_json_failures_resolve_unavailable(self):
        expected_reasons = {
            "fetch_failed": "fetch_failed",
            "http_error": "http_error",
            "malformed_json": "invalid_payload",
        }
        for mode, reason in expected_reasons.items():
            with self.subTest(mode=mode):
                state = run_candidate_module(
                    'api.load("candidate_signals.json")',
                    candidate_payload([]),
                    mode,
                )
                self.assertEqual(
                    state,
                    {
                        "status": "unavailable",
                        "candidates": [],
                        "metadata": {},
                        "reason": reason,
                    },
                )
                self.assertNotIn("private", json.dumps(state))

    def test_malformed_and_unsupported_payloads_are_unavailable(self):
        cases = [
            (None, "invalid_payload"),
            ([], "invalid_payload"),
            ({"schema_version": "1.0"}, "invalid_payload"),
            ({"schema_version": "2.0", "candidates": []}, "unsupported_schema"),
            ({"candidates": []}, "unsupported_schema"),
            (
                {"schema_version": "1.0", "candidates": ["bad row"]},
                "invalid_payload",
            ),
        ]
        for payload, reason in cases:
            with self.subTest(payload=payload):
                state = run_candidate_module("api.normalize(input.payload)", payload)
                self.assertEqual(state["status"], "unavailable")
                self.assertEqual(state["reason"], reason)
                self.assertEqual(state["candidates"], [])
                self.assertEqual(state["metadata"], {})

    def test_duplicate_and_missing_candidate_ids_are_rejected(self):
        cases = [
            [candidate_row("same", "One"), candidate_row("same", "Two")],
            [candidate_row("", "One")],
            [candidate_row("   ", "One")],
            [{**candidate_row(), "candidate_id": None}],
        ]
        for candidates in cases:
            with self.subTest(candidates=candidates):
                state = run_candidate_module(
                    "api.normalize(input.payload)",
                    candidate_payload(candidates),
                )
                self.assertEqual(state["status"], "unavailable")
                self.assertEqual(state["reason"], "invalid_payload")

    def test_missing_published_names_are_rejected(self):
        missing = candidate_row()
        missing.pop("candidate_name")
        cases = [
            [missing],
            [candidate_row("alpha", "")],
            [candidate_row("alpha", "   ")],
            [{**candidate_row(), "candidate_name": None}],
        ]
        for candidates in cases:
            with self.subTest(candidates=candidates):
                state = run_candidate_module(
                    "api.normalize(input.payload)",
                    candidate_payload(candidates),
                )
                self.assertEqual(state["status"], "unavailable")
                self.assertEqual(state["reason"], "invalid_payload")

    def test_source_order_and_published_evidence_are_preserved(self):
        rows = [
            candidate_row("zeta", "Zeta"),
            candidate_row("alpha", "Alpha"),
            candidate_row("middle", "Middle"),
        ]
        state = run_candidate_module(
            "api.normalize(input.payload)",
            candidate_payload(rows),
        )
        self.assertEqual(
            [item["candidate_id"] for item in state["candidates"]],
            ["zeta", "alpha", "middle"],
        )
        normalized = state["candidates"][0]
        self.assertEqual(normalized["candidate_name"], "Zeta")
        self.assertEqual(normalized["polling"], rows[0]["polling"])
        self.assertEqual(
            normalized["campaign_attention"],
            rows[0]["campaign_attention"],
        )
        self.assertEqual(
            normalized["general_visibility"],
            rows[0]["general_visibility"],
        )
        self.assertEqual(normalized["scrutiny"], rows[0]["scrutiny"])
        self.assertEqual(
            normalized["latest_development"],
            rows[0]["latest_development"],
        )

    def test_normalization_does_not_mutate_source_objects(self):
        row = candidate_row()
        result = run_candidate_module(
            """(() => {
              const sourceCandidate = input.payload.candidates[0];
              const sourcePolling = sourceCandidate.polling;
              const before = JSON.stringify(input.payload);
              const state = api.normalize(input.payload);
              state.candidates[0].polling.range_min = 999;
              state.metadata.candidate_universe.count = 999;
              return {
                sourceUnchanged: JSON.stringify(input.payload) === before,
                candidateIsNew: state.candidates[0] !== sourceCandidate,
                pollingIsNew: state.candidates[0].polling !== sourcePolling
              };
            })()""",
            candidate_payload([row]),
        )
        self.assertEqual(
            result,
            {
                "sourceUnchanged": True,
                "candidateIsNew": True,
                "pollingIsNew": True,
            },
        )

    def test_missing_optional_evidence_normalizes_to_null_not_zero(self):
        minimal = {
            "candidate_id": "minimal",
            "candidate_name": "Minimal Candidate",
        }
        state = run_candidate_module(
            "api.normalize(input.payload)",
            candidate_payload([minimal]),
        )
        self.assertEqual(state["status"], "ready")
        candidate = state["candidates"][0]
        for field in (
            "polling",
            "campaign_attention",
            "general_visibility",
            "scrutiny",
            "latest_development",
        ):
            self.assertIsNone(candidate[field])
        self.assertNotIn(0, candidate.values())

    def test_current_schema_normalizes_complete_presidential_active_and_poll_history(self):
        payload = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )
        state = run_candidate_module("api.normalize(input.payload)", payload)
        self.assertEqual(state["status"], "ready")
        self.assertEqual(
            len(state["candidates"]),
            payload["candidate_universe"]["count"],
        )
        field = state["metadata"]["presidentialField"]
        self.assertEqual(
            field,
            payload["presidential_field"],
        )
        self.assertTrue(
            all(candidate["candidacy"] for candidate in state["candidates"])
        )
        self.assertEqual(
            [candidate["candidate_id"] for candidate in state["candidates"]],
            [candidate["candidate_id"] for candidate in payload["candidates"]],
        )
        monitoring = state["metadata"]["activeMonitoringField"]
        self.assertEqual(
            monitoring,
            payload["active_monitoring_field"],
        )
        self.assertEqual(
            monitoring["counts"]["active"],
            len(monitoring["main"]) + len(monitoring["secondary"]),
        )

        active = state["metadata"]["activeFieldVisibility"]
        self.assertEqual(active, payload["active_field_visibility"])
        self.assertEqual(active["method"], "share_of_active_candidate_linked_records")
        self.assertEqual(
            active["denominator_scope"],
            "records_linked_to_at_least_one_active_monitoring_candidate",
        )
        for scope_name in ("primary", "general"):
            scope = active[scope_name]
            quality = scope["comparison_quality"]
            self.assertEqual(
                quality["current_record_count"],
                scope["current_period"]["record_count"],
            )
            self.assertEqual(
                quality["prior_record_count"],
                scope["prior_period"]["record_count"],
            )
            if quality["status"] == "comparable":
                self.assertEqual(quality["reason"], "comparable")
            else:
                self.assertIn(
                    quality["reason"],
                    {"insufficient_data", "publisher_panel_changed"},
                )
                self.assertTrue(
                    all(
                        row["share_change"] is None
                        for tier in ("main", "secondary")
                        for row in scope[tier]
                    )
                )

        self.assertEqual(payload["schema_version"], "1.5")
        normalized_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in state["candidates"]
        }
        for source_candidate in payload["candidates"]:
            self.assertEqual(
                normalized_by_id[source_candidate["candidate_id"]]["poll_history"],
                source_candidate["poll_history"],
            )

    def test_schema_15_isolates_malformed_or_missing_optional_poll_history(self):
        base = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )
        reported_index = next(
            index
            for index, candidate in enumerate(base["candidates"])
            if candidate["poll_history"]["observation_count"] > 1
        )

        cases = []

        bad_count = json.loads(json.dumps(base))
        bad_count["candidates"][reported_index]["poll_history"][
            "observation_count"
        ] += 1
        cases.append(("count_mismatch", bad_count))

        bad_range = json.loads(json.dumps(base))
        observation = bad_range["candidates"][reported_index][
            "poll_history"
        ]["observations"][0]
        observation["selected_score"] = observation["range_max"] + 1
        cases.append(("selected_score_outside_range", bad_range))

        duplicate_url = json.loads(json.dumps(base))
        urls = duplicate_url["candidates"][reported_index][
            "poll_history"
        ]["observations"][0]["source_urls"]
        urls.append(urls[0])
        cases.append(("duplicate_source_url", duplicate_url))

        bad_package = json.loads(json.dumps(base))
        bad_package["candidates"][reported_index]["poll_history"][
            "observations"
        ][0]["package_key"] = "[]"
        cases.append(("package_key_mismatch", bad_package))

        bad_order = json.loads(json.dumps(base))
        bad_order["candidates"][reported_index]["poll_history"][
            "observations"
        ].reverse()
        cases.append(("non_chronological", bad_order))

        missing = json.loads(json.dumps(base))
        missing["candidates"][reported_index].pop("poll_history")
        cases.append(("missing", missing))

        for label, payload in cases:
            with self.subTest(case=label):
                state = run_candidate_module(
                    "api.normalize(input.payload)",
                    payload,
                )
                self.assertEqual(state["status"], "ready")
                self.assertIsNone(state["reason"])
                candidate_id = base["candidates"][reported_index][
                    "candidate_id"
                ]
                normalized = next(
                    candidate
                    for candidate in state["candidates"]
                    if candidate["candidate_id"] == candidate_id
                )
                self.assertIsNone(normalized["poll_history"])
                self.assertEqual(
                    normalized["polling"],
                    base["candidates"][reported_index]["polling"],
                )
                self.assertEqual(
                    normalized["agenda_profile"],
                    base["candidates"][reported_index]["agenda_profile"],
                )

    def test_schema_12_accepts_dynamic_candidate_and_tier_counts(self):
        tier_sets = (
            ("main", "main", "secondary", "hidden"),
            ("main", "secondary", "secondary", "secondary", "hidden"),
            tuple(["main"] * 9 + ["secondary"] * 8 + ["hidden"] * 8),
        )
        for tiers in tier_sets:
            with self.subTest(tiers=tiers):
                payload = dynamic_schema_12_payload(tiers)
                state = run_candidate_module(
                    "api.normalize(input.payload)",
                    payload,
                )
                self.assertEqual(state["status"], "ready")
                self.assertEqual(len(state["candidates"]), len(tiers))
                counts = state["metadata"]["presidentialField"]["counts"]
                self.assertEqual(counts["main"], tiers.count("main"))
                self.assertEqual(
                    counts["secondary"], tiers.count("secondary")
                )
                self.assertEqual(counts["hidden"], tiers.count("hidden"))
                self.assertEqual(
                    counts["active"],
                    counts["main"] + counts["secondary"],
                )
                self.assertEqual(counts["total"], len(tiers))

    def test_schema_12_dynamic_count_inconsistencies_still_reject(self):
        base = dynamic_schema_12_payload()
        cases = []
        total = json.loads(json.dumps(base))
        total["presidential_field"]["counts"]["total"] += 1
        cases.append(total)
        active = json.loads(json.dumps(base))
        active["presidential_field"]["counts"]["active"] += 1
        cases.append(active)
        tier_total = json.loads(json.dumps(base))
        tier_total["presidential_field"]["counts"]["hidden"] += 1
        cases.append(tier_total)
        missing_membership = json.loads(json.dumps(base))
        missing_membership["presidential_field"]["secondary"].pop()
        cases.append(missing_membership)

        for payload in cases:
            with self.subTest(counts=payload["presidential_field"]["counts"]):
                state = run_candidate_module(
                    "api.normalize(input.payload)",
                    payload,
                )
                self.assertEqual(state["status"], "unavailable")
                self.assertEqual(state["reason"], "invalid_payload")

    def test_schema_12_rejects_invalid_tier_membership_counts_and_eligibility(self):
        base = dynamic_schema_12_payload()
        cases = []
        duplicate = json.loads(json.dumps(base))
        duplicate["presidential_field"]["secondary"].append(
            duplicate["presidential_field"]["main"][0]
        )
        duplicate["presidential_field"]["counts"]["secondary"] += 1
        duplicate["presidential_field"]["counts"]["active"] += 1
        duplicate["presidential_field"]["counts"]["total"] += 1
        cases.append(duplicate)
        unknown = json.loads(json.dumps(base))
        unknown["presidential_field"]["main"][0] = "unknown-candidate"
        cases.append(unknown)
        missing = json.loads(json.dumps(base))
        missing["presidential_field"]["main"].pop()
        missing["presidential_field"]["counts"]["main"] -= 1
        missing["presidential_field"]["counts"]["active"] -= 1
        missing["presidential_field"]["counts"]["total"] -= 1
        cases.append(missing)
        counts = json.loads(json.dumps(base))
        counts["presidential_field"]["counts"]["active"] = 20
        cases.append(counts)
        eligibility = json.loads(json.dumps(base))
        eligibility["candidates"][0]["candidacy"][
            "active_field_eligible"
        ] = not eligibility["candidates"][0]["candidacy"][
            "active_field_eligible"
        ]
        cases.append(eligibility)
        mismatch = json.loads(json.dumps(base))
        mismatch["candidates"][0]["candidacy"]["display_tier"] = "hidden"
        mismatch["candidates"][0]["candidacy"][
            "active_field_eligible"
        ] = False
        cases.append(mismatch)
        for payload in cases:
            with self.subTest(payload=payload["presidential_field"]):
                state = run_candidate_module(
                    "api.normalize(input.payload)",
                    payload,
                )
                self.assertEqual(state["status"], "unavailable")
                self.assertEqual(state["reason"], "invalid_payload")

    def test_schema_12_rejects_malformed_active_projection(self):
        base = dynamic_schema_12_payload()
        cases = []
        hidden = json.loads(json.dumps(base))
        hidden["active_field_visibility"]["primary"]["secondary"][0][
            "candidate_id"
        ] = "sarah-knafo"
        cases.append(hidden)
        duplicate = json.loads(json.dumps(base))
        duplicate["active_field_visibility"]["primary"]["secondary"][0] = (
            duplicate["active_field_visibility"]["primary"]["main"][0]
        )
        cases.append(duplicate)
        denominator = json.loads(json.dumps(base))
        denominator["active_field_visibility"]["primary"]["current_period"][
            "record_count"
        ] = 122
        cases.append(denominator)
        share = json.loads(json.dumps(base))
        share["active_field_visibility"]["general"]["main"][0][
            "current_share"
        ] = 0.999
        cases.append(share)
        fabricated_delta = json.loads(json.dumps(base))
        fabricated_delta["active_field_visibility"]["primary"]["main"][0][
            "share_change"
        ] = 0
        cases.append(fabricated_delta)
        missing = json.loads(json.dumps(base))
        missing["active_field_visibility"]["general"]["secondary"].pop()
        cases.append(missing)
        tier = json.loads(json.dumps(base))
        tier["active_field_visibility"]["general"]["main"][0][
            "display_tier"
        ] = "secondary"
        cases.append(tier)
        quality = json.loads(json.dumps(base))
        quality_state = quality["active_field_visibility"]["primary"][
            "comparison_quality"
        ]
        quality_state["status"] = (
            "not_comparable"
            if quality_state["status"] == "comparable"
            else "comparable"
        )
        cases.append(quality)
        ordering = json.loads(json.dumps(base))
        ordering["active_field_visibility"]["general"]["main"][0:2] = reversed(
            ordering["active_field_visibility"]["general"]["main"][0:2]
        )
        cases.append(ordering)

        for index, payload in enumerate(cases):
            with self.subTest(case=index):
                state = run_candidate_module("api.normalize(input.payload)", payload)
                self.assertEqual(state["status"], "unavailable")
                self.assertEqual(state["reason"], "invalid_payload")

    def test_schema_11_does_not_fabricate_active_projection(self):
        payload = json.loads(
            (ROOT / "candidate_signals.json").read_text(encoding="utf-8")
        )
        payload["schema_version"] = "1.1"
        payload.pop("active_field_visibility")
        payload.pop("active_monitoring_field")

        payload["presidential_field"]["counts"]["active"] = (
            len(payload["presidential_field"]["main"])
            + len(payload["presidential_field"]["secondary"])
        )

        for candidate in payload["candidates"]:
            candidate["candidacy"].pop(
                "upstream_presence",
                None,
            )
            candidate["candidacy"]["active_field_eligible"] = (
                candidate["candidacy"]["display_tier"] != "hidden"
            )

        state = run_candidate_module("api.normalize(input.payload)", payload)
        self.assertEqual(state["status"], "ready")
        self.assertIsNone(state["metadata"]["activeMonitoringField"])
        self.assertIsNone(state["metadata"]["activeFieldVisibility"])

    def test_schema_10_retains_evidence_without_fabricating_active_field(self):
        payload = candidate_payload([candidate_row()], schema_version="1.0")
        state = run_candidate_module("api.normalize(input.payload)", payload)
        self.assertEqual(state["status"], "ready")
        self.assertIsNone(state["metadata"]["presidentialField"])
        self.assertIsNone(state["candidates"][0]["candidacy"])
        self.assertEqual(state["candidates"][0]["polling"], payload["candidates"][0]["polling"])

    def test_no_scoring_or_visual_renderer_is_introduced(self):
        self.assertIn(".sort(activeRowOrder)", self.candidate_js)
        self.assertNotRegex(
            self.candidate_js.lower(),
            r"\b(momentum|viability|sentiment|probability|forecast)\b",
        )
        self.assertNotRegex(
            self.candidate_js,
            r"\b(render|matrix|dossier|card)\w*\s*\(",
        )
        self.assertNotIn("document.", self.candidate_js)
        self.assertNotIn("querySelector", self.candidate_js)
        self.assertNotIn("combined_score", self.candidate_js)
        self.assertNotIn("composite", self.candidate_js.lower())

    def test_candidate_signals_loads_once_during_initialization_not_tabs(self):
        result = run_hybrid_candidate_integration(
            "resolve",
            """(() => {
              api.setActiveSignalView("events");
              api.setActiveSignalView("candidates");
              api.setActiveSignalView("candidates");
              return { loadCount, loadedUrls };
            })()""",
        )
        self.assertEqual(
            result,
            {"loadCount": 1, "loadedUrls": ["candidate_signals.json"]},
        )
        self.assertEqual(
            self.hybrid_js.count('.load("candidate_signals.json")'),
            1,
        )
        interaction_start = self.hybrid_js.index(
            "  function bindInteractions()"
        )
        interaction_end = self.hybrid_js.index(
            "  function renderTopMediaPulsePanel(", interaction_start
        )
        self.assertNotIn(
            "candidate_signals.json",
            self.hybrid_js[interaction_start:interaction_end],
        )

    def test_agenda_history_loads_once_during_initialization_not_tabs(self):
        result = run_hybrid_candidate_integration(
            "resolve",
            """(() => {
              api.setActiveSignalView("events");
              api.setActiveSignalView("candidates");
              api.setActiveSignalView("candidates");
              return { agendaLoadCount, agendaLoadedUrls };
            })()""",
        )
        self.assertEqual(result, {
            "agendaLoadCount": 1,
            "agendaLoadedUrls": ["candidate_agenda_history.json"],
        })
        self.assertEqual(
            self.hybrid_js.count(
                '.load("candidate_agenda_history.json")'
            ),
            1,
        )
        interaction_start = self.hybrid_js.index(
            "  function bindInteractions()"
        )
        interaction_end = self.hybrid_js.index(
            "  function renderTopMediaPulsePanel(", interaction_start
        )
        self.assertNotIn(
            "candidate_agenda_history.json",
            self.hybrid_js[interaction_start:interaction_end],
        )
        self.assertNotIn("fetch(", self.hybrid_js[
            self.hybrid_js.index("const candidateAgendaHistoryRequest"):
            self.hybrid_js.index(
                "  const number = value", self.hybrid_js.index(
                    "const candidateAgendaHistoryRequest"
                )
            )
        ])

    def test_candidate_failure_isolated_from_dashboard_initialization(self):
        result = run_hybrid_candidate_integration(
            "reject",
            """({
              apiReady: !!api,
              loadCount,
              stateAttribute:
                candidateRoot.attributes["data-candidate-signals-state"]
            })""",
        )
        self.assertEqual(
            result,
            {
                "apiReady": True,
                "loadCount": 1,
                "stateAttribute": "unavailable",
            },
        )
        self.assertIn(".catch(() => {", self.hybrid_js)

    def test_loading_scaffold_and_state_attribute_contract(self):
        workspace = run_router_script(
            "",
            """api.renderFocusWorkspace({
              runoff: { state: "empty", message: "runoff" },
              events: { state: "empty", message: "events" },
              agenda: { state: "empty", message: "agenda" },
              issues: { state: "empty", message: "issues" },
              claims: { state: "empty", message: "claims" }
            })""",
        )
        self.assertEqual(workspace.count('aria-label="Loading candidate evidence"'), 1)
        self.assertNotIn("Loading candidate evidence…", workspace)
        self.assertNotIn("candidate-signals-header", workspace)
        self.assertNotIn(
            "Candidate evidence will be rendered in the next implementation stage.",
            workspace,
        )
        attribute = re.search(
            r'data-candidate-signals-state="([^"]+)"',
            workspace,
        )
        self.assertIsNotNone(attribute)
        self.assertEqual(attribute.group(1), "loading")
        allowed = {"loading", "ready", "empty", "unavailable"}
        module_values = run_candidate_module("Object.values(api.STATES)")
        self.assertEqual(set(module_values), allowed)


if __name__ == "__main__":
    unittest.main()
